import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import streamlit as st
from openai import OpenAI
from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

from pdf_utils import (
    PdfExtractionError,
    PdfPasswordRequiredError,
    extract_pdf_text,
)

# -------------------------
# Config
# -------------------------
APP_TITLE = "IB DP Physics IA Marker"
DEFAULT_MODEL = "gpt-5-mini"
MAX_RAW_CHARS_BEFORE_DIGEST = 180_000  # if docs are huge, make a structured digest first
DIGEST_TARGET_CHARS = 70_000           # approximate size of digest text
DIGEST_CHUNK_TARGET_CHARS = 30_000     # chunk size for per-chunk summaries
STORE_RESPONSES = False                # privacy-friendly default
CRITERIA_PATH = Path(__file__).resolve().parent / "criteria" / "ib_phy_ia_criteria.md"
MAX_PASSWORD_ATTEMPTS = 5
PASSWORD_ATTEMPT_WINDOW_SECONDS = 300

# -------------------------
# Prompt templates (loaded from files)
# -------------------------
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


EXAMINER1_PROMPT = load_prompt("examiner1_prompt.md")
EXAMINER2_PROMPT = load_prompt("examiner2_prompt.md")
MODERATOR_PROMPT = load_prompt("moderator_prompt.md")


# -------------------------
# PDF extraction
# -------------------------
def show_pdf_error(message: str) -> None:
    st.error(message)
    st.stop()


# -------------------------
# OpenAI helper
# -------------------------
@dataclass
class AIResult:
    text: str
    used_digest: bool = False
    used_chunking: bool = False


@dataclass
class LLMError(Exception):
    user_message: str
    debug_info: dict


def get_openai_client() -> OpenAI:
    if not hasattr(st, "secrets") or "OPENAI_API_KEY" not in st.secrets:
        raise RuntimeError(
            "OpenAI API key not found. Set OPENAI_API_KEY in Streamlit secrets."
        )
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


def call_llm(client: OpenAI, model: str, instructions: str, user_input: str) -> str:
    try:
        request_args = {
            "model": model,
            "instructions": instructions,
            "input": user_input,
            "store": STORE_RESPONSES,
        }
        resp = client.responses.create(
            **request_args,
        )
    except RateLimitError as exc:
        raise LLMError(
            user_message="API error: rate limited, try again in 30 seconds.",
            debug_info={"error_type": "rate_limit", "detail": str(exc)},
        ) from exc
    except (APITimeoutError, TimeoutError) as exc:
        raise LLMError(
            user_message="API error: request timed out. Try again.",
            debug_info={"error_type": "timeout", "detail": str(exc)},
        ) from exc
    except APIConnectionError as exc:
        raise LLMError(
            user_message="API error: connection issue. Check your network and try again.",
            debug_info={"error_type": "connection", "detail": str(exc)},
        ) from exc
    except APIError as exc:
        raise LLMError(
            user_message="API error: unexpected response from the model. Try again shortly.",
            debug_info={
                "error_type": "api_error",
                "detail": str(exc),
                "status_code": getattr(exc, "status_code", None),
            },
        ) from exc
    return (resp.output_text or "").strip()


def chunk_text(raw_text: str, target_chars: int) -> list[str]:
    paragraphs = [para.strip() for para in raw_text.split("\n\n") if para.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        if paragraph_len > target_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            for start in range(0, paragraph_len, target_chars):
                chunks.append(paragraph[start:start + target_chars])
            continue

        if current_len + paragraph_len + 2 > target_chars and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0

        current.append(paragraph)
        current_len += paragraph_len + 2

    if current:
        chunks.append("\n\n".join(current))

    return chunks or [raw_text]


def make_structured_digest(client: OpenAI, model: str, label: str, raw_text: str) -> AIResult:
    """
    Compress a large document into a structured digest that preserves marking-relevant evidence.
    This is a pragmatic workaround for context length limits.
    """
    instructions = "You compress documents for evidence-preserving academic review."
    chunks = chunk_text(raw_text, target_chars=DIGEST_CHUNK_TARGET_CHARS)
    chunk_summaries = []
    for index, chunk in enumerate(chunks, start=1):
        chunk_prompt = f"""
You are preparing an evidence-preserving digest for an IB Physics IA marking workflow.

Document type: {label}
Chunk: {index} of {len(chunks)}

Goal:
- Preserve all information relevant to assessment and moderation.
- Keep structure. Keep key numbers, units, uncertainties, relationships, model choices.
- List all figures/tables/graphs you can detect from headings/captions or nearby text.
- If content seems missing (e.g., no uncertainties, no graph captions), explicitly note it.

Output format (strict):
1) Outline or section hints present in this chunk
2) Research question/aim content in this chunk
3) Variables/method details in this chunk
4) Data tables mentioned in this chunk (units, repeats, uncertainty fields)
5) Graphs/figures in this chunk (axes/units/fit type if stated)
6) Processing/uncertainty/statistics in this chunk
7) Conclusion/evaluation statements in this chunk
8) Missing/unclear items in this chunk

[DOCUMENT_START]
{chunk}
[DOCUMENT_END]
"""
        chunk_summary = call_llm(client, model, instructions=instructions, user_input=chunk_prompt)
        chunk_summaries.append(f"[CHUNK {index} SUMMARY]\n{chunk_summary}")

    consolidation_prompt = f"""
You are consolidating chunk-level digests for an IB Physics IA marking workflow.

Document type: {label}

Goal:
- Merge chunk summaries into a single coherent evidence-preserving digest.
- Keep structure. Keep key numbers, units, uncertainties, relationships, model choices.
- List all figures/tables/graphs you can detect from the summaries.
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

[CHUNK_SUMMARIES_START]
{chr(10).join(chunk_summaries)}
[CHUNK_SUMMARIES_END]
"""
    digest = call_llm(client, model, instructions=instructions, user_input=consolidation_prompt)
    return AIResult(text=digest, used_digest=True, used_chunking=len(chunks) > 1)


def maybe_digest(
    client: OpenAI,
    model: str,
    label: str,
    raw_text: str,
) -> AIResult:
    if len(raw_text) <= MAX_RAW_CHARS_BEFORE_DIGEST:
        return AIResult(text=raw_text, used_digest=False, used_chunking=False)
    return make_structured_digest(client, model, label=label, raw_text=raw_text)


# -------------------------
# Streamlit UI
# -------------------------
st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)
st.markdown(
    """
    <style>
    button[aria-label="Mark with Examiner 1"],
    button[aria-label="Mark with Examiner 2"],
    button[aria-label="Mark with Moderator"] {
        background-color: #7c3aed;
        border-color: #7c3aed;
        color: #ffffff;
    }
    button[aria-label="Mark with Examiner 1"]:hover,
    button[aria-label="Mark with Examiner 2"]:hover,
    button[aria-label="Mark with Moderator"]:hover {
        background-color: #6d28d9;
        border-color: #6d28d9;
        color: #ffffff;
    }
    button[aria-label="Mark with Examiner 1"]:active,
    button[aria-label="Mark with Examiner 2"]:active,
    button[aria-label="Mark with Moderator"]:active {
        background-color: #5b21b6;
        border-color: #5b21b6;
        color: #ffffff;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.caption(
    "Upload the student IA PDF. Choose which AI persona should mark the IA and "
    "generate a Markdown report. Best results when PDFs contain selectable text "
    "(OCR can help with scanned PDFs)."
)


def require_password() -> None:
    if "APP_PASSWORD" not in st.secrets:
        st.error("App password not configured. Set APP_PASSWORD in Streamlit secrets.")
        st.stop()

    if "password_ok" not in st.session_state:
        st.session_state.password_ok = False
    if "failed_attempts" not in st.session_state:
        st.session_state.failed_attempts = 0
    if "last_failed_at" not in st.session_state:
        st.session_state.last_failed_at = None

    now = time.time()
    if st.session_state.last_failed_at:
        elapsed_since_fail = now - st.session_state.last_failed_at
        if elapsed_since_fail > PASSWORD_ATTEMPT_WINDOW_SECONDS:
            st.session_state.failed_attempts = 0
            st.session_state.last_failed_at = None

    if not st.session_state.password_ok:
        if (
            st.session_state.failed_attempts >= MAX_PASSWORD_ATTEMPTS
            and st.session_state.last_failed_at
            and (now - st.session_state.last_failed_at) < PASSWORD_ATTEMPT_WINDOW_SECONDS
        ):
            remaining = int(PASSWORD_ATTEMPT_WINDOW_SECONDS - (now - st.session_state.last_failed_at))
            st.error("Too many failed attempts. Please wait before trying again.")
            st.info(f"Cooldown remaining: {remaining} seconds.")
            st.stop()

        st.subheader("Password required")
        password = st.text_input("Password", type="password")
        if password:
            if password == st.secrets["APP_PASSWORD"]:
                st.session_state.password_ok = True
                st.session_state.failed_attempts = 0
                st.session_state.last_failed_at = None
                st.rerun()
            else:
                st.session_state.failed_attempts += 1
                st.session_state.last_failed_at = now
                st.error("Incorrect password.")
        st.stop()


require_password()

with st.sidebar:
    st.subheader("Settings")
    model = DEFAULT_MODEL
    st.text(f"Model: {model}")
    st.checkbox(
        "Store API responses (OpenAI)",
        value=STORE_RESPONSES,
        disabled=True,
        help="This app is set to store=false by default in code. Toggle in code if you want storage.",
    )
    enable_ocr = st.checkbox("Enable OCR for scanned pages", value=True)
    ocr_language = st.text_input("OCR language (Tesseract)", value="eng")
    pdf_password = st.text_input("PDF password (if encrypted)", type="password")
    st.markdown("---")
    st.caption("Uses Streamlit secrets key `OPENAI_API_KEY` for OpenAI access.")
    st.markdown("**Tip:** If your PDFs are scanned images, text extraction may fail. OCR can recover text.")
    st.caption("Deterministic scoring is disabled: results may vary slightly between runs.")

if "examiner1_report" not in st.session_state:
    st.session_state.examiner1_report = ""
if "examiner2_report" not in st.session_state:
    st.session_state.examiner2_report = ""
if "moderator_report" not in st.session_state:
    st.session_state.moderator_report = ""
if "debug_info" not in st.session_state:
    st.session_state.debug_info = {}
if "doc_cache_key" not in st.session_state:
    st.session_state.doc_cache_key = None
if "ia_ready_text" not in st.session_state:
    st.session_state.ia_ready_text = ""
if "ia_used_digest" not in st.session_state:
    st.session_state.ia_used_digest = False
if "criteria_text" not in st.session_state:
    st.session_state.criteria_text = ""


def reset_reports() -> None:
    st.session_state.examiner1_report = ""
    st.session_state.examiner2_report = ""
    st.session_state.moderator_report = ""
    st.session_state.debug_info = {}


def record_llm_error(context: str, error: LLMError) -> None:
    st.session_state.debug_info.setdefault("llm_errors", [])
    st.session_state.debug_info["llm_errors"].append(
        {
            "context": context,
            "message": error.user_message,
            "details": error.debug_info,
        }
    )


def ensure_documents(
    client: OpenAI,
    model: str,
    ia_upload: st.runtime.uploaded_file_manager.UploadedFile,
    use_ocr: bool,
    ocr_language_setting: str,
    pdf_password: str | None,
) -> None:
    ia_bytes = ia_upload.getvalue()
    sha256_hex = hashlib.sha256(ia_bytes).hexdigest()
    cache_key = (
        ia_upload.name,
        sha256_hex,
        use_ocr,
        ocr_language_setting,
        model,
    )
    if st.session_state.doc_cache_key == cache_key:
        return

    reset_reports()
    with st.spinner("Extracting text from PDF..."):
        try:
            ia_text, ia_pages, ia_ocr_pages = extract_pdf_text(
                ia_bytes,
                use_ocr=use_ocr,
                ocr_language=ocr_language_setting,
                pdf_password=pdf_password or None,
            )
        except PdfPasswordRequiredError as exc:
            show_pdf_error(exc.user_message)
        except PdfExtractionError as exc:
            show_pdf_error(exc.user_message)
        criteria_text = CRITERIA_PATH.read_text(encoding="utf-8")

    if ia_text.count("[No extractable text") > ia_pages * 0.7:
        st.warning("IA PDF appears to have little extractable text (possibly scanned). Marking quality may suffer.")

    with st.spinner("Preparing documents (digesting if too large)..."):
        ia_ready = maybe_digest(
            client,
            model,
            label="Student IA",
            raw_text=ia_text,
        )

        st.session_state.debug_info = {
            "ia_pages": ia_pages,
            "ia_ocr_pages": ia_ocr_pages,
            "ia_used_digest": ia_ready.used_digest,
            "ia_used_chunking": ia_ready.used_chunking,
            "ia_chars": len(ia_text),
            "criteria_chars": len(criteria_text),
        }

    st.session_state.doc_cache_key = cache_key
    st.session_state.ia_ready_text = ia_ready.text
    st.session_state.ia_used_digest = ia_ready.used_digest
    st.session_state.criteria_text = criteria_text


ia_file = st.file_uploader("Upload student IA PDF", type=["pdf"], key="ia_pdf")
reports_ready = bool(st.session_state.examiner1_report.strip()) and bool(
    st.session_state.examiner2_report.strip()
)

columns = st.columns(3, gap="small")
with columns[0]:
    run_examiner1 = st.button(
        "Mark with Examiner 1",
        type="primary",
        disabled=not ia_file,
        help="Strict rubric-first examiner who assigns marks based on evidence.",
        use_container_width=True,
    )
with columns[1]:
    run_examiner2 = st.button(
        "Mark with Examiner 2",
        type="primary",
        disabled=not ia_file,
        help="Equally experienced examiner who assigns marks based on evidence.",
        use_container_width=True,
    )
with columns[2]:
    run_moderator = st.button(
        "Mark with Moderator",
        type="primary",
        disabled=not ia_file or not reports_ready,
        help="Chief examiner who adjudicates based on the IA, rubric, and both examiner reports.",
        use_container_width=True,
    )
selected_action = None
if run_examiner1:
    selected_action = "examiner1"
elif run_examiner2:
    selected_action = "examiner2"
elif run_moderator:
    selected_action = "moderator"

if selected_action:
    try:
        client = get_openai_client()
    except Exception as e:
        st.error(str(e))
        st.stop()

    try:
        ensure_documents(
            client,
            model=model,
            ia_upload=ia_file,
            use_ocr=enable_ocr,
            ocr_language_setting=ocr_language,
            pdf_password=pdf_password,
        )
    except LLMError as exc:
        record_llm_error("prepare_documents", exc)
        st.error(exc.user_message)
        st.stop()

    criteria_ready = AIResult(text=st.session_state.criteria_text, used_digest=False)
    ia_ready = AIResult(text=st.session_state.ia_ready_text, used_digest=st.session_state.ia_used_digest)

    if selected_action == "examiner1":
        with st.spinner("Generating Examiner 1 report..."):
            examiner_input = EXAMINER1_PROMPT.format(
                rubric_text=criteria_ready.text,
                ia_text=ia_ready.text,
            )
            try:
                examiner_report = call_llm(
                    client,
                    model=model,
                    instructions=(
                        "You are Examiner 1: an expert IB DP Physics IA examiner. "
                        "Follow the rubric strictly and output Markdown."
                    ),
                    user_input=examiner_input,
                )
            except LLMError as exc:
                record_llm_error("examiner1_report", exc)
                st.error(exc.user_message)
            else:
                st.session_state.examiner1_report = examiner_report
                st.success("Examiner 1 report generated.")
                st.rerun()

    if selected_action == "examiner2":
        with st.spinner("Generating Examiner 2 report..."):
            examiner_input = EXAMINER2_PROMPT.format(
                rubric_text=criteria_ready.text,
                ia_text=ia_ready.text,
            )
            try:
                examiner_report = call_llm(
                    client,
                    model=model,
                    instructions=(
                        "You are Examiner 2: an expert IB DP Physics IA examiner. "
                        "Follow the rubric strictly and output Markdown."
                    ),
                    user_input=examiner_input,
                )
            except LLMError as exc:
                record_llm_error("examiner2_report", exc)
                st.error(exc.user_message)
            else:
                st.session_state.examiner2_report = examiner_report
                st.success("Examiner 2 report generated.")
                st.rerun()

    if selected_action == "moderator":
        with st.spinner("Generating Moderator report..."):
            moderator_input = MODERATOR_PROMPT.format(
                rubric_text=criteria_ready.text,
                ia_text=ia_ready.text,
                examiner1_report=st.session_state.examiner1_report,
                examiner2_report=st.session_state.examiner2_report,
            )
            try:
                moderator_report = call_llm(
                    client,
                    model=model,
                    instructions=(
                        "You are the chief IB DP Physics IA moderator. "
                        "Use the IA, rubric, and both examiner reports to adjudicate final marks. "
                        "Output Markdown."
                    ),
                    user_input=moderator_input,
                )
            except LLMError as exc:
                record_llm_error("moderator_report", exc)
                st.error(exc.user_message)
            else:
                st.session_state.moderator_report = moderator_report
                st.success("Moderator report generated.")

# -------------------------
# Display + downloads
# -------------------------
if (
    st.session_state.examiner1_report
    or st.session_state.examiner2_report
    or st.session_state.moderator_report
):
    st.markdown("---")
    st.subheader("Reports")

    tab1, tab2, tab3 = st.tabs(["Examiner 1 report", "Examiner 2 report", "Moderator report"])

    with tab1:
        st.download_button(
            "Download Examiner 1 report (.md)",
            data=st.session_state.examiner1_report,
            file_name="examiner1_report.md",
            mime="text/markdown",
            disabled=not st.session_state.examiner1_report,
        )
        st.markdown(st.session_state.examiner1_report or "_No report yet._")

    with tab2:
        st.download_button(
            "Download Examiner 2 report (.md)",
            data=st.session_state.examiner2_report,
            file_name="examiner2_report.md",
            mime="text/markdown",
            disabled=not st.session_state.examiner2_report,
        )
        st.markdown(st.session_state.examiner2_report or "_No report yet._")

    with tab3:
        st.download_button(
            "Download Moderator report (.md)",
            data=st.session_state.moderator_report,
            file_name="moderator_report.md",
            mime="text/markdown",
            disabled=not st.session_state.moderator_report,
        )
        st.markdown(st.session_state.moderator_report or "_No report yet._")

    with st.expander("Debug info (optional)"):
        st.json(st.session_state.debug_info)
