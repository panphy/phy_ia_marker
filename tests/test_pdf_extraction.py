import io

import pytest
from pypdf import PdfWriter

from pdf_utils import PdfPasswordRequiredError, extract_pdf_text


def build_encrypted_pdf(password: str) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
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

    text, pages, ocr_pages = extract_pdf_text(
        encrypted_pdf,
        use_ocr=False,
        ocr_language="eng",
        pdf_password="secret",
    )

    assert pages == 1
    assert ocr_pages == 0
    assert "[No extractable text found on this page]" in text
