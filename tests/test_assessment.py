import json
from types import SimpleNamespace

import pytest
from assessment import (parse_record, render_record, enforce_review, missing_visuals,
                        original_page_selection, rank_visuals)
from app_utils import report_validation_issues, report_page_issues

SOURCE = '--- Page 1 ---\nThe measured force was 2 N.'


def parse(record, images=()):
    return parse_record(json.dumps(record), SOURCE, list(images), 2)


def test_record_totals_and_render_are_single_source(assessment_record):
    assessment_record['total'] = 24
    result = parse(assessment_record)
    assert result['total'] == 16
    report = render_record(result, 'Final decision')
    assert '**Total:** 16/24' in report
    assert not report_validation_issues(report, False)
    assert not report_page_issues(report, 2)


@pytest.mark.parametrize('change, message', [
    ({'quote': 'There are no error bars.'}, 'quote not found'),
    ({'page': 3}, 'outside'),
    ({'quote': '', 'visual_id': 'p1:missing'}, 'not supplied'),
    ({'observation': 'Too long. ' * 25}, '40-word'),
    ({'kind': 'limitation', 'action': ''}, 'next action'),
])
def test_invalid_annotations_fail_closed(assessment_record, change, message):
    assessment_record['criteria'][0]['annotations'][0].update(change)
    with pytest.raises(ValueError, match=message):
        parse(assessment_record)


def test_checks_force_review_and_maximum_does_not_invent_weakness(assessment_record):
    c = assessment_record['criteria'][0]
    c['mark'] = 6
    c['annotations'][0].update(kind='check', quote='', action='Inspect the original table.')
    record = parse(assessment_record)
    assert record['review_required']
    assert record['review_reasons']
    assert c['why_not_higher'] != record['criteria'][0]['why_not_higher']
    assert record['criteria'][0]['why_not_higher'] == 'Maximum mark achieved.'
    assert 'Provisional decision' in render_record(record, 'Final decision')


def test_unresolved_gap_overrides_model_clearance(assessment_record):
    record = enforce_review(parse(assessment_record), ['Page 2 unreadable'])
    assert record['review_required']
    assert 'Page 2 unreadable' in render_record(record, 'Final decision')


def test_visual_readability_required_and_unreadable_forces_review(assessment_record):
    image = SimpleNamespace(page_number=1, name='graph')
    with pytest.raises(ValueError, match='readability check'):
        parse(assessment_record, [image])
    assessment_record['visual_checks'] = [{'visual_id': 'p1:graph', 'status': 'unreadable',
                                         'reason': 'Axis values cannot be read.'}]
    assert parse(assessment_record, [image])['review_required']


def test_one_image_does_not_cover_other_image_on_same_page():
    visuals = [SimpleNamespace(page_number=1, name=n, kind='image', captions=()) for n in ('graph', 'photo')]
    assert missing_visuals(visuals, visuals[:1]) == visuals[1:]
    full_page = SimpleNamespace(page_number=1, name='detail', covers_page=True)
    assert not missing_visuals(visuals, [full_page])


def test_data_visuals_rank_before_early_decorative_images():
    photo = SimpleNamespace(page_number=1, name='photo', kind='image', captions=('Cover photo',))
    graph = SimpleNamespace(page_number=5, name='graph', kind='image', captions=('Force graph with uncertainty',))
    assert rank_visuals([photo, graph]) == [graph, photo]


def test_digest_navigation_returns_originals_and_explicit_omissions():
    raw = SOURCE + '\n--- Page 2 ---\nA long original passage.'
    text, omitted = original_page_selection(raw, [2, 1], budget=45)
    assert 'A long original passage.' in text
    assert omitted == [1]
    with pytest.raises(ValueError):
        original_page_selection(raw, [99])
    with pytest.raises(ValueError):
        original_page_selection(raw, [{}])
