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
"""Audit ADK skill content before it can activate or execute.

ADK's ``LoadSkillTool`` writes activation state inside ``run_async``, so an
``after_tool`` rejection cannot prevent activation. This adapter wraps the
skill tools and audits their actual body/resource/script before delegating to
the original implementation, which keeps rejection side-effect free.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from google.adk.tools import BaseTool
from google.adk.tools.skill_toolset import (
    ListSkillsTool,
    LoadSkillResourceTool,
    LoadSkillTool,
    RunSkillScriptTool,
    SearchSkillsTool,
    SkillToolset,
)

from ..config import DEFAULT_BLOCK_MESSAGE

SkillAudit = Callable[[str, str], Awaitable[bool]]
"""``(invocation_id, text) -> allowed``."""


class SkillAuditUnavailable(RuntimeError):
    """The adapter could not obtain the skill content to audit.

    Skill execution is fail-closed: if the content cannot be fetched before
    the wrapped tool runs, the call is rejected rather than delegated
    unaudited.
    """


class AuditedSkillToolset(SkillToolset):
    """A ``SkillToolset`` whose load/resource/script tools are pre-audited.

    ``audit`` is called with the text that would cross the trust boundary. A
    ``False`` result returns a tool error and never calls the wrapped tool, so
    no activation state is written and no script runs.

    Example::

        plugin = build_content_safety(config)
        toolset = AuditedSkillToolset(
            skills=[...],
            audit=plugin.audit_skill_text,
            block_message=plugin.block_message,
        )
    """

    def __init__(
        self,
        *args: Any,
        audit: SkillAudit,
        block_message: str = DEFAULT_BLOCK_MESSAGE,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self._audit = audit
        self._block_message = block_message

    async def get_tools(self, readonly_context: Any = None) -> list[BaseTool]:
        tools = await super().get_tools(readonly_context)
        return [self._wrap(tool) for tool in tools]

    def _wrap(self, tool: BaseTool) -> BaseTool:
        if isinstance(tool, (LoadSkillTool, LoadSkillResourceTool, RunSkillScriptTool)):
            return _AuditedSkillTool(
                tool, audit=self._audit, block_message=self._block_message
            )
        if isinstance(tool, (ListSkillsTool, SearchSkillsTool)):
            return _AuditedResultTool(
                tool, audit=self._audit, block_message=self._block_message
            )
        return tool


class _AuditedSkillTool(BaseTool):
    def __init__(
        self,
        inner: BaseTool,
        *,
        audit: SkillAudit,
        block_message: str,
    ):
        super().__init__(name=inner.name, description=inner.description)
        self._inner = inner
        self._audit = audit
        self._block_message = block_message

    def _get_declaration(self) -> Any:
        return self._inner._get_declaration()

    async def run_async(self, *, args: dict[str, Any], tool_context: Any) -> Any:
        try:
            text = await _skill_audit_text(self._inner, args, tool_context)
        except SkillAuditUnavailable:
            return {"error": self._block_message, "blocked": True}
        if text:
            allowed = await self._audit(tool_context.invocation_id, text)
            if not allowed:
                return {"error": self._block_message, "blocked": True}
        return await self._inner.run_async(args=args, tool_context=tool_context)


class _AuditedResultTool(BaseTool):
    """Audit a read-only skill metadata tool's result before returning it.

    Listing/searching has no side effects, so the result can be audited after
    the inner call. A rejected result is replaced by a tool error and never
    reaches the model.
    """

    def __init__(
        self,
        inner: BaseTool,
        *,
        audit: SkillAudit,
        block_message: str,
    ):
        super().__init__(name=inner.name, description=inner.description)
        self._inner = inner
        self._audit = audit
        self._block_message = block_message

    def _get_declaration(self) -> Any:
        return self._inner._get_declaration()

    async def run_async(self, *, args: dict[str, Any], tool_context: Any) -> Any:
        result = await self._inner.run_async(args=args, tool_context=tool_context)
        text = _result_audit_text(self._inner, result)
        if text:
            allowed = await self._audit(tool_context.invocation_id, text)
            if not allowed:
                return {"error": self._block_message, "blocked": True}
        return result


def _result_audit_text(inner: BaseTool, result: Any) -> str:
    if isinstance(inner, ListSkillsTool):
        if isinstance(result, str) and result:
            return f"[skill_list]\n{result}"
        return ""
    if isinstance(inner, SearchSkillsTool):
        if isinstance(result, list) and result:
            return (
                "[skill_search]\n"
                f"{json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)}"
            )
        return ""
    return ""


async def _skill_audit_text(
    inner: BaseTool, args: dict[str, Any], tool_context: Any
) -> str:
    skill_name = args.get("skill_name")
    if not skill_name:
        return ""
    try:
        skill = await inner._toolset._get_or_fetch_skill(
            skill_name, tool_context.invocation_id
        )
    except Exception as exc:
        raise SkillAuditUnavailable(
            f"cannot fetch skill {skill_name!r} for pre-execution audit"
        ) from exc
    if skill is None:
        return ""

    if isinstance(inner, LoadSkillTool):
        frontmatter = skill.frontmatter.model_dump()
        return (
            "[skill_metadata]\n"
            f"{json.dumps(frontmatter, ensure_ascii=False, sort_keys=True, default=str)}"
            f"\n[skill_body]\n{skill.instructions}"
        )

    file_path = args.get("file_path")
    if not file_path:
        return ""

    if isinstance(inner, LoadSkillResourceTool):
        content: str | bytes | None = None
        if file_path.startswith("references/"):
            content = skill.resources.get_reference(file_path[len("references/") :])
        elif file_path.startswith("assets/"):
            content = skill.resources.get_asset(file_path[len("assets/") :])
        elif file_path.startswith("scripts/"):
            script = skill.resources.get_script(file_path[len("scripts/") :])
            content = script.src if script is not None else None
        if content is None:
            return ""
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        return f"[skill_resource]\n{file_path}\n{content}"

    if isinstance(inner, RunSkillScriptTool):
        script = skill.resources.get_script(
            file_path[len("scripts/") :]
            if file_path.startswith("scripts/")
            else file_path
        )
        if script is None:
            return ""
        return (
            f"[skill_script]\n{file_path}\n{script.src}\n[args]\n"
            f"{json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)}"
        )

    return ""
