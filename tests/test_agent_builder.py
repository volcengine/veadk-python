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

"""Unit tests for :mod:`veadk.agent_builder`.

These exercise the YAML config reader and the recursive ``_build`` dispatch
(type lookup, dotted-path tool import, and sub-agent recursion) using a fake
agent class registered into ``AGENT_TYPES``. No real ``Agent`` is instantiated,
so there is no model or network access.
"""

from __future__ import annotations

import textwrap
from typing import Any, cast

import pytest

from veadk import agent_builder
from veadk.agent_builder import AGENT_TYPES, AgentBuilder

# A module-level callable used to verify dotted-path tool resolution in ``_build``.
SENTINEL_TOOL_CALLS = []


def sample_tool() -> str:
    """A trivial tool resolved by its dotted import path during tests."""
    return "tool-result"


class _FakeAgent:
    """Records the kwargs ``_build`` passes to the resolved agent class."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs: dict[str, Any] = kwargs
        # Mirror the fields the tests assert on for convenience.
        self.sub_agents: list[Any] = kwargs.get("sub_agents", [])
        self.tools: list[Any] = kwargs.get("tools", [])
        self.name: Any = kwargs.get("name")


@pytest.fixture
def fake_agent_types(monkeypatch):
    """Register ``FakeAgent`` so ``_build`` constructs it instead of a real Agent."""
    monkeypatch.setitem(AGENT_TYPES, "FakeAgent", _FakeAgent)
    return _FakeAgent


def test_agent_types_registry_contents():
    """The registry maps the documented type names to classes."""
    assert set(AGENT_TYPES) == {
        "Agent",
        "SequentialAgent",
        "ParallelAgent",
        "LoopAgent",
        "RemoteVeAgent",
    }


def test_read_config_rejects_non_yaml(tmp_path):
    """Only ``.yaml`` config files are accepted."""
    bad = tmp_path / "config.json"
    bad.write_text("{}")

    with pytest.raises(AssertionError, match="must be a `.yaml` file"):
        AgentBuilder()._read_config(str(bad))


def test_read_config_parses_yaml_to_dict(tmp_path):
    """A well-formed YAML file parses into a plain dict."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            root_agent:
              type: FakeAgent
              name: root
            """
        )
    )

    result = AgentBuilder()._read_config(str(cfg))

    assert isinstance(result, dict)
    assert result["root_agent"]["type"] == "FakeAgent"
    assert result["root_agent"]["name"] == "root"


def test_build_constructs_registered_type(fake_agent_types):
    """``_build`` looks up the class by ``type`` and forwards remaining config."""
    agent = AgentBuilder()._build({"type": "FakeAgent", "name": "leaf"})

    assert isinstance(agent, _FakeAgent)
    assert agent.name == "leaf"
    # ``_build`` always supplies sub_agents and tools, defaulting to empty lists.
    assert agent.sub_agents == []
    assert agent.tools == []


def test_build_unknown_type_raises_keyerror(fake_agent_types):
    """An unregistered ``type`` surfaces a KeyError from the registry lookup."""
    with pytest.raises(KeyError):
        AgentBuilder()._build({"type": "DoesNotExist"})


def test_build_resolves_tools_by_dotted_path(fake_agent_types):
    """Tool entries are imported by ``module.func`` and passed as callables."""
    config = {
        "type": "FakeAgent",
        "name": "with_tools",
        "tools": [{"name": "tests.test_agent_builder.sample_tool"}],
    }

    agent = cast(_FakeAgent, AgentBuilder()._build(config))

    assert len(agent.tools) == 1
    resolved = agent.tools[0]
    assert callable(resolved)
    assert resolved.__name__ == "sample_tool"
    # The resolved callable is a genuine, invokable function.
    assert resolved() == "tool-result"


def test_build_recurses_into_sub_agents(fake_agent_types):
    """Nested ``sub_agents`` are built recursively and attached to the parent."""
    config = {
        "type": "FakeAgent",
        "name": "parent",
        "sub_agents": [
            {"type": "FakeAgent", "name": "child_a"},
            {"type": "FakeAgent", "name": "child_b"},
        ],
    }

    agent = AgentBuilder()._build(config)

    assert [c.name for c in agent.sub_agents] == ["child_a", "child_b"]
    assert all(isinstance(c, _FakeAgent) for c in agent.sub_agents)


def test_build_pops_sub_agents_and_tools_from_config(fake_agent_types):
    """``_build`` consumes ``sub_agents``/``tools`` so they are not re-passed."""
    config = {
        "type": "FakeAgent",
        "name": "p",
        "sub_agents": [{"type": "FakeAgent", "name": "c"}],
        "tools": [{"name": "tests.test_agent_builder.sample_tool"}],
    }

    agent = cast(_FakeAgent, AgentBuilder()._build(config))

    # The raw config dict had its consumed keys removed in place.
    assert "sub_agents" not in config
    assert "tools" not in config
    # And they were re-supplied to the constructor as kwargs.
    assert "sub_agents" in agent.kwargs
    assert "tools" in agent.kwargs
    assert len(agent.sub_agents) == 1
    assert len(agent.tools) == 1


def test_build_entrypoint_reads_config_and_dispatches(tmp_path, fake_agent_types):
    """``build`` reads the file then builds the agent under ``root_agent_identifier``."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            root_agent:
              type: FakeAgent
              name: top
            """
        )
    )

    agent = AgentBuilder().build(str(cfg))

    assert isinstance(agent, _FakeAgent)
    assert agent.name == "top"


def test_build_entrypoint_honours_custom_identifier(tmp_path, fake_agent_types):
    """A non-default ``root_agent_identifier`` selects a different top-level key."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent(
            """
            my_root:
              type: FakeAgent
              name: custom
            """
        )
    )

    agent = AgentBuilder().build(str(cfg), root_agent_identifier="my_root")

    assert agent.name == "custom"


def test_build_entrypoint_missing_identifier_raises(tmp_path, fake_agent_types):
    """A missing root identifier surfaces a KeyError."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("other_agent:\n  type: FakeAgent\n")

    with pytest.raises(KeyError):
        AgentBuilder().build(str(cfg))


def test_module_logger_present():
    """The module exposes a configured logger (contract check)."""
    assert agent_builder.logger is not None
