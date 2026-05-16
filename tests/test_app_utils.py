from pathlib import Path

from app_utils import (
    PROMPT_QA_MARKER,
    apply_prompt_qa,
    chunk_pages,
    report_has_expected_citations,
)


PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def read_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


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


def test_examiner_prompts_keep_distinct_personas() -> None:
    examiner1 = read_prompt("examiner1_prompt.md")
    examiner2 = read_prompt("examiner2_prompt.md")

    assert "rubric literalist / evidence sufficiency examiner" in examiner1
    assert "technical-methodology examiner" in examiner2
    assert "technical-methodology examiner" not in examiner1
    assert "rubric literalist / evidence sufficiency examiner" not in examiner2
    assert "This lens must not override the rubric" in examiner1
    assert "This lens must not override the rubric" in examiner2


def test_moderator_prompt_adjudicates_without_averaging() -> None:
    moderator = read_prompt("moderator_prompt.md")

    assert "adjudicator, not an averager" in moderator
    assert "Do not average examiner marks." in moderator
    assert "Independent provisional mark" in moderator
    assert "If both examiners agree but their evidence is unsupported, override them." in moderator
