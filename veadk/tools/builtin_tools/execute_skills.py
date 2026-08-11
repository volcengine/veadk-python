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
import time
from collections.abc import Iterable
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


_SKILL_API_UPGRADE_STATUS_CODES = frozenset({404, 405})
_SKILL_API_TRANSIENT_STATUS_CODES = frozenset({502, 503, 504})
_SKILL_API_TIMEOUT = 900
_SKILL_API_HEALTH_TIMEOUT = 30.0
_SKILL_API_HEALTH_POLL_INTERVAL = 1.0
_SKILL_API_HEALTH_REQUEST_TIMEOUT = 5.0


def _validate_timeout(timeout: int) -> None:
    if type(timeout) is not int or not 1 <= timeout <= _SKILL_API_TIMEOUT:
        raise ValueError(
            f"timeout must be an integer between 1 and {_SKILL_API_TIMEOUT} seconds"
        )


def _skill_api_upgrade_hint(path: str) -> str:
    api_path = (
        "/v1/skills/stream"
        if path.rstrip("/").endswith("/stream")
        else "/v1/skills/execute"
    )
    return (
        f"提示：当前 Skill 沙箱镜像未实现 {api_path} 接口，可能是旧版沙箱镜像。"
        "请升级 Skill 沙箱镜像或切换到支持 Skill HTTP API 的新版沙箱。"
    )


def _tool_user_session_id(tool_context: ToolContext) -> str:
    invocation_context = tool_context._invocation_context
    session_id = invocation_context.session.id
    agent_name = invocation_context.agent.name
    user_id = invocation_context.user_id
    return agent_name + "_" + user_id + "_" + session_id


def _tip_token_key(tool_context: ToolContext) -> str | None:
    state = tool_context.state or {}
    return (
        state.get("TIP_TOKEN_KEY")
        or state.get("tip_token_key")
        or os.getenv("TIP_TOKEN_KEY")
        or None
    )


def _skill_api_url(endpoint: str, path: str) -> str:
    if not endpoint:
        raise RuntimeError("AgentKit session endpoint is empty")
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
    stream: bool,
) -> str:
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
            if stream:
                return _parse_skill_stream_response(response)
            return _parse_skill_execute_response(response.read())
    except error.HTTPError as exc:
        if exc.code in _SKILL_API_UPGRADE_STATUS_CODES:
            raise RuntimeError(
                f"Skill HTTP API returned HTTP {exc.code}. "
                f"{_skill_api_upgrade_hint(path)}"
            ) from exc
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Skill HTTP API request failed with HTTP {exc.code}: {detail}"
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(
            f"Skill HTTP API endpoint is not reachable: {exc.reason}"
        ) from exc


def _wait_for_skill_api_health(
    *,
    endpoint: str,
    timeout: float = _SKILL_API_HEALTH_TIMEOUT,
    poll_interval: float = _SKILL_API_HEALTH_POLL_INTERVAL,
) -> None:
    """Wait until the Skill API upstream is reachable through the session endpoint."""
    deadline = time.monotonic() + timeout
    last_error = "unknown error"
    while True:
        req = request.Request(
            _skill_api_url(endpoint, "/v1/skills/healthz"),
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            remaining = max(0.001, deadline - time.monotonic())
            with request.urlopen(
                req,
                timeout=min(_SKILL_API_HEALTH_REQUEST_TIMEOUT, remaining),
            ):
                return
        except error.HTTPError as exc:
            if exc.code in _SKILL_API_UPGRADE_STATUS_CODES:
                # Some compatible images predate the dedicated health endpoint.
                return
            if exc.code not in _SKILL_API_TRANSIENT_STATUS_CODES:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Skill HTTP API health check failed with HTTP {exc.code}: {detail}"
                ) from exc
            last_error = f"HTTP {exc.code}"
        except error.URLError as exc:
            last_error = str(exc.reason)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"Timed out waiting for Skill HTTP API health check: {last_error}"
            )
        time.sleep(min(poll_interval, remaining))


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


def _parse_skill_stream_response(raw: bytes | Iterable[bytes]) -> str:
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

    raw_lines = raw.splitlines() if isinstance(raw, bytes) else raw
    for raw_line in raw_lines:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
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
            tool_state=tool_context.state,
            ttl=max(timeout, 1800),
            wait_until_ready=True,
        )
    except Exception as exc:
        raise RuntimeError(
            f"AgentKit session endpoint is not available: {exc}"
        ) from exc
    _wait_for_skill_api_health(endpoint=endpoint)
    path = "/v1/skills/stream" if prefer_stream else "/v1/skills/execute"
    return _post_skill_api_json(
        endpoint=endpoint,
        path=path,
        payload={"prompt": workflow_prompt},
        tip_token_key=_tip_token_key(tool_context),
        timeout=timeout,
        stream=prefer_stream,
    )


def execute_skills(
    workflow_prompt: str,
    tool_context: ToolContext = None,
    env_vars: Optional[dict[str, str]] = None,
    prefer_stream: bool = False,
    timeout: int = _SKILL_API_TIMEOUT,
) -> str:
    """Execute skills in a sandbox and return the output.

    Execute skills in a remote sandbox amining to provide isolation and security.

    Args:
        workflow_prompt (str): instruction of workflow
        env_vars (Optional[dict[str, str]]): Environment variables passed to the
            skill agent process for this execution only. Requests with custom
            environment variables use the legacy RunCode execution path.
        timeout (int, optional): Maximum execution time in seconds. Defaults to
            900. The value can be adjusted for each call but must be between 1
            and 900 seconds.

    Returns:
        str: The output of the code execution.
    """
    if tool_context is None:
        raise ValueError("tool_context is required for execute_skills")
    _validate_timeout(timeout)

    tool_id = resolve_agentkit_tool_id("AGENTKIT_TOOL_ID_SKILLS")
    if env_vars:
        account_id = get_agentkit_account_id(tool_context.state)
        extra_env_vars = dict(env_vars)
        if account_id:
            extra_env_vars.setdefault(
                "TOS_SKILLS_DIR",
                f"tos://agentkit-platform-{account_id}/skills/",
            )
        return run_sandbox_agent(
            workflow_prompt=workflow_prompt,
            tool_id=tool_id,
            tool_context=tool_context,
            timeout=timeout,
            extra_env_vars=extra_env_vars,
        )

    return _execute_skills_via_skill_api(
        workflow_prompt=workflow_prompt,
        tool_id=tool_id,
        tool_context=tool_context,
        prefer_stream=prefer_stream,
        timeout=timeout,
    )
