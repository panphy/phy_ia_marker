# IB DP Physics IA Marker

Modern Streamlit workspace for reviewing IB DP Physics scientific investigations (first assessment 2025 onward) against the current official rubric. It extracts page-linked evidence from a student PDF, proposes a mark, audits the evidence behind it, and moderates disputed or uncertain cases.

## Features
- **Rubric-driven marking** for Research design, Data analysis, Conclusion, and Evaluation.
- **Evidence audit** checks the primary mark's claims, calculations, citations and rubric fit.
- **Targeted moderation** for mark disagreements, audit concerns and source-coverage gaps; marks are never averaged.
- **PDF text extraction + OCR fallback** for scanned documents, with per-page diagnostics.
- **Digest navigation** for large IAs: retrieves original pages before marking; omitted pages keep the result provisional.
- **Original PDF visuals supplied directly to marking calls**, with source-page labels and a reviewable preview.
- **Coverage reporting** that flags missing text, OCR confidence, and unresolved figure/table labels.
- **Instruction screening** that withholds likely marker-directed text or visuals and requires teacher review of flagged IAs.
- **Validated assessment records** with centrally calculated totals, exact source-quote checks, per-visual readability checks and one bounded repair attempt.
- **Concise annotations**: up to three per criterion, each at most 40 words plus a source quote of at most 20 words. Credit, limitations, optional advice and teacher checks are distinct.
- **Source navigation and annotated PDF downloads**: jump to a cited page; exact unique text matches are highlighted. Visuals, scans and ambiguous text receive page notes instead of guessed highlights.
- **One-click complete assessment**, stage-by-stage reruns, score cards and downloadable Markdown reports. Unresolved evidence gaps remain provisional after moderation.
- **Password gate + cooldown** to reduce unauthorized access attempts.

## Repository layout
- `app.py` — Streamlit UI, extraction flow, OpenAI calls, and report generation.
- `app_utils.py` — prompt QA helpers, page chunking, and citation validation.
- `assessment.py` — structured record validation, concise comments, source selection and report rendering.
- `pdf_utils.py` — PDF parsing, OCR, and visual extraction helpers.
- `criteria/ib_phy_ia_criteria.md` — rubric content used in prompts.
- `prompts/` — prompt templates for the primary marker, evidence auditor and moderator.
- `eval_marking.py` — compare exported scoring records with qualified human marks.
- `tests/` — unit tests for prompt QA and PDF extraction utilities.
- `tasks.md` — roadmap and follow-up tasks.
- `AGENTS.md` — concise contributor guidance and marking safeguards; `CLAUDE.md` points to it.

## Development

Install `requirements.txt`, then run `streamlit run app.py` or `pytest tests/`. PDF rendering uses the bundled PDFium package; OCR requires Tesseract. Streamlit Community Cloud installs Tesseract from `packages.txt`. Set `OPENAI_API_KEY` and `APP_PASSWORD` through Streamlit secrets or environment variables before running the app. Keep secrets and student PDFs out of the repository.

## Usage
1. Open the app in your browser.
2. Enter the app password.
3. Upload a student IA PDF.
4. Select **Run complete assessment**.
5. Review the concise feedback; select **View Page** to inspect the cited source. Expand **Teacher view** for marking rationale.
6. Resolve any teacher checks before using provisional marks. Review the evidence audit and per-visual coverage.
7. Download the decision, complete Markdown bundle, or annotated IA. PDF comments can be opened in a PDF reader; encrypted uploads retain their password on export.

## Configuration notes
- **Models**: marking and visual analysis use `gpt-6-sol` through the Responses API.
- **Reasoning**: marking and adjudication use high reasoning effort; evidence-preserving digest work uses low effort.
- **OCR**: toggle in the sidebar; set OCR language via the text input.
- **Digesting**: above 180,000 extracted characters, a descriptive digest helps select original pages. Each marking stage receives up to 150,000 characters of whole original pages; it does not mark from the digest. Omitted pages are explicitly flagged for teacher review. Very large individual pages may exceed this budget and remain unverified.
- **Visual analysis**: vector graphics are rasterized per page. Optional extra vision summaries are off by default; selected original visuals still go directly to marking calls.
- **Storage**: `STORE_RESPONSES` is `False` by default for privacy.
- **Password throttle**: the app shares a 5-minute cooldown across browser sessions in one server process after five failed attempts. Deployments with multiple worker processes need an external shared rate limiter.
- **Encrypted PDFs**: supply a PDF password in the sidebar if needed.

## How marking works
1. The PDF is parsed page-by-page. OCR is attempted on pages with no selectable text and on image-heavy pages with only a short selectable header (if enabled).
2. If the IA is too large, a descriptive digest guides source-page retrieval. Only original page text and directly supplied visuals support annotations.
3. The app builds a page index and exact candidate excerpts for rubric areas; these are navigation aids, not verified claims. A primary marker applies all four criteria and cites original pages.
4. An evidence auditor checks primary claims and missed strengths against original evidence. Audit and moderation can retrieve additional visuals and enlarged page renders for unresolved checks.
5. Exact agreement with no evidence warning is finalized using the audited record. A mark difference, audit concern or coverage gap goes to the Chief Moderator. Moderation alone cannot clear a remaining source gap: it stays provisional. The UI honors the final human-review verdict.
6. Suspected instructions aimed at the marker, or selected visuals that cannot be screened, prevent automatic sign-off. The app shows provisional marks and requires a teacher to inspect the original PDF.

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
- Initial source-image selection is capped at six visuals, prioritizing data, graphs, uncertainty work and apparatus evidence. Each later stage can add up to six unsupplied visuals and up to six enlarged pages requested by earlier checks. Full-page renders cover all detected items on that page; a single extracted image does not. Uninspected items remain explicit review gaps, including uncaptioned items.
- Each supplied visual receives a model-reported readable/unreadable/not-needed status. These are review aids, not independent verification.
- Quote matching verifies source location, not scientific interpretation. Annotated PDF highlights require a unique literal text match; text reflow, OCR or repeated quotations can produce page notes instead. PDF output is built in memory without changing the original upload.
- At 6/6 the report says “Maximum mark achieved.” Optional enrichment never counts as a reason to withhold marks.
- Instruction screening is heuristic. It can miss disguised or poorly extracted text, so all marks still need a check against the original IA before use.

## Calibration against human marks

The **Technical details** panel can download a scoring record containing marks, route, model usage and a PDF-derived case ID, without the student's PDF or report text. Add `human_marks` for each of the four criteria and optionally `human_review_required` (a Boolean) to each record. Save one JSON object per line in a JSONL file, then run `python eval_marking.py records.jsonl`. Keep the human marks blind to the app's result where possible. The comparison reports criterion and total mark error, signed bias (positive means overmarking), within-one-mark rates, human-review recall and average API usage. Paired stage comparisons measure changes in criterion error after audit and moderation; negative change means improvement. Repeated runs of the same case, model and configuration report criterion variation and total-mark range. Use the same IAs to compare this workflow with any previous or alternative pipeline; no quality claim should be inferred until such a set is evaluated.

For teacher evaluation of annotations, optionally add `annotation_reviews`, a list with Boolean `citation_correct`, `supported`, and `actionable` labels (omit nonapplicable labels). Add `missed_strengths_count` as a nonnegative integer for a reviewed case. These labels must come from a teacher, not the marking model. The evaluator reports rates with their denominators and missing-strength counts. See [calibration guide](CALIBRATION.md) for the evaluation protocol.

## Troubleshooting
- **No extractable text**: enable OCR or verify your PDF isn’t image-only.
- **OCR errors**: confirm Tesseract is installed and the language code exists.
- **PDF rendering errors**: check that the PDF opens normally and its password is correct; Poppler is not required.
- **Rate limits/timeouts**: retry after a short delay.
- **Encrypted PDFs**: provide the password in the sidebar if prompted.

## Visual coverage roadmap
To avoid unfair marks when PDFs contain photos, diagrams, graphs, or tables, see `tasks.md` for the planned extraction and visual-understanding upgrades that will surface unread content explicitly.
