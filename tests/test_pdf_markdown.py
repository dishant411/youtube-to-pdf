from __future__ import annotations

import importlib.util
import unittest

from app.pdf import _markdown_to_summary_blocks


class PdfMarkdownTests(unittest.TestCase):
    def test_markdown_parser_converts_bold_in_paragraphs_and_lists(self) -> None:
        if importlib.util.find_spec("markdown") is None:
            self.skipTest("markdown package is not installed in this environment")

        blocks = _markdown_to_summary_blocks(
            "## Executive Summary\n\n**Mental model:** Diplomacy can be theater.\n\n- **Escalation signals contradict negotiation intent.**"
        )

        self.assertEqual(blocks[0], {"type": "heading", "level": 2, "text": "Executive Summary"})
        self.assertEqual(
            blocks[1],
            {"type": "paragraph", "text": "<b>Mental model:</b> Diplomacy can be theater."},
        )
        self.assertEqual(
            blocks[2],
            {
                "type": "list",
                "ordered": False,
                "items": ["<b>Escalation signals contradict negotiation intent.</b>"],
            },
        )


if __name__ == "__main__":
    unittest.main()
