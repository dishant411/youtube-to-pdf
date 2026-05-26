from __future__ import annotations

import unittest

from app.formatting import blocks_to_compact_text, build_summary_blocks, clean_transcript_segments
from app.models import TranscriptSegment


class SummaryFormattingTests(unittest.TestCase):
    def test_clean_transcript_segments_drops_noise_and_adjacent_duplicates(self) -> None:
        segments = [
            TranscriptSegment(text="[Music]", start=0.0, duration=1.0),
            TranscriptSegment(text="Hello", start=1.0, duration=1.0),
            TranscriptSegment(text="Hello", start=2.0, duration=1.0),
            TranscriptSegment(text="okay", start=3.0, duration=1.0),
            TranscriptSegment(text="World", start=4.0, duration=1.0),
        ]
        cleaned = clean_transcript_segments(segments)
        self.assertEqual([segment.text for segment in cleaned], ["Hello", "World"])

    def test_build_summary_blocks_preserves_sparse_timestamps(self) -> None:
        segments = [
            TranscriptSegment(text="Opening words.", start=0.0, duration=1.0),
            TranscriptSegment(text="Still intro.", start=2.0, duration=1.0),
            TranscriptSegment(text="Major point.", start=190.0, duration=1.0),
        ]
        blocks = build_summary_blocks(segments, timestamp_interval_seconds=180)
        self.assertEqual(blocks[0][0], "00:00:00")
        self.assertEqual(blocks[1][0], "00:03:10")

    def test_blocks_to_compact_text_formats_timestamped_blocks(self) -> None:
        compact_text = blocks_to_compact_text([("00:00:00", "Hello world."), (None, "Second block.")])
        self.assertEqual(compact_text, "[00:00:00] Hello world.\n\nSecond block.")


if __name__ == "__main__":
    unittest.main()
