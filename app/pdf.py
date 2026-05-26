from __future__ import annotations

import html
from html.parser import HTMLParser
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


def _normalize_reportlab_markup(tag: str, content: str) -> str:
    if tag in {"strong", "b"}:
        return "<b>{content}</b>".format(content=content)
    if tag in {"em", "i"}:
        return "<i>{content}</i>".format(content=content)
    if tag == "code":
        return '<font name="Courier">{content}</font>'.format(content=content)
    return content


class _SummaryHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "root", "children": []}
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs) -> None:
        node = {"tag": tag.lower(), "children": []}
        self.stack[-1]["children"].append(node)
        if tag.lower() not in {"br", "hr", "img", "meta", "link", "input"}:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index]["tag"] == normalized:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data:
            self.stack[-1]["children"].append(data)


def _render_inline_html(node: dict[str, object]) -> str:
    parts: List[str] = []
    for child in node.get("children", []):
        if isinstance(child, str):
            parts.append(html.escape(child, quote=False))
            continue
        if isinstance(child, dict):
            child_content = _render_inline_html(child)
            parts.append(_normalize_reportlab_markup(str(child.get("tag", "")).lower(), child_content))
    return "".join(parts)


def _markdown_to_summary_blocks(summary_text: str) -> List[dict[str, object]]:
    import markdown

    rendered_summary = markdown.markdown(
        summary_text or "",
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )
    parser = _SummaryHtmlParser()
    parser.feed(rendered_summary)
    root = parser.root
    blocks: List[dict[str, object]] = []

    for child in root["children"]:
        if not isinstance(child, dict):
            continue
        tag = str(child.get("tag", "")).lower()
        if tag in {"h1", "h2", "h3"}:
            blocks.append({"type": "heading", "level": int(tag[1]), "text": _render_inline_html(child)})
            continue
        if tag == "p":
            blocks.append({"type": "paragraph", "text": _render_inline_html(child)})
            continue
        if tag in {"ul", "ol"}:
            items = []
            for item in child.get("children", []):
                if isinstance(item, dict) and str(item.get("tag", "")).lower() == "li":
                    items.append(_render_inline_html(item))
            blocks.append({"type": "list", "ordered": tag == "ol", "items": items})
            continue
        if tag == "blockquote":
            blocks.append({"type": "blockquote", "text": _render_inline_html(child)})

    return blocks


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


def render_summary_pdf(
    output_path: Path,
    title: str,
    canonical_url: str,
    generated_at: str,
    model: str,
    summary_text: str,
) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase import ttfonts
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    output_path.parent.mkdir(parents=True, exist_ok=True)

    margin = 0.75 * inch
    body_font = _register_body_font(ttfonts, pdfmetrics)
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="SummaryTitle",
            parent=styles["Title"],
            fontName="Times-Bold",
            fontSize=18,
            leading=22,
            spaceAfter=10,
            textColor=colors.black,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SummaryMeta",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=9,
            leading=12,
            spaceAfter=2,
            textColor=colors.HexColor("#444444"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="SummaryBody",
            parent=styles["Normal"],
            fontName=body_font,
            fontSize=11,
            leading=15,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SummaryBlockquote",
            parent=styles["Normal"],
            fontName=body_font,
            fontSize=11,
            leading=15,
            leftIndent=14,
            borderPadding=8,
            borderWidth=0,
            borderColor=colors.HexColor("#d0d5dd"),
            backColor=colors.HexColor("#f8fafc"),
            textColor=colors.HexColor("#344054"),
            spaceBefore=4,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SummaryHeading1",
            parent=styles["Heading1"],
            fontName="Times-Bold",
            fontSize=17,
            leading=20,
            spaceBefore=8,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SummaryHeading2",
            parent=styles["Heading2"],
            fontName="Times-Bold",
            fontSize=13,
            leading=16,
            spaceBefore=6,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SummaryHeading3",
            parent=styles["Heading3"],
            fontName="Times-Bold",
            fontSize=11,
            leading=14,
            spaceBefore=4,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SummaryListItem",
            parent=styles["Normal"],
            fontName=body_font,
            fontSize=11,
            leading=15,
            leftIndent=0,
            spaceAfter=2,
        )
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=title,
        author="youtube-to-pdf",
    )

    story = [
        Paragraph(html.escape(title), styles["SummaryTitle"]),
        Paragraph("Source: {url}".format(url=html.escape(canonical_url)), styles["SummaryMeta"]),
        Paragraph("Generated: {generated_at}".format(generated_at=html.escape(generated_at)), styles["SummaryMeta"]),
        Paragraph("Model: {model}".format(model=html.escape(model)), styles["SummaryMeta"]),
        Spacer(1, 10),
    ]

    heading_style_names = {
        1: "SummaryHeading1",
        2: "SummaryHeading2",
        3: "SummaryHeading3",
    }

    for block in _markdown_to_summary_blocks(summary_text):
        block_type = str(block["type"])
        if block_type == "heading":
            level = int(block["level"])
            story.append(Paragraph(str(block["text"]), styles[heading_style_names.get(level, "SummaryHeading3")]))
            continue
        if block_type == "paragraph":
            story.append(Paragraph(str(block["text"]), styles["SummaryBody"]))
            continue
        if block_type == "blockquote":
            story.append(Paragraph(str(block["text"]), styles["SummaryBlockquote"]))
            continue
        if block_type == "list":
            items = [
                ListItem(Paragraph(str(item), styles["SummaryListItem"]))
                for item in block["items"]
            ]
            story.append(
                ListFlowable(
                    items,
                    bulletType="1" if bool(block["ordered"]) else "bullet",
                    leftIndent=16,
                    bulletFontName=body_font,
                    bulletFontSize=11,
                    bulletOffsetY=2,
                )
            )
            story.append(Spacer(1, 6))

    def draw_footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Times-Roman", 9)
        canvas.drawRightString(doc.pagesize[0] - margin, 0.5 * inch, "Page {page}".format(page=canvas.getPageNumber()))
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
