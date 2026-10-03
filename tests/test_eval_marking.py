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


def test_bias_stage_comparison_repeat_stability_and_annotation_labels():
    names = ('Research design', 'Data analysis', 'Conclusion', 'Evaluation')
    human = dict.fromkeys(names, 4)
    first = dict(human, **{'Data analysis': 5})
    worse = dict(human, **{'Data analysis': 6})
    cases = [
        {'case_id': 'same', 'model': 'test', 'marks': first, 'human_marks': human,
         'primary_marks': worse, 'audit_marks': first,
         'annotation_reviews': [{'citation_correct': True, 'supported': False, 'actionable': True}],
         'missed_strengths_count': 2},
        {'case_id': 'same', 'model': 'test', 'marks': human, 'human_marks': human,
         'primary_marks': first, 'audit_marks': worse},
    ]
    result = evaluate_records(cases)['unspecified']
    assert result['criterion_signed_bias']['Data analysis'] == 0.5
    assert result['stage_comparison']['audit_marks']['improved'] == 1
    assert result['stage_comparison']['audit_marks']['worsened'] == 1
    assert result['repeat_stability']['criterion_mean_pairwise_difference']['Data analysis'] == 1
    assert result['annotation_quality']['supported_rate'] == 0
    assert result['annotation_quality']['mean_missed_strengths'] == 2


def test_repeat_stability_does_not_mix_configurations():
    marks = dict.fromkeys(('Research design', 'Data analysis', 'Conclusion', 'Evaluation'), 4)
    cases = [{'case_id': 'same', 'configuration_id': str(i), 'marks': marks, 'human_marks': marks}
             for i in range(2)]
    assert evaluate_records(cases)['unspecified']['repeat_stability']['repeated_cases'] == 0
