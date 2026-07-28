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
from typing import Optional
from urllib import error, request
from urllib.parse import urlsplit, urlunsplit

from google.adk.tools import ToolContext

from veadk.tools.builtin_tools._agentkit import (
    ensure_agentkit_session_endpoint,
    get_agentkit_account_id,
    resolve_agentkit_tool_id,
)
from veadk.tools.builtin_tools.run_sandbox_agent import run_sandbox_agent
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


_SKILL_API_UPGRADE_STATUS_CODES = frozenset({404})
_SKILL_API_TIMEOUT = 900

_SKILL_API_UPGRADE_HINT = (
    "提示：当前 Skill 沙箱镜像未实现 Skill HTTP API "
    "(/v1/skills/execute|stream)，可能是旧版沙箱镜像。"
    "请升级 Skill 沙箱镜像或切换到支持 Skill HTTP API 的新版沙箱。"
)

_SKILL_STREAM_MISSING_HINT = (
    "提示：当前 Skill 沙箱镜像未实现 /v1/skills/stream 接口（HTTP 404）。"
    "请升级 Skill 沙箱镜像到支持 /v1/skills/stream 的新版沙箱。"
)


class _SkillApiCompatibilityMiss(Exception):
    """Raised when the sandbox endpoint is unreachable so legacy fallback should apply."""


class _SkillApiUpgradeRequired(Exception):
    """Raised when the sandbox is reachable but does not expose the Skill HTTP API."""


def _tool_user_session_id(tool_context: ToolContext) -> str:
    invocation_context = tool_context._invocation_context
    session_id = invocation_context.session.id
    agent_name = invocation_context.agent.name
    user_id = invocation_context.user_id
    return agent_name + "_" + user_id + "_" + session_id


def _tip_token_key(tool_context: ToolContext | None) -> str | None:
    if tool_context is None:
        return os.getenv("TIP_TOKEN_KEY") or None
    state = tool_context.state or {}
    return (
        state.get("TIP_TOKEN_KEY")
        or state.get("tip_token_key")
        or os.getenv("TIP_TOKEN_KEY")
        or None
    )


def _skill_api_enabled(env_vars: Optional[dict[str, str]]) -> bool:
    protocol = os.getenv("VEADK_EXECUTE_SKILLS_PROTOCOL", "auto").strip().lower()
    if protocol in {"legacy", "runcode", "run_code"}:
        return False
    # Per-execution env vars are guaranteed by the legacy RunCode path. The new
    # Skill HTTP API does not accept arbitrary per-request env overrides.
    return not env_vars


def _skill_api_url(endpoint: str, path: str) -> str:
    if not endpoint:
        raise _SkillApiCompatibilityMiss("AgentKit session endpoint is empty")
    parts = urlsplit(endpoint)
    endpoint_path = parts.path.rstrip("/")
    skill_path = path.lstrip("/")
    joined_path = f"{endpoint_path}/{skill_path}" if endpoint_path else f"/{skill_path}"
    return urlunsplit(
        (parts.scheme, parts.netloc, joined_path, parts.query, parts.fragment)
    )


def _post_skill_api_json(
    *,
    endpoint: str,
    path: str,
    payload: dict[str, object],
    tip_token_key: str | None,
    timeout: int,
) -> bytes:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if tip_token_key:
        headers["X-Tip-Token-Key"] = tip_token_key

    req = request.Request(
        _skill_api_url(endpoint, path),
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except error.HTTPError as exc:
        if exc.code in _SKILL_API_UPGRADE_STATUS_CODES:
            hint = (
                _SKILL_STREAM_MISSING_HINT
                if path.rstrip("/").endswith("/v1/skills/stream")
                else _SKILL_API_UPGRADE_HINT
            )
            raise _SkillApiUpgradeRequired(
                f"Skill HTTP API returned HTTP {exc.code}. {hint}"
            ) from exc
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Skill HTTP API request failed with HTTP {exc.code}: {detail}"
        ) from exc
    except error.URLError as exc:
        raise _SkillApiCompatibilityMiss(
            f"Skill HTTP API endpoint is not reachable: {exc.reason}"
        ) from exc


def _parse_skill_execute_response(raw: bytes) -> str:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return raw.decode("utf-8", errors="replace")

    if isinstance(payload, dict):
        if isinstance(payload.get("content"), str):
            return payload["content"]
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("content"), str):
            return data["content"]
    return json.dumps(payload, ensure_ascii=False)


def _parse_skill_stream_response(raw: bytes) -> str:
    chunks: list[str] = []
    event_name = "message"
    data_lines: list[str] = []

    def flush_event() -> None:
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = "message"
            return
        data = "\n".join(data_lines)
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            payload = {}

        if event_name == "error":
            content = payload.get("content") if isinstance(payload, dict) else None
            if isinstance(content, str):
                raise RuntimeError(content)
            raise RuntimeError(data)
        if isinstance(payload, dict) and payload.get("type") == "text":
            content = payload.get("content")
            if isinstance(content, str):
                chunks.append(content)

        event_name = "message"
        data_lines = []

    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line:
            flush_event()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())

    flush_event()
    return "".join(chunks)


def _execute_skills_via_skill_api(
    *,
    workflow_prompt: str,
    tool_id: str,
    tool_context: ToolContext,
    prefer_stream: bool,
    timeout: int,
) -> str:
    try:
        endpoint = ensure_agentkit_session_endpoint(
            tool_id=tool_id,
            tool_user_session_id=_tool_user_session_id(tool_context),
            tool_state=tool_context.state if tool_context else None,
            ttl=max(timeout, 1800),
        )
    except Exception as exc:
        raise _SkillApiCompatibilityMiss(
            f"AgentKit session endpoint is not available: {exc}"
        ) from exc
    path = "/v1/skills/stream" if prefer_stream else "/v1/skills/execute"
    raw = _post_skill_api_json(
        endpoint=endpoint,
        path=path,
        payload={"prompt": workflow_prompt},
        tip_token_key=_tip_token_key(tool_context),
        timeout=timeout,
    )
    if prefer_stream:
        return _parse_skill_stream_response(raw)
    return _parse_skill_execute_response(raw)


def execute_skills(
    workflow_prompt: str,
    tool_context: ToolContext = None,
    env_vars: Optional[dict[str, str]] = None,
    prefer_stream: bool = False,
) -> str:
    """Execute skills in a sandbox and return the output.

    Execute skills in a remote sandbox amining to provide isolation and security.

    Args:
        workflow_prompt (str): instruction of workflow
        env_vars (Optional[dict[str, str]]): Environment variables passed to the
            skill agent process for this execution only.

    Returns:
        str: The output of the code execution.
    """
    timeout = _SKILL_API_TIMEOUT
    tool_id = resolve_agentkit_tool_id("AGENTKIT_TOOL_ID_SKILLS")

    if tool_context is not None and _skill_api_enabled(env_vars):
        try:
            return _execute_skills_via_skill_api(
                workflow_prompt=workflow_prompt,
                tool_id=tool_id,
                tool_context=tool_context,
                prefer_stream=prefer_stream,
                timeout=timeout,
            )
        except _SkillApiUpgradeRequired as exc:
            raise RuntimeError(str(exc)) from exc
        except _SkillApiCompatibilityMiss as exc:
            logger.warning(
                f"Skill HTTP API endpoint unreachable, falling back to legacy RunCode: {exc}"
            )

    account_id = get_agentkit_account_id(tool_context.state if tool_context else None)
    extra_env_vars = {}
    if account_id:
        extra_env_vars["TOS_SKILLS_DIR"] = (
            f"tos://agentkit-platform-{account_id}/skills/"
        )
    if env_vars:
        extra_env_vars.update(env_vars)

    return run_sandbox_agent(
        workflow_prompt=workflow_prompt,
        tool_id=tool_id,
        tool_context=tool_context,
        timeout=timeout,
        extra_env_vars=extra_env_vars,
    )
