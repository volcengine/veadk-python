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


def invoke_skill(
    workflow_prompt: str,
    tool_context: ToolContext = None,
    timeout: int = 1800,
) -> dict:
    """Create an A2A skill task and return the initial task object."""
    if tool_context is None:
        raise ValueError("tool_context is required for invoke_skill")
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

    invocation_context = tool_context._invocation_context
    deadline = time.monotonic() + timeout
    inbound_auth = _inbound_auth_token(tool_context)

    return _a2a_result_task(
        "A2ASendMessage",
        _post_a2a_jsonrpc(
            endpoint=endpoint,
            payload={
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
                    "configuration": {
                        "blocking": False,
                        "historyLength": _A2A_HISTORY_LENGTH,
                    },
                },
            },
            timeout=_a2a_request_timeout(deadline),
            retry_until=deadline,
            inbound_auth=inbound_auth,
        ),
    )
