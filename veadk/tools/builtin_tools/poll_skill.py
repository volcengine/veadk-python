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

import time
import uuid

from google.adk.tools import ToolContext

from veadk.tools.builtin_tools._agentkit import (
    ensure_agentkit_session_endpoint,
    resolve_agentkit_tool_id,
)
from veadk.tools.builtin_tools.execute_skills import (
    _A2A_HISTORY_LENGTH,
    _a2a_request_timeout,
    _a2a_result_task,
    _inbound_auth_token,
    _post_a2a_jsonrpc,
    _tool_user_session_id,
    _validate_timeout,
)


def poll_skill(
    task_id: str,
    tool_context: ToolContext = None,
    timeout: int = 1800,
) -> dict:
    """Fetch one A2A skill task status snapshot."""
    if tool_context is None:
        raise ValueError("tool_context is required for poll_skill")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("task_id is required for poll_skill")
    _validate_timeout(timeout)

    tool_id = resolve_agentkit_tool_id("AGENTKIT_TOOL_ID_SKILLS")
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

    deadline = time.monotonic() + timeout
    return _a2a_result_task(
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
            inbound_auth=_inbound_auth_token(tool_context),
        ),
    )
