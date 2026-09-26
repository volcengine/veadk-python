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

"""Keep business schemas isolated from summaries at the actual HTTP boundary.

All transport responses are synthetic. These tests check SDK contracts, not a
model's ability to produce correct facts or obey structured-output constraints.
"""

import copy
import json
from typing import Literal

import httpx
import pytest
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, ConfigDict

from veadk import Agent, Runner
from veadk.context.budget import ContextBudgetError
from veadk.context.runtime import is_summary
from veadk.context.summary import HistorySummary
from veadk.models.ark_llm import ArkLlm
from veadk.models.retrying_lite_llm import RetryingLiteLlm

MODEL = "doubao-seed-2-1-pro-260628"
POLICY = {
    "context_window": 20000,
    "output_reserve": 2000,
    "safety_margin": 256,
    "trigger_ratio": 0.4,
    "summary_trigger_ratio": 0.4,
    "target_ratio": 0.3,
}


class Amount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    currency: Literal["CNY", "USD"]


class InvoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str
    amount: Amount
    payment_allowed: bool


ANSWER = {
    "reference": "INV-418",
    "amount": {"value": "187.25", "currency": "CNY"},
    "payment_allowed": False,
}
SUMMARY = HistorySummary(
    goal="Reconcile INV-418",
    active_constraints=["Never submit payment"],
    decisions=[],
    completed_work=[],
    pending_work=[],
    evidence=["INV-418 total=187.25 CNY"],
    uncertainties=[],
)


def content(role, text):
    return types.Content(role=role, parts=[types.Part(text=text)])


def history():
    result = []
    for index in range(8):
        result.extend(
            [
                content("user", f"Invoice INV-418 step {index}. Never submit payment."),
                content("model", "Historical explanation. " * 35 + "Total 187.25 CNY."),
            ]
        )
    return result


def schema_format(body):
    if "messages" in body:
        return body["response_format"]["json_schema"]
    return body["text"]["format"]


@pytest.fixture
def wire(monkeypatch):
    captures = []
    behavior = {"invalid_summary": False}

    # Freeze only the Ark expiry clock so complete wire bodies can be compared.
    monkeypatch.setattr("veadk.models.ark_llm.time.time", lambda: 1800000000)

    async def send(self, request, **kwargs):
        assert request.url.host == "ark.cn-beijing.volces.com"
        body = json.loads(request.content)
        if "/embeddings" in request.url.path:
            # Default retrieval can now request embeddings. This fixture tests
            # business/summary wire schemas with that optional service absent;
            # embedding response bodies are not business-schema requests.
            return httpx.Response(
                403,
                request=request,
                json={
                    "error": {
                        "code": "offline_embedding_disabled",
                        "message": "Synthetic optional service failure",
                    }
                },
            )
        summary = is_summary.get()
        captures.append((summary, body))
        expected = HistorySummary if summary else InvoiceAnswer
        assert set(schema_format(body)["schema"]["properties"]) == set(
            expected.model_fields
        )
        text = SUMMARY.model_dump_json() if summary else json.dumps(ANSWER)
        if summary and behavior["invalid_summary"]:
            text = "{}"
        if request.url.path.endswith("/chat/completions"):
            response = {
                "id": "synthetic",
                "created": 0,
                "object": "chat.completion",
                "model": MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": text},
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        else:
            assert request.url.path.endswith("/responses")
            response = {
                "id": "synthetic",
                "created_at": 0,
                "object": "response",
                "model": MODEL,
                "status": "completed",
                "error": None,
                "incomplete_details": None,
                "output": [
                    {
                        "id": "synthetic-message",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": text, "annotations": []}
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "total_tokens": 2,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            }
        return httpx.Response(200, request=request, json=response)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    return captures, behavior


def model_for(adapter, *, mode="auto"):
    kwargs = {}
    if adapter is not LiteLlm:
        kwargs["context_compression"] = {**POLICY, "mode": mode}
    if adapter is ArkLlm:
        kwargs["reasoning"] = {"effort": "medium"}
    return adapter(
        model="openai/" + MODEL,
        api_base="https://ark.cn-beijing.volces.com/api/v3",
        api_key="synthetic-offline",
        extra_body={"thinking": {"type": "enabled"}},
        **kwargs,
    )


def request_for(*, long=False, schema=InvoiceAnswer):
    return LlmRequest(
        contents=[
            *(history() if long else []),
            content("user", "Return the invoice details."),
        ],
        config=types.GenerateContentConfig(
            system_instruction="Retain invoice facts. Never submit payment.",
            response_mime_type="application/json",
            response_schema=schema,
            max_output_tokens=512,
            temperature=0.3,
        ),
    )


async def collect(model, request):
    responses = [r async for r in model.generate_content_async(request)]
    text = "".join(p.text or "" for r in responses for p in r.content.parts)
    assert json.loads(text) == ANSWER


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "off"])
async def test_short_business_schema_matches_native_litellm_wire(wire, mode):
    captures, _ = wire
    await collect(model_for(LiteLlm), request_for())
    await collect(model_for(RetryingLiteLlm, mode=mode), request_for())
    assert len(captures) == 2
    assert captures[0] == captures[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", [RetryingLiteLlm, ArkLlm])
@pytest.mark.parametrize("as_dict", [False, True])
async def test_summary_schema_never_replaces_business_schema(wire, adapter, as_dict):
    captures, _ = wire
    schema = InvoiceAnswer.model_json_schema() if as_dict else InvoiceAnswer
    request = request_for(long=True, schema=schema)
    original = copy.deepcopy(request)
    model = model_for(adapter)
    additional = copy.deepcopy(model._additional_args)

    await collect(model_for(adapter, mode="off"), copy.deepcopy(request))
    await collect(model, request)
    assert [summary for summary, _ in captures] == [False, True, False]
    baseline, summary, main = [body for _, body in captures]
    assert schema_format(main) == schema_format(baseline)
    assert schema_format(main)["schema"]["additionalProperties"] is False
    assert set(schema_format(main)["schema"]["required"]) == set(
        InvoiceAnswer.model_fields
    )
    assert schema_format(main) != schema_format(summary)
    history_key = "messages" if adapter is RetryingLiteLlm else "input"
    assert {k: v for k, v in main.items() if k != history_key} == {
        k: v for k, v in baseline.items() if k != history_key
    }
    assert len(json.dumps(main[history_key])) < len(json.dumps(baseline[history_key]))
    assert "Summary of earlier conversation" in json.dumps(main[history_key])
    assert main[history_key][-1] == baseline[history_key][-1]
    assert main["thinking"] == {"type": "enabled"}
    if adapter is RetryingLiteLlm:
        assert summary["thinking"] == {"type": "disabled"}
    else:
        # Responses uses reasoning.effort, unlike Chat's thinking.type control.
        assert summary["reasoning"] == {"effort": "minimal"}
        assert main["reasoning"] == {"effort": "medium"}
    assert request == original
    assert model._additional_args == additional

    # Reusing the same model for a fresh request must not retain summary state.
    await collect(model, request_for(schema=schema))
    assert not captures[-1][0]
    assert schema_format(captures[-1][1]) == schema_format(baseline)


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", [RetryingLiteLlm, ArkLlm])
async def test_invalid_summary_fallback_keeps_complete_main_request(wire, adapter):
    captures, behavior = wire
    request = request_for(long=True)
    original = copy.deepcopy(request)
    await collect(model_for(adapter, mode="off"), copy.deepcopy(request))
    behavior["invalid_summary"] = True
    await collect(model_for(adapter), request)
    assert [summary for summary, _ in captures] == [False, True, False]
    assert captures[0][1] == captures[-1][1]
    assert request == original


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", [RetryingLiteLlm, ArkLlm])
async def test_oversized_business_schema_is_not_dropped_to_fit(wire, adapter):
    captures, _ = wire
    schema = InvoiceAnswer.model_json_schema()
    schema["properties"]["reference"]["description"] = "x" * 30000
    request = request_for(schema=schema)
    original = copy.deepcopy(request)
    with pytest.raises(ContextBudgetError):
        await collect(model_for(adapter), request)
    assert captures == []
    assert request == original


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", [RetryingLiteLlm, ArkLlm])
async def test_runner_output_schema_and_original_events_survive_summary(wire, adapter):
    captures, _ = wire
    identity = {"app_name": "schema_test", "user_id": "user", "session_id": "session"}
    service = InMemorySessionService()
    session = await service.create_session(**identity)
    originals = history()
    for index, value in enumerate(originals):
        await service.append_event(
            session,
            Event(
                author="user" if value.role == "user" else "accountant",
                invocation_id=f"history-{index // 2}",
                content=value,
            ),
        )
    events_before = [event.model_dump(mode="json") for event in session.events]
    agent = Agent(
        name="accountant",
        model=model_for(adapter),
        model_api_key="synthetic-offline",
        instruction="Retain invoice facts. Never submit payment.",
        output_schema=InvoiceAnswer,
        output_key="invoice_result",
        generate_content_config=types.GenerateContentConfig(max_output_tokens=512),
    )
    runner = Runner(agent=agent, app_name=identity["app_name"], session_service=service)
    events = [
        event
        async for event in runner.run_async(
            user_id=identity["user_id"],
            session_id=identity["session_id"],
            new_message=content("user", "Return the invoice details."),
        )
    ]
    saved = await service.get_session(**identity)
    assert [summary for summary, _ in captures] == [True, False]
    assert saved.state["invoice_result"] == ANSWER
    assert [
        event.model_dump(mode="json") for event in saved.events[: len(events_before)]
    ] == events_before
    assert any(event.is_final_response() for event in events)
    assert agent.output_schema is InvoiceAnswer
