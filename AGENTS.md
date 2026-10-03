# Repository guide

A Streamlit app that marks IB DP Physics work. The user picks IA or EE first:

- **IA**: four criteria in `criteria/ib_phy_ia_criteria.md`, /24.
- **EE**: criteria A–D of the 2027 model in `criteria/ib_phy_ee_criteria.md`, /26. Criterion E, Reflection (/4), is deliberately not marked because the RPF is usually unavailable (official total /30).

Other docs: `README.md` (setup, user-facing behavior), `todo.md` (the single list of open work, in phase order; start there), `CALIBRATION.md` (protocol for comparing against human marks).

## Where to work

- `app.py`: UI, theme CSS, session state, stage runners, downloads. It runs the page on import, so keep testable logic elsewhere.
- `app_utils.py`: `AssessmentType` specs (`IA`, `EE`: criteria, maxima, rubric/prompt files, `pipeline` label, `marking_notice`), report validation and parsing, moderation routing, quote checks, score exports. Parsers default to `IA`.
- `assessment.py`: IA JSON assessment records (validation, exact quote/visual checks, annotation limits, bands/totals, Markdown rendering, original-page selection). EE still uses Markdown reports.
- `llm_utils.py`: OpenAI calls, digesting, visual analysis, `STORE_RESPONSES`, anti-injection instructions. No Streamlit; usage goes through `on_usage`.
- `pdf_utils.py`: text extraction, OCR, encryption, source images (`PageRenderer` renders each page once).
- `pdf_annotate.py`: annotated examiner and student PDFs. No Streamlit.
- `prompts/`: IA primary/audit/moderator prompts and `ee_*` equivalents (same placeholders); shared `suggestions_prompt.md`, `student_notes_prompt.md` (inserted via `{margin_notes_instructions}`) and `examiner_notes_prompt.md`. Margin notes come back as JSON under `## Margin notes` (`split_margin_notes`).
- `eval_marking.py`: offline comparison with human marks. `tests/`: regression tests. `.streamlit/config.toml`: theme.

## Assessment flow

1. Extract page-linked text and source visuals (OCR when needed). Large IAs use a digest only to navigate to original pages; omitted originals keep marks provisional. EE marks from the digest with mandatory escalation.
2. Primary marker → evidence auditor. IA stages return validated JSON records (annotations ≤40 words, ≤3 per criterion; quotes ≤20 words). Audit and moderation can fetch extra visuals and enlarged pages.
3. Deterministic checks (`app_utils.py`): every criterion has a mark and page citation; cited pages exist; stated totals equal the sum; the audit's heading mark matches its recommendation and primary-mark copy; quotes appear on the cited page.
4. Exact agreement with no escalation reason gives an audited decision. Disagreement, audit concerns, evidence/coverage gaps, unverified quotes, a summarised document or suspected injection go to the Chief Moderator. Never average marks.
5. After a final decision, a suggestions call writes student-facing suggestions (validated by `suggestions_validation_issues`). With the sidebar **Create annotated PDFs** toggle on (off by default, for cost), it also writes student margin notes; IA examiner notes reuse the final record's annotations, EE examiner notes need one more call. Failures keep the marks and can be retried. Rerunning a marking stage clears suggestions and notes.
6. Marks are shown as provisional for unresolved IA source gaps, a `Human review recommended` or missing verdict, suspected injection, or unverified quotes in the final decision.

All marking stages use `gpt-6.1-sol` (`DEFAULT_MODEL` in `app.py`; was `gpt-6-sol` before Oct 2026). Scoring records carry the model and pipeline, so compare runs by both. Don't claim improved accuracy or independent agreement without evaluation against qualified human marks, and don't change how the models mark (IA or EE) until the evaluation set exists (Phase 1 of `todo.md`).

## Invariants

- Keep rubric and app instructions separate from untrusted content (student text, extracted text, visual summaries, model reports). Preserve prompt-injection defenses.
- Original pages and PDF visuals are evidence; coverage diagnostics and vision summaries are only aids. Flag unreadable or missing evidence rather than guessing.
- Cite PDF pages for material claims. When prompts or output formats change, keep validation, page-range checks, the parsers (`extract_report_scores`, `report_stated_totals`, `audit_mark_issues`, `HUMAN_REVIEW_PATTERN`) and the "verbatim text only inside quotation marks" rule in step.
- Missing or ambiguous model verdicts fail safe: escalate or require review.
- Keep `STORE_RESPONSES = False` unless the user changes the privacy policy. Never commit API keys, student PDFs, reports with student text, or human-mark files.
- Rerunning an earlier stage must invalidate later reports. Changing IA/EE resets reports (it is part of the settings and document cache keys); never mark one with the other's rubric.
- Bump the type's `pipeline` value in `app_utils.py` whenever its marking flow changes.
- EE: `EE.criteria` holds A–D only, totals are /26, and `EE.marking_notice` appears wherever EE marks do (results, final-decision download, bundle). The EE descriptors are paraphrased until verified (`todo.md`); don't present them as verbatim.
- Suggestions and the student PDF go to students: no marks, markbands or totals (`STUDENT_NOTE_MARK_PATTERN` filters notes), page citations required, no replacement content written for the student.
- Annotated PDFs contain student work: download only, never stored, re-encrypted if the upload was encrypted. A note whose quote can't be found becomes a page note, never placed on unrelated text.

## UI notes

- Palette colours live in `.streamlit/config.toml` and the `:root` CSS tokens in `app.py`; keep them matched. The theme is locked to `base = "light"`.
- CSS targets containers by `key=` classes (`.st-key-upload_card` etc.) and some `data-testid` values, which Streamlit upgrades can rename: smoke-check the UI after upgrading.

## Before committing

- Keep prompt placeholders aligned with their `.format(...)` calls.
- Run `pytest tests/`; for UI changes, also smoke-check Streamlit when possible.
- Update `README.md` for user-facing or flow changes, and tick or add items in `todo.md`.
