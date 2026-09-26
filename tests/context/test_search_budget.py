"""Search evidence must share the same serialized input allowance as read pages."""

import asyncio
import copy
import json

import pytest
from test_recoverable_context import mcp_source, read
from veadk.context.config import ContextCompressionConfig
from veadk.context.tool_results import compact_tool_results


def cost(value):
    return (
        len(
            json.dumps(
                json.dumps(value, ensure_ascii=False), ensure_ascii=False
            ).encode()
        )
        + 128
    )


@pytest.mark.asyncio
async def test_search_result_accounts_for_escaping_before_storage():
    text = 'Evidence record: "quoted" \x01\t value.\n' * 3000
    request, scope = mcp_source(text)
    saved = copy.deepcopy(scope.session.events)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    scope.retrieval_headroom = 4000
    value = await read(
        request, scope, next(iter(refs)), operation="search", query="Evidence record"
    )
    assert value.get("matches"), "A bounded nonempty evidence window should fit"
    assert all(m["text"] == text[m["offset"] : m["end"]] for m in value["matches"])
    assert cost(value) <= 4000, (
        "Search result must fit the complete escaped result allowance"
    )
    assert 0 <= scope.retrieval_headroom <= 4000 - cost(value)
    assert scope.session.events == saved


@pytest.mark.asyncio
async def test_parallel_search_results_share_the_remaining_input_allowance():
    text = "".join(
        f"Record {i}: invoice approval evidence remains pending.\n" for i in range(3000)
    )
    request, scope = mcp_source(text)
    saved = copy.deepcopy(scope.session.events)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    scope.retrieval_headroom = 5000
    ref = next(iter(refs))
    results = await asyncio.gather(
        *(
            read(request, scope, ref, operation="search", query=q)
            for q in (
                "invoice approval",
                "approval evidence",
                "evidence pending",
                "Record invoice",
            )
        )
    )
    admitted = [r for r in results if r.get("matches")]
    assert admitted
    assert all(
        m["text"] == text[m["offset"] : m["end"]]
        for r in admitted
        for m in r["matches"]
    )
    assert sum(cost(r) for r in admitted) <= 5000, (
        "Parallel search results must not each spend the same headroom"
    )
    assert 0 <= scope.retrieval_headroom <= 5000 - sum(cost(r) for r in admitted)
    assert any(
        r.get("error") == "context_retrieval_input_budget_exhausted" for r in results
    )
    assert scope.session.events == saved
