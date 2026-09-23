from eval_marking import evaluate_records


def test_evaluation_reports_criterion_error_and_human_review_recall() -> None:
    cases = [
        {
            "case_id": "a",
            "pipeline": "evidence_audit_v1",
            "marks": {"Research design": 4, "Data analysis": 5, "Conclusion": 4, "Evaluation": 3},
            "human_marks": {"Research design": 4, "Data analysis": 4, "Conclusion": 4, "Evaluation": 3},
            "human_review_required": True,
            "review_recommended": True,
            "api_seconds": 12,
        },
        {
            "case_id": "b",
            "pipeline": "evidence_audit_v1",
            "marks": {"Research design": 3, "Data analysis": 4, "Conclusion": 4, "Evaluation": 3},
            "human_marks": {"Research design": 3, "Data analysis": 4, "Conclusion": 4, "Evaluation": 3},
            "human_review_required": False,
            "review_recommended": False,
            "api_seconds": 8,
        },
    ]

    result = evaluate_records(cases)["evidence_audit_v1"]

    assert result["cases"] == 2
    assert result["criterion_mae"]["Data analysis"] == 0.5
    assert result["total_mae"] == 0.5
    assert result["human_review_recall"] == 1.0
    assert result["mean_api_seconds"] == 10.0
