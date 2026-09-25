# Repository guide

This Streamlit app reviews IB DP Physics IAs against the four criteria in `criteria/ib_phy_ia_criteria.md` (24 marks total). `README.md` covers setup and user-facing behavior. `todo.md` lists open follow-up work, with a recommended order.

## Where to work

- `app.py`: UI, theme CSS, session state, assessment flow, OpenAI calls, and report downloads.
- `app_utils.py`: page evidence, prompt helpers, report validation and parsing, moderation routing, quote checks, and score exports.
- `pdf_utils.py`: PDF text, OCR, encryption detection, and source-image extraction.
- `prompts/`: primary marker, evidence auditor, and Chief Moderator instructions.
- `eval_marking.py`: offline comparison with human marks.
- `.streamlit/config.toml`: theme colours and toolbar settings.
- `tests/`: regression tests.
- `todo.md`: the single list of open work. Start there.

## Assessment flow

1. Extract page-linked text and selected source visuals, using OCR when needed. Large IAs may be summarised into a digest that keeps page references.
2. The primary marker applies the rubric. The evidence auditor checks its claims, citations and marks against the IA.
3. Deterministic checks run on every report (`app_utils.py`):
   - each criterion has a mark and a page citation;
   - cited pages exist in the PDF;
   - any stated total equals the sum of the criterion marks;
   - the audit's heading mark (`— audited X/6`) matches its `Audited mark recommendation` and its copy of the primary mark;
   - quoted excerpts appear in the extracted text of the cited page.
4. Exact agreement with no escalation reason produces an audited decision, which keeps any auditor note on overstated claims. Any of the following triggers Chief Moderator adjudication:
   - a mark disagreement or audit concern;
   - an evidence or coverage gap;
   - an unverified quote;
   - a summarised IA;
   - a suspected injection.

   Never average marks.
5. The Chief Moderator's `Human review recommended` verdict, missing verdicts, suspected injection, and unverified quotes in the final decision make the marks provisional in the UI.

The three marking stages currently use `gpt-6-sol`. Their distinct jobs matter more than different personas. Do not claim independent model agreement or improved accuracy without evaluation against qualified human marks. Do not change how the models mark (see Phase 2 in `todo.md`) until the evaluation set exists.

## Invariants

- Keep the rubric and app instructions separate from untrusted student content, extracted text, visual summaries, and model reports. Preserve prompt-injection defenses.
- Treat original IA pages and supplied PDF visuals as evidence. Coverage diagnostics and optional vision summaries are aids, not independent proof. Flag unreadable or missing evidence rather than guessing.
- Cite PDF pages for material marking claims. When you change prompts or output formats, keep report validation, page-range checks, the parsers (`extract_report_scores`, `report_stated_totals`, `audit_mark_issues`, `HUMAN_REVIEW_PATTERN`) and the "verbatim text only inside quotation marks" rule in step with them.
- Missing or ambiguous model verdicts must fail safe: escalate, or require review.
- Keep `STORE_RESPONSES = False` unless the user explicitly changes the privacy policy. Never commit API keys, passwords, student PDFs, reports containing student text, or human-mark files.
- Respect Streamlit session-state dependencies: rerunning an earlier stage must invalidate later reports.
- Bump the `pipeline` value in `build_evaluation_record` whenever the marking flow changes, so evaluation results stay comparable.

## UI notes

- Palette colours are defined twice and must match: `.streamlit/config.toml` and the CSS tokens on `:root` at the top of the UI section in `app.py`. The theme is locked to `base = "light"` because the CSS assumes it.
- Custom CSS targets bordered containers through their `key=` classes (`.st-key-upload_card` etc.) and a few Streamlit `data-testid` values. Streamlit updates can rename test IDs, so smoke-check the UI after upgrading.
- The header logo links to `PANPHY_URL` (https://panphy.app).

## Before committing

- Read the relevant implementation and prompt before editing. Keep template placeholders aligned with their `.format(...)` calls.
- Run `pytest tests/` after code or prompt changes. For UI changes, also run a Streamlit smoke check when possible.
- Update `README.md` when user-facing behavior, setup, or the assessment flow changes. Tick or add items in `todo.md` when follow-up work is done or discovered.
