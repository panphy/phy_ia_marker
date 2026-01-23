from app_utils import (
    PROMPT_QA_MARKER,
    apply_prompt_qa,
    chunk_pages,
    report_has_expected_citations,
)


def test_report_has_expected_citations_accepts_page_markers_with_digest() -> None:
    report = "Evidence cited at --- Page 3 --- for the measurement table."
    assert report_has_expected_citations(report, used_digest=True)


def test_chunk_pages_reinserts_header_for_oversized_pages() -> None:
    raw_text = "--- Page 1 ---\n" + ("A" * 120)
    chunks = chunk_pages(raw_text, target_chars=40)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk["start_page"] == 1
        assert chunk["end_page"] == 1
        assert chunk["text"].startswith("--- Page 1 ---")


def test_apply_prompt_qa_inserts_guidance_block() -> None:
    prompt = "Visual analysis summary\n\nVisual summary + tables/graphs inventory"
    updated = apply_prompt_qa(prompt)

    assert PROMPT_QA_MARKER in updated


def test_apply_prompt_qa_skips_when_marker_present() -> None:
    prompt = f"Example\n\n{PROMPT_QA_MARKER}\nAlready applied."
    updated = apply_prompt_qa(prompt)

    assert updated == prompt
