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

"""Compatibility helpers for AgentKit Session display-name metadata."""

from __future__ import annotations

from typing import Any

from agentkit.sdk.tools import types as tools_types
from pydantic import Field

SESSION_DISPLAY_NAME_MAX_LENGTH = 40
SESSION_DISPLAY_NAME_METADATA_KEY = "veadk_display_name"


class _SessionMetadata(tools_types.ToolsBaseModel):
    key: str = Field(alias="Key")
    type: str = Field(default="String", alias="Type")
    value: str = Field(alias="Value")


class _CreateSessionRequestCompat(tools_types.CreateSessionRequest):
    metadata: list[_SessionMetadata] | None = Field(default=None, alias="Metadata")


class _GetSessionResponseCompat(tools_types.ToolsBaseModel):
    created_at: str | None = Field(default=None, alias="CreatedAt")
    endpoint: str | None = Field(default=None, alias="Endpoint")
    expire_at: str | None = Field(default=None, alias="ExpireAt")
    internal_endpoint: str | None = Field(default=None, alias="InternalEndpoint")
    session_id: str | None = Field(default=None, alias="SessionId")
    status: str | None = Field(default=None, alias="Status")
    tool_type: str | None = Field(default=None, alias="ToolType")
    user_session_id: str | None = Field(default=None, alias="UserSessionId")
    metadata: list[_SessionMetadata] | None = Field(default=None, alias="Metadata")


class _SessionInfoCompat(_GetSessionResponseCompat):
    pass


class _ListSessionsResponseCompat(tools_types.ToolsBaseModel):
    next_token: str | None = Field(default=None, alias="NextToken")
    session_infos: list[_SessionInfoCompat] | None = Field(
        default=None,
        alias="SessionInfos",
    )


def _model_supports_alias(model: Any, alias: str) -> bool:
    fields = getattr(model, "model_fields", {})
    return any(getattr(field, "alias", None) == alias for field in fields.values())


def build_create_session_request(
    *,
    tool_id: str,
    ttl_seconds: int,
    user_session_id: str,
    display_name: str,
) -> Any:
    """Build a native or compatibility CreateSession request."""
    request_type: Any = tools_types.CreateSessionRequest
    if display_name and not _model_supports_alias(request_type, "Metadata"):
        request_type = _CreateSessionRequestCompat
    request_data: dict[str, Any] = {
        "ToolId": tool_id,
        "Ttl": ttl_seconds,
        "TtlUnit": "second",
        "UserSessionId": user_session_id,
    }
    if display_name:
        request_data["Metadata"] = [
            _SessionMetadata(
                Key=SESSION_DISPLAY_NAME_METADATA_KEY,
                Type="String",
                Value=display_name,
            )
        ]
    return request_type(**request_data)


def call_session_client(client: Any, method_name: str, request: Any) -> Any:
    """Invoke a Session API while preserving Metadata on older SDK releases."""
    native_response_model: Any | None = None
    compat_response_model: Any | None = None
    api_action = ""
    if method_name == "get_session":
        native_response_model = tools_types.GetSessionResponse
        compat_response_model = _GetSessionResponseCompat
        api_action = "GetSession"
    elif method_name == "list_sessions":
        native_response_model = tools_types.SessionInfosForListSessions
        compat_response_model = _ListSessionsResponseCompat
        api_action = "ListSessions"

    invoke_api = getattr(client, "_invoke_api", None)
    if (
        native_response_model is not None
        and compat_response_model is not None
        and not _model_supports_alias(native_response_model, "Metadata")
        and callable(invoke_api)
    ):
        return invoke_api(
            api_action=api_action,
            request=request,
            response_type=compat_response_model,
        )
    return getattr(client, method_name)(request)


def session_display_name(value: Any) -> str:
    """Extract a valid Studio display name from one Session response."""
    metadata = getattr(value, "metadata", None)
    if not isinstance(metadata, (list, tuple)):
        return ""
    for item in metadata:
        if isinstance(item, dict):
            key = item.get("key") or item.get("Key")
            name = item.get("value") or item.get("Value")
        else:
            key = getattr(item, "key", "")
            name = getattr(item, "value", "")
        if key != SESSION_DISPLAY_NAME_METADATA_KEY or not isinstance(name, str):
            continue
        normalized = name.strip()
        if 0 < len(normalized) <= SESSION_DISPLAY_NAME_MAX_LENGTH:
            return normalized
    return ""
