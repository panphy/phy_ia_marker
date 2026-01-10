# IB DP Physics IA Marker (Rubric-based)

Streamlit app that marks IB DP Physics Internal Assessments using the official rubric. It extracts text from a student IA PDF (with optional OCR), injects the rubric and IA into structured prompts, and produces examiner/moderator markdown reports.

## Features
- **Rubric-driven marking** for Research design, Data analysis, Conclusion, and Evaluation.
- **Two personas**: strict examiner and skeptical moderator reports.
- **PDF text extraction + OCR fallback** for scanned documents.
- **Digest mode** for large IAs to fit within model context limits.
- **Downloadable markdown reports** and optional debug info.

## Repository layout
- `app.py` — Streamlit UI, PDF extraction, OpenAI calls, and report generation.
- `criteria/ib_phy_ia_criteria.md` — rubric content used in prompts.
- `prompts/` — prompt templates for examiner and moderator.

## Setup
1. Create a virtual environment (recommended).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Install system tools for PDF/OCR (required for OCR and some PDFs):
   - **Tesseract OCR** (for `pytesseract`).
   - **Poppler** (for `pdf2image`).

## Configure secrets
This app expects Streamlit secrets:

- `OPENAI_API_KEY` — your OpenAI API key.
- `APP_PASSWORD` — password gate for the UI.

Create `.streamlit/secrets.toml`:
```toml
OPENAI_API_KEY = "your-api-key"
APP_PASSWORD = "your-app-password"
```

## Run the app
```bash
streamlit run app.py
```

## Usage
1. Open the app in your browser.
2. Enter the app password.
3. Upload a student IA PDF.
4. Choose **Mark with Examiner** or **Mark with Moderator**.
5. Download the generated report as Markdown.

## Configuration notes
- **Model**: change in the sidebar or edit `DEFAULT_MODEL` in `app.py`.
- **OCR**: toggle in the sidebar; set OCR language via the text input.
- **Digesting**: large PDFs are summarized into a structured digest before marking.
- **Storage**: `STORE_RESPONSES` is `False` by default for privacy.

## Troubleshooting
- **No extractable text**: enable OCR or verify your PDF isn’t image-only.
- **OCR errors**: confirm Tesseract is installed and the language code exists.
- **PDF extraction errors**: ensure Poppler is installed and accessible.
- **Rate limits/timeouts**: retry after a short delay.
