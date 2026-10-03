# Marking and annotation calibration

The automated tests verify app behavior with synthetic inputs. They do not establish agreement with IB examiners.

## Human reference set

Use consented/de-identified IAs across all mark bands and experimental, simulation and secondary-data investigations. Include clear PDFs, scans, dense tables, transformed graphs and long documents. Keep a held-out set that is not used to tune prompts.

Ask two qualified teachers to mark each IA independently and blind to app marks, then adjudicate disagreements. Record four criterion marks and whether source problems genuinely require human review. Do not silently turn a range of human judgments into an exact ground truth; record adjudication notes outside the student-free scoring export.

## Paired comparisons

Export scoring records from the same IAs for each pipeline/configuration. Add `human_marks` and, where assessed, Boolean `human_review_required`. Run:

```sh
python eval_marking.py records.jsonl
```

Review criterion and total error, signed bias, within-one rates and human-review recall. The stage comparison uses mean absolute criterion error, so overmarking one criterion cannot cancel undermarking another. Examine both improved and worsened cases after auditing and moderation.

Repeat each case several times with unchanged model/settings/prompts. Repeated-case statistics group by case ID, model and configuration ID. Distinguish between-case accuracy from within-case stability. Compare investigation types and PDF-quality groups separately using labelled subsets; do not interpret a small pooled average as evidence of reliability for every group.

## Concise annotation review

For each final comment, a teacher can add an item to `annotation_reviews`:

```json
{"citation_correct": true, "supported": true, "actionable": true}
```

- `citation_correct`: the cited passage/visual exists and the location is correct.
- `supported`: the observation and criterion consequence follow from that evidence.
- `actionable`: the suggested change is specific, feasible and relevant. Omit for credit-only comments.

Record `missed_strengths_count` for materially important strengths omitted from feedback. Do not count every unmentioned detail. Also inspect whether advice is being misrepresented as a mark requirement and whether comments fit the 40-word cap without becoming cryptic.

Review false criticisms and missed source gaps before deciding whether a change improves marking. Keep benchmark reports and student work outside the repository. Do not claim improved accuracy until these comparisons have been completed.
