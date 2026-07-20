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
