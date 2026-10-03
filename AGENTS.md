# Repository guide

This Streamlit app reviews IB DP Physics IAs against the four criteria in `criteria/ib_phy_ia_criteria.md` (24 marks total), and physics extended essays against criteria A–D of the 2027 EE model in `criteria/ib_phy_ee_criteria.md` (26 marks; Discussion and evaluation /8). EE criterion E, Reflection (/4), is deliberately not marked because the RPF is usually unavailable; the official total is 30. The user picks IA or EE before marking. `README.md` covers setup and user-facing behavior. `todo.md` lists open follow-up work, with a recommended order.

## Where to work

- `app.py`: UI, theme CSS, session state, assessment flow, stage runners, and report downloads. It runs the Streamlit page on import, so keep testable logic in the modules below.
- `llm_utils.py`: OpenAI calls (`call_llm`, `call_vision_llm`), digesting, visual analysis, `STORE_RESPONSES` and the anti-injection instructions. Free of Streamlit; usage is reported through an `on_usage` callback.
- `assessment.py`: validated IA assessment records, exact quote/visual checks, concise comments, original-page selection and Markdown rendering. EE retains the existing Markdown flow.
- `app_utils.py`: the `AssessmentType` specs (`IA`, `EE`: criteria and maxima, rubric and prompt files, evidence terms, pipeline label), page evidence, prompt helpers, report validation and parsing, moderation routing, quote checks, and score exports. Parsers take the assessment type and default to `IA`.
- `pdf_annotate.py`: the annotated examiner and student PDFs (ReportLab margin notes drawn as page content, quotes located with pypdfium2 text search, Markdown cover pages). Free of Streamlit.
- `pdf_utils.py`: PDF text, OCR, encryption detection, and source-image extraction. `PageRenderer` renders each page once for both OCR and rasterization; skipped PDF structures are logged, not silently dropped.
- `prompts/`: primary marker, evidence auditor, and Chief Moderator instructions for the IA, and `ee_*_prompt.md` equivalents for the EE. Both sets use the same `.format(...)` placeholders. `suggestions_prompt.md`, `student_notes_prompt.md` (appended to the suggestions prompt through `{margin_notes_instructions}`) and `examiner_notes_prompt.md` are shared by both and have their own placeholders (`work_name`, `final_report`, `criterion_headings`, `criterion_list`). Both return margin notes as JSON under `## Margin notes`, parsed by `split_margin_notes`.
- `eval_marking.py`: offline comparison with human marks.
- `.streamlit/config.toml`: theme colours and toolbar settings.
- `tests/`: regression tests.
- `todo.md`: the single list of open work. Start there.

## Assessment flow

1. Extract page-linked text and selected source visuals, using OCR when needed. Large IAs use a descriptive digest to retrieve original pages before marking; omitted originals keep marks provisional. EE retains digest-based marking with mandatory escalation.
2. The primary marker applies the rubric. The evidence auditor checks its claims, citations and marks against the IA. IA stages return validated JSON records; `assessment.py` renders their reports and computes bands/totals. Annotations are at most 40 words, three per criterion; quotes are at most 20 words. Audit/moderation can retrieve additional visuals and enlarged pages.
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
5. After any final decision, a suggestions call writes student-facing suggestions for improvement (no marks, page-cited, validated by `suggestions_validation_issues`). When the sidebar's **Create annotated PDFs** toggle is on (off by default, to control cost), the same stage also writes student margin notes; IA examiner notes reuse validated assessment annotations, while EE examiner notes use a separate call; when it is off, no notes are requested and no extra call is made. A failure there keeps the marks and can be retried. Rerunning any marking stage clears the suggestions and notes.
6. Unresolved IA source gaps are enforced independently of model verdicts and remain provisional. The Chief Moderator's `Human review recommended` verdict, missing verdicts, suspected injection, and unverified quotes in the final decision make the marks provisional in the UI.

The three marking stages currently use `gpt-6.1-sol` (changed from `gpt-6-sol` in Oct 2026; scoring records carry the model, so compare runs by model as well as pipeline). Their distinct jobs matter more than different personas. Do not claim independent model agreement or improved accuracy without evaluation against qualified human marks. Do not change how the models mark (see Phase 2 in `todo.md`) until the evaluation set exists. This applies to the EE prompts too, once the EE rubric text is verified.

## Invariants

- Keep the rubric and app instructions separate from untrusted student content, extracted text, visual summaries, and model reports. Preserve prompt-injection defenses.
- Treat original IA pages and supplied PDF visuals as evidence. Coverage diagnostics and optional vision summaries are aids, not independent proof. Flag unreadable or missing evidence rather than guessing.
- Cite PDF pages for material marking claims. When you change prompts or output formats, keep report validation, page-range checks, the parsers (`extract_report_scores`, `report_stated_totals`, `audit_mark_issues`, `HUMAN_REVIEW_PATTERN`) and the "verbatim text only inside quotation marks" rule in step with them.
- Missing or ambiguous model verdicts must fail safe: escalate, or require review.
- Keep `STORE_RESPONSES = False` unless the user explicitly changes the privacy policy. Never commit API keys, passwords, student PDFs, reports containing student text, or human-mark files.
- Respect Streamlit session-state dependencies: rerunning an earlier stage must invalidate later reports.
- Bump the assessment type's `pipeline` value (in `app_utils.py`) whenever its marking flow changes, so evaluation results stay comparable.
- Changing the IA/EE selection must reset reports (it is part of the settings key and the document cache key). Never mark EE work with the IA rubric or the reverse.
- EE Reflection is not marked (the user's decision, Oct 2026): `EE.criteria` holds A–D only, totals are /26, and `EE.marking_notice` must be shown wherever EE marks appear (results, final-decision download, bundle). The EE descriptors are paraphrased until verified (see `todo.md`); don't present them as verbatim.
- Suggestions for improvement and the student PDF go to students: they must never state marks, markbands or totals, must cite pages, and must not write replacement content for the student. Keep `STUDENT_NOTE_MARK_PATTERN` filtering student margin notes.
- Annotated PDFs contain student work: offer them only as downloads, never store them, and re-encrypt them when the upload was encrypted. A note whose quote can't be found must become a page note, never be placed on unrelated text.

## UI notes

- Palette colours are defined twice and must match: `.streamlit/config.toml` and the CSS tokens on `:root` at the top of the UI section in `app.py`. The theme is locked to `base = "light"` because the CSS assumes it.
- Custom CSS targets bordered containers through their `key=` classes (`.st-key-upload_card` etc.) and a few Streamlit `data-testid` values. Streamlit updates can rename test IDs, so smoke-check the UI after upgrading.
- The header logo links to `PANPHY_URL` (https://panphy.app).

## Before committing

- Read the relevant implementation and prompt before editing. Keep template placeholders aligned with their `.format(...)` calls.
- Run `pytest tests/` after code or prompt changes. For UI changes, also run a Streamlit smoke check when possible.
- Update `README.md` when user-facing behavior, setup, or the assessment flow changes. Tick or add items in `todo.md` when follow-up work is done or discovered.
