"""Independent transport-boundary checks for summary partition planning."""

import copy
from pathlib import Path

import pytest
from google.adk.models.lite_llm import LiteLLMClient
from google.genai import types
from litellm import ModelResponse

from veadk.context.budget import check_payload, count_input
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import is_summary
from veadk.context.summary import HistorySummary, _input_size, summarize
from veadk.models.retrying_lite_llm import RetryingLiteLlm

assert (
    Path(_input_size.__code__.co_filename).resolve()
    == (Path(__file__).resolve().parents[2] / "veadk/context/summary.py").resolve()
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text", ["ASCII facts.", "中文记录🙂。", 'Quotes " slash \\ newline\n']
)
@pytest.mark.parametrize("length", [2, 400])
@pytest.mark.parametrize("override", [False, True])
async def test_summary_estimate_covers_actual_adapter_serialization(
    text, length, override
):
    policy = ContextCompressionConfig(context_window=256000, input_limit=40000)
    requests = []

    class Client(LiteLLMClient):
        async def acompletion(self, **kwargs):
            assert (
                is_summary.get()
                and not kwargs.get("stream")
                and not kwargs.get("tools")
            )
            check_payload(kwargs, policy)
            requests.append(copy.deepcopy(kwargs))
            value = HistorySummary(
                goal="Preserve records",
                active_constraints=[],
                decisions=[],
                completed_work=[],
                pending_work=[],
                evidence=["Synthetic source record."],
                uncertainties=[],
            )
            return ModelResponse(
                model="deepseek-v4-1-flash-260910",
                choices=[
                    {
                        "message": {
                            "role": "assistant",
                            "content": value.model_dump_json(),
                        }
                    }
                ],
            )

    extra = (
        {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "synthetic",
                    "schema": {
                        "type": "object",
                        "description": "Extra serialization detail. " * 100,
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            }
        }
        if override
        else {}
    )
    model = RetryingLiteLlm(
        model="openai/deepseek-v4-1-flash-260910",
        api_key="synthetic-offline-test",
        llm_client=Client(),
        context_compression=policy,
        max_tokens=1024,
        extra_body={"thinking": {"type": "disabled"}},
        **extra,
    )
    contents = [types.Content(role="user", parts=[types.Part(text=text * length)])]
    before = [content.model_dump(mode="json") for content in contents]
    estimate = await _input_size(contents, model, policy, "Retain exact source facts.")
    assert requests == []
    await summarize(
        contents, model, policy, continuation_request="Retain exact source facts."
    )
    assert len(requests) == 1 and estimate >= count_input(requests[0], policy)
    assert [content.model_dump(mode="json") for content in contents] == before


@pytest.mark.asyncio
@pytest.mark.parametrize("length", [3, 6])
async def test_unknown_serializer_contract_is_rejected_before_model_call(
    monkeypatch, length
):
    from google.adk.models import lite_llm

    from veadk.context.budget import ContextBudgetError

    class NoCalls(LiteLLMClient):
        async def acompletion(self, **kwargs):
            pytest.fail("unknown serializer must not reach a model client")

    async def unknown(*args):
        return (None,) * length

    policy = ContextCompressionConfig(context_window=256000, input_limit=40000)
    model = RetryingLiteLlm(
        model="openai/deepseek-v4-1-flash-260910",
        api_key="synthetic-offline-test",
        llm_client=NoCalls(),
        context_compression=policy,
        max_tokens=1024,
    )
    monkeypatch.setattr(lite_llm, "_get_completion_inputs", unknown)
    with pytest.raises(ContextBudgetError) as raised:
        await _input_size(
            [types.Content(role="user", parts=[types.Part(text="Source fact.")])],
            model,
            policy,
        )
    assert raised.value.code == "summary_adapter_unsupported"
