from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Tuple


def _wrap_word(
    word: str,
    max_width: float,
    font_name: str,
    font_size: int,
    string_width,
) -> List[str]:
    if not word:
        return [word]
    chunks = []
    current = ""
    for char in word:
        candidate = current + char
        if current and string_width(candidate, font_name, font_size) > max_width:
            chunks.append(current)
            current = char
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [word]


def _wrap_text(
    text: str,
    max_width: float,
    font_name: str,
    font_size: int,
    string_width,
) -> List[str]:
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        fragments = _wrap_word(word, max_width, font_name, font_size, string_width)
        for fragment in fragments:
            candidate = fragment if not current else current + " " + fragment
            if current and string_width(candidate, font_name, font_size) > max_width:
                lines.append(current)
                current = fragment
            else:
                current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _register_body_font(ttfonts, pdfmetrics) -> str:
    try:
        font_path = None
        try:
            import reportlab

            font_path = Path(reportlab.__file__).resolve().parent / "fonts" / "Vera.ttf"
        except Exception:
            font_path = None
        if font_path and font_path.exists():
            font_name = "VeraBody"
            if font_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(ttfonts.TTFont(font_name, str(font_path)))
            return font_name
    except Exception:
        pass
    return "Times-Roman"


def render_pdf(
    output_path: Path,
    title: str,
    canonical_url: str,
    language: Optional[str],
    generated_at: str,
    paragraphs: Iterable[Tuple[Optional[str], str]],
) -> None:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase import ttfonts
    from reportlab.pdfgen import canvas

    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_width, page_height = LETTER
    margin = 0.75 * inch
    body_font = _register_body_font(ttfonts, pdfmetrics)
    body_size = 11
    timestamp_font = "Courier-Bold"
    timestamp_size = 9
    title_font = "Times-Bold"
    title_size = 18
    meta_size = 9
    line_height = 14
    paragraph_gap = 10
    usable_width = page_width - (2 * margin)
    top_y = page_height - margin
    bottom_y = margin

    pdf = canvas.Canvas(str(output_path), pagesize=LETTER, pageCompression=0)
    page_number = 1

    def draw_footer(current_page: int) -> None:
        pdf.setFont("Times-Roman", 9)
        pdf.drawRightString(page_width - margin, 0.5 * inch, "Page {page}".format(page=current_page))

    def new_page() -> float:
        nonlocal page_number
        draw_footer(page_number)
        pdf.showPage()
        page_number += 1
        return top_y

    y_position = top_y
    pdf.setTitle(title)
    pdf.setAuthor("youtube-to-pdf")

    pdf.setFont(title_font, title_size)
    for line in _wrap_text(title, usable_width, title_font, title_size, pdfmetrics.stringWidth):
        pdf.drawString(margin, y_position, line)
        y_position -= 24

    pdf.setFont("Times-Roman", meta_size)
    metadata_lines = [
        "Source: {url}".format(url=canonical_url),
        "Transcript language: {language}".format(language=language or "unknown"),
        "Generated: {generated_at}".format(generated_at=generated_at),
    ]
    for line in metadata_lines:
        if y_position <= bottom_y + line_height:
            y_position = new_page()
            pdf.setFont("Times-Roman", meta_size)
        for wrapped in _wrap_text(line, usable_width, "Times-Roman", meta_size, pdfmetrics.stringWidth):
            pdf.drawString(margin, y_position, wrapped)
            y_position -= 12

    y_position -= 12
    for timestamp_label, paragraph in paragraphs:
        if timestamp_label:
            if y_position <= bottom_y + line_height:
                y_position = new_page()
            pdf.setFont(timestamp_font, timestamp_size)
            pdf.drawString(margin, y_position, "[{label}]".format(label=timestamp_label))
            y_position -= 12

        pdf.setFont(body_font, body_size)
        for line in _wrap_text(paragraph, usable_width, body_font, body_size, pdfmetrics.stringWidth):
            if y_position <= bottom_y + line_height:
                y_position = new_page()
                pdf.setFont(body_font, body_size)
            pdf.drawString(margin, y_position, line)
            y_position -= line_height
        y_position -= paragraph_gap

    draw_footer(page_number)
    pdf.save()
