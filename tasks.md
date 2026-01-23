# PDF Visual Understanding Tasks

## Goal
Ensure the system can account for **all content in PDFs** (text, photos, diagrams, graphs, tables). Anything unread should be surfaced explicitly to avoid unfair marks.

## Milestone 1: Extraction coverage audit
- [ ] Add per-page extraction diagnostics (text vs OCR vs image-only) and surface warnings in the UI.
- [ ] Track OCR confidence (if available) and flag low-confidence pages/regions.
- [ ] Record missing labels or unresolved figure/table references.

## Milestone 2: Image + figure extraction
- [ ] Extract embedded images and vector graphics from PDFs.
- [ ] Link extracted visuals to nearby captions/figure numbers when possible.
- [ ] Store extracted visuals for downstream analysis.

## Milestone 3: Visual understanding pipeline
- [ ] Add a vision-capable model pass for diagrams/photos.
- [ ] Add chart understanding (axes, trends, fit line, key values).
- [ ] Add table structure extraction (rows/columns/units/uncertainties).

## Milestone 4: Prompt + rubric integration
- [ ] Extend IA prompts to include visual summaries and tables/graphs outputs.
- [ ] Require explicit mention when evidence is missing or unreadable.
- [ ] Add a final “coverage report” section for the moderator.

## Milestone 5: Validation and UX
- [ ] Add tests for mixed-content PDFs (text + images + tables).
- [ ] Provide a user-facing “content coverage” summary with actionable guidance.
- [ ] Add an option to upload higher-quality scans if coverage is low.
