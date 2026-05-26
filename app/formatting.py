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


NOISE_PATTERNS = [
    re.compile(r"^\[(music|applause|laughter|silence|background music)\]$", re.IGNORECASE),
    re.compile(r"^\((music|applause|laughter|silence|background music)\)$", re.IGNORECASE),
]
FILLER_ONLY_RE = re.compile(
    r"^(uh|um|hmm|mm-hmm|mm|ah|er|you know|like|so|okay|ok|right|well)[.!?]*$",
    re.IGNORECASE,
)


def is_low_signal_segment(text: str) -> bool:
    cleaned = clean_segment_text(text)
    if not cleaned:
        return True
    if any(pattern.match(cleaned) for pattern in NOISE_PATTERNS):
        return True
    if len(cleaned.split()) <= 3 and FILLER_ONLY_RE.match(cleaned):
        return True
    return False


def clean_transcript_segments(
    segments: Iterable[TranscriptSegment],
    drop_low_signal: bool = True,
    dedupe_adjacent: bool = True,
) -> List[TranscriptSegment]:
    cleaned_segments = []
    previous_text = None

    for segment in segments:
        cleaned_text = clean_segment_text(segment.text)
        if not cleaned_text:
            continue
        if drop_low_signal and is_low_signal_segment(cleaned_text):
            continue
        if dedupe_adjacent and previous_text == cleaned_text:
            continue
        cleaned_segments.append(
            TranscriptSegment(text=cleaned_text, start=max(0.0, segment.start), duration=max(0.0, segment.duration))
        )
        previous_text = cleaned_text

    return cleaned_segments


def build_summary_blocks(
    segments: Iterable[TranscriptSegment],
    pause_threshold: float = 8.0,
    max_block_length: int = 900,
    timestamp_interval_seconds: int = 180,
    preserve_timestamps: bool = True,
) -> List[Tuple[Optional[str], str]]:
    blocks = []
    current_text = ""
    current_label = None
    previous_end = None
    last_timestamp_start = None

    for segment in clean_transcript_segments(segments):
        should_break = False
        if previous_end is not None and segment.start - previous_end >= pause_threshold:
            should_break = True
        if current_text and len(current_text) >= max_block_length:
            should_break = True
        if (
            preserve_timestamps
            and current_text
            and last_timestamp_start is not None
            and segment.start - last_timestamp_start >= timestamp_interval_seconds
        ):
            should_break = True

        if should_break and current_text:
            blocks.append((current_label, current_text))
            current_text = ""
            current_label = None

        if not current_text and preserve_timestamps:
            if last_timestamp_start is None or segment.start - last_timestamp_start >= timestamp_interval_seconds:
                current_label = format_timestamp(segment.start)
                last_timestamp_start = segment.start

        current_text = join_with_spacing(current_text, segment.text)
        previous_end = segment.start + segment.duration

    if current_text:
        blocks.append((current_label, current_text))

    return blocks


def blocks_to_compact_text(blocks: Iterable[Tuple[Optional[str], str]]) -> str:
    formatted_blocks = []
    for timestamp_label, paragraph in blocks:
        if timestamp_label:
            formatted_blocks.append("[{label}] {paragraph}".format(label=timestamp_label, paragraph=paragraph))
        else:
            formatted_blocks.append(paragraph)
    return "\n\n".join(formatted_blocks)


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
