# IB DP Physics IA & EE Marker

Modern Streamlit workspace for reviewing IB DP Physics scientific investigations (IA, first assessment 2025 onward) and physics extended essays (EE, first assessment 2027) against their rubrics. The teacher selects IA or EE before marking. The app extracts page-linked evidence from a student PDF, proposes a mark, audits the evidence behind it, and moderates disputed or uncertain cases.

## Features
- **Rubric-driven marking** for the IA (Research design, Data analysis, Conclusion, Evaluation; 24 marks) or the EE (Framework for the essay, Knowledge and understanding, Analysis and line of argument, Discussion and evaluation /8; 26 marks). The EE's Reflection criterion (/4, assessed from the Reflection and Progress Form) is not marked, so EE totals are out of 26 rather than the official 30; the app warns about this wherever EE marks appear.
- **Suggestions for improvement**: after each final decision, a separate, page-cited list of concise actions for the student, without marks, to send back before the final submission.
- **Annotated PDFs** (optional, sidebar toggle **Create annotated PDFs**, off by default to save cost): two annotated copies of the uploaded PDF. The **examiner copy** starts with the marks and the full final decision, then shows numbered margin notes linking highlighted evidence to each criterion. The **student copy** starts with the full suggestions list, then shows margin notes with actions to take, and never shows marks. Notes are drawn into a widened right margin, so every viewer shows and prints them.
- **Evidence audit** checks the primary mark's claims, calculations, citations and rubric fit.
- **Targeted moderation** for mark disagreements, audit concerns and source-coverage gaps; marks are never averaged.
- **Deterministic report checks** (no model involved): criterion marks, page citations, stated totals, audit mark consistency, and quotes checked against the cited page.
- **Concise IA feedback**: validated comments of at most 40 words, up to three per criterion, with quotes of at most 20 words. Credit, limitations, optional advice and teacher checks are distinct. Select **View Page** to inspect the source; expand **Teacher view** for marking rationale. Optional examiner and student margin notes also have a 40-word maximum and three-per-criterion cap.
- **Clear review signals**: the total is shown as provisional, with a teacher-review banner, when the moderator asks for review, a final-decision quote can't be verified, screening flags the IA, or any material IA source-coverage gap remains unresolved after moderation.
- **PDF text extraction + OCR fallback** for scanned documents, with per-page diagnostics.
- **Digest navigation for large IAs**: retrieve original pages before marking; omitted original pages remain provisional. The EE retains its existing digest-and-moderation workflow.
- **Original PDF visuals supplied directly to marking calls**, with source-page labels and a reviewable preview.
- **Coverage reporting** that flags missing text, OCR confidence, and unresolved figure/table labels.
- **Instruction screening** that withholds likely marker-directed text or visuals and requires teacher review of flagged IAs.
- **One-click complete assessment**, stage-by-stage reruns, a progress tracker, a total with per-criterion bars, and downloadable Markdown reports.
- **Password gate + cooldown** to reduce unauthorized access attempts.

## Repository layout
- `app.py` — Streamlit UI and theme CSS, extraction flow, stage runners, and report generation.
- `llm_utils.py` — OpenAI calls, digesting and visual analysis, kept free of Streamlit so they can be tested.
- `assessment.py` — validated IA assessment records, concise annotations, source selection and report rendering.
- `app_utils.py` — prompt QA helpers, page chunking, report validation and parsing, moderation routing, quote checks, and scoring-record export.
- `pdf_utils.py` — PDF parsing, encryption detection, page rendering (once per page), OCR, and visual extraction helpers.
- `criteria/ib_phy_ia_criteria.md` and `criteria/ib_phy_ee_criteria.md` — IA and EE rubric content used in prompts.
- `prompts/` — prompt templates for the primary marker, evidence auditor and moderator (`examiner1/examiner2/moderator_prompt.md` for the IA, `ee_*_prompt.md` for the EE).
- `eval_marking.py` — compare exported scoring records with qualified human marks.
- `tests/` — unit tests for marking safeguards, report parsing, prompts, PDF extraction, and the model-calling helpers (with a fake client, never the real API).
- `.streamlit/config.toml` — theme colours (kept in sync with the CSS tokens in `app.py`) and toolbar settings.
- `assets/` — PanPhy logo and favicon. The header logo links to https://panphy.app.
- `todo.md` — the single list of open work, in recommended order.
- `AGENTS.md` — concise contributor guidance and marking safeguards; `CLAUDE.md` points to it.

## Development

Install `requirements.txt`, then run `streamlit run app.py` or `pytest tests/`. PDF rendering uses the bundled PDFium package; OCR requires Tesseract. Streamlit Community Cloud installs Tesseract from `packages.txt`. Set `OPENAI_API_KEY` and `APP_PASSWORD` through Streamlit secrets or environment variables before running the app. Keep secrets and student PDFs out of the repository.

## Usage
1. Open the app in your browser and enter the workspace password.
2. Optionally adjust the sidebar settings: OCR, extra visual summaries, annotated PDFs, and (under **Advanced**) the OCR language.
3. Choose **Internal assessment (IA)** or **Extended essay (EE)**. Marking stays disabled until one is selected; changing it clears earlier reports.
4. Upload the student PDF. If it is encrypted, enter its password in the field that appears. For an EE, no Reflection and Progress Form (RPF) is needed: Reflection is not marked and the total is out of 26.
5. Select **Run complete assessment**. The progress tracker shows each stage; **Advanced · run or repeat one stage** reruns a single stage.
6. Read the results banner first. It says whether the decision is ready or needs teacher review, and why.
7. Review the final decision, primary mark, evidence audit and the **Source evidence** tab (page counts, coverage report, evidence index and the original visuals).
8. Read the **Suggestions for improvement** below the reports. Check them against the draft, then download them (Markdown, or the annotated student PDF) to send to the student. Download the annotated examiner PDF from the row under the results. If the suggestions or notes fail, the marks are kept and **Advanced · run or repeat one stage → Write suggestions & notes** retries them.
9. Download the final decision, the complete Markdown bundle (which ends with the suggestions), or (under **Technical details**) the scoring record for calibration.

## Configuration notes
- **Models**: marking and visual analysis use `gpt-6.1-sol` (released September 2026) through the Responses API.
- **Reasoning**: marking and adjudication use high reasoning effort; evidence-preserving digest work uses low effort.
- **OCR**: toggle in the sidebar; choose an installed Tesseract language under **Advanced**.
- **Digesting**: above 180,000 extracted characters, the IA uses a descriptive digest to select whole original pages (up to 150,000 characters per marking stage). Only original source text and supplied visuals support annotations. Omitted pages, including any single page exceeding the budget, keep the result provisional. EE marking continues to use the digest and always escalates summarized work.
- **Visual analysis**: vector graphics are rasterized per page. Optional extra vision summaries are off by default; selected original visuals still go directly to marking calls.
- **Storage**: `STORE_RESPONSES` (in `llm_utils.py`) is `False` by default for privacy.
- **Password throttle**: the app shares a 5-minute cooldown across browser sessions in one server process after five failed attempts. Deployments with multiple worker processes need an external shared rate limiter.
- **Encrypted PDFs**: a password field appears below the upload box when the PDF needs one.
- **Model details**: the marking and visual models and the rubric version are listed under **Advanced** in the sidebar.
- **Theme**: a light "lab notebook" palette matched to the PanPhy logo. Colours live in `.streamlit/config.toml` and the matching CSS tokens at the top of the UI section in `app.py`; keep them in sync. The theme is locked to light mode.

## How marking works
1. The PDF is parsed page-by-page. OCR is attempted on pages with no selectable text and on image-heavy pages with only a short selectable header (if enabled).
2. A large IA gets a descriptive navigation digest. Each marking stage retrieves original pages before judging the evidence; the digest is not marking evidence.
3. The app builds a page index and exact candidate excerpts for rubric areas; these are navigation aids, not verified claims. A primary marker applies all four criteria and cites original pages.
4. An evidence auditor checks the primary claims and missed strengths against original evidence. IA audit and moderation can retrieve further visuals and enlarged pages for unresolved checks.
5. IA stages return validated records with exact original-text quote checks, supplied visual IDs and readability verdicts. Reports, bands and totals are rendered centrally; malformed records get one repair attempt. EE reports retain their Markdown mark, total, citation and quote checks. Quote matching verifies location, not scientific interpretation.
6. Exact agreement without evidence warnings finalizes the corrected audited IA record. Mark disagreement, audit concerns or source gaps trigger moderation. Remaining source gaps stay provisional even if the moderator says no review is needed. At 6/6 the IA report says “Maximum mark achieved”; optional enrichment is not a reason to withhold marks.
7. If the Chief Moderator recommends human review, or quotes text that is not on the cited page, the app shows the marks as provisional and asks for teacher review.
8. Suspected instructions aimed at the marker, or selected visuals that cannot be screened, prevent automatic sign-off. The app shows provisional marks and requires a teacher to inspect the original PDF.
9. A final call (`prompts/suggestions_prompt.md`) turns the final decision into student-facing suggestions: top priorities, then 2–4 actions per criterion, each citing a page. The app checks that every criterion has a cited section, that cited pages exist and that no marks are stated, and warns about quotes not found on the cited page. When annotated PDFs are on, the same call also returns the student's margin notes (`prompts/student_notes_prompt.md` is appended); notes mentioning marks or grades are dropped.
10. When annotated PDFs are on, validated IA annotations supply examiner margin notes without another model call. EE examiner notes still use `prompts/examiner_notes_prompt.md`. With the toggle off, neither set of notes is requested, so the run makes no extra call. For both PDFs (`pdf_annotate.py`), each note's quote is searched in the page's text layer and highlighted. A quote that isn't found (for example on an OCR-only page) becomes a page note, and the download says how many. An encrypted upload's annotated copies keep its password. None of this affects marks.

## Rubric currency
The bundled IA rubric is sourced from the *Physics guide* (February 2023, updated November 2024), first assessment 2025. The IB's 2026 Physics examiner instructions continue to use the same four criteria and 24-mark structure. Current-session application notes are recorded in `criteria/ib_phy_ia_criteria.md`.

The EE rubric follows the *Extended essay guide* for first assessment 2027 (five criteria, 30 marks), which replaced the 34-mark model. **Its descriptors are currently a close paraphrase from secondary summaries, not the official text**, because the guide could not be downloaded when the option was added. Replace them with the verbatim guide wording before relying on EE marks (see `todo.md`). The EE prompts add physics-specific application notes. Criterion E (Reflection) is not marked, because the RPF is usually unavailable when the app is used; EE marks are out of 26.

## How visuals are read and used
1. **Visual extraction**: embedded raster images are extracted from the PDF. Vector graphics are detected and rasterized per page for vision analysis when possible.  
2. **Caption linking**: figure/table captions are inferred from IA text lines that start with `Figure`, `Fig.`, or `Table`. A caption is attached only when its page has one caption and one visual.
3. **Optional vision summaries**: when enabled, selected visuals are summarized by a vision-capable model using a strict, five-line schema (type, summary, chart details, table structure, readability issues). This option is off by default because the marking calls receive selected source images directly.
4. **Coverage reporting**: the app produces a content coverage report that flags missing text, OCR usage/quality, and unresolved figure/table labels.
5. **Marking safeguards**: the IA text and directly attached original PDF visuals can support Page N citations. Extraction reports are diagnostics; separate vision summaries remain uncited hints. Citations to pages outside the PDF are rejected.

**Reliability notes**
- Vector graphics are rasterized per page; low-resolution source PDFs can still limit chart/table readability.
- OCR confidence warnings and “no-text” page flags are intended to prevent over-reliance on unreadable content.
- IA selection starts with six visuals, prioritizing data, graphs, uncertainty work and apparatus evidence. Each later stage can add up to six unsupplied visuals and six enlarged pages requested by earlier checks. Coverage is per item: one image does not cover other images on the same page; a full-page render does. Uninspected items remain review gaps. EE retains its six-image selection.
- IA visual readability statuses are model-reported review aids, not independent verification. In the final-decision tab, the optional highlighted examiner copy uses native PDF comments and unique literal text matches; ambiguous/OCR-only locations receive page notes. The original file is unchanged, and encrypted exports use AES-256 with the original password. The existing printable margin-note copies remain available.
- Instruction screening is heuristic. It can miss disguised or poorly extracted text, so all marks still need a check against the original IA before use.

## Calibration against human marks

The **Technical details** panel can download a scoring record containing marks, route, model usage, the assessment type (`ia` or `ee`) and a PDF-derived case ID, without the student's PDF or report text. Add `human_marks` for each criterion of that assessment and optionally `human_review_required` (a Boolean) to each record. Save one JSON object per line in a JSONL file, then run `python eval_marking.py records.jsonl`. Keep the human marks blind to the app's result where possible. Each record carries a `pipeline` label (`source_anchored_v2` for the IA, `ee_evidence_audit_v2` for the EE; `ee_evidence_audit_v1` records include Reflection and are out of 30), which changes whenever the marking flow changes, so results from different versions or assessment types aren't mixed. The comparison reports criterion and total mark error, within-one-mark rates, human-review recall and average API usage. It also gives the same accuracy figures separately for the primary mark, the audit and the final decision (`stages`), how cases were decided (`decision_modes`), and how often each escalation reason fired. To check consistency, mark the same IAs more than once and run `python eval_marking.py --variance records.jsonl`, which reports how much each criterion's mark changes between runs and needs no human marks. Use the same IAs to compare this workflow with any previous or alternative pipeline; no quality claim should be inferred until such a set is evaluated. Building this set is the first item in `todo.md`, and later prompt changes depend on it.

Calibration also reports signed bias, paired stage improvements/worsening, and repeated-run differences grouped by model and configuration. Optionally add teacher-labelled `annotation_reviews` with Boolean `citation_correct`, `supported`, and `actionable` fields, plus a nonnegative `missed_strengths_count`. Missing labels are excluded, not assumed correct. See [CALIBRATION.md](CALIBRATION.md) for the protocol; automated synthetic tests do not establish marking accuracy.

## Troubleshooting
- **No extractable text**: enable OCR or verify your PDF isn’t image-only.
- **OCR errors**: confirm Tesseract and the selected language data are installed.
- **PDF rendering errors**: check that the PDF opens normally and its password is correct; Poppler is not required.
- **Rate limits/timeouts**: retry after a short delay.
- **Encrypted PDFs**: enter the password in the field below the upload box.
- **"Needs another run" after a stage**: a report failed a format check (missing mark or citation, a page outside the PDF, or a total that doesn't match the marks). Rerun that stage.
- **Unverified quote warnings**: the quoted text wasn't found in the extracted text of the cited page. It may be fabricated, or the page may have extracted poorly (for example through OCR). Check the original PDF.

## Roadmap
Open work is tracked in `todo.md`. Measuring against human marks comes first, then prompt improvements; engineering tasks such as faster page rendering and tighter error handling can be done at any time.
