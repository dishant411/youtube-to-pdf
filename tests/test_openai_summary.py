from __future__ import annotations

import json
import unittest
from unittest import mock

from app.models import TranscriptSegment
from app.openai_summary import SummaryGenerationError, summarize_transcript


class OpenAISummaryTests(unittest.TestCase):
    def test_missing_api_key_fails(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(SummaryGenerationError):
                summarize_transcript(
                    title="Video",
                    canonical_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    segments=[TranscriptSegment(text="Hello world.", start=0.0, duration=1.0)],
                )

    def test_short_transcript_uses_single_executive_summary_call(self) -> None:
        response_payload = json.dumps(
            {
                "output": [
                    {
                        "content": [
                            {
                                "text": "# Video\n## Executive Summary\nShort summary.",
                            }
                        ]
                    }
                ]
            }
        ).encode("utf-8")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return response_payload

        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "secret"}, clear=True):
            with mock.patch("app.openai_summary.urlopen", return_value=FakeResponse()) as mocked_urlopen:
                summary_text, model = summarize_transcript(
                    title="Video",
                    canonical_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    segments=[TranscriptSegment(text="Hello world.", start=0.0, duration=1.0)],
                )

        self.assertIn("Executive Summary", summary_text)
        self.assertEqual(model, "gpt-5.4-nano")
        self.assertEqual(mocked_urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
