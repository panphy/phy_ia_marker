from eval_marking import evaluate_records, evaluate_variance


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


def _record(case_id: str, marks: tuple[int, int, int, int], **extra) -> dict:
    criteria = ("Research design", "Data analysis", "Conclusion", "Evaluation")
    record = {"case_id": case_id, "pipeline": "evidence_audit_v1", "marks": dict(zip(criteria, marks))}
    for key in ("primary_marks", "audit_marks", "human_marks"):
        if key in extra:
            extra[key] = dict(zip(criteria, extra[key]))
    record.update(extra)
    return record


def test_evaluation_reports_each_stage_and_escalations() -> None:
    cases = [
        _record(
            "a", (4, 4, 4, 3), primary_marks=(3, 4, 4, 3), audit_marks=(4, 4, 4, 3),
            human_marks=(4, 4, 4, 3), decision_mode="moderated",
            escalation_reasons=[
                "Research design: primary 3/6, audit 4/6",
                "Primary mark: 2 quoted excerpts were not found on the cited pages",
            ],
        ),
        _record(
            "b", (5, 5, 4, 4), primary_marks=(5, 5, 4, 4), audit_marks=(5, 5, 4, 4),
            human_marks=(5, 4, 4, 4), decision_mode="audited agreement", escalation_reasons=[],
        ),
        _record(
            "c", (2, 3, 3, 2), human_marks=(3, 3, 3, 2),
            decision_mode="moderated",
            escalation_reasons=[
                "Research design: primary 2/6, audit 3/6",
                "Evidence audit: 1 quoted excerpt was not found on the cited page",
            ],
        ),
    ]
    cases[2]["primary_marks"] = {"Research design": 2}  # partial marks are skipped, not fatal

    result = evaluate_records(cases)["evidence_audit_v1"]

    assert result["stages"]["primary"]["cases"] == 2
    assert result["stages"]["primary"]["criterion_mae"]["Research design"] == 0.5
    assert result["stages"]["audit"]["criterion_exact_rate"]["Research design"] == 1.0
    assert result["stages"]["final"]["total_mae"] == result["total_mae"]
    assert result["decision_modes"] == {"audited agreement": 1, "moderated": 2}
    assert result["escalation_rate"] == 0.667
    reasons = result["escalation_reasons"]
    assert reasons["Research design: primary #/6, audit #/6"] == {"count": 2, "rate": 0.667}
    quote_reasons = [key for key in reasons if "quoted" in key]
    assert len(quote_reasons) == 2  # primary and audit are separate categories
    assert all("excerpt(s) was/were" in key for key in quote_reasons)


def test_variance_reports_spread_for_repeated_cases_without_human_marks() -> None:
    records = [
        _record("a", (4, 4, 4, 3)),
        _record("a", (4, 5, 4, 3)),
        _record("a", (4, 3, 4, 3)),
        _record("b", (5, 5, 5, 5)),
        _record("b", (5, 5, 5, 5)),
        _record("c", (2, 2, 2, 2)),
    ]

    result = evaluate_variance(records)["evidence_audit_v1"]

    assert result["cases"] == 3
    assert result["repeated_cases"] == 2
    assert result["mean_runs_per_repeated_case"] == 2.5
    assert result["criterion_mean_spread"]["Data analysis"] == 1.0
    assert result["criterion_changed_rate"]["Data analysis"] == 0.5
    assert result["criterion_changed_rate"]["Research design"] == 0.0
    assert result["total_max_spread"] == 2
    assert result["any_mark_changed_rate"] == 0.5
    assert evaluate_variance([_record("x", (1, 1, 1, 1))])["evidence_audit_v1"] == {
        "cases": 1, "repeated_cases": 0,
    }
