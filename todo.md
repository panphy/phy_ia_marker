# To-do for AI agents

The single list of open work for this repository. Read `AGENTS.md` first: its invariants (trust
boundaries, page citations, `STORE_RESPONSES = False`, no averaging, invalidating later stages) apply to
every task here.

## How to work through this list

- **Phase 1 blocks Phase 2.** Do not change how the models mark (prompts, stage structure, rubric
  guidance) until you can measure the effect against qualified human marks.
- **Engineering** tasks don't affect marks and can be done at any time.
- One task per branch or PR. Keep prompt placeholders aligned with their `.format(...)` calls.
- Run `pytest tests/` after every change. For UI changes, also do a Streamlit smoke check.
- Update `README.md` when user-facing behavior or the assessment flow changes.
- When you finish a task, tick it, record the result (the metric change or a link to the PR), and move it
  to **Done**.
- Never commit student PDFs, reports containing student text, human-mark files or API keys. Evaluation
  data stays outside the repository.

---

## Phase 1 — Measure (do first)

### [ ] 1. Build a human-marked evaluation set  *(blocks Phase 2)*
- **Why:** there's no evidence yet that the audit or moderation stages improve accuracy, and no way to
  test prompt changes.
- **What:** gather 20–40 IAs with qualified human or IB-moderated marks. Start with IB-published exemplars
  and moderator comments. Export a scoring record for each run (the "Download scoring record" button,
  built by `build_evaluation_record` in `app_utils.py`), add `human_marks` and `human_review_required`,
  and save as JSONL outside the repo. Use these IAs as the regression set for every marking change.
- **Files:** `eval_marking.py`, `app_utils.py` (`build_evaluation_record`).
- **Add to the report:**
  - accuracy of the primary mark, the audit mark and the final mark, each against the human marks
    (records already hold `primary_marks` and `audit_marks`);
  - escalation rate, split by `decision_mode`;
  - how often each escalation reason fires. Group reason strings by prefix, because they contain marks.
- **Done when:** `python eval_marking.py records.jsonl` prints per-stage exact / within-one / MAE figures
  and escalation stats. Tests cover the new calculations using synthetic records only.

### [ ] 2. Measure run-to-run variance
- **Why:** each stage is sampled once. Unstable marks are a hidden risk and could become an escalation
  signal.
- **What:** add an offline script, or an `eval_marking.py` mode, that compares records from repeated runs
  of the same `case_id` and reports the spread per criterion.
- **Done when:** the spread per criterion is reported for the evaluation set. Record the baseline here.

### [ ] 3. Measure how often the quote check flags genuine quotes
- **Why:** `unverified_quotes` in `app_utils.py` compares quotes with extracted page text. OCR noise, or
  quotes read from a graph image on a page that also has plenty of text, can make a genuine quote look
  unverified.
- **What:** on the evaluation runs, sample the flagged quotes and label each one genuine or fabricated.
  Tune `MIN_VERIFIABLE_PAGE_CHARS`, the fuzzy `threshold`, or the handling of OCR pages (the `used_ocr`
  diagnostics) if genuine quotes are flagged too often.
- **Done when:** the share of flags that were genuine quotes is recorded here, and any threshold change
  has a regression test.

### [ ] 4. Real end-to-end check of the UI and safeguards
- **Why:** the September 2026 UI and safeguard changes were checked with unit tests and simulated
  session state only, never a real marking run.
- **What:** with an API key and a non-sensitive test IA, run a full assessment and check:
  - the progress step shows "In progress" while running;
  - the results banner states;
  - the audit heading format (`— audited X/6`) is followed;
  - the total check doesn't cause frequent reruns;
  - encrypted-PDF upload works.

  Also check whether the Streamlit settings menu still offers dark mode. The CSS assumes the light theme
  set by `base = "light"` in `.streamlit/config.toml`.
- **Done when:** issues found are fixed or listed here.

---

## Phase 2 — Improve marking (only with Phase 1 metrics)

For each task: run the evaluation set before and after. Keep the change only if final-mark accuracy holds
or improves, and escalation stays reasonable. Record both results here, and bump the `pipeline` value in
`build_evaluation_record` (currently `evidence_audit_v1`) so results stay comparable.

### [ ] 5. Blind audit pass
- **Why:** the auditor reads the primary marks first and tends to anchor on them, so "exact agreement"
  is weak evidence.
- **What:** add a blind marking call that marks from the IA without the primary report. Run it at the
  same time as the primary mark. Escalate when blind marks differ from the primary. Keep the existing
  evidence check. Never average marks. Invalidate the blind result whenever the primary or the document
  changes (session-state rules).
- **Files:** new prompt in `prompts/`, `app.py` (stage runners, full-run flow, `reset_reports`),
  `app_utils.py` (`moderation_reasons`), tests.

### [ ] 6. Make the primary marker neutral
- **Why:** `prompts/examiner1_prompt.md` still frames the only full marker as "the Experimentalist", with
  extra attention on method and evaluation. `AGENTS.md` says the stages' jobs matter more than personas.
- **What:** remove the lens, or balance it with equal attention to data analysis and the conclusion.
  Rename "Primary mark — Experimentalist" in `build_combined_report` and the "Examiner 1 decision"
  heading. Update `test_primary_and_auditor_prompts_have_distinct_jobs`.

### [ ] 7. Also check against the band below
- **Why:** the prompts ask only "why not higher", which may bias marks downward.
- **What:** add a matching "why not lower" check to the primary and moderator prompts. Keep the output
  parseable by `extract_report_scores` and `report_has_expected_citations`.

### [ ] 8. Reduce moderator bias toward one report
- **Why:** the moderator always sees the primary report then the audit, labelled by role.
- **What:** try limiting adjudication to the disputed criteria, and neutral labels ("Report A/B") in a
  randomized order. Make sure the final table still maps back to primary/audit columns for
  `extract_report_scores`.

### [ ] 9. Add uncertainty-handling guidance
- **Why:** the rubric defers uncertainty expectations to the Physics Teacher Support Material, which the
  models never see. Data analysis marks hinge on it.
- **What:** add a short paraphrased section to `criteria/ib_phy_ia_criteria.md`, clearly labelled as app
  guidance rather than rubric text. It should cover propagation, uncertainties of transformed variables,
  error bars and gradient uncertainty, and comparing results with accepted values within uncertainty.
  Do not copy the IB text verbatim.

### [ ] 10. Common-pitfall checklist
- **Why:** markers can miss frequent student errors that bear on specific criteria.
- **What:** add a short checklist to the primary prompt, framed as things to check, not automatic
  deductions:
  - Research design: aim confused with research question; control variables missing.
  - Data analysis: inconsistent significant figures; no uncertainty on processed data.
  - Conclusion: precision claimed beyond what the uncertainties support.
  - Evaluation: generic improvements not linked to specific weaknesses.

  It must not add requirements the rubric doesn't state.

### [ ] 11. Mark from the full text rather than the summary
- **Why:** when an IA is summarised (`maybe_digest`, over `MAX_RAW_CHARS_BEFORE_DIGEST`), the marker and
  auditor both see a summary written with low reasoning effort, and the auditor can't catch summary
  errors. Such cases now always escalate, but the Chief Moderator also only sees the summary.
- **What:** give the models the full page text when it fits in context, and use the summary only for
  finding things. Alternatively, raise the threshold to reflect current context limits.

### [ ] 12. Word-count diagnostic
- **What:** first confirm the current Physics guide's word-limit policy, including whether text beyond
  the limit is assessed. Then add a word-count line to the coverage report and a warning if the IA is
  over the limit. Don't invent a penalty the guide doesn't state.

---

## Engineering (any time; no effect on marks)

No open items. Add new engineering tasks here.

---

## Done

Details are in git history and the merged PRs.

- **PDF extraction and visuals:**
  - per-page diagnostics, OCR confidence and coverage warnings;
  - embedded-image and vector-graphic extraction, with caption linking and label suffixes ("Figure 2a");
  - optional vision summaries with a strict output sanitizer;
  - source visuals supplied directly to marking calls;
  - image-count fix;
  - PDF password included in the document cache key;
  - rendering through PDFium, with no Poppler dependency.
- **Prompt and rubric safeguards:**
  - trusted and untrusted input blocks;
  - prompt-injection screening with teacher review;
  - within-band calibration and next-band counter-checks;
  - physics-specific processing checks;
  - no invented universal thresholds;
  - holistic best-fit marking;
  - moderator escalation rules;
  - digest citation handling.
- **Marking flow:** the primary marker, evidence auditor and Chief Moderator replaced the two-persona
  design. Marks are never averaged.
- **Deterministic report checks (Sept 2026):**
  - audit heading, recommendation and quoted primary mark must agree;
  - the moderator's human-review verdict is surfaced in the UI;
  - stated totals must match the criterion marks;
  - quotes are checked against the cited pages;
  - agreed decisions keep auditor notes;
  - summarised IAs escalate.
- **UI (Sept 2026):**
  - logo-matched palette and a compact header linking to panphy.app;
  - progress tracker with a running state;
  - simplified sidebar;
  - password prompt only for encrypted PDFs;
  - results with a prominent total and one status banner.
- **Engineering (Sept 2026):**
  - model-calling helpers moved from `app.py` to `llm_utils.py` and covered by fake-client tests;
  - `PageRenderer` opens each PDF once and renders each page once for OCR and vector rasterization;
  - narrow exception handling in `pdf_utils.py` where errors are known, with skipped PDF structures
    logged rather than silently dropped, and the unused `count_page_images` removed.
- **Dropped:** "Fix dataclass Exception inheritance". `LLMError` has an explicit `__init__`, and
  `str(PdfExtractionError("msg"))` already returns the message.
