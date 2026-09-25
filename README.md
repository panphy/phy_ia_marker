# IB DP Physics IA Marker

Modern Streamlit workspace for reviewing IB DP Physics scientific investigations (first assessment 2025 onward) against the current official rubric. It extracts page-linked evidence from a student PDF, proposes a mark, audits the evidence behind it, and moderates disputed or uncertain cases.

## Features
- **Rubric-driven marking** for Research design, Data analysis, Conclusion, and Evaluation.
- **Evidence audit** checks the primary mark's claims, calculations, citations and rubric fit.
- **Targeted moderation** for mark disagreements, audit concerns and source-coverage gaps; marks are never averaged.
- **Deterministic report checks** (no model involved): criterion marks, page citations, stated totals, audit mark consistency, and quotes checked against the cited page.
- **Clear review signals**: the total is shown as provisional, with a teacher-review banner, when the moderator asks for review, a final-decision quote can't be verified, or screening flags the IA.
- **PDF text extraction + OCR fallback** for scanned documents, with per-page diagnostics.
- **Digest mode** for large IAs to fit within model context limits (auto-triggers over a size threshold).
- **Original PDF visuals supplied directly to marking calls**, with source-page labels and a reviewable preview.
- **Coverage reporting** that flags missing text, OCR confidence, and unresolved figure/table labels.
- **Instruction screening** that withholds likely marker-directed text or visuals and requires teacher review of flagged IAs.
- **One-click complete assessment**, stage-by-stage reruns, a progress tracker, a total with per-criterion bars, and downloadable Markdown reports.
- **Password gate + cooldown** to reduce unauthorized access attempts.

## Repository layout
- `app.py` — Streamlit UI and theme CSS, extraction flow, OpenAI calls, and report generation.
- `app_utils.py` — prompt QA helpers, page chunking, report validation and parsing, moderation routing, quote checks, and scoring-record export.
- `pdf_utils.py` — PDF parsing, encryption detection, OCR, and visual extraction helpers.
- `criteria/ib_phy_ia_criteria.md` — rubric content used in prompts.
- `prompts/` — prompt templates for the primary marker, evidence auditor and moderator.
- `eval_marking.py` — compare exported scoring records with qualified human marks.
- `tests/` — unit tests for marking safeguards, report parsing, prompts, and PDF extraction.
- `.streamlit/config.toml` — theme colours (kept in sync with the CSS tokens in `app.py`) and toolbar settings.
- `assets/` — PanPhy logo and favicon. The header logo links to https://panphy.app.
- `todo.md` — follow-up tasks for the marking pipeline and UI.
- `tasks.md` — PDF extraction roadmap.
- `AGENTS.md` — concise contributor guidance and marking safeguards; `CLAUDE.md` points to it.

## Development

Install `requirements.txt`, then run `streamlit run app.py` or `pytest tests/`. PDF rendering uses the bundled PDFium package; OCR requires Tesseract. Streamlit Community Cloud installs Tesseract from `packages.txt`. Set `OPENAI_API_KEY` and `APP_PASSWORD` through Streamlit secrets or environment variables before running the app. Keep secrets and student PDFs out of the repository.

## Usage
1. Open the app in your browser and enter the workspace password.
2. Optionally adjust the sidebar settings: OCR, extra visual summaries, and (under **Advanced**) the OCR language.
3. Upload a student IA PDF. If it is encrypted, enter its password in the field that appears.
4. Select **Run complete assessment**. The progress tracker shows each stage; **Advanced · run or repeat one stage** reruns a single stage.
5. Read the results banner first. It says whether the decision is ready or needs teacher review, and why.
6. Review the final decision, primary mark, evidence audit and the **Source evidence** tab (page counts, coverage report, evidence index and the original visuals).
7. Download the final decision, the complete Markdown bundle, or (under **Technical details**) the scoring record for calibration.

## Configuration notes
- **Models**: marking and visual analysis use `gpt-6-sol` through the Responses API.
- **Reasoning**: marking and adjudication use high reasoning effort; evidence-preserving digest work uses low effort.
- **OCR**: toggle in the sidebar; choose an installed Tesseract language under **Advanced**.
- **Digesting**: large PDFs are summarized into a structured digest before marking. The digest
  preserves key evidence (numbers, units, uncertainties, figures/tables) and keeps page-range
  labels so citations can still reference where evidence came from. Digested IAs always go to the
  Chief Moderator, because the audit cannot check the full text.
- **Visual analysis**: vector graphics are rasterized per page. Optional extra vision summaries are off by default; selected original visuals still go directly to marking calls.
- **Storage**: `STORE_RESPONSES` is `False` by default for privacy.
- **Password throttle**: the app shares a 5-minute cooldown across browser sessions in one server process after five failed attempts. Deployments with multiple worker processes need an external shared rate limiter.
- **Encrypted PDFs**: a password field appears below the upload box when the PDF needs one.
- **Model details**: the marking and visual models and the rubric version are listed under **Advanced** in the sidebar.
- **Theme**: a light "lab notebook" palette matched to the PanPhy logo. Colours live in `.streamlit/config.toml` and the matching CSS tokens at the top of the UI section in `app.py`; keep them in sync. The theme is locked to light mode.

## How marking works
1. The PDF is parsed page-by-page. OCR is attempted on pages with no selectable text and on image-heavy pages with only a short selectable header (if enabled).
2. If the IA is too large, it is automatically summarized into a structured digest to fit the model
   context. The digest keeps page-range labels so evidence can still be cited.
3. The app builds a page index and exact candidate excerpts for rubric areas; these are navigation aids, not verified claims. A primary marker applies all four criteria and cites original pages.
4. An evidence auditor checks the primary claims against the IA and attached original visuals.
5. The app checks the reports without a model: the audit's heading mark must match its recommendation and its copy of the primary mark; stated totals must equal the criterion marks; and short quotes must appear in the extracted text of the cited page (image-only pages and rubric wording are skipped).
6. Exact agreement with no evidence warning is finalized after audit, keeping any auditor note on overstated claims. A mark difference, audit concern, coverage gap, unverified quote, or use of a summarized IA goes to the Chief Moderator.
7. If the Chief Moderator recommends human review, or quotes text that is not on the cited page, the app shows the marks as provisional and asks for teacher review.
8. Suspected instructions aimed at the marker, or selected visuals that cannot be screened, prevent automatic sign-off. The app shows provisional marks and requires a teacher to inspect the original PDF.

## Rubric currency
The bundled rubric is sourced from the *Physics guide* (February 2023, updated November 2024), first assessment 2025. The IB's 2026 Physics examiner instructions continue to use the same four criteria and 24-mark structure. Current-session application notes are recorded in `criteria/ib_phy_ia_criteria.md`.

## How visuals are read and used
1. **Visual extraction**: embedded raster images are extracted from the PDF. Vector graphics are detected and rasterized per page for vision analysis when possible.  
2. **Caption linking**: figure/table captions are inferred from IA text lines that start with `Figure`, `Fig.`, or `Table`. A caption is attached only when its page has one caption and one visual.
3. **Optional vision summaries**: when enabled, selected visuals are summarized by a vision-capable model using a strict, five-line schema (type, summary, chart details, table structure, readability issues). This option is off by default because the marking calls receive selected source images directly.
4. **Coverage reporting**: the app produces a content coverage report that flags missing text, OCR usage/quality, and unresolved figure/table labels.
5. **Marking safeguards**: the IA text and directly attached original PDF visuals can support Page N citations. Extraction reports are diagnostics; separate vision summaries remain uncited hints. Citations to pages outside the PDF are rejected.

**Reliability notes**
- Vector graphics are rasterized per page; low-resolution source PDFs can still limit chart/table readability.
- OCR confidence warnings and “no-text” page flags are intended to prevent over-reliance on unreadable content.
- Source-image selection is capped at six images per assessment. The auditor is instructed to request escalation if a necessary visual was not supplied or is unreadable.
- Instruction screening is heuristic. It can miss disguised or poorly extracted text, so all marks still need a check against the original IA before use.

## Calibration against human marks

The **Technical details** panel can download a scoring record containing marks, route, model usage and a PDF-derived case ID, without the student's PDF or report text. Add `human_marks` for each of the four criteria and optionally `human_review_required` (a Boolean) to each record. Save one JSON object per line in a JSONL file, then run `python eval_marking.py records.jsonl`. Keep the human marks blind to the app's result where possible. Each record carries a `pipeline` label, which changes whenever the marking flow changes, so results from different versions aren't mixed. The comparison reports criterion and total mark error, within-one-mark rates, human-review recall and average API usage. Use the same IAs to compare this workflow with any previous or alternative pipeline; no quality claim should be inferred until such a set is evaluated. Building this set is the first item in `todo.md`, and later prompt changes depend on it.

## Troubleshooting
- **No extractable text**: enable OCR or verify your PDF isn’t image-only.
- **OCR errors**: confirm Tesseract and the selected language data are installed.
- **PDF rendering errors**: check that the PDF opens normally and its password is correct; Poppler is not required.
- **Rate limits/timeouts**: retry after a short delay.
- **Encrypted PDFs**: enter the password in the field below the upload box.
- **"Needs another run" after a stage**: a report failed a format check (missing mark or citation, a page outside the PDF, or a total that doesn't match the marks). Rerun that stage.
- **Unverified quote warnings**: the quoted text wasn't found in the extracted text of the cited page. It may be fabricated, or the page may have extracted poorly (for example through OCR). Check the original PDF.

## Roadmap
- `todo.md` — marking-pipeline and UI follow-ups: measure against human marks first, then improve the prompts.
- `tasks.md` — extraction and visual-understanding upgrades, so unread photos, diagrams, graphs and tables are surfaced explicitly rather than marked unfairly.
