from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.env_loader import load_repo_env
from app.formatting import blocks_to_compact_text, build_summary_blocks
from app.models import TranscriptSegment

DEFAULT_MODEL = "gpt-5.4-nano"
DEFAULT_TIMEOUT_SECONDS = 60
RESPONSES_API_URL = "https://api.openai.com/v1/responses"
RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "node-backend" / "prompts"

load_repo_env()


class SummaryGenerationError(RuntimeError):
    """Raised when an executive summary cannot be generated."""


def load_prompt_template(file_name: str) -> str:
    prompt_path = PROMPTS_DIR / file_name
    try:
        return prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SummaryGenerationError("Prompt file could not be read: {path}".format(path=prompt_path)) from exc


def render_prompt(file_name: str, variables: dict[str, str]) -> str:
    template = load_prompt_template(file_name)
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def estimate_token_count(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def chunk_text_blocks(
    blocks: Sequence[Tuple[Optional[str], str]],
    max_chunk_chars: int,
) -> List[str]:
    chunks = []
    current_blocks: List[Tuple[Optional[str], str]] = []
    current_length = 0

    for block in blocks:
        block_text = blocks_to_compact_text([block])
        projected_length = len(block_text) if current_length == 0 else current_length + 2 + len(block_text)
        if current_blocks and projected_length > max_chunk_chars:
            chunks.append(blocks_to_compact_text(current_blocks))
            current_blocks = []
            current_length = 0
        current_blocks.append(block)
        current_length = len(block_text) if current_length == 0 else current_length + 2 + len(block_text)

    if current_blocks:
        chunks.append(blocks_to_compact_text(current_blocks))

    return chunks


def chunk_text_items(items: Sequence[str], max_chunk_chars: int) -> List[str]:
    chunks = []
    current_items: List[str] = []
    current_length = 0

    for item in items:
        cleaned = item.strip()
        if not cleaned:
            continue
        projected_length = len(cleaned) if current_length == 0 else current_length + 2 + len(cleaned)
        if current_items and projected_length > max_chunk_chars:
            chunks.append("\n\n".join(current_items))
            current_items = []
            current_length = 0
        current_items.append(cleaned)
        current_length = len(cleaned) if current_length == 0 else current_length + 2 + len(cleaned)

    if current_items:
        chunks.append("\n\n".join(current_items))

    return chunks


def _extract_response_text(payload: dict) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    text_parts = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            text = content.get("text") or content.get("value")
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())

    if not text_parts:
        raise SummaryGenerationError("OpenAI response did not contain text output.")

    return "\n\n".join(text_parts).strip()


def _response_error_message(error_body: Optional[bytes]) -> str:
    if not error_body:
        return "OpenAI request failed."
    try:
        payload = json.loads(error_body.decode("utf-8"))
    except Exception:
        return error_body.decode("utf-8", errors="replace")
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
    return json.dumps(payload, ensure_ascii=True)


def request_summary_text(
    prompt: str,
    model: Optional[str] = None,
    max_output_tokens: int = 700,
    retries: int = 4,
    timeout_seconds: Optional[int] = None,
) -> tuple[str, str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SummaryGenerationError(
            "OPENAI_API_KEY is required for summary generation. Put it in a repo .env file or export it in your shell."
        )

    resolved_model = model or os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL
    timeout = timeout_seconds or int(os.environ.get("OPENAI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    payload = json.dumps(
        {
            "model": resolved_model,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
        }
    ).encode("utf-8")

    attempt = 0
    while True:
        request = Request(
            RESPONSES_API_URL,
            data=payload,
            method="POST",
            headers={
                "Authorization": "Bearer {token}".format(token=api_key),
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
                return _extract_response_text(response_payload), resolved_model
        except HTTPError as exc:
            message = _response_error_message(exc.read())
            if exc.code in RETRYABLE_STATUS_CODES and attempt < retries:
                time.sleep((2**attempt) + 0.2)
                attempt += 1
                continue
            raise SummaryGenerationError(message) from exc
        except URLError as exc:
            if attempt < retries:
                time.sleep((2**attempt) + 0.2)
                attempt += 1
                continue
            raise SummaryGenerationError(str(exc.reason)) from exc


def summarize_transcript(
    title: str,
    canonical_url: str,
    segments: Iterable[TranscriptSegment],
    model: Optional[str] = None,
    max_chunk_chars: int = 7000,
    max_block_length: int = 900,
    timestamp_interval_seconds: int = 180,
    final_input_token_budget: int = 2500,
    chunk_summary_max_output_tokens: int = 260,
    final_summary_max_output_tokens: int = 700,
) -> tuple[str, str]:
    blocks = build_summary_blocks(
        segments,
        max_block_length=max_block_length,
        preserve_timestamps=True,
        timestamp_interval_seconds=timestamp_interval_seconds,
    )
    if not blocks:
        raise SummaryGenerationError("Transcript cleaning removed all usable transcript content.")

    compact_transcript = blocks_to_compact_text(blocks)
    timestamp_guidance = "Use timestamps only when they help the reader jump to a material moment."

    prompt = render_prompt(
        "executive-summary.md",
        {
            "sourceUrl": canonical_url,
            "timestampGuidance": timestamp_guidance,
            "transcriptText": compact_transcript,
            "videoTitle": title,
        },
    )
    return request_summary_text(
        prompt,
        model=model,
        max_output_tokens=final_summary_max_output_tokens,
    )
