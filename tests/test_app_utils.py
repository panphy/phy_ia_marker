from pathlib import Path

from app_utils import (
    PROMPT_QA_MARKER,
    apply_prompt_qa,
    build_combined_report,
    chunk_pages,
    extract_report_scores,
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

    assert "Examiner 1 — the Experimentalist" in examiner1
    assert "Examiner 2 — the Data & Physics Analyst" in examiner2
    assert "Data & Physics Analyst" not in examiner1
    assert "the Experimentalist" not in examiner2
    assert "This lens must not override the rubric" in examiner1
    assert "This lens must not override the rubric" in examiner2
    assert "Do not use invented universal thresholds" in examiner1
    assert "Do not use invented universal thresholds" in examiner2


def test_moderator_prompt_adjudicates_without_averaging() -> None:
    moderator = read_prompt("moderator_prompt.md")

    assert "adjudicator, not an averager" in moderator
    assert "Do not average examiner marks" in moderator
    assert "independent provisional mark" in moderator
    assert "If both examiners agree but their evidence is unsupported, override them." in moderator
    assert "examiner marks differ by 3 or more" in moderator


def test_prompt_templates_format_with_runtime_inputs() -> None:
    common = {
        "rubric_text": "Rubric",
        "ia_text": "--- Page 1 ---\nIA",
        "coverage_report": "Coverage",
        "visual_analysis": "Visuals",
        "digest_citation_guidance": "",
    }
    assert "Rubric" in read_prompt("examiner1_prompt.md").format(**common)
    assert "Rubric" in read_prompt("examiner2_prompt.md").format(**common)
    assert "Examiner one" in read_prompt("moderator_prompt.md").format(
        **common,
        examiner1_report="Examiner one",
        examiner2_report="Examiner two",
    )


def test_extract_report_scores_reads_examiner_headings() -> None:
    report = """
### Research design — 5/6
### Data analysis — 4/6
### Conclusion — 6/6
### Evaluation — 3/6
"""
    assert extract_report_scores(report) == {
        "Research design": 5,
        "Data analysis": 4,
        "Conclusion": 6,
        "Evaluation": 3,
    }


def test_extract_report_scores_uses_final_column_in_moderator_table() -> None:
    report = """
| Criterion | Examiner 1 | Examiner 2 | Final | Maximum | Decisive evidence |
|---|---:|---:|---:|---:|---|
| Research design | 4 | 5 | 5 | 6 | Evidence |
| Data analysis | 3 | 4 | 4 | 6 | Evidence |
| Conclusion | 4 | 4 | 4 | 6 | Evidence |
| Evaluation | 2 | 3 | 3 | 6 | Evidence |
"""
    assert extract_report_scores(report) == {
        "Research design": 5,
        "Data analysis": 4,
        "Conclusion": 4,
        "Evaluation": 3,
    }


def test_build_combined_report_omits_empty_sections() -> None:
    bundle = build_combined_report("Examiner one", "", "Final decision")

    assert "Examiner 1 — Experimentalist" in bundle
    assert "Examiner 2 — Data & Physics Analyst" not in bundle
    assert "Chief Moderator — Final decision" in bundle
