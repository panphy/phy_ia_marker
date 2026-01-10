import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import streamlit as st
from pdf2image import convert_from_bytes
from pypdf import PdfReader
import pytesseract
from openai import OpenAI


# -------------------------
# Config
# -------------------------
APP_TITLE = "IB DP Physics IA Marker (Rubric-based)"
DEFAULT_MODEL = "gpt-5-mini"  # You can change this (e.g., gpt-5, gpt-5-mini, etc.)
MAX_RAW_CHARS_BEFORE_DIGEST = 180_000  # if docs are huge, make a structured digest first
DIGEST_TARGET_CHARS = 70_000           # approximate size of digest text
STORE_RESPONSES = False                # privacy-friendly default
CRITERIA_PATH = Path(__file__).resolve().parent / "criteria" / "ib_phy_ia_criteria.md"

# -------------------------
# Prompt templates (loaded from files)
# -------------------------
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


EXAMINER_PROMPT = load_prompt("examiner_prompt.txt")
MODERATOR_PROMPT = load_prompt("moderator_prompt.txt")
KIND_MODERATOR_PROMPT = load_prompt("kind_moderator_prompt.txt")


# -------------------------
# PDF extraction
# -------------------------
def ocr_pdf_page(file_bytes: bytes, page_number: int, language: str) -> str:
    images = convert_from_bytes(
        file_bytes,
        first_page=page_number,
        last_page=page_number,
    )
    if not images:
        return ""
    return pytesseract.image_to_string(images[0], lang=language).strip()


def extract_pdf_text(file_bytes: bytes, use_ocr: bool, ocr_language: str) -> Tuple[str, int, int]:
    """Return extracted text, page count, and OCR page count."""
    reader = PdfReader(io.BytesIO(file_bytes))
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


# -------------------------
# OpenAI helper
# -------------------------
@dataclass
class AIResult:
    text: str
    used_digest: bool = False


def get_openai_client() -> OpenAI:
    if not hasattr(st, "secrets") or "OPENAI_API_KEY" not in st.secrets:
        raise RuntimeError(
            "OpenAI API key not found. Set OPENAI_API_KEY in Streamlit secrets."
        )
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


def call_llm(client: OpenAI, model: str, instructions: str, user_input: str) -> str:
    resp = client.responses.create(
        model=model,
        instructions=instructions,
        input=user_input,
        store=STORE_RESPONSES,
    )
    return (resp.output_text or "").strip()


def make_structured_digest(client: OpenAI, model: str, label: str, raw_text: str) -> str:
    """
    Compress a large document into a structured digest that preserves marking-relevant evidence.
    This is a pragmatic workaround for context length limits.
    """
    instructions = "You compress documents for evidence-preserving academic review."
    prompt = f"""
You are preparing an evidence-preserving digest for an IB Physics IA marking workflow.

Document type: {label}

Goal:
- Preserve all information relevant to assessment and moderation.
- Keep structure. Keep key numbers, units, uncertainties, relationships, model choices.
- List all figures/tables/graphs you can detect from headings/captions or nearby text.
- If content seems missing (e.g., no uncertainties, no graph captions), explicitly note it.

Output format (strict):
1) Document outline (headings you can infer)
2) Research question / aim (if present)
3) Variables (IV/DV/controls) and method summary
4) Data: tables and what each contains (units, repeats, uncertainty fields)
5) Graphs/figures: list + what they show + axes/units/fit type if stated
6) Processing: calculations, uncertainty treatment, fits, stats, sample calc
7) Conclusion: main claims + linked evidence
8) Evaluation: limitations + improvements + impact on result
9) Any missing/unclear items that an examiner would penalize

Keep it under ~{DIGEST_TARGET_CHARS} characters if possible.

[DOCUMENT_START]
{raw_text}
[DOCUMENT_END]
"""
    return call_llm(client, model, instructions=instructions, user_input=prompt)


def maybe_digest(client: OpenAI, model: str, label: str, raw_text: str) -> AIResult:
    if len(raw_text) <= MAX_RAW_CHARS_BEFORE_DIGEST:
        return AIResult(text=raw_text, used_digest=False)
    digest = make_structured_digest(client, model, label=label, raw_text=raw_text)
    return AIResult(text=digest, used_digest=True)


# -------------------------
# Streamlit UI
# -------------------------
st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)

st.caption(
    "Upload the student IA PDF. The app uses the built-in IA criteria file and "
    "generates three Markdown reports (Examiner, Moderator, Kind Moderator). "
    "Best results when PDFs contain selectable text (OCR can help with scanned PDFs)."
)

with st.sidebar:
    st.subheader("Settings")
    model = st.text_input("Model", value=DEFAULT_MODEL)
    st.checkbox("Store API responses (OpenAI)", value=STORE_RESPONSES, disabled=True,
                help="This app is set to store=false by default in code. Toggle in code if you want storage.")
    enable_ocr = st.checkbox("Enable OCR for scanned pages", value=True)
    ocr_language = st.text_input("OCR language (Tesseract)", value="eng")
    st.markdown("---")
    st.caption("Uses Streamlit secrets key `OPENAI_API_KEY` for OpenAI access.")
    st.markdown("**Tip:** If your PDFs are scanned images, text extraction may fail. OCR can recover text.")

ia_file = st.file_uploader("Upload student IA PDF", type=["pdf"], key="ia_pdf")

run = st.button("Mark IA and generate 3 reports", type="primary", disabled=not ia_file)

if "examiner_report" not in st.session_state:
    st.session_state.examiner_report = ""
if "moderator_report" not in st.session_state:
    st.session_state.moderator_report = ""
if "kind_moderator_report" not in st.session_state:
    st.session_state.kind_moderator_report = ""
if "debug_info" not in st.session_state:
    st.session_state.debug_info = {}

if run:
    try:
        client = get_openai_client()
    except Exception as e:
        st.error(str(e))
        st.stop()

    with st.spinner("Extracting text from PDFs..."):
        ia_bytes = ia_file.read()
        ia_text, ia_pages, ia_ocr_pages = extract_pdf_text(
            ia_bytes,
            use_ocr=enable_ocr,
            ocr_language=ocr_language,
        )
        criteria_text = CRITERIA_PATH.read_text(encoding="utf-8")

    # Basic quality checks
    if ia_text.count("[No extractable text") > ia_pages * 0.7:
        st.warning("IA PDF appears to have little extractable text (possibly scanned). Marking quality may suffer.")

    with st.spinner("Preparing documents (digesting if too large)..."):
        ia_ready = maybe_digest(client, model, label="Student IA", raw_text=ia_text)
        criteria_ready = AIResult(text=criteria_text, used_digest=False)

        st.session_state.debug_info = {
            "ia_pages": ia_pages,
            "ia_ocr_pages": ia_ocr_pages,
            "ia_used_digest": ia_ready.used_digest,
            "ia_chars": len(ia_text),
            "criteria_chars": len(criteria_text),
        }

    # 1) Examiner
    with st.spinner("Generating Examiner report..."):
        examiner_input = EXAMINER_PROMPT.format(
            rubric_text=criteria_ready.text,
            ia_text=ia_ready.text,
        )
        examiner_report = call_llm(
            client,
            model=model,
            instructions="You are an expert IB DP Physics IA examiner. Follow the rubric strictly and output Markdown.",
            user_input=examiner_input,
        )
        st.session_state.examiner_report = examiner_report

    # 2) Moderator (uses examiner output)
    with st.spinner("Generating Moderator report..."):
        moderator_input = MODERATOR_PROMPT.format(
            rubric_text=criteria_ready.text,
            ia_text=ia_ready.text,
            examiner_report=st.session_state.examiner_report,
        )
        moderator_report = call_llm(
            client,
            model=model,
            instructions=(
                "You are a strict IB DP Physics IA moderator. Be skeptical and evidence-led, "
                "but slightly less strict than the examiner. Output Markdown."
            ),
            user_input=moderator_input,
        )
        st.session_state.moderator_report = moderator_report

    # 3) Kind moderator
    with st.spinner("Generating Kind Moderator report..."):
        kind_moderator_input = KIND_MODERATOR_PROMPT.format(
            rubric_text=criteria_ready.text,
            ia_text=ia_ready.text,
        )
        kind_moderator_report = call_llm(
            client,
            model=model,
            instructions=(
                "You are a kind IB DP Physics IA moderator. Be supportive, accurate, and rubric-aligned, "
                "while slightly less strict than a formal moderator. Output Markdown."
            ),
            user_input=kind_moderator_input,
        )
        st.session_state.kind_moderator_report = kind_moderator_report

    st.success("Done. Reports generated below.")


# -------------------------
# Display + downloads
# -------------------------
if st.session_state.examiner_report or st.session_state.moderator_report or st.session_state.kind_moderator_report:
    st.markdown("---")
    st.subheader("Reports")

    tab1, tab2, tab3 = st.tabs(["Examiner report", "Moderator report", "Kind moderator report"])

    with tab1:
        st.download_button(
            "Download Examiner report (.md)",
            data=st.session_state.examiner_report,
            file_name="examiner_report.md",
            mime="text/markdown",
            disabled=not st.session_state.examiner_report,
        )
        st.markdown(st.session_state.examiner_report or "_No report yet._")

    with tab2:
        st.download_button(
            "Download Moderator report (.md)",
            data=st.session_state.moderator_report,
            file_name="moderator_report.md",
            mime="text/markdown",
            disabled=not st.session_state.moderator_report,
        )
        st.markdown(st.session_state.moderator_report or "_No report yet._")

    with tab3:
        st.download_button(
            "Download Kind Moderator report (.md)",
            data=st.session_state.kind_moderator_report,
            file_name="kind_moderator_report.md",
            mime="text/markdown",
            disabled=not st.session_state.kind_moderator_report,
        )
        st.markdown(st.session_state.kind_moderator_report or "_No report yet._")

    with st.expander("Debug info (optional)"):
        st.json(st.session_state.debug_info)
