# IB DP Physics IA Marker

Streamlit app that marks IB DP Physics Internal Assessments using the official rubric. It extracts text from a student IA PDF (with optional OCR), injects the rubric and IA into structured prompts, and produces examiner/moderator markdown reports.

## Features
- **Rubric-driven marking** for Research design, Data analysis, Conclusion, and Evaluation.
- **Two examiner personas + chief moderator** for cross-checking and adjudication.
- **PDF text extraction + OCR fallback** for scanned documents.
- **Digest mode** for large IAs to fit within model context limits.
- **Downloadable markdown reports** and optional debug info.
- **Password gate + cooldown** to reduce unauthorized access attempts.

## Repository layout
- `app.py` — Streamlit UI, PDF extraction, OpenAI calls, and report generation.
- `criteria/ib_phy_ia_criteria.md` — rubric content used in prompts.
- `prompts/` — prompt templates for the two examiners and moderator.
- `pdf_utils.py` — PDF parsing and OCR helpers (pypdf + pdf2image + Tesseract).
- `tests/` — minimal unit tests for PDF helpers.

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
- **Digesting**: large PDFs are summarized into a structured digest before marking.
- **Storage**: `STORE_RESPONSES` is `False` by default for privacy.
- **Password throttle**: the app blocks repeated failed password attempts for 5 minutes.
- **Encrypted PDFs**: supply a PDF password in the sidebar if needed.

## How marking works
1. The PDF is parsed page-by-page. If a page has no selectable text, OCR is attempted (if enabled).
2. If the IA is too large, it is summarized into a structured digest to fit the model context.
3. Two examiner prompts produce independent reports.
4. A moderator prompt adjudicates the final report using the IA, rubric, and both examiner reports.

## Troubleshooting
- **No extractable text**: enable OCR or verify your PDF isn’t image-only.
- **OCR errors**: confirm Tesseract is installed and the language code exists.
- **PDF extraction errors**: ensure Poppler is installed and accessible.
- **Rate limits/timeouts**: retry after a short delay.
- **Encrypted PDFs**: provide the password in the sidebar if prompted.
