# IB DP Physics IA Marker

Streamlit app that marks IB DP Physics Internal Assessments (first assessment 2025) using the official rubric. It extracts text from a student IA PDF (with optional OCR), adds coverage diagnostics and visual analysis summaries, injects the rubric and IA into structured prompts, and produces examiner/moderator Markdown reports.

## Features
- **Rubric-driven marking** for Research design, Data analysis, Conclusion, and Evaluation.
- **Two examiner personas + chief moderator** for cross-checking and adjudication.
- **PDF text extraction + OCR fallback** for scanned documents, with per-page diagnostics.
- **Digest mode** for large IAs to fit within model context limits (auto-triggers over a size threshold).
- **Visual extraction + vision summaries** for raster images and vector graphics.
- **Coverage reporting** that flags missing text, OCR confidence, and unresolved figure/table labels.
- **Downloadable Markdown reports** and optional debug info.
- **Password gate + cooldown** to reduce unauthorized access attempts.

## Repository layout
- `app.py` — Streamlit UI, extraction flow, OpenAI calls, and report generation.
- `app_utils.py` — prompt QA helpers, page chunking, and citation validation.
- `pdf_utils.py` — PDF parsing, OCR, and visual extraction helpers.
- `criteria/ib_phy_ia_criteria.md` — rubric content used in prompts.
- `prompts/` — prompt templates for the two examiners and moderator.
- `tests/` — unit tests for prompt QA and PDF extraction utilities.
- `tasks.md` — roadmap and follow-up tasks.

## Usage
1. Open the app in your browser.
2. Enter the app password.
3. Upload a student IA PDF.
4. Generate both **Examiner 1** and **Examiner 2** reports.
5. Run the **Moderator** report once both examiner reports are available.
6. Download the generated report(s) as Markdown.

## Configuration notes
- **Model**: change in the sidebar or edit `DEFAULT_MODEL` in `app.py`.
- **OCR**: toggle in the sidebar; set OCR language via the text input.
- **Digesting**: large PDFs are summarized into a structured digest before marking. The digest
  preserves key evidence (numbers, units, uncertainties, figures/tables) and keeps page-range
  labels so citations can still reference where evidence came from.
- **Visual analysis**: vector graphics are rasterized per page and summarized by a vision-capable model.
- **Storage**: `STORE_RESPONSES` is `False` by default for privacy.
- **Password throttle**: the app blocks repeated failed password attempts for 5 minutes.
- **Encrypted PDFs**: supply a PDF password in the sidebar if needed.

## How marking works
1. The PDF is parsed page-by-page. If a page has no selectable text, OCR is attempted (if enabled).
2. If the IA is too large, it is automatically summarized into a structured digest to fit the model
   context. The digest keeps page-range labels so evidence can still be cited.
3. Two examiner prompts produce independent reports.
4. A moderator prompt adjudicates the final report using the IA, rubric, and both examiner reports.

## How visuals are read and used
1. **Visual extraction**: embedded raster images are extracted from the PDF. Vector graphics are detected and rasterized per page for vision analysis when possible.  
2. **Caption linking**: figure/table captions are inferred from IA text lines that start with `Figure`, `Fig.`, or `Table`, and attached to visuals on the same page when possible.
3. **Vision analysis**: extracted raster visuals are summarized by a vision-capable model using a strict, five-line schema (type, summary, chart details, table structure, readability issues).
4. **Coverage reporting**: the app produces a content coverage report that flags missing text, OCR usage/quality, and unresolved figure/table labels.
5. **Marking safeguards**: prompts require that **only IA text or the coverage report can be cited as evidence**. Visual analysis is treated as **uncited hints** and must remain separate from evidence-backed claims.

**Reliability notes**
- Vector graphics are rasterized per page; low-resolution source PDFs can still limit chart/table readability.
- OCR confidence warnings and “no-text” page flags are intended to prevent over-reliance on unreadable content.
- For planned upgrades (visual prioritization and cross-checking visual hints against IA text), see `tasks.md`.

## Troubleshooting
- **No extractable text**: enable OCR or verify your PDF isn’t image-only.
- **OCR errors**: confirm Tesseract is installed and the language code exists.
- **PDF extraction errors**: ensure Poppler is installed and accessible.
- **Rate limits/timeouts**: retry after a short delay.
- **Encrypted PDFs**: provide the password in the sidebar if prompted.

## Visual coverage roadmap
To avoid unfair marks when PDFs contain photos, diagrams, graphs, or tables, see `tasks.md` for the planned extraction and visual-understanding upgrades that will surface unread content explicitly.
