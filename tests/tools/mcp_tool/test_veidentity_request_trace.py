"""VeIdentity request metadata carries only the active W3C context."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool
from opentelemetry import baggage, context, trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, TraceState

from veadk.integrations.ve_identity.auth_config import api_key_auth
from veadk.integrations.ve_identity.mcp_tool import VeIdentityMcpTool
import veadk.integrations.ve_identity.mcp_tool as tool_module


@pytest.fixture
def invocation(monkeypatch):
    result = object()
    session = Mock(call_tool=AsyncMock(return_value=result))
    manager = Mock(create_session=AsyncMock(return_value=session))
    headers = {"Authorization": "synthetic-private-credential"}
    monkeypatch.setattr(tool_module, "generate_headers", lambda credential: headers)
    with patch("veadk.integrations.ve_identity.auth_mixins.IdentityClient"):
        tool = VeIdentityMcpTool(
            mcp_tool=Tool(name="synthetic_tool", inputSchema={"type": "object"}),
            mcp_session_manager=manager,
            auth_config=api_key_auth("synthetic-provider", region="cn-beijing"),
        )
    return tool, manager, session, headers, result


def parent(value=1, sampled=True):
    return NonRecordingSpan(
        SpanContext(
            trace_id=value,
            span_id=value + 10,
            is_remote=False,
            trace_flags=TraceFlags(1 if sampled else 0),
            trace_state=TraceState([("vendor", "synthetic")]),
        )
    )


async def invoke(tool, args):
    return await tool._run_async_impl(
        args=args, tool_context=object(), credential=object()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("sampled", [True, False])
async def test_active_context_is_request_meta_not_auth_headers(invocation, sampled):
    tool, manager, session, headers, result = invocation
    args = {"query": "synthetic-private-input"}
    span = parent(sampled=sampled)
    with trace.use_span(span, end_on_exit=False):
        assert await invoke(tool, args) is result
        assert trace.get_current_span() is span
    manager.create_session.assert_awaited_once_with(headers=headers)
    assert manager.create_session.await_args.kwargs["headers"] is headers
    assert session.call_tool.await_args.args == ("synthetic_tool",)
    assert session.call_tool.await_args.kwargs["arguments"] is args
    meta = session.call_tool.await_args.kwargs["meta"]
    assert meta == {
        "traceparent": f"00-{1:032x}-{11:016x}-{'01' if sampled else '00'}",
        "tracestate": "vendor=synthetic",
    }
    assert headers == {"Authorization": "synthetic-private-credential"}
    assert "synthetic-private" not in repr(meta)


@pytest.mark.asyncio
async def test_no_span_keeps_original_call_shape(invocation):
    tool, _, session, _, result = invocation
    args = {}
    with trace.use_span(trace.INVALID_SPAN, end_on_exit=False):
        assert await invoke(tool, args) is result
    session.call_tool.assert_awaited_once_with("synthetic_tool", arguments=args)


@pytest.mark.asyncio
async def test_baggage_is_not_forwarded(invocation):
    tool, _, session, _, _ = invocation
    token = context.attach(baggage.set_baggage("private", "synthetic-private-baggage"))
    try:
        with trace.use_span(parent(), end_on_exit=False):
            await invoke(tool, {})
    finally:
        context.detach(token)
    meta = session.call_tool.await_args.kwargs["meta"]
    assert set(meta) == {"traceparent", "tracestate"}
    assert "synthetic-private-baggage" not in repr(meta)


@pytest.mark.asyncio
async def test_concurrent_callers_do_not_share_metadata(invocation):
    tool, _, session, _, _ = invocation

    async def run(value):
        span = parent(value)
        with trace.use_span(span, end_on_exit=False):
            await asyncio.sleep(0)
            await invoke(tool, {"number": value})
            assert trace.get_current_span() is span

    await asyncio.gather(run(3), run(4))
    observed = {
        call.kwargs["arguments"]["number"]: call.kwargs["meta"]["traceparent"]
        for call in session.call_tool.await_args_list
    }
    assert observed == {
        value: f"00-{value:032x}-{value + 10:016x}-01" for value in (3, 4)
    }


@pytest.mark.asyncio
async def test_retry_preserves_count_error_and_redacts_message(invocation, caplog):
    tool, manager, session, _, _ = invocation
    error = ValueError("synthetic-private-error-credential")
    session.call_tool.side_effect = [error, error]
    with caplog.at_level("INFO"):
        with pytest.raises(ValueError) as caught:
            with trace.use_span(parent(), end_on_exit=False):
                await invoke(tool, {})
    assert caught.value is error
    assert session.call_tool.await_count == manager.create_session.await_count == 2
    assert "synthetic-private-error-credential" not in caplog.text
    assert "ValueError" in caplog.text


@pytest.mark.asyncio
async def test_cancellation_is_not_retried(invocation):
    tool, _, session, _, _ = invocation
    error = asyncio.CancelledError()
    session.call_tool.side_effect = error
    with pytest.raises(asyncio.CancelledError) as caught:
        with trace.use_span(parent(), end_on_exit=False):
            await invoke(tool, {})
    assert caught.value is error
    assert session.call_tool.await_count == 1


@pytest.mark.asyncio
async def test_propagation_failure_keeps_one_business_call(invocation, monkeypatch):
    from veadk.tools.mcp_tool import request_trace_context as module

    def fail(self, carrier):
        raise RuntimeError("synthetic-private-propagation-error")

    monkeypatch.setattr(module.TraceContextTextMapPropagator, "inject", fail)
    tool, manager, session, _, result = invocation
    args = {}
    span = parent()
    with trace.use_span(span, end_on_exit=False):
        assert await invoke(tool, args) is result
        assert trace.get_current_span() is span
    session.call_tool.assert_awaited_once_with("synthetic_tool", arguments=args)
    assert manager.create_session.await_count == 1


@pytest.mark.asyncio
async def test_context_without_tracestate_has_only_traceparent(invocation):
    tool, _, session, _, _ = invocation
    span = NonRecordingSpan(
        SpanContext(
            trace_id=7, span_id=17, is_remote=False, trace_flags=TraceFlags.SAMPLED
        )
    )
    with trace.use_span(span, end_on_exit=False):
        await invoke(tool, {})
    assert session.call_tool.await_args.kwargs["meta"] == {
        "traceparent": f"00-{7:032x}-{17:016x}-01"
    }


@pytest.mark.asyncio
async def test_existing_retry_succeeds_without_changing_request_context(invocation):
    tool, manager, session, _, result = invocation
    session.call_tool.side_effect = [ConnectionError("synthetic-private"), result]
    with trace.use_span(parent(), end_on_exit=False):
        assert await invoke(tool, {}) is result
    assert session.call_tool.await_count == manager.create_session.await_count == 2
    assert (
        session.call_tool.await_args_list[0].kwargs["meta"]
        == session.call_tool.await_args_list[1].kwargs["meta"]
    )
