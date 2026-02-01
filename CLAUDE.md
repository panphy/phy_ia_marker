# CLAUDE.md - AI Assistant Guide for IB DP Physics IA Marker

## Project Overview

This is an **IB DP Physics Internal Assessment (IA) Marker** - a Streamlit web application that automatically marks IB Diploma Programme Physics IAs using OpenAI language models. The system implements a **three-examiner approach**: two independent AI examiners provide initial marks, and a chief moderator adjudicates the final verdict based on the official IB rubric.

**Key Capabilities:**
- PDF text extraction with OCR fallback for scanned documents
- Visual extraction and analysis (images, diagrams, charts, tables)
- Rubric-driven marking across 4 criteria (max 24 marks total)
- Content coverage diagnostics with missing evidence flagging
- Digest mode for large documents to fit model context limits
- Password-protected access with rate limiting

## Repository Structure

```
phy_ia_marker/
├── app.py                          # Main Streamlit application (~1400 lines)
├── app_utils.py                    # Prompt QA, chunking, citation utilities
├── pdf_utils.py                    # PDF parsing, OCR, visual extraction
├── requirements.txt                # Python dependencies
├── README.md                       # User documentation
├── tasks.md                        # Development roadmap and follow-up tasks
├── criteria/
│   └── ib_phy_ia_criteria.md       # Official IB Physics IA rubric (4 criteria)
├── prompts/
│   ├── examiner1_prompt.md         # First examiner persona prompt
│   ├── examiner2_prompt.md         # Second examiner persona prompt
│   └── moderator_prompt.md         # Chief moderator adjudication prompt
└── tests/
    ├── conftest.py                 # Pytest configuration
    ├── test_app_utils.py           # Tests for utility functions
    └── test_pdf_extraction.py      # PDF extraction tests
```

## Key Files and Responsibilities

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI, PDF extraction orchestration, OpenAI API calls, report generation, session state management |
| `app_utils.py` | Prompt QA verification, page splitting/chunking, citation validation, visual sampling |
| `pdf_utils.py` | PDF text extraction, OCR integration, image/visual extraction, encryption handling |
| `criteria/ib_phy_ia_criteria.md` | The official IB rubric used in all marking prompts |
| `prompts/*.md` | Structured prompt templates with placeholders for IA content, rubric, and reports |

## Architecture Decisions

### Three-Examiner System
Two independent AI examiners mark the IA separately, then a moderator adjudicates based on both reports. This ensures cross-validation and reduces bias.

### Trust Boundaries
The codebase explicitly separates **trusted** content (rubric, system prompts, coverage reports) from **untrusted** content (student IA text, visual analysis). Prompts include anti-injection instructions.

### Digest Mode
Large PDFs (>180K chars) are automatically compressed into structured digests (~70K chars) that preserve marking-relevant evidence (numbers, units, uncertainties, figure/table references) while keeping page-range citations.

### Visual Analysis Safeguards
Visual analysis from the vision model is treated as "hints only" - prompts require that only IA text or the coverage report can be cited as evidence for marks.

## Configuration Constants (app.py)

```python
DEFAULT_MODEL = "gpt-5-mini"                    # LLM for text analysis
DEFAULT_VISION_MODEL = "gpt-5-mini"             # Vision model for images
MAX_RAW_CHARS_BEFORE_DIGEST = 180_000           # Trigger digest mode threshold
DIGEST_TARGET_CHARS = 70_000                    # Target digest size
DIGEST_CHUNK_TARGET_CHARS = 30_000              # Chunk size for digestion
OCR_CONFIDENCE_WARNING_THRESHOLD = 60.0         # Flag low-confidence OCR
MAX_VISUALS_PER_ANALYSIS = 12                   # Limit vision API calls
MAX_UNCAPTIONED_VISUALS = 4                     # Limit uncaptioned visuals
MAX_PASSWORD_ATTEMPTS = 5                       # Rate limiting threshold
PASSWORD_ATTEMPT_WINDOW_SECONDS = 300           # 5-minute cooldown
STORE_RESPONSES = False                         # Privacy-friendly (no OpenAI storage)
```

## Development Commands

### Running the Application
```bash
streamlit run app.py
```

### Running Tests
```bash
pytest tests/
```

### Required System Dependencies
- **Tesseract** - OCR engine
- **Poppler** - PDF utilities (pdftoppm, pdfimages)

## Code Conventions

### Type Hints
Full type annotations are used throughout:
```python
def extract_pdf_text(pdf_bytes: bytes, ocr_lang: str = "eng") -> tuple[str, list[PageExtractionDiagnostic], list[ExtractedVisual]]:
```

### Dataclasses
Structured data uses dataclasses:
- `AIResult` - LLM response with metadata
- `LLMError` - API error with debug info
- `PageExtractionDiagnostic` - Per-page extraction status
- `ExtractedVisual` - Extracted image with metadata

### Error Handling
- `PdfExtractionError` - Base PDF error class
- `PdfPasswordRequiredError` - Encrypted PDF requiring password
- User-friendly error messages via `st.error()`

### Naming Conventions
- `snake_case` for functions and variables
- `UPPER_CASE` for constants
- `PascalCase` for classes

### Session State Keys (app.py)
```python
# Password state
password_ok, failed_attempts, last_failed_at

# Generated reports
examiner1_report, examiner2_report, moderator_report

# Extracted document cache
ia_ready_text, ia_used_digest, ia_coverage_report
ia_page_diagnostics, ia_coverage_warnings
ia_extracted_visuals, ia_visual_analysis
doc_cache_key, debug_info
```

## Testing Patterns

Tests use pytest with simple function-based tests:

```python
def test_some_feature():
    # Arrange
    input_data = ...

    # Act
    result = function_under_test(input_data)

    # Assert
    assert result == expected
```

### Test Coverage Areas
- Encrypted PDF handling (password-required, wrong password, correct password)
- Mixed-content PDFs (text + image pages)
- Page chunking with oversized pages
- Prompt QA insertion and verification
- Citation format validation
- Digest citation markers

## Security Features

1. **Password Protection** - Rate-limited with 5-minute cooldown after 5 failed attempts
2. **Prompt Injection Detection** - Regex patterns detect common injection phrases
3. **Injection Redaction** - Detected phrases are redacted before LLM processing
4. **Anti-Injection Instructions** - Explicit instructions to ignore embedded commands
5. **Trust Boundaries** - Explicit separation of trusted vs untrusted inputs
6. **Data Privacy** - `STORE_RESPONSES = False` prevents OpenAI storage

### Injection Detection Patterns (app.py:62-68)
```python
INJECTION_PHRASE_PATTERNS = [
    r"\bignore (?:all|any|previous|earlier) instructions\b",
    r"\bdisregard (?:all|any|previous|earlier) instructions\b",
    r"\b(system prompt|developer message)\b",
    r"\boverride (?:the )?system\b",
    r"\bjailbreak\b",
]
```

## Deployment

- **Platform**: Streamlit Cloud or self-hosted
- **Secrets**: Configure via `.streamlit/secrets.toml`:
  ```toml
  OPENAI_API_KEY = "sk-..."
  APP_PASSWORD = "..."
  ```

## Marking Rubric (4 Criteria, Max 24 Marks)

| Criterion | Max | Focus |
|-----------|-----|-------|
| Research Design | 6 | Research question, methodology, reproducibility |
| Data Analysis | 6 | Data recording, processing, uncertainty handling |
| Conclusion | 6 | Relevance, consistency, scientific context |
| Evaluation | 6 | Weaknesses, limitations, realistic improvements |

## Common Development Tasks

### Adding a New Prompt
1. Create `prompts/new_prompt.md` with placeholders: `{RUBRIC}`, `{IA_TEXT}`, `{COVERAGE_REPORT}`
2. Load in `app.py`: `NEW_PROMPT = load_prompt("new_prompt.md")`
3. Ensure prompt includes anti-injection guidance and trust boundary markers

### Modifying PDF Extraction
- Text extraction logic: `pdf_utils.py`
- Extraction diagnostics: `PageExtractionDiagnostic` dataclass
- Visual extraction: `ExtractedVisual` dataclass

### Updating the Rubric
- Edit `criteria/ib_phy_ia_criteria.md`
- The rubric is automatically injected into all prompts via `{RUBRIC}` placeholder

### Adding Tests
- Add test files to `tests/` directory
- Use `pytest` conventions
- Run with `pytest tests/`

## Known Issues / Follow-up Tasks

From `tasks.md`:
- Image-count diagnostics may show 0 even when images exist (fix needed)
- Figure/table labels with suffixes (e.g., "Figure 2a") not fully captured
- Vector rasterization lacks DPI control/caching for large PDFs

## Important Notes for AI Assistants

1. **Read before editing** - Always read files before proposing changes
2. **Test your changes** - Run `pytest tests/` after modifications
3. **Preserve security** - Maintain prompt injection protections
4. **Keep prompts separated** - Trusted vs untrusted content must remain distinct
5. **Citation validation** - Reports must include page markers for evidence-based marking
6. **Session state** - UI state is managed via Streamlit session state
7. **Privacy defaults** - Keep `STORE_RESPONSES = False` unless explicitly changed
