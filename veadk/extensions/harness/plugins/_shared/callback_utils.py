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

"""Shared helpers for Harness Runner plugin callback objects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from veadk.extensions.harness.schemas import (
    ConversationMessage,
    HarnessInvocationRef,
    TaskContract,
)
from veadk.extensions.harness.utils import stringify_json_value

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.tool_context import ToolContext


def run_context_from_callback(
    callback_context: "CallbackContext",
    *,
    profile: str,
) -> HarnessInvocationRef:
    session = callback_context.session
    goal = user_text_from_callback(callback_context)
    return HarnessInvocationRef(
        app_name=getattr(session, "app_name", ""),
        user_id=getattr(callback_context, "user_id", ""),
        session_id=getattr(session, "id", ""),
        invocation_id=getattr(callback_context, "invocation_id", ""),
        profile=profile,
        task=TaskContract(goal=goal) if goal else None,
    )


def run_context_from_invocation(
    invocation_context: "InvocationContext",
    *,
    profile: str,
) -> HarnessInvocationRef:
    session = invocation_context.session
    return HarnessInvocationRef(
        app_name=getattr(session, "app_name", ""),
        user_id=getattr(session, "user_id", ""),
        session_id=getattr(session, "id", ""),
        invocation_id=getattr(invocation_context, "invocation_id", ""),
        profile=profile,
    )


def run_context_from_tool(
    tool_context: "ToolContext",
    *,
    profile: str,
) -> HarnessInvocationRef:
    session = tool_context.session
    return HarnessInvocationRef(
        app_name=getattr(session, "app_name", ""),
        user_id=getattr(tool_context, "user_id", ""),
        session_id=getattr(session, "id", ""),
        invocation_id=getattr(tool_context, "invocation_id", ""),
        profile=profile,
    )


def user_text_from_callback(callback_context: "CallbackContext") -> str:
    user_content = getattr(callback_context, "user_content", None)
    return stringify_json_value(user_content.model_dump()) if user_content else ""


def message_from_text(role: str, text: str) -> ConversationMessage:
    return ConversationMessage(role=role, content=text)


def tool_name(tool: "BaseTool") -> str:
    return str(getattr(tool, "name", tool.__class__.__name__))


def looks_like_error_result(result: Mapping[str, object]) -> bool:
    if "error" in result or "exception" in result:
        return True
    status = str(result.get("status", "")).lower()
    return status in {"error", "failed", "failure"}
