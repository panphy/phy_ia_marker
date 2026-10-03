"""Margin-note annotation of the student's PDF, for the examiner and student downloads.

Notes are drawn into a widened right margin as page content, so every viewer shows and prints
them. Each note is anchored by highlighting its quoted excerpt where the page's text layer
contains it; otherwise it is placed as a page-level note (for example on OCR-only pages).
"""

import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)

NOTE_FONT_SIZE = 7.5
NOTE_LEADING = 9.2
NOTE_PADDING = 4.0
MARGIN_RATIO = 0.42
MIN_MARGIN_WIDTH = 200.0
HIGHLIGHT_ALPHA = 0.33
INK = colors.HexColor("#1f1e1b")
MUTED = colors.HexColor("#6b665c")
LINE = colors.HexColor("#e7e1d4")
PAPER = colors.HexColor("#faf7f0")
HIGHLIGHT = colors.HexColor("#f5d547")

_FONT_CANDIDATES = (
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
)


def _register_fonts() -> tuple[str, str]:
    """Prefer DejaVu Sans, which covers Greek letters and maths symbols; fall back to Helvetica."""
    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            try:
                pdfmetrics.registerFont(TTFont("NoteSans", regular))
                pdfmetrics.registerFont(TTFont("NoteSans-Bold", bold))
                pdfmetrics.registerFontFamily("NoteSans", normal="NoteSans", bold="NoteSans-Bold")
                return "NoteSans", "NoteSans-Bold"
            except Exception as exc:  # a broken font file must not stop the download
                logger.warning("Could not register %s: %s", regular, exc)
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = _register_fonts()


def _safe_text(text: str) -> str:
    """Helvetica cannot draw characters outside Latin-1; replace them rather than fail."""
    if FONT != "Helvetica":
        return text
    return text.encode("latin-1", "replace").decode("latin-1")


@dataclass(frozen=True)
class MarginNote:
    page: int
    quote: str
    note: str
    label: str = ""


@dataclass
class _PlacedNote:
    number: int
    note: MarginNote
    rects: list[tuple[float, float, float, float]]

    @property
    def anchor_top(self) -> float | None:
        return max(rect[3] for rect in self.rects) if self.rects else None


def _search_variants(quote: str) -> list[str]:
    words = " ".join(quote.replace("…", " ").replace("...", " ").split()).split()
    variants = [" ".join(words)]
    for size in (8, 5):
        if len(words) > size:
            variants.append(" ".join(words[:size]))
            variants.append(" ".join(words[-size:]))
    return [variant for variant in dict.fromkeys(variants) if len(variant) >= 8]


def find_quote_rects(textpage: "pdfium.PdfTextPage", quote: str) -> list[tuple[float, float, float, float]]:
    """Rectangles (left, bottom, right, top) of the first match of the quote, or a shorter part of it."""
    for variant in _search_variants(quote):
        searcher = textpage.search(variant, match_case=False)
        try:
            found = searcher.get_next()
        finally:
            searcher.close()
        if found:
            index, count = found
            total = textpage.count_rects(index, count)
            rects = [tuple(textpage.get_rect(i)) for i in range(total)]
            if rects:
                return rects
    return []


def _wrap(text: str, font: str, width: float) -> list[str]:
    return simpleSplit(_safe_text(text), font, NOTE_FONT_SIZE, width) or [""]


def _note_lines(placed: _PlacedNote, width: float) -> tuple[list[str], list[str]]:
    anchor = "" if placed.rects else " (page note)"
    head = f"{placed.number}. {placed.note.label}{anchor}".strip() if placed.note.label else f"{placed.number}.{anchor}"
    return _wrap(head, FONT_BOLD, width), _wrap(placed.note.note, FONT, width)


def _note_height(placed: _PlacedNote, width: float) -> float:
    head, body = _note_lines(placed, width)
    return (len(head) + len(body)) * NOTE_LEADING + 2 * NOTE_PADDING


def _draw_note(pdf: canvas.Canvas, placed: _PlacedNote, x: float, top: float, width: float, accent) -> float:
    head, body = _note_lines(placed, width - 2 * NOTE_PADDING)
    height = (len(head) + len(body)) * NOTE_LEADING + 2 * NOTE_PADDING
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(accent)
    pdf.setLineWidth(0.6)
    pdf.roundRect(x, top - height, width, height, 3, stroke=1, fill=1)
    y = top - NOTE_PADDING - NOTE_FONT_SIZE
    pdf.setFillColor(accent)
    pdf.setFont(FONT_BOLD, NOTE_FONT_SIZE)
    for line in head:
        pdf.drawString(x + NOTE_PADDING, y, line)
        y -= NOTE_LEADING
    pdf.setFillColor(INK)
    pdf.setFont(FONT, NOTE_FONT_SIZE)
    for line in body:
        pdf.drawString(x + NOTE_PADDING, y, line)
        y -= NOTE_LEADING
    return height


def _draw_marker(pdf: canvas.Canvas, number: int, x: float, y: float, accent) -> None:
    pdf.setFillColor(accent)
    pdf.circle(x, y, 5, stroke=0, fill=1)
    pdf.setFillColor(colors.white)
    pdf.setFont(FONT_BOLD, 6)
    pdf.drawCentredString(x, y - 2.1, str(number))


def _overlay_page(
    box: tuple[float, float, float, float],
    margin_left: float,
    placed: list[_PlacedNote],
    title: str,
    accent,
) -> tuple[bytes, list[_PlacedNote]]:
    """Draw highlights and margin notes; return the overlay PDF and the notes that did not fit."""
    left, bottom, right, top = box
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(right, top))
    pdf.setFillColor(PAPER)
    pdf.rect(margin_left, bottom, right - margin_left, top - bottom, stroke=0, fill=1)
    pdf.setStrokeColor(LINE)
    pdf.line(margin_left, bottom, margin_left, top)
    pdf.setFillColor(MUTED)
    pdf.setFont(FONT_BOLD, 6.5)
    pdf.drawString(margin_left + 8, top - 14, _safe_text(title.upper())[:60])

    pdf.saveState()
    pdf.setFillColor(HIGHLIGHT)
    pdf.setFillAlpha(HIGHLIGHT_ALPHA)
    for item in placed:
        for rect_left, rect_bottom, rect_right, rect_top in item.rects:
            pdf.rect(rect_left, rect_bottom, rect_right - rect_left, rect_top - rect_bottom, stroke=0, fill=1)
    pdf.restoreState()

    note_x = margin_left + 8
    note_width = right - note_x - 8
    cursor = top - 22
    floor = bottom + 8
    overflow: list[_PlacedNote] = []
    ordered = sorted(placed, key=lambda item: -(item.anchor_top if item.anchor_top is not None else top))
    for item in ordered:
        height = _note_height(item, note_width - 2 * NOTE_PADDING)
        desired = item.anchor_top + 4 if item.anchor_top is not None else cursor
        note_top = min(desired, cursor)
        if note_top - height < floor:
            overflow.append(item)
            continue
        _draw_note(pdf, item, note_x, note_top, note_width, accent)
        if item.rects:
            # The marker sits just before the highlight; the connector stays in the margin
            # so it never crosses the student's text.
            first = max(item.rects, key=lambda rect: (rect[3], -rect[0]))
            anchor_y = (first[1] + first[3]) / 2
            _draw_marker(pdf, item.number, max(left + 6, first[0] - 7), anchor_y, accent)
            pdf.setStrokeColor(accent)
            pdf.setLineWidth(0.4)
            pdf.setDash(1.5, 1.5)
            pdf.line(margin_left, anchor_y, note_x, note_top - NOTE_PADDING - 3)
            pdf.setDash()
            _draw_marker(pdf, item.number, margin_left, anchor_y, accent)
        cursor = note_top - height - 6
    pdf.showPage()
    pdf.save()
    return buffer.getvalue(), overflow


def _overflow_page(size: tuple[float, float], page_number: int, notes: list[_PlacedNote], title: str, accent) -> bytes:
    width, height = size
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=size)
    pdf.setFillColor(MUTED)
    pdf.setFont(FONT_BOLD, 8)
    pdf.drawString(36, height - 36, _safe_text(f"{title.upper()} · MORE NOTES FOR PAGE {page_number}"))
    cursor = height - 52
    for item in notes:
        box_height = _note_height(item, width - 72 - 2 * NOTE_PADDING)
        if cursor - box_height < 36:
            pdf.showPage()
            cursor = height - 36
        _draw_note(pdf, item, 36, cursor, width - 72, accent)
        cursor -= box_height + 6
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _inline_markdown(text: str) -> str:
    text = escape(_safe_text(text))
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", text)
    return re.sub(r"`(.+?)`", r"\1", text)


def markdown_flowables(markdown: str, accent) -> list:
    """Render the small Markdown subset the reports use: headings, bullets, tables and paragraphs."""
    styles = {
        1: ParagraphStyle("h1", fontName=FONT_BOLD, fontSize=16, leading=20, spaceAfter=8, textColor=INK),
        2: ParagraphStyle("h2", fontName=FONT_BOLD, fontSize=12.5, leading=16, spaceBefore=8, spaceAfter=5, textColor=accent),
        3: ParagraphStyle("h3", fontName=FONT_BOLD, fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=3, textColor=INK),
    }
    body = ParagraphStyle("body", fontName=FONT, fontSize=9.5, leading=13, alignment=TA_LEFT, textColor=INK)
    cell = ParagraphStyle("cell", parent=body, fontSize=8.5, leading=11)
    flowables: list = []
    bullets: list = []
    table_rows: list[list[str]] = []

    def flush() -> None:
        if bullets:
            flowables.append(ListFlowable(bullets[:], bulletType="bullet", start="•", leftIndent=12, bulletFontSize=8))
            bullets.clear()
        if table_rows:
            data = [[Paragraph(_inline_markdown(value), cell) for value in row] for row in table_rows]
            table = Table(data, repeatRows=1, hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                        ("BACKGROUND", (0, 0), (-1, 0), PAPER),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            flowables.extend([table, Spacer(1, 6)])
            table_rows.clear()

    for raw in markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("|"):
            if bullets:
                flush()
            cells = [value.strip() for value in stripped.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", value) for value in cells if value):
                table_rows.append(cells)
            continue
        if table_rows:
            flush()
        heading = re.match(r"^(#{1,6})\s+(.*)", stripped)
        bullet = re.match(r"^[-*]\s+(.*)", stripped)
        if heading:
            flush()
            flowables.append(Paragraph(_inline_markdown(heading.group(2)), styles[min(len(heading.group(1)), 3)]))
        elif bullet:
            bullets.append(ListItem(Paragraph(_inline_markdown(bullet.group(1)), body), leftIndent=12))
        elif stripped.startswith(">"):
            flush()
            flowables.append(Paragraph(_inline_markdown(stripped.lstrip("> ")), body))
        elif not stripped or stripped == "---":
            flush()
            flowables.append(Spacer(1, 4))
        else:
            flush()
            flowables.append(Paragraph(_inline_markdown(stripped), body))
    flush()
    return flowables


def _cover_pdf(markdown: str, size: tuple[float, float], accent) -> bytes:
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=size, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48
    )
    document.build(markdown_flowables(markdown, accent))
    return buffer.getvalue()


def _encrypt(writer: PdfWriter, password: str) -> None:
    try:
        writer.encrypt(password, algorithm="AES-256")
    except Exception:  # AES needs an optional crypto package; RC4 is built in
        writer.encrypt(password, algorithm="RC4-128")


def build_annotated_pdf(
    pdf_bytes: bytes,
    notes: list[MarginNote],
    cover_markdown: str,
    *,
    title: str,
    accent_hex: str = "#b8432f",
    password: str | None = None,
) -> tuple[bytes, dict[str, int]]:
    """Return the annotated PDF and counts of highlighted and page-level notes.

    The cover pages (from Markdown) come first; each original page gains a right margin with
    its notes. An encrypted input is re-encrypted with the same password.
    """
    accent = colors.HexColor(accent_hex)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if reader.is_encrypted:
        reader.decrypt(password or "")
    document = pdfium.PdfDocument(pdf_bytes, password=password or None)
    stats = {"highlighted": 0, "page_notes": 0}
    writer = PdfWriter()

    first = reader.pages[0]
    cover_size = (float(first.cropbox.width), float(first.cropbox.height))
    if first.rotation % 180:
        cover_size = cover_size[::-1]
    if cover_markdown.strip():
        for page in PdfReader(io.BytesIO(_cover_pdf(cover_markdown, cover_size, accent))).pages:
            writer.add_page(page)

    by_page: dict[int, list[MarginNote]] = {}
    for note in notes:
        if 1 <= note.page <= len(reader.pages):
            by_page.setdefault(note.page, []).append(note)
    number = 0
    for index, page in enumerate(reader.pages, start=1):
        page_notes = by_page.get(index, [])
        if not page_notes:
            writer.add_page(page)
            continue
        rotated = bool(page.rotation % 360)
        textpage = document[index - 1].get_textpage() if not rotated else None
        placed = []
        for note in page_notes:
            number += 1
            rects = find_quote_rects(textpage, note.quote) if textpage is not None and note.quote else []
            stats["highlighted" if rects else "page_notes"] += 1
            placed.append(_PlacedNote(number, note, rects))
        if textpage is not None:
            textpage.close()
        page = writer.add_page(page)  # edit the writer's copy, as pypdf requires
        if rotated:
            page.transfer_rotation_to_content()
        crop = page.cropbox
        left, bottom, right, top = float(crop.left), float(crop.bottom), float(crop.right), float(crop.top)
        margin = max(MIN_MARGIN_WIDTH, (right - left) * MARGIN_RATIO)
        box = (left, bottom, right + margin, top)
        overlay, overflow = _overlay_page(box, right, placed, title, accent)
        page.merge_page(PdfReader(io.BytesIO(overlay)).pages[0])
        page.mediabox = RectangleObject(box)
        page.cropbox = RectangleObject(box)
        if overflow:
            extra = _overflow_page((right - left + margin, top - bottom), index, overflow, title, accent)
            for extra_page in PdfReader(io.BytesIO(extra)).pages:
                writer.add_page(extra_page)
    document.close()

    if password:
        _encrypt(writer, password)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), stats
