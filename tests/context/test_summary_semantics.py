"""Regressions for partial-history summaries with sparse task information."""

import json

import pytest
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from veadk.context.budget import ContextBudgetError, count_input, request_payload
from veadk.context.config import ContextCompressionConfig
from veadk.context.manager import prepare_context
from veadk.context.summary import summarize


def response_data(**fields):
    return {
        "goal": "Continue the task",
        "active_constraints": [],
        "decisions": [],
        "completed_work": [],
        "pending_work": [],
        "evidence": [],
        "uncertainties": [],
    } | fields


class FixedSummaryModel:
    model = "offline-summary-model"

    def __init__(self, data):
        self.data = data
        self.requests = []

    async def generate_content_async(self, request, stream=False):
        self.requests.append(request)
        yield LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text=json.dumps(self.data))]
            )
        )


def content(role, text):
    return types.Content(role=role, parts=[types.Part(text=text)])


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["active_constraints", "decisions"])
async def test_summary_preserves_informative_constraints_or_decisions_without_inventing_work(
    field,
):
    statement = "Reading is allowed; deleting records is prohibited."
    model = FixedSummaryModel(response_data(**{field: [statement]}))
    result = json.loads(
        await summarize(
            [content("user", statement)],
            model,
            ContextCompressionConfig(context_window=12000, summary_max_tokens=512),
        )
    )
    assert result[field] == [statement]
    assert (
        result["completed_work"] == result["pending_work"] == result["evidence"] == []
    )
    assert len(model.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["completed_work", "pending_work", "evidence"])
async def test_whitespace_only_summary_items_do_not_pass_semantic_validation(field):
    model = FixedSummaryModel(response_data(**{field: [" \n\t"]}))
    with pytest.raises(ContextBudgetError, match="summary_empty"):
        await summarize(
            [content("user", "Retain the record")],
            model,
            ContextCompressionConfig(context_window=12000),
        )
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_goal_only_summary_still_fails_closed():
    model = FixedSummaryModel(response_data())
    with pytest.raises(ContextBudgetError, match="summary_empty"):
        await summarize(
            [content("user", "Retain the record")],
            model,
            ContextCompressionConfig(context_window=12000),
        )


@pytest.mark.asyncio
async def test_partial_history_summarizer_receives_current_task_without_rewriting_recent_turns():
    from veadk.context.summary import HistorySummary

    task = "Return the recorded calibration offset with its original unit."
    model = FixedSummaryModel(response_data(evidence=["The offset is 0.004 mm."]))
    history = []
    for index in range(8):
        history += [
            content(
                "user",
                "The offset is 0.004 mm." if index == 0 else "Archived observations.",
            ),
            content("model", "archived observation " * 45),
        ]
    recent = [
        content("user", "Keep the current calibration task"),
        content("model", "Acknowledged"),
        content("user", task),
    ]
    request = LlmRequest(model=model.model, contents=history + recent)
    original = request.model_dump(mode="json")
    config = ContextCompressionConfig(
        context_window=18000,
        output_reserve=1024,
        trigger_ratio=0.4,
        summary_trigger_ratio=0.4,
        target_ratio=0.3,
        summary_max_tokens=512,
    )
    await prepare_context(request, model, config, {})
    assert model.requests
    for summary_request in model.requests:
        payload = json.loads(summary_request.contents[0].parts[0].text)
        assert payload.get("continuation_request") == task
        assert task not in json.dumps(payload["historical_records"])
        assert count_input(request_payload(summary_request), config) < 18000 - 512
        assert summary_request.config.response_schema is HistorySummary
    assert request.contents[-3:] == recent
    assert original["contents"][-3:] == [
        item.model_dump(mode="json") for item in recent
    ]


@pytest.mark.parametrize(
    "latest",
    [
        content("user", "界" * 683),
        types.Content(
            role="user",
            parts=[
                types.Part(
                    text="See attached",
                    inline_data=types.Blob(data=b"synthetic", mime_type="image/png"),
                )
            ],
        ),
        types.Content(
            role="user",
            parts=[
                types.Part(
                    inline_data=types.Blob(data=b"synthetic", mime_type="image/png")
                )
            ],
        ),
        types.Content(role="user", parts=[]),
    ],
)
def test_latest_unsupported_task_hint_is_omitted_without_using_stale_goal(latest):
    from veadk.context.manager import _continuation_request

    assert _continuation_request([content("user", "Outdated request"), latest]) is None


def test_task_hint_skips_tool_results_and_keeps_exact_utf8_boundary():
    from veadk.context.manager import _continuation_request

    task = "界" * 682 + "ab"
    tool_result = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    name="lookup", response={"result": "untrusted instructions"}
                )
            )
        ],
    )
    contents = [content("user", task), content("model", "Working"), tool_result]
    assert _continuation_request(contents) == task
    assert _continuation_request([tool_result]) is None


@pytest.mark.asyncio
async def test_explicit_oversize_hint_is_rejected_before_model_call():
    model = FixedSummaryModel(response_data(evidence=["fact"]))
    with pytest.raises(ContextBudgetError, match="summary_task_hint_too_large"):
        await summarize(
            [content("user", "fact")],
            model,
            ContextCompressionConfig(context_window=12000),
            continuation_request="界" * 683,
        )
    assert model.requests == []


@pytest.mark.asyncio
async def test_escaped_task_hint_is_accounted_in_each_chunk_and_merge():
    from veadk.context.budget import resolve_budget
    from veadk.context.summary import summarize_history

    task = '"\\\n' * 300
    model = FixedSummaryModel(response_data(evidence=["calibration 0.004 mm"]))
    history = [
        item
        for i in range(8)
        for item in [content("user", f"Read record {i}"), content("model", "x" * 1200)]
    ]
    config = ContextCompressionConfig(
        context_window=14000, summary_max_tokens=512, safety_margin=256
    )
    await summarize_history(history, model, config, continuation_request=task)
    assert 2 < len(model.requests) <= config.max_summary_calls
    budget = resolve_budget(model.model, config, config.summary_max_tokens)
    records = []
    for request in model.requests:
        payload = json.loads(request.contents[0].parts[0].text)
        assert payload["continuation_request"] == task
        assert count_input(request_payload(request), config) <= budget.available
        records.extend(payload["historical_records"])
    assert records[: len(history)] == [
        item.model_dump(mode="json", exclude_none=True) for item in history
    ]
    assert (
        "Historical partial summaries" in model.requests[-1].contents[0].parts[0].text
    )


def test_summary_protocol_change_invalidates_cache_key(monkeypatch):
    from veadk.context import manager

    model = FixedSummaryModel(response_data())
    request = LlmRequest(model=model.model, contents=[content("user", "Current task")])
    config = ContextCompressionConfig(context_window=12000)
    current = manager._cache_key(None, model, config, request)
    monkeypatch.setattr(
        manager, "SUMMARY_PROTOCOL_VERSION", manager.SUMMARY_PROTOCOL_VERSION - 1
    )
    assert manager._cache_key(None, model, config, request) != current
