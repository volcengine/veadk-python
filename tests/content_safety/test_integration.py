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

from pathlib import Path

import pytest
from google.adk.apps import App
from google.adk.plugins import BasePlugin

from veadk import Agent, Runner
from veadk.content_safety import (
    DEFAULT_QUESTION_INSTRUCTIONS,
    ContentSafetyConfig,
    ContentSafetyConfigError,
    load_content_safety_config_if_present,
    resolve_content_safety_plugin,
    resolve_content_safety_plugins,
)
from veadk.content_safety.types import Provider

DECISION_BLOCK = """
tool:
  content_safety:
    provider: decision
    decision:
      api_url: https://systemone.example/v1/judge
      api_key: test-key
    questions:
      prompt_injection:
        instructions: test instructions
        threshold: 0.5
"""


def write_config(tmp_path: Path, text: str) -> None:
    (tmp_path / "config.yaml").write_text(text, encoding="utf-8")


def make_agent(**kwargs) -> Agent:
    return Agent(
        name=kwargs.pop("name", "content_safety_test"),
        instruction="test",
        model_api_key="test-model-key",
        **kwargs,
    )


class MarkerPlugin(BasePlugin):
    def __init__(self):
        super().__init__(name="marker")


@pytest.fixture
def decision_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_config(tmp_path, DECISION_BLOCK)
    return tmp_path


class TestOptionalLoader:
    def test_returns_none_without_config_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert load_content_safety_config_if_present() is None

    def test_returns_none_without_content_safety_block(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_config(tmp_path, "model:\n  name: test\n")
        assert load_content_safety_config_if_present() is None

    def test_loads_configured_block(self, decision_cwd):
        config = load_content_safety_config_if_present()
        assert config is not None
        assert config.provider is Provider.DECISION
        assert config.decision.api_url == "https://systemone.example/v1/judge"

    def test_omitted_questions_use_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_config(
            tmp_path,
            """
tool:
  content_safety:
    provider: decision
    decision:
      api_url: https://systemone.example/v1/judge
      api_key: test-key
""",
        )
        plugin = resolve_content_safety_plugin()
        assert plugin is not None
        assert len(plugin._config.questions) == len(DEFAULT_QUESTION_INSTRUCTIONS)

    def test_invalid_block_still_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_config(
            tmp_path,
            """
tool:
  content_safety:
    provider: decision
    use_default_questions: false
""",
        )
        with pytest.raises(ContentSafetyConfigError, match="invalid `content_safety`"):
            load_content_safety_config_if_present()


class TestResolvePlugin:
    def test_no_config_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert resolve_content_safety_plugin() is None

    def test_provider_none_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_config(tmp_path, "tool:\n  content_safety:\n    provider: none\n")
        assert resolve_content_safety_plugin() is None

    def test_config_yaml_builds_plugin(self, decision_cwd):
        plugin = resolve_content_safety_plugin()
        assert plugin is not None
        assert plugin.name == "content_safety_decision"

    def test_existing_plugin_is_not_duplicated(self, decision_cwd):
        first = resolve_content_safety_plugins()
        merged = resolve_content_safety_plugins(existing=first)
        assert merged == first

    def test_existing_unrelated_plugin_is_preserved(self, decision_cwd):
        marker = MarkerPlugin()
        merged = resolve_content_safety_plugins(existing=[marker])
        assert merged[0] is marker
        assert [plugin.name for plugin in merged] == [
            "marker",
            "content_safety_decision",
        ]

    def test_agent_false_disables_yaml_config(self, decision_cwd):
        agent = make_agent(content_safety=False)
        assert resolve_content_safety_plugin(agent) is None

    def test_agent_true_requires_yaml_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = make_agent(content_safety=True)
        with pytest.raises(ContentSafetyConfigError, match="content_safety=True"):
            resolve_content_safety_plugin(agent)

    def test_agent_mapping_overrides_yaml(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = ContentSafetyConfig.from_dict(
            {
                "provider": "decision",
                "decision": {
                    "api_url": "https://inline.example/v1/judge",
                    "api_key": "inline-key",
                },
                "questions": {
                    "prompt_injection": {
                        "instructions": "inline instructions",
                        "threshold": 0.5,
                    }
                },
            }
        )
        agent = make_agent(content_safety=config)
        plugin = resolve_content_safety_plugin(agent)
        assert plugin is not None
        assert plugin.name == "content_safety_decision"

    def test_agent_invalid_type_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = make_agent(content_safety="yes")
        with pytest.raises(TypeError, match="content_safety must be"):
            resolve_content_safety_plugin(agent)

    def test_agent_property_matches_resolver(self, decision_cwd):
        agent = make_agent()
        plugins = agent.content_safety_plugins
        assert [plugin.name for plugin in plugins] == ["content_safety_decision"]


class TestRunnerIntegration:
    def test_runner_mounts_configured_plugin(self, decision_cwd):
        agent = make_agent()
        runner = Runner(agent=agent, app_name="content_safety_runner")
        assert [plugin.name for plugin in runner.plugin_manager.plugins] == [
            "content_safety_decision"
        ]

    def test_runner_keeps_explicit_plugins(self, decision_cwd):
        marker = MarkerPlugin()
        agent = make_agent()
        runner = Runner(
            agent=agent,
            app_name="content_safety_runner",
            plugins=[marker],
        )
        names = [plugin.name for plugin in runner.plugin_manager.plugins]
        assert names == ["marker", "content_safety_decision"]

    def test_runner_without_config_keeps_no_plugins(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = make_agent()
        runner = Runner(agent=agent, app_name="content_safety_runner")
        assert runner.plugin_manager.plugins == []

    def test_runner_agent_false_disables_yaml_config(self, decision_cwd):
        agent = make_agent(content_safety=False)
        runner = Runner(agent=agent, app_name="content_safety_runner")
        assert runner.plugin_manager.plugins == []

    def test_runner_extends_existing_app(self, decision_cwd):
        agent = make_agent()
        app = App(name="content_safety_app", root_agent=agent)
        runner = Runner(app=app)
        assert [plugin.name for plugin in runner.plugin_manager.plugins] == [
            "content_safety_decision"
        ]

    def test_runner_app_does_not_duplicate_plugin(self, decision_cwd):
        agent = make_agent()
        plugin = resolve_content_safety_plugin(agent)
        assert plugin is not None
        app = App(name="content_safety_app", root_agent=agent, plugins=[plugin])
        runner = Runner(app=app)
        assert [p.name for p in runner.plugin_manager.plugins] == [
            "content_safety_decision"
        ]
