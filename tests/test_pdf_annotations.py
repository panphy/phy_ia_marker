import io
from pypdf import PdfReader, PdfWriter
from pdf_utils import annotate_pdf, render_pdf_page_image


def test_pdf_highlight_exact_quote_and_fallback_note(source_pdf, assessment_record):
    assessment_record['criteria'][1]['annotations'][0]['quote'] = ''
    assessment_record['criteria'][1]['annotations'][0]['visual_id'] = 'p1:graph'
    annotated, anchors = annotate_pdf(source_pdf, assessment_record)
    assert anchors[0]['anchor'] == 'text highlight'
    assert anchors[1]['anchor'] == 'page note'
    reader = PdfReader(io.BytesIO(annotated))
    assert len(reader.pages) == 2
    annotations = [a.get_object() for a in reader.pages[0]['/Annots']]
    assert annotations[0]['/Subtype'] == '/Highlight'
    assert annotations[1]['/Subtype'] == '/Text'
    assert 'Force is reported with units.' in annotations[0]['/Contents']
    assert render_pdf_page_image(annotated, 1)[0]
    assert '/Annots' not in PdfReader(io.BytesIO(source_pdf)).pages[0]


def test_annotation_export_preserves_encryption(source_pdf, assessment_record):
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(source_pdf)))
    writer.encrypt('test-password')
    buffer = io.BytesIO()
    writer.write(buffer)
    annotated, _ = annotate_pdf(buffer.getvalue(), assessment_record, 'test-password')
    reader = PdfReader(io.BytesIO(annotated))
    assert reader.is_encrypted
    assert reader.decrypt('test-password')
    assert len(reader.pages[0]['/Annots']) == 4
