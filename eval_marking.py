"""Compare app scoring records with human marks, without uploading student work."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from itertools import combinations

CRITERIA = ("Research design", "Data analysis", "Conclusion", "Evaluation")


def _marks(record: dict, key: str) -> dict[str, int]:
    values = record.get(key)
    if not isinstance(values, dict) or set(values) != set(CRITERIA):
        raise ValueError(f"{record.get('case_id', '?')}: {key} must contain all four criteria")
    if any(type(values[criterion]) is not int for criterion in CRITERIA):
        raise ValueError(f"{record.get('case_id', '?')}: {key} marks must be integers")
    marks = {criterion: values[criterion] for criterion in CRITERIA}
    if any(mark < 0 or mark > 6 for mark in marks.values()):
        raise ValueError(f"{record.get('case_id', '?')}: {key} marks must be from 0 to 6")
    return marks


def evaluate_records(records: list[dict]) -> dict[str, dict]:
    """Calculate criterion and total errors for each pipeline in a human-labelled set."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("pipeline", "unspecified"))].append(record)

    results = {}
    for pipeline, cases in sorted(grouped.items()):
        criterion_errors = {criterion: [] for criterion in CRITERIA}
        total_errors = []
        signed_errors = {criterion: [] for criterion in CRITERIA}
        signed_totals = []
        review_required = []
        for case in cases:
            predicted = _marks(case, "marks")
            human = _marks(case, "human_marks")
            for criterion in CRITERIA:
                criterion_errors[criterion].append(abs(predicted[criterion] - human[criterion]))
                signed_errors[criterion].append(predicted[criterion] - human[criterion])
            total_errors.append(abs(sum(predicted.values()) - sum(human.values())))
            signed_totals.append(sum(predicted.values()) - sum(human.values()))
            if "human_review_required" in case:
                review_required.append(
                    (bool(case["human_review_required"]), bool(case.get("review_recommended", False)))
                )
        required_count = sum(required for required, _ in review_required)
        results[pipeline] = {
            "cases": len(cases),
            "criterion_mae": {
                criterion: round(sum(errors) / len(errors), 3)
                for criterion, errors in criterion_errors.items()
            },
            "criterion_exact_rate": {
                criterion: round(sum(error == 0 for error in errors) / len(errors), 3)
                for criterion, errors in criterion_errors.items()
            },
            "criterion_within_one_rate": {
                criterion: round(sum(error <= 1 for error in errors) / len(errors), 3)
                for criterion, errors in criterion_errors.items()
            },
            "total_mae": round(sum(total_errors) / len(total_errors), 3),
            "criterion_signed_bias": {c: round(sum(v) / len(v), 3) for c, v in signed_errors.items()},
            "total_signed_bias": round(sum(signed_totals) / len(signed_totals), 3),
            "stage_comparison": stage_comparison(cases),
            "repeat_stability": repeat_stability(cases),
            "annotation_quality": annotation_quality(cases),
            "human_review_recall": (
                round(sum(required and flagged for required, flagged in review_required) / required_count, 3)
                if required_count else None
            ),
            "mean_api_seconds": round(
                sum(float(case.get("api_seconds", 0)) for case in cases) / len(cases), 2
            ),
            "mean_input_tokens": round(
                sum(int(case.get("api_input_tokens", 0)) for case in cases) / len(cases)
            ),
            "mean_output_tokens": round(
                sum(int(case.get("api_output_tokens", 0)) for case in cases) / len(cases)
            ),
        }
    return results


def stage_comparison(cases: list[dict]) -> dict:
    """Paired criterion error: total-mark cancellation must not count as improvement."""
    result = {}
    for field in ("audit_marks", "marks"):
        deltas = []
        for case in cases:
            if "primary_marks" not in case or field not in case:
                continue
            primary, stage, human = (_marks(case, k) for k in ("primary_marks", field, "human_marks"))
            before = sum(abs(primary[c] - human[c]) for c in CRITERIA) / 4
            after = sum(abs(stage[c] - human[c]) for c in CRITERIA) / 4
            deltas.append(after - before)
        result[field] = {
            "paired_cases": len(deltas),
            "mean_criterion_mae_change": round(sum(deltas) / len(deltas), 3) if deltas else None,
            "improved": sum(d < 0 for d in deltas),
            "worsened": sum(d > 0 for d in deltas),
            "unchanged": sum(d == 0 for d in deltas),
        }
    return result


def repeat_stability(cases: list[dict]) -> dict:
    groups = defaultdict(list)
    for case in cases:
        if case.get("case_id"):
            # Do not mix revisions/models or different investigation settings.
            groups[(case["case_id"], case.get("model"), case.get("configuration_id"))].append(case)
    repeated = [values for values in groups.values() if len(values) > 1]
    deltas = {c: [] for c in CRITERIA}
    total_ranges = []
    for group in repeated:
        marks = [_marks(case, "marks") for case in group]
        totals = [sum(m.values()) for m in marks]
        total_ranges.append(max(totals) - min(totals))
        for left, right in combinations(marks, 2):
            for c in CRITERIA:
                deltas[c].append(abs(left[c] - right[c]))
    return {
        "repeated_cases": len(repeated),
        "criterion_mean_pairwise_difference": {
            c: round(sum(values) / len(values), 3) if values else None for c, values in deltas.items()
        },
        "mean_total_range": round(sum(total_ranges) / len(total_ranges), 3) if total_ranges else None,
    }


def annotation_quality(cases: list[dict]) -> dict:
    """Optional teacher labels, never self-scored by the marking model."""
    annotations = [a for case in cases for a in case.get("annotation_reviews", [])]
    result = {"reviewed_annotations": len(annotations)}
    for field in ("citation_correct", "supported", "actionable"):
        values = [a[field] for a in annotations if field in a]
        if any(type(v) is not bool for v in values):
            raise ValueError(f"Annotation review {field} must be Boolean.")
        result[field + "_count"] = len(values)
        result[field + "_rate"] = round(sum(values) / len(values), 3) if values else None
    missed = [case["missed_strengths_count"] for case in cases if "missed_strengths_count" in case]
    if any(type(v) is not int or v < 0 for v in missed):
        raise ValueError("missed_strengths_count must be a nonnegative integer.")
    result["cases_reviewed_for_missed_strengths"] = len(missed)
    result["mean_missed_strengths"] = round(sum(missed) / len(missed), 3) if missed else None
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare IA scoring records with qualified human marks."
    )
    parser.add_argument("records", type=Path, help="JSONL file with one labelled scoring record per line")
    args = parser.parse_args()
    records = [
        json.loads(line) for line in args.records.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        parser.error("The records file is empty.")
    print(json.dumps(evaluate_records(records), indent=2))


if __name__ == "__main__":
    main()
