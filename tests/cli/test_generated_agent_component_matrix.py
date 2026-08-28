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

from __future__ import annotations

import ast

import pytest

from veadk.cli.generated_agent_catalog import (
    A2A_REGISTRY_ENV,
    BUILTIN_TOOLS,
    KB_BACKENDS,
    LTM_BACKENDS,
    MODEL_ENV,
    STM_BACKENDS,
    TRACING_EXPORTERS,
    BackendOption,
    EnvVar,
    ExporterOption,
)
from veadk.cli.generated_agent_codegen import (
    A2ARegistryConfig,
    AgentDraft,
    DeploymentConfig,
    GeneratedProject,
    McpTool,
    MemoryConfig,
    debug_runtime_env_from_draft,
    generate_project_from_draft,
)


def _files(project: GeneratedProject) -> dict[str, str]:
    return {file.path: file.content for file in project.files}


def _env_keys(env_example: str) -> set[str]:
    return {
        line.split("=", 1)[0]
        for line in env_example.splitlines()
        if line and not line.startswith("#")
    }


def _catalog_env_keys(*groups: tuple[EnvVar, ...]) -> set[str]:
    return {item.key for group in groups for item in group}


def _assert_python_files_compile(project: GeneratedProject) -> None:
    for path, content in _files(project).items():
        if path.endswith(".py"):
            ast.parse(content, filename=path)


def _veadk_requirement(extras: set[str]) -> str:
    extras_str = f"[{','.join(sorted(extras))}]" if extras else ""
    return f"veadk-python{extras_str}==1.1.6"


EXPECTED_LTM_EXTRAS = {
    "local": {"extensions"},
    "opensearch": {"extensions"},
    "redis": {"extensions"},
    "viking": set(),
    "openviking": set(),
    "mem0": {"database"},
}

EXPECTED_KB_EXTRAS = {
    "local": {"extensions"},
    "opensearch": {"extensions"},
    "viking": set(),
    "context_search": set(),
    "openviking": set(),
}

DEFAULT_ARK_DEBUG_ENV = {
    item.key: item.placeholder
    for item in MODEL_ENV
    if item.key in {"MODEL_AGENT_PROVIDER", "MODEL_AGENT_API_BASE", "MODEL_AGENT_NAME"}
}
DEFAULT_ARK_DEBUG_ENV["MODEL_NAME"] = DEFAULT_ARK_DEBUG_ENV["MODEL_AGENT_NAME"]


def test_component_catalog_does_not_request_auto_resolved_credentials() -> None:
    component_env_keys = _catalog_env_keys(
        *(item.env for item in BUILTIN_TOOLS),
        *(item.env for item in STM_BACKENDS),
        *(item.env for item in LTM_BACKENDS),
        *(item.env for item in KB_BACKENDS),
        *(item.env for item in TRACING_EXPORTERS),
    )

    auto_resolved_credentials = {
        "MODEL_AGENT_API_KEY",
        "MODEL_EMBEDDING_API_KEY",
        "MODEL_IMAGE_API_KEY",
        "MODEL_EDIT_API_KEY",
        "MODEL_VIDEO_API_KEY",
        "TOOL_VESPEECH_API_KEY",
        "TOOL_VESEARCH_API_KEY",
        "VOLCENGINE_ACCESS_KEY",
        "VOLCENGINE_SECRET_KEY",
        "OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY",
    }

    assert component_env_keys.isdisjoint(auto_resolved_credentials)
    assert "MODEL_AGENT_API_KEY" not in _catalog_env_keys(MODEL_ENV)


@pytest.mark.parametrize(
    ("draft_updates", "env"),
    [({"builtinTools": [option.id]}, option.env) for option in BUILTIN_TOOLS]
    + [
        (
            {
                "memory": MemoryConfig(shortTerm=True),
                "shortTermBackend": option.id,
            },
            option.env,
        )
        for option in STM_BACKENDS
    ]
    + [
        (
            {
                "memory": MemoryConfig(longTerm=True),
                "longTermBackend": option.id,
            },
            option.env,
        )
        for option in LTM_BACKENDS
    ]
    + [
        (
            {"knowledgebase": True, "knowledgebaseBackend": option.id},
            option.env,
        )
        for option in KB_BACKENDS
    ],
)
def test_debug_runtime_forwards_active_component_env(
    draft_updates: dict[str, object],
    env: tuple[EnvVar, ...],
) -> None:
    env_values = {item.key: f"configured-{item.key.lower()}" for item in env}
    env_values["UNSELECTED_COMPONENT_ENV"] = "blocked"
    draft = AgentDraft.model_validate(
        {
            "name": "debug-env",
            "deployment": DeploymentConfig(envValues=env_values),
            **draft_updates,
        }
    )

    result = debug_runtime_env_from_draft(draft)

    expected_component_env = {
        key: value
        for key, value in env_values.items()
        if key != "UNSELECTED_COMPONENT_ENV"
    }
    assert result == {**DEFAULT_ARK_DEBUG_ENV, **expected_component_env}


@pytest.mark.parametrize("exporter", TRACING_EXPORTERS, ids=lambda item: item.id)
def test_debug_runtime_forwards_active_tracing_env_and_enable_flag(
    exporter: ExporterOption,
) -> None:
    env_values = {item.key: f"configured-{item.key.lower()}" for item in exporter.env}
    draft = AgentDraft(
        name="debug-tracing-env",
        tracing=True,
        tracingExporters=[exporter.id],
        deployment=DeploymentConfig(envValues=env_values),
    )

    assert debug_runtime_env_from_draft(draft) == {
        **DEFAULT_ARK_DEBUG_ENV,
        **env_values,
        exporter.enable_flag: "true",
    }


def test_debug_runtime_materializes_mcp_token_env_without_mutating_draft() -> None:
    draft = AgentDraft(
        name="debug-agent",
        mcpTools=[
            McpTool(
                name="orders",
                transport="http",
                url="https://mcp.example.com/mcp",
                authToken="debug-secret",
            )
        ],
    )

    assert debug_runtime_env_from_draft(draft) == {
        **DEFAULT_ARK_DEBUG_ENV,
        "MCP_DEBUG_AGENT_ORDERS_AUTH_TOKEN": "debug-secret",
    }
    assert draft.mcpTools[0].authToken == "debug-secret"


def test_debug_runtime_materializes_nested_a2a_registry_defaults() -> None:
    draft = AgentDraft(
        name="debug-a2a-env",
        subAgents=[
            AgentDraft(
                name="remote-agent",
                agentType="a2a",
                a2aRegistry=A2ARegistryConfig(
                    enabled=True,
                    registrySpaceId="space-debug",
                ),
            )
        ],
    )

    assert debug_runtime_env_from_draft(draft) == {
        **DEFAULT_ARK_DEBUG_ENV,
        "REGISTRY_SPACE_ID": "space-debug",
        "REGISTRY_TOP_K": "3",
        "REGISTRY_REGION": "cn-beijing",
        "REGISTRY_ENDPOINT": "https://open.volcengineapi.com/",
    }


def test_managed_components_keep_only_component_specific_env() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="managed-components",
            builtinTools=[
                "web_search",
                "link_reader",
                "image_generate",
                "image_edit",
                "video_generate",
                "text_to_speech",
                "vesearch",
            ],
            memory=MemoryConfig(shortTerm=True, longTerm=True),
            longTermBackend="viking",
            knowledgebase=True,
            knowledgebaseBackend="context_search",
            tracing=True,
            tracingExporters=["apmplus", "tls"],
        )
    )
    env_keys = _env_keys(_files(project)[".env.example"])

    assert "VOLCENGINE_ACCESS_KEY" not in env_keys
    assert "VOLCENGINE_SECRET_KEY" not in env_keys
    assert "MODEL_AGENT_API_KEY" not in env_keys
    assert "DATABASE_CONTEXT_SEARCH_ENGINE_ID" in env_keys
    assert "DATABASE_CONTEXT_SEARCH_ENGINE_ENDPOINT" in env_keys
    assert "DATABASE_CONTEXT_SEARCH_ENGINE_APIKEY" in env_keys
    assert "TOOL_VESPEECH_APP_ID" in env_keys
    assert "TOOL_VESEARCH_ENDPOINT" in env_keys
    assert "OBSERVABILITY_OPENTELEMETRY_APMPLUS_SERVICE_NAME" in env_keys
    assert "MODEL_EMBEDDING_API_KEY" not in env_keys
    assert "MODEL_IMAGE_API_KEY" not in env_keys
    assert "MODEL_EDIT_API_KEY" not in env_keys
    assert "MODEL_VIDEO_API_KEY" not in env_keys
    assert "TOOL_VESPEECH_API_KEY" not in env_keys
    assert "TOOL_VESEARCH_API_KEY" not in env_keys
    assert "OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY" not in env_keys


def test_byteplus_generated_project_uses_byteplus_modelark_defaults() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="byteplus-agent",
            cloudProvider="byteplus",
            knowledgebase=True,
            knowledgebaseBackend="opensearch",
            builtinTools=["image_generate", "image_edit", "video_generate"],
        )
    )
    env_example = _files(project)[".env.example"]

    assert "MODEL_AGENT_NAME=seed-2-0-lite-260228" in env_example
    assert (
        "MODEL_AGENT_API_BASE=https://ark.ap-southeast.bytepluses.com/api/v3"
        in env_example
    )
    assert "MODEL_EMBEDDING_NAME=skylark-embedding-vision-250615" in env_example
    assert (
        "MODEL_EMBEDDING_API_BASE=https://ark.ap-southeast.bytepluses.com/api/v3"
        in env_example
    )
    assert "MODEL_IMAGE_NAME=dola-seedream-5-0-pro-260628" in env_example
    assert "MODEL_EDIT_NAME=seededit-3-0-i2i-250628" in env_example
    assert "MODEL_VIDEO_NAME=dreamina-seedance-2-0-260128" in env_example
    assert "ark.cn-beijing.volces.com" not in env_example
    assert "doubao-" not in env_example


def test_run_code_generates_tool_import_and_sandbox_env() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="code-agent",
            instruction="Execute code when it helps answer the request.",
            builtinTools=["run_code"],
        )
    )
    files = _files(project)
    agent_py = files["agents/code_agent/agent.py"]
    env_example = files[".env.example"]

    assert "from veadk.tools.builtin_tools.run_code import run_code" in agent_py
    assert "tools=[run_code]" in agent_py
    assert "AGENTKIT_TOOL_ID=" in env_example
    assert "AGENTKIT_TOOL_REGION=cn-beijing" in env_example
    assert "AGENTKIT_TOOL_ID_SCRIPT=" not in env_example
    _assert_python_files_compile(project)


@pytest.mark.parametrize("backend", STM_BACKENDS, ids=lambda item: item.id)
def test_every_short_term_memory_backend_generates_code_and_env(
    backend: BackendOption,
) -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name=f"stm-{backend.id}",
            memory=MemoryConfig(shortTerm=True),
            shortTermBackend=backend.id,
        )
    )
    files = _files(project)
    agent_py = files[f"agents/stm_{backend.id}/agent.py"]

    assert f'ShortTermMemory(backend="{backend.id}"' in agent_py
    assert _env_keys(files[".env.example"]) == _catalog_env_keys(MODEL_ENV, backend.env)
    _assert_python_files_compile(project)


@pytest.mark.parametrize("backend", LTM_BACKENDS, ids=lambda item: item.id)
def test_every_long_term_memory_backend_generates_code_env_and_dependency(
    backend: BackendOption,
) -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name=f"ltm-{backend.id}",
            memory=MemoryConfig(longTerm=True),
            longTermBackend=backend.id,
            autoSaveSession=True,
        )
    )
    files = _files(project)
    agent_py = files[f"agents/ltm_{backend.id}/agent.py"]

    assert f'LongTermMemory(backend="{backend.id}"' in agent_py
    assert "auto_save_session=True" in agent_py
    assert _env_keys(files[".env.example"]) == _catalog_env_keys(MODEL_ENV, backend.env)
    assert files["requirements.txt"].splitlines()[0] == _veadk_requirement(
        EXPECTED_LTM_EXTRAS[backend.id]
    )
    _assert_python_files_compile(project)


def test_openviking_long_term_memory_generates_required_runtime_env() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="ltm-openviking",
            memory=MemoryConfig(longTerm=True),
            longTermBackend="openviking",
        )
    )
    files = _files(project)

    assert (
        'LongTermMemory(backend="openviking"' in files["agents/ltm_openviking/agent.py"]
    )
    assert _env_keys(files[".env.example"]) == _catalog_env_keys(
        MODEL_ENV,
        next(item.env for item in LTM_BACKENDS if item.id == "openviking"),
    )
    assert "DATABASE_OPENVIKING_MEMORY_POLICY=\n" in files[".env.example"]
    assert "不填写时使用官方默认策略" in files[".env.example"]
    assert files["requirements.txt"].splitlines()[0] == _veadk_requirement(set())


def test_viking_long_term_memory_uses_selected_index() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="ltm-viking",
            memory=MemoryConfig(longTerm=True),
            longTermBackend="viking",
            longTermMemoryIndex="existing_memory",
        )
    )
    agent_py = _files(project)["agents/ltm_viking/agent.py"]

    assert 'LongTermMemory(backend="viking", index="existing_memory"' in agent_py
    assert "'longTermMemoryIndex': 'existing_memory'" in agent_py
    _assert_python_files_compile(project)


@pytest.mark.parametrize("backend", KB_BACKENDS, ids=lambda item: item.id)
def test_every_knowledgebase_backend_generates_code_env_and_dependency(
    backend: BackendOption,
) -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name=f"kb-{backend.id}",
            knowledgebase=True,
            knowledgebaseBackend=backend.id,
        )
    )
    files = _files(project)
    agent_py = files[f"agents/kb_{backend.id}/agent.py"]

    assert f'KnowledgeBase(backend="{backend.id}"' in agent_py
    assert _env_keys(files[".env.example"]) == _catalog_env_keys(MODEL_ENV, backend.env)
    assert files["requirements.txt"].splitlines()[0] == _veadk_requirement(
        EXPECTED_KB_EXTRAS[backend.id]
    )
    _assert_python_files_compile(project)


def test_component_dependencies_are_merged_and_deduplicated() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="dependency-combination",
            memory=MemoryConfig(longTerm=True),
            longTermBackend="mem0",
            subAgents=[
                AgentDraft(
                    name="opensearch-worker",
                    memory=MemoryConfig(longTerm=True),
                    longTermBackend="opensearch",
                    knowledgebase=True,
                    knowledgebaseBackend="opensearch",
                )
            ],
        )
    )

    requirements = _files(project)["requirements.txt"].splitlines()

    assert requirements[0] == _veadk_requirement({"database", "extensions"})
    assert requirements[0].count("extensions") == 1


def test_viking_knowledgebase_uses_selected_index() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="kb-viking",
            knowledgebase=True,
            knowledgebaseBackend="viking",
            knowledgebaseIndex="existing_kb",
        )
    )
    agent_py = _files(project)["agents/kb_viking/agent.py"]

    assert 'KnowledgeBase(backend="viking", index="existing_kb"' in agent_py
    _assert_python_files_compile(project)


def test_openviking_knowledgebase_generates_required_runtime_env() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="kb-openviking",
            knowledgebase=True,
            knowledgebaseBackend="openviking",
            knowledgebaseIndex="company_faq",
        )
    )
    files = _files(project)
    agent_py = files["agents/kb_openviking/agent.py"]

    assert 'KnowledgeBase(backend="openviking", index="company_faq"' in agent_py
    assert _env_keys(files[".env.example"]) == _catalog_env_keys(
        MODEL_ENV,
        next(item.env for item in KB_BACKENDS if item.id == "openviking"),
    )
    assert "DATABASE_OPENVIKING_TARGET_URI=\n" in files[".env.example"]
    assert files["requirements.txt"].splitlines()[0] == _veadk_requirement(set())
    _assert_python_files_compile(project)


@pytest.mark.parametrize("exporter", TRACING_EXPORTERS, ids=lambda item: item.id)
def test_every_tracing_exporter_generates_code_and_env(
    exporter: ExporterOption,
) -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name=f"tracing-{exporter.id}",
            tracing=True,
            tracingExporters=[exporter.id],
        )
    )
    files = _files(project)
    agent_py = files[f"agents/tracing_{exporter.id}/agent.py"]

    assert "OpentelemetryTracer()" in agent_py
    assert "tracers=[tracer_agent]" in agent_py
    assert _env_keys(files[".env.example"]) == (
        _catalog_env_keys(MODEL_ENV, exporter.env) | {exporter.enable_flag}
    )
    _assert_python_files_compile(project)


def test_a2a_registry_child_attaches_tools_to_llm_parent() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="root-agent",
            instruction="Use available tools to answer user requests.",
            subAgents=[
                AgentDraft(
                    name="Reliability Review Remote Agent",
                    description="ignored remote description",
                    instruction="ignored remote instruction",
                    agentType="a2a",
                    a2aRegistry=A2ARegistryConfig(
                        enabled=True,
                        registrySpaceId="space-test",
                    ),
                )
            ],
        )
    )
    files = _files(project)
    agent_py = files["agents/root_agent/agent.py"]

    assert "a2a_registry_config_agent_sub_1 = registry_config_from_env()" in agent_py
    assert "tools=[*a2a_registry_tools_agent_sub_1]" in agent_py
    assert (
        'setattr(agent, "_veadk_a2a_registry_config", '
        "a2a_registry_config_agent_sub_1)" in agent_py
    )
    assert "agent_sub_1 = Agent(" not in agent_py
    assert "sub_agents=[agent_sub_1]" not in agent_py
    runtime_agent_py = agent_py.split("AGENT_DRAFT =", 1)[0]
    assert "Reliability Review Remote Agent" not in runtime_agent_py
    assert "ignored remote description" not in runtime_agent_py
    assert "ignored remote instruction" not in runtime_agent_py
    assert "REGISTRY_SPACE_ID=space-test" in files[".env.example"]
    _assert_python_files_compile(project)


def test_a2a_registry_center_generates_tools_and_env() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="a2a-center",
            agentType="sequential",
            subAgents=[
                AgentDraft(
                    name="ignored-remote-name",
                    description="ignored remote description",
                    instruction="ignored remote instruction",
                    agentType="a2a",
                    a2aRegistry=A2ARegistryConfig(
                        enabled=True,
                        registrySpaceId="space-test",
                    ),
                )
            ],
        )
    )
    files = _files(project)
    app_py = files["app.py"]
    agent_py = files["agents/a2a_center/agent.py"]
    dynamic_py = files["agents/a2a_center/dynamic_a2a.py"]

    assert "enable_dynamic_a2a_tools(app, root_agent)" in app_py
    assert "from veadk.a2a.registry_client import registry_config_from_env" in agent_py
    assert "from veadk.tools.builtin_tools.a2a_registry import" in agent_py
    assert "a2a_registry_config_agent_sub_1 = registry_config_from_env()" in agent_py
    assert "build_a2a_registry_tools" in agent_py
    assert "tools=[*a2a_registry_tools_agent_sub_1]" in agent_py
    assert "RemoteVeAgent(" not in agent_py
    assert (
        'setattr(agent_sub_1, "_veadk_a2a_registry_config", '
        "a2a_registry_config_agent_sub_1)" in agent_py
    )
    assert 'name="agent_sub_1"' in agent_py
    runtime_agent_py = agent_py.split("AGENT_DRAFT =", 1)[0]
    assert "ignored-remote-name" not in runtime_agent_py
    assert "ignored remote description" not in runtime_agent_py
    assert "ignored remote instruction" not in runtime_agent_py
    assert "build_remote_a2a_agent_tools(prompt, registry_config)" in dynamic_py
    assert "def _run_request_custom_metadata(" in dynamic_py
    assert 'getattr(req, "custom_metadata", None)' in dynamic_py
    assert "req.custom_metadata" not in dynamic_py
    assert "_ADK_SERVER_STATE_KEY" in dynamic_py
    assert "_DYNAMIC_A2A_ROUTES_ENABLED_STATE_KEY" in dynamic_py
    assert "def _has_dynamic_a2a_routes(" in dynamic_py
    assert '@app.post("/run_sse")' in dynamic_py
    assert '@app.post("/invoke")' in dynamic_py
    assert "types.UserContent" in dynamic_py
    assert _env_keys(files[".env.example"]) == _catalog_env_keys(
        MODEL_ENV,
        A2A_REGISTRY_ENV,
    )
    assert "REGISTRY_TOP_K=3" in files[".env.example"]
    assert "REGISTRY_REGION=cn-beijing" in files[".env.example"]
    assert "REGISTRY_ENDPOINT=https://open.volcengineapi.com/" in files[".env.example"]
    _assert_python_files_compile(project)


def test_remote_agent_cannot_be_generated_as_root() -> None:
    with pytest.raises(ValueError, match="Remote Agent cannot be the root Agent"):
        generate_project_from_draft(
            AgentDraft(
                agentType="a2a",
                a2aRegistry=A2ARegistryConfig(
                    enabled=True,
                    registrySpaceId="space-test",
                ),
            )
        )


def test_a2a_registry_center_env_example_uses_configured_values() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="a2a-center-custom",
            a2aRegistry=A2ARegistryConfig(
                enabled=True,
                registrySpaceId="space-custom",
                registryTopK="8",
                registryRegion="cn-shanghai",
                registryEndpoint="https://example.com/",
            ),
        )
    )
    env_example = _files(project)[".env.example"]

    assert "REGISTRY_SPACE_ID=space-custom" in env_example
    assert "REGISTRY_TOP_K=8" in env_example
    assert "REGISTRY_REGION=cn-shanghai" in env_example
    assert "REGISTRY_ENDPOINT=https://example.com/" in env_example


def test_nested_a2a_registry_agent_generates_dynamic_helper() -> None:
    project = generate_project_from_draft(
        AgentDraft(
            name="root-sequential",
            agentType="sequential",
            subAgents=[
                AgentDraft(
                    name="registry-worker",
                    agentType="a2a",
                    a2aRegistry=A2ARegistryConfig(
                        enabled=True,
                        registrySpaceId="space-test",
                    ),
                )
            ],
        )
    )
    files = _files(project)

    assert "agents/root_sequential/dynamic_a2a.py" in files
    assert "enable_dynamic_a2a_tools(app, root_agent)" in files["app.py"]
    agent_py = files["agents/root_sequential/agent.py"]
    assert "agent_sub_1 = Agent(" in agent_py
    assert 'name="agent_sub_1"' in agent_py
    runtime_agent_py = agent_py.split("AGENT_DRAFT =", 1)[0]
    assert "registry-worker" not in runtime_agent_py
    assert "REGISTRY_SPACE_ID=space-test" in files[".env.example"]
    assert (
        "_has_a2a_registry_config(child)"
        in files["agents/root_sequential/dynamic_a2a.py"]
    )
    _assert_python_files_compile(project)


def test_deeply_nested_agent_types_generate_complete_component_project() -> None:
    component_worker = AgentDraft(
        name="component-worker",
        memory=MemoryConfig(shortTerm=True, longTerm=True),
        shortTermBackend="postgresql",
        longTermBackend="opensearch",
        autoSaveSession=True,
        knowledgebase=True,
        knowledgebaseBackend="context_search",
        tracing=True,
        tracingExporters=[item.id for item in TRACING_EXPORTERS],
    )
    draft = AgentDraft(
        name="root-sequential",
        agentType="sequential",
        subAgents=[
            AgentDraft(
                name="parallel-layer",
                agentType="parallel",
                subAgents=[
                    AgentDraft(
                        name="loop-layer",
                        agentType="loop",
                        maxIterations=5,
                        subAgents=[
                            component_worker,
                            AgentDraft(
                                name="remote-worker",
                                agentType="a2a",
                                a2aUrl="https://agent.example.com",
                            ),
                        ],
                    )
                ],
            )
        ],
    )

    project = generate_project_from_draft(draft)
    files = _files(project)
    agent_py = files["agents/root_sequential/agent.py"]
    expected_env = _catalog_env_keys(
        MODEL_ENV,
        next(item.env for item in STM_BACKENDS if item.id == "postgresql"),
        next(item.env for item in LTM_BACKENDS if item.id == "opensearch"),
        next(item.env for item in KB_BACKENDS if item.id == "context_search"),
        *(item.env for item in TRACING_EXPORTERS),
    ) | {item.enable_flag for item in TRACING_EXPORTERS}

    assert "agent = SequentialAgent(" in agent_py
    assert "agent_sub_1 = ParallelAgent(" in agent_py
    assert "agent_sub_1_sub_1 = LoopAgent(" in agent_py
    assert "max_iterations=5" in agent_py
    assert "agent_sub_1_sub_1_sub_1 = Agent(" in agent_py
    assert "agent_sub_1_sub_1_sub_2 = RemoteVeAgent(" in agent_py
    assert 'ShortTermMemory(backend="postgresql")' in agent_py
    assert 'LongTermMemory(backend="opensearch"' in agent_py
    assert 'KnowledgeBase(backend="context_search"' in agent_py
    assert "OpentelemetryTracer()" in agent_py
    assert _env_keys(files[".env.example"]) == expected_env
    assert "veadk-python[extensions]==1.1.6" in files["requirements.txt"]
    _assert_python_files_compile(project)
