from __future__ import annotations

import unittest

from app.formatting import build_output_stem, build_timestamped_paragraphs, regroup_segments, sanitize_title
from app.models import TranscriptSegment


class FormattingTests(unittest.TestCase):
    def test_regroups_segments_on_long_pause(self) -> None:
        segments = [
            TranscriptSegment(text="Hello", start=0.0, duration=1.0),
            TranscriptSegment(text="world.", start=1.2, duration=1.0),
            TranscriptSegment(text="Second paragraph.", start=8.5, duration=1.0),
        ]
        paragraphs = regroup_segments(segments)
        self.assertEqual(paragraphs, ["Hello world.", "Second paragraph."])

    def test_removes_duplicate_consecutive_segments(self) -> None:
        segments = [
            TranscriptSegment(text="Repeat", start=0.0, duration=1.0),
            TranscriptSegment(text="Repeat", start=1.0, duration=1.0),
            TranscriptSegment(text="End", start=2.5, duration=1.0),
        ]
        paragraphs = regroup_segments(segments, pause_threshold=10.0)
        self.assertEqual(paragraphs, ["Repeat End"])

    def test_preserves_untrusted_text_as_literal_text(self) -> None:
        segments = [
            TranscriptSegment(text="<script>alert(1)</script>", start=0.0, duration=1.0),
            TranscriptSegment(text="$(rm -rf /) **bold**", start=1.0, duration=1.0),
        ]
        paragraphs = regroup_segments(segments, pause_threshold=10.0)
        self.assertEqual(paragraphs[0], "<script>alert(1)</script> $(rm -rf /) **bold**")

    def test_sanitizes_dangerous_titles(self) -> None:
        title = "../../DROP TABLE users; 你好"
        self.assertEqual(sanitize_title(title), "drop-table-users")

    def test_build_output_stem_uses_clean_title_only(self) -> None:
        stem = build_output_stem("Hello / World")
        self.assertEqual(stem, "hello-world")

    def test_build_timestamped_paragraphs_adds_five_minute_markers(self) -> None:
        segments = [
            TranscriptSegment(text="Opening words.", start=0.0, duration=1.0),
            TranscriptSegment(text="Crossed five minutes.", start=301.0, duration=1.0),
            TranscriptSegment(text="More text.", start=302.0, duration=1.0),
        ]
        paragraphs = build_timestamped_paragraphs(segments)
        self.assertEqual(paragraphs[0], (None, "Opening words."))
        self.assertEqual(paragraphs[1], ("00:05:00", "Crossed five minutes. More text."))


if __name__ == "__main__":
    unittest.main()
