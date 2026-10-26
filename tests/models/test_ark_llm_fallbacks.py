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

import httpx
import json
import logging
from types import SimpleNamespace
import pytest
from google.adk.models import LlmResponse
from google.adk.models import LlmRequest
from google.genai import types
from volcenginesdkarkruntime._exceptions import ArkBadRequestError
from volcenginesdkarkruntime.types.responses import ResponseFunctionToolCall

from veadk.models.ark_llm import ArkLlm
from veadk.models import ark_llm


@pytest.mark.asyncio
async def test_ark_llm_uses_next_model_when_primary_fails(monkeypatch):
    model = ArkLlm(
        model="openai/primary-model",
        fallbacks=["openai/fallback-model"],
    )
    calls = []

    async def fake_generate(self, responses_args, stream=False):
        calls.append((responses_args["model"], stream))
        if responses_args["model"] == "openai/primary-model":
            raise RuntimeError("primary failed")
        yield LlmResponse(model_version=responses_args["model"])

    monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)

    responses = [
        response
        async for response in model._generate_content_with_fallbacks(
            {"input": []}, stream=True
        )
    ]

    assert calls == [
        ("openai/primary-model", True),
        ("openai/fallback-model", True),
    ]
    assert [response.model_version for response in responses] == [
        "openai/fallback-model"
    ]


@pytest.mark.asyncio
async def test_ark_llm_raises_last_error_when_all_models_fail(monkeypatch):
    model = ArkLlm(
        model="openai/primary-model",
        fallbacks=["openai/fallback-model"],
    )

    async def fake_generate(self, responses_args, stream=False):
        if False:
            yield
        raise RuntimeError(f"{responses_args['model']} failed")

    monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)

    with pytest.raises(RuntimeError, match="openai/fallback-model failed"):
        async for _ in model._generate_content_with_fallbacks({"input": []}):
            pass


@pytest.mark.asyncio
async def test_ark_llm_does_not_fallback_after_stream_output(monkeypatch):
    model = ArkLlm(
        model="openai/primary-model",
        fallbacks=["openai/fallback-model"],
    )
    calls = []

    async def fake_generate(self, responses_args, stream=False):
        calls.append(responses_args["model"])
        yield LlmResponse(model_version=responses_args["model"], partial=True)
        raise RuntimeError("stream interrupted")

    monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)

    generator = model._generate_content_with_fallbacks({"input": []}, stream=True)
    first_response = await anext(generator)
    assert first_response.model_version == "openai/primary-model"

    with pytest.raises(RuntimeError, match="stream interrupted"):
        await anext(generator)

    assert calls == ["openai/primary-model"]


@pytest.mark.asyncio
async def test_ark_llm_retries_expired_response_before_fallback(monkeypatch):
    model = ArkLlm(
        model="openai/primary-model",
        fallbacks=["openai/fallback-model"],
    )
    calls = []
    request = httpx.Request("POST", "https://ark.example/v1/responses")
    expired_error = ArkBadRequestError(
        "previous response expired",
        response=httpx.Response(400, request=request),
        body={"code": "InvalidParameter.PreviousResponseNotFound"},
        request_id="request-id",
    )

    async def fake_generate(self, responses_args, stream=False):
        calls.append(
            (responses_args["model"], responses_args.get("previous_response_id"))
        )
        if len(calls) == 1:
            raise expired_error
        if responses_args["model"] == "openai/primary-model":
            raise RuntimeError("primary failed without cache")
        yield LlmResponse(model_version=responses_args["model"])

    monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)

    responses = [
        response
        async for response in model._generate_content_with_fallbacks(
            {"input": [], "previous_response_id": "expired-id"}
        )
    ]

    assert calls == [
        ("openai/primary-model", "expired-id"),
        ("openai/primary-model", None),
        ("openai/fallback-model", None),
    ]
    assert responses[0].model_version == "openai/fallback-model"


@pytest.mark.asyncio
async def test_ark_llm_does_not_replay_expired_response_when_disabled(monkeypatch):
    model = ArkLlm(
        model="openai/primary-model",
        retry_expired_response=False,
    )
    calls = []
    request = httpx.Request("POST", "https://ark.example/v1/responses")
    expired_error = ArkBadRequestError(
        "previous response expired",
        response=httpx.Response(400, request=request),
        body={"code": "InvalidParameter.PreviousResponseNotFound"},
        request_id="request-id",
    )

    async def fake_generate(self, responses_args, stream=False):
        calls.append(responses_args.get("previous_response_id"))
        raise expired_error
        yield  # pragma: no cover

    monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)

    with pytest.raises(RuntimeError, match="context expired; start a new Session"):
        async for _ in model._generate_content_with_fallbacks(
            {"input": [], "previous_response_id": "expired-id"}
        ):
            pass

    assert calls == ["expired-id"]
    assert "retry_expired_response" not in model._additional_args


def test_model_trace_disabled_by_default(monkeypatch, caplog):
    monkeypatch.delenv("MANAGED_AGENT_MODEL_TRACE", raising=False)
    with caplog.at_level(logging.INFO, logger="anthropic.managed_agent_model"):
        ark_llm._trace_model_request(
            {"model": "model-a", "tools": [{"name": "bash", "type": "function"}]}
        )
    assert not [
        record
        for record in caplog.records
        if record.name == "anthropic.managed_agent_model"
    ]


def test_model_trace_owner_configures_ready_without_root_logger(monkeypatch, capsys):
    monkeypatch.setenv("MANAGED_AGENT_MODEL_TRACE", "true")
    logger = logging.getLogger("anthropic.managed_agent_model")
    existing = list(logger.handlers)
    try:
        logger.handlers.clear()
        ark_llm.configure_managed_agent_model_trace()
        captured = capsys.readouterr()
        payload = json.loads(captured.err.strip())
        assert payload["event"] == "model_trace_ready"
        assert payload["module"].endswith("/veadk/models/ark_llm.py")
        assert logger.propagate is False
        assert len(logger.handlers) == 1
    finally:
        logger.handlers[:] = existing


def test_model_trace_whitelists_request_and_response_fields(monkeypatch, caplog):
    monkeypatch.setenv("MANAGED_AGENT_MODEL_TRACE", "true")
    logger = logging.getLogger("anthropic.managed_agent_model")
    existing_handlers = list(logger.handlers)
    existing_propagate = logger.propagate
    logger.handlers.clear()
    logger.propagate = True
    try:
        with caplog.at_level(logging.INFO, logger=logger.name):
            ark_llm._trace_model_request(
                {
                    "model": "model-a",
                    "tools": [
                        {
                            "name": "bash",
                            "type": "function",
                            "parameters": {"secret": "no"},
                        },
                        {"name": "bad name", "type": "custom"},
                    ],
                    "tool_choice": {"type": "function", "function": {"name": "bash"}},
                    "previous_response_id": "secret-response-id",
                    "input": "secret prompt",
                    "api_key": "secret-key",
                }
            )
            ark_llm._trace_model_response(
                SimpleNamespace(
                    output=[
                        SimpleNamespace(type="function_call"),
                        SimpleNamespace(type="message"),
                    ],
                    secret="no",
                )
            )
    finally:
        logger.handlers[:] = existing_handlers
        logger.propagate = existing_propagate
    payloads = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == logger.name
    ]
    assert payloads == [
        {
            "event": "model_request",
            "has_previous_response_id": True,
            "model": "model-a",
            "tool_choice": {"name": "bash", "type": "function"},
            "tools": [
                {"name": "bash", "type": "function"},
                {"name": "", "type": "custom"},
            ],
        },
        {"event": "model_response", "output_types": ["function_call", "message"]},
    ]
    rendered = "\n".join(record.message for record in caplog.records)
    assert "secret prompt" not in rendered
    assert "secret-key" not in rendered
    assert "secret-response-id" not in rendered


@pytest.mark.asyncio
async def test_controlled_function_call_response_is_traced_and_converted(
    monkeypatch, caplog
):
    monkeypatch.setenv("MANAGED_AGENT_MODEL_TRACE", "true")
    raw_response = SimpleNamespace(
        output=[
            ResponseFunctionToolCall(
                type="function_call",
                call_id="toolu-safe-1",
                name="bash",
                arguments='{"command":"printf controlled"}',
                id="output-safe-1",
                status="completed",
            )
        ],
        status="completed",
        incomplete_details=None,
        model="model-a",
        usage=None,
        id="response-secret-not-logged",
        error=None,
    )

    class Client(ark_llm.ArkLlmClient):
        async def aresponses(self, **kwargs):
            assert kwargs["tools"][0]["name"] == "bash"
            return raw_response

    model = ArkLlm(model="openai/model-a", llm_client=Client())
    logger = logging.getLogger("anthropic.managed_agent_model")
    existing = list(logger.handlers)
    logger.handlers.clear()
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger=logger.name):
            responses = [
                item
                async for item in model.generate_content_via_responses(
                    {
                        "model": "openai/model-a",
                        "input": [],
                        "tools": [{"name": "bash", "type": "function"}],
                        "tool_choice": {"type": "function", "name": "bash"},
                    }
                )
            ]
    finally:
        logger.handlers[:] = existing

    calls = responses[0].content.parts[0].function_call
    assert calls.name == "bash"
    assert calls.id == "toolu-safe-1"
    payloads = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == logger.name
    ]
    assert [payload["event"] for payload in payloads] == [
        "model_trace_ready",
        "model_request",
        "model_response",
    ]
    assert payloads[1]["tools"] == [{"name": "bash", "type": "function"}]
    assert payloads[1]["tool_choice"] == {"name": "bash", "type": "function"}
    assert payloads[2] == {"event": "model_response", "output_types": ["function_call"]}
    assert "printf controlled" not in "\n".join(
        record.message for record in caplog.records
    )
    assert "response-secret-not-logged" not in "\n".join(
        record.message for record in caplog.records
    )


@pytest.mark.asyncio
async def test_generate_path_self_configures_model_trace(monkeypatch, capsys):
    monkeypatch.setenv("MANAGED_AGENT_MODEL_TRACE", "true")
    logger = logging.getLogger("anthropic.managed_agent_model")
    existing = list(logger.handlers)

    class Client(ark_llm.ArkLlmClient):
        async def aresponses(self, **kwargs):
            return SimpleNamespace(
                output=[
                    ResponseFunctionToolCall(
                        type="function_call",
                        call_id="toolu-self-configured",
                        name="bash",
                        arguments="{}",
                        id="output-self-configured",
                        status="completed",
                    )
                ],
                status="completed",
                incomplete_details=None,
                model="model-a",
                usage=None,
                id="response-not-logged",
                error=None,
            )

    try:
        logger.handlers.clear()
        model = ArkLlm(model="openai/model-a", llm_client=Client())
        responses = [
            response
            async for response in model.generate_content_via_responses(
                {
                    "model": "openai/model-a",
                    "input": [],
                    "tools": [{"name": "bash", "type": "function"}],
                }
            )
        ]
        assert responses[0].content.parts[0].function_call.name == "bash"
        events = [
            json.loads(line)["event"] for line in capsys.readouterr().err.splitlines()
        ]
        assert events == ["model_trace_ready", "model_request", "model_response"]
    finally:
        logger.handlers[:] = existing


@pytest.mark.asyncio
async def test_generate_content_preserves_authorized_tools_with_previous_id(
    monkeypatch,
):
    requests = []

    class Client(ark_llm.ArkLlmClient):
        async def aresponses(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(
                output=[],
                status="completed",
                incomplete_details=None,
                model="model-a",
                usage=None,
                id="response-2",
                error=None,
            )

    model = ArkLlm(model="openai/model-a", llm_client=Client())
    monkeypatch.setattr(
        ark_llm,
        "ark_response_to_generate_content_response",
        lambda response: LlmResponse(model_version=response.model),
    )
    request = LlmRequest(
        previous_interaction_id="response-1",
        config=types.GenerateContentConfig(
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name="bash",
                            description="Run a command",
                            parameters_json_schema={"type": "object"},
                        )
                    ]
                )
            ]
        ),
    )

    _ = [item async for item in model.generate_content_async(request)]

    assert requests[0]["previous_response_id"] == "response-1"
    assert [tool["name"] for tool in requests[0]["tools"]] == ["bash"]
