# PDF Visual Understanding Tasks

## Goal
Ensure the system can account for **all content in PDFs** (text, photos, diagrams, graphs, tables). Anything unread should be surfaced explicitly to avoid unfair marks.

## Completed work summary
- Added per-page extraction diagnostics (text vs OCR vs image-only), OCR confidence tracking, and missing-label reporting with UI warnings.
- Extracted embedded images and vector graphics, linked visuals to captions/figure numbers, and stored visuals for downstream analysis.
- Added vision-capable analysis for diagrams/photos, chart understanding, and table structure extraction.
- Extended IA prompts with visual summaries, missing-evidence callouts, and a moderator coverage report section.
- Added tests for mixed-content PDFs, and provided user-facing content coverage guidance plus higher-quality scan upload options.
- Hardened prompts with OCR confidence parsing fixes, anti-injection guidance, caption redaction, deduplicated citation guidance, and clearer trusted/untrusted input blocks.
- Moved label fabrication warnings into trusted prompts/coverage text and tightened output schemas to reduce format drift.
- Included PDF password (or derived flag) in document cache keys to avoid stale extractions.
- Added a visual-analysis output sanitizer for required five-line responses and reviewer flags.
- Added OCR coverage-quality warnings when confidence is missing, and cached coverage warnings for consistent UI.
- Added prompt QA checks for contradictions and ensured prompts separate IA evidence from visual-analysis hints.
- Rendered vector graphics for vision analysis, added visual prioritization with `max_visuals`, and required visual-to-text confirmation before influencing marking.
- Fixed digest citation handling to accept `--- Page N ---` markers and re-injected page headers for chunked pages.
- Added visual analysis sampling limits, reduced prompt redundancy, and defined minimal citation formats.
- Added regression tests for digest citation warnings, oversized chunking behavior, and prompt QA insertion.

---

## Bug fixes (code)

### High priority
- [ ] **Fix image-count diagnostics** (`pdf_utils.py:79-87`): Use `len(page_images)` from the extracted image list instead of `count_page_images(page)`. The `page.images` property can be non-sized, causing `image_count=0` even when images exist.
- [ ] **Add regression test for image-count accuracy**: Ensure image-count diagnostics match extracted visuals for image-only PDFs.
- [ ] **Capture figure/table label suffixes** (`app.py:240`): Update regex from `(\d+)` to `(\d+[a-zA-Z]*)` to capture labels like "Figure 2a", "Table 3i" for accurate unresolved-label reporting.

### Medium priority
- [ ] **Add optional DPI control or caching for vector rasterization**: Avoid repeated high-cost renders on large PDFs.
- [ ] **Narrow broad exception handlers** (`pdf_utils.py`): Replace `except Exception:` blocks with specific exception types (e.g., `AttributeError`, `TypeError`) to improve debuggability. Currently ~15 instances silently swallow errors.

### Low priority (code quality)
- [ ] **Fix dataclass Exception inheritance** (`app.py:89-92`, `pdf_utils.py:37-39`): `LLMError` and `PdfExtractionError` dataclasses don't call `Exception.__init__`, so `str(exc)` returns empty string. Not breaking (code uses `.user_message` directly) but non-idiomatic.

---

## Prompt improvements (for human-equivalent marking quality)

### High priority - Examiner differentiation
- [ ] **Differentiate Examiner 1 and 2 personas**: Currently near-identical (only one sentence differs). Create genuinely distinct marking perspectives:
  - **Examiner 1 ("The Experimentalist")**: Emphasize practical methodology, equipment choices, control variables, reproducibility. Key question: "Could I reproduce this in my lab with these instructions?"
  - **Examiner 2 ("The Analyst")**: Emphasize statistical rigor, uncertainty propagation, data visualization quality, fit appropriateness. Key question: "Does the data processing support the claimed precision?"

### High priority - Calibration and boundaries
- [ ] **Add calibration examples to examiner prompts**: Include anonymized excerpts showing what each mark band looks like for each criterion. Example:
  - 6/6 Research Design: RQ with both variables, specific context citing physics principles, methodology specifies WHY chosen ranges
  - 4/6 Research Design: All elements present but one is superficial, reproducibility requires minor assumptions
  - 2/6 Research Design: RQ vague, no variables stated, procedure lacks detail
- [ ] **Add grade boundary guidance**: Explicit decision rules for distinguishing adjacent bands (e.g., "Award 6 when... Award 5 when..."). Currently prompts say "if between bands, state why" but give no criteria.

### Medium priority - Physics-specific assessment
- [ ] **Add physics-specific data processing checks**: Extend the "Data processing checks" section with:
  - Linearization appropriateness (e.g., T² vs L for pendulum, correct transformed uncertainties)
  - Significant figure conventions (final results match measurement precision, intermediate calcs carried to extra precision)
  - Error bar sizing and presence on graphs
  - Residual analysis interpretation (random vs systematic patterns)
  - Fit choice justification (not just "best R²" but theoretically motivated)
- [ ] **Enhance visual analysis prompt** (`app.py:504-532`): Add physics-specific checks:
  - Are error bars present and appropriately sized?
  - Is the fit type theoretically justified?
  - Are residuals random or showing systematic pattern?
  - Do axes start from zero when appropriate?
  - Is linearization the standard approach for the phenomenon?

### Medium priority - Moderator improvements
- [ ] **Add escalation criteria to moderator prompt**: Guidance for:
  - Handling 3+ mark disagreements between examiners
  - Flagging borderline cases for human review
  - When to override both examiners if evidence contradicts their claims
- [ ] **Add holistic assessment guidance**: Rubric descriptors are applied per-clause, but IB marking allows some holistic judgment. Add guidance on whether strong evidence in one area can compensate for weakness in another within the same criterion.

### Low priority - Additional improvements
- [ ] **Add quantitative thresholds where possible**: The rubric uses terms like "appropriate" and "sufficient" without numbers. Add guidance such as:
  - "Appropriate number of trials" typically means ≥5 repeats
  - "Appropriate uncertainty" typically means percentage uncertainties <10% for main measurements
  - "Sufficient data range" typically means ≥5 data points spanning the independent variable
- [ ] **Add common pitfall warnings**: Flag common student errors that affect specific criteria:
  - Research Design: Confusing aim with research question, missing control variables
  - Data Analysis: Inconsistent significant figures, missing uncertainty on processed data
  - Conclusion: Claiming precision beyond what uncertainties support
  - Evaluation: Generic improvements not linked to specific weaknesses

---

## Testing improvements
- [ ] **Add unit tests for core LLM functions**: `call_llm()`, `call_vision_llm()`, `analyze_visuals()`, `make_structured_digest()` have no test coverage.
- [ ] **Create golden test cases**: Known IAs with expected mark ranges to validate marking consistency.
- [ ] **Add inter-rater reliability testing**: Run multiple marking passes on same IA to measure variance.
