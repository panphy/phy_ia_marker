import io

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from pdf_utils import (
    ExtractedVisual,
    PdfExtractionError,
    PdfPasswordRequiredError,
    attach_unambiguous_captions,
    ocr_pdf_page,
    prepare_source_images,
    render_pdf_page_image,
    extract_pdf_text,
)


def build_encrypted_pdf(password: str) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def add_text_page(writer: PdfWriter, text: str) -> None:
    page = writer.add_blank_page(width=72, height=72)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    content = StreamObject()
    content._data = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET".encode("utf-8")
    content_ref = writer._add_object(content)
    page[NameObject("/Contents")] = content_ref


def build_image_pdf() -> bytes:
    image = Image.new("RGB", (10, 10), color="red")
    buffer = io.BytesIO()
    image.save(buffer, format="PDF")
    return buffer.getvalue()


def encrypt_pdf(file_bytes: bytes, password: str) -> bytes:
    reader = PdfReader(io.BytesIO(file_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(password)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_extract_pdf_text_requires_password_for_encrypted_pdf() -> None:
    encrypted_pdf = build_encrypted_pdf("secret")

    with pytest.raises(PdfPasswordRequiredError):
        extract_pdf_text(encrypted_pdf, use_ocr=False, ocr_language="eng")


def test_extract_pdf_text_rejects_wrong_password_for_encrypted_pdf() -> None:
    encrypted_pdf = build_encrypted_pdf("secret")

    with pytest.raises(PdfPasswordRequiredError):
        extract_pdf_text(
            encrypted_pdf,
            use_ocr=False,
            ocr_language="eng",
            pdf_password="wrong",
        )


def test_extract_pdf_text_accepts_correct_password_for_encrypted_pdf() -> None:
    encrypted_pdf = build_encrypted_pdf("secret")

    text, pages, ocr_pages, diagnostics, visuals = extract_pdf_text(
        encrypted_pdf,
        use_ocr=False,
        ocr_language="eng",
        pdf_password="secret",
    )

    assert pages == 1
    assert ocr_pages == 0
    assert "[No extractable text found on this page]" in text
    assert diagnostics[0].page_number == 1
    assert diagnostics[0].has_text is False
    assert visuals == []


def test_extract_pdf_text_handles_mixed_content_pdf() -> None:
    writer = PdfWriter()
    add_text_page(writer, "Hello text page")

    image_reader = PdfReader(io.BytesIO(build_image_pdf()))
    writer.add_page(image_reader.pages[0])

    buffer = io.BytesIO()
    writer.write(buffer)

    text, pages, ocr_pages, diagnostics, visuals = extract_pdf_text(
        buffer.getvalue(),
        use_ocr=False,
        ocr_language="eng",
    )

    assert pages == 2
    assert ocr_pages == 0
    assert "Hello text page" in text
    assert diagnostics[0].has_text is True
    assert diagnostics[0].image_count == 0
    assert diagnostics[1].has_text is False
    assert diagnostics[1].image_count >= 1
    assert any(visual.page_number == 2 for visual in visuals)


def test_short_text_with_image_receives_ocr_supplement(monkeypatch: pytest.MonkeyPatch) -> None:
    writer = PdfWriter()
    add_text_page(writer, "Page 1")
    buffer = io.BytesIO()
    writer.write(buffer)
    image = ExtractedVisual(1, "scan", "png", 10, 10, b"image")
    monkeypatch.setattr("pdf_utils.extract_page_images", lambda page, page_number: [image])
    monkeypatch.setattr(
        "pdf_utils.ocr_pdf_page",
        lambda *args, **kwargs: ("A long scanned body with measurements and uncertainties.", 92.0),
    )

    text, _, ocr_pages, diagnostics, _ = extract_pdf_text(
        buffer.getvalue(), use_ocr=True, ocr_language="eng"
    )

    assert "Page 1\n[OCR supplement]" in text
    assert "measurements and uncertainties" in text
    assert ocr_pages == 1
    assert diagnostics[0].has_text and diagnostics[0].used_ocr


def test_captions_are_only_linked_when_match_is_unambiguous() -> None:
    first = ExtractedVisual(1, "a", "png", 10, 10, b"a")
    second = ExtractedVisual(1, "b", "png", 10, 10, b"b")

    assert attach_unambiguous_captions([first, second], {1: ["Figure 1: graph"]}) == [first, second]
    assert attach_unambiguous_captions([first], {1: ["Figure 1: graph"]})[0].captions == (
        "Figure 1: graph",
    )


def test_prepare_source_images_normalizes_and_deduplicates_vector_page() -> None:
    image = Image.new("RGB", (10, 10), color="blue")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    vector = ExtractedVisual(
        2, "vector-a", "pdf-vector", 10, 10, b"vector", kind="vector",
        rasterized_data=buffer.getvalue(), rasterized_format="png",
    )
    duplicate = ExtractedVisual(
        2, "vector-b", "pdf-vector", 10, 10, b"vector", kind="vector",
        rasterized_data=buffer.getvalue(), rasterized_format="png",
    )

    prepared = prepare_source_images([vector, duplicate])

    assert len(prepared) == 1
    assert prepared[0].page_number == 2
    assert prepared[0].png_data.startswith(b"\x89PNG")


def test_scanned_pdf_uses_ocr_without_poppler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pdf_utils.pytesseract.image_to_string", lambda *args, **kwargs: "OCR text")
    monkeypatch.setattr(
        "pdf_utils.pytesseract.image_to_data",
        lambda *args, **kwargs: {"conf": ["92", "88"]},
    )

    text, pages, ocr_pages, diagnostics, _ = extract_pdf_text(
        build_image_pdf(), use_ocr=True, ocr_language="eng"
    )

    assert pages == 1
    assert ocr_pages == 1
    assert "[OCR]\nOCR text" in text
    assert diagnostics[0].ocr_confidence == 90


def test_pdfium_render_accepts_pdf_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encrypted_pdf = encrypt_pdf(build_image_pdf(), "secret")
    monkeypatch.setattr("pdf_utils.pytesseract.image_to_string", lambda *args, **kwargs: "OCR text")
    monkeypatch.setattr("pdf_utils.pytesseract.image_to_data", lambda *args, **kwargs: {"conf": ["90"]})
    data, image_format = render_pdf_page_image(
        encrypted_pdf,
        page_number=1,
        pdf_password="secret",
    )
    text, confidence = ocr_pdf_page(encrypted_pdf, page_number=1, language="eng", pdf_password="secret")

    assert data is not None and data.startswith(b"\x89PNG")
    assert image_format == "png"
    assert text == "OCR text"
    assert confidence == 90
    assert render_pdf_page_image(encrypted_pdf, page_number=1) == (None, None)


def test_ocr_pdf_page_surfaces_renderer_failures() -> None:
    with pytest.raises(PdfExtractionError, match="outside the PDF"):
        ocr_pdf_page(build_image_pdf(), page_number=2, language="eng")
