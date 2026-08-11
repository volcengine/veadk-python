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
_SKILL_API_TIMEOUT = 1800
_SKILL_API_HEALTH_TIMEOUT = 30.0
_SKILL_API_HEALTH_POLL_INTERVAL = 1.0
_SKILL_API_HEALTH_REQUEST_TIMEOUT = 5.0
_SKILL_INVOCATION_MODE_ENV = "AGENTKIT_SKILL_INVOCATION_MODE"
_SKILL_INVOCATION_MODES = frozenset(
    {"execute", "skill_api", "run_sse", "a2a", "a2a_blocking", "python_agent"}
)
_A2A_POLL_INTERVAL = 2.0
_A2A_REQUEST_TIMEOUT = 60
_A2A_HISTORY_LENGTH = 20
_A2A_TERMINAL_STATES = frozenset(
    {
        "completed",
        "failed",
        "canceled",
        "rejected",
        "input-required",
        "auth-required",
    }
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
    resolved = (mode or os.getenv(_SKILL_INVOCATION_MODE_ENV) or "a2a").strip()
    if not resolved:
        return "a2a"
    normalized = resolved.lower().replace("-", "_")
    if normalized not in _SKILL_INVOCATION_MODES:
        raise ValueError(
            "Unsupported AgentKit Skill invocation mode "
            f"{resolved!r}. Expected one of: "
            "execute, run_sse, a2a, a2a_blocking, python_agent."
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
        if _is_adk_thought_part(part):
            continue
        text = part.get("text")
        if isinstance(text, str):
            chunks.append(text)
            continue
        text_part = part.get("textPart")
        if isinstance(text_part, dict) and isinstance(text_part.get("text"), str):
            chunks.append(text_part["text"])
    return "".join(chunks)


def _is_adk_thought_part(part: dict) -> bool:
    metadata = part.get("metadata")
    return isinstance(metadata, dict) and metadata.get("adk_thought") is True


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


def _a2a_result_task(operation: str, response: object) -> dict:
    if not isinstance(response, dict):
        raise RuntimeError(f"{operation} response JSON is not an object")
    if response.get("error") is not None:
        raise RuntimeError(json.dumps(response["error"], ensure_ascii=False))
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"{operation} response does not contain result task")
    if result.get("kind") != "task" and "status" not in result:
        raise RuntimeError(f"{operation} response result is not an A2A task")
    return result


def _a2a_task_id(task: dict) -> str:
    value = task.get("id")
    if not isinstance(value, str) or not value:
        raise RuntimeError("A2A message/send response task does not contain id")
    return value


def _a2a_task_state(task: dict) -> str | None:
    status = task.get("status")
    if not isinstance(status, dict):
        return None
    state = status.get("state")
    return state if isinstance(state, str) else None


def _a2a_task_result_text(task: dict) -> str:
    artifacts = task.get("artifacts")
    if isinstance(artifacts, list):
        chunks = [
            _extract_text_from_parts(artifact.get("parts"))
            for artifact in artifacts
            if isinstance(artifact, dict)
        ]
        text = "\n".join(chunk for chunk in chunks if chunk)
        if text:
            return text

    status = task.get("status")
    if isinstance(status, dict):
        message = status.get("message")
        if isinstance(message, dict):
            text = _extract_text_from_parts(message.get("parts"))
            if text:
                return text

    history = task.get("history")
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


def _post_a2a_jsonrpc(
    *,
    endpoint: str,
    payload: dict[str, object],
    timeout: int,
) -> dict:
    raw = _post_json(endpoint=endpoint, path="/a2a", payload=payload, timeout=timeout)
    try:
        response = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("A2A JSON-RPC response is not valid JSON") from exc
    if not isinstance(response, dict):
        raise RuntimeError("A2A JSON-RPC response JSON is not an object")
    return response


def _a2a_request_timeout(deadline: float) -> int:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return 0
    return max(1, int(min(_A2A_REQUEST_TIMEOUT, remaining)))


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
    deadline = time.monotonic() + timeout
    message = {
        "kind": "message",
        "messageId": uuid.uuid4().hex,
        "role": "user",
        "parts": [{"kind": "text", "text": workflow_prompt}],
    }
    metadata = {
        "user_id": invocation_context.user_id,
        "session_id": invocation_context.session.id,
    }
    task = _a2a_result_task(
        "A2ASendMessage",
        _post_a2a_jsonrpc(
            endpoint=endpoint,
            payload={
                "jsonrpc": "2.0",
                "id": uuid.uuid4().hex,
                "method": "message/send",
                "params": {
                    "message": message,
                    "metadata": metadata,
                    "configuration": {
                        "blocking": False,
                        "historyLength": _A2A_HISTORY_LENGTH,
                    },
                },
            },
            timeout=_a2a_request_timeout(deadline),
        ),
    )
    task_id = _a2a_task_id(task)

    while _a2a_task_state(task) not in _A2A_TERMINAL_STATES:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Timed out while waiting for A2A task {task_id}")
        time.sleep(min(_A2A_POLL_INTERVAL, remaining))
        task = _a2a_result_task(
            "A2AGetTask",
            _post_a2a_jsonrpc(
                endpoint=endpoint,
                payload={
                    "jsonrpc": "2.0",
                    "id": uuid.uuid4().hex,
                    "method": "tasks/get",
                    "params": {
                        "id": task_id,
                        "historyLength": _A2A_HISTORY_LENGTH,
                    },
                },
                timeout=_a2a_request_timeout(deadline),
            ),
        )

    state = _a2a_task_state(task)
    if state != "completed":
        raise RuntimeError(
            f"A2A task {task_id} ended with state {state}: "
            f"{json.dumps(task, ensure_ascii=False)}"
        )

    text = _a2a_task_result_text(task)
    if text:
        return text
    return json.dumps(task, ensure_ascii=False)


def _execute_skills_via_a2a_blocking(
    *,
    workflow_prompt: str,
    endpoint: str,
    tool_context: ToolContext,
    timeout: int,
) -> str:
    invocation_context = tool_context._invocation_context
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
    response = _post_a2a_jsonrpc(endpoint=endpoint, payload=payload, timeout=timeout)
    if response.get("error"):
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
    if invocation_mode == "a2a_blocking":
        return _execute_skills_via_a2a_blocking(
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
            Supported values are "a2a" (default), "execute", "run_sse",
            "a2a_blocking", and "python_agent". It can also be set with
            AGENTKIT_SKILL_INVOCATION_MODE.
        timeout (int, optional): Maximum execution time in seconds. Defaults to
            1800. The value can be adjusted for each call but must be between 1
            and 1800 seconds.

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
