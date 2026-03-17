from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from app.pdf import render_pdf


@unittest.skipUnless(importlib.util.find_spec("reportlab"), "reportlab is required for PDF rendering tests")
class PdfRenderingTests(unittest.TestCase):
    def test_render_pdf_creates_multi_page_output(self) -> None:
        paragraphs = [
            " ".join(["This is a long paragraph with readable transcript text."] * 40)
            for _ in range(25)
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.pdf"
            render_pdf(
                output_path=output_path,
                title="Transcript Title",
                canonical_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                language="en",
                generated_at="2025-03-16T00:00:00+00:00",
                paragraphs=[(None, paragraph) for paragraph in paragraphs],
            )

            self.assertTrue(output_path.exists())
            pdf_bytes = output_path.read_bytes()
            self.assertIn(b"%PDF", pdf_bytes[:16])
            self.assertGreater(pdf_bytes.count(b"/Type /Page"), 1)


if __name__ == "__main__":
    unittest.main()
