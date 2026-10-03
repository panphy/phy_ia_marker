import io
import json
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app_utils import EE, IA, build_examiner_cover, split_margin_notes
from pdf_annotate import MarginNote, build_annotated_pdf, markdown_flowables

ROOT = Path(__file__).resolve().parents[1]


def _sample_pdf(pages: list[list[str]]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for lines in pages:
        y = 780
        for line in lines:
            pdf.drawString(60, y, line)
            y -= 18
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


SAMPLE = _sample_pdf(
    [
        ["Research question: How does the length of a pendulum affect its period?"],
        ["The gradient of T^2 against L gives g = 9.62 m s^-2.", "A limitation is reaction time."],
    ]
)


def _notes_section(items: list[dict]) -> str:
    return "## Margin notes\n```json\n" + json.dumps(items) + "\n```\n"


def test_split_margin_notes_reads_valid_notes_and_drops_bad_ones() -> None:
    report = "## Suggestions for improvement\n- Body\n\n" + _notes_section(
        [
            {"page": 2, "quote": "The gradient of  T^2", "criterion": "Data analysis", "note": "Add Δg."},
            {"page": 9, "quote": "x", "criterion": "Data analysis", "note": "Outside the PDF."},
            {"page": 1, "quote": "", "criterion": "Unknown", "note": "Whole-page note."},
            {"page": "2", "quote": "x", "note": "Page is a string."},
            {"page": 1, "quote": "Research question", "criterion": "Research design", "note": "This is worth 4/6."},
        ]
    )
    body, notes, warnings = split_margin_notes(report, 2, IA, for_student=True)
    assert body == "## Suggestions for improvement\n- Body"
    assert notes == [
        {"page": 2, "quote": "The gradient of T^2", "note": "Add Δg.", "label": "Data analysis"},
        {"page": 1, "quote": "", "note": "Whole-page note.", "label": "General"},
    ]
    assert any("outside this PDF" in warning for warning in warnings)
    assert any("mentioned marks" in warning for warning in warnings)
    assert any("incomplete" in warning for warning in warnings)

    # The examiner copy may mention marks.
    _, examiner_notes, _ = split_margin_notes(report, 2, IA)
    assert len(examiner_notes) == 3


def test_split_margin_notes_fails_safe_without_usable_json() -> None:
    assert split_margin_notes("## Suggestions\n- Body", 3) == ("## Suggestions\n- Body", [], ["No margin notes were returned."])
    body, notes, warnings = split_margin_notes("Body\n## Margin notes\n```json\n[{oops\n```", 3)
    assert (body, notes) == ("Body", [])
    assert warnings == ["The margin notes could not be read."]
    # Unfenced arrays are accepted.
    _, notes, _ = split_margin_notes('## Margin notes\n[{"page": 1, "quote": "", "note": "n"}]', 1)
    assert notes[0]["page"] == 1


def test_annotated_pdf_highlights_quotes_and_falls_back_to_page_notes() -> None:
    notes = [
        MarginNote(2, "The gradient of T^2 against L", "Add an uncertainty to the gradient (Δg).", "Data analysis"),
        MarginNote(2, "A limitation is reaction time", "Link this to an improvement.", "Evaluation"),
        MarginNote(1, "words that do not appear on this page", "General note.", "General"),
    ]
    output, stats = build_annotated_pdf(SAMPLE, notes, "# Cover\n- One point", title="Examiner copy")
    assert stats == {"highlighted": 2, "page_notes": 1}
    reader = PdfReader(io.BytesIO(output))
    assert len(reader.pages) == 3  # cover + two pages
    original_width = float(PdfReader(io.BytesIO(SAMPLE)).pages[1].mediabox.width)
    assert float(reader.pages[2].mediabox.width) > original_width * 1.3
    document = pdfium.PdfDocument(output)
    page_text = document[2].get_textpage().get_text_range()
    assert "The gradient of T^2" in page_text  # the student's text is kept
    assert "Add an uncertainty to the gradient" in page_text
    assert "Cover" in document[0].get_textpage().get_text_range()


def test_annotated_pdf_without_notes_or_cover_keeps_pages_unchanged() -> None:
    output, stats = build_annotated_pdf(SAMPLE, [], "", title="Student copy")
    assert stats == {"highlighted": 0, "page_notes": 0}
    reader = PdfReader(io.BytesIO(output))
    assert [float(page.mediabox.width) for page in reader.pages] == [
        float(page.mediabox.width) for page in PdfReader(io.BytesIO(SAMPLE)).pages
    ]


def test_annotated_pdf_overflowing_notes_go_to_an_extra_page() -> None:
    notes = [MarginNote(1, "", "A long note about the research question. " * 6, "Research design")] * 25
    output, stats = build_annotated_pdf(SAMPLE, notes, "", title="Examiner copy")
    assert stats["page_notes"] == 25
    assert len(PdfReader(io.BytesIO(output)).pages) > 2


def test_annotated_pdf_keeps_the_original_password() -> None:
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(SAMPLE)).pages:
        writer.add_page(page)
    writer.encrypt("secret", algorithm="RC4-128")
    encrypted = io.BytesIO()
    writer.write(encrypted)
    output, stats = build_annotated_pdf(
        encrypted.getvalue(), [MarginNote(1, "Research question", "Note.", "Research design")], "",
        title="Examiner copy", password="secret",
    )
    assert stats["highlighted"] == 1
    reader = PdfReader(io.BytesIO(output))
    assert reader.is_encrypted
    assert reader.decrypt("secret")


def test_markdown_flowables_render_report_markup() -> None:
    flowables = markdown_flowables(
        "# Title\n> **Note:** x\n| A | B |\n|---|---|\n| 1 | <2> |\n- **Add** Δg & more\n\nText", "#b8432f"
    )
    assert len(flowables) >= 5


def test_examiner_cover_lists_marks_notice_and_final_decision() -> None:
    final = "## Final decision\n" + "\n".join(
        f"### {name} — 3/{maximum}\n- Page 1" for name, maximum in EE.criteria
    )
    cover = build_examiner_cover(EE, final, "**Final decision ready.**  \nReview the cited pages.")
    assert cover.startswith("# Examiner copy: IB DP Physics EE")
    assert EE.marking_notice in cover
    assert "| Discussion and evaluation | 3 | 8 |" in cover
    assert "| **Total** | **12** | **26** |" in cover
    assert cover.rstrip().endswith(final.splitlines()[-1])


def test_examiner_notes_prompt_formats() -> None:
    prompt = (ROOT / "prompts" / "examiner_notes_prompt.md").read_text(encoding="utf-8")
    filled = prompt.format(
        work_name="IA",
        rubric_text="Rubric",
        evidence_index="Index",
        ia_text="--- Page 1 ---\nText",
        final_report="Final",
        criterion_list=", ".join(f'"{name}"' for name in IA.names),
        digest_citation_guidance="",
    )
    assert "## Margin notes" in filled
    assert '{"page": 3' in filled
    assert "untrusted" in filled


def test_student_notes_prompt_is_appended_only_when_requested() -> None:
    notes_block = (ROOT / "prompts" / "student_notes_prompt.md").read_text(encoding="utf-8").format(
        criterion_list=", ".join(f'"{name}"' for name in IA.names)
    )
    assert "## Margin notes" in notes_block
    assert '"Research design"' in notes_block
    assert '{"page": 4' in notes_block
    suggestions = (ROOT / "prompts" / "suggestions_prompt.md").read_text(encoding="utf-8")
    assert "{margin_notes_instructions}" in suggestions
    assert "## Margin notes" not in suggestions
