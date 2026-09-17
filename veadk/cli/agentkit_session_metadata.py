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

"""Compatibility helpers for AgentKit Session metadata."""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from types import SimpleNamespace
from typing import Any

SESSION_DISPLAY_NAME_MAX_LENGTH = 40
SESSION_METADATA_VALUE_MAX_BYTES = 63
SESSION_DISPLAY_NAME_METADATA_KEY = "veadk_display_name"
SESSION_CREATOR_NAME_METADATA_KEY = "veadk_creator_name"
SESSION_AGENT_KIND_METADATA_KEY = "veadk_agent_kind"
SESSION_USERNAME_METADATA_KEY = "Username"
_SESSION_DISPLAY_NAME_TRUNCATION_MARK = "…"


@cache
def _session_models() -> SimpleNamespace:
    """Build SDK compatibility models only for an actual Session request."""

    from agentkit.sdk.tools import types as tools_types
    from pydantic import Field, create_model

    session_metadata = create_model(
        "_SessionMetadata",
        __base__=tools_types.ToolsBaseModel,
        __module__=__name__,
        key=(str, Field(alias="Key")),
        type=(str | None, Field(default=None, alias="Type")),
        value=(str, Field(alias="Value")),
    )
    session_env = create_model(
        "_SessionEnv",
        __base__=tools_types.ToolsBaseModel,
        __module__=__name__,
        key=(str, Field(alias="Key")),
        value=(str, Field(alias="Value")),
    )
    create_request_compat = create_model(
        "_CreateSessionRequestCompat",
        __base__=tools_types.CreateSessionRequest,
        __module__=__name__,
        metadata=(
            list[session_metadata] | None,
            Field(default=None, alias="Metadata"),
        ),
    )
    create_request_full_compat = create_model(
        "_CreateSessionRequestFullCompat",
        __base__=tools_types.ToolsBaseModel,
        __module__=__name__,
        tool_id=(str, Field(alias="ToolId")),
        ttl=(int | None, Field(default=None, alias="Ttl")),
        ttl_unit=(str | None, Field(default=None, alias="TtlUnit")),
        user_session_id=(
            str | None,
            Field(default=None, alias="UserSessionId"),
        ),
        metadata=(
            list[session_metadata] | None,
            Field(default=None, alias="Metadata"),
        ),
        envs=(list[session_env] | None, Field(default=None, alias="Envs")),
    )
    list_request_compat = create_model(
        "_ListSessionsRequestCompat",
        __base__=tools_types.ListSessionsRequest,
        __module__=__name__,
        metadata=(
            list[session_metadata] | None,
            Field(default=None, alias="Metadata"),
        ),
    )
    get_response_compat = create_model(
        "_GetSessionResponseCompat",
        __base__=tools_types.ToolsBaseModel,
        __module__=__name__,
        created_at=(str | None, Field(default=None, alias="CreatedAt")),
        endpoint=(str | None, Field(default=None, alias="Endpoint")),
        expire_at=(str | None, Field(default=None, alias="ExpireAt")),
        internal_endpoint=(
            str | None,
            Field(default=None, alias="InternalEndpoint"),
        ),
        session_id=(str | None, Field(default=None, alias="SessionId")),
        status=(str | None, Field(default=None, alias="Status")),
        tool_type=(str | None, Field(default=None, alias="ToolType")),
        user_session_id=(
            str | None,
            Field(default=None, alias="UserSessionId"),
        ),
        metadata=(
            list[session_metadata] | None,
            Field(default=None, alias="Metadata"),
        ),
    )
    session_info_compat = create_model(
        "_SessionInfoCompat",
        __base__=get_response_compat,
        __module__=__name__,
    )
    list_response_compat = create_model(
        "_ListSessionsResponseCompat",
        __base__=tools_types.ToolsBaseModel,
        __module__=__name__,
        next_token=(str | None, Field(default=None, alias="NextToken")),
        session_infos=(
            list[session_info_compat] | None,
            Field(default=None, alias="SessionInfos"),
        ),
    )
    snapshot_info_compat = create_model(
        "_SnapshotInfoCompat",
        __base__=tools_types.SnapshotsForListSessionSnapshots,
        __module__=__name__,
        session_metadata=(
            list[session_metadata] | None,
            Field(default=None, alias="SessionMetadata"),
        ),
    )
    list_snapshots_response_compat = create_model(
        "_ListSessionSnapshotsResponseCompat",
        __base__=tools_types.ToolsBaseModel,
        __module__=__name__,
        next_token=(str | None, Field(default=None, alias="NextToken")),
        snapshots=(
            list[snapshot_info_compat] | None,
            Field(default=None, alias="Snapshots"),
        ),
    )
    return SimpleNamespace(
        tools_types=tools_types,
        session_metadata=session_metadata,
        session_env=session_env,
        create_request_compat=create_request_compat,
        create_request_full_compat=create_request_full_compat,
        list_request_compat=list_request_compat,
        get_response_compat=get_response_compat,
        list_response_compat=list_response_compat,
        list_snapshots_response_compat=list_snapshots_response_compat,
    )


def _model_supports_alias(model: Any, alias: str) -> bool:
    fields = getattr(model, "model_fields", {})
    return any(getattr(field, "alias", None) == alias for field in fields.values())


def session_display_name_metadata_value(value: str) -> str:
    """Fit a display name into VeFaaS metadata without splitting UTF-8 text."""
    if len(value.encode("utf-8")) <= SESSION_METADATA_VALUE_MAX_BYTES:
        return value
    marker_bytes = len(_SESSION_DISPLAY_NAME_TRUNCATION_MARK.encode("utf-8"))
    prefix_byte_limit = SESSION_METADATA_VALUE_MAX_BYTES - marker_bytes
    prefix: list[str] = []
    prefix_bytes = 0
    for character in value:
        character_bytes = len(character.encode("utf-8"))
        if prefix_bytes + character_bytes > prefix_byte_limit:
            break
        prefix.append(character)
        prefix_bytes += character_bytes
    return "".join(prefix) + _SESSION_DISPLAY_NAME_TRUNCATION_MARK


def build_create_session_request(
    *,
    tool_id: str,
    ttl_seconds: int,
    user_session_id: str,
    display_name: str,
    username: str = "",
    creator_name: str = "",
    agent_kind: str = "",
    envs: Mapping[str, str] | None = None,
) -> Any:
    """Build a native or compatibility CreateSession request."""
    models = _session_models()
    tools_types = models.tools_types
    metadata = []
    if display_name:
        display_name = session_display_name_metadata_value(display_name)
        metadata.append(
            models.session_metadata(
                Key=SESSION_DISPLAY_NAME_METADATA_KEY,
                Type="String",
                Value=display_name,
            )
        )
    if username:
        metadata.append(
            models.session_metadata(
                Key=SESSION_USERNAME_METADATA_KEY,
                Type="String",
                Value=username,
            )
        )
    if creator_name:
        metadata.append(
            models.session_metadata(
                Key=SESSION_CREATOR_NAME_METADATA_KEY,
                Type="String",
                Value=creator_name,
            )
        )
    if agent_kind:
        metadata.append(
            models.session_metadata(
                Key=SESSION_AGENT_KIND_METADATA_KEY,
                Type="String",
                Value=agent_kind,
            )
        )
    request_type: Any = tools_types.CreateSessionRequest
    supports_metadata = _model_supports_alias(request_type, "Metadata")
    supports_envs = _model_supports_alias(request_type, "Envs")
    if metadata and not supports_metadata:
        request_type = models.create_request_compat
    if envs and not supports_envs:
        request_type = models.create_request_full_compat
    request_data: dict[str, Any] = {
        "ToolId": tool_id,
        "Ttl": ttl_seconds,
        "TtlUnit": "second",
        "UserSessionId": user_session_id,
    }
    if metadata:
        request_data["Metadata"] = metadata
    if envs:
        env_type = getattr(tools_types, "EnvsItemForCreateSession", models.session_env)
        request_data["Envs"] = [
            env_type(Key=key, Value=value)
            for key, value in envs.items()
            if key and value
        ]
    return request_type(**request_data)


def build_list_sessions_request(
    *,
    tool_id: str,
    max_results: int,
    next_token: str | None = None,
    username: str | None = None,
) -> Any:
    """Build ListSessions with an optional Username metadata filter."""
    models = _session_models()
    tools_types = models.tools_types
    request_type: Any = tools_types.ListSessionsRequest
    if username is not None and not _model_supports_alias(request_type, "Metadata"):
        request_type = models.list_request_compat
    request_data: dict[str, Any] = {
        "ToolId": tool_id,
        "MaxResults": max_results,
        "NextToken": next_token,
    }
    if username is not None:
        request_data["Metadata"] = [
            models.session_metadata(
                Key=SESSION_USERNAME_METADATA_KEY,
                Value=username,
            )
        ]
    return request_type(**request_data)


def call_session_client(client: Any, method_name: str, request: Any) -> Any:
    """Invoke a Session API while preserving Metadata on older SDK releases."""
    models = _session_models()
    tools_types = models.tools_types
    native_response_model: Any | None = None
    compat_response_model: Any | None = None
    api_action = ""
    metadata_alias = "Metadata"
    if method_name == "get_session":
        native_response_model = tools_types.GetSessionResponse
        compat_response_model = models.get_response_compat
        api_action = "GetSession"
    elif method_name == "list_sessions":
        native_response_model = tools_types.SessionInfosForListSessions
        compat_response_model = models.list_response_compat
        api_action = "ListSessions"

    elif method_name == "list_session_snapshots":
        native_response_model = tools_types.SnapshotsForListSessionSnapshots
        compat_response_model = models.list_snapshots_response_compat
        api_action = "ListSessionSnapshots"
        metadata_alias = "SessionMetadata"

    invoke_api = getattr(client, "_invoke_api", None)
    if (
        native_response_model is not None
        and compat_response_model is not None
        and not _model_supports_alias(native_response_model, metadata_alias)
        and callable(invoke_api)
    ):
        return invoke_api(
            api_action=api_action,
            request=request,
            response_type=compat_response_model,
        )
    return getattr(client, method_name)(request)


def _metadata_string(value: Any, expected_key: str) -> str:
    """Extract one string metadata value from a Session response."""
    metadata = getattr(value, "session_metadata", None)
    if metadata is None:
        metadata = getattr(value, "metadata", None)
    if not isinstance(metadata, (list, tuple)):
        return ""
    for item in metadata:
        if isinstance(item, dict):
            key = item.get("key") or item.get("Key")
            string_value = item.get("value") or item.get("Value")
        else:
            key = getattr(item, "key", "")
            string_value = getattr(item, "value", "")
        if key == expected_key and isinstance(string_value, str):
            return string_value.strip()
    return ""


def session_display_name(value: Any) -> str:
    """Extract a valid Studio display name from one Session response."""
    normalized = _metadata_string(value, SESSION_DISPLAY_NAME_METADATA_KEY)
    if 0 < len(normalized) <= SESSION_DISPLAY_NAME_MAX_LENGTH:
        return normalized
    return ""


def session_username(value: Any) -> str:
    """Extract the Username owner metadata from one Session response."""
    return _metadata_string(value, SESSION_USERNAME_METADATA_KEY)


def session_creator_name(value: Any) -> str:
    """Extract the human-readable creator name from one Session response."""
    return _metadata_string(value, SESSION_CREATOR_NAME_METADATA_KEY)


def session_agent_kind(value: Any) -> str:
    """Extract the Studio frontend agent kind from one Session response."""
    return _metadata_string(value, SESSION_AGENT_KIND_METADATA_KEY)
