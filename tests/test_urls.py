from __future__ import annotations

import unittest
from unittest import mock

from app.models import VideoReference
from app.youtube import VideoValidationError, dedupe_references, fetch_transcript_data, parse_video_reference


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

    def test_fetch_transcript_prefers_english_then_hindi(self) -> None:
        class FakeFetched:
            language_code = "hi"

            def to_raw_data(self):
                return [{"text": "नमस्ते", "start": 0.0, "duration": 1.0}]

        class FakeApi:
            def fetch(self, video_id, languages):
                self.video_id = video_id
                self.languages = languages
                return FakeFetched()

        class FakeApiFactory:
            last_instance = None

            def __call__(self):
                self.last_instance = FakeApi()
                return self.last_instance

        factory = FakeApiFactory()
        youtube_module = __import__("app.youtube", fromlist=["_import_transcript_api"])
        with mock.patch.object(youtube_module, "_import_transcript_api", return_value=factory):
            segments, language = fetch_transcript_data("kKNoBH0iE1k")

        self.assertEqual(language, "hi")
        self.assertEqual(segments[0].text, "नमस्ते")
        self.assertEqual(factory.last_instance.languages, ["en", "hi"])


if __name__ == "__main__":
    unittest.main()
