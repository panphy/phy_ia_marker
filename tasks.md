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

## Follow-up tasks from review (bugs + improvements)
- [ ] Fix image-count diagnostics to use the extracted image list length (the `page.images` property can be non-sized, causing `image_count=0` even when images exist).
- [ ] Add a regression test that ensures image-count diagnostics match extracted visuals for image-only PDFs.
- [ ] Capture figure/table labels that include suffixes (e.g., "Figure 2a") so unresolved-label reporting is more accurate.
- [ ] Add optional DPI control or caching for vector rasterization to avoid repeated high-cost renders on large PDFs.
