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

## Setup

### Prerequisites
- Python 3.10+
- Tesseract (for OCR)
- Poppler (for PDF rendering)

On macOS with Homebrew:
```bash
brew install tesseract poppler
```

On Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr poppler-utils
```

### Install dependencies
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure secrets
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
4. Generate both **Examiner 1** and **Examiner 2** reports.
5. Run the **Moderator** report once both examiner reports are available.
6. Download the generated report(s) as Markdown.

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
