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

"""Agent policy inheritance and legacy ownership must be explicit."""

import pytest
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions import Session
from pydantic import ValidationError

from veadk import Agent
from veadk.context.budget import ContextBudgetError
from veadk.context.runtime import ContextScope, current_scope
from veadk.extensions.harness.plugins.compactor import HarnessCompressPlugin
from veadk.models.retrying_lite_llm import RetryingLiteLlm


def configured_model():
    return RetryingLiteLlm(
        model="openai/context-test",
        context_compression={
            "context_window": 10000,
            "output_reserve": 1000,
        },
    )


def test_agent_inherits_policy_of_supplied_supported_model():
    model = configured_model()
    agent = Agent(name="test", model=model)
    assert agent.context_compression == model._context_config
    assert agent.context_compression_status["state"] == "configured"
    assert agent.context_compression_status["input_budget"] == 7976


@pytest.mark.parametrize("mode", ["auto", "off"])
def test_explicit_none_inherits_model_policy_without_claiming_ownership(mode):
    model = configured_model().with_context_compression({"mode": mode})
    agent = Agent(name="inherited", model=model, context_compression=None)
    assert agent.model is model
    assert agent.context_compression == model._context_config
    assert "context_compression" not in agent._veadk_explicit_fields


def test_explicit_none_accepts_unsupported_adapter_as_inherited_policy():
    model = LiteLlm(model="openai/unknown-context-model")
    agent = Agent(name="custom", model=model, context_compression=None)
    assert agent.model is model
    assert agent.context_compression_status["state"] == "unsupported_model_adapter"


def test_clone_policy_update_changes_transport_without_mutating_original():
    original = Agent(name="original", model=configured_model())
    clone = original.clone(update={"name": "disabled", "context_compression": False})
    assert clone.context_compression_status["mode"] == "off"
    assert clone.model.llm_client.config.mode == "off"
    assert original.context_compression_status["mode"] == "auto"
    assert clone.model is not original.model


def test_switching_model_drops_capacity_bound_to_the_previous_model():
    original = Agent(name="original", model=configured_model())
    clone = original.clone(update={"name": "changed"})
    clone.update_model("unknown-other-context-model")
    assert clone.context_compression_status["state"] == "needs_configuration"
    assert clone.context_compression.context_window is None
    assert original.context_compression_status["input_budget"] == 7976


def test_default_agent_has_verified_capacity_without_manual_configuration():
    agent = Agent(name="default_capacity")
    assert agent.context_compression_status["state"] == "configured"
    assert agent.context_compression_status["context_window"] == 256000
    assert agent.context_compression_status["output_reserve"] == 16384


def test_clone_with_a_new_model_keeps_that_models_capacity():
    original = Agent(
        name="original", model=configured_model(), context_compression=True
    )
    new_model = configured_model().with_context_compression({"context_window": 6000})
    clone = original.clone(update={"name": "other", "model": new_model})
    assert clone.context_compression_status["context_window"] == 6000
    assert original.context_compression_status["context_window"] == 10000


def test_updating_to_same_model_preserves_explicit_capacity():
    agent = Agent(name="original", model=configured_model())
    agent.update_model("context-test")
    assert agent.context_compression_status["context_window"] == 10000


def test_policy_merge_revalidates_cross_field_invariants():
    model = configured_model().with_context_compression({"trigger_ratio": 0.7})
    with pytest.raises(ValidationError, match="target_ratio must be below"):
        model.with_context_compression({"target_ratio": 0.75})
    with pytest.raises(
        ValidationError, match="summary_trigger_ratio must not be below"
    ):
        model.with_context_compression({"summary_trigger_ratio": 0.65})


def test_explicit_off_copies_custom_model_without_mutating_other_agents():
    model = configured_model()
    original = Agent(name="original", model=model)
    disabled = Agent(name="disabled", model=model, context_compression=False)
    assert original.model is model
    assert disabled.model is not model
    assert original.context_compression_status["mode"] == "auto"
    assert disabled.context_compression_status["mode"] == "off"
    assert (
        disabled.context_compression_status["input_budget"]
        == original.context_compression_status["input_budget"]
    )
    assert disabled.model.llm_client.config.mode == "off"


def test_unknown_model_reports_capacity_gap_instead_of_claiming_protection():
    agent = Agent(
        name="unknown", model=RetryingLiteLlm(model="openai/unknown-context-model")
    )
    assert agent.context_compression_status == {
        "state": "needs_configuration",
        "mode": "auto",
        "reason": "model_capacity_required",
    }


def test_unsupported_custom_model_rejects_explicit_compression():
    with pytest.raises(ValidationError, match="unsupported_model_adapter") as error:
        Agent(
            name="custom",
            model=LiteLlm(model="openai/unknown-context-model"),
            context_compression=True,
        )
    assert error.value.errors()[0]["ctx"]["error"].code == "unsupported_model_adapter"


@pytest.mark.asyncio
async def test_legacy_plugin_conflict_is_detected_before_modifying_input():
    scope = ContextScope(
        session=Session(id="s", user_id="u", app_name="a"),
        agent_name="agent",
        branch="",
        compression_owner="builtin",
    )
    token = current_scope.set(scope)
    request = LlmRequest()
    try:
        with pytest.raises(
            ContextBudgetError, match="multiple_context_compression_owners"
        ):
            await HarnessCompressPlugin().before_model_callback(
                callback_context=None, llm_request=request
            )
        assert request.contents == []
    finally:
        current_scope.reset(token)


@pytest.mark.asyncio
async def test_explicit_legacy_plugin_owns_inherited_sdk_compression():
    scope = ContextScope(
        session=Session(id="s", user_id="u", app_name="a"),
        agent_name="agent",
        branch="",
    )
    token = current_scope.set(scope)
    try:
        await HarnessCompressPlugin().before_model_callback(
            callback_context=None, llm_request=LlmRequest()
        )
        assert scope.compression_owner == "legacy_harness"
    finally:
        current_scope.reset(token)
