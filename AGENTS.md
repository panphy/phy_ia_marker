# Repository guide

This Streamlit app reviews IB DP Physics IAs against the four criteria in `criteria/ib_phy_ia_criteria.md` (24 marks total). `README.md` covers setup and user-facing behavior.

## Where to work

- `app.py`: UI, session state, assessment flow, OpenAI calls, and report downloads.
- `app_utils.py`: page evidence, prompt helpers, report validation, and score exports.
- `pdf_utils.py`: PDF text, OCR, and source-image extraction.
- `prompts/`: primary marker, evidence auditor, and Chief Moderator instructions.
- `eval_marking.py`: offline comparison with human marks.
- `tests/`: regression tests. `todo.md` tracks follow-ups from the latest review (start there); `tasks.md` holds the older extraction roadmap.

## Assessment flow

1. Extract page-linked text and selected source visuals; use OCR when needed. Large IAs may be digested with page references preserved.
2. The primary marker applies the rubric. The evidence auditor checks its claims, citations, and marks against the IA.
3. Exact agreement without evidence warnings produces an audited decision. Disagreement or an evidence gap triggers Chief Moderator adjudication. Never average marks.

The three marking stages currently use `gpt-6-sol`; their distinct jobs matter more than different personas. Do not claim independent model agreement or improved accuracy without evaluation against qualified human marks.

## Invariants

- Keep the rubric and app instructions separate from untrusted student content, extracted text, visual summaries, and model reports. Preserve prompt-injection defenses.
- Treat original IA pages and supplied PDF visuals as evidence. Coverage diagnostics and optional vision summaries are aids, not independent proof. Flag unreadable or missing evidence rather than guessing.
- Cite PDF pages for material marking claims. Preserve report validation and page-range checks when changing prompts or output formats.
- Keep `STORE_RESPONSES = False` unless the user explicitly changes the privacy policy. Never commit API keys, passwords, or student PDFs.
- Respect Streamlit session-state dependencies: rerunning an earlier stage must invalidate later reports.

## Before committing

- Read the relevant implementation and prompt before editing; keep template placeholders aligned with their `.format(...)` calls.
- Run `pytest tests/` after code or prompt changes. For UI changes, also run a Streamlit smoke check when possible.
- Update `README.md` when user-facing behavior, setup, or the assessment flow changes.
