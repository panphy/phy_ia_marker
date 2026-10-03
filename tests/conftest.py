from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject
from app_utils import CRITERION_NAMES


@pytest.fixture
def assessment_record():
    """Synthetic transport fixture, not a calibrated physics marking example."""
    return {
        'review_required': False, 'review_reasons': [], 'escalation_required': False,
        'visual_checks': [],
        'criteria': [
            {'name': name, 'mark': 4, 'best_fit': 'The cited evidence supports this band.',
             'within_band': 'The evidence meets the lower mark.',
             'why_not_higher': 'The explanation is limited.', 'evidence_ids': [1],
             'annotations': [{'kind': 'credit', 'page': 1, 'quote': 'The measured force was 2 N.',
                              'visual_id': '', 'observation': 'Force is reported with units.',
                              'consequence': 'This supports clear communication.', 'action': ''}]}
            for name in CRITERION_NAMES
        ],
    }


@pytest.fixture
def source_pdf():
    writer = PdfWriter()
    for text in ('The measured force was 2 N.', 'The repeated measurement was 3 N.'):
        page = writer.add_blank_page(width=595, height=842)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                 NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = StreamObject()
        stream.set_data(f'BT /F1 16 Tf 50 740 Td ({text}) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()
