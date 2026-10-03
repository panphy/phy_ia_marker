from types import SimpleNamespace

import pytest
from openai import APIConnectionError, RateLimitError

import llm_utils
from llm_utils import (
    LLMError,
    analyze_visuals,
    call_llm,
    call_vision_llm,
    make_structured_digest,
    maybe_digest,
    sanitize_visual_analysis_output,
    select_visuals_for_analysis,
)
from pdf_utils import ExtractedVisual


class FakeResponses:
    """Stands in for client.responses; never calls the real API."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        output = self.outputs.pop(0) if self.outputs else "ok"
        if callable(output):
            output = output(kwargs)
        if isinstance(output, Exception):
            raise output
        if isinstance(output, SimpleNamespace):
            return output
        return SimpleNamespace(
            output_text=output,
            status="completed",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )


def api_error(cls, message: str) -> Exception:
    """Build an OpenAI SDK error without depending on the SDK's HTTP transport types."""
    error = cls.__new__(cls)
    Exception.__init__(error, message)
    return error


def fake_client(*outputs):
    return SimpleNamespace(responses=FakeResponses(outputs))


def visual(page: int, name: str, captions=(), kind: str = "image", **extra) -> ExtractedVisual:
    return ExtractedVisual(
        page_number=page,
        name=name,
        data=b"img",
        image_format="png",
        width=10,
        height=10,
        captions=tuple(captions),
        kind=kind,
        **extra,
    )


def test_call_llm_returns_text_sends_store_false_and_reports_usage() -> None:
    client = fake_client("  Report text  ")
    usage = []

    output = call_llm(
        client, "model-x", "instructions", "input",
        usage_stage="primary mark",
        on_usage=lambda resp, model, stage, seconds: usage.append((model, stage, resp.usage.input_tokens)),
    )

    assert output == "Report text"
    request = client.responses.calls[0]
    assert request["store"] is False
    assert request["model"] == "model-x"
    assert request["reasoning"] == {"effort": llm_utils.MARKING_REASONING_EFFORT}
    assert usage == [("model-x", "primary mark", 10)]


@pytest.mark.parametrize(
    ("response", "error_type"),
    [
        (SimpleNamespace(output_text="partial", status="incomplete", usage=None), "incomplete_response"),
        (SimpleNamespace(output_text="   ", status="completed", usage=None), "empty_response"),
    ],
)
def test_call_llm_rejects_incomplete_and_empty_responses(response, error_type) -> None:
    with pytest.raises(LLMError) as raised:
        call_llm(fake_client(response), "model-x", "instructions", "input")
    assert raised.value.debug_info["error_type"] == error_type
    assert str(raised.value) == raised.value.user_message


def test_call_llm_maps_api_errors_to_user_messages() -> None:
    with pytest.raises(LLMError) as raised:
        call_llm(fake_client(api_error(RateLimitError, "slow down")), "model-x", "instructions", "input")
    assert raised.value.debug_info["error_type"] == "rate_limit"
    assert "rate limited" in raised.value.user_message

    with pytest.raises(LLMError) as raised:
        call_llm(fake_client(api_error(APIConnectionError, "offline")), "model-x", "instructions", "input")
    assert raised.value.debug_info["error_type"] == "connection"


def test_call_vision_llm_sends_image_with_store_false() -> None:
    client = fake_client("- Visual type: chart")
    usage = []

    output = call_vision_llm(
        client, "vision-x", "Describe", b"\x89PNG", "PNG",
        on_usage=lambda resp, model, stage, seconds: usage.append(stage),
    )

    assert output == "- Visual type: chart"
    request = client.responses.calls[0]
    assert request["store"] is False
    content = request["input"][0]["content"]
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    assert usage == ["visual analysis"]
    assert call_vision_llm(client, "vision-x", "Describe", b"", "png") == ""
    assert len(client.responses.calls) == 1


def test_call_vision_llm_maps_api_errors() -> None:
    with pytest.raises(LLMError) as raised:
        call_vision_llm(fake_client(api_error(APIConnectionError, "offline")), "v", "p", b"x", "png")
    assert raised.value.debug_info["error_type"] == "vision_error"


def test_select_visuals_prefers_captioned_and_caps_uncaptioned() -> None:
    captioned = [visual(page, f"fig{page}", captions=[f"Figure {page}"]) for page in (3, 1)]
    uncaptioned = [visual(page, f"img{page}") for page in range(1, 9)]

    selected = select_visuals_for_analysis(captioned + uncaptioned, max_visuals=5, max_uncaptioned=2)

    assert [item.name for item in selected[:2]] == ["fig1", "fig3"]
    assert len(selected) == 4
    assert all(not item.captions for item in selected[2:])
    many = [visual(page, f"fig{page}", captions=["Figure"]) for page in range(1, 20)]
    assert len(select_visuals_for_analysis(many, max_visuals=6, max_uncaptioned=2)) == 6


def test_analyze_visuals_sanitizes_output_and_skips_unrendered_vectors() -> None:
    client = fake_client("Visual type: graph\nextra line without a key")
    visuals = [
        visual(1, "graph", captions=["Figure 1"]),
        visual(2, "vector", captions=["Figure 2"], kind="vector"),
    ]

    results = analyze_visuals(client, "vision-x", visuals, max_visuals=5, max_uncaptioned=2)

    assert len(client.responses.calls) == 1
    assert results[0]["format_warning"] is True
    assert results[0]["analysis"].splitlines()[0] == "- Visual type: graph extra line without a key"
    assert results[1]["analysis"] == "Vector graphic detected but not rendered for vision analysis."


def test_sanitize_visual_analysis_output_accepts_compliant_output() -> None:
    compliant = "\n".join([
        "- Visual type: table",
        "- Summary: Raw data",
        "- Chart details: N/A",
        "- Table structure: 3 columns",
        "- Readability issues: none",
    ])
    assert sanitize_visual_analysis_output(compliant) == (compliant, False)
    missing, warning = sanitize_visual_analysis_output("")
    assert warning is True and "Missing output" in missing


def test_make_structured_digest_keeps_page_labels_and_reports_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_utils, "DIGEST_CHUNK_TARGET_CHARS", 60)
    raw_text = "\n".join(f"--- Page {page} ---\n" + "evidence " * 8 for page in range(1, 4))
    reply = lambda request: "final digest" if "consolidating" in request["input"] else "chunk summary"
    client = fake_client(*[reply] * 20)
    stages = []

    result = make_structured_digest(
        client, "model-x", "Student IA", raw_text,
        on_usage=lambda resp, model, stage, seconds: stages.append(stage),
    )

    assert result.text == "final digest"
    assert result.used_digest and result.used_chunking
    prompts = [call["input"] for call in client.responses.calls]
    assert "Source pages: Page 1" in prompts[0]
    assert "[CHUNK 1 | Page 1 SUMMARY]" in prompts[-1]
    assert all(call["store"] is False for call in client.responses.calls)
    assert all(call["reasoning"] == {"effort": llm_utils.DIGEST_REASONING_EFFORT} for call in client.responses.calls)
    assert set(stages) == {"digest"} and len(stages) == len(prompts)


def test_maybe_digest_leaves_short_text_untouched() -> None:
    client = fake_client()
    result = maybe_digest(client, "model-x", "Student IA", "--- Page 1 ---\nshort")
    assert result.text == "--- Page 1 ---\nshort"
    assert not result.used_digest
    assert client.responses.calls == []
