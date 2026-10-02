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

"""All Studio creation paths must retain defaults and threshold validation."""

import pytest
from pydantic import ValidationError

from veadk.cli.generated_agent_codegen import AgentDraft, StudioContextCompressionConfig


def test_missing_policy_defaults_for_root_and_recursive_children():
    root = AgentDraft(
        name="root",
        subAgents=[{"name": "child", "subAgents": [{"name": "grandchild"}]}],
    )
    child = root.subAgents[0]
    assert all(
        node.contextCompression.mode == "auto"
        for node in (root, child, child.subAgents[0])
    )


def test_all_thresholds_round_trip_in_studio_policy():
    policy = {
        "mode": "auto",
        "context_window": 64000,
        "input_limit": 48000,
        "output_reserve": 8000,
        "trigger_ratio": 0.75,
        "summary_trigger_ratio": 0.9,
        "target_ratio": 0.5,
    }
    assert (
        StudioContextCompressionConfig(**policy).model_dump(exclude_none=True) == policy
    )


@pytest.mark.parametrize(
    "policy",
    [
        {"target_ratio": 0.9},
        {"trigger_ratio": 0.99},
        {"trigger_ratio": 0},
        {"target_ratio": True},
        {"trigger_ratio": "0.8"},
    ],
)
def test_invalid_thresholds_rejected_before_code_generation(policy):
    with pytest.raises(ValidationError):
        StudioContextCompressionConfig(**policy)


@pytest.mark.asyncio
async def test_agentkit_app_default_sqlite_survives_recreation(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from veadk.memory.short_term_memory import ShortTermMemory
    import veadk.integrations.agentkit.app as integration
    from veadk import Agent

    monkeypatch.chdir(tmp_path)
    memories = []

    class Server:
        def __init__(self, **kwargs):
            memory = kwargs["short_term_memory"]
            assert isinstance(memory, ShortTermMemory)
            memories.append(memory)
            self.app = FastAPI()

    monkeypatch.setattr(integration, "AgentkitAgentServerApp", Server)
    owner = Agent(name="default_app", model_api_key="offline-test")
    who = dict(app_name="default_app", user_id="u", session_id="s")
    integration.create_agentkit_app(owner)
    try:
        await memories[-1].session_service.create_session(
            **who, state={"checkpoint": "preserved"}
        )
    finally:
        await memories[-1].session_service.close()
    integration.create_agentkit_app(owner)
    try:
        restored = await memories[-1].session_service.get_session(**who)
        assert restored is not None and restored.state["checkpoint"] == "preserved"
    finally:
        await memories[-1].session_service.close()
