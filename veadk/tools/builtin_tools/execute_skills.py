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
import uuid
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
_SKILL_INVOCATION_MODE_ENV = "AGENTKIT_SKILL_INVOCATION_MODE"
_SKILL_INVOCATION_MODES = frozenset(
    {"execute", "skill_api", "run_sse", "a2a", "python_agent"}
)


def _validate_timeout(timeout: int) -> None:
    if type(timeout) is not int or not 1 <= timeout <= _SKILL_API_TIMEOUT:
        raise ValueError(
            f"timeout must be an integer between 1 and {_SKILL_API_TIMEOUT} seconds"
        )


def _skill_api_upgrade_hint() -> str:
    return (
        "提示：当前 Skill 沙箱镜像未实现 /v1/skills/execute 接口，"
        "可能是旧版沙箱镜像。"
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


def _resolve_skill_invocation_mode(mode: str | None = None) -> str:
    # 默认保持 /v1/skills/execute；新沙箱可通过参数或环境变量显式切换后端。
    resolved = (mode or os.getenv(_SKILL_INVOCATION_MODE_ENV) or "execute").strip()
    if not resolved:
        return "execute"
    normalized = resolved.lower().replace("-", "_")
    if normalized not in _SKILL_INVOCATION_MODES:
        raise ValueError(
            "Unsupported AgentKit Skill invocation mode "
            f"{resolved!r}. Expected one of: "
            "execute, run_sse, a2a, python_agent."
        )
    return "execute" if normalized == "skill_api" else normalized


def _post_skill_api_json(
    *,
    endpoint: str,
    path: str,
    payload: dict[str, object],
    tip_token_key: str | None,
    timeout: int,
) -> str:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
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
            return _parse_skill_execute_response(response.read())
    except error.HTTPError as exc:
        if exc.code in _SKILL_API_UPGRADE_STATUS_CODES:
            raise RuntimeError(
                f"Skill HTTP API returned HTTP {exc.code}. {_skill_api_upgrade_hint()}"
            ) from exc
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Skill HTTP API request failed with HTTP {exc.code}: {detail}"
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(
            f"Skill HTTP API endpoint is not reachable: {exc.reason}"
        ) from exc


def _post_json(
    *,
    endpoint: str,
    path: str,
    payload: dict[str, object],
    timeout: int,
    accept: str = "application/json",
) -> bytes:
    req = request.Request(
        _skill_api_url(endpoint, path),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": accept},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"AgentKit Skill {path} request failed with HTTP {exc.code}: {detail}"
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(
            f"AgentKit Skill {path} endpoint is not reachable: {exc.reason}"
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


def _run_request_payload(workflow_prompt: str, tool_context: ToolContext) -> dict:
    invocation_context = tool_context._invocation_context
    return {
        "app_name": invocation_context.agent.name,
        "user_id": invocation_context.user_id,
        "session_id": invocation_context.session.id,
        "new_message": {
            "role": "user",
            "parts": [{"text": workflow_prompt}],
        },
        "streaming": True,
    }


def _extract_text_from_parts(parts: object) -> str:
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str):
            chunks.append(text)
            continue
        text_part = part.get("textPart")
        if isinstance(text_part, dict) and isinstance(text_part.get("text"), str):
            chunks.append(text_part["text"])
    return "".join(chunks)


def _extract_text_from_a2a_result(result: object) -> str:
    if not isinstance(result, dict):
        return ""
    if result.get("kind") == "message":
        return _extract_text_from_parts(result.get("parts"))
    artifacts = result.get("artifacts")
    if isinstance(artifacts, list):
        chunks = [
            _extract_text_from_parts(artifact.get("parts"))
            for artifact in artifacts
            if isinstance(artifact, dict)
        ]
        text = "".join(chunks)
        if text:
            return text
    history = result.get("history")
    if isinstance(history, list):
        for message in reversed(history):
            if isinstance(message, dict) and message.get("role") in {
                "agent",
                "assistant",
            }:
                text = _extract_text_from_parts(message.get("parts"))
                if text:
                    return text
    return ""


def _parse_run_sse_response(raw: bytes) -> str:
    chunks: list[str] = []
    for raw_line in raw.splitlines():
        line = raw_line.decode("utf-8", errors="replace")
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and isinstance(event.get("error"), str):
            raise RuntimeError(event["error"])
        if not isinstance(event, dict):
            continue
        content = event.get("content")
        if isinstance(content, dict):
            text = _extract_text_from_parts(content.get("parts"))
            if text:
                chunks.append(text)
    return "".join(chunks)


def _execute_skills_via_run_sse(
    *,
    workflow_prompt: str,
    endpoint: str,
    tool_context: ToolContext,
    timeout: int,
) -> str:
    # run_sse 复用 ADK 运行入口，适配只暴露 ADK Runtime 接口的 Skill 沙箱。
    raw = _post_json(
        endpoint=endpoint,
        path="/run_sse",
        payload=_run_request_payload(workflow_prompt, tool_context),
        timeout=timeout,
        accept="text/event-stream",
    )
    return _parse_run_sse_response(raw)


def _execute_skills_via_a2a(
    *,
    workflow_prompt: str,
    endpoint: str,
    tool_context: ToolContext,
    timeout: int,
) -> str:
    invocation_context = tool_context._invocation_context
    # A2A 沙箱使用 JSON-RPC message/send，同步等待最终结果。
    payload = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "messageId": uuid.uuid4().hex,
                "role": "user",
                "parts": [{"kind": "text", "text": workflow_prompt}],
            },
            "metadata": {
                "user_id": invocation_context.user_id,
                "session_id": invocation_context.session.id,
            },
            "configuration": {"blocking": True},
        },
    }
    raw = _post_json(endpoint=endpoint, path="/a2a", payload=payload, timeout=timeout)
    response = json.loads(raw.decode("utf-8"))
    if isinstance(response, dict) and response.get("error"):
        raise RuntimeError(json.dumps(response["error"], ensure_ascii=False))
    result = response.get("result") if isinstance(response, dict) else None
    text = _extract_text_from_a2a_result(result)
    if text:
        return text
    return json.dumps(result, ensure_ascii=False)


def _execute_skills_via_python_agent(
    *,
    workflow_prompt: str,
    tool_id: str,
    tool_context: ToolContext,
    timeout: int,
    env_vars: Optional[dict[str, str]] = None,
) -> str:
    # python_agent 是旧版 RunCode 路径，本质是在沙箱内执行 python agent.py。
    account_id = get_agentkit_account_id(tool_context.state)
    extra_env_vars = dict(env_vars or {})
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


def _execute_skills_via_skill_api(
    *,
    workflow_prompt: str,
    tool_id: str,
    tool_context: ToolContext,
    timeout: int,
    invocation_mode: str,
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

    if invocation_mode == "run_sse":
        return _execute_skills_via_run_sse(
            workflow_prompt=workflow_prompt,
            endpoint=endpoint,
            tool_context=tool_context,
            timeout=timeout,
        )
    if invocation_mode == "a2a":
        return _execute_skills_via_a2a(
            workflow_prompt=workflow_prompt,
            endpoint=endpoint,
            tool_context=tool_context,
            timeout=timeout,
        )

    _wait_for_skill_api_health(endpoint=endpoint)
    return _post_skill_api_json(
        endpoint=endpoint,
        path="/v1/skills/execute",
        payload={"prompt": workflow_prompt},
        tip_token_key=_tip_token_key(tool_context),
        timeout=timeout,
    )


def execute_skills(
    workflow_prompt: str,
    tool_context: ToolContext = None,
    env_vars: Optional[dict[str, str]] = None,
    invocation_mode: Optional[str] = None,
    timeout: int = _SKILL_API_TIMEOUT,
) -> str:
    """Execute skills in a sandbox and return the output.

    Execute skills in a remote sandbox amining to provide isolation and security.

    Args:
        workflow_prompt (str): instruction of workflow
        env_vars (Optional[dict[str, str]]): Environment variables passed to the
            skill agent process for this execution only. Requests with custom
            environment variables use the legacy RunCode execution path.
        invocation_mode (Optional[str]): AgentKit Skill sandbox invocation backend.
            Supported values are "execute" (default), "run_sse", "a2a", and
            "python_agent". It can also be set with AGENTKIT_SKILL_INVOCATION_MODE.
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
        # env_vars 依赖进程级环境变量注入，只能走 legacy python agent.py 路径。
        return _execute_skills_via_python_agent(
            workflow_prompt=workflow_prompt,
            tool_id=tool_id,
            tool_context=tool_context,
            timeout=timeout,
            env_vars=env_vars,
        )

    mode = _resolve_skill_invocation_mode(invocation_mode)
    if mode == "python_agent":
        return _execute_skills_via_python_agent(
            workflow_prompt=workflow_prompt,
            tool_id=tool_id,
            tool_context=tool_context,
            timeout=timeout,
        )

    return _execute_skills_via_skill_api(
        workflow_prompt=workflow_prompt,
        tool_id=tool_id,
        tool_context=tool_context,
        timeout=timeout,
        invocation_mode=mode,
    )
