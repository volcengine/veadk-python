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

"""Capability metadata must describe the runtime that actually calls the model."""

import pytest

from veadk import Agent
from veadk.context import ContextCompressionConfig
from veadk.context.status import agent_context_metadata


@pytest.mark.parametrize("runtime", ["codex", "piagent"])
@pytest.mark.parametrize("policy", [None, True, False])
def test_external_runtime_never_advertises_unused_sdk_budget(runtime, policy):
    agent = Agent(name="external", runtime=runtime, context_compression=policy)
    assert agent.context_compression_status == {
        "state": "unsupported_runtime",
        "mode": "off",
        "reason": "runtime_owns_model_loop",
    }
    assert agent_context_metadata(agent) == {
        "contextCompression": agent.context_compression_status,
    }
    # Reporting effective capability must not mutate the requested policy.
    assert isinstance(agent.context_compression, ContextCompressionConfig)
    assert agent.context_compression.mode == ("off" if policy is False else "auto")


def test_cloning_between_runtimes_recomputes_effective_capability():
    original = Agent(name="original")
    external = original.clone(update={"name": "external", "runtime": "piagent"})
    restored = external.clone(update={"name": "restored", "runtime": "adk"})
    assert original.context_compression_status["state"] == "configured"
    assert external.context_compression_status["state"] == "unsupported_runtime"
    assert restored.context_compression_status == original.context_compression_status
    assert isinstance(original.context_compression, ContextCompressionConfig)
    assert isinstance(external.context_compression, ContextCompressionConfig)
    assert (
        original.context_compression.mode == external.context_compression.mode == "auto"
    )


def test_studio_topology_reports_each_child_runtime_without_budget_claims():
    from veadk.integrations.agentkit.app import _agent_node

    root = Agent(
        name="root",
        sub_agents=[Agent(name="external", runtime="piagent")],
    )
    info = _agent_node(root, {})
    assert info["contextCompression"]["state"] == "configured"
    child = info["children"][0]["contextCompression"]
    assert child["state"] == "unsupported_runtime"
    assert "input_budget" not in child
    assert "context_window" not in child
