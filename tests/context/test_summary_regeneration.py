"""Malformed summary recovery must use original evidence and shared budgets."""

import asyncio
import copy
import json

import pytest
from google.adk.sessions import Session
from google.genai import types
from test_summary import EvidenceSummarizer, history

from veadk.context.attempts import AttemptLedger, current_attempts
from veadk.context.budget import ContextBudgetError
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import ContextScope, current_scope, is_summary
from veadk.context.summary import summarize_history


class MalformedOnce(EvidenceSummarizer):
    def __init__(self, invalid="{", always=False):
        super().__init__()
        self.invalid = invalid
        self.always = always
        self.closed = 0

    async def generate_content_async(self, request, stream=False):
        try:
            async for response in super().generate_content_async(request, stream):
                if len(self.requests) == 1 or self.always:
                    response.content.parts[0].text = self.invalid
                yield response
        finally:
            self.closed += 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["{", "{}"])
@pytest.mark.parametrize("scoped", [False, True])
async def test_invalid_summary_regenerates_once_from_identical_original_input(
    invalid, scoped
):
    model = MalformedOnce(invalid)
    config = ContextCompressionConfig(context_window=256000, max_summary_calls=2)
    scope = ContextScope(
        session=Session(id="s", user_id="u", app_name="a"),
        agent_name="agent",
        branch="",
    )
    token = current_scope.set(scope if scoped else None)
    contents = history()[:2]
    original = copy.deepcopy(contents)
    try:
        result = json.loads(await summarize_history(contents, model, config))
        assert result["evidence"] == ["INV-0 = 0.25 CNY"]
        assert len(model.requests) == model.closed == 2
        assert model.requests[0].model_dump() == model.requests[1].model_dump()
        assert contents == original and scope.pending_state == {}
        assert scope.summary_calls == (2 if scoped else 0)
    finally:
        current_scope.reset(token)
    assert not is_summary.get()


@pytest.mark.asyncio
async def test_repeated_malformed_summaries_stop_after_one_regeneration():
    model = MalformedOnce(always=True)
    with pytest.raises(ContextBudgetError, match="summary_validation_failed"):
        await summarize_history(
            history()[:2],
            model,
            ContextCompressionConfig(context_window=256000, max_summary_calls=4),
        )
    assert len(model.requests) == model.closed == 2


@pytest.mark.asyncio
async def test_no_regeneration_without_spare_call_budget():
    model = MalformedOnce()
    with pytest.raises(ContextBudgetError, match="summary_validation_failed"):
        await summarize_history(
            history()[:2],
            model,
            ContextCompressionConfig(context_window=256000, max_summary_calls=1),
        )
    assert len(model.requests) == model.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("calls", [3, 4])
async def test_regeneration_reserves_remaining_chunks_and_merge(calls):
    model = MalformedOnce()
    config = ContextCompressionConfig(
        context_window=9000,
        summary_max_tokens=512,
        safety_margin=256,
        max_summary_calls=calls,
    )
    if calls == 3:
        with pytest.raises(ContextBudgetError, match="summary_validation_failed"):
            await summarize_history(history()[:10], model, config)
        assert len(model.requests) == 1
    else:
        result = json.loads(await summarize_history(history()[:10], model, config))
        assert set(result["evidence"]) == {f"INV-{i} = {i}.25 CNY" for i in range(5)}
        assert len(model.requests) == 4


@pytest.mark.asyncio
async def test_regeneration_does_not_reset_shared_summary_deadline():
    ledger = AttemptLedger(3, 100, summary_timeout=1)

    class Expired(MalformedOnce):
        async def generate_content_async(self, request, stream=False):
            async for response in super().generate_content_async(request, stream):
                ledger.started -= 2
                yield response

    model = Expired()
    token = current_attempts.set(ledger)
    try:
        with pytest.raises(ContextBudgetError, match="summary_time_budget_exhausted"):
            await summarize_history(
                history()[:2], model, ContextCompressionConfig(context_window=256000)
            )
        assert len(model.requests) == 1
    finally:
        current_attempts.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["protected_fact", "tool_call", "cancel"])
async def test_regeneration_never_retries_unsafe_or_cancelled_outputs(failure):
    class Rejected(EvidenceSummarizer):
        async def generate_content_async(self, request, stream=False):
            async for response in super().generate_content_async(request, stream):
                if failure == "cancel":
                    raise asyncio.CancelledError()
                if failure == "tool_call":
                    response.content.parts = [
                        types.Part(
                            function_call=types.FunctionCall(name="unsafe", args={})
                        )
                    ]
                yield response

    model = Rejected()
    config = ContextCompressionConfig(
        context_window=256000,
        protected_context=("missing protected value",)
        if failure == "protected_fact"
        else (),
    )
    error = asyncio.CancelledError if failure == "cancel" else ContextBudgetError
    with pytest.raises(error):
        await summarize_history(history()[:2], model, config)
    assert len(model.requests) == 1
    assert not is_summary.get()
