"""Compare app scoring records with human marks, without uploading student work."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

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
        review_required = []
        for case in cases:
            predicted = _marks(case, "marks")
            human = _marks(case, "human_marks")
            for criterion in CRITERIA:
                criterion_errors[criterion].append(abs(predicted[criterion] - human[criterion]))
            total_errors.append(abs(sum(predicted.values()) - sum(human.values())))
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
