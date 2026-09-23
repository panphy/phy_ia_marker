import io
import re
from dataclasses import dataclass, replace
from typing import Tuple

from PIL import Image
from pdf2image import convert_from_bytes
from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
import pytesseract
from pytesseract.pytesseract import TesseractError, TesseractNotFoundError


@dataclass(frozen=True)
class PageExtractionDiagnostic:
    page_number: int
    has_text: bool
    used_ocr: bool
    ocr_confidence: float | None
    image_count: int
    vector_count: int
    text_length: int


@dataclass(frozen=True)
class ExtractedVisual:
    page_number: int
    name: str
    image_format: str | None
    width: int | None
    height: int | None
    data: bytes
    captions: tuple[str, ...] = ()
    kind: str = "image"
    rasterized_data: bytes | None = None
    rasterized_format: str | None = None


@dataclass(frozen=True)
class SourceImage:
    page_number: int
    name: str
    png_data: bytes
    captions: tuple[str, ...] = ()


def prepare_source_images(visuals: list[ExtractedVisual]) -> list[SourceImage]:
    """Normalize selected PDF visuals for direct inspection by marking models."""
    prepared: list[SourceImage] = []
    rendered_vector_pages: set[int] = set()
    for visual in visuals:
        if visual.kind == "vector" and visual.page_number in rendered_vector_pages:
            continue
        source_data = visual.rasterized_data if visual.kind == "vector" else visual.data
        if not source_data:
            continue
        try:
            with Image.open(io.BytesIO(source_data)) as image:
                image.thumbnail((2000, 2000))
                output = io.BytesIO()
                image.convert("RGB").save(output, format="PNG")
        except (OSError, ValueError):
            continue
        prepared.append(SourceImage(visual.page_number, visual.name, output.getvalue(), visual.captions))
        if visual.kind == "vector":
            rendered_vector_pages.add(visual.page_number)
    return prepared


@dataclass
class PdfExtractionError(Exception):
    user_message: str


class PdfPasswordRequiredError(PdfExtractionError):
    pass


def _format_pdf_render_error(exc: Exception) -> str:
    if isinstance(exc, PDFInfoNotInstalledError):
        return "Poppler is not installed or not available on PATH. Install Poppler and try again."
    if isinstance(exc, PDFPageCountError):
        return "Unable to render the PDF page for OCR. If the PDF is encrypted, check the password."
    if isinstance(exc, PDFSyntaxError):
        return "Unable to render the PDF page for OCR because the PDF appears malformed."
    return "Unable to render the PDF page for OCR. Check Poppler and the PDF file, then try again."


def _format_tesseract_error(exc: Exception, language: str) -> str:
    if isinstance(exc, TesseractNotFoundError):
        return "Tesseract is not installed or not available on PATH. Install Tesseract and try again."
    if isinstance(exc, TesseractError):
        return (
            f"Tesseract OCR failed for language '{language}'. "
            "Check that the language data is installed and the language code is valid."
        )
    return "Tesseract OCR failed. Check the OCR installation and try again."


def ocr_pdf_page(
    file_bytes: bytes,
    page_number: int,
    language: str,
    pdf_password: str | None = None,
) -> tuple[str, float | None]:
    try:
        images = convert_from_bytes(
            file_bytes,
            first_page=page_number,
            last_page=page_number,
            userpw=pdf_password,
        )
    except (PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError) as exc:
        raise PdfExtractionError(_format_pdf_render_error(exc)) from exc
    if not images:
        return "", None
    image = images[0]
    try:
        text = pytesseract.image_to_string(image, lang=language).strip()
    except (TesseractNotFoundError, TesseractError) as exc:
        raise PdfExtractionError(_format_tesseract_error(exc, language)) from exc
    confidence = None
    try:
        data = pytesseract.image_to_data(image, lang=language, output_type=pytesseract.Output.DICT)
        confidences: list[float] = []
        for value in data.get("conf", []):
            if isinstance(value, (int, float)):
                parsed_value = float(value)
            elif isinstance(value, str):
                try:
                    parsed_value = float(value)
                except ValueError:
                    continue
            else:
                continue
            if parsed_value >= 0:
                confidences.append(parsed_value)
        if confidences:
            confidence = sum(confidences) / len(confidences)
    except (TesseractNotFoundError, TesseractError):
        confidence = None
    return text, confidence


def count_page_images(page: object) -> int:
    try:
        images = page.images
    except Exception:
        return 0
    try:
        return len(images)
    except TypeError:
        return 0


def extract_page_images(page: object, page_number: int) -> list[ExtractedVisual]:
    try:
        images = list(page.images)
    except Exception:
        return []

    extracted: list[ExtractedVisual] = []
    for index, image in enumerate(images, start=1):
        name = getattr(image, "name", "") or f"page-{page_number}-image-{index}"
        data = getattr(image, "data", b"") or b""
        pil_image = getattr(image, "image", None)
        width = height = None
        image_format = None
        if pil_image is not None:
            try:
                width, height = pil_image.size
            except Exception:
                width = height = None
            try:
                image_format = (pil_image.format or "").lower() or None
            except Exception:
                image_format = None
            if not data:
                buffer = io.BytesIO()
                save_format = pil_image.format or "PNG"
                try:
                    pil_image.save(buffer, format=save_format)
                    data = buffer.getvalue()
                    image_format = image_format or save_format.lower()
                except Exception:
                    data = b""
        extracted.append(
            ExtractedVisual(
                page_number=page_number,
                name=name,
                image_format=image_format,
                width=width,
                height=height,
                data=data,
            )
        )
    return extracted


def attach_unambiguous_captions(
    visuals: list[ExtractedVisual], captions_by_page: dict[int, list[str]]
) -> list[ExtractedVisual]:
    """Link a caption only when there is exactly one visual and one caption on its page."""
    visual_counts: dict[int, int] = {}
    for visual in visuals:
        visual_counts[visual.page_number] = visual_counts.get(visual.page_number, 0) + 1
    linked = []
    for visual in visuals:
        captions = captions_by_page.get(visual.page_number, [])
        if visual_counts[visual.page_number] == 1 and len(captions) == 1:
            linked.append(replace(visual, captions=(captions[0],)))
        else:
            linked.append(visual)
    return linked


def _collect_content_streams(page: object) -> list[bytes]:
    try:
        contents = page.get_contents()
    except Exception:
        return []
    if contents is None:
        return []
    streams = contents if isinstance(contents, list) else [contents]
    data_list: list[bytes] = []
    for stream in streams:
        try:
            data_list.append(stream.get_data())
        except Exception:
            continue
    return data_list


def _has_vector_operators(stream_data: bytes) -> bool:
    if not stream_data:
        return False
    pattern = re.compile(
        rb"(?<![A-Za-z0-9])(?:m|l|re|c|v|y|h|S|s|f\*?|B\*?|b\*?|n)(?![A-Za-z0-9])"
    )
    return bool(pattern.search(stream_data))


def extract_vector_graphics(page: object, page_number: int) -> list[ExtractedVisual]:
    extracted: list[ExtractedVisual] = []
    vector_streams = [data for data in _collect_content_streams(page) if _has_vector_operators(data)]
    if vector_streams:
        media_box = getattr(page, "mediabox", None)
        width = height = None
        if media_box is not None:
            try:
                width = int(media_box.width)
                height = int(media_box.height)
            except Exception:
                width = height = None
        extracted.append(
            ExtractedVisual(
                page_number=page_number,
                name=f"page-{page_number}-vector-content",
                image_format="pdf-vector",
                width=width,
                height=height,
                data=b"\n".join(vector_streams),
                kind="vector",
            )
        )
    try:
        resources = page.get("/Resources") or {}
        xobjects = resources.get("/XObject") or {}
    except Exception:
        xobjects = {}
    for name, xobject_ref in xobjects.items():
        try:
            xobject = xobject_ref.get_object()
        except Exception:
            continue
        if xobject.get("/Subtype") != "/Form":
            continue
        try:
            data = xobject.get_data()
        except Exception:
            data = b""
        width = height = None
        bbox = xobject.get("/BBox")
        if bbox and len(bbox) == 4:
            try:
                width = int(bbox[2] - bbox[0])
                height = int(bbox[3] - bbox[1])
            except Exception:
                width = height = None
        extracted.append(
            ExtractedVisual(
                page_number=page_number,
                name=str(name),
                image_format="pdf-form",
                width=width,
                height=height,
                data=data,
                kind="vector",
            )
        )
    return extracted


def render_pdf_page_image(
    file_bytes: bytes,
    page_number: int,
    dpi: int = 200,
    pdf_password: str | None = None,
) -> tuple[bytes | None, str | None]:
    try:
        images = convert_from_bytes(
            file_bytes,
            first_page=page_number,
            last_page=page_number,
            dpi=dpi,
            userpw=pdf_password,
        )
    except Exception:
        return None, None
    if not images:
        return None, None
    image = images[0]
    buffer = io.BytesIO()
    try:
        image.save(buffer, format="PNG")
    except Exception:
        return None, None
    return buffer.getvalue(), "png"


def extract_pdf_text(
    file_bytes: bytes,
    use_ocr: bool,
    ocr_language: str,
    pdf_password: str | None = None,
) -> Tuple[str, int, int, list[PageExtractionDiagnostic], list[ExtractedVisual]]:
    """Return extracted text, page count, OCR page count, per-page diagnostics, and visuals."""
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
    diagnostics: list[PageExtractionDiagnostic] = []
    visuals: list[ExtractedVisual] = []
    for i, page in enumerate(reader.pages, start=1):
        page_images = extract_page_images(page, page_number=i)
        image_count = len(page_images)
        page_vectors = extract_vector_graphics(page, page_number=i)
        if page_vectors:
            rasterized_data, rasterized_format = render_pdf_page_image(
                file_bytes,
                page_number=i,
                pdf_password=pdf_password,
            )
            if rasterized_data:
                page_vectors = [
                    replace(
                        visual,
                        rasterized_data=rasterized_data,
                        rasterized_format=rasterized_format,
                    )
                    for visual in page_vectors
                ]
        visuals.extend(page_images)
        visuals.extend(page_vectors)
        vector_count = len(page_vectors)
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        t = re.sub(r"[ \t]+", " ", t).strip()
        # A selectable page number or header can sit on top of an otherwise scanned page.
        # OCR short text pages with visual content instead of treating them as complete.
        needs_ocr = use_ocr and (not t or (len(t) < 80 and (page_images or page_vectors)))
        ocr_text = ""
        ocr_confidence = None
        if needs_ocr:
            ocr_text, ocr_confidence = ocr_pdf_page(
                file_bytes,
                page_number=i,
                language=ocr_language,
                pdf_password=pdf_password,
            )
        use_ocr_text = bool(ocr_text) and (not t or len(ocr_text) > len(t) + 20)
        if use_ocr_text:
            ocr_pages += 1
        if t:
            page_text = t
            if use_ocr_text:
                page_text += f"\n[OCR supplement]\n{ocr_text}"
        elif use_ocr_text:
            page_text = f"[OCR]\n{ocr_text}"
        else:
            page_text = "[No extractable text found on this page]"
        chunks.append(f"\n\n--- Page {i} ---\n{page_text}")
        diagnostics.append(
            PageExtractionDiagnostic(
                page_number=i,
                has_text=bool(t),
                used_ocr=use_ocr_text,
                ocr_confidence=ocr_confidence if use_ocr_text else None,
                image_count=image_count,
                vector_count=vector_count,
                text_length=len(page_text) if t or use_ocr_text else 0,
            )
        )
    return "\n".join(chunks).strip(), pages, ocr_pages, diagnostics, visuals
