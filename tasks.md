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
- [x] Extract vector graphics (non-image drawings) from PDFs.

## Milestone 3: Visual understanding pipeline
- [x] Add a vision-capable model pass for diagrams/photos.
- [x] Add chart understanding (axes, trends, fit line, key values).
- [x] Add table structure extraction (rows/columns/units/uncertainties).

## Milestone 4: Prompt + rubric integration
- [x] Extend IA prompts to include visual summaries and tables/graphs outputs.
- [x] Require explicit mention when evidence is missing or unreadable.
- [x] Add a final “coverage report” section for the moderator.

## Milestone 5: Validation and UX
- [x] Add tests for mixed-content PDFs (text + images + tables).
- [x] Provide a user-facing “content coverage” summary with actionable guidance.
- [x] Add an option to upload higher-quality scans if coverage is low.

## Milestone 6: Prompt hardening and quality improvements
- [x] Fix OCR confidence parsing to accept float-string values from Tesseract.
- [x] Add anti-injection guidance to visual analysis prompts (captions are untrusted input).
- [x] Redact injection phrases before visual analysis so captions can't steer vision outputs.
- [x] Deduplicate digest citation guidance in examiner prompts to reduce token overhead.
- [x] Move the "do not fabricate labels" notice out of IA text and into trusted prompt/coverage text.
- [x] Include PDF password (or a derived flag) in the document cache key to avoid stale extractions.
- [x] Clarify trusted vs untrusted input blocks in prompts to reduce ambiguity.
- [x] Tighten output schemas to reduce format drift under long contexts.

## Milestone 7: Next update (code + prompt QA follow-ups)
- [x] Add a visual-analysis output sanitizer to collapse multi-line responses into the required five-line format and flag non-compliant outputs for reviewers.
- [x] Add a coverage-quality warning when OCR text is present but confidence is missing/empty, so reviewers know OCR quality is unknown.
- [x] Cache and reuse the computed coverage warnings to avoid double recomputation in the UI and keep warning text consistent.
- [x] Add a prompts QA pass that checks for internal contradictions (e.g., “visual analysis untrusted” vs. “required inventory”) and resolves them with explicit guidance on what can be cited as evidence.
- [x] Require the examiner/moderator prompts to separate “IA evidence” from “visual analysis hints” so citations always come from IA text or coverage report, never from vision-only output.

## Milestone 8: Visual reliability upgrades (planned)
- [x] Render vector graphics to images for vision analysis so charts/diagrams in vector-only PDFs are not skipped.
- [x] Add a visual prioritization strategy (e.g., caption-matched visuals first) and allow configurable `max_visuals` to reduce missed figures.
- [x] Add a visual-to-text confirmation step: require any visual-analysis hint to be cross-checked against IA text/captions before it can influence marking.

## Completed highlights (summary)
- Extraction coverage diagnostics with OCR confidence warnings and UI surface.
- Visual extraction (raster + vector), caption linking, and vision-model summaries.
- Digesting workflow with chunk-aware citation guidance and prompt QA checks.
- Prompt safeguards against prompt injection and evidence fabrication.
- Tests covering mixed-content PDFs, digest citation warnings, and prompt QA insertion.

## Follow-up tasks from review (codebase + prompt QA)
- [x] Fix `report_has_expected_citations` to accept `--- Page N ---` style markers even when a digest is used, since digest outputs can preserve page markers and currently trigger false warnings.
- [x] When chunking oversized pages in `chunk_pages`, re-inject the page header (`--- Page N ---`) for every sub-chunk so digest summaries always include page identifiers.
- [x] Add a limit + sampling strategy for visual analysis (e.g., `max_visuals`, sample uncaptioned visuals) to avoid oversized vision calls on large PDFs while still capturing key evidence.
- [x] Tighten prompt instructions to reduce redundancy across examiner prompts and explicitly define the minimal citation format (e.g., `Page N` vs `Pages N-M`) to improve model compliance.
- [x] Add tests that cover digest citation warnings, oversized single-page chunking behavior, and prompt QA block insertion to catch regressions.

## Follow-up tasks from review (bugs + improvements)
- [ ] Fix image-count diagnostics to use the extracted image list length (the `page.images` property can be non-sized, causing `image_count=0` even when images exist).
- [ ] Add a regression test that ensures image-count diagnostics match extracted visuals for image-only PDFs.
- [ ] Capture figure/table labels that include suffixes (e.g., "Figure 2a") so unresolved-label reporting is more accurate.
- [ ] Add optional DPI control or caching for vector rasterization to avoid repeated high-cost renders on large PDFs.
