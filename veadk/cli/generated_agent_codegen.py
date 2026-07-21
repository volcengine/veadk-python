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

"""Generate VeADK projects from frontend AgentDraft JSON on the backend."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from veadk.cli.generated_agent_catalog import (
    A2A_REGISTRY_ENV,
    EXPORTER_BY_ID,
    KB_BY_ID,
    LTM_BY_ID,
    MODEL_ENV,
    STM_BY_ID,
    TOOL_BY_ID,
    EnvVar,
)

_PYTHON_LICENSE_HEADER = """# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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
"""


class GeneratedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    content: str


class GeneratedProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    files: list[GeneratedFile]


class MemoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shortTerm: bool = False
    longTerm: bool = False


class CustomTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    description: str = ""


class McpTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    transport: Literal["http", "stdio"] = "http"
    url: str = ""
    authToken: str = ""
    command: str = ""
    args: list[str] = Field(default_factory=list)


class A2ARegistryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    registrySpaceId: str = ""
    registryTopK: str = ""
    registryRegion: str = ""
    registryEndpoint: str = ""

    @field_validator(
        "registrySpaceId",
        "registryTopK",
        "registryRegion",
        "registryEndpoint",
        mode="before",
    )
    @classmethod
    def _coerce_string(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value)


class SelectedSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["skillhub", "local", "skillspace"] = "skillhub"
    folder: str = ""
    name: str = ""
    description: str = ""
    slug: str = ""
    namespace: str = "public"
    localFiles: list[GeneratedFile] = Field(default_factory=list)
    skillSpaceId: str = ""
    skillSpaceName: str = ""
    skillSpaceRegion: str = ""
    skillId: str = ""
    version: str = ""

    @model_validator(mode="after")
    def _default_folder(self) -> "SelectedSkill":
        if not self.folder:
            self.folder = (
                self.name or self.slug.rsplit("/", 1)[-1] or self.skillId or "skill"
            )
        if not self.name:
            self.name = self.folder
        if self.source == "skillhub" and not self.namespace:
            self.namespace = "public"
        return self


class WorkflowNode(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = ""
    agent: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="allow")

    from_: str = Field(default="", alias="from")
    to: str = ""


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: str = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


class DeploymentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feishuEnabled: bool = False
    envValues: dict[str, str] = Field(default_factory=dict)


class AgentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    description: str = ""
    instruction: str = ""
    agentType: Literal["llm", "sequential", "parallel", "loop", "a2a"] = "llm"
    maxIterations: int = 3
    a2aUrl: str = ""
    model: str = ""
    modelName: str = ""
    modelProvider: str = ""
    modelApiBase: str = ""
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    knowledgebase: bool = False
    tracing: bool = False
    subAgents: list["AgentDraft"] = Field(default_factory=list)
    builtinTools: list[str] = Field(default_factory=list)
    customTools: list[CustomTool] = Field(default_factory=list)
    mcpTools: list[McpTool] = Field(default_factory=list)
    a2aRegistry: A2ARegistryConfig = Field(default_factory=A2ARegistryConfig)
    shortTermBackend: str = "local"
    longTermBackend: str = "local"
    autoSaveSession: bool = False
    knowledgebaseBackend: str = "local"
    tracingExporters: list[str] = Field(default_factory=list)
    selectedSkills: list[SelectedSkill] = Field(default_factory=list)
    workflow: WorkflowConfig | None = None
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig)

    @model_validator(mode="before")
    @classmethod
    def _ignore_retired_a2ui_option(cls, value: Any) -> Any:
        """Accept old Studio drafts without carrying A2UI into generation."""
        if not isinstance(value, dict) or "enableA2ui" not in value:
            return value
        normalized = value.copy()
        normalized.pop("enableA2ui")
        return normalized

    @field_validator("maxIterations", mode="before")
    @classmethod
    def _coerce_max_iterations(cls, value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 3


class GeneratedAgentProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: AgentDraft


class GeneratedAgentTestRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: AgentDraft


class _Acc:
    def __init__(self) -> None:
        self.imports: list[str] = []
        self.pre_lines: list[str] = []
        self.env: list[EnvVar] = list(MODEL_ENV)
        self.extras: set[str] = set()
        self.used_names: set[str] = set()
        self.agent_display_names: dict[str, str] = {}


def normalize_and_validate_draft(raw: Any) -> AgentDraft:
    if isinstance(raw, AgentDraft):
        return raw
    return AgentDraft.model_validate(raw)


def ident(raw: str, fallback: str) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or s[0].isdigit():
        return f"a_{s}" if s else fallback
    return s


def _agent_name(acc: _Acc, draft: AgentDraft, fallback: str) -> str:
    """Return the ADK-safe id while retaining the user-facing Agent name."""
    agent_name = ident(draft.name, fallback)
    acc.agent_display_names[agent_name] = draft.name.strip() or agent_name
    return agent_name


def _py_str(value: str) -> str:
    escaped = (
        (value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    )
    return f'"{escaped}"'


def _py_triple(value: str) -> str:
    escaped = (value or "").replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return f'"""{escaped}"""'


def _unique_ident(acc: _Acc, raw: str, fallback: str) -> str:
    base = ident(raw, fallback)
    name = base
    n = 2
    while name in acc.used_names:
        name = f"{base}_{n}"
        n += 1
    acc.used_names.add(name)
    return name


def _add_import(acc: _Acc, line: str) -> None:
    if line not in acc.imports:
        acc.imports.append(line)


def _add_env(acc: _Acc, env: tuple[EnvVar, ...]) -> None:
    acc.env.extend(env)


def _emit_tool_stub(acc: _Acc, name: str, description: str) -> str:
    fn = _unique_ident(acc, name, "custom_tool")
    doc = (description or "").strip() or f"TODO: 描述 {name} 的用途与参数。"
    comment_name = name.replace("\r", " ").replace("\n", " ")
    acc.pre_lines.append(
        f"def {fn}(query: str) -> dict:\n"
        f"    {_py_triple(doc)}\n"
        f"    # TODO: 实现「{comment_name}」的逻辑。\n"
        f'    return {{"result": f"{fn} 尚未实现: {{query}}"}}'
    )
    return fn


def _build_orchestrator(acc: _Acc, draft: AgentDraft, var_name: str) -> str:
    cls = {
        "parallel": "ParallelAgent",
        "loop": "LoopAgent",
        "sequential": "SequentialAgent",
    }.get(draft.agentType, "SequentialAgent")
    _add_import(acc, f"from google.adk.agents import {cls}")

    sub_vars: list[str] = []
    for idx, sub in enumerate(draft.subAgents):
        child_var = f"{var_name}_sub_{idx + 1}"
        _build_agent(acc, sub, child_var)
        sub_vars.append(child_var)

    kwargs = [
        f"name={_py_str(_agent_name(acc, draft, var_name))}",
        f"description={_py_str(draft.description or draft.name or 'A VeADK orchestrator agent.')}",
    ]
    if draft.agentType == "loop":
        kwargs.append(
            f"max_iterations={draft.maxIterations if draft.maxIterations > 0 else 3}"
        )
    kwargs.append(f"sub_agents=[{', '.join(sub_vars)}]")
    joined_kwargs = ",\n    ".join(kwargs)
    acc.pre_lines.append(f"{var_name} = {cls}(\n    {joined_kwargs},\n)")
    return var_name


def _build_a2a(acc: _Acc, draft: AgentDraft, var_name: str) -> str:
    _add_import(acc, "from veadk.a2a.remote_ve_agent import RemoteVeAgent")
    kwargs = [
        f"name={_py_str(_agent_name(acc, draft, var_name))}",
        f"url={_py_str((draft.a2aUrl or '').strip())}",
    ]
    joined_kwargs = ",\n    ".join(kwargs)
    acc.pre_lines.append(f"{var_name} = RemoteVeAgent(\n    {joined_kwargs},\n)")
    return var_name


def _build_agent(acc: _Acc, draft: AgentDraft, var_name: str) -> str:
    if draft.agentType == "a2a":
        return _build_a2a(acc, draft, var_name)
    if draft.agentType != "llm":
        return _build_orchestrator(acc, draft, var_name)

    tool_exprs: list[str] = []

    for tool_id in draft.builtinTools:
        tool = TOOL_BY_ID.get(tool_id)
        if tool is None:
            continue
        _add_import(acc, tool.import_line)
        tool_exprs.extend(tool.tool_names)
        _add_env(acc, tool.env)
        if tool.pip_extra:
            acc.extras.add(tool.pip_extra)

    for custom_tool in draft.customTools:
        if custom_tool.name.strip():
            tool_exprs.append(
                _emit_tool_stub(acc, custom_tool.name, custom_tool.description)
            )

    for mcp_tool in draft.mcpTools:
        if mcp_tool.transport == "http" and mcp_tool.url.strip():
            _add_import(
                acc, "from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset"
            )
            _add_import(
                acc,
                "from google.adk.tools.mcp_tool.mcp_session_manager import "
                "StreamableHTTPConnectionParams",
            )
            v = _unique_ident(acc, f"{mcp_tool.name or 'mcp'}_mcp", "mcp_tool")
            headers = ""
            if mcp_tool.authToken.strip():
                headers = (
                    ', headers={"Authorization": '
                    f"{_py_str('Bearer ' + mcp_tool.authToken.strip())}}}"
                )
            acc.pre_lines.append(
                f"{v} = MCPToolset(connection_params=StreamableHTTPConnectionParams("
                f"url={_py_str(mcp_tool.url.strip())}{headers}))"
            )
            tool_exprs.append(v)
        elif mcp_tool.transport == "stdio" and mcp_tool.command.strip():
            _add_import(
                acc, "from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset"
            )
            _add_import(
                acc,
                "from google.adk.tools.mcp_tool.mcp_toolset import "
                "StdioConnectionParams, StdioServerParameters",
            )
            v = _unique_ident(acc, f"{mcp_tool.name or 'mcp'}_mcp", "mcp_tool")
            args = ", ".join(_py_str(arg) for arg in mcp_tool.args if arg.strip())
            acc.pre_lines.append(
                f"{v} = MCPToolset(connection_params=StdioConnectionParams("
                "server_params=StdioServerParameters("
                f"command={_py_str(mcp_tool.command.strip())}, args=[{args}]), "
                "timeout=30))"
            )
            tool_exprs.append(v)

    if draft.a2aRegistry.enabled:
        _add_import(
            acc, "from veadk.a2a.registry_client import registry_config_from_env"
        )
        _add_import(
            acc,
            "from veadk.tools.builtin_tools.a2a_registry import "
            "build_a2a_registry_tools",
        )
        registry_var = _unique_ident(
            acc,
            f"a2a_registry_config_{var_name}",
            "a2a_registry_config",
        )
        tools_var = _unique_ident(
            acc,
            f"a2a_registry_tools_{var_name}",
            "a2a_registry_tools",
        )
        acc.pre_lines.append(f"{registry_var} = registry_config_from_env()")
        acc.pre_lines.append(f"{tools_var} = build_a2a_registry_tools({registry_var})")
        tool_exprs.append(f"*{tools_var}")
        _add_env(acc, A2A_REGISTRY_ENV)

    for name in draft.tools:
        if name.strip():
            tool_exprs.append(_emit_tool_stub(acc, name, ""))

    skill_folders = [
        skill.folder for skill in draft.selectedSkills if skill.folder.strip()
    ]
    if skill_folders:
        _add_import(acc, "from pathlib import Path as _Path")
        _add_import(acc, "from google.adk.skills import load_skill_from_dir")
        _add_import(acc, "from google.adk.tools.skill_toolset import SkillToolset")
        v = _unique_ident(acc, f"skills_{var_name}", "skill_toolset")
        loaders = [
            "        load_skill_from_dir("
            f'_Path(__file__).parent.parent.parent / "skills" / {_py_str(folder)})'
            for folder in skill_folders
        ]
        joined_loaders = ",\n".join(loaders)
        acc.pre_lines.append(f"{v} = SkillToolset(skills=[\n{joined_loaders},\n    ])")
        tool_exprs.append(v)

    kwargs = [
        f"name={_py_str(_agent_name(acc, draft, var_name))}",
        f"description={_py_str(draft.description or draft.name or 'A VeADK agent.')}",
        f"instruction=INSTRUCTION_{var_name.upper()}",
    ]
    acc.pre_lines.append(
        f"INSTRUCTION_{var_name.upper()} = "
        f"{_py_triple(draft.instruction or 'You are a helpful assistant.')}"
    )

    if tool_exprs:
        kwargs.append(f"tools=[{', '.join(tool_exprs)}]")
    if draft.modelName.strip():
        kwargs.append(f"model_name={_py_str(draft.modelName.strip())}")
    if draft.modelProvider.strip():
        kwargs.append(f"model_provider={_py_str(draft.modelProvider.strip())}")
    if draft.modelApiBase.strip():
        kwargs.append(f"model_api_base={_py_str(draft.modelApiBase.strip())}")

    if draft.memory.shortTerm:
        backend = STM_BY_ID.get(draft.shortTermBackend or "local")
        if backend:
            _add_import(
                acc, "from veadk.memory.short_term_memory import ShortTermMemory"
            )
            args = [f"backend={_py_str(backend.id)}"]
            if backend.extra_args:
                args.append(backend.extra_args)
            v = f"stm_{var_name}"
            acc.pre_lines.append(f"{v} = ShortTermMemory({', '.join(args)})")
            kwargs.append(f"short_term_memory={v}")
            _add_env(acc, backend.env)
            if backend.pip_extra:
                acc.extras.add(backend.pip_extra)

    if draft.memory.longTerm:
        backend = LTM_BY_ID.get(draft.longTermBackend or "local")
        if backend:
            _add_import(acc, "from veadk.memory.long_term_memory import LongTermMemory")
            idx = ident(draft.name, var_name)
            v = f"ltm_{var_name}"
            acc.pre_lines.append(
                f"{v} = LongTermMemory(backend={_py_str(backend.id)}, "
                f"index={_py_str(idx)}, app_name={_py_str(idx)})"
            )
            kwargs.append(f"long_term_memory={v}")
            if draft.autoSaveSession:
                kwargs.append("auto_save_session=True")
            _add_env(acc, backend.env)
            if backend.pip_extra:
                acc.extras.add(backend.pip_extra)

    if draft.knowledgebase:
        backend = KB_BY_ID.get(draft.knowledgebaseBackend or "local")
        if backend:
            _add_import(acc, "from veadk.knowledgebase import KnowledgeBase")
            idx = ident(f"{draft.name}_kb", f"{var_name}_kb")
            v = f"kb_{var_name}"
            acc.pre_lines.append(
                f"{v} = KnowledgeBase(backend={_py_str(backend.id)}, "
                f"index={_py_str(idx)}, app_name={_py_str(idx)})"
            )
            kwargs.append(f"knowledgebase={v}")
            _add_env(acc, backend.env)
            if backend.pip_extra:
                acc.extras.add(backend.pip_extra)

    if draft.tracing and draft.tracingExporters:
        _add_import(
            acc,
            "from veadk.tracing.telemetry.opentelemetry_tracer import "
            "OpentelemetryTracer",
        )
        v = f"tracer_{var_name}"
        acc.pre_lines.append(f"{v} = OpentelemetryTracer()")
        kwargs.append(f"tracers=[{v}]")
        for exporter_id in draft.tracingExporters:
            exporter = EXPORTER_BY_ID.get(exporter_id)
            if exporter:
                acc.env.append(
                    EnvVar(exporter.enable_flag, True, "true", f"{exporter.label} 开关")
                )
                _add_env(acc, exporter.env)

    sub_vars: list[str] = []
    for idx, sub in enumerate(draft.subAgents):
        child_var = f"{var_name}_sub_{idx + 1}"
        _build_agent(acc, sub, child_var)
        sub_vars.append(child_var)
    if sub_vars:
        kwargs.append(f"sub_agents=[{', '.join(sub_vars)}]")

    joined_kwargs = ",\n    ".join(kwargs)
    acc.pre_lines.append(f"{var_name} = Agent(\n    {joined_kwargs},\n)")
    if draft.a2aRegistry.enabled:
        acc.pre_lines.append(
            f'setattr({var_name}, "_veadk_a2a_registry_config", {registry_var})'
        )
    return var_name


def _dedupe_imports(imports: list[str]) -> list[str]:
    return list(dict.fromkeys(imports))


def _dedupe_env(env: list[EnvVar]) -> list[EnvVar]:
    deduped: dict[str, EnvVar] = {}
    for item in env:
        cur = deduped.get(item.key)
        if cur is None:
            deduped[item.key] = item
        elif item.required and not cur.required:
            deduped[item.key] = EnvVar(
                cur.key,
                True,
                cur.placeholder,
                cur.comment,
            )
    return list(deduped.values())


def render_env_example(env: list[EnvVar]) -> str:
    lines = [
        "# 复制为 .env 并填入真实值（或改用 config.yaml）。",
        "# 标记 [必填] 的变量缺失时 Agent 无法启动。",
        "",
    ]
    for item in env:
        if item.comment or item.required:
            lines.append(
                f"# {'[必填] ' if item.required else ''}{item.comment}".rstrip()
            )
        lines.append(f"{item.key}={item.placeholder}")
    return "\n".join(lines) + "\n"


def render_requirements(extras: set[str], include_feishu_channel: bool) -> str:
    # Pin minimum versions so the Docker image upgrades past pre-installed
    # older veadk releases that lack the newer tools and use Starlette 1.x
    # which removed Router.on_startup (breaks AgentkitAgentServer.lifespan).
    all_extras = set(extras)
    if include_feishu_channel:
        all_extras.add("extensions")
    unique_extras = sorted(all_extras)
    extras_str = f"[{','.join(unique_extras)}]" if unique_extras else ""
    pkg = f"veadk-python{extras_str}>=1.0.5"
    packages = [pkg, "agentkit-sdk-python", "google-adk", "starlette<1.0.0"]
    return "\n".join(packages) + "\n"


def render_readme(name: str, draft: AgentDraft) -> str:
    lines = [
        f"# {name}",
        "",
        draft.description or "由 VeADK Web UI「自定义模式」生成的 Agent 项目。",
        "",
        "## 运行",
        "",
        "```bash",
        "pip install -r requirements.txt",
        "cp .env.example .env   # 填入你的密钥",
        "python app.py",
        "```",
        "",
        "`app.py` 通过 VeADK 的 AgentKit 公共组件发布 `root_agent`，监听 `0.0.0.0:8000`。",
        "",
    ]
    if draft.deployment.feishuEnabled:
        lines.extend(
            [
                "## 飞书机器人",
                "",
                "在 VeADK 前端部署时勾选「飞书」并填写 App ID / App Secret，runtime 会在同一进程内启动 FeishuChannelExtension。",
                "",
            ]
        )
    return "\n".join(lines)


def _render_app_py(
    pkg: str,
    feishu_channel_enabled: bool,
    a2a_registry_enabled: bool,
) -> str:
    lines = [
        _PYTHON_LICENSE_HEADER.rstrip(),
        "",
        f"from agents.{pkg}.agent import AGENT_DISPLAY_NAMES, root_agent",
    ]
    if a2a_registry_enabled:
        lines.append(f"from agents.{pkg}.dynamic_a2a import enable_dynamic_a2a_tools")
    lines.extend(
        [
            "from veadk.integrations.agentkit import create_agentkit_app, run_agentkit_app",
            "",
            "app = create_agentkit_app(",
            "    root_agent,",
            "    AGENT_DISPLAY_NAMES,",
            f"    enable_feishu={feishu_channel_enabled!r},",
            ")",
        ]
    )
    if a2a_registry_enabled:
        lines.extend(["", "enable_dynamic_a2a_tools(app, root_agent)"])
    lines.extend(["", 'if __name__ == "__main__":', "    run_agentkit_app(app)", ""])
    return "\n".join(lines)


def _render_dynamic_a2a_py() -> str:
    return (
        _PYTHON_LICENSE_HEADER
        + r"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from google.adk.agents import RunConfig
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.run_config import StreamingMode
from google.adk.apps.app import App
from google.adk.cli.api_server import RunAgentRequest
from google.adk.runners import Runner as AdkRunner
from google.adk.utils.context_utils import Aclosing


_SERVER_STATE_KEY = "_veadk_agentkit_server"
_ADK_SERVER_STATE_KEY = "_veadk_adk_server"
_DYNAMIC_A2A_ROUTES_ENABLED_STATE_KEY = "_veadk_dynamic_a2a_routes_enabled"
_REGISTRY_CONFIG_ATTR = "_veadk_a2a_registry_config"


def _tool_name(tool: object) -> str | None:
    name = getattr(tool, "__name__", None) or getattr(tool, "name", None)
    return str(name) if name else None


def _content_text(content: object) -> str:
    parts = getattr(content, "parts", None) or []
    texts: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            texts.append(str(text))
    return "\n".join(texts)


def _has_a2a_registry_config(agent: object) -> bool:
    if getattr(agent, _REGISTRY_CONFIG_ATTR, None) is not None:
        return True
    return any(
        _has_a2a_registry_config(child)
        for child in getattr(agent, "sub_agents", []) or []
    )


def _add_dynamic_a2a_agent_tools(agent: object, prompt: str) -> int:
    attached = 0
    registry_config = getattr(agent, _REGISTRY_CONFIG_ATTR, None)
    prompt = prompt.strip()
    if registry_config is not None and prompt:
        from veadk.tools.builtin_tools.a2a_registry import build_remote_a2a_agent_tools

        dynamic_tools = build_remote_a2a_agent_tools(prompt, registry_config)
        existing = {
            name
            for tool in getattr(agent, "tools", []) or []
            if (name := _tool_name(tool))
        }
        for tool in dynamic_tools:
            name = _tool_name(tool)
            if not name or name in existing:
                continue
            getattr(agent, "tools").append(tool)
            existing.add(name)
            attached += 1

    for child in getattr(agent, "sub_agents", []) or []:
        attached += _add_dynamic_a2a_agent_tools(child, prompt)
    return attached


def _spawn_dynamic_a2a_agent(base_agent: BaseAgent, prompt: str) -> BaseAgent:
    cloned = base_agent.clone(update={})
    attached = _add_dynamic_a2a_agent_tools(cloned, prompt)
    if _has_a2a_registry_config(cloned):
        print(
            f"dynamic A2A tool assembly completed for this turn: attached={attached}",
            flush=True,
        )
    return cloned


def _promote_route(app: FastAPI, endpoint) -> None:
    routes = app.router.routes
    for index, route in enumerate(routes):
        if getattr(route, "endpoint", None) == endpoint:
            routes.insert(0, routes.pop(index))
            return


class _RuntimeServices:
    def __init__(self, app: FastAPI):
        agent_server = getattr(app.state, _SERVER_STATE_KEY, None)
        if agent_server is not None:
            self._load_from_server(getattr(agent_server, "server", agent_server))
            return

        adk_server = getattr(app.state, _ADK_SERVER_STATE_KEY, None)
        if adk_server is not None:
            self._load_from_server(adk_server)
            return

        attrs = getattr(app, "_tmpl_attrs", {})
        self.default_app_name = attrs.get("app_name")
        self.current_app_name_ref = attrs.get("current_app_name_ref")
        self.artifact_service = attrs.get("artifact_service")
        self.session_service = attrs.get("session_service")
        self.memory_service = attrs.get("memory_service")
        self.credential_service = attrs.get("credential_service")
        self.auto_create_session = bool(attrs.get("auto_create_session", False))

    def _load_from_server(self, server: object) -> None:
        self.default_app_name = getattr(server, "default_app_name", None)
        self.current_app_name_ref = getattr(server, "current_app_name_ref", None)
        self.artifact_service = getattr(server, "artifact_service", None)
        self.session_service = getattr(server, "session_service", None)
        self.memory_service = getattr(server, "memory_service", None)
        self.credential_service = getattr(server, "credential_service", None)
        self.auto_create_session = bool(getattr(server, "auto_create_session", False))


def _dynamic_runner(services: _RuntimeServices, *, app_name: str, root_agent: BaseAgent, prompt: str):
    run_agent = _spawn_dynamic_a2a_agent(root_agent, prompt)
    agent_app = App(name=app_name, root_agent=run_agent, plugins=[])
    return AdkRunner(
        app=agent_app,
        artifact_service=services.artifact_service,
        session_service=services.session_service,
        memory_service=services.memory_service,
        credential_service=services.credential_service,
        auto_create_session=services.auto_create_session,
    )


def _resolve_run_app_name(services: _RuntimeServices, root_agent: BaseAgent, req: RunAgentRequest) -> str:
    app_name = req.app_name or services.default_app_name
    if not app_name:
        app_name = getattr(root_agent, "name", "") or ""
    if not app_name:
        raise HTTPException(
            status_code=400,
            detail="app_name is required when ADK_DEFAULT_APP_NAME is not set",
        )
    req.app_name = app_name
    if services.current_app_name_ref is not None:
        services.current_app_name_ref.value = app_name
    return app_name


def enable_dynamic_a2a_tools(app: FastAPI, root_agent: BaseAgent) -> None:
    if getattr(app.state, _DYNAMIC_A2A_ROUTES_ENABLED_STATE_KEY, False):
        return

    services = _RuntimeServices(app)
    if services.session_service is None or not _has_a2a_registry_config(root_agent):
        return

    @app.post("/run", response_model=None)
    async def run_agent_dynamic(
        req: RunAgentRequest,
        request: Request,
    ) -> list[Any] | Response:
        app_name = _resolve_run_app_name(services, root_agent, req)
        runner = _dynamic_runner(
            services,
            app_name=app_name,
            root_agent=root_agent,
            prompt=_content_text(req.new_message),
        )
        run_config = (
            RunConfig(custom_metadata=req.custom_metadata)
            if req.custom_metadata
            else None
        )

        async def worker() -> list[Any]:
            async with Aclosing(
                runner.run_async(
                    user_id=req.user_id,
                    session_id=req.session_id,
                    new_message=req.new_message,
                    state_delta=req.state_delta,
                    invocation_id=req.invocation_id,
                    run_config=run_config,
                )
            ) as agen:
                return [event async for event in agen]

        worker_task = asyncio.create_task(worker())

        async def monitor() -> None:
            try:
                while True:
                    message = await request.receive()
                    if message.get("type") == "http.disconnect":
                        worker_task.cancel()
                        break
            except asyncio.CancelledError:
                pass

        monitor_task = asyncio.create_task(monitor())
        try:
            return await worker_task
        except asyncio.CancelledError:
            if await request.is_disconnected():
                return Response(status_code=499)
            raise
        finally:
            monitor_task.cancel()

    @app.post("/run_sse")
    async def run_agent_sse_dynamic(req: RunAgentRequest) -> StreamingResponse:
        app_name = _resolve_run_app_name(services, root_agent, req)
        runner = _dynamic_runner(
            services,
            app_name=app_name,
            root_agent=root_agent,
            prompt=_content_text(req.new_message),
        )
        stream_mode = StreamingMode.SSE if req.streaming else StreamingMode.NONE

        if not runner.auto_create_session:
            session = await services.session_service.get_session(
                app_name=app_name,
                user_id=req.user_id,
                session_id=req.session_id,
            )
            if not session:
                raise HTTPException(
                    status_code=404,
                    detail=f"Session not found: {req.session_id}",
                )

        async def event_generator():
            try:
                async with Aclosing(
                    runner.run_async(
                        user_id=req.user_id,
                        session_id=req.session_id,
                        new_message=req.new_message,
                        state_delta=req.state_delta,
                        run_config=RunConfig(
                            streaming_mode=stream_mode,
                            custom_metadata=req.custom_metadata,
                        ),
                        invocation_id=req.invocation_id,
                    )
                ) as agen:
                    async for event in agen:
                        events_to_stream = [event]
                        if (
                            not req.function_call_event_id
                            and event.actions.artifact_delta
                            and event.content
                            and event.content.parts
                        ):
                            content_event = event.model_copy(deep=True)
                            content_event.actions.artifact_delta = {}
                            artifact_event = event.model_copy(deep=True)
                            artifact_event.content = None
                            events_to_stream = [content_event, artifact_event]

                        for event_to_stream in events_to_stream:
                            yield (
                                "data: "
                                + event_to_stream.model_dump_json(
                                    exclude_none=True,
                                    by_alias=True,
                                )
                                + "\n\n"
                            )
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    _promote_route(app, run_agent_dynamic)
    _promote_route(app, run_agent_sse_dynamic)
    setattr(app.state, _DYNAMIC_A2A_ROUTES_ENABLED_STATE_KEY, True)
"""
    )


def _draft_has_a2a_registry(draft: AgentDraft) -> bool:
    if draft.a2aRegistry.enabled:
        return True
    return any(_draft_has_a2a_registry(sub_agent) for sub_agent in draft.subAgents)


def generate_project_from_draft(draft: AgentDraft) -> GeneratedProject:
    pkg = ident(draft.name, "my_agent")
    acc = _Acc()
    feishu_channel_enabled = bool(draft.deployment.feishuEnabled)
    if feishu_channel_enabled:
        acc.env.extend(
            [
                EnvVar(
                    "FEISHU_APP_ID",
                    False,
                    "cli_xxx",
                    "飞书机器人 App ID（前端部署时填写）",
                ),
                EnvVar(
                    "FEISHU_APP_SECRET",
                    False,
                    "your-feishu-app-secret",
                    "飞书机器人 App Secret（前端部署时填写）",
                ),
            ]
        )

    _build_agent(acc, draft, "agent")

    import_block = "\n".join(["from veadk import Agent", *_dedupe_imports(acc.imports)])
    agent_definition = (
        "\n\n".join(acc.pre_lines)
        + f"\n\nAGENT_DISPLAY_NAMES = {acc.agent_display_names!r}\n"
        + "\n# ADK 加载器要求：顶层 agent 必须命名为 root_agent\nroot_agent = agent\n"
    )
    agent_py = f"{_PYTHON_LICENSE_HEADER}\n{import_block}\n\n{agent_definition}"

    a2a_registry_enabled = _draft_has_a2a_registry(draft)
    app_py = _render_app_py(pkg, feishu_channel_enabled, a2a_registry_enabled)
    files = [
        GeneratedFile(path="app.py", content=app_py),
        # Top-level agents package marker so `from agents.<pkg>.agent import
        # root_agent` resolves when the container runs `python -m app`.
        GeneratedFile(path="agents/__init__.py", content=_PYTHON_LICENSE_HEADER),
        GeneratedFile(path=f"agents/{pkg}/agent.py", content=agent_py),
        GeneratedFile(
            path=f"agents/{pkg}/__init__.py",
            content=(
                f"{_PYTHON_LICENSE_HEADER}\n"
                "from .agent import AGENT_DISPLAY_NAMES, root_agent\n\n"
                '__all__ = ["AGENT_DISPLAY_NAMES", "root_agent"]\n'
            ),
        ),
        *(
            [
                GeneratedFile(
                    path=f"agents/{pkg}/dynamic_a2a.py",
                    content=_render_dynamic_a2a_py(),
                )
            ]
            if a2a_registry_enabled
            else []
        ),
        GeneratedFile(
            path=".env.example", content=render_env_example(_dedupe_env(acc.env))
        ),
        GeneratedFile(
            path="requirements.txt",
            content=render_requirements(acc.extras, feishu_channel_enabled),
        ),
        GeneratedFile(path="README.md", content=render_readme(pkg, draft)),
    ]
    return GeneratedProject(name=pkg, files=files)
