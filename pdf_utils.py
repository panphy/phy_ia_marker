import io
import re
from dataclasses import dataclass
from typing import Tuple

from pdf2image import convert_from_bytes
from pypdf import PdfReader
from pypdf.errors import PdfReadError
import pytesseract


@dataclass
class PdfExtractionError(Exception):
    user_message: str


class PdfPasswordRequiredError(PdfExtractionError):
    pass


def ocr_pdf_page(file_bytes: bytes, page_number: int, language: str) -> str:
    images = convert_from_bytes(
        file_bytes,
        first_page=page_number,
        last_page=page_number,
    )
    if not images:
        return ""
    return pytesseract.image_to_string(images[0], lang=language).strip()


def extract_pdf_text(
    file_bytes: bytes,
    use_ocr: bool,
    ocr_language: str,
    pdf_password: str | None = None,
) -> Tuple[str, int, int]:
    """Return extracted text, page count, and OCR page count."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except PdfReadError as exc:
        raise PdfExtractionError(
            "Unable to read the PDF. It may be corrupted or password-protected."
        ) from exc
    except Exception as exc:
        raise PdfExtractionError(
            "Unexpected error while opening the PDF. Please re-upload and try again."
        ) from exc

    if reader.is_encrypted:
        try:
            empty_password_ok = reader.decrypt("") != 0
        except PdfReadError as exc:
            raise PdfExtractionError(
                "Unable to read the encrypted PDF. Please re-upload and try again."
            ) from exc
        if not empty_password_ok:
            if not pdf_password:
                raise PdfPasswordRequiredError(
                    "This PDF is encrypted. Enter the password in the sidebar and try again."
                )
            try:
                password_ok = reader.decrypt(pdf_password) != 0
            except PdfReadError as exc:
                raise PdfExtractionError(
                    "Unable to decrypt the PDF with the supplied password."
                ) from exc
            if not password_ok:
                raise PdfPasswordRequiredError(
                    "The PDF password is incorrect. Please try again."
                )

    pages = len(reader.pages)
    chunks = []
    ocr_pages = 0
    for i, page in enumerate(reader.pages, start=1):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        t = re.sub(r"[ \t]+", " ", t).strip()
        if t:
            chunks.append(f"\n\n--- Page {i} ---\n{t}")
        else:
            ocr_text = ""
            if use_ocr:
                try:
                    ocr_text = ocr_pdf_page(file_bytes, page_number=i, language=ocr_language)
                except Exception:
                    ocr_text = ""
            if ocr_text:
                ocr_pages += 1
                chunks.append(f"\n\n--- Page {i} ---\n[OCR]\n{ocr_text}")
            else:
                chunks.append(f"\n\n--- Page {i} ---\n[No extractable text found on this page]")
    return "\n".join(chunks).strip(), pages, ocr_pages
