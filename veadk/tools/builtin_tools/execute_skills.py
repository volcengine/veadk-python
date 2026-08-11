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
import time
import uuid
from typing import Optional
from urllib import error, request
from urllib.parse import urlsplit, urlunsplit

from google.adk.tools import ToolContext

from veadk.tools.builtin_tools._agentkit import (
    ensure_agentkit_session_endpoint,
    resolve_agentkit_tool_id,
)

_SKILL_API_TIMEOUT = 1800
_A2A_POLL_INTERVAL = 2.0
_A2A_REQUEST_TIMEOUT = 60
_A2A_HISTORY_LENGTH = 20
_A2A_RETRY_STATUS_CODES = frozenset({502, 503, 504})
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


def _tool_user_session_id(tool_context: ToolContext) -> str:
    invocation_context = tool_context._invocation_context
    session_id = invocation_context.session.id
    agent_name = invocation_context.agent.name
    user_id = invocation_context.user_id
    return agent_name + "_" + user_id + "_" + session_id


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


def _a2a_jsonrpc_url(endpoint: str) -> str:
    if not endpoint:
        raise RuntimeError("AgentKit session endpoint is empty")
    parts = urlsplit(endpoint)
    normalized_path = parts.path.rstrip("/")
    if normalized_path.endswith("/a2a"):
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                normalized_path,
                parts.query,
                parts.fragment,
            )
        )
    return _skill_api_url(endpoint, "/a2a")


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
    retry_until: float | None = None,
) -> dict:
    url = _a2a_jsonrpc_url(endpoint)
    while True:
        request_timeout = (
            _a2a_request_timeout(retry_until) if retry_until is not None else timeout
        )
        if request_timeout <= 0:
            raise TimeoutError("Timed out while waiting for A2A endpoint")
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=request_timeout) as response:
                raw = response.read()
            break
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in _A2A_RETRY_STATUS_CODES and retry_until is not None:
                remaining = retry_until - time.monotonic()
                if remaining > 0:
                    time.sleep(min(_A2A_POLL_INTERVAL, remaining))
                    continue
            raise RuntimeError(
                f"AgentKit Skill /a2a request failed with HTTP {exc.code}: {detail}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(
                f"AgentKit Skill /a2a endpoint is not reachable: {exc.reason}"
            ) from exc
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
            retry_until=deadline,
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
                retry_until=deadline,
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


def _execute_skills_via_skill_api(
    *,
    workflow_prompt: str,
    tool_id: str,
    tool_context: ToolContext,
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

    return _execute_skills_via_a2a(
        workflow_prompt=workflow_prompt,
        endpoint=endpoint,
        tool_context=tool_context,
        timeout=timeout,
    )


def execute_skills(
    workflow_prompt: str,
    tool_context: ToolContext = None,
    env_vars: Optional[dict[str, str]] = None,
    timeout: int = _SKILL_API_TIMEOUT,
) -> str:
    """Execute skills in a sandbox and return the output.

    Execute skills in a remote sandbox amining to provide isolation and security.

    Args:
        workflow_prompt (str): instruction of workflow
        env_vars (Optional[dict[str, str]]): Unsupported. AgentKit Skill execution
            uses A2A and does not support per-call process environment injection.
        timeout (int, optional): Maximum execution time in seconds. Defaults to
            1800. The value can be adjusted for each call but must be between 1
            and 1800 seconds.

    Returns:
        str: The output of the code execution.
    """
    if tool_context is None:
        raise ValueError("tool_context is required for execute_skills")
    _validate_timeout(timeout)
    if env_vars is not None:
        raise ValueError("env_vars is not supported for execute_skills A2A execution")

    tool_id = resolve_agentkit_tool_id("AGENTKIT_TOOL_ID_SKILLS")
    return _execute_skills_via_skill_api(
        workflow_prompt=workflow_prompt,
        tool_id=tool_id,
        tool_context=tool_context,
        timeout=timeout,
    )
