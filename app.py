import os
import io
import re
from dataclasses import dataclass
from typing import Optional, Tuple

import streamlit as st
from pypdf import PdfReader
from openai import OpenAI


# -------------------------
# Config
# -------------------------
APP_TITLE = "IB DP Physics IA Marker (Rubric-based)"
DEFAULT_MODEL = "gpt-5-mini"  # You can change this (e.g., gpt-5, gpt-5-mini, etc.)
MAX_RAW_CHARS_BEFORE_DIGEST = 180_000  # if docs are huge, make a structured digest first
DIGEST_TARGET_CHARS = 70_000           # approximate size of digest text
STORE_RESPONSES = False                # privacy-friendly default

# -------------------------
# Prompt templates (as plain strings)
# -------------------------
EXAMINER_PROMPT = r"""
# Role
You are an **IB DP Physics Internal Assessment (IA) examiner** with **many years of moderation and marking experience**. You will mark the candidate’s IA **strictly using the uploaded rubric** below.

# Inputs
## Rubric (authoritative)
[RUBRIC_START]
{rubric_text}
[RUBRIC_END]

## Subject specification (supplementary, optional)
[SPEC_START]
{spec_text}
[SPEC_END]

## IA report (authoritative)
[IA_START]
{ia_text}
[IA_END]

# Your task
## A) Determine the mark for each criterion
- Use the **exact criteria and markbands** from the rubric above.
- For **each criterion**, award:
  - **Mark awarded:** x / max
  - **Markband/descriptor chosen:** (quote or precisely paraphrase from rubric)
  - **Justification based on evidence from the IA**

## B) Evidence-based justification
Evidence can include:
- short text excerpts
- graphs/diagrams/tables (describe what is shown and where, e.g., “Figure 2”, “Table 1”, “Graph: V vs I”)
- missing elements (explicitly state what is absent)

You do **not** need to literally quote every time, but you must reference **specific locations** or items.

## C) Be decisive
- If between two bands, state why the higher one is not reached.
- If something is present but weak, explain why it only partially meets the descriptor.

## D) Output format (must follow exactly)
### 1) Rubric snapshot (from the rubric above)
- List each criterion name and maximum marks exactly as in the rubric.
- Summarize key distinguishing features of top/middle/low bands per criterion (brief).

### 2) Criterion-by-criterion marking
For each criterion:

#### Criterion: <criterion name> (x / max)
- **Awarded mark:** x / max
- **Rubric basis (descriptor):** “…” (from rubric)
- **Evidence from IA (text/figure/table/missing):**
  - Evidence 1: (Type: text/graph/diagram/table/missing) (Location: …)
    - What it shows / what is missing: …
    - Why this matches (or fails to match) the descriptor: …
  - Evidence 2: …
- **Why not higher:** …
- **Key weaknesses holding it back:** (bullets)
- **Quick improvement advice aligned to rubric:** (bullets)

### 3) Overall results summary
- Table: Criterion | Mark | Max | One-sentence rationale
- Total mark: **__/__**
- 5–10 line moderator-style summary.

### 4) Red flags / academic integrity (only if evidence appears)
List concerns as concerns (not accusations) with the triggering evidence.

# Rules
- The rubric above is the authority.
- Do not invent evidence; if not found, say so.
- Keep quotes short.
"""

MODERATOR_PROMPT = r"""
# Role
You are an **IB DP Physics IA moderator** (experienced, strict, and skeptical). Your job is to **quality-check** an examiner’s marking for fairness, clarity, and alignment with the **uploaded rubric**. You assume nothing. You challenge anything not explicitly evidenced.

# Inputs
## Rubric (authoritative)
[RUBRIC_START]
{rubric_text}
[RUBRIC_END]

## Subject specification (supplementary, optional)
[SPEC_START]
{spec_text}
[SPEC_END]

## IA report (authoritative)
[IA_START]
{ia_text}
[IA_END]

## Examiner’s report (to audit)
[EXAMINER_REPORT_START]
{examiner_report}
[EXAMINER_REPORT_END]

# Your task
## A) Reconstruct rubric requirements
Extract criterion names, max marks, and markband descriptors from the rubric above.

## B) Audit the examiner’s marking
For each criterion:
- Identify examiner mark + rationale.
- Verify rubric-alignment and evidence-anchoring.
- Challenge unclear/vague claims and demand specifics.
- Independently check the IA evidence (text/figures/tables/missing items).

## C) Decide outcomes
For each criterion choose:
- Accept
- Accept with clarification required
- Recommend adjust up
- Recommend adjust down
- Unable to verify

If recommending change, provide recommended mark and why (rubric + IA evidence).

## D) Output format (must follow exactly)

### 1) Moderator overview
- Total marks awarded by examiner: **__/__**
- Overall confidence: **High / Medium / Low**
- Top 3 systemic issues (if any)

### 2) Criterion-by-criterion moderation audit
#### Criterion: <criterion name> (max: __)
- **Examiner mark:** __ / __
- **Moderator decision:** Accept / Accept with clarification required / Recommend adjust up / Recommend adjust down / Unable to verify
- **Rubric checkpoint:** (1–3 bullets)
- **Evidence audit (IA vs examiner report):**
  - Examiner claim 1: “...”
    - Evidence examiner provided: ... (or note absent)
    - Moderator check in IA: ... (where found or “not found”)
    - Verdict: Supported / Partially supported / Not supported
  - Examiner claim 2: ...
- **What is unclear or unproven in examiner report:** (bullets)
- **Your recommended mark (if different):** __ / __ (with why)
- **Clarifications you would demand from the examiner:** Q1, Q2, ...

### 3) Summary table
Criterion | Examiner | Moderator decision | Recommended (if different) | Key reason

### 4) Final moderation statement
### 5) Red flags / integrity concerns (only if evidence appears)

# Strict rules
- Rubric is the authority.
- Do not invent evidence. If not found, say “not evidenced in the IA”.
- Keep quotes short.
"""

KIND_TEACHER_PROMPT = r"""
# Role
You are a **kind, supportive IB DP Physics teacher** who is highly familiar with the **IB Physics IA assessment criteria**. Your goal is to help the student improve while still being accurate and rubric-aligned.

# Inputs
## Rubric (authoritative)
[RUBRIC_START]
{rubric_text}
[RUBRIC_END]

## Subject specification (supplementary, optional)
[SPEC_START]
{spec_text}
[SPEC_END]

## IA report (authoritative)
[IA_START]
{ia_text}
[IA_END]

# Your task
## A) Understand rubric first
Extract each criterion name + max marks from the rubric above, and explain (student-friendly) what it rewards.

## B) Give mark estimate + gentle justification
For each criterion:
- Provide a likely mark range (unless crystal clear).
- Use specific evidence from the IA (text/graphs/tables/diagrams/missing items).

## C) Actionable improvement plan
For each criterion:
- Provide 3–7 concrete fixes aligned to rubric.
- Include mini examples when helpful.

## D) Output format (must follow exactly)

### 1) Warm overview (5–8 lines)
### 2) Rubric map
### 3) Feedback by criterion
#### Criterion: <criterion name> (max: __)
- Estimated mark range: __–__ / __
- What you did well (evidence):
- What to improve next (rubric-linked):
- Quick model example (preferred)

### 4) If you had 2 hours, do these first
### 5) Encouraging next steps

# Tone rules
- Kind, motivating, honest.
- Do not inflate marks.
- Evidence can be described (graphs/diagrams/tables/missing items).
"""


# -------------------------
# PDF extraction
# -------------------------
def extract_pdf_text(file_bytes: bytes) -> Tuple[str, int]:
    """Return extracted text and page count. Works best for text PDFs (not scanned images)."""
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = len(reader.pages)
    chunks = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        t = re.sub(r"[ \t]+", " ", t).strip()
        if t:
            chunks.append(f"\n\n--- Page {i} ---\n{t}")
        else:
            chunks.append(f"\n\n--- Page {i} ---\n[No extractable text found on this page]")
    return "\n".join(chunks).strip(), pages


# -------------------------
# OpenAI helper
# -------------------------
@dataclass
class AIResult:
    text: str
    used_digest: bool = False


def get_openai_client() -> OpenAI:
    # Prefer Streamlit secrets, fallback to env var
    api_key = None
    if hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OpenAI API key not found. Set OPENAI_API_KEY in Streamlit secrets or environment variables."
        )
    return OpenAI(api_key=api_key)


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
    "Upload the IA rubric PDF, optionally the IB Physics subject specification, and the student IA PDF. "
    "The app extracts text and generates three Markdown reports (Examiner, Moderator, Kind Teacher). "
    "Best results when PDFs contain selectable text."
)

with st.sidebar:
    st.subheader("Settings")
    model = st.text_input("Model", value=DEFAULT_MODEL)
    st.checkbox("Store API responses (OpenAI)", value=STORE_RESPONSES, disabled=True,
                help="This app is set to store=false by default in code. Toggle in code if you want storage.")
    st.markdown("---")
    st.markdown("**Tip:** If your PDFs are scanned images, text extraction may fail. Convert to text PDF or add OCR.")

col1, col2, col3 = st.columns(3)
with col1:
    rubric_file = st.file_uploader("Upload IB IA rubric PDF", type=["pdf"], key="rubric_pdf")
with col2:
    spec_file = st.file_uploader("Upload subject specification PDF (optional)", type=["pdf"], key="spec_pdf")
with col3:
    ia_file = st.file_uploader("Upload student IA PDF", type=["pdf"], key="ia_pdf")

run = st.button("Mark IA and generate 3 reports", type="primary", disabled=not (rubric_file and ia_file))

if "examiner_report" not in st.session_state:
    st.session_state.examiner_report = ""
if "moderator_report" not in st.session_state:
    st.session_state.moderator_report = ""
if "teacher_report" not in st.session_state:
    st.session_state.teacher_report = ""
if "debug_info" not in st.session_state:
    st.session_state.debug_info = {}

if run:
    try:
        client = get_openai_client()
    except Exception as e:
        st.error(str(e))
        st.stop()

    with st.spinner("Extracting text from PDFs..."):
        rubric_bytes = rubric_file.read()
        ia_bytes = ia_file.read()
        spec_bytes = spec_file.read() if spec_file else None

        rubric_text, rubric_pages = extract_pdf_text(rubric_bytes)
        ia_text, ia_pages = extract_pdf_text(ia_bytes)
        if spec_bytes:
            spec_text, spec_pages = extract_pdf_text(spec_bytes)
        else:
            spec_text, spec_pages = "Not provided.", 0

    # Basic quality checks
    if rubric_text.count("[No extractable text") > rubric_pages * 0.7:
        st.warning("Rubric PDF appears to have little extractable text (possibly scanned). Marking quality may suffer.")
    if ia_text.count("[No extractable text") > ia_pages * 0.7:
        st.warning("IA PDF appears to have little extractable text (possibly scanned). Marking quality may suffer.")
    if spec_bytes and spec_text.count("[No extractable text") > spec_pages * 0.7:
        st.warning("Subject specification PDF appears to have little extractable text (possibly scanned).")

    with st.spinner("Preparing documents (digesting if too large)..."):
        rubric_ready = maybe_digest(client, model, label="Rubric/Specification", raw_text=rubric_text)
        ia_ready = maybe_digest(client, model, label="Student IA", raw_text=ia_text)
        if spec_bytes:
            spec_ready = maybe_digest(client, model, label="Subject Specification", raw_text=spec_text)
            spec_ready_text = spec_ready.text
            spec_used_digest = spec_ready.used_digest
        else:
            spec_ready_text = spec_text
            spec_used_digest = False

        st.session_state.debug_info = {
            "rubric_pages": rubric_pages,
            "ia_pages": ia_pages,
            "spec_pages": spec_pages,
            "rubric_used_digest": rubric_ready.used_digest,
            "ia_used_digest": ia_ready.used_digest,
            "spec_used_digest": spec_used_digest,
            "rubric_chars": len(rubric_text),
            "ia_chars": len(ia_text),
            "spec_chars": len(spec_text),
        }

    # 1) Examiner
    with st.spinner("Generating Examiner report..."):
        examiner_input = EXAMINER_PROMPT.format(
            rubric_text=rubric_ready.text,
            spec_text=spec_ready_text,
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
            rubric_text=rubric_ready.text,
            spec_text=spec_ready_text,
            ia_text=ia_ready.text,
            examiner_report=st.session_state.examiner_report,
        )
        moderator_report = call_llm(
            client,
            model=model,
            instructions="You are a strict IB DP Physics IA moderator. Be skeptical and evidence-led. Output Markdown.",
            user_input=moderator_input,
        )
        st.session_state.moderator_report = moderator_report

    # 3) Kind teacher
    with st.spinner("Generating Kind Teacher report..."):
        teacher_input = KIND_TEACHER_PROMPT.format(
            rubric_text=rubric_ready.text,
            spec_text=spec_ready_text,
            ia_text=ia_ready.text,
        )
        teacher_report = call_llm(
            client,
            model=model,
            instructions="You are a kind IB DP Physics teacher. Be supportive but accurate and rubric-aligned. Output Markdown.",
            user_input=teacher_input,
        )
        st.session_state.teacher_report = teacher_report

    st.success("Done. Reports generated below.")


# -------------------------
# Display + downloads
# -------------------------
if st.session_state.examiner_report or st.session_state.moderator_report or st.session_state.teacher_report:
    st.markdown("---")
    st.subheader("Reports")

    tab1, tab2, tab3 = st.tabs(["Examiner report", "Moderator report", "Kind teacher report"])

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
            "Download Kind Teacher report (.md)",
            data=st.session_state.teacher_report,
            file_name="kind_teacher_report.md",
            mime="text/markdown",
            disabled=not st.session_state.teacher_report,
        )
        st.markdown(st.session_state.teacher_report or "_No report yet._")

    with st.expander("Debug info (optional)"):
        st.json(st.session_state.debug_info)
