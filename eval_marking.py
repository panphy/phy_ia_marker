"""Compare app scoring records with human marks, without uploading student work."""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from itertools import combinations

from app_utils import ASSESSMENT_TYPES, IA

# Scoring-record keys holding each stage's marks; "marks" is the final decision.
STAGE_KEYS = {"primary": "primary_marks", "audit": "audit_marks", "final": "marks"}


def _marks(record: dict, key: str) -> dict[str, int]:
    case = record.get("case_id", "?")
    assessment = ASSESSMENT_TYPES.get(str(record.get("assessment", IA.key)))
    if assessment is None:
        raise ValueError(f"{case}: unknown assessment {record.get('assessment')!r}")
    values = record.get(key)
    if not isinstance(values, dict) or set(values) != set(assessment.names):
        raise ValueError(f"{case}: {key} must contain all {assessment.short_name} criteria")
    if any(type(values[criterion]) is not int for criterion in assessment.names):
        raise ValueError(f"{case}: {key} marks must be integers")
    marks = {criterion: values[criterion] for criterion in assessment.names}
    for criterion, maximum in assessment.criteria:
        if not 0 <= marks[criterion] <= maximum:
            raise ValueError(f"{case}: {key} {criterion} mark must be from 0 to {maximum}")
    return marks


def _optional_marks(record: dict, key: str) -> dict[str, int] | None:
    """Stage marks that may be partial in older or failed runs; skip them rather than fail."""
    try:
        return _marks(record, key)
    except ValueError:
        return None


def _accuracy(pairs: list[tuple[dict[str, int], dict[str, int]]]) -> dict[str, object]:
    criterion_errors = {
        criterion: [abs(predicted[criterion] - human[criterion]) for predicted, human in pairs]
        for criterion in pairs[0][1]
    }
    total_errors = [abs(sum(predicted.values()) - sum(human.values())) for predicted, human in pairs]
    return {
        "cases": len(pairs),
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
        "criterion_signed_bias": {c: round(sum(p[c] - h[c] for p, h in pairs) / len(pairs), 3)
                                  for c in criterion_errors},
        "total_signed_bias": round(sum(sum(p.values()) - sum(h.values()) for p, h in pairs) / len(pairs), 3),
    }


def reason_category(reason: str) -> str:
    """Group escalation reasons that differ only in their marks or counts."""
    category = re.sub(r"(?<![/\d])\d+", "#", reason)  # keeps "/6", "/24" and other denominators
    return re.sub(r"excerpts? (was|were)", "excerpt(s) was/were", category)


def evaluate_records(records: list[dict]) -> dict[str, dict]:
    """Calculate criterion and total errors for each pipeline in a human-labelled set.

    IA and EE records use different pipeline labels, so each group has one set of criteria.
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("pipeline", "unspecified"))].append(record)

    results = {}
    for pipeline, cases in sorted(grouped.items()):
        final_pairs = [(_marks(case, "marks"), _marks(case, "human_marks")) for case in cases]
        review_required = [
            (bool(case["human_review_required"]), bool(case.get("review_recommended", False)))
            for case in cases
            if "human_review_required" in case
        ]
        required_count = sum(required for required, _ in review_required)

        stages = {}
        for stage, key in STAGE_KEYS.items():
            pairs = [
                (stage_marks, human)
                for case, (_, human) in zip(cases, final_pairs)
                if (stage_marks := _optional_marks(case, key)) is not None
            ]
            if pairs:
                stages[stage] = _accuracy(pairs)

        reason_counts = Counter(
            reason_category(str(reason))
            for case in cases
            for reason in case.get("escalation_reasons") or []
        )
        decision_modes = Counter(str(case.get("decision_mode") or "unknown") for case in cases)

        results[pipeline] = {
            **_accuracy(final_pairs),
            "stages": stages,
            "stage_comparison": stage_comparison(cases),
            "repeat_stability": repeat_stability(cases),
            "annotation_quality": annotation_quality(cases),
            "decision_modes": dict(sorted(decision_modes.items())),
            "escalation_rate": round(
                sum(bool(case.get("escalation_reasons")) for case in cases) / len(cases), 3
            ),
            "escalation_reasons": {
                reason: {"count": count, "rate": round(count / len(cases), 3)}
                for reason, count in reason_counts.most_common()
            },
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


def evaluate_variance(records: list[dict]) -> dict[str, dict]:
    """Measure how much final marks change across repeated runs of the same case.

    Needs no human marks. Cases with a single run are counted but not scored.
    """
    grouped: dict[tuple[str, str, str, str], list[dict[str, int]]] = defaultdict(list)
    for record in records:
        key = (str(record.get("pipeline", "unspecified")), str(record.get("case_id", "?")),
               str(record.get("model", "")), str(record.get("configuration_id", "")))
        grouped[key].append(_marks(record, "marks"))

    by_pipeline: dict[str, list[list[dict[str, int]]]] = defaultdict(list)
    for (pipeline, _, _, _), runs in grouped.items():
        by_pipeline[pipeline].append(runs)

    results = {}
    for pipeline, cases in sorted(by_pipeline.items()):
        repeated = [runs for runs in cases if len(runs) >= 2]
        if not repeated:
            results[pipeline] = {"cases": len(cases), "repeated_cases": 0}
            continue
        criteria = list(repeated[0][0])
        spreads = {
            criterion: [max(run[criterion] for run in runs) - min(run[criterion] for run in runs) for runs in repeated]
            for criterion in criteria
        }
        total_spreads = [
            max(sum(run.values()) for run in runs) - min(sum(run.values()) for run in runs)
            for runs in repeated
        ]
        results[pipeline] = {
            "cases": len(cases),
            "repeated_cases": len(repeated),
            "mean_runs_per_repeated_case": round(sum(len(runs) for runs in repeated) / len(repeated), 2),
            "criterion_mean_spread": {
                criterion: round(sum(values) / len(values), 3) for criterion, values in spreads.items()
            },
            "criterion_changed_rate": {
                criterion: round(sum(value > 0 for value in values) / len(values), 3)
                for criterion, values in spreads.items()
            },
            "total_mean_spread": round(sum(total_spreads) / len(total_spreads), 3),
            "total_max_spread": max(total_spreads),
            "any_mark_changed_rate": round(
                sum(any(spreads[criterion][index] for criterion in criteria) for index in range(len(repeated)))
                / len(repeated),
                3,
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
            primary, stage = (_optional_marks(case, k) for k in ("primary_marks", field))
            if primary is None or stage is None:
                continue
            human = _marks(case, "human_marks")
            before = sum(abs(primary[c] - human[c]) for c in human) / len(human)
            after = sum(abs(stage[c] - human[c]) for c in human) / len(human)
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
    criteria = _marks(cases[0], "marks")
    deltas = {c: [] for c in criteria}
    total_ranges = []
    for group in repeated:
        marks = [_marks(case, "marks") for case in group]
        totals = [sum(m.values()) for m in marks]
        total_ranges.append(max(totals) - min(totals))
        for left, right in combinations(marks, 2):
            for c in criteria:
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
        description="Compare IA or EE scoring records with qualified human marks."
    )
    parser.add_argument("records", type=Path, help="JSONL file with one scoring record per line")
    parser.add_argument(
        "--variance",
        action="store_true",
        help="Report run-to-run mark spread for repeated case_ids instead (no human marks needed).",
    )
    args = parser.parse_args()
    records = [
        json.loads(line) for line in args.records.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        parser.error("The records file is empty.")
    report = evaluate_variance(records) if args.variance else evaluate_records(records)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
