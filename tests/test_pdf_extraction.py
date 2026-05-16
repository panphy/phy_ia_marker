import io

import pytest
from PIL import Image
from pdf2image.exceptions import PDFPageCountError
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from pdf_utils import (
    PdfExtractionError,
    PdfPasswordRequiredError,
    ocr_pdf_page,
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


def test_ocr_pdf_page_passes_pdf_password_to_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}

    class FakeImage:
        pass

    def fake_convert_from_bytes(*args, **kwargs):
        calls["userpw"] = kwargs.get("userpw")
        return [FakeImage()]

    monkeypatch.setattr("pdf_utils.convert_from_bytes", fake_convert_from_bytes)
    monkeypatch.setattr("pdf_utils.pytesseract.image_to_string", lambda *args, **kwargs: "OCR text")
    monkeypatch.setattr(
        "pdf_utils.pytesseract.image_to_data",
        lambda *args, **kwargs: {"conf": ["92", "88"]},
    )

    text, confidence = ocr_pdf_page(
        b"%PDF",
        page_number=1,
        language="eng",
        pdf_password="secret",
    )

    assert text == "OCR text"
    assert confidence == 90
    assert calls["userpw"] == "secret"


def test_render_pdf_page_image_passes_pdf_password_to_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {}

    class FakeImage:
        def save(self, buffer, format):
            buffer.write(b"png-bytes")

    def fake_convert_from_bytes(*args, **kwargs):
        calls["userpw"] = kwargs.get("userpw")
        return [FakeImage()]

    monkeypatch.setattr("pdf_utils.convert_from_bytes", fake_convert_from_bytes)

    data, image_format = render_pdf_page_image(
        b"%PDF",
        page_number=1,
        pdf_password="secret",
    )

    assert data == b"png-bytes"
    assert image_format == "png"
    assert calls["userpw"] == "secret"


def test_ocr_pdf_page_surfaces_renderer_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_convert_from_bytes(*args, **kwargs):
        raise PDFPageCountError("unable to get page count")

    monkeypatch.setattr("pdf_utils.convert_from_bytes", fake_convert_from_bytes)

    with pytest.raises(PdfExtractionError, match="Unable to render"):
        ocr_pdf_page(b"%PDF", page_number=1, language="eng")
