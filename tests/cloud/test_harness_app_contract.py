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

"""Contract tests for the Harness server schemas (``veadk.cloud.harness_app``).

These pin the per-invocation override schema, the full creation-time config, and
the HTTP request/response models so that a change to a field name, default, or
the overridable/fixed split silently breaking the deployed server (or the
``veadk harness`` CLI, whose flags are generated from these fields) is caught
here rather than in production.

Only ``types`` and ``utils`` are imported: ``app.py`` builds the live agent at
import time, so it is intentionally left out to keep these tests offline.
"""

from pathlib import Path

from veadk.cloud.harness_app.types import (
    HarnessConfig,
    HarnessOverrides,
    InvokeHarnessRequest,
    InvokeHarnessResponse,
    RunAgentRequest,
)
from veadk.cloud.harness_app.env_mapping import to_runtime_env
from veadk.cloud.harness_app.utils import config_from_env, split_csv
from veadk.consts import DEFAULT_MODEL_AGENT_NAME
from veadk.prompts.agent_default_prompt import DEFAULT_INSTRUCTION


def _fields(model) -> dict:
    """Map of pydantic field name -> FieldInfo for ``model``."""
    return dict(model.model_fields)


class TestHarnessOverrides:
    def test_fields(self):
        assert set(_fields(HarnessOverrides)) == {
            "model_name",
            "tools",
            "skills",
            "system_prompt",
            "runtime",
            "registry_space_id",
            "registry_endpoint",
            "registry_region",
            "registry_top_k",
        }

    def test_defaults(self):
        fields = _fields(HarnessOverrides)
        assert fields["model_name"].default == DEFAULT_MODEL_AGENT_NAME
        assert fields["tools"].default == ""
        assert fields["skills"].default == ""
        assert fields["system_prompt"].default == "You are a helpful assistant."
        assert fields["runtime"].default == "adk"
        assert fields["registry_space_id"].default == ""
        assert fields["registry_endpoint"].default == ""
        assert fields["registry_region"].default == ""
        assert fields["registry_top_k"].default == 3

    def test_tools_and_skills_are_csv_strings(self):
        # The server splits these with split_csv(); they must stay plain strings,
        # not lists, to keep the CLI/curl pass-through contract.
        h = HarnessOverrides()
        assert isinstance(h.tools, str)
        assert isinstance(h.skills, str)

    def test_every_field_has_a_description(self):
        # Descriptions are the single source of truth for the generated
        # `veadk harness invoke` flags, so each field must carry one.
        for name, field in _fields(HarnessOverrides).items():
            assert field.description, f"{name} is missing a description"


class TestHarnessConfig:
    def test_extends_overrides(self):
        assert issubclass(HarnessConfig, HarnessOverrides)

    def test_adds_creation_time_fields(self):
        assert set(_fields(HarnessConfig)) == set(_fields(HarnessOverrides)) | {
            "app_name",
            "description",
            "knowledgebase_type",
            "longterm_memory_type",
            "shortterm_memory_type",
            "max_llm_calls",
            "structured_tool_calls",
            "include_tools_every_turn",
            "registry_type",
            "registry_version",
            "registry_service_name",
            "registry_timeout_ms",
            "registry_poll_interval_ms",
        }

    def test_component_defaults(self):
        fields = _fields(HarnessConfig)
        # Empty backend = component disabled; short-term memory defaults to local.
        assert fields["knowledgebase_type"].default == ""
        assert fields["longterm_memory_type"].default == ""
        assert fields["shortterm_memory_type"].default == "local"
        assert fields["structured_tool_calls"].default is False
        assert fields["include_tools_every_turn"].default is True
        assert fields["registry_type"].default == ""
        assert fields["registry_top_k"].default == 3
        assert fields["registry_timeout_ms"].default == 60000
        assert fields["registry_poll_interval_ms"].default == 5000

    def test_system_prompt_default_is_veadk_instruction(self):
        # HarnessConfig overrides the override-layer default with VeADK's own.
        assert _fields(HarnessConfig)["system_prompt"].default == DEFAULT_INSTRUCTION

    def test_app_name_populated_via_name_alias(self):
        assert HarnessConfig(name="research-agent").app_name == "research-agent"
        assert HarnessConfig().app_name == "harness_app"

    def test_registry_yaml_maps_to_runtime_env(self):
        envs = to_runtime_env(
            {
                "registry": {
                    "type": "agentkit_a2a",
                    "space_id": "space-test",
                    "top_k": 5,
                    "region": "cn-beijing",
                }
            }
        )

        assert envs["REGISTRY_TYPE"] == "agentkit_a2a"
        assert envs["REGISTRY_SPACE_ID"] == "space-test"
        assert envs["REGISTRY_TOP_K"] == "5"
        assert envs["REGISTRY_REGION"] == "cn-beijing"

    def test_tool_calling_yaml_maps_to_runtime_env(self):
        envs = to_runtime_env(
            {
                "structured_tool_calls": True,
                "include_tools_every_turn": True,
            }
        )

        assert envs["STRUCTURED_TOOL_CALLS"] == "true"
        assert envs["INCLUDE_TOOLS_EVERY_TURN"] == "true"

    def test_config_from_env_reads_registry_fields(self, monkeypatch):
        monkeypatch.setenv("REGISTRY_TYPE", "agentkit_a2a")
        monkeypatch.setenv("REGISTRY_SPACE_ID", "space-test")
        monkeypatch.setenv("REGISTRY_TOP_K", "5")
        monkeypatch.setenv("REGISTRY_REGION", "cn-beijing")

        config = config_from_env()

        assert config.registry_type == "agentkit_a2a"
        assert config.registry_space_id == "space-test"
        assert config.registry_top_k == 5
        assert config.registry_region == "cn-beijing"

    def test_config_from_env_reads_tool_calling_fields(self, monkeypatch):
        monkeypatch.setenv("STRUCTURED_TOOL_CALLS", "true")
        monkeypatch.setenv("INCLUDE_TOOLS_EVERY_TURN", "false")

        config = config_from_env()

        assert config.structured_tool_calls is True
        assert config.include_tools_every_turn is False

    def test_registry_overrides_remount_registry_tools(self):
        source = Path("veadk/cloud/harness_app/utils.py").read_text()

        assert "_apply_registry_overrides(" in source
        assert "_remove_a2a_registry_tools(" in source
        assert "build_a2a_registry_tools(overridden_config)" in source

    def test_registry_dynamic_tools_are_added_per_run(self):
        utils_source = Path("veadk/cloud/harness_app/utils.py").read_text()
        app_source = Path("veadk/cloud/harness_app/app.py").read_text()

        assert "build_remote_a2a_agent_tools(prompt, registry_config)" in utils_source
        assert "def spawn_harness_run_agent(" in utils_source
        assert "has_a2a_registry_config(self.agent)" in app_source
        assert "spawn_harness_run_agent(" in app_source


class TestRequestResponseSchemas:
    def test_run_agent_request_fields(self):
        assert set(_fields(RunAgentRequest)) == {
            "user_id",
            "session_id",
            "max_llm_calls",
        }

    def test_invoke_request_fields(self):
        assert set(_fields(InvokeHarnessRequest)) == {
            "prompt",
            "harness_name",
            "harness",
            "run_agent_request",
        }

    def test_invoke_request_harness_is_optional_override(self):
        # A null `harness` means "use the served agent"; a non-null one is the
        # once-time override. The field must therefore allow None and default to it.
        field = _fields(InvokeHarnessRequest)["harness"]
        assert field.default is None
        assert field.annotation == (HarnessOverrides | None)

    def test_invoke_response_fields_and_defaults(self):
        fields = _fields(InvokeHarnessResponse)
        assert set(fields) == {"harness_name", "overwrite", "output", "error"}
        assert fields["overwrite"].default is False
        # `error` is unset on success and carries the message verbatim on failure.
        assert fields["error"].default is None


class TestSplitCsv:
    def test_splits_and_trims(self):
        assert split_csv("web_search, web_fetch") == ["web_search", "web_fetch"]

    def test_empty_string_is_empty_list(self):
        assert split_csv("") == []

    def test_drops_blank_segments(self):
        assert split_csv("a,,  ,b") == ["a", "b"]
