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

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from google.adk.tools import ToolContext

from veadk.tools.builtin_tools.execute_skills import execute_skills

_REMOTE_SKILL_TIMEOUT = 1800


@dataclass(frozen=True)
class RemoteSkillDefinition:
    """Runtime Agent 可见的 RemoteSkill 描述，不包含真实 Skill 实现。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    display_name: str | None = None
    timeout: int = _REMOTE_SKILL_TIMEOUT


def load_remote_skill_definitions(
    value: str | os.PathLike[str],
) -> list[RemoteSkillDefinition]:
    """从 JSON 字符串或文件路径加载 RemoteSkill 列表。"""

    raw = _load_manifest_json(value)
    skills = raw.get("remote_skills")
    if not isinstance(skills, list):
        raise ValueError("RemoteSkills manifest must contain a remote_skills list")

    definitions = [_parse_remote_skill(item) for item in skills]
    names = [item.name for item in definitions]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"RemoteSkills manifest has duplicate names: {duplicates}")
    return definitions


def _load_manifest_json(value: str | os.PathLike[str]) -> dict[str, Any]:
    """读取 manifest；支持直接传 JSON，也支持传本地文件路径。"""

    text = str(value).strip()
    if not text:
        raise ValueError("RemoteSkills manifest path or JSON content is empty")
    if text.startswith("{"):
        data = json.loads(text)
    else:
        data = json.loads(Path(text).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("RemoteSkills manifest must be a JSON object")
    return data


def _parse_remote_skill(item: Any) -> RemoteSkillDefinition:
    """校验单个 RemoteSkill 配置，并转换为运行时定义。"""

    if not isinstance(item, dict):
        raise ValueError("Each RemoteSkill entry must be an object")

    name = _required_string(item, "name")
    description = _required_string(item, "description")
    input_schema = item.get("input_schema")
    if not isinstance(input_schema, dict):
        raise ValueError(f"RemoteSkill {name!r} must define input_schema as an object")

    timeout = int(
        item.get("timeout") or item.get("timeout_seconds") or _REMOTE_SKILL_TIMEOUT
    )
    if timeout <= 0 or timeout > _REMOTE_SKILL_TIMEOUT:
        raise ValueError(
            f"RemoteSkill {name!r} timeout must be between 1 and {_REMOTE_SKILL_TIMEOUT}"
        )

    display_name = item.get("display_name")
    return RemoteSkillDefinition(
        name=name,
        display_name=str(display_name).strip() if display_name else None,
        description=description,
        input_schema=input_schema,
        timeout=timeout,
    )


def _required_string(item: dict[str, Any], field: str) -> str:
    """读取必填字符串字段；空值直接视为 manifest 配置错误。"""

    value = item.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"RemoteSkill must define non-empty {field}")
    return value.strip()


def build_remote_skill_tools(
    definitions: list[RemoteSkillDefinition],
    *,
    executor: Callable[..., str] = execute_skills,
) -> list[Callable[..., str]]:
    """把 RemoteSkill 描述转换成 Agent 可挂载的工具函数。"""

    return [
        _make_remote_skill_tool(definition, executor=executor)
        for definition in definitions
    ]


def _make_remote_skill_tool(
    definition: RemoteSkillDefinition,
    *,
    executor: Callable[..., str],
) -> Callable[..., str]:
    """为单个 RemoteSkill 生成工具函数，真正执行时统一复用 execute_skills。"""

    def remote_skill(
        query: str,
        arguments: dict[str, Any] | None = None,
        tool_context: ToolContext | None = None,
    ) -> str:
        """通过 AgentKit Skills Sandbox 远程执行受保护的 RemoteSkill。"""

        if tool_context is None:
            raise ValueError("tool_context is required for RemoteSkill execution")

        # 本地 Agent 只负责组织 QueryInput；真实 Skill 代码和执行流程都在远端沙箱。
        query_input = {
            "skill_name": definition.name,
            "query": query,
            "arguments": arguments or {},
            "request_id": f"req_{uuid.uuid4().hex}",
        }
        return executor(
            json.dumps(query_input, ensure_ascii=False),
            tool_context=tool_context,
            timeout=definition.timeout,
        )

    remote_skill.__name__ = definition.name
    remote_skill.__doc__ = (
        f"{definition.description}\n\n"
        "RemoteSkill 只暴露能力描述和输入 Schema；真实实现由远端 Skills Sandbox 执行。\n"
        "arguments must follow this JSON schema: "
        f"{json.dumps(definition.input_schema, ensure_ascii=False)}"
    )
    return remote_skill
