from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoReference:
    raw_input: str
    video_id: str
    canonical_url: str


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start: float
    duration: float
