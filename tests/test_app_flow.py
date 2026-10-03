"""Offline Streamlit integration checks. No student work or API requests."""
import io
import json
from copy import deepcopy
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest


def setup_app(monkeypatch, source_pdf, records):
    import streamlit as st
    import openai
    monkeypatch.setenv('APP_PASSWORD', 'test-only')
    monkeypatch.setenv('OPENAI_API_KEY', 'not-used')
    upload = io.BytesIO(source_pdf)
    upload.name = 'synthetic.pdf'
    monkeypatch.setattr(st, 'file_uploader', lambda *args, **kwargs: upload)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        record = records(kwargs) if callable(records) else records.pop(0)
        output = record if isinstance(record, str) else json.dumps(record)
        return SimpleNamespace(output_text=output, status='completed', usage=None)

    monkeypatch.setattr(openai, 'OpenAI', lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=create)))
    app = AppTest.from_file('app.py', default_timeout=20)
    app.session_state['password_ok'] = True
    app.run()
    assert not app.exception
    return app, calls


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception


def test_complete_assessment_source_navigation_download_and_rerun(monkeypatch, source_pdf, assessment_record):
    records = [deepcopy(assessment_record) for _ in range(3)]
    app, calls = setup_app(monkeypatch, source_pdf, records)
    click(app, 'Run complete assessment')
    assert app.session_state['decision_mode'] == 'audited agreement'
    assert app.session_state['assessment_records']['final']['total'] == 16
    assert len(calls) == 2
    assert all(call['store'] is False for call in calls)
    assert app.session_state['annotation_export']
    click(app, 'View Page 1')
    assert app.session_state['annotation_page'] == 1
    click(app, 'Run primary mark')
    assert app.session_state['examiner2_report'] == ''
    assert app.session_state['moderator_report'] == ''
    assert 'final' not in app.session_state['assessment_records']


def test_human_review_verdict_stays_provisional(monkeypatch, source_pdf, assessment_record):
    flagged = deepcopy(assessment_record)
    flagged['review_required'] = True
    flagged['review_reasons'] = ['Check the uncertainty calculation on Page 1.']
    records = [deepcopy(flagged) for _ in range(3)]
    app, _ = setup_app(monkeypatch, source_pdf, records)
    click(app, 'Run complete assessment')
    assert app.session_state['decision_mode'] == 'moderated'
    assert any(metric.label == 'Provisional total' for metric in app.metric)
    assert not any('Final decision ready' in success.value for success in app.success)


def test_validation_repairs_once_before_display(monkeypatch, source_pdf, assessment_record):
    invalid = deepcopy(assessment_record)
    invalid['criteria'][0]['annotations'][0]['quote'] = 'Invented source quotation.'
    app, calls = setup_app(monkeypatch, source_pdf, [invalid, deepcopy(assessment_record), deepcopy(assessment_record)])
    click(app, 'Run complete assessment')
    assert len(calls) == 3
    assert 'Invented source quotation' not in app.session_state['moderator_report']


def test_model_cannot_clear_extraction_warning(monkeypatch, source_pdf, assessment_record):
    from dataclasses import replace
    import pdf_utils
    extract = pdf_utils.extract_pdf_text

    def low_quality(*args, **kwargs):
        text, pages, count, diagnostics, visuals = extract(*args, **kwargs)
        diagnostics[0] = replace(diagnostics[0], used_ocr=True, ocr_confidence=20)
        return text, pages, count, diagnostics, visuals

    monkeypatch.setattr(pdf_utils, 'extract_pdf_text', low_quality)
    app, _ = setup_app(monkeypatch, source_pdf, [deepcopy(assessment_record) for _ in range(3)])
    click(app, 'Run complete assessment')
    final = app.session_state['assessment_records']['final']
    assert final['review_required']
    assert any('Low OCR' in reason for reason in final['review_reasons'])
    assert any(metric.label == 'Provisional total' for metric in app.metric)


def test_digest_is_navigation_only_and_missing_originals_stay_provisional(monkeypatch, source_pdf, assessment_record):
    import pdf_utils
    extract = pdf_utils.extract_pdf_text

    def long_document(*args, **kwargs):
        _, pages, count, diagnostics, visuals = extract(*args, **kwargs)
        text = '--- Page 1 ---\nThe measured force was 2 N.\n--- Page 2 ---\n' + ('original ' * 21000)
        return text, pages, count, diagnostics, visuals

    monkeypatch.setattr(pdf_utils, 'extract_pdf_text', long_document)

    def responses(kwargs):
        if 'You compress documents' in kwargs['instructions']:
            return 'NAVIGATION_ONLY_SENTINEL. Pages 1–2 contain the investigation.'
        if 'Select source pages' in kwargs['instructions']:
            return {'pages': [1, 2]}
        assert 'NAVIGATION_ONLY_SENTINEL' not in kwargs['input']
        assert 'The measured force was 2 N.' in kwargs['input']
        return deepcopy(assessment_record)

    app, _ = setup_app(monkeypatch, source_pdf, responses)
    click(app, 'Run complete assessment')
    assert app.session_state['source_text_gaps'] == [2]
    assert app.session_state['assessment_records']['final']['review_required']
