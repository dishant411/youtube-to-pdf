from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence

from app.formatting import build_output_stem, build_timestamped_paragraphs
from app.models import VideoReference
from app.openai_summary import SummaryGenerationError, summarize_transcript
from app.pdf import render_pdf, render_summary_pdf
from app.youtube import (
    TranscriptUnavailableError,
    VideoValidationError,
    dedupe_references,
    fetch_transcript_data,
    fetch_video_title,
    parse_video_reference,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert YouTube videos into summary or transcript PDFs.")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--url", help="One accepted YouTube video URL.")
    source_group.add_argument("--batch-file", help="Path to a UTF-8 file containing one URL per line.")
    parser.add_argument("--output-dir", required=True, help="Directory where output files should be written.")
    parser.add_argument(
        "--mode",
        choices=["summary", "transcript"],
        default="summary",
        help="Generate a summary PDF or the legacy full transcript PDF.",
    )
    return parser


def _read_batch_lines(batch_file: Path) -> List[str]:
    lines = []
    for raw_line in batch_file.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def _remove_legacy_json_outputs(output_dir: Path) -> None:
    for path in output_dir.glob("*.json"):
        if path.is_file():
            path.unlink()


def _resolve_pdf_path(output_dir: Path, title: str) -> Path:
    base_stem = build_output_stem(title)
    candidate = output_dir / "{stem}.pdf".format(stem=base_stem)
    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        candidate = output_dir / "{stem}-{suffix}.pdf".format(stem=base_stem, suffix=suffix)
        if not candidate.exists():
            return candidate
        suffix += 1


def _process_reference(reference: VideoReference, output_dir: Path, generated_at: str, mode: str) -> None:
    print(
        "Processing {url} in {mode} mode...".format(url=reference.canonical_url, mode=mode),
        file=sys.stderr,
    )
    segments, language = fetch_transcript_data(reference.video_id)
    title = fetch_video_title(reference.canonical_url) or "video"
    pdf_path = _resolve_pdf_path(output_dir, title)

    if mode == "transcript":
        print("Rendering transcript PDF for {title}...".format(title=title), file=sys.stderr)
        paragraphs = build_timestamped_paragraphs(segments)
        render_pdf(
            output_path=pdf_path,
            title=title,
            canonical_url=reference.canonical_url,
            language=language,
            generated_at=generated_at,
            paragraphs=paragraphs,
        )
        print("Wrote PDF: {path}".format(path=pdf_path), file=sys.stderr)
        return

    print("Generating executive summary for {title}...".format(title=title), file=sys.stderr)
    summary_text, model = summarize_transcript(
        title=title,
        canonical_url=reference.canonical_url,
        segments=segments,
    )
    print("Rendering summary PDF for {title}...".format(title=title), file=sys.stderr)
    render_summary_pdf(
        output_path=pdf_path,
        title=title,
        canonical_url=reference.canonical_url,
        generated_at=generated_at,
        model=model,
        summary_text=summary_text,
    )
    print("Wrote PDF: {path}".format(path=pdf_path), file=sys.stderr)


def _resolve_references(source_inputs: Sequence[str]) -> tuple[List[VideoReference], List[str]]:
    references = []
    failures = []
    for raw_input in source_inputs:
        try:
            references.append(parse_video_reference(raw_input))
        except VideoValidationError as exc:
            failures.append("{input_value}: {message}".format(input_value=raw_input, message=exc))
    return references, failures


def _record_duplicate_skips(references: Sequence[VideoReference]) -> List[str]:
    results = []
    seen = set()
    for reference in references:
        if reference.video_id in seen:
            results.append(reference.raw_input)
        else:
            seen.add(reference.video_id)
    return results


def run_single(url: str, output_dir: Path, generated_at: str, mode: str) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    _remove_legacy_json_outputs(output_dir)
    print("Starting single video job...", file=sys.stderr)

    try:
        reference = parse_video_reference(url)
        _process_reference(reference, output_dir, generated_at, mode)
        return 0
    except VideoValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except TranscriptUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except SummaryGenerationError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def run_batch(batch_file: Path, output_dir: Path, generated_at: str, mode: str) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    _remove_legacy_json_outputs(output_dir)
    print("Starting batch job from {path}...".format(path=batch_file), file=sys.stderr)

    if not batch_file.exists() or not batch_file.is_file():
        print("Batch file does not exist or is not a file.", file=sys.stderr)
        return 1

    try:
        source_inputs = _read_batch_lines(batch_file)
    except OSError as exc:
        print("Batch file could not be read: {message}".format(message=exc), file=sys.stderr)
        return 1

    references, failures = _resolve_references(source_inputs)
    for failure in failures:
        print(failure, file=sys.stderr)
    for duplicate in _record_duplicate_skips(references):
        print("Skipping duplicate URL: {duplicate}".format(duplicate=duplicate), file=sys.stderr)

    for reference in dedupe_references(references):
        try:
            _process_reference(reference, output_dir, generated_at, mode)
        except TranscriptUnavailableError as exc:
            print(
                "Skipping {url}: {message}".format(url=reference.raw_input, message=exc),
                file=sys.stderr,
            )
        except SummaryGenerationError as exc:
            print(
                "Skipping {url}: {message}".format(url=reference.raw_input, message=exc),
                file=sys.stderr,
            )

    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    generated_at = datetime.now(timezone.utc).isoformat()

    if args.url:
        return run_single(args.url, output_dir, generated_at, args.mode)
    return run_batch(Path(args.batch_file).expanduser().resolve(), output_dir, generated_at, args.mode)


if __name__ == "__main__":
    sys.exit(main())
