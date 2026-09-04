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

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import types
from pydantic import ValidationError

from veadk import Agent
from veadk.cloud.harness_app.agentkit_resources import (
    AgentKitMcpRouterResolver,
    AgentKitResourceResolver,
)
from veadk.cloud.harness_app.env_mapping import to_runtime_env
from veadk.cloud.harness_app.types import (
    HarnessAgentConfigRequest,
    HarnessBuiltinTool,
    HarnessCompactionMetric,
    HarnessConfig,
    HarnessCreateSessionRequest,
    HarnessEnhanceOverrides,
    HarnessMcpServer,
    HarnessOverrides,
    HarnessPluginMetrics,
    HarnessRegistryOverride,
    HarnessResourceOverride,
    HarnessResponseMetrics,
    HarnessSelectedSkill,
    InvokeHarnessRequest,
    InvokeHarnessResponse,
    LlmUsageMetrics,
    RunAgentRequest,
)
from veadk.cloud.harness_app.utils import (
    ResourceResolutionError,
    agent_name_from_harness,
    config_from_env,
    harness_overrides_from_env,
    init_harness_agent,
    merge_harness_overrides,
    normalize_harness_overrides,
    set_harness_mcp_router_resolver,
    set_harness_resource_resolver,
    spawn_harness_agent,
    spawn_harness_run_agent,
    split_csv,
)
from veadk.consts import DEFAULT_MODEL_AGENT_NAME
from veadk.knowledgebase import KnowledgeBase
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.save_session_callback import save_session_to_long_term_memory
from veadk.prompts.agent_default_prompt import DEFAULT_INSTRUCTION
from veadk.tools.builtin_tools.create_agent.sources.cloud import CloudCredentials
from veadk.tools.builtin_tools.load_knowledgebase import LoadKnowledgebaseTool


def _fields(model) -> dict:
    """Map of pydantic field name -> FieldInfo for ``model``."""
    return dict(model.model_fields)


def _after_agent_callbacks(agent: Agent) -> list[object]:
    callback = agent.after_agent_callback
    if callback is None:
        return []
    if isinstance(callback, list):
        return callback
    return [callback]


@pytest.fixture(autouse=True)
def _offline_embedding_key(monkeypatch):
    monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "test-embedding-key")
    set_harness_resource_resolver(None)
    set_harness_mcp_router_resolver(None)
    yield
    set_harness_resource_resolver(None)
    set_harness_mcp_router_resolver(None)


class TestHarnessOverrides:
    def test_fields(self):
        assert set(_fields(HarnessOverrides)) == {
            "model_name",
            "tools",
            "builtin_tools",
            "mcp_router_id",
            "skills",
            "selected_skills",
            "mcp",
            "system_prompt",
            "runtime",
            "registry_space_id",
            "registry_endpoint",
            "registry_region",
            "registry_top_k",
            "registry",
            "knowledgebase",
            "longterm_memory",
            "temperature",
            "top_p",
            "max_tokens",
            "presence_penalty",
            "frequency_penalty",
            "penalty",
            "max_llm_calls",
        }

    def test_defaults(self):
        fields = _fields(HarnessOverrides)
        assert fields["model_name"].default == DEFAULT_MODEL_AGENT_NAME
        assert fields["tools"].default == ""
        assert HarnessOverrides().builtin_tools == []
        assert fields["mcp_router_id"].default == ""
        assert fields["skills"].default == ""
        assert HarnessOverrides().selected_skills == []
        assert HarnessOverrides().mcp == []
        assert fields["system_prompt"].default == "You are a helpful assistant."
        assert fields["runtime"].default == "adk"
        assert fields["registry_space_id"].default == ""
        assert fields["registry_endpoint"].default == ""
        assert fields["registry_region"].default == ""
        assert fields["registry_top_k"].default == 3
        assert fields["registry"].default is None
        assert fields["knowledgebase"].default is None
        assert fields["longterm_memory"].default is None
        assert fields["temperature"].default is None
        assert fields["top_p"].default is None
        assert fields["max_tokens"].default is None
        assert fields["presence_penalty"].default is None
        assert fields["frequency_penalty"].default is None
        assert fields["penalty"].default is None
        assert fields["max_llm_calls"].default is None

    def test_max_llm_calls_has_only_minimum_limit(self):
        assert HarnessOverrides(max_llm_calls=20).max_llm_calls == 20
        assert HarnessConfig(max_llm_calls=20).max_llm_calls == 20
        assert RunAgentRequest(user_id="u1", session_id="s1", max_llm_calls=20)
        with pytest.raises(ValidationError):
            HarnessOverrides(max_llm_calls=0)
        with pytest.raises(ValidationError):
            HarnessConfig(max_llm_calls=0)
        with pytest.raises(ValidationError):
            RunAgentRequest(user_id="u1", session_id="s1", max_llm_calls=0)

    def test_legacy_tools_and_skills_are_still_csv_strings(self):
        h = HarnessOverrides()
        assert isinstance(h.tools, str)
        assert isinstance(h.skills, str)

    def test_structured_tools_skills_and_mcp_are_accepted(self):
        h = HarnessOverrides.model_validate(
            {
                "mcp_router_id": "mt-1",
                "builtin_tools": [
                    {"id": "web_search"},
                    {"id": "run_code", "config": {"tool_id": "t-1"}},
                ],
                "selected_skills": [
                    {"source": "skillhub", "slug": "team/reporting"},
                    {
                        "source": "skillspace",
                        "space_id": "ss-1",
                        "skill_id": "skill-1",
                    },
                ],
                "mcp": [{"name": "db", "url": "http://db.test/mcp"}],
            }
        )

        assert h.builtin_tools == [
            HarnessBuiltinTool(id="web_search"),
            HarnessBuiltinTool(id="run_code", config={"tool_id": "t-1"}),
        ]
        assert h.mcp_router_id == "mt-1"
        assert h.selected_skills[1] == HarnessSelectedSkill(
            source="skillspace",
            skill_space_id="ss-1",
            skill_id="skill-1",
        )
        assert h.mcp == [HarnessMcpServer(name="db", server_url="http://db.test/mcp")]

    def test_structured_registry_is_accepted_and_normalized(self):
        h = HarnessOverrides.model_validate(
            {
                "registry": {
                    "space_id": "space-1",
                    "region": "cn-beijing",
                    "top_k": 5,
                }
            }
        )

        assert h.registry == HarnessRegistryOverride(
            space_id="space-1",
            region="cn-beijing",
            top_k=5,
        )

        normalized = normalize_harness_overrides(h)

        assert normalized.registry is None
        assert normalized.model_dump(mode="json", exclude_unset=True) == {
            "registry_space_id": "space-1",
            "registry_region": "cn-beijing",
            "registry_top_k": 5,
        }

    def test_legacy_csv_fields_normalize_to_structured_fields(self):
        h = normalize_harness_overrides(
            HarnessOverrides(
                tools="web_search, run_code",
                mcp_router_id="mt-1",
                skills="team/reporting, space:ss-1",
            )
        )

        assert h.model_dump(mode="json", exclude_unset=True) == {
            "builtin_tools": [
                {"id": "web_search", "config": {}},
                {"id": "run_code", "config": {}},
                {"id": "mcp_router", "config": {"mcp_router_id": "mt-1"}},
            ],
            "mcp_router_id": "mt-1",
            "selected_skills": [
                {"source": "skillhub", "slug": "team/reporting"},
                {"source": "skillspace", "skill_space_id": "ss-1"},
            ],
        }

    def test_merge_harness_overrides_applies_session_then_current(self):
        merged = merge_harness_overrides(
            {
                "model_name": "session-model",
                "tools": "web_search",
                "system_prompt": "session prompt",
                "temperature": 0.2,
            },
            HarnessOverrides(
                builtin_tools=[{"id": "link_reader"}],
                system_prompt="current prompt",
                temperature=None,
                top_p=0.8,
            ),
        )

        assert merged.model_dump(mode="json", exclude_unset=True) == {
            "model_name": "session-model",
            "builtin_tools": [{"id": "link_reader", "config": {}}],
            "system_prompt": "current prompt",
            "temperature": None,
            "top_p": 0.8,
        }

    def test_long_term_memory_alias_is_accepted(self):
        h = HarnessOverrides.model_validate(
            {
                "long_term_memory": {
                    "type": "local",
                    "id": "ltm-1",
                    "config": {"index": "ltm-index"},
                }
            }
        )

        assert h.longterm_memory == HarnessResourceOverride(
            type="local", id="ltm-1", config={"index": "ltm-index"}
        )
        assert h.model_fields_set == {"longterm_memory"}

    def test_misspelled_knowledgebase_alias_is_accepted(self):
        h = HarnessOverrides.model_validate(
            {"konwledgebase": {"type": "local", "id": "kb-1"}}
        )

        assert h.knowledgebase == HarnessResourceOverride(type="local", id="kb-1")
        assert h.model_fields_set == {"knowledgebase"}

    def test_every_field_has_a_description(self):
        # Descriptions feed FastAPI schemas and the subset of CLI flags that are
        # still generated from this model, so each field must carry one.
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
        assert fields["max_llm_calls"].default == 10
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
                "mcp_router_id": "mt-1",
            }
        )

        assert envs["STRUCTURED_TOOL_CALLS"] == "true"
        assert envs["INCLUDE_TOOLS_EVERY_TURN"] == "true"
        assert envs["MCP_ROUTER_ID"] == "mt-1"
        assert envs["TOOLS"] == "mcp_router"

    def test_doc_harness_block_maps_to_runtime_env(self):
        envs = to_runtime_env(
            {
                "harness": {
                    "model_name": "doc-model",
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "max_llm_calls": 8,
                    "builtin_tools": [
                        {
                            "id": "run_code",
                            "config": {
                                "tool_id": "t-script-1",
                                "region": "cn-beijing",
                            },
                        },
                        {
                            "id": "mcp_router",
                            "config": {
                                "url": "http://router.test/mcp",
                                "api_key": "router-token",
                            },
                        },
                    ],
                    "selected_skills": [
                        {"source": "skillhub", "slug": "team/reporting"},
                    ],
                    "mcp": [{"name": "db", "server_url": "http://db.test/mcp"}],
                    "knowledgebase": {
                        "type": "viking",
                        "config": {
                            "index": "kb-viking-index",
                            "app_name": "kb-viking-index",
                            "project": "default",
                            "region": "cn-beijing",
                            "resource_id": "resource-xxx",
                        },
                    },
                    "longterm_memory": {
                        "type": "mem0",
                        "config": {
                            "index": "memory-index",
                            "app_name": "memory-index",
                            "api_key": "mem0-token",
                            "base_url": "https://api.mem0.ai",
                        },
                    },
                }
            }
        )

        assert envs["MODEL_AGENT_NAME"] == "doc-model"
        assert envs["MODEL_NAME"] == "doc-model"
        assert envs["MODEL_AGENT_TEMPERATURE"] == "0.3"
        assert envs["MODEL_AGENT_TOP_P"] == "0.9"
        assert envs["MAX_LLM_CALLS"] == "8"
        assert envs["TOOLS"] == "run_code,mcp_router"
        assert envs["AGENTKIT_TOOL_ID_SCRIPT"] == "t-script-1"
        assert envs["AGENTKIT_TOOL_REGION"] == "cn-beijing"
        assert envs["TOOL_MCP_ROUTER_URL"] == "http://router.test/mcp"
        assert envs["TOOL_MCP_ROUTER_API_KEY"] == "router-token"
        assert json.loads(envs["SELECTED_SKILLS_JSON"]) == [
            {"source": "skillhub", "slug": "team/reporting"}
        ]
        assert json.loads(envs["MCP_SERVERS_JSON"]) == [
            {"name": "db", "server_url": "http://db.test/mcp"}
        ]
        assert envs["KNOWLEDGEBASE_TYPE"] == "viking"
        assert envs["DATABASE_VIKING_PROJECT"] == "default"
        assert envs["DATABASE_VIKING_REGION"] == "cn-beijing"
        assert envs["DATABASE_VIKING_RESOURCE_ID"] == "resource-xxx"
        assert json.loads(envs["KNOWLEDGEBASE_CONFIG_JSON"]) == {
            "index": "kb-viking-index",
            "app_name": "kb-viking-index",
            "project": "default",
            "region": "cn-beijing",
            "resource_id": "resource-xxx",
        }
        assert envs["LONG_TERM_MEMORY_TYPE"] == "mem0"
        assert envs["DATABASE_MEM0_API_KEY"] == "mem0-token"
        assert envs["DATABASE_MEM0_BASE_URL"] == "https://api.mem0.ai"
        assert json.loads(envs["LONG_TERM_MEMORY_CONFIG_JSON"]) == {
            "index": "memory-index",
            "app_name": "memory-index",
            "api_key": "mem0-token",
            "base_url": "https://api.mem0.ai",
        }

    def test_cli_style_model_yaml_maps_current_and_legacy_model_env(self):
        envs = to_runtime_env(
            {
                "model": {"name": "cli-model"},
                "temperature": 0.2,
                "top_p": 0.7,
            }
        )

        assert envs["MODEL_AGENT_NAME"] == "cli-model"
        assert envs["MODEL_NAME"] == "cli-model"
        assert envs["MODEL_AGENT_TEMPERATURE"] == "0.2"
        assert envs["MODEL_AGENT_TOP_P"] == "0.7"

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

    def test_config_from_env_reads_agentkit_runtime_fields(self, monkeypatch):
        monkeypatch.setenv("MODEL_AGENT_NAME", "model-agent")
        monkeypatch.setenv("MODEL_NAME", "legacy-model")
        monkeypatch.setenv("MODEL_AGENT_TEMPERATURE", "0.2")
        monkeypatch.setenv("MODEL_AGENT_TOP_P", "0.8")
        monkeypatch.setenv(
            "SELECTED_SKILLS_JSON",
            '{"selected_skills":[{"source":"skillhub","slug":"team/reporting"}]}',
        )
        monkeypatch.setenv(
            "MCP_SERVERS_JSON",
            '[{"name":"db","server_url":"http://db.test/mcp","bear_token":"tok"}]',
        )
        monkeypatch.setenv("MCP_ROUTER_ID", "mt-1")
        monkeypatch.setenv("KNOWLEDGEBASE_TYPE", "local")
        monkeypatch.setenv("KNOWLEDGEBASE_ID", "kb-1")
        monkeypatch.setenv(
            "KNOWLEDGEBASE_CONFIG_JSON",
            '{"index":"kb-index","top_k":7}',
        )
        monkeypatch.setenv("LONG_TERM_MEMORY_TYPE", "local")
        monkeypatch.setenv("LONG_TERM_MEMORY_ID", "mem-1")
        monkeypatch.setenv(
            "LONG_TERM_MEMORY_CONFIG_JSON",
            '{"index":"memory-index"}',
        )

        config = config_from_env()

        assert config.model_name == "model-agent"
        assert config.temperature == 0.2
        assert config.top_p == 0.8
        assert config.selected_skills == [
            HarnessSelectedSkill(source="skillhub", slug="team/reporting")
        ]
        assert config.mcp == [
            HarnessMcpServer(
                name="db",
                server_url="http://db.test/mcp",
                bear_token="tok",
            )
        ]
        assert config.mcp_router_id == "mt-1"
        assert config.knowledgebase == HarnessResourceOverride(
            type="local",
            id="kb-1",
            config={"index": "kb-index", "top_k": 7},
        )
        assert config.longterm_memory == HarnessResourceOverride(
            type="local",
            id="mem-1",
            config={"index": "memory-index"},
        )

    def test_harness_overrides_from_env_uses_run_sse_harness_shape(self, monkeypatch):
        monkeypatch.setenv("MODEL_AGENT_NAME", "model-agent")
        monkeypatch.setenv("MODEL_AGENT_TEMPERATURE", "0.2")
        monkeypatch.setenv("MODEL_AGENT_TOP_P", "0.8")
        monkeypatch.setenv("MAX_LLM_CALLS", "4")
        monkeypatch.setenv("TOOLS", "web_search")
        monkeypatch.setenv("MCP_ROUTER_ID", "mt-1")
        monkeypatch.setenv(
            "SELECTED_SKILLS_JSON",
            '[{"source":"skillhub","slug":"team/reporting"}]',
        )
        monkeypatch.setenv("KNOWLEDGEBASE_TYPE", "viking")
        monkeypatch.setenv("KNOWLEDGEBASE_ID", "kb-1")
        monkeypatch.setenv(
            "KNOWLEDGEBASE_CONFIG_JSON",
            '{"index":"secret-kb-index","api_key":"secret"}',
        )
        monkeypatch.setenv("LONG_TERM_MEMORY_TYPE", "mem0")
        monkeypatch.setenv("LONG_TERM_MEMORY_ID", "memory-1")
        monkeypatch.setenv(
            "LONG_TERM_MEMORY_CONFIG_JSON",
            '{"index":"secret-memory-index","api_key":"secret"}',
        )

        config = harness_overrides_from_env()

        assert config.model_name == "model-agent"
        assert config.temperature == 0.2
        assert config.top_p == 0.8
        assert config.max_llm_calls == 4
        assert config.builtin_tools == [
            HarnessBuiltinTool(id="web_search"),
            HarnessBuiltinTool(id="mcp_router", config={"mcp_router_id": "mt-1"}),
        ]
        assert config.selected_skills == [
            HarnessSelectedSkill(source="skillhub", slug="team/reporting")
        ]
        assert config.knowledgebase == HarnessResourceOverride(
            type="viking",
            id="kb-1",
            config={"index": "secret-kb-index", "api_key": "secret"},
        )
        assert config.longterm_memory == HarnessResourceOverride(
            type="mem0",
            id="memory-1",
            config={"index": "secret-memory-index", "api_key": "secret"},
        )

    def test_resource_yaml_ids_map_to_runtime_env(self):
        envs = to_runtime_env(
            {
                "konwledgebase": {
                    "type": "viking",
                    "_id": "kb-1",
                    "project": "default",
                },
                "long_term_memory": {
                    "type": "mem0",
                    "id": "mem-1",
                    "base_url": "https://api.mem0.ai",
                },
            }
        )

        assert envs["KNOWLEDGEBASE_TYPE"] == "viking"
        assert envs["KNOWLEDGEBASE_ID"] == "kb-1"
        assert envs["DATABASE_VIKING_PROJECT"] == "default"
        assert envs["LONG_TERM_MEMORY_TYPE"] == "mem0"
        assert envs["LONG_TERM_MEMORY_ID"] == "mem-1"
        assert envs["DATABASE_MEM0_BASE_URL"] == "https://api.mem0.ai"

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

    def test_registry_request_auth_is_bound_to_run_agent_config(self):
        registry_source = Path("veadk/a2a/registry_client.py").read_text()
        utils_source = Path("veadk/cloud/harness_app/utils.py").read_text()
        app_source = Path("veadk/cloud/harness_app/app.py").read_text()

        assert "_apply_registry_request_auth(" in utils_source
        assert "upstream_tip_token=cleaned_tip_token" in utils_source
        assert "upstream_authorization=cleaned_authorization" in utils_source
        assert "registry_tip_token=tip_token" in app_source
        assert "registry_authorization=auth_header" in app_source
        assert "registry_authorization_from_headers" in app_source
        assert "registry_authorization_from_headers(" in registry_source
        assert "ContextVar" not in registry_source
        assert "use_registry_tip_token" not in registry_source
        assert "use_registry_tip_token" not in app_source

    def test_spawn_mounts_registry_tools_from_structured_registry(self):
        base = Agent(model_name="base-model", model_api_key="test-key")

        cloned = spawn_harness_agent(
            base,
            HarnessOverrides.model_validate(
                {
                    "registry": {
                        "space_id": "space-test",
                        "region": "cn-beijing",
                        "top_k": 5,
                    }
                }
            ),
        )

        registry_config = cloned._veadk_a2a_registry_config
        assert registry_config.space_id == "space-test"
        assert registry_config.region == "cn-beijing"
        assert registry_config.top_k == 5
        assert {
            "a2a_registry_search_agent_cards",
            "a2a_registry_task_create",
            "a2a_registry_task_poll",
        }.issubset({getattr(tool, "__name__", "") for tool in cloned.tools})

    def test_spawn_applies_sampling_overrides_to_clone_only(self):
        base = Agent(
            model_name="base-model",
            model_api_key="test-key",
            generate_content_config=types.GenerateContentConfig(temperature=0.1),
        )

        cloned = spawn_harness_agent(
            base,
            HarnessOverrides(
                top_p=0.9,
                max_tokens=128,
                penalty=0.2,
                presence_penalty=0.3,
            ),
        )

        assert base.generate_content_config is not None
        assert base.generate_content_config.temperature == 0.1
        assert base.generate_content_config.top_p is None
        assert cloned.generate_content_config.temperature == 0.1
        assert cloned.generate_content_config.top_p == 0.9
        assert cloned.generate_content_config.max_output_tokens == 128
        assert cloned.generate_content_config.presence_penalty == 0.3
        assert cloned.generate_content_config.frequency_penalty == 0.2

    def test_spawn_applies_resource_overrides_to_clone_only(self):
        base_kb = KnowledgeBase(backend="local", app_name="base-app")
        base_memory = LongTermMemory(backend="local", app_name="base-app")
        base = Agent(
            model_name="base-model",
            model_api_key="test-key",
            knowledgebase=base_kb,
            long_term_memory=base_memory,
        )

        cloned = spawn_harness_agent(
            base,
            HarnessOverrides(
                knowledgebase={
                    "type": "local",
                    "config": {"index": "request-kb"},
                },
                longterm_memory={
                    "type": "local",
                    "config": {"index": "request-memory"},
                },
            ),
            app_name="request-app",
        )

        base_kb_tools = [
            tool for tool in base.tools if isinstance(tool, LoadKnowledgebaseTool)
        ]
        cloned_kb_tools = [
            tool for tool in cloned.tools if isinstance(tool, LoadKnowledgebaseTool)
        ]

        assert base.knowledgebase is base_kb
        assert base.long_term_memory is base_memory
        assert base.knowledgebase.index == "base-app"
        assert base.long_term_memory.index == "base-app"
        assert len(base_kb_tools) == 1
        assert base_kb_tools[0].knowledgebase.index == "base-app"

        assert cloned.knowledgebase is not base.knowledgebase
        assert cloned.long_term_memory is not base.long_term_memory
        assert cloned.knowledgebase.index == "request-kb"
        assert cloned.long_term_memory.index == "request-memory"
        assert cloned.auto_save_session is True
        assert save_session_to_long_term_memory in _after_agent_callbacks(cloned)
        assert len(cloned_kb_tools) == 1
        assert cloned_kb_tools[0].knowledgebase.index == "request-kb"
        assert (
            sum(getattr(tool, "name", None) == "load_memory" for tool in cloned.tools)
            == 1
        )

    def test_spawn_removes_auto_save_when_longterm_memory_is_cleared(self):
        base_memory = LongTermMemory(backend="local", app_name="base-app")

        def custom_callback(*_args):
            return None

        base = Agent(
            model_name="base-model",
            model_api_key="test-key",
            long_term_memory=base_memory,
            auto_save_session=True,
            after_agent_callback=custom_callback,
        )

        cloned = spawn_harness_agent(
            base,
            HarnessOverrides.model_validate({"longterm_memory": None}),
            app_name="request-app",
        )

        assert base.long_term_memory is base_memory
        assert base.auto_save_session is True
        assert save_session_to_long_term_memory in _after_agent_callbacks(base)
        assert cloned.long_term_memory is None
        assert cloned.auto_save_session is False
        assert _after_agent_callbacks(cloned) == [custom_callback]
        assert not any(
            getattr(tool, "name", None) == "load_memory" for tool in cloned.tools
        )

    def test_resource_id_without_resolver_falls_back_to_index_and_app_name(self):
        base = Agent(model_name="base-model", model_api_key="test-key")

        cloned = spawn_harness_agent(
            base,
            HarnessOverrides(
                knowledgebase={"type": "local", "id": "kb-id"},
                longterm_memory={"type": "local", "id": "memory-id"},
            ),
            app_name="request-app",
        )

        assert cloned.knowledgebase.index == "kb-id"
        assert cloned.knowledgebase.app_name == "kb-id"
        assert cloned.long_term_memory.index == "memory-id"
        assert cloned.long_term_memory.app_name == "memory-id"

    def test_resource_resolver_merges_control_plane_config(self):
        base = Agent(model_name="base-model", model_api_key="test-key")
        calls = []

        def resolver(kind, resource):
            calls.append((kind, resource.type, resource.id))
            if kind == "knowledgebase":
                return {"type": "local", "index": "resolved-kb", "top_k": 4}
            return HarnessResourceOverride(
                type="local",
                config={"index": "resolved-memory", "top_k": 2},
            )

        set_harness_resource_resolver(resolver)
        try:
            cloned = spawn_harness_agent(
                base,
                HarnessOverrides(
                    knowledgebase={
                        "type": "local",
                        "id": "kb-id",
                        "config": {"top_k": 7},
                    },
                    longterm_memory={"type": "local", "id": "memory-id"},
                ),
                app_name="request-app",
            )
        finally:
            set_harness_resource_resolver(None)

        assert calls == [
            ("knowledgebase", "local", "kb-id"),
            ("longterm_memory", "local", "memory-id"),
        ]
        assert cloned.knowledgebase.index == "resolved-kb"
        assert cloned.knowledgebase.top_k == 7
        assert cloned.long_term_memory.index == "resolved-memory"
        assert cloned.long_term_memory.top_k == 2

    def test_resource_resolver_can_supply_missing_resource_type(self):
        base = Agent(model_name="base-model", model_api_key="test-key")
        calls = []

        def resolver(kind, resource):
            calls.append((kind, resource.type, resource.id))
            if kind == "knowledgebase":
                return HarnessResourceOverride(
                    type="local",
                    config={"index": "resolved-kb"},
                )
            return HarnessResourceOverride(
                type="local",
                config={"index": "resolved-memory"},
            )

        set_harness_resource_resolver(resolver)
        try:
            cloned = spawn_harness_agent(
                base,
                HarnessOverrides(
                    knowledgebase={"id": "kb-id"},
                    longterm_memory={"id": "memory-id"},
                ),
                app_name="request-app",
            )
        finally:
            set_harness_resource_resolver(None)

        assert calls == [
            ("knowledgebase", "", "kb-id"),
            ("longterm_memory", "", "memory-id"),
        ]
        assert cloned.knowledgebase.index == "resolved-kb"
        assert cloned.long_term_memory.index == "resolved-memory"

    def test_init_harness_agent_resolves_env_resource_ids_without_types(
        self, monkeypatch
    ):
        calls = []

        def resolver(kind, resource):
            calls.append((kind, resource.type, resource.id))
            if kind == "knowledgebase":
                return HarnessResourceOverride(
                    type="local",
                    config={"index": "env-kb"},
                )
            return HarnessResourceOverride(
                type="local",
                config={"index": "env-memory"},
            )

        def mcp_router_resolver(mcp_router_id, config):
            calls.append(("mcp_router", "", mcp_router_id))
            return {
                "url": "http://router.test/mcp",
                "api_key": "router-token",
            }

        monkeypatch.setenv("MODEL_AGENT_NAME", "env-agent")
        monkeypatch.setenv("MCP_ROUTER_ID", "mt-1")
        monkeypatch.setenv("KNOWLEDGEBASE_ID", "kb-id")
        monkeypatch.setenv("LONG_TERM_MEMORY_ID", "memory-id")
        set_harness_resource_resolver(resolver)
        set_harness_mcp_router_resolver(mcp_router_resolver)
        try:
            agent, _memory = init_harness_agent()
        finally:
            set_harness_resource_resolver(None)
            set_harness_mcp_router_resolver(None)

        assert calls == [
            ("mcp_router", "", "mt-1"),
            ("knowledgebase", "", "kb-id"),
            ("longterm_memory", "", "memory-id"),
        ]
        mcp_router = next(
            tool
            for tool in agent.tools
            if getattr(tool, "_veadk_harness_builtin_tool_id", "") == "mcp_router"
        )
        assert mcp_router._connection_params.url == "http://router.test/mcp"
        assert mcp_router._connection_params.headers == {
            "Authorization": "Bearer router-token"
        }
        assert agent.knowledgebase.index == "env-kb"
        assert agent.long_term_memory.index == "env-memory"
        assert agent.auto_save_session is True
        assert save_session_to_long_term_memory in _after_agent_callbacks(agent)

    def test_resource_resolver_missing_id_fails_clearly(self):
        base = Agent(model_name="base-model", model_api_key="test-key")
        set_harness_resource_resolver(lambda *_args: None)
        try:
            with pytest.raises(
                ResourceResolutionError,
                match="No runtime config found for knowledgebase resource 'kb-id'",
            ):
                spawn_harness_agent(
                    base,
                    HarnessOverrides(knowledgebase={"type": "local", "id": "kb-id"}),
                    app_name="request-app",
                )
        finally:
            set_harness_resource_resolver(None)

    def test_agentkit_resolver_fetches_mem0_connection_info(self):
        memory_requests = []

        class MemoryClient:
            def get_memory_collection(self, request):
                memory_requests.append(("get", request.memory_id))
                return SimpleNamespace(
                    memory_id=request.memory_id,
                    name="my_agent_memory",
                    provider_collection_id="ak-my_agent_memory",
                    provider_type="MEM0",
                    region="cn-beijing",
                    project_name="default",
                )

            def get_memory_connection_info(self, request):
                memory_requests.append(("connection", request.memory_id))
                return SimpleNamespace(
                    memory_id=request.memory_id,
                    provider_collection_id="ak-my_agent_memory",
                    provider_type="MEM0",
                    connection_infos=[
                        SimpleNamespace(
                            status="Ready",
                            addr_type="Public",
                            auth_key="mem0-api-key",
                            base_url="https://mem0.example.com",
                        )
                    ],
                )

        resolver = AgentKitResourceResolver(
            region="cn-beijing",
            credential_resolver=lambda: CloudCredentials("ak", "sk", "sts"),
            memory_client_factory=lambda credentials, region: MemoryClient(),
        )

        resolved = resolver(
            "longterm_memory",
            HarnessResourceOverride(type="", id="mem-1"),
        )

        assert memory_requests == [("get", "mem-1"), ("connection", "mem-1")]
        assert resolved == HarnessResourceOverride(
            type="mem0",
            id="mem-1",
            config={
                "index": "ak-my_agent_memory",
                "app_name": "ak-my_agent_memory",
                "api_key": "mem0-api-key",
                "base_url": "https://mem0.example.com",
                "project_id": "ak-my_agent_memory",
            },
        )

    def test_agentkit_resolver_fetches_viking_knowledge_connection_info(self):
        knowledge_requests = []

        class KnowledgeClient:
            def get_knowledge_base(self, request):
                knowledge_requests.append(("get", request.knowledge_id))
                return SimpleNamespace(
                    knowledge_id=request.knowledge_id,
                    name="my_travel_knowledge",
                    description="travel knowledge",
                    provider_knowledge_id="kb-travel-001",
                    provider_type="VIKINGDB_KNOWLEDGE",
                    region="cn-beijing",
                    project_name="default",
                )

            def get_knowledge_connection_info(self, request):
                knowledge_requests.append(("connection", request.knowledge_id))
                return SimpleNamespace(
                    knowledge_id=request.knowledge_id,
                    provider_knowledge_id="kb-travel-001",
                    provider_type="VIKINGDB_KNOWLEDGE",
                    connection_infos=[
                        SimpleNamespace(
                            status="Ready",
                            addr_type="Public",
                            auth_type="STS",
                            auth_key=json.dumps(
                                {
                                    "AccessKeyId": "temporary-ak",
                                    "SecretAccessKey": "temporary-sk",
                                    "SessionToken": "temporary-token",
                                }
                            ),
                            base_url="https://knowledge.example.com",
                            region="cn-beijing",
                        )
                    ],
                )

        resolver = AgentKitResourceResolver(
            region="cn-beijing",
            credential_resolver=lambda: CloudCredentials("fallback-ak", "fallback-sk"),
            knowledge_client_factory=lambda credentials, region: KnowledgeClient(),
        )

        resolved = resolver(
            "knowledgebase",
            HarnessResourceOverride(
                type="",
                id="kb-1",
                config={"top_k": 7},
            ),
        )

        assert knowledge_requests == [("get", "kb-1"), ("connection", "kb-1")]
        assert resolved.type == "viking"
        assert resolved.id == "kb-1"
        assert resolved.config == {
            "name": "my_travel_knowledge",
            "description": "travel knowledge",
            "index": "my_travel_knowledge",
            "app_name": "my_travel_knowledge",
            "resource_id": "kb-travel-001",
            "region": "cn-beijing",
            "volcengine_project": "default",
            "volcengine_access_key": "temporary-ak",
            "volcengine_secret_key": "temporary-sk",
            "session_token": "temporary-token",
            "cloud_provider": "volcengine",
            "base_url": "https://knowledge.example.com",
            "host": "knowledge.example.com",
            "schema": "https",
            "top_k": 7,
        }

    def test_agentkit_resolver_without_credentials_allows_config_fallback(self):
        resolver = AgentKitResourceResolver(
            credential_resolver=lambda: None,
        )

        resolved = resolver(
            "knowledgebase",
            HarnessResourceOverride(
                type="viking",
                id="kb-1",
                config={"index": "explicit-index"},
            ),
        )

        assert resolved is None

    def test_agentkit_mcp_router_resolver_fetches_toolset_connection_info(self):
        mcp_requests = []

        class MCPClient:
            def get_mcp_toolset(self, request):
                mcp_requests.append(request.mcp_toolset_id)
                return SimpleNamespace(
                    mcp_toolset=SimpleNamespace(
                        mcp_toolset_id=request.mcp_toolset_id,
                        name="router",
                        path="/mcp",
                        network_configurations=[
                            SimpleNamespace(
                                network_type="Public",
                                endpoint="https://router.example.com",
                            )
                        ],
                        authorizer_configuration=SimpleNamespace(
                            authorizer_type="ApiKey",
                            authorizer=SimpleNamespace(
                                key_auth=SimpleNamespace(
                                    api_keys=[
                                        SimpleNamespace(
                                            key="router-token",
                                            name="default",
                                        )
                                    ]
                                )
                            ),
                        ),
                    )
                )

        resolver = AgentKitMcpRouterResolver(
            region="cn-beijing",
            credential_resolver=lambda: CloudCredentials("ak", "sk"),
            mcp_client_factory=lambda credentials, region: MCPClient(),
        )

        resolved = resolver("mt-1")

        assert mcp_requests == ["mt-1"]
        assert resolved == {
            "mcp_router_id": "mt-1",
            "url": "https://router.example.com/mcp",
            "api_key": "router-token",
            "name": "router",
        }

    def test_spawn_mounts_mcp_router_from_id(self):
        base = Agent(model_name="base-model", model_api_key="test-key")
        calls = []

        def resolver(mcp_router_id, config):
            calls.append((mcp_router_id, config))
            return {
                "url": "http://router.test/mcp",
                "api_key": "router-token",
            }

        set_harness_mcp_router_resolver(resolver)
        try:
            cloned = spawn_harness_agent(
                base,
                HarnessOverrides(mcp_router_id="mt-1"),
            )
        finally:
            set_harness_mcp_router_resolver(None)

        mcp_router = next(
            tool
            for tool in cloned.tools
            if getattr(tool, "_veadk_harness_builtin_tool_id", "") == "mcp_router"
        )

        assert calls == [("mt-1", {"mcp_router_id": "mt-1"})]
        assert mcp_router._connection_params.url == "http://router.test/mcp"
        assert mcp_router._connection_params.headers == {
            "Authorization": "Bearer router-token"
        }

    def test_spawn_replaces_builtin_tools(self, monkeypatch):
        from veadk.cloud.harness_app import utils

        def base_web_search():
            return "base-web"

        def custom_tool():
            return "custom"

        def fake_get_builtin_tool(name):
            def tool():
                return name

            tool.__name__ = name
            return tool

        base_web_search.__name__ = "web_search"
        custom_tool.__name__ = "custom_tool"
        monkeypatch.setattr(utils, "get_builtin_tool", fake_get_builtin_tool)
        base = Agent(model_name="base-model", model_api_key="test-key")
        base.tools = [base_web_search, custom_tool]

        cloned = spawn_harness_agent(
            base,
            HarnessOverrides(builtin_tools=[{"id": "link_reader"}]),
        )

        tool_names = [getattr(tool, "__name__", "") for tool in cloned.tools]
        assert tool_names == ["custom_tool", "link_reader"]

    def test_spawn_replaces_skills(self, monkeypatch):
        from veadk.cloud.harness_app import utils

        class FakeSkillToolset:
            def __init__(self, names):
                self.names = names

        old_skill_toolset = FakeSkillToolset(["old"])

        def custom_tool():
            return "custom"

        def fake_build_skill_toolset(skill_ids, download_dir=None):
            return FakeSkillToolset(skill_ids) if skill_ids else None

        custom_tool.__name__ = "custom_tool"
        monkeypatch.setattr(utils, "SkillToolset", FakeSkillToolset)
        monkeypatch.setattr(utils, "build_skill_toolset", fake_build_skill_toolset)
        base = Agent(model_name="base-model", model_api_key="test-key")
        base.tools = [old_skill_toolset, custom_tool]

        cloned = spawn_harness_agent(
            base,
            HarnessOverrides(
                selected_skills=[{"source": "skillhub", "slug": "team/new-skill"}]
            ),
        )

        assert custom_tool in cloned.tools
        skill_toolsets = [
            tool for tool in cloned.tools if isinstance(tool, FakeSkillToolset)
        ]
        assert old_skill_toolset not in cloned.tools
        assert len(skill_toolsets) == 1
        assert skill_toolsets[0].names == ["team/new-skill"]

    def test_spawn_clears_builtin_tools_and_skills_with_empty_overrides(
        self, monkeypatch
    ):
        from veadk.cloud.harness_app import utils

        class FakeSkillToolset:
            pass

        def base_web_search():
            return "base-web"

        base_web_search.__name__ = "web_search"
        monkeypatch.setattr(utils, "SkillToolset", FakeSkillToolset)
        base = Agent(model_name="base-model", model_api_key="test-key")
        base.tools = [base_web_search, FakeSkillToolset()]

        cloned = spawn_harness_agent(
            base,
            HarnessOverrides.model_validate(
                {
                    "tools": "",
                    "selected_skills": [],
                }
            ),
        )

        assert cloned.tools == []

    def test_spawn_applies_agentkit_structured_runtime_tools(self, monkeypatch):
        from veadk.cloud.harness_app import utils

        def fake_get_builtin_tool(name):
            def tool():
                return {
                    "tool_id": os.environ.get("AGENTKIT_TOOL_ID_SCRIPT"),
                    "region": os.environ.get("AGENTKIT_TOOL_REGION"),
                }

            tool.__name__ = name
            return tool

        monkeypatch.setattr(utils, "get_builtin_tool", fake_get_builtin_tool)
        base = Agent(model_name="base-model", model_api_key="test-key")
        cloned = spawn_harness_agent(
            base,
            HarnessOverrides(
                builtin_tools=[
                    {
                        "id": "run_code",
                        "config": {
                            "tool_id": "t-script-1",
                            "region": "cn-beijing",
                        },
                    },
                    {
                        "id": "mcp_router",
                        "config": {
                            "url": "http://router.test/mcp",
                            "api_key": "router-token",
                        },
                    },
                ],
                mcp=[
                    {
                        "name": "db",
                        "server_url": "http://db.test/mcp",
                        "bear_token": "db-token",
                    }
                ],
            ),
        )

        run_code = next(
            tool
            for tool in cloned.tools
            if getattr(tool, "_veadk_harness_builtin_tool_id", "") == "run_code"
        )
        mcp_router = next(
            tool
            for tool in cloned.tools
            if getattr(tool, "_veadk_harness_builtin_tool_id", "") == "mcp_router"
        )
        mcp = next(
            tool
            for tool in cloned.tools
            if getattr(tool, "_veadk_harness_mcp_server", "") == "db"
        )

        assert run_code() == {
            "tool_id": "t-script-1",
            "region": "cn-beijing",
        }
        assert mcp_router._connection_params.url == "http://router.test/mcp"
        assert mcp_router._connection_params.headers == {
            "Authorization": "Bearer router-token"
        }
        assert mcp._connection_params.url == "http://db.test/mcp"
        assert mcp._connection_params.headers == {"Authorization": "Bearer db-token"}

    def test_spawn_run_agent_merges_session_and_current_overrides(self):
        base = Agent(
            model_name="base-model",
            model_api_key="test-key",
            instruction="base prompt",
            generate_content_config=types.GenerateContentConfig(temperature=0.1),
        )

        cloned = spawn_harness_run_agent(
            base,
            "hello",
            session_overrides={
                "model_name": "session-model",
                "system_prompt": "session prompt",
                "temperature": 0.2,
            },
            current_overrides={
                "system_prompt": "current prompt",
                "top_p": 0.8,
            },
        )

        assert base.model_name == "base-model"
        assert base.instruction == "base prompt"
        assert base.generate_content_config.temperature == 0.1
        assert cloned.model_name == "session-model"
        assert cloned.instruction == "current prompt"
        assert cloned.generate_content_config.temperature == 0.2
        assert cloned.generate_content_config.top_p == 0.8


class TestRequestResponseSchemas:
    def test_create_session_request_accepts_agentkit_id(self):
        request = HarnessCreateSessionRequest.model_validate(
            {
                "id": "session-1",
                "state": {"foo": "bar"},
                "events": [],
            }
        )

        assert request.id == "session-1"
        assert request.session_id is None
        assert request.state == {"foo": "bar"}
        assert request.events == []

    def test_create_session_request_accepts_adk_session_id_alias(self):
        request = HarnessCreateSessionRequest.model_validate({"sessionId": "session-1"})

        assert request.id is None
        assert request.session_id == "session-1"

    def test_get_agent_config_request_accepts_camel_case(self):
        request = HarnessAgentConfigRequest.model_validate(
            {
                "appName": "test_agent",
                "userId": "test_user",
                "sessionId": "session-1",
            }
        )

        assert request.app_name == "test_agent"
        assert request.user_id == "test_user"
        assert request.session_id == "session-1"

    def test_get_agent_config_request_defaults_user_and_session(self):
        request = HarnessAgentConfigRequest.model_validate({})

        assert request.app_name is None
        assert request.user_id == "default"
        assert request.session_id == "default"

    def test_run_agent_request_fields(self):
        assert set(_fields(RunAgentRequest)) == {
            "user_id",
            "session_id",
            "max_llm_calls",
        }

    def test_enhance_override_defaults(self):
        assert HarnessEnhanceOverrides().model_dump() == {
            "enabled": False,
            "components": "invocation_context,compactor,response_verification",
            "profile": "default",
            "compression_provider": None,
        }

    def test_invoke_request_fields(self):
        assert set(_fields(InvokeHarnessRequest)) == {
            "prompt",
            "harness_name",
            "harness",
            "harness_merge",
            "harness_enhance",
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
        assert set(fields) == {
            "harness_name",
            "overwrite",
            "output",
            "metrics",
            "error",
        }
        assert fields["overwrite"].default is False
        assert fields["metrics"].default is None
        # `error` is unset on success and carries the message verbatim on failure.
        assert fields["error"].default is None

    def test_usage_metrics_accumulate(self):
        usage = LlmUsageMetrics(prompt_tokens=10, total_tokens=12, usage_event_count=1)
        usage.add(
            LlmUsageMetrics(
                prompt_tokens=20,
                completion_tokens=5,
                total_tokens=25,
                cached_tokens=3,
                usage_event_count=1,
            )
        )

        assert HarnessResponseMetrics(llm_usage=usage).model_dump() == {
            "llm_usage": {
                "prompt_tokens": 30,
                "completion_tokens": 5,
                "total_tokens": 37,
                "cached_tokens": 3,
                "usage_event_count": 2,
            },
            "harness_plugins": {
                "names": [],
                "compaction_reports": [],
            },
        }

    def test_harness_plugin_metrics_are_structured(self):
        metrics = HarnessResponseMetrics(
            harness_plugins=HarnessPluginMetrics(
                names=["harness_compress_plugin"],
                compaction_reports=[
                    HarnessCompactionMetric(
                        provider="builtin",
                        original_chars=8000,
                        compressed_chars=400,
                        changed=True,
                        tokens_before=2000,
                        tokens_after=100,
                        tokens_saved=1900,
                        compression_ratio=0.05,
                        transforms_applied=["builtin_tool_fact_compaction"],
                    )
                ],
            )
        )

        report = metrics.harness_plugins.compaction_reports[0]
        assert metrics.harness_plugins.names == ["harness_compress_plugin"]
        assert report.changed is True
        assert report.compressed_chars < report.original_chars


class TestSplitCsv:
    def test_splits_and_trims(self):
        assert split_csv("web_search, web_fetch") == ["web_search", "web_fetch"]

    def test_empty_string_is_empty_list(self):
        assert split_csv("") == []

    def test_drops_blank_segments(self):
        assert split_csv("a,,  ,b") == ["a", "b"]


class TestAgentNameFromHarness:
    """The agent name (and thus the A2A card name) is derived from the harness
    name, normalized to a valid ADK identifier."""

    def test_identifier_passes_through(self):
        assert agent_name_from_harness("harness_app") == "harness_app"

    def test_hyphens_become_underscores(self):
        assert agent_name_from_harness("oauth-test") == "oauth_test"

    def test_leading_digit_is_prefixed(self):
        assert agent_name_from_harness("2048-bot") == "_2048_bot"

    def test_reserved_user_is_escaped(self):
        assert agent_name_from_harness("user") == "user_"

    def test_result_is_always_a_valid_identifier(self):
        for raw in ["oauth-test", "2048-bot", "user", "a.b c", ""]:
            name = agent_name_from_harness(raw)
            assert name.isidentifier(), raw
            assert name != "user"
