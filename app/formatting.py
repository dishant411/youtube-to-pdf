from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Optional, Tuple

from app.models import TranscriptSegment

MULTISPACE_RE = re.compile(r"\s+")
SAFE_SLUG_RE = re.compile(r"[^a-z0-9-]+")
HYPHEN_RE = re.compile(r"-{2,}")


def clean_segment_text(text: str) -> str:
    return MULTISPACE_RE.sub(" ", text.strip())


def join_with_spacing(current: str, addition: str) -> str:
    if not current:
        return addition
    if not addition:
        return current
    if current.endswith("-"):
        return current + addition
    if addition[0] in ",.;:!?)]}":
        return current + addition
    return current + " " + addition


def regroup_segments(
    segments: Iterable[TranscriptSegment],
    pause_threshold: float = 6.0,
    max_paragraph_length: int = 900,
) -> List[str]:
    paragraphs = []
    current_parts = []
    previous_end = None
    previous_text = None

    for segment in segments:
        cleaned = clean_segment_text(segment.text)
        if not cleaned:
            continue
        if previous_text == cleaned:
            previous_end = segment.start + segment.duration
            continue

        should_break = False
        if previous_end is not None and segment.start - previous_end >= pause_threshold:
            should_break = True
        if current_parts and len(" ".join(current_parts)) >= max_paragraph_length:
            should_break = True

        if should_break and current_parts:
            paragraphs.append("".join(current_parts))
            current_parts = []

        if not current_parts:
            current_parts.append(cleaned)
        else:
            current_parts[-1] = join_with_spacing(current_parts[-1], cleaned)

        previous_end = segment.start + segment.duration
        previous_text = cleaned

    if current_parts:
        paragraphs.append("".join(current_parts))

    return paragraphs


def format_timestamp(seconds: float) -> str:
    whole_seconds = max(0, int(seconds))
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return "{hours:02d}:{minutes:02d}:{seconds:02d}".format(
        hours=hours,
        minutes=minutes,
        seconds=secs,
    )


def build_timestamped_paragraphs(
    segments: Iterable[TranscriptSegment],
    pause_threshold: float = 6.0,
    max_paragraph_length: int = 900,
    timestamp_interval_seconds: int = 300,
) -> List[Tuple[Optional[str], str]]:
    paragraphs = []
    current_text = ""
    current_label = None
    previous_end = None
    previous_text = None
    next_timestamp = timestamp_interval_seconds

    for segment in segments:
        cleaned = clean_segment_text(segment.text)
        if not cleaned:
            continue
        if previous_text == cleaned:
            previous_end = segment.start + segment.duration
            continue

        while segment.start >= next_timestamp:
            if current_text:
                paragraphs.append((current_label, current_text))
                current_text = ""
            current_label = format_timestamp(next_timestamp)
            next_timestamp += timestamp_interval_seconds

        should_break = False
        if previous_end is not None and segment.start - previous_end >= pause_threshold:
            should_break = True
        if current_text and len(current_text) >= max_paragraph_length:
            should_break = True

        if should_break and current_text:
            paragraphs.append((current_label, current_text))
            current_text = ""

        current_text = join_with_spacing(current_text, cleaned)
        previous_end = segment.start + segment.duration
        previous_text = cleaned

    if current_text:
        paragraphs.append((current_label, current_text))

    return paragraphs


def sanitize_title(title: str, max_length: int = 80) -> str:
    normalized = unicodedata.normalize("NFKD", title or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower().replace("/", " ").replace("\\", " ")
    lowered = MULTISPACE_RE.sub(" ", lowered).strip()
    slug = lowered.replace(" ", "-")
    slug = SAFE_SLUG_RE.sub("", slug)
    slug = HYPHEN_RE.sub("-", slug).strip("-")
    if not slug:
        return "video"
    return slug[:max_length].rstrip("-") or "video"


def build_output_stem(title: str) -> str:
    return sanitize_title(title)
