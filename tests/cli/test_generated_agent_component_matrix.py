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
    GeneratedProject,
    MemoryConfig,
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
    assert ("[extensions]" in files["requirements.txt"]) == bool(backend.pip_extra)
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
    assert ("[extensions]" in files["requirements.txt"]) == bool(backend.pip_extra)
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
    assert "Reliability Review Remote Agent" not in agent_py
    assert "ignored remote description" not in agent_py
    assert "ignored remote instruction" not in agent_py
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
    assert "ignored-remote-name" not in agent_py
    assert "ignored remote description" not in agent_py
    assert "ignored remote instruction" not in agent_py
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
    assert "registry-worker" not in agent_py
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
    assert "veadk-python[extensions]>=1.0.5" in files["requirements.txt"]
    _assert_python_files_compile(project)
