# PDF Visual Understanding Tasks

## Goal
Ensure the system can account for **all content in PDFs** (text, photos, diagrams, graphs, tables). Anything unread should be surfaced explicitly to avoid unfair marks.

## Milestone 1: Extraction coverage audit
- [x] Add per-page extraction diagnostics (text vs OCR vs image-only) and surface warnings in the UI.
- [x] Track OCR confidence (if available) and flag low-confidence pages/regions.
- [x] Record missing labels or unresolved figure/table references.

## Milestone 2: Image + figure extraction
- [x] Extract embedded images from PDFs (vector graphics still pending).
- [x] Link extracted visuals to nearby captions/figure numbers when possible.
- [x] Store extracted visuals for downstream analysis.
- [ ] Extract vector graphics (non-image drawings) from PDFs.

## Milestone 3: Visual understanding pipeline
- [ ] Add a vision-capable model pass for diagrams/photos.
- [ ] Add chart understanding (axes, trends, fit line, key values).
- [ ] Add table structure extraction (rows/columns/units/uncertainties).

## Milestone 4: Prompt + rubric integration
- [ ] Extend IA prompts to include visual summaries and tables/graphs outputs.
- [x] Require explicit mention when evidence is missing or unreadable.
- [x] Add a final “coverage report” section for the moderator.

## Milestone 5: Validation and UX
- [ ] Add tests for mixed-content PDFs (text + images + tables).
- [x] Provide a user-facing “content coverage” summary with actionable guidance.
- [x] Add an option to upload higher-quality scans if coverage is low.
