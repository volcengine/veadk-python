# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Chunking, cancellation and validation without external model calls."""

import asyncio
import json
import re

import pytest
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions import Session
from google.genai import types

from veadk.context.attempts import AttemptLedger, current_attempts
from veadk.context.budget import (
    ContextBudgetError,
    count_input,
    request_payload,
    resolve_budget,
)
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import ContextScope, current_scope, is_summary
from veadk.context.summary import summarize_history


class EvidenceSummarizer:
    model = "offline-summary-model"

    def __init__(self):
        self.requests = []

    async def generate_content_async(self, request, stream=False):
        assert is_summary.get()
        assert not stream and not request.tools_dict and not request.config.tools
        self.requests.append(request)
        source = request.contents[0].parts[0].text
        result = {
            "goal": "Collect exact references",
            "active_constraints": ["Do not execute actions"],
            "decisions": [],
            "completed_work": ["Read history"],
            "pending_work": [],
            "evidence": sorted(set(re.findall(r"INV-\d+ = \d+\.\d+ CNY", source))),
            "uncertainties": [],
        }
        yield LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text=json.dumps(result))]
            )
        )


def history():
    contents = []
    for index in range(8):
        contents.extend(
            [
                types.Content(
                    role="user", parts=[types.Part(text=f"Read invoice {index}")]
                ),
                types.Content(
                    role="model",
                    parts=[
                        types.Part(text=f"INV-{index} = {index}.25 CNY. " + "x" * 1200)
                    ],
                ),
            ]
        )
    return contents


@pytest.mark.asyncio
async def test_oversized_summary_source_is_chunked_and_every_call_fits():
    model = EvidenceSummarizer()
    config = ContextCompressionConfig(
        context_window=9000, summary_max_tokens=512, safety_margin=256
    )
    result = json.loads(await summarize_history(history(), model, config))
    assert set(result["evidence"]) == {f"INV-{i} = {i}.25 CNY" for i in range(8)}
    assert 2 < len(model.requests) <= config.max_summary_calls
    budget = resolve_budget(model.model, config, config.summary_max_tokens)
    assert all(
        count_input(request_payload(r), config) <= budget.available
        for r in model.requests
    )
    assert not is_summary.get()


@pytest.mark.asyncio
async def test_small_chronological_summaries_avoid_an_unnecessary_merge_deadline():
    from google.adk.models.llm_request import LlmRequest

    from veadk.context.manager import prepare_context

    class SlowMergeSummarizer(EvidenceSummarizer):
        async def generate_content_async(self, request, stream=False):
            if "Historical partial summaries" in request.contents[0].parts[0].text:
                await asyncio.Event().wait()
            async for response in super().generate_content_async(request, stream):
                yield response

    model = SlowMergeSummarizer()
    config = ContextCompressionConfig(
        context_window=9000,
        output_reserve=512,
        summary_max_tokens=512,
        safety_margin=256,
        summary_timeout_seconds=2,
    )
    contents = history() + [
        types.Content(role="user", parts=[types.Part(text="Keep the invoice facts")]),
        types.Content(role="model", parts=[types.Part(text="Acknowledged")]),
        types.Content(role="user", parts=[types.Part(text="Return all invoice facts")]),
    ]
    original = [item.model_dump(mode="json") for item in contents]
    request = LlmRequest(model=model.model, contents=contents)
    # Exclude first catalogue loading from this call-chain deadline contract.
    resolve_budget(model.model, config)
    ledger = AttemptLedger(3, 1)
    token = current_attempts.set(ledger)
    try:
        await asyncio.wait_for(prepare_context(request, model, config, {}), timeout=2)
        assert ledger.remaining() > 0
    finally:
        current_attempts.reset(token)
    assert len(model.requests) == 2
    assert request.contents[1:] == contents[-3:]
    text = request.contents[0].parts[0].text
    result = json.loads(text.split("\n", 1)[1].rsplit("\n", 1)[0])
    evidence = [
        item
        for summary in result["chronological_summaries"]
        for item in summary["evidence"]
    ]
    assert evidence == [f"INV-{i} = {i}.25 CNY" for i in range(8)]
    assert original == [item.model_dump(mode="json") for item in contents]
    assert count_input(request_payload(request), config) <= 8232
    assert not is_summary.get()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["byte_limit", "consumer_budget"])
async def test_summary_batch_keeps_bounded_merge_fallback(reason):
    class VerbosePartials(EvidenceSummarizer):
        async def generate_content_async(self, request, stream=False):
            async for response in super().generate_content_async(request, stream):
                if (
                    reason == "byte_limit"
                    and "Historical partial summaries"
                    not in request.contents[0].parts[0].text
                ):
                    data = json.loads(response.content.parts[0].text)
                    data["uncertainties"] = ["x" * 2000]
                    response.content.parts[0].text = json.dumps(data)
                yield response

    model = VerbosePartials()
    config = ContextCompressionConfig(
        context_window=9000, summary_max_tokens=512, safety_margin=256
    )
    result = json.loads(
        await summarize_history(
            history(),
            model,
            config,
            accept_candidate=lambda _: reason != "consumer_budget",
        )
    )
    assert len(model.requests) == 3
    assert set(result["evidence"]) == {f"INV-{i} = {i}.25 CNY" for i in range(8)}
    budget = resolve_budget(model.model, config, config.summary_max_tokens)
    assert all(
        count_input(request_payload(r), config) <= budget.available
        for r in model.requests
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
async def test_summary_batch_checks_protected_values_across_all_parts(missing):
    model = EvidenceSummarizer()
    protected = ("INV-0 = 0.25 CNY", "INV-7 = 7.25 CNY")
    config = ContextCompressionConfig(
        context_window=9000,
        summary_max_tokens=512,
        safety_margin=256,
        protected_context=protected + (("absent fact",) if missing else ()),
    )
    if missing:
        with pytest.raises(ContextBudgetError, match="summary_protected_fact_missing"):
            await summarize_history(
                history(), model, config, accept_candidate=lambda _: True
            )
    else:
        result = json.loads(
            await summarize_history(
                history(), model, config, accept_candidate=lambda _: True
            )
        )
        evidence = [
            fact
            for part in result["chronological_summaries"]
            for fact in part["evidence"]
        ]
        assert all(fact in evidence for fact in protected)
    assert len(model.requests) == 2


@pytest.mark.asyncio
async def test_manager_rejects_batch_when_recent_context_needs_smaller_merge():
    from google.adk.models.llm_request import LlmRequest

    from veadk.context.manager import prepare_context

    class VerbosePartials(EvidenceSummarizer):
        async def generate_content_async(self, request, stream=False):
            async for response in super().generate_content_async(request, stream):
                if (
                    "Historical partial summaries"
                    not in request.contents[0].parts[0].text
                ):
                    data = json.loads(response.content.parts[0].text)
                    data["uncertainties"] = ["x" * 600]
                    response.content.parts[0].text = json.dumps(data)
                yield response

    model = VerbosePartials()
    config = ContextCompressionConfig(
        context_window=9000,
        output_reserve=512,
        summary_max_tokens=512,
        safety_margin=256,
    )
    recent = [
        types.Content(role="user", parts=[types.Part(text="r" * 3250)]),
        types.Content(role="model", parts=[types.Part(text="Acknowledged")]),
        types.Content(role="user", parts=[types.Part(text="s" * 3250)]),
    ]
    request = LlmRequest(model=model.model, contents=history() + recent)
    await prepare_context(request, model, config, {})
    assert len(model.requests) == 3
    assert request.contents[1:] == recent
    assert "chronological_summaries" not in request.contents[0].parts[0].text
    assert count_input(request_payload(request), config) <= 8232


@pytest.mark.asyncio
async def test_balanced_chunks_avoid_large_request_timeout_without_extra_calls():
    config = ContextCompressionConfig(
        context_window=9000,
        summary_max_tokens=512,
        safety_margin=256,
        summary_timeout_seconds=0.1,
    )

    class LatencyLimitedSummarizer(EvidenceSummarizer):
        async def generate_content_async(self, request, stream=False):
            # Simulate a provider whose prefill latency exceeds the deadline
            # above this input size. The full model window still fits 8,232.
            if count_input(request_payload(request), config) > 6500:
                await asyncio.Event().wait()
            async for response in super().generate_content_async(request, stream):
                yield response

    model = LatencyLimitedSummarizer()
    contents = history()[:10]
    original = [item.model_dump(mode="json", exclude_none=True) for item in contents]
    result = json.loads(await summarize_history(contents, model, config))
    assert len(model.requests) == 3  # Two partial summaries and one merge.
    assert set(result["evidence"]) == {f"INV-{i} = {i}.25 CNY" for i in range(5)}
    actual = [
        record
        for request in model.requests[:-1]
        for record in json.loads(request.contents[0].parts[0].text)[
            "historical_records"
        ]
    ]
    assert actual == original


@pytest.mark.asyncio
@pytest.mark.parametrize("padding", ["x", '\\"'])
async def test_balanced_chunks_keep_tool_transactions_and_check_escaped_payloads(
    padding,
):
    padding_size = 650 if padding == "x" else 120
    contents = []
    for index in range(5):
        contents.extend(
            [
                types.Content(role="user", parts=[types.Part(text="Read record")]),
                types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id=f"call-{index}", name="lookup", args={"index": index}
                            )
                        )
                    ],
                ),
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=f"call-{index}",
                                name="lookup",
                                response={
                                    "result": f"INV-{index} = {index}.25 CNY. "
                                    + padding * padding_size
                                },
                            )
                        )
                    ],
                ),
                types.Content(
                    role="model", parts=[types.Part(text=padding * padding_size)]
                ),
            ]
        )
    config = ContextCompressionConfig(
        context_window=9000, summary_max_tokens=512, safety_margin=256
    )
    model = EvidenceSummarizer()
    result = json.loads(await summarize_history(contents, model, config))
    assert 2 < len(model.requests) <= config.max_summary_calls
    assert set(result["evidence"]) == {f"INV-{i} = {i}.25 CNY" for i in range(5)}
    actual = []
    for request in model.requests[:-1]:
        records = json.loads(request.contents[0].parts[0].text)["historical_records"]
        pending = set()
        for record in records:
            for part in record.get("parts", []):
                if "function_call" in part:
                    pending.add(part["function_call"]["id"])
                if "function_response" in part:
                    pending.remove(part["function_response"]["id"])
        assert not pending
        actual.extend(records)
    assert actual == [
        item.model_dump(mode="json", exclude_none=True) for item in contents
    ]
    budget = resolve_budget(model.model, config, config.summary_max_tokens)
    assert all(
        count_input(request_payload(r), config) <= budget.available
        for r in model.requests
    )


@pytest.mark.asyncio
async def test_exhausted_summary_budget_sends_no_partial_chunk_work():
    model = EvidenceSummarizer()
    scope = ContextScope(
        session=Session(id="s", user_id="u", app_name="a"),
        agent_name="agent",
        branch="",
    )
    scope.summary_calls = 3
    token = current_scope.set(scope)
    try:
        with pytest.raises(ContextBudgetError, match="summary_call_budget_exhausted"):
            await summarize_history(
                history(),
                model,
                ContextCompressionConfig(
                    context_window=9000,
                    summary_max_tokens=512,
                    safety_margin=256,
                ),
            )
        assert model.requests == []
        assert scope.pending_state == {}
    finally:
        current_scope.reset(token)


@pytest.mark.asyncio
async def test_cancellation_closes_summarizer_without_installing_state():
    entered = asyncio.Event()
    closed = asyncio.Event()

    class SlowSummarizer(EvidenceSummarizer):
        async def generate_content_async(self, request, stream=False):
            try:
                entered.set()
                await asyncio.Event().wait()
                yield  # pragma: no cover
            finally:
                closed.set()

    task = asyncio.create_task(
        summarize_history(
            history()[:2],
            SlowSummarizer(),
            ContextCompressionConfig(context_window=9000, summary_max_tokens=512),
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    assert not is_summary.get()


@pytest.mark.asyncio
async def test_explicit_protected_fact_must_survive_summary():
    model = EvidenceSummarizer()
    with pytest.raises(ContextBudgetError, match="summary_protected_fact_missing"):
        await summarize_history(
            history()[:2],
            model,
            ContextCompressionConfig(
                context_window=9000,
                summary_max_tokens=512,
                protected_context=("Never transfer money",),
            ),
        )


@pytest.mark.asyncio
async def test_protected_facts_across_chunks_are_validated_in_final_summary():
    model = EvidenceSummarizer()
    protected = ("INV-0 = 0.25 CNY", "INV-7 = 7.25 CNY")
    result = json.loads(
        await summarize_history(
            history(),
            model,
            ContextCompressionConfig(
                context_window=9000,
                summary_max_tokens=512,
                safety_margin=256,
                protected_context=protected,
            ),
        )
    )
    assert len(model.requests) == 3
    assert all(item in result["evidence"] for item in protected)


@pytest.mark.asyncio
async def test_final_merge_cannot_drop_a_protected_fact_from_a_partial_summary():
    class LosingMergeSummarizer(EvidenceSummarizer):
        async def generate_content_async(self, request, stream=False):
            async for response in super().generate_content_async(request, stream):
                if "Historical partial summaries" in request.contents[0].parts[0].text:
                    data = json.loads(response.content.parts[0].text)
                    data["evidence"] = ["INV-7 = 7.25 CNY"]
                    response.content.parts[0].text = json.dumps(data)
                yield response

    model = LosingMergeSummarizer()
    with pytest.raises(ContextBudgetError, match="summary_protected_fact_missing"):
        await summarize_history(
            history(),
            model,
            ContextCompressionConfig(
                context_window=9000,
                summary_max_tokens=512,
                safety_margin=256,
                protected_context=("INV-0 = 0.25 CNY", "INV-7 = 7.25 CNY"),
            ),
        )
    assert len(model.requests) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("required", "field_value", "should_pass"),
    [
        ('WHERE status = "ready"\nLIMIT 1', 'WHERE status = "ready"\nLIMIT 1', True),
        (r"\n", "\n", False),
    ],
)
async def test_protected_facts_match_decoded_values_not_json_escapes(
    required, field_value, should_pass
):
    class FieldSummarizer(EvidenceSummarizer):
        async def generate_content_async(self, request, stream=False):
            async for response in super().generate_content_async(request, stream):
                data = json.loads(response.content.parts[0].text)
                data["evidence"] = [field_value]
                response.content.parts[0].text = json.dumps(data)
                yield response

    model = FieldSummarizer()
    config = ContextCompressionConfig(
        context_window=9000,
        summary_max_tokens=512,
        protected_context=(required,),
    )
    if should_pass:
        result = json.loads(await summarize_history(history()[:2], model, config))
        assert result["evidence"] == [required]
    else:
        with pytest.raises(ContextBudgetError, match="summary_protected_fact_missing"):
            await summarize_history(history()[:2], model, config)
    assert len(model.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("parent_seconds", [None, 0.01])
async def test_summary_timeout_is_distinct_and_respects_parent_deadline(parent_seconds):
    closed = asyncio.Event()

    class SlowSummarizer(EvidenceSummarizer):
        async def generate_content_async(self, request, stream=False):
            try:
                await asyncio.Event().wait()
                yield  # pragma: no cover
            finally:
                closed.set()

    ledger = AttemptLedger(3, parent_seconds) if parent_seconds else None
    token = current_attempts.set(ledger)
    try:
        with pytest.raises(ContextBudgetError) as caught:
            await asyncio.wait_for(
                summarize_history(
                    history()[:2],
                    SlowSummarizer(),
                    ContextCompressionConfig(
                        context_window=9000,
                        summary_max_tokens=512,
                        summary_timeout_seconds=1 if ledger else 0.01,
                        summary_time_budget_ratio=1,
                    ),
                ),
                timeout=0.5,
            )
        expected = "request_time_budget_exhausted" if ledger else "summary_timeout"
        assert caught.value.code == expected
        assert closed.is_set()
        assert not is_summary.get()
        assert current_attempts.get() is ledger
    finally:
        current_attempts.reset(token)


@pytest.mark.asyncio
async def test_expired_parent_budget_prevents_summary_network_call():
    model = EvidenceSummarizer()
    token = current_attempts.set(AttemptLedger(3, 1, started=0))
    try:
        with pytest.raises(ContextBudgetError, match="request_time_budget_exhausted"):
            await summarize_history(
                history()[:2], model, ContextCompressionConfig(context_window=9000)
            )
        assert model.requests == []
    finally:
        current_attempts.reset(token)
