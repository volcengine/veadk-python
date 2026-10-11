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

"""Studio policies must reach the generated SDK Agent without side effects."""

import ast

import pytest
from pydantic import ValidationError

from veadk.cli.generated_agent_codegen import AgentDraft, generate_project_from_draft
from veadk.cli.generated_agent_planner import (
    DEFAULT_GENERATED_MODEL_NAME,
    GeneratedAgentPlan,
    _to_agent_draft,
)


def generated_calls(draft):
    project = generate_project_from_draft(draft)
    source = next(f.content for f in project.files if f.path.endswith("/agent.py"))
    tree = ast.parse(source)
    compile(tree, "generated_agent.py", "exec")
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id in {"Agent", "SequentialAgent", "ParallelAgent", "LoopAgent"}
    ]


def compression(call):
    return ast.literal_eval(
        next(k.value for k in call.keywords if k.arg == "context_compression")
    )


def test_missing_codegen_policy_enables_compression():
    (call,) = generated_calls(AgentDraft(name="legacy"))
    assert compression(call) == {"mode": "auto"}


def test_generated_project_pins_the_sdk_that_supplies_its_context_api():
    from importlib.metadata import version

    project = generate_project_from_draft(AgentDraft(name="version_contract"))
    requirements = next(
        f.content for f in project.files if f.path == "requirements.txt"
    )
    assert f"veadk-python=={version('veadk-python')}\n" in requirements


def test_generated_default_agent_module_starts_with_candidate_sdk(
    tmp_path, monkeypatch
):
    import runpy

    project = generate_project_from_draft(
        AgentDraft.model_validate(
            {
                "name": "startup_contract",
                "contextCompression": {"mode": "auto"},
            }
        )
    )
    for file in project.files:
        path = tmp_path / file.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file.content)
    source = next(
        tmp_path / file.path
        for file in project.files
        if file.path.endswith("/agent.py")
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    namespace = runpy.run_path(str(source))
    agent = namespace["root_agent"]
    assert agent.context_compression.mode == "auto"
    assert agent.context_compression_status["state"] == "configured"


def test_codegen_preserves_recursive_policies_and_sdk_accepts_them():
    from veadk import Agent

    policy = {
        "mode": "auto",
        "context_window": 32000,
        "output_reserve": 4000,
        "trigger_ratio": 0.75,
        "target_ratio": 0.5,
        "summary_trigger_ratio": 0.9,
    }
    draft = AgentDraft.model_validate(
        {
            "name": "root",
            "agentType": "sequential",
            "subAgents": [
                {"name": "first", "contextCompression": policy},
                {"name": "second", "contextCompression": {"mode": "off"}},
            ],
        }
    )
    calls = generated_calls(draft)
    llms = [call for call in calls if call.func.id == "Agent"]
    assert [compression(call) for call in llms] == [policy, {"mode": "off"}]
    assert not any(
        k.arg == "context_compression"
        for call in calls
        if call.func.id != "Agent"
        for k in call.keywords
    )
    for call in llms:
        agent = Agent(name="generated", context_compression=compression(call))
        assert agent.context_compression.mode == compression(call)["mode"]


@pytest.mark.parametrize(
    "policy",
    [
        None,
        "auto",
        {"mode": "bad"},
        {"context_window": -1},
        {"context_window": True},
        {"context_window": "32000"},
        {"unknown": 1},
    ],
)
def test_invalid_studio_policy_is_rejected(policy):
    with pytest.raises(ValidationError):
        AgentDraft.model_validate({"contextCompression": policy})


def test_intelligent_creation_explicitly_enables_auto():
    plan = GeneratedAgentPlan.model_validate(
        {
            "name": "planned",
            "description": "test",
            "instruction": "test",
            "agentType": "llm",
            "maxIterations": 3,
            "modelName": DEFAULT_GENERATED_MODEL_NAME,
            "builtinTools": [],
            "customTools": [],
            "subAgents": [],
        }
    )
    assert _to_agent_draft(plan).contextCompression.mode == "auto"


def test_runtime_graph_reports_capacity_without_protected_content():
    import json

    from veadk import Agent
    from veadk.integrations.agentkit.app import _agent_node

    child = Agent(name="unknown", model_name="unknown-context-model")
    root = Agent(
        name="root",
        sub_agents=[child],
        context_compression={
            "context_window": 32000,
            "output_reserve": 4000,
            "protected_context": ["SYNTHETIC_PRIVATE_CONSTRAINT"],
        },
    )
    node = _agent_node(root, {})
    assert node["contextCompression"]["state"] == "configured"
    assert node["contextCompression"]["input_budget"] == 26976
    assert node["children"][0]["contextCompression"]["state"] == "needs_configuration"
    assert "SYNTHETIC_PRIVATE_CONSTRAINT" not in json.dumps(node)
