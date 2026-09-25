"""Compare app scoring records with human marks, without uploading student work."""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

CRITERIA = ("Research design", "Data analysis", "Conclusion", "Evaluation")
# Scoring-record keys holding each stage's marks; "marks" is the final decision.
STAGE_KEYS = {"primary": "primary_marks", "audit": "audit_marks", "final": "marks"}


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


def _optional_marks(record: dict, key: str) -> dict[str, int] | None:
    """Stage marks that may be partial in older or failed runs; skip them rather than fail."""
    try:
        return _marks(record, key)
    except ValueError:
        return None


def _accuracy(pairs: list[tuple[dict[str, int], dict[str, int]]]) -> dict[str, object]:
    criterion_errors = {
        criterion: [abs(predicted[criterion] - human[criterion]) for predicted, human in pairs]
        for criterion in CRITERIA
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
    }


def reason_category(reason: str) -> str:
    """Group escalation reasons that differ only in their marks or counts."""
    category = re.sub(r"(?<![/\d])\d+", "#", reason)  # keeps "/6" and "/24" denominators
    return re.sub(r"excerpts? (was|were)", "excerpt(s) was/were", category)


def evaluate_records(records: list[dict]) -> dict[str, dict]:
    """Calculate criterion and total errors for each pipeline in a human-labelled set."""
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
    grouped: dict[tuple[str, str], list[dict[str, int]]] = defaultdict(list)
    for record in records:
        key = (str(record.get("pipeline", "unspecified")), str(record.get("case_id", "?")))
        grouped[key].append(_marks(record, "marks"))

    by_pipeline: dict[str, list[list[dict[str, int]]]] = defaultdict(list)
    for (pipeline, _), runs in grouped.items():
        by_pipeline[pipeline].append(runs)

    results = {}
    for pipeline, cases in sorted(by_pipeline.items()):
        repeated = [runs for runs in cases if len(runs) >= 2]
        if not repeated:
            results[pipeline] = {"cases": len(cases), "repeated_cases": 0}
            continue
        spreads = {
            criterion: [max(run[criterion] for run in runs) - min(run[criterion] for run in runs) for runs in repeated]
            for criterion in CRITERIA
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
                sum(any(spreads[criterion][index] for criterion in CRITERIA) for index in range(len(repeated)))
                / len(repeated),
                3,
            ),
        }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare IA scoring records with qualified human marks."
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
