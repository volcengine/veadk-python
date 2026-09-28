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

"""Capacity resolution and no-send regressions; every provider is synthetic."""

from datetime import date
from typing import Any

import pytest
from google.adk.models.lite_llm import LiteLLMClient, LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from litellm import ModelResponse

from veadk.context.budget import (
    ContextBudgetError,
    check_payload,
    model_limits,
    resolve_budget,
)
from veadk.context.client import BudgetedLiteLLMClient
from veadk.context.config import ContextCompressionConfig
from veadk.models.ark_llm import ArkLlm, ArkLlmClient
from veadk.models.retrying_lite_llm import RetryingLiteLlm


class RecordingClient(LiteLLMClient):
    def __init__(self):
        self.calls = []

    def completion(self, model, messages, tools=None, stream=False, **kwargs):
        self.calls.append(model)
        return ModelResponse(choices=[])

    async def acompletion(self, model, messages, tools=None, stream=False, **kwargs):
        self.calls.append(model)
        return ModelResponse(choices=[])


@pytest.mark.parametrize("mode", ["auto", "off"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "model", ["openai/not-reviewed-capacity", "openai/ep-private-test"]
)
def test_unknown_sync_is_rejected_before_delegate(mode, stream, model):
    delegate = RecordingClient()
    client = BudgetedLiteLLMClient(delegate, ContextCompressionConfig(mode=mode))
    with pytest.raises(ContextBudgetError, match="model_capacity_required") as exc:
        client.completion(model=model, messages=[], stream=stream)
    assert delegate.calls == []
    assert "context_window" in str(exc.value) and "output_reserve" in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "off"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "model", ["openai/not-reviewed-capacity", "openai/ep-private-test"]
)
async def test_unknown_async_is_rejected_before_delegate(mode, stream, model):
    delegate = RecordingClient()
    client = BudgetedLiteLLMClient(delegate, ContextCompressionConfig(mode=mode))
    with pytest.raises(ContextBudgetError, match="model_capacity_required"):
        await client.acompletion(
            model=model, messages=[], stream=stream, fallbacks=["openai/gpt-4o"]
        )
    assert delegate.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "off"])
@pytest.mark.parametrize("stream", [False, True])
async def test_unknown_managed_model_rejected_before_adk(monkeypatch, mode, stream):
    calls = []

    async def generate(*args, **kwargs):
        calls.append(True)
        yield LlmResponse()

    monkeypatch.setattr(LiteLlm, "generate_content_async", generate)
    model = RetryingLiteLlm(
        model="openai/ep-private-test", context_compression={"mode": mode}
    )
    request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])]
    )
    before = request.model_dump()
    with pytest.raises(ContextBudgetError, match="model_capacity_required"):
        _ = [r async for r in model.generate_content_async(request, stream=stream)]
    assert calls == []
    assert request.model_dump() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "off"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("path", ["responses", "managed"])
async def test_unknown_ark_responses_rejected_before_transport(mode, stream, path):
    class Client(ArkLlmClient):
        def __init__(self):
            self.calls = []

        async def aresponses(self, **kwargs):
            self.calls.append(kwargs)
            raise RuntimeError("unexpected synthetic transport invocation")

    delegate = Client()
    model = ArkLlm(
        model="openai/ep-private-test",
        llm_client=delegate,
        context_compression={"mode": mode},
    )
    responses = (
        model.generate_content_via_responses(
            {"model": model.model, "input": []}, stream=stream
        )
        if path == "responses"
        else model.generate_content_async(
            LlmRequest(
                contents=[types.Content(role="user", parts=[types.Part(text="hello")])]
            ),
            stream=stream,
        )
    )
    with pytest.raises(ContextBudgetError, match="model_capacity_required"):
        _ = [r async for r in responses]
    assert delegate.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "off"])
async def test_private_deployment_with_explicit_capacity_can_send(mode):
    delegate = RecordingClient()
    client = BudgetedLiteLLMClient(
        delegate,
        ContextCompressionConfig(mode=mode, context_window=8000, output_reserve=1000),
    )
    client.completion(model="openai/ep-private-test", messages=[])
    await client.acompletion(model="openai/ep-private-test", messages=[])
    assert delegate.calls == ["openai/ep-private-test"] * 2


def test_capacity_error_does_not_echo_model_or_request():
    marker = "synthetic-sensitive-marker"
    with pytest.raises(ContextBudgetError) as exc:
        check_payload(
            {"model": marker, "messages": [{"content": marker}]},
            ContextCompressionConfig(),
        )
    assert exc.value.code == "model_capacity_required"
    assert marker not in str(exc.value)


def test_reviewed_table_has_complete_valid_provenance_and_budgets():
    from veadk.context.model_capacity import MODEL_CAPACITIES, get_model_capacity

    names = set()
    for row in MODEL_CAPACITIES:
        assert (row.provider, row.model_id) not in names
        names.add((row.provider, row.model_id))
        for value in (
            row.context_window,
            row.max_input_tokens,
            row.max_output_tokens,
            row.default_output_reserve,
        ):
            assert type(value) is int and value > 0
        assert row.max_input_tokens <= row.context_window
        assert row.max_output_tokens <= row.context_window
        assert row.default_output_reserve < row.context_window
        assert row.default_output_reserve <= row.max_output_tokens
        assert row.source.startswith("https://")
        assert date.fromisoformat(row.verified_on).isoformat() == row.verified_on
        for alias in (row.model_id, *row.aliases):
            for name in (alias, f"{row.provider}/{alias}"):
                assert get_model_capacity(name)["model_id"] == row.model_id
                assert get_model_capacity(name)["provider"] == row.provider
                budget = resolve_budget(name, ContextCompressionConfig())
                assert budget and 0 < budget.available <= row.max_input_tokens
            if row.provider == "volcengine":
                assert get_model_capacity("openai/" + alias)["model_id"] == row.model_id
        copy = get_model_capacity(row.model_id)
        copy["context_window"] = 1
        assert get_model_capacity(row.model_id)["context_window"] == row.context_window


def test_exact_seed_revisions_and_explicit_limits_cannot_expand_capacity():
    config = ContextCompressionConfig(context_window=2000000, input_limit=2000000)
    old = resolve_budget("openai/doubao-seed-2-1-pro-260628", config)
    new = resolve_budget("openai/doubao-seed-2-1-pro-260915", config)
    assert old and old.window == 256000
    assert new and new.window == 1024000
    limited = resolve_budget("openai/doubao-seed-2-0-lite-260428", config)
    assert limited and limited.available == 224000
    smaller = resolve_budget(
        "openai/doubao-seed-2-1-pro-260915",
        ContextCompressionConfig(context_window=64000),
    )
    assert smaller and smaller.window == 64000


@pytest.mark.parametrize(
    "name",
    [
        "doubao-seed-2-1-pro-new",
        "doubao-seed-2-1-pro",
        "ep-private-test",
        "anthropic/doubao-seed-2-1-pro-260628",
        "azure/doubao-seed-2-1-pro-260628",
        "openai/volcengine/doubao-seed-2-1-pro-260628",
        "openai/claude-fable-5-1",
        "deepseek/deepseek-v4-1-flash-260910",
        "volcengine/gpt-6-astra",
    ],
)
def test_no_family_guess_or_cross_provider_lookup(monkeypatch, name):
    monkeypatch.setattr("veadk.context.budget._catalogue", lambda: {})
    assert model_limits(name) == {}


def test_reviewed_table_precedes_outdated_installed_catalogue(monkeypatch):
    monkeypatch.setattr(
        "veadk.context.budget._catalogue",
        lambda: {"openai/doubao-seed-2-1-pro-260915": {"max_input_tokens": 256000}},
    )
    assert (
        model_limits("openai/doubao-seed-2-1-pro-260915")["context_window"] == 1024000
    )


def test_installed_catalogue_exact_match_and_provider_boundary(monkeypatch):
    monkeypatch.setattr(
        "veadk.context.budget._catalogue",
        lambda: {
            "catalogue-model": {
                "max_input_tokens": 8000,
                "max_output_tokens": 1000,
                "litellm_provider": "anthropic",
            },
            "openai/catalogue-model": {"max_input_tokens": True},
            "volcengine/catalogue-ark": {
                "max_input_tokens": 8000,
                "max_output_tokens": 1000,
                "litellm_provider": "volcengine",
            },
        },
    )
    assert model_limits("openai/catalogue-model") == {}
    assert model_limits("openai/catalogue-ark")["max_input_tokens"] == 8000
    assert model_limits("catalogue-ark-larger") == {}


def test_ark_answer_and_total_output_semantics_are_version_specific():
    seed = {
        "model": "openai/doubao-seed-2-1-pro-260915",
        "messages": [],
        "max_tokens": 8192,
    }
    flash = {**seed, "model": "openai/deepseek-v4-1-flash-260910"}
    config = ContextCompressionConfig()
    assert check_payload(seed, config).output == 8192 + 12288
    assert check_payload(flash, config).output == 8192
    seed["extra_body"] = {"thinking": {"type": "disabled"}}
    assert check_payload(seed, config).output == 8192


@pytest.mark.parametrize("contents", ["not json", "[]", "null"])
def test_invalid_installed_catalogue_still_gives_actionable_error(
    monkeypatch, tmp_path, contents
):
    from types import SimpleNamespace
    from veadk.context.budget import _catalogue

    path = tmp_path / "model_prices_and_context_window_backup.json"
    path.write_text(contents)
    monkeypatch.setattr(
        "veadk.context.budget.find_spec",
        lambda _: SimpleNamespace(origin=str(tmp_path / "__init__.py")),
    )
    _catalogue.cache_clear()
    try:
        with pytest.raises(ContextBudgetError, match="model_capacity_required"):
            check_payload(
                {"model": "openai/ep-private-test", "messages": []},
                ContextCompressionConfig(),
            )
    finally:
        _catalogue.cache_clear()


def test_direct_agent_uses_reviewed_flash_capacity_without_manual_window():
    from veadk import Agent

    # Pydantic's before-validator accepts dictionaries at this public boundary.
    policy: dict[str, Any] = {
        "context_compression": {"input_limit": 80000, "output_reserve": 8192}
    }
    agent = Agent(
        name="assistant",
        model_name="deepseek-v4-1-flash-260910",
        model_provider="openai",
        model_api_base="https://ark.cn-beijing.volces.com/api/v3",
        model_api_key="synthetic-offline",
        model_extra_config={
            "max_tokens": 8192,
            "extra_body": {"thinking": {"type": "disabled"}},
        },
        **policy,
    )
    state = agent.context_compression_status
    assert state["state"] == "configured" and state["mode"] == "auto"
    assert state["context_window"] == 1024000
    assert state["input_budget"] == 80000 and state["output_reserve"] == 8192
