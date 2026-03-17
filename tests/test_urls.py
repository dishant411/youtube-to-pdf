from __future__ import annotations

import unittest

from app.models import VideoReference
from app.youtube import VideoValidationError, dedupe_references, parse_video_reference


class UrlParsingTests(unittest.TestCase):
    def test_accepts_watch_url(self) -> None:
        reference = parse_video_reference("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(reference.video_id, "dQw4w9WgXcQ")
        self.assertEqual(reference.canonical_url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_accepts_shorts_url(self) -> None:
        reference = parse_video_reference("https://www.youtube.com/shorts/dQw4w9WgXcQ")
        self.assertEqual(reference.video_id, "dQw4w9WgXcQ")

    def test_accepts_embed_url(self) -> None:
        reference = parse_video_reference("https://www.youtube.com/embed/dQw4w9WgXcQ")
        self.assertEqual(reference.video_id, "dQw4w9WgXcQ")

    def test_accepts_short_link(self) -> None:
        reference = parse_video_reference("https://youtu.be/dQw4w9WgXcQ?t=43")
        self.assertEqual(reference.video_id, "dQw4w9WgXcQ")

    def test_rejects_non_youtube_host(self) -> None:
        with self.assertRaises(VideoValidationError):
            parse_video_reference("https://example.com/watch?v=dQw4w9WgXcQ")

    def test_rejects_playlist_only_url(self) -> None:
        with self.assertRaises(VideoValidationError):
            parse_video_reference("https://www.youtube.com/playlist?list=PL123456789")

    def test_rejects_embedded_url_in_query(self) -> None:
        with self.assertRaises(VideoValidationError):
            parse_video_reference(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ&next=https://evil.example.com/watch?v=abc"
            )

    def test_rejects_invalid_video_id(self) -> None:
        with self.assertRaises(VideoValidationError):
            parse_video_reference("https://www.youtube.com/watch?v=short")

    def test_deduplicates_by_video_id(self) -> None:
        refs = [
            VideoReference("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            VideoReference(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1",
                "dQw4w9WgXcQ",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            ),
        ]
        unique = dedupe_references(refs)
        self.assertEqual(len(unique), 1)


if __name__ == "__main__":
    unittest.main()

