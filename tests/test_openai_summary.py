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

        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "your_test_openai_key"}, clear=True):
            with mock.patch("app.openai_summary.urlopen", return_value=FakeResponse()) as mocked_urlopen:
                summary_text, model = summarize_transcript(
                    title="Video",
                    canonical_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    segments=[TranscriptSegment(text="Hello world.", start=0.0, duration=1.0)],
                )

        self.assertIn("Executive Summary", summary_text)
        self.assertEqual(model, "gpt-5.4-nano")
        self.assertEqual(mocked_urlopen.call_count, 1)

    def test_hindi_transcript_is_summarized_before_translation(self) -> None:
        with mock.patch("app.openai_summary.request_summary_text") as request_text:
            request_text.side_effect = [
                ("## कार्यकारी सारांश\nहिंदी सारांश।", "gpt-5.4-nano"),
                ("## Executive Summary\nEnglish summary.", "gpt-5.4-nano"),
            ]
            summary_text, model = summarize_transcript(
                title="Hindi Video",
                canonical_url="https://www.youtube.com/watch?v=kKNoBH0iE1k",
                segments=[TranscriptSegment(text="नमस्ते सभी लोग।", start=0.0, duration=1.0)],
                language="hi",
            )

        self.assertIn("English summary", summary_text)
        self.assertEqual(model, "gpt-5.4-nano")
        self.assertEqual(request_text.call_count, 2)
        source_summary_prompt = request_text.call_args_list[0].args[0]
        translation_prompt = request_text.call_args_list[1].args[0]
        self.assertIn("Create a concise executive summary", source_summary_prompt)
        self.assertIn("नमस्ते", source_summary_prompt)
        self.assertIn("Translate this video summary into polished professional English", translation_prompt)
        self.assertIn("Source language: hi", translation_prompt)
        self.assertIn("हिंदी सारांश", translation_prompt)


if __name__ == "__main__":
    unittest.main()
