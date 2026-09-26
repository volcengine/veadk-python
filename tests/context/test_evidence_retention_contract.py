"""Regressions for loss of retrieved evidence and model argument variations."""

import copy
from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.genai import types
from test_evidence_quality import fixture

from veadk.context.config import ContextCompressionConfig
from veadk.context.evidence import evidence_ranges
from veadk.context.runtime import current_scope
from veadk.context.tool_results import READ_CONTEXT_TOOL, compact_tool_results


@pytest.mark.parametrize("padding", [181, 391, 607, 859])
def test_small_complete_evidence_paragraph_is_not_cut_mid_list(padding):
    fact = (
        "The aurora protocol supports "
        + ", ".join(f"language_{i}" for i in range(27))
        + "."
    )
    text = "Unrelated background sentence. " * padding + "\n\n" + fact
    text += "\n\n" + "Other irrelevant statements. " * 300
    matches = evidence_ranges(text, "Which languages does aurora support?", 1100)
    assert any(fact in m["text"] for m in matches)
    assert sum(len(m["text"].encode()) for m in matches) <= 1100
    assert all(text[m["offset"] : m["end"]] == m["text"] for m in matches)


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", ["00137", "137", 137])
async def test_canonical_decimal_offset_reads_same_unicode_range(offset):
    text = "订单档案🙂 " * 4500
    request, scope = fixture(text, "核对原始记录。")
    config = ContextCompressionConfig()
    refs = compact_tool_results(request, scope, config)
    original = copy.deepcopy(scope.session.events)
    token = current_scope.set(scope)
    try:
        result = await request.tools_dict[READ_CONTEXT_TOOL].func(
            reference=next(iter(refs)),
            offset=offset,
            tool_context=SimpleNamespace(session=scope.session, agent_name="agent"),
        )
    finally:
        current_scope.reset(token)
    assert result["offset"] == 137
    assert result["text"] == text[137 : result["end"]]
    assert scope.retrieval_calls == 1 and scope.session.events == original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "offset",
    [True, "1e2", "-1", "1.0", "9" * 10000],
    ids=["bool", "exponent", "negative", "float", "oversize"],
)
async def test_invalid_offset_cannot_bypass_reader_call_budget(offset):
    request, scope = fixture("Unique source line.\n" * 3000, "Read the source.")
    config = ContextCompressionConfig(max_retrieval_calls=2)
    refs = compact_tool_results(request, scope, config)
    token = current_scope.set(scope)
    try:
        for _ in range(2):
            result = await request.tools_dict[READ_CONTEXT_TOOL].func(
                reference=next(iter(refs)),
                offset=offset,
                tool_context=SimpleNamespace(session=scope.session, agent_name="agent"),
            )
            assert "error" in result and "text" not in result
        compact_tool_results(request, scope, config)
        names = {
            d.name
            for t in request.config.tools or []
            for d in t.function_declarations or []
        }
        assert READ_CONTEXT_TOOL not in names and scope.retrieval_calls == 2
    finally:
        current_scope.reset(token)


def test_previous_search_keeps_end_of_matched_evidence_with_exact_offsets():
    fact = "The approval code is FT-48271; currency JPY; approval remains pending."
    text = "Background. " * 5000 + "Beginning of evidence. " * 35 + fact + " End." * 20
    request, scope = fixture(text, "What is the approval code and its status?")
    config = ContextCompressionConfig()
    refs = compact_tool_results(request, scope, config)
    ref = next(iter(refs))
    start = text.index("Beginning of evidence.")
    for index in range(2):
        result = {
            "reference": ref,
            "source_sha256": refs[ref]["text_hash"],
            "matches": [{"offset": start, "end": len(text), "text": text[start:]}],
            "complete": False,
        }
        scope.session.events.append(
            Event(
                id=f"retrieval-{index}",
                author="agent",
                content=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=f"read-{index}",
                                name=READ_CONTEXT_TOOL,
                                response=result,
                            ),
                        )
                    ],
                ),
            )
        )
    original = copy.deepcopy(scope.session.events)
    request.contents = [copy.deepcopy(e.content) for e in scope.session.events]
    compact_tool_results(request, scope, config)
    earlier = request.contents[1].parts[0].function_response.response
    responses = {
        p.function_response.id: p.function_response.response
        for content in request.contents
        for p in content.parts or []
        if p.function_response
    }
    restored = []
    for match in earlier["matches"]:
        if "included_in_response" in match:
            target = responses[match["included_in_response"]]
            match = next(
                item
                for item in target["matches"]
                if item["offset"] == match["offset"] and item["end"] == match["end"]
            )
        # Resolve directly to exact text in this input, without another read.
        assert text[match["offset"] : match["end"]] == match["text"]
        restored.append(match["text"])
    assert any(fact in item for item in restored)
    assert scope.session.events == original
