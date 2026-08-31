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

"""Reusable AgentKit Sandbox Sessions for Studio Codex agents."""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
import os
import posixpath
import re
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Annotated, Any, Protocol

from fastapi import File, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from frontend.server.sandbox.tool_sessions import SandboxToolPair
from veadk.cli.agentkit_sandbox_region import is_agentkit_resource_not_found
from veadk.cli.agentkit_session_metadata import (
    SESSION_DISPLAY_NAME_MAX_LENGTH,
    build_create_session_request,
    build_list_sessions_request,
    call_session_client,
    session_agent_kind,
    session_creator_name,
    session_display_name,
    session_display_name_metadata_value,
    session_username,
)
from veadk.cli.codex_app_server import (
    ApprovalDecision,
    CodexAppServerError,
    CodexAppServerEvent,
    CodexAppServerSession,
    CodexAppServerTransportError,
    CodexAppServerTurnTimeoutError,
    CodexDirectoryListing,
    CodexImportedImage,
    CodexImportedMessage,
    CodexModel,
    CodexPermissionSettings,
    CodexSkill,
    CodexThreadMessage,
    CodexThreadSnapshot,
    CodexThreadSummary,
    CodexTokenUsage,
    approval_decision_from_payload,
    permission_settings_from_payload,
)
from veadk.cli.frontend_sandbox_proxy import (
    SANDBOX_UPLOAD_MAX_BYTES,
    SandboxProxyTarget,
    browser_launch_url,
    mount_sandbox_proxy_routes,
    proxy_cookie_name,
    proxy_prefix,
    terminal_launch_url,
    upload_sandbox_file,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

STUDIO_SANDBOX_TOOL_NAME = "veadk-studio-codex"
STUDIO_SANDBOX_TTL_SECONDS = 28_800
STUDIO_SANDBOX_MAX_ACTIVE = 20
STUDIO_SANDBOX_DISPLAY_NAME_MAX_LENGTH = SESSION_DISPLAY_NAME_MAX_LENGTH
_SANDBOX_CHAT_TOOL_ENV = "SANDBOX_CHAT_CODEX"
_SANDBOX_CHAT_SNAPSHOT_TOOL_ENV = "SANDBOX_CHAT_CODEX_SNAPSHOT"
_SANDBOX_ENDPOINT_EXPORT_ENV = "STUDIO_EXPOSE_SANDBOX_ENDPOINT"
_CODEX_PROJECT_HANDOFF_PAIRING_TTL_ENV = (
    "STUDIO_CODEX_PROJECT_HANDOFF_PAIRING_TTL_SECONDS"
)
_CODEX_PROJECT_HANDOFF_PAIRING_DEFAULT_TTL_SECONDS = 20 * 60
_CODEX_PROJECT_HANDOFF_PAIRING_MAX_TTL_SECONDS = 60 * 60
_CODEX_PROJECT_HANDOFF_PAIRING_MIN_TTL_SECONDS = 60
_CODEX_PROJECT_HANDOFF_PAIRING_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_CODEX_PROJECT_HANDOFF_PAIRING_LENGTH = 8
_SANDBOX_AGENT_TOOL_ENVS = {
    "deepseek-harness": (_SANDBOX_CHAT_TOOL_ENV,),
    "openclaw": ("SANDBOX_CHAT_OPENCLAW", "SANDBOX_OPENCLAW_TOOL"),
    "hermes": ("SANDBOX_CHAT_HERMES", "SANDBOX_HERMES_TOOL"),
}
_SANDBOX_AGENT_SNAPSHOT_TOOL_ENVS = {
    "deepseek-harness": _SANDBOX_CHAT_SNAPSHOT_TOOL_ENV,
    "openclaw": "SANDBOX_CHAT_OPENCLAW_SNAPSHOT",
    "hermes": "SANDBOX_CHAT_HERMES_SNAPSHOT",
}
_SANDBOX_CODEX_AGENT_KIND = "codex"
_CREATE_SESSION_START_FAIL_CODE = "ErrCreateSessionFail"
_SESSION_NOT_FOUND_CODE = "InvalidResource.NotFound"
_ACTIVE_SESSION_STATUSES = {"creating", "pending", "running", "ready", "starting"}
_RESTORABLE_SNAPSHOT_STATUSES = {"completed", "ready", "success", "succeeded"}
_AUTO_RESUME_SNAPSHOT_CONCURRENCY = 3
_RESUME_SESSION_ATTEMPTS = 36
_RESUME_SESSION_INTERVAL_SECONDS = 5
_SENSITIVE_PATTERN = re.compile(
    r"(?i)((?:api[_-]?key|access[_-]?key|secret|token|authorization|password)"
    r"\s*[:=]\s*)(?:[\"'][^\"']*[\"']|[^\s,;]+)"
)
_CODEX_PROJECT_HANDOFF_PAIRINGS: dict[str, dict[str, object]] = {}
_CODEX_PROJECT_HANDOFF_AGENT_NAME_MAX_LENGTH = 12
_CODEX_PROJECT_HANDOFF_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,64}")
_CODEX_PROJECT_HANDOFF_HISTORY_MAX_MESSAGES = 100
_SANDBOX_THREAD_HISTORY_MAX_MESSAGES = 200
_CODEX_PROJECT_HANDOFF_HISTORY_MAX_MESSAGE_CHARACTERS = 20_000
_CODEX_PROJECT_HANDOFF_HISTORY_MAX_CHARACTERS = 100_000
_CODEX_PROJECT_HANDOFF_HISTORY_MAX_IMAGES = 10
_CODEX_PROJECT_HANDOFF_HISTORY_MAX_IMAGE_BYTES = 4 * 1024 * 1024
_CODEX_PROJECT_HANDOFF_HISTORY_MAX_IMAGE_TOTAL_BYTES = 8 * 1024 * 1024
_CODEX_PROJECT_HANDOFF_HISTORY_IMAGE_MIME_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)
_CODEX_PROJECT_HANDOFF_CONTINUATION_MAX_CHARACTERS = 20_000
_CODEX_PROJECT_HANDOFF_FIRST_EVENT_TIMEOUT_SECONDS = 120
_CODEX_PROJECT_HANDOFF_PROGRESS_HEARTBEAT_SECONDS = 15
_CODEX_PROJECT_HANDOFF_PERMISSIONS = CodexPermissionSettings(
    approval_policy="never",
    approvals_reviewer="auto_review",
    sandbox_mode="danger-full-access",
    network_access=True,
)
_SESSION_CREATE_ENV_ALLOWLIST = frozenset(
    {
        "AGENTKIT_SANDBOX_MODEL_PROVIDER",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
        "CODEX_BASE_URL",
        "CODEX_CONFIG_TOML",
        "CODEX_MODEL",
        "CODEX_MODEL_CATALOG_JSON",
        "MODEL_BASE_URL",
        "OPENCODE_BASE_URL",
        "OPENCODE_MODEL",
    }
)
_SESSION_MODEL_ENV_KEYS = frozenset(
    {
        "ANTHROPIC_MODEL",
        "CODEX_MODEL",
        "OPENCODE_MODEL",
    }
)
_SESSION_CODEX_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class SandboxError(RuntimeError):
    """Base error safe to translate at the HTTP boundary."""

    code = "SANDBOX_ERROR"
    retryable = False


class SandboxConfigurationError(SandboxError):
    """Required server-side Sandbox configuration is missing."""

    code = "SANDBOX_NOT_CONFIGURED"


class SandboxToolQuotaError(SandboxConfigurationError):
    """The configured cloud account cannot create another Sandbox Session."""

    code = "SANDBOX_TOOL_QUOTA_EXCEEDED"


class SandboxPermissionError(SandboxError):
    """The caller is not allowed to use a Sandbox capability."""

    code = "SANDBOX_FORBIDDEN"


class SandboxValidationError(SandboxError):
    """A Studio Sandbox request did not satisfy the public contract."""

    code = "SANDBOX_INVALID_REQUEST"


class SandboxProvisioningError(SandboxError):
    """AgentKit could not provision the requested Sandbox resource."""

    code = "SANDBOX_PROVISIONING_FAILED"
    retryable = True


class SandboxSessionNotFoundError(SandboxError):
    """The cloud Session or local conversation connection is unavailable."""

    code = "SANDBOX_SESSION_NOT_FOUND"


class SandboxSessionUnavailableError(SandboxError):
    """The cloud Session exists but cannot accept a conversation yet."""

    code = "SANDBOX_SESSION_UNAVAILABLE"
    retryable = True


class SandboxInvocationError(SandboxError):
    """The coding agent failed while serving a conversation turn."""

    code = "SANDBOX_INVOCATION_FAILED"
    retryable = True


class SandboxTransportError(SandboxInvocationError):
    """The connection to the coding agent ended unexpectedly."""

    code = "SANDBOX_TRANSPORT_FAILED"


class SandboxTurnTimeoutError(SandboxInvocationError):
    """The coding agent exceeded the configured inactivity timeout."""

    code = "SANDBOX_TURN_TIMEOUT"


class SandboxCapacityError(SandboxError):
    """Studio has reached its local conversation-bridge limit."""

    code = "SANDBOX_CAPACITY_EXCEEDED"
    retryable = True


def _require_session_access(
    session: SandboxCloudSession,
    owner_id: str,
    *,
    is_admin: bool,
) -> None:
    if not is_admin and session.created_by != owner_id:
        raise SandboxSessionNotFoundError("智能体 Session 不存在或不属于当前用户。")


def _build_studio_user_session_id() -> str:
    return f"studio-{uuid.uuid4()}"


def _safe_error_message(error: object) -> str:
    """Return a bounded, credential-safe message including the exception chain."""
    parts: list[str] = []
    current = error if isinstance(error, BaseException) else None
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        detail = str(current).strip()
        if not parts:
            parts.append(detail or type(current).__name__)
        else:
            label = type(current).__name__
            parts.append(
                f"Caused by {label}: {detail}" if detail else f"Caused by {label}"
            )
        next_error = current.__cause__
        if next_error is None and not current.__suppress_context__:
            next_error = current.__context__
        current = next_error
    raw_message = "\n".join(parts) if parts else str(error).strip()
    message = _redact_public_text(raw_message, maximum=20_000)
    return message or type(error).__name__


def _sandbox_invocation_error(error: CodexAppServerError) -> SandboxInvocationError:
    """Preserve actionable Codex failure categories at the Sandbox boundary."""
    message = _safe_error_message(error)
    if isinstance(error, CodexAppServerTurnTimeoutError):
        return SandboxTurnTimeoutError(message)
    if isinstance(error, CodexAppServerTransportError):
        return SandboxTransportError(message)
    return SandboxInvocationError(message)


def _is_agentkit_tool_quota_error(error: BaseException) -> bool:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current).lower()
        if "quotaexceeded.tool" in message or (
            "tool" in message and "quota exceeded" in message
        ):
            return True
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    return False


def _raise_tool_configuration_error(error: BaseException) -> None:
    if _is_agentkit_tool_quota_error(error):
        raise SandboxToolQuotaError(
            "Sandbox Tool 配额不足，请管理员释放不用的 Tool 或申请扩容。"
        ) from error
    raise SandboxConfigurationError(
        "Sandbox Tool 不存在或已失效，请管理员重新配置。"
    ) from error


def _sandbox_endpoint_export_enabled() -> bool:
    value = (os.getenv(_SANDBOX_ENDPOINT_EXPORT_ENV) or "").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _redact_public_text(value: str, *, maximum: int) -> str:
    """Redact credentials from browser-visible text without inventing content."""
    message = value
    for key, env_value in os.environ.items():
        if (
            env_value
            and len(env_value) >= 8
            and any(
                token in key.upper() for token in ("KEY", "SECRET", "TOKEN", "PASSWORD")
            )
        ):
            message = message.replace(env_value, "***")
    message = re.sub(r"(?i)(\bbearer\s+)\S+", r"\1***", message)
    message = _SENSITIVE_PATTERN.sub(r"\1***", message)
    message = re.sub(r"https?://[^\s?]+\?[^\s]+", "[sandbox endpoint]", message)
    return message[:maximum]


def _safe_public_value(value: object, depth: int = 0) -> object:
    """Return a bounded, credential-safe value for browser-visible events."""
    if depth > 4:
        return "…"
    if isinstance(value, str):
        return _redact_public_text(value, maximum=20_000)
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in list(value.items())[:30]:
            safe_key = _redact_public_text(key, maximum=100)
            if any(
                marker in str(key).upper()
                for marker in ("KEY", "PASSWORD", "SECRET", "TOKEN", "AUTHORIZATION")
            ):
                result[safe_key] = "***"
            else:
                result[safe_key] = _safe_public_value(item, depth + 1)
        return result
    if isinstance(value, list):
        return [_safe_public_value(item, depth + 1) for item in value[:30]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe_error_message(value)


def _public_event_text(value: object) -> str:
    """Extract readable text from a Codex event field."""
    if isinstance(value, str):
        return _redact_public_text(value, maximum=100_000)
    if isinstance(value, list):
        return "\n".join(filter(None, (_public_event_text(item) for item in value)))
    if isinstance(value, dict):
        return _public_event_text(
            value.get("text") or value.get("content") or value.get("summary")
        )
    return ""


def _utc_timestamp(value: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))


def _codex_project_handoff_pairing_ttl_seconds(value: object = None) -> int:
    if value is None:
        raw = (os.getenv(_CODEX_PROJECT_HANDOFF_PAIRING_TTL_ENV) or "").strip()
        if raw:
            try:
                value = int(raw)
            except ValueError:
                value = _CODEX_PROJECT_HANDOFF_PAIRING_DEFAULT_TTL_SECONDS
        else:
            value = _CODEX_PROJECT_HANDOFF_PAIRING_DEFAULT_TTL_SECONDS
    if not isinstance(value, int) or isinstance(value, bool):
        raise SandboxValidationError("配对码有效期必须是整数秒数。")
    if value < _CODEX_PROJECT_HANDOFF_PAIRING_MIN_TTL_SECONDS:
        raise SandboxValidationError(
            "配对码有效期不能少于 "
            f"{_CODEX_PROJECT_HANDOFF_PAIRING_MIN_TTL_SECONDS} 秒。"
        )
    return min(value, _CODEX_PROJECT_HANDOFF_PAIRING_MAX_TTL_SECONDS)


def _cleanup_codex_project_handoff_pairings(now: int) -> None:
    active: dict[str, dict[str, object]] = {}
    for code, pairing in _CODEX_PROJECT_HANDOFF_PAIRINGS.items():
        expire_at = pairing.get("exp")
        if isinstance(expire_at, int) and expire_at > now:
            active[code] = pairing
    _CODEX_PROJECT_HANDOFF_PAIRINGS.clear()
    _CODEX_PROJECT_HANDOFF_PAIRINGS.update(active)


def _format_codex_project_handoff_pairing(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def _normalize_codex_project_handoff_pairing(value: object) -> str:
    if not isinstance(value, str):
        raise SandboxPermissionError("Codex 云端接力配对码无效或已过期。")
    normalized = re.sub(r"[-\s]", "", value).upper()
    if len(normalized) != _CODEX_PROJECT_HANDOFF_PAIRING_LENGTH or any(
        character not in _CODEX_PROJECT_HANDOFF_PAIRING_ALPHABET
        for character in normalized
    ):
        raise SandboxPermissionError("Codex 云端接力配对码无效或已过期。")
    return normalized


def _create_codex_project_handoff_pairing(
    owner_id: str,
    creator_name: str,
    ttl_seconds: int,
) -> tuple[str, int]:
    now = int(time.time())
    expire_at = now + ttl_seconds
    _cleanup_codex_project_handoff_pairings(now)
    for _attempt in range(16):
        code = "".join(
            secrets.choice(_CODEX_PROJECT_HANDOFF_PAIRING_ALPHABET)
            for _ in range(_CODEX_PROJECT_HANDOFF_PAIRING_LENGTH)
        )
        if code in _CODEX_PROJECT_HANDOFF_PAIRINGS:
            continue
        _CODEX_PROJECT_HANDOFF_PAIRINGS[code] = {
            "ownerId": owner_id,
            "creatorName": creator_name,
            "exp": expire_at,
            "state": "issued",
            "createdAt": now,
        }
        return _format_codex_project_handoff_pairing(code), expire_at
    raise SandboxCapacityError("暂时无法生成云端接力配对码，请稍后重试。")


def _claim_codex_project_handoff_pairing(
    pairing_code: object,
    expected_state: str,
    claimed_state: str,
) -> tuple[str, dict[str, object]]:
    code = _normalize_codex_project_handoff_pairing(pairing_code)
    _cleanup_codex_project_handoff_pairings(int(time.time()))
    pairing = _CODEX_PROJECT_HANDOFF_PAIRINGS.get(code)
    if pairing is None or pairing.get("state") != expected_state:
        raise SandboxPermissionError("Codex 云端接力配对码已使用或已过期。")
    pairing["state"] = claimed_state
    pairing.pop("error", None)
    pairing.pop("failedStage", None)
    return code, pairing


def _get_codex_project_handoff_pairing(
    pairing_code: object,
    owner_id: str,
) -> dict[str, object]:
    code = _normalize_codex_project_handoff_pairing(pairing_code)
    _cleanup_codex_project_handoff_pairings(int(time.time()))
    pairing = _CODEX_PROJECT_HANDOFF_PAIRINGS.get(code)
    if pairing is None or pairing.get("ownerId") != owner_id:
        raise SandboxSessionNotFoundError("端云接力请求不存在或已过期。")
    return pairing


def _codex_project_upload_project_name(value: object) -> str:
    if value is None:
        return "project"
    if not isinstance(value, str):
        raise SandboxValidationError("项目名称必须是文本。")
    cleaned = re.sub(r"\s+", " ", value.strip())
    return cleaned or "project"


def _codex_project_handoff_agent_name(value: object) -> str:
    if not isinstance(value, str):
        raise SandboxValidationError("云端 Agent 名称必须是文本。")
    display_name = re.sub(r"\s+", " ", value.strip())
    if not display_name:
        raise SandboxValidationError("云端 Agent 名称不能为空。")
    if len(display_name) > _CODEX_PROJECT_HANDOFF_AGENT_NAME_MAX_LENGTH:
        raise SandboxValidationError(
            "云端 Agent 名称不能超过 "
            f"{_CODEX_PROJECT_HANDOFF_AGENT_NAME_MAX_LENGTH} 个字符。"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in display_name):
        raise SandboxValidationError("云端 Agent 名称包含不支持的控制字符。")
    return display_name


def _codex_project_handoff_id(value: object) -> str:
    if not isinstance(value, str) or not _CODEX_PROJECT_HANDOFF_ID_PATTERN.fullmatch(
        value
    ):
        raise SandboxValidationError("端云接力请求 ID 无效。")
    return value


def _codex_project_handoff_image_matches(mime_type: str, data: bytes) -> bool:
    if mime_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if mime_type == "image/gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if mime_type == "image/webp":
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    return False


def _codex_project_handoff_history(
    value: object,
) -> tuple[CodexImportedMessage, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise SandboxValidationError("端侧会话历史格式无效。")
    if len(value) > _CODEX_PROJECT_HANDOFF_HISTORY_MAX_MESSAGES:
        raise SandboxValidationError("端侧会话历史消息过多。")
    messages: list[CodexImportedMessage] = []
    total_characters = 0
    total_image_bytes = 0
    total_images = 0
    for item in value:
        if not isinstance(item, dict):
            raise SandboxValidationError("端侧会话历史格式无效。")
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            raise SandboxValidationError("端侧会话历史只支持用户和助手消息。")
        content = content.strip()
        if len(content) > _CODEX_PROJECT_HANDOFF_HISTORY_MAX_MESSAGE_CHARACTERS:
            raise SandboxValidationError("端侧会话历史单条消息过长。")
        total_characters += len(content)
        if total_characters > _CODEX_PROJECT_HANDOFF_HISTORY_MAX_CHARACTERS:
            raise SandboxValidationError("端侧会话历史内容过大。")
        raw_images = item.get("images", [])
        if not isinstance(raw_images, list) or (role == "assistant" and raw_images):
            raise SandboxValidationError("端侧会话历史图片格式无效。")
        images: list[CodexImportedImage] = []
        for raw_image in raw_images:
            if not isinstance(raw_image, dict):
                raise SandboxValidationError("端侧会话历史图片格式无效。")
            mime_type = raw_image.get("mimeType")
            encoded = raw_image.get("data")
            name = raw_image.get("name", "")
            alt = raw_image.get("alt", "")
            if (
                mime_type not in _CODEX_PROJECT_HANDOFF_HISTORY_IMAGE_MIME_TYPES
                or not isinstance(encoded, str)
                or not encoded
                or not isinstance(name, str)
                or not isinstance(alt, str)
                or len(name) > 255
                or len(alt) > 500
            ):
                raise SandboxValidationError("端侧会话历史图片格式无效。")
            try:
                decoded = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as error:
                raise SandboxValidationError("端侧会话历史图片编码无效。") from error
            if not _codex_project_handoff_image_matches(mime_type, decoded):
                raise SandboxValidationError("端侧会话历史图片格式无效。")
            image_bytes = len(decoded)
            total_images += 1
            total_image_bytes += image_bytes
            if total_images > _CODEX_PROJECT_HANDOFF_HISTORY_MAX_IMAGES:
                raise SandboxValidationError("端侧会话历史图片过多。")
            if image_bytes > _CODEX_PROJECT_HANDOFF_HISTORY_MAX_IMAGE_BYTES:
                raise SandboxValidationError("端侧会话历史单张图片过大。")
            if total_image_bytes > _CODEX_PROJECT_HANDOFF_HISTORY_MAX_IMAGE_TOTAL_BYTES:
                raise SandboxValidationError("端侧会话历史图片内容过大。")
            images.append(
                CodexImportedImage(
                    mime_type=mime_type,
                    data=encoded,
                    name=name,
                    alt=alt,
                )
            )
        if not content and not images:
            raise SandboxValidationError("端侧会话历史包含空消息。")
        messages.append(
            CodexImportedMessage(
                role=role,
                content=content,
                images=tuple(images),
            )
        )
    return tuple(messages)


def _codex_project_upload_directory_name(project_name: str) -> str:
    directory = project_name.strip().replace("/", "-").replace("\\", "-")
    directory = re.sub(r"[^A-Za-z0-9._-]+", "-", directory)
    directory = re.sub(r"-+", "-", directory).strip(" ._-")
    return directory or "project"


def _codex_project_upload_remote_home(value: object) -> str:
    if value is None or value == "":
        return "/home/gem"
    if not isinstance(value, str):
        raise SandboxValidationError("远端 Home 目录必须是文本。")
    remote_home = posixpath.normpath(value.strip())
    if not remote_home.startswith("/"):
        raise SandboxValidationError("远端 Home 目录必须是绝对路径。")
    return remote_home


def _studio_url_for_request(request: Request) -> str:
    forwarded_proto = (
        request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    )
    forwarded_host = (
        request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
    )
    scheme = forwarded_proto or request.url.scheme
    host = forwarded_host or request.headers.get("host") or request.url.netloc
    root_path = str(request.scope.get("root_path") or "").rstrip("/")
    return f"{scheme}://{host}{root_path}"


@dataclass(frozen=True)
class SandboxCloudSession:
    """Remote AgentKit Sandbox Session data kept only on the server."""

    tool_id: str
    instance_id: str
    user_session_id: str
    endpoint: str
    region: str = ""
    status: str = "Unknown"
    created_at: str = ""
    expire_at: str = ""
    tool_type: str = ""
    display_name: str = ""
    created_by: str = ""
    creator_name: str = ""
    agent_kind: str = ""
    persistent: bool = False


@dataclass(frozen=True)
class SandboxCloudSnapshot:
    """Restorable AgentKit Session snapshot without a running data plane."""

    tool_id: str
    snapshot_id: str
    session_id: str
    user_session_id: str
    region: str = ""
    status: str = "Unknown"
    reason: str = ""
    created_at: str = ""
    display_name: str = ""
    created_by: str = ""


def _restorable_snapshots(
    sessions: list[SandboxCloudSession],
    snapshots: list[SandboxCloudSnapshot],
) -> list[SandboxCloudSnapshot]:
    active_user_session_ids = {
        session.user_session_id
        for session in sessions
        if session.user_session_id
        and session.status.lower() in _ACTIVE_SESSION_STATUSES
    }
    active_session_ids = {
        session.instance_id
        for session in sessions
        if session.status.lower() in _ACTIVE_SESSION_STATUSES
    }
    restorable: list[SandboxCloudSnapshot] = []
    for snapshot in sorted(snapshots, key=lambda item: item.created_at, reverse=True):
        if snapshot.status.lower() not in _RESTORABLE_SNAPSHOT_STATUSES:
            continue
        if (
            snapshot.user_session_id
            and snapshot.user_session_id in active_user_session_ids
        ):
            continue
        if not snapshot.user_session_id and snapshot.session_id in active_session_ids:
            continue
        restorable.append(snapshot)
    return restorable


def _request_auto_resume_snapshots(request: Request, *, default: bool = False) -> bool:
    raw_value = request.query_params.get("autoResumeSnapshots")
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def _auto_resume_snapshot_batch(
    snapshots: list[SandboxCloudSnapshot],
    resume: Callable[[SandboxCloudSnapshot], Awaitable[SandboxCloudSession]],
) -> None:
    if not snapshots:
        return
    semaphore = asyncio.Semaphore(_AUTO_RESUME_SNAPSHOT_CONCURRENCY)

    async def _resume(snapshot: SandboxCloudSnapshot) -> None:
        async with semaphore:
            try:
                await resume(snapshot)
            except Exception as error:  # noqa: BLE001
                logger.warning(
                    "Failed to auto-resume Sandbox snapshot snapshot_id=%s "
                    "session_id=%s error_type=%s",
                    snapshot.snapshot_id,
                    snapshot.session_id,
                    type(error).__name__,
                )

    await asyncio.gather(*(_resume(snapshot) for snapshot in snapshots))


def _session_for_tools(
    session: SandboxCloudSession,
    tools: SandboxToolPair,
) -> SandboxCloudSession:
    """Attach the browser-safe persistence mode derived from its Tool id."""
    return replace(session, persistent=tools.is_persistent(session.tool_id))


def _session_matches_agent_kind(
    session: SandboxCloudSession,
    agent_kind: str,
    *,
    include_legacy: bool = False,
) -> bool:
    actual = session.agent_kind.strip()
    if actual == agent_kind:
        return True
    return include_legacy and not actual


@dataclass
class SandboxConversation:
    """Server-side connection state for one reusable cloud Session."""

    session_id: str
    owner_id: str
    cloud: SandboxCloudSession
    codex: SandboxCodexConnection
    proxy_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    expires_at: float = field(
        default_factory=lambda: time.monotonic() + STUDIO_SANDBOX_TTL_SECONDS
    )
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    pending_prompt: str = ""
    pending_prompt_timestamp: int = 0
    background_turn: asyncio.Task[None] | None = None


@dataclass(frozen=True)
class SandboxStreamEvent:
    """One typed event emitted while the coding agent is running."""

    kind: str = ""
    item_id: str = ""
    status: str = "done"
    text: str = ""
    name: str = ""
    arguments: object | None = None
    response: object | None = None
    thread_id: str | None = None
    approval: object | None = None
    approval_resolved_id: str = ""
    turn_id: str = ""
    usage: CodexTokenUsage | None = None
    thread_total: CodexTokenUsage | None = None
    model_context_window: int | None = None


class SandboxCodexConnection(Protocol):
    """Persistent Codex app-server connection owned by one Studio session."""

    thread_id: str
    cwd: str
    model: str
    permissions: CodexPermissionSettings

    @property
    def active(self) -> bool:
        """Whether a turn is currently running."""
        raise NotImplementedError

    @property
    def workspace_locked(self) -> bool:
        """Whether the first turn has already started."""
        raise NotImplementedError

    async def connect(self) -> None:
        """Ensure the app-server transport is connected."""
        raise NotImplementedError

    @property
    def healthy(self) -> bool:
        """Whether the app-server transport can accept a request."""
        raise NotImplementedError

    async def ensure_connected(self, *, minimum_lifetime_seconds: float = 60) -> None:
        """Refresh a stale transport while preserving its active thread."""
        raise NotImplementedError

    async def stream_turn(
        self,
        prompt: str,
        skill_ids: tuple[str, ...] = (),
        *,
        permissions: CodexPermissionSettings | None = None,
        timeout_seconds: float | None = None,
        output_schema: dict[str, object] | None = None,
    ) -> AsyncIterator[CodexAppServerEvent]:
        """Run and stream one turn."""
        if False:
            yield CodexAppServerEvent()

    async def interrupt(self) -> None:
        """Interrupt the active turn when the user explicitly requests it."""
        raise NotImplementedError

    @property
    def thread_token_total(self) -> CodexTokenUsage | None:
        """Latest cumulative token usage for the active thread."""
        raise NotImplementedError

    @property
    def model_context_window(self) -> int | None:
        """Current model context window when reported by app-server."""
        raise NotImplementedError

    async def list_models(self) -> tuple[CodexModel, ...]:
        """List visible Codex models."""
        raise NotImplementedError

    async def set_model(self, model: str) -> str:
        """Change the active thread model."""
        raise NotImplementedError

    async def list_skills(self, force_reload: bool = False) -> tuple[CodexSkill, ...]:
        """List browser-safe Skills."""
        raise NotImplementedError

    async def new_thread(self) -> CodexThreadSnapshot:
        """Start a fresh thread."""
        raise NotImplementedError

    async def list_threads(
        self,
        *,
        cursor: str = "",
        search_term: str = "",
        archived: bool = False,
    ) -> tuple[tuple[CodexThreadSummary, ...], str]:
        """List recent threads."""
        raise NotImplementedError

    async def resume_thread(self, thread_id: str) -> CodexThreadSnapshot:
        """Resume an existing thread."""
        raise NotImplementedError

    async def read_thread(self, thread_id: str) -> CodexThreadSnapshot:
        """Read an existing thread without activating it."""
        raise NotImplementedError

    async def inject_history(self, messages: tuple[CodexImportedMessage, ...]) -> None:
        """Import visible messages without replaying their turns."""
        raise NotImplementedError

    async def fork_thread(self) -> CodexThreadSnapshot:
        """Fork the active thread."""
        raise NotImplementedError

    async def archive_thread(self, thread_id: str) -> CodexThreadSnapshot | None:
        """Archive one thread."""
        raise NotImplementedError

    async def delete_thread(self, thread_id: str) -> CodexThreadSnapshot | None:
        """Permanently delete one thread."""
        raise NotImplementedError

    async def compact_thread(self) -> None:
        """Compact the active thread."""
        raise NotImplementedError

    async def update_permissions(
        self, settings: CodexPermissionSettings
    ) -> CodexPermissionSettings:
        """Persist and hot-apply Session permissions."""
        raise NotImplementedError

    async def apply_session_permissions(
        self, settings: CodexPermissionSettings
    ) -> None:
        """Adopt permissions persisted by another thread."""
        raise NotImplementedError

    async def update_workspace(self, cwd: str) -> str:
        """Update the CWD before the first turn."""
        raise NotImplementedError

    async def list_directories(self, path: str) -> CodexDirectoryListing:
        """List remote directories."""
        raise NotImplementedError

    def resolve_approval(self, approval_id: str, decision: ApprovalDecision) -> None:
        """Resolve one pending user approval."""
        raise NotImplementedError

    async def close(self) -> None:
        """Close the persistent connection."""
        raise NotImplementedError


class SandboxCloudGateway(Protocol):
    """AgentKit operations needed by the Studio Session service."""

    async def get_tool(self, tool_id: str) -> Any:
        """Read one configured Sandbox Tool."""
        raise NotImplementedError

    async def list_sessions(
        self, tool_id: str, username: str | None = None
    ) -> list[SandboxCloudSession]:
        """List Sessions, optionally filtered by Username metadata."""
        raise NotImplementedError

    async def list_snapshots(self, tool_id: str) -> list[SandboxCloudSnapshot]:
        """List restorable snapshots for an administrator."""
        raise NotImplementedError

    async def get_session(self, tool_id: str, session_id: str) -> SandboxCloudSession:
        """Resolve one existing Session and its private Endpoint."""
        raise NotImplementedError

    async def create_session(
        self,
        tool_id: str,
        display_name: str = "",
        username: str = "",
        creator_name: str = "",
        agent_kind: str = "",
        envs: Mapping[str, str] | None = None,
    ) -> SandboxCloudSession:
        """Create a fresh remote Sandbox session."""
        raise NotImplementedError

    async def delete_session(self, session: SandboxCloudSession) -> None:
        """Delete a remote Sandbox session."""
        raise NotImplementedError

    async def resume_snapshot(
        self, snapshot: SandboxCloudSnapshot
    ) -> SandboxCloudSession:
        """Restore one snapshot and wait for its Session to become ready."""
        raise NotImplementedError

    async def delete_snapshot(self, snapshot: SandboxCloudSnapshot) -> None:
        """Delete one restorable snapshot."""
        raise NotImplementedError

    async def open_codex(self, session: SandboxCloudSession) -> SandboxCodexConnection:
        """Open one persistent Codex app-server connection."""
        raise NotImplementedError

    async def drain(self) -> None:
        """Wait for asynchronous cloud cleanup started by cancelled requests."""
        raise NotImplementedError


class AgentkitSandboxGateway:
    """AgentKit SDK and persistent Codex app-server adapter.

    The AgentKit management SDK is synchronous, so each API call runs in a
    worker thread. Conversation output uses the Sandbox app-server WebSocket;
    the Session Endpoint, including its authorization query, never leaves this
    process.
    """

    def __init__(
        self,
        client: Any | Callable[..., Any],
        *,
        region_candidates: tuple[str, ...] = (),
    ) -> None:
        self._client = client
        self._region_candidates = region_candidates
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _track_cleanup(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _call(self, method_name: str, request: Any, *, region: str = "") -> Any:
        if callable(self._client):
            client = self._client(region) if self._region_candidates else self._client()
        else:
            client = self._client
        return await asyncio.to_thread(
            call_session_client,
            client,
            method_name,
            request,
        )

    async def _reconcile_created_session(
        self, tool_id: str, user_session_id: str, region: str = ""
    ) -> SandboxCloudSession | None:
        from agentkit.sdk.tools import types as tools_types

        for attempt in range(6):
            response = await self._call(
                "list_sessions",
                tools_types.ListSessionsRequest(
                    ToolId=tool_id,
                    MaxResults=10,
                    Filters=[
                        tools_types.FiltersItemForListSessions(
                            Name="UserSessionId", Values=[user_session_id]
                        )
                    ],
                ),
                region=region,
            )
            for session in response.session_infos or []:
                if session.user_session_id != user_session_id:
                    continue
                if (session.status or "").lower() != "ready":
                    continue
                if session.session_id and session.endpoint:
                    return self._cloud_session(
                        tool_id,
                        session,
                        region=region,
                        fallback_user_session_id=user_session_id,
                    )
            if attempt < 5:
                await asyncio.sleep(5)
        return None

    @staticmethod
    def _cloud_session(
        tool_id: str,
        value: Any,
        *,
        region: str = "",
        fallback_user_session_id: str = "",
    ) -> SandboxCloudSession:
        instance_id = str(getattr(value, "session_id", "") or "").strip()
        if not instance_id:
            raise SandboxProvisioningError("AgentKit Session 响应缺少 SessionId。")
        return SandboxCloudSession(
            tool_id=tool_id,
            instance_id=instance_id,
            user_session_id=str(
                getattr(value, "user_session_id", "") or fallback_user_session_id
            ).strip(),
            endpoint=str(getattr(value, "endpoint", "") or "").strip(),
            region=region,
            status=str(getattr(value, "status", "") or "Unknown").strip(),
            created_at=str(getattr(value, "created_at", "") or "").strip(),
            expire_at=str(getattr(value, "expire_at", "") or "").strip(),
            tool_type=str(getattr(value, "tool_type", "") or "").strip(),
            display_name=session_display_name(value),
            created_by=session_username(value),
            creator_name=session_creator_name(value),
            agent_kind=session_agent_kind(value),
        )

    @staticmethod
    def _cloud_snapshot(
        tool_id: str,
        value: Any,
        *,
        region: str,
    ) -> SandboxCloudSnapshot | None:
        snapshot_id = str(getattr(value, "snapshot_id", "") or "").strip()
        user_session_id = str(getattr(value, "user_session_id", "") or "").strip()
        if not snapshot_id:
            return None
        display_name = user_session_id or snapshot_id
        if not display_name:
            display_name = user_session_id or snapshot_id
        return SandboxCloudSnapshot(
            tool_id=tool_id,
            snapshot_id=snapshot_id,
            session_id=str(getattr(value, "session_id", "") or "").strip(),
            user_session_id=user_session_id,
            region=region,
            status=str(getattr(value, "status", "") or "Unknown").strip(),
            reason=str(getattr(value, "reason", "") or "").strip(),
            created_at=str(getattr(value, "created_at", "") or "").strip(),
            display_name=display_name,
            created_by="",
        )

    async def get_tool(self, tool_id: str) -> Any:
        from agentkit.sdk.tools import types as tools_types

        regions = self._region_candidates or ("",)
        for index, region in enumerate(regions):
            try:
                return await self._call(
                    "get_tool",
                    tools_types.GetToolRequest(ToolId=tool_id),
                    region=region,
                )
            except SandboxError:
                raise
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(regions):
                    continue
                if is_agentkit_resource_not_found(error):
                    _raise_tool_configuration_error(error)
                raise SandboxProvisioningError(
                    f"读取 AgentKit Tool 失败：{_safe_error_message(error)}"
                ) from error
        raise SandboxProvisioningError("无法在支持的地域读取 AgentKit Tool。")

    async def list_sessions(
        self, tool_id: str, username: str | None = None
    ) -> list[SandboxCloudSession]:
        regions = self._region_candidates or ("",)
        for index, region in enumerate(regions):
            sessions: dict[str, SandboxCloudSession] = {}
            next_token: str | None = None
            seen_tokens: set[str] = set()
            try:
                for _page in range(100):
                    response = await self._call(
                        "list_sessions",
                        build_list_sessions_request(
                            tool_id=tool_id,
                            max_results=100,
                            next_token=next_token,
                            username=username,
                        ),
                        region=region,
                    )
                    for value in response.session_infos or []:
                        session = self._cloud_session(
                            tool_id,
                            value,
                            region=region,
                        )
                        sessions[session.instance_id] = session
                    next_token = str(response.next_token or "").strip() or None
                    if next_token is None:
                        return sorted(
                            sessions.values(),
                            key=lambda item: item.created_at,
                            reverse=True,
                        )
                    if next_token in seen_tokens:
                        raise SandboxProvisioningError(
                            "AgentKit ListSessions 返回了重复的 NextToken。"
                        )
                    seen_tokens.add(next_token)
                raise SandboxProvisioningError(
                    "AgentKit ListSessions 分页超过安全上限。"
                )
            except SandboxError:
                raise
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(regions):
                    continue
                if is_agentkit_resource_not_found(error):
                    _raise_tool_configuration_error(error)
                raise SandboxProvisioningError(
                    f"读取 AgentKit Session 失败：{_safe_error_message(error)}"
                ) from error
        raise SandboxProvisioningError("无法在支持的地域读取 AgentKit Session。")

    async def list_snapshots(self, tool_id: str) -> list[SandboxCloudSnapshot]:
        from agentkit.sdk.tools import types as tools_types

        regions = self._region_candidates or ("",)
        for index, region in enumerate(regions):
            snapshots: dict[str, SandboxCloudSnapshot] = {}
            next_token: str | None = None
            seen_tokens: set[str] = set()
            try:
                for _page in range(100):
                    response = await self._call(
                        "list_session_snapshots",
                        tools_types.ListSessionSnapshotsRequest(
                            ToolId=tool_id,
                            MaxResults=100,
                            NextToken=next_token,
                        ),
                        region=region,
                    )
                    for value in response.snapshots or []:
                        snapshot = self._cloud_snapshot(
                            tool_id,
                            value,
                            region=region,
                        )
                        if snapshot is not None:
                            snapshots[snapshot.snapshot_id] = snapshot
                    next_token = str(response.next_token or "").strip() or None
                    if next_token is None:
                        return sorted(
                            snapshots.values(),
                            key=lambda item: item.created_at,
                            reverse=True,
                        )
                    if next_token in seen_tokens:
                        raise SandboxProvisioningError(
                            "AgentKit ListSessionSnapshots 返回了重复的 NextToken。"
                        )
                    seen_tokens.add(next_token)
                raise SandboxProvisioningError(
                    "AgentKit ListSessionSnapshots 分页超过安全上限。"
                )
            except SandboxError:
                raise
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(regions):
                    continue
                if is_agentkit_resource_not_found(error):
                    _raise_tool_configuration_error(error)
                raise SandboxProvisioningError(
                    f"读取 AgentKit Session 快照失败：{_safe_error_message(error)}"
                ) from error
        raise SandboxProvisioningError("无法在支持的地域读取 AgentKit Session 快照。")

    async def get_session(self, tool_id: str, session_id: str) -> SandboxCloudSession:
        from agentkit.sdk.tools import types as tools_types

        regions = self._region_candidates or ("",)
        for index, region in enumerate(regions):
            try:
                response = await self._call(
                    "get_session",
                    tools_types.GetSessionRequest(
                        ToolId=tool_id,
                        SessionId=session_id,
                    ),
                    region=region,
                )
                return self._cloud_session(tool_id, response, region=region)
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(regions):
                    continue
                if is_agentkit_resource_not_found(error):
                    raise SandboxSessionNotFoundError(
                        "AgentKit Session 不存在或已过期。"
                    ) from error
                raise SandboxProvisioningError(
                    f"读取 AgentKit Session 失败：{_safe_error_message(error)}"
                ) from error
        raise SandboxSessionNotFoundError("AgentKit Session 不存在或已过期。")

    async def create_session(
        self,
        tool_id: str,
        display_name: str = "",
        username: str = "",
        creator_name: str = "",
        agent_kind: str = "",
        envs: Mapping[str, str] | None = None,
    ) -> SandboxCloudSession:
        user_session_id = _build_studio_user_session_id()
        display_name = session_display_name_metadata_value(display_name)
        regions = self._region_candidates or ("",)
        for index, region in enumerate(regions):
            request = build_create_session_request(
                tool_id=tool_id,
                ttl_seconds=STUDIO_SANDBOX_TTL_SECONDS,
                user_session_id=user_session_id,
                display_name=display_name,
                username=username,
                creator_name=creator_name,
                agent_kind=agent_kind,
                envs=envs,
            )
            create_task = asyncio.create_task(
                self._call("create_session", request, region=region)
            )
            try:
                response = await asyncio.shield(create_task)
            except asyncio.CancelledError:
                self._track_cleanup(
                    self._cleanup_cancelled_create(
                        create_task,
                        tool_id=tool_id,
                        user_session_id=user_session_id,
                        region=region,
                    )
                )
                raise
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(regions):
                    continue
                if is_agentkit_resource_not_found(error):
                    _raise_tool_configuration_error(error)
                if _is_agentkit_tool_quota_error(error):
                    _raise_tool_configuration_error(error)
                if _CREATE_SESSION_START_FAIL_CODE not in str(error):
                    raise SandboxProvisioningError(
                        f"创建 AgentKit 沙箱会话失败：{_safe_error_message(error)}"
                    ) from error
                reconciled = await self._reconcile_created_session(
                    tool_id, user_session_id, region
                )
                if reconciled is not None:
                    return reconciled
                raise SandboxProvisioningError(
                    "AgentKit 返回会话启动失败，且未找到已就绪的会话。"
                ) from error

            instance_id = (response.session_id or "").strip()
            endpoint = (response.endpoint or "").strip()
            if not instance_id:
                raise SandboxProvisioningError("AgentKit 创建会话响应缺少 SessionId。")
            return SandboxCloudSession(
                tool_id=tool_id,
                instance_id=instance_id,
                user_session_id=response.user_session_id or user_session_id,
                endpoint=endpoint,
                region=region,
                status="Ready" if endpoint else "Creating",
                display_name=display_name,
                created_by=username,
                creator_name=creator_name,
                agent_kind=agent_kind,
            )
        raise SandboxProvisioningError("无法在支持的地域创建 AgentKit 沙箱会话。")

    async def _cleanup_cancelled_create(
        self,
        create_task: asyncio.Task[Any],
        *,
        tool_id: str,
        user_session_id: str,
        region: str = "",
    ) -> None:
        """Delete a cloud session whose synchronous create outlived its request."""
        cloud: SandboxCloudSession | None = None
        try:
            response = await create_task
            if response.session_id:
                cloud = SandboxCloudSession(
                    tool_id=tool_id,
                    instance_id=response.session_id,
                    user_session_id=response.user_session_id or user_session_id,
                    endpoint=response.endpoint or "",
                    region=region,
                    status="Ready" if response.endpoint else "Creating",
                )
        except Exception as error:  # noqa: BLE001 - cleanup boundary
            if _CREATE_SESSION_START_FAIL_CODE in str(error):
                cloud = await self._reconcile_created_session(
                    tool_id, user_session_id, region
                )
            else:
                logger.warning(
                    "Cancelled Sandbox create failed before cleanup: %s",
                    _safe_error_message(error),
                )
        if cloud is not None:
            try:
                await self.delete_session(cloud)
            except SandboxError as error:
                logger.warning(
                    "Failed to clean up cancelled Sandbox create: %s",
                    _safe_error_message(error),
                )

    async def delete_session(self, session: SandboxCloudSession) -> None:
        from agentkit.sdk.tools import types as tools_types

        try:
            await self._call(
                "delete_session",
                tools_types.DeleteSessionRequest(
                    ToolId=session.tool_id,
                    SessionId=session.instance_id,
                ),
                region=session.region,
            )
        except Exception as error:
            if _SESSION_NOT_FOUND_CODE in str(error):
                return
            raise SandboxProvisioningError(
                f"删除 AgentKit 沙箱会话失败：{_safe_error_message(error)}"
            ) from error

    async def _active_session_for_snapshot(
        self, snapshot: SandboxCloudSnapshot
    ) -> SandboxCloudSession | None:
        if not snapshot.user_session_id:
            return None
        from agentkit.sdk.tools import types as tools_types

        response = await self._call(
            "list_sessions",
            tools_types.ListSessionsRequest(
                ToolId=snapshot.tool_id,
                MaxResults=10,
                Filters=[
                    tools_types.FiltersItemForListSessions(
                        Name="UserSessionId",
                        Values=[snapshot.user_session_id],
                    )
                ],
            ),
            region=snapshot.region,
        )
        for value in response.session_infos or []:
            if str(getattr(value, "user_session_id", "") or "").strip() != (
                snapshot.user_session_id
            ):
                continue
            session = self._cloud_session(
                snapshot.tool_id,
                value,
                region=snapshot.region,
                fallback_user_session_id=snapshot.user_session_id,
            )
            if session.status.lower() == "ready" and session.endpoint:
                return session
        return None

    async def resume_snapshot(
        self, snapshot: SandboxCloudSnapshot
    ) -> SandboxCloudSession:
        from agentkit.sdk.tools import types as tools_types

        try:
            current = await self._active_session_for_snapshot(snapshot)
            if current is not None:
                return current
            response = await self._call(
                "resume_session_from_snapshot",
                tools_types.ResumeSessionFromSnapshotRequest(
                    ToolId=snapshot.tool_id,
                    SnapshotId=snapshot.snapshot_id,
                    Ttl=STUDIO_SANDBOX_TTL_SECONDS,
                    CreateNewInstance=False,
                ),
                region=snapshot.region,
            )
            session_id = str(response.session_id or "").strip()
            if not session_id:
                raise SandboxProvisioningError("AgentKit 唤醒快照响应缺少 SessionId。")
            latest: SandboxCloudSession | None = None
            for attempt in range(_RESUME_SESSION_ATTEMPTS):
                try:
                    value = await self._call(
                        "get_session",
                        tools_types.GetSessionRequest(
                            ToolId=snapshot.tool_id,
                            SessionId=session_id,
                        ),
                        region=snapshot.region,
                    )
                    latest = self._cloud_session(
                        snapshot.tool_id,
                        value,
                        region=snapshot.region,
                        fallback_user_session_id=snapshot.user_session_id,
                    )
                    status = latest.status.lower()
                    if status == "ready" and latest.endpoint:
                        return latest
                    if status in {"failed", "error", "deleted", "expired"}:
                        raise SandboxProvisioningError(
                            f"AgentKit 快照唤醒失败，当前状态：{latest.status}。"
                        )
                except Exception as error:
                    if not is_agentkit_resource_not_found(error):
                        raise
                if attempt + 1 < _RESUME_SESSION_ATTEMPTS:
                    await asyncio.sleep(_RESUME_SESSION_INTERVAL_SECONDS)
            last_status = latest.status if latest is not None else "Unknown"
            raise SandboxProvisioningError(
                f"AgentKit 快照唤醒超时，最后状态：{last_status}。"
            )
        except SandboxError:
            raise
        except Exception as error:
            raise SandboxProvisioningError(
                f"唤醒 AgentKit Session 快照失败：{_safe_error_message(error)}"
            ) from error

    async def delete_snapshot(self, snapshot: SandboxCloudSnapshot) -> None:
        from agentkit.sdk.tools import types as tools_types

        try:
            await self._call(
                "delete_session_snapshot",
                tools_types.DeleteSessionSnapshotRequest(
                    ToolId=snapshot.tool_id,
                    SnapshotId=snapshot.snapshot_id,
                ),
                region=snapshot.region,
            )
        except Exception as error:
            if _SESSION_NOT_FOUND_CODE in str(error):
                return
            raise SandboxProvisioningError(
                f"删除 AgentKit Session 快照失败：{_safe_error_message(error)}"
            ) from error

    async def drain(self) -> None:
        if self._background_tasks:
            await asyncio.gather(*tuple(self._background_tasks), return_exceptions=True)

    async def open_codex(self, session: SandboxCloudSession) -> SandboxCodexConnection:
        """Connect to Codex without exposing the private Session Endpoint."""
        connection = CodexAppServerSession(session.endpoint)
        try:
            await connection.connect()
        except CodexAppServerError as error:
            await connection.close()
            raise SandboxInvocationError(
                f"连接 AgentKit 沙箱失败：{_safe_error_message(error)}"
            ) from error
        return connection


class SandboxConversationService:
    """Manage reusable cloud Sessions and per-user conversation connections."""

    def __init__(
        self,
        gateway: SandboxCloudGateway,
        tool_id: str | None = None,
        snapshot_tool_id: str | None = None,
        agent_kind: str = _SANDBOX_CODEX_AGENT_KIND,
    ) -> None:
        self._gateway = gateway
        self._configured_tool_id = (tool_id or "").strip()
        self._configured_snapshot_tool_id = (snapshot_tool_id or "").strip()
        self._agent_kind = agent_kind
        self._sessions: dict[tuple[str, str], SandboxConversation] = {}
        self._registry_lock = asyncio.Lock()
        self._sessions_starting = 0

    def capabilities(self) -> dict[str, object]:
        """Report whether the dedicated Codex Tool is configured."""
        tools = self._tools()
        enabled = bool(tools.configured)
        return {
            "enabled": enabled,
            "reason": "" if enabled else "管理员未配置",
            "persistentEnabled": bool(tools.persistent),
            "persistentReason": "" if tools.persistent else "管理员未配置快照版 Tool",
            "endpointExportEnabled": _sandbox_endpoint_export_enabled(),
        }

    def _tools(self) -> SandboxToolPair:
        return SandboxToolPair(
            transient=(
                self._configured_tool_id
                or (os.getenv(_SANDBOX_CHAT_TOOL_ENV) or "").strip()
            ),
            persistent=(
                self._configured_snapshot_tool_id
                or (os.getenv(_SANDBOX_CHAT_SNAPSHOT_TOOL_ENV) or "").strip()
            ),
        )

    def _tool_id(self, *, persistent: bool = False, required: bool = True) -> str:
        tool_id = self._tools().select(persistent)
        if required and not tool_id:
            detail = "快照版 " if persistent else ""
            raise SandboxConfigurationError(f"管理员未配置{detail}Sandbox Tool。")
        return tool_id

    async def get_tool(self, *, persistent: bool = False) -> Any:
        """Read the configured transient or snapshot Sandbox Tool."""
        return await self._gateway.get_tool(self._tool_id(persistent=persistent))

    async def _cloud_session(self, session_id: str) -> SandboxCloudSession:
        """Find a Session across the configured transient and snapshot Tools."""
        tools = self._tools()
        if not tools.configured:
            self._tool_id()
        for tool_id in tools.configured:
            try:
                cloud = await self._gateway.get_session(tool_id, session_id)
            except SandboxSessionNotFoundError:
                continue
            cloud = _session_for_tools(cloud, tools)
            if not _session_matches_agent_kind(
                cloud,
                self._agent_kind,
                include_legacy=True,
            ):
                continue
            return cloud
        raise SandboxSessionNotFoundError("AgentKit Session 不存在或已过期。")

    async def list_sessions(
        self, owner_id: str, *, is_admin: bool = False
    ) -> list[SandboxCloudSession]:
        """List the configured account's Sessions without exposing Endpoints."""
        tools = self._tools()
        if not tools.configured:
            self._tool_id()
        sessions: dict[str, SandboxCloudSession] = {}
        for tool_id in tools.configured:
            found = await self._gateway.list_sessions(
                tool_id,
                None if is_admin else owner_id,
            )
            sessions.update(
                (session.instance_id, _session_for_tools(session, tools))
                for session in found
                if _session_matches_agent_kind(
                    session,
                    self._agent_kind,
                    include_legacy=True,
                )
            )
        return sorted(
            sessions.values(),
            key=lambda session: session.created_at,
            reverse=True,
        )

    async def list_snapshots(
        self, owner_id: str, *, is_admin: bool = False
    ) -> list[SandboxCloudSnapshot]:
        del owner_id
        tools = self._tools()
        if not is_admin or not tools.persistent:
            return []
        return await self._gateway.list_snapshots(tools.persistent)

    async def list_resources(
        self,
        owner_id: str,
        *,
        is_admin: bool = False,
        auto_resume_snapshots: bool = False,
    ) -> tuple[list[SandboxCloudSession], list[SandboxCloudSnapshot]]:
        sessions, snapshots = await asyncio.gather(
            self.list_sessions(owner_id, is_admin=is_admin),
            self.list_snapshots(owner_id, is_admin=is_admin),
        )
        restorable = _restorable_snapshots(sessions, snapshots)
        if auto_resume_snapshots and is_admin and restorable:
            await _auto_resume_snapshot_batch(
                restorable,
                self._resume_snapshot,
            )
            return await self.list_sessions(owner_id, is_admin=is_admin), []
        return sessions, restorable

    async def _resume_snapshot(
        self, snapshot: SandboxCloudSnapshot
    ) -> SandboxCloudSession:
        session = await self._gateway.resume_snapshot(snapshot)
        return _session_for_tools(
            replace(
                session,
                display_name=session.display_name or snapshot.display_name,
                created_by=session.created_by or snapshot.created_by,
            ),
            self._tools(),
        )

    async def resume_snapshot(
        self,
        snapshot_id: str,
        owner_id: str,
        *,
        is_admin: bool = False,
    ) -> SandboxCloudSession:
        snapshots = await self.list_snapshots(owner_id, is_admin=is_admin)
        snapshot = next(
            (item for item in snapshots if item.snapshot_id == snapshot_id),
            None,
        )
        if snapshot is None:
            raise SandboxSessionNotFoundError("智能体快照不存在或不属于当前用户。")
        return await self._resume_snapshot(snapshot)

    async def delete_snapshot(
        self,
        snapshot_id: str,
        owner_id: str,
        *,
        is_admin: bool = False,
    ) -> None:
        snapshots = await self.list_snapshots(owner_id, is_admin=is_admin)
        snapshot = next(
            (item for item in snapshots if item.snapshot_id == snapshot_id),
            None,
        )
        if snapshot is None:
            raise SandboxSessionNotFoundError("智能体快照不存在或不属于当前用户。")
        await self._gateway.delete_snapshot(snapshot)

    async def create(
        self,
        owner_id: str,
        display_name: object = "",
        creator_name: str = "",
        persistent: object = True,
        envs: Mapping[str, str] | None = None,
    ) -> SandboxCloudSession:
        """Create a cloud Session without opening a conversation connection."""
        if not isinstance(display_name, str):
            raise SandboxValidationError("智能体名称必须是文本。")
        display_name = display_name.strip()
        if len(display_name) > STUDIO_SANDBOX_DISPLAY_NAME_MAX_LENGTH:
            raise SandboxValidationError(
                f"智能体名称不能超过 {STUDIO_SANDBOX_DISPLAY_NAME_MAX_LENGTH} 个字符。"
            )
        if not isinstance(persistent, bool):
            raise SandboxValidationError("persistent 必须是布尔值。")
        session_envs: dict[str, str] | None = None
        if envs is not None:
            if not isinstance(envs, Mapping):
                raise SandboxValidationError("Session 环境变量格式无效。")
            session_envs = {}
            for key, value in envs.items():
                if key not in _SESSION_CREATE_ENV_ALLOWLIST:
                    raise SandboxValidationError("Session 环境变量不支持该键。")
                if not isinstance(value, str):
                    raise SandboxValidationError("Session 环境变量值必须是文本。")
                normalized = value.strip()
                if not normalized:
                    continue
                if key in _SESSION_MODEL_ENV_KEYS and not (
                    _SESSION_CODEX_MODEL_RE.fullmatch(normalized)
                ):
                    raise SandboxValidationError("模型 ID 格式无效。")
                session_envs[key] = normalized
            if not session_envs:
                session_envs = None
        tool_id = self._tool_id(persistent=persistent)
        await self.cleanup_expired()
        async with self._registry_lock:
            if len(self._sessions) + self._sessions_starting >= (
                STUDIO_SANDBOX_MAX_ACTIVE
            ):
                raise SandboxCapacityError("Sandbox 创建或连接数已达上限，请稍后重试。")
            self._sessions_starting += 1
        try:
            created = await self._gateway.create_session(
                tool_id,
                display_name,
                owner_id,
                creator_name,
                self._agent_kind,
                **({"envs": session_envs} if session_envs else {}),
            )
            authoritative = await self._gateway.get_session(
                tool_id, created.instance_id
            )
            return _session_for_tools(
                replace(
                    authoritative,
                    agent_kind=authoritative.agent_kind or self._agent_kind,
                ),
                self._tools(),
            )
        finally:
            async with self._registry_lock:
                self._sessions_starting -= 1

    async def connect(
        self,
        session_id: str,
        owner_id: str,
        *,
        is_admin: bool = False,
    ) -> SandboxConversation:
        """Attach an existing Ready cloud Session to the conversation bridge."""
        key = (owner_id, session_id)
        existing = self._sessions.get(key)
        if existing is not None:
            try:
                await existing.codex.ensure_connected()
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error
            return existing
        await self.cleanup_expired()
        async with self._registry_lock:
            existing = self._sessions.get(key)
            if existing is not None:
                try:
                    await existing.codex.ensure_connected()
                except CodexAppServerError as error:
                    raise SandboxInvocationError(_safe_error_message(error)) from error
                return existing
            if len(self._sessions) + self._sessions_starting >= (
                STUDIO_SANDBOX_MAX_ACTIVE
            ):
                raise SandboxCapacityError("智能体连接数已达上限，请稍后重试。")
            self._sessions_starting += 1
        try:
            cloud = await self._cloud_session(session_id)
            _require_session_access(cloud, owner_id, is_admin=is_admin)
            if cloud.status.lower() != "ready" or not cloud.endpoint:
                status = cloud.status or "Unknown"
                raise SandboxSessionUnavailableError(
                    f"AgentKit Session 尚未就绪，当前状态：{status}。"
                )
            codex = await self._gateway.open_codex(cloud)
            conversation = SandboxConversation(
                session_id=cloud.instance_id,
                owner_id=owner_id,
                cloud=cloud,
                codex=codex,
            )
            async with self._registry_lock:
                existing = self._sessions.get(key)
                if existing is not None:
                    await codex.close()
                    return existing
                self._sessions[key] = conversation
                return conversation
        finally:
            async with self._registry_lock:
                self._sessions_starting -= 1

    def _owned(self, session_id: str, owner_id: str) -> SandboxConversation:
        session = self._sessions.get((owner_id, session_id))
        if session is None:
            raise SandboxSessionNotFoundError("智能体尚未连接，请返回列表后重新进入。")
        return session

    def require_owned(self, session_id: str, owner_id: str) -> None:
        """Fail before an SSE response starts when a session is unavailable."""
        self._owned(session_id, owner_id)

    async def stream_message(
        self,
        session_id: str,
        owner_id: str,
        prompt: str,
        skill_ids: tuple[str, ...] = (),
        *,
        turn_permissions: CodexPermissionSettings | None = None,
        turn_timeout_seconds: float | None = None,
        turn_output_schema: dict[str, object] | None = None,
    ) -> AsyncIterator[SandboxStreamEvent]:
        session = self._owned(session_id, owner_id)
        if session.background_turn is not None and not session.background_turn.done():
            raise SandboxSessionUnavailableError("当前 Codex 任务仍在运行。")
        queue: asyncio.Queue[SandboxStreamEvent | SandboxError | None] = asyncio.Queue()
        listening = True

        async def _run_turn() -> None:
            nonlocal listening
            try:
                async with session.lock:
                    session.pending_prompt = prompt
                    session.pending_prompt_timestamp = int(time.time() * 1_000)
                    try:
                        if (
                            turn_permissions is None
                            and turn_timeout_seconds is None
                            and turn_output_schema is None
                        ):
                            events = (
                                session.codex.stream_turn(prompt, skill_ids)
                                if skill_ids
                                else session.codex.stream_turn(prompt)
                            )
                        else:
                            events = session.codex.stream_turn(
                                prompt,
                                skill_ids,
                                permissions=turn_permissions,
                                timeout_seconds=turn_timeout_seconds,
                                output_schema=turn_output_schema,
                            )
                        async for event in events:
                            if event.kind and listening:
                                queue.put_nowait(
                                    SandboxStreamEvent(
                                        kind=event.kind,
                                        item_id=event.item_id,
                                        status=event.status,
                                        text=_public_event_text(event.text),
                                        name=_safe_error_message(event.name),
                                        arguments=_safe_public_value(event.arguments),
                                        response=_safe_public_value(event.response),
                                        thread_id=session.codex.thread_id,
                                        approval=(
                                            _safe_public_value(
                                                event.approval.public_dict()
                                            )
                                            if event.approval is not None
                                            else None
                                        ),
                                        approval_resolved_id=(
                                            event.approval_resolved_id
                                        ),
                                        turn_id=event.turn_id,
                                        usage=event.usage,
                                        thread_total=event.thread_total,
                                        model_context_window=(
                                            event.model_context_window
                                        ),
                                    )
                                )
                    finally:
                        session.pending_prompt = ""
                        session.pending_prompt_timestamp = 0
            except CodexAppServerError as error:
                if listening:
                    queue.put_nowait(_sandbox_invocation_error(error))
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - background task boundary
                if listening:
                    queue.put_nowait(SandboxInvocationError(_safe_error_message(error)))
            finally:
                if listening:
                    queue.put_nowait(None)

        turn = asyncio.create_task(
            _run_turn(),
            name=f"sandbox-turn-{session_id}",
        )
        session.background_turn = turn

        def _release_turn(task: asyncio.Task[None]) -> None:
            if session.background_turn is task:
                session.background_turn = None
            if not task.cancelled():
                task.exception()

        turn.add_done_callback(_release_turn)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    return
                if isinstance(event, SandboxError):
                    raise event
                yield event
        finally:
            listening = False

    async def interrupt(self, session_id: str, owner_id: str) -> None:
        """Stop a turn only after an explicit user action."""
        session = self._owned(session_id, owner_id)
        try:
            await session.codex.interrupt()
        except CodexAppServerError as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error

    def settings(self, session_id: str, owner_id: str) -> dict[str, object]:
        """Return the current permissions, workspace, and lock state."""
        session = self._owned(session_id, owner_id)
        return {
            "threadId": session.codex.thread_id,
            "cwd": session.codex.cwd,
            **(
                {"model": session.codex.model}
                if getattr(session.codex, "model", "")
                else {}
            ),
            "workspaceLocked": session.codex.workspace_locked,
            "busy": session.codex.active,
            "permissions": session.codex.permissions.public_dict(),
        }

    def status(self, session_id: str, owner_id: str) -> dict[str, object]:
        """Return current thread settings and exact usage when available."""
        session = self._owned(session_id, owner_id)
        total = getattr(session.codex, "thread_token_total", None)
        context_window = getattr(session.codex, "model_context_window", None)
        return {
            **self.settings(session_id, owner_id),
            **(
                {"threadTotal": total.public_dict()}
                if isinstance(total, CodexTokenUsage)
                else {}
            ),
            **(
                {"modelContextWindow": context_window}
                if isinstance(context_window, int)
                else {}
            ),
        }

    def export_endpoint(self, session_id: str, owner_id: str) -> dict[str, object]:
        """Return the raw Sandbox endpoint only when explicitly enabled."""
        if not _sandbox_endpoint_export_enabled():
            raise SandboxPermissionError("管理员未启用 Sandbox Endpoint 导出。")
        session = self._owned(session_id, owner_id)
        if not session.cloud.endpoint:
            raise SandboxSessionUnavailableError("AgentKit Session 暂无可用 Endpoint。")
        return {
            "endpoint": session.cloud.endpoint,
            "sessionId": session.cloud.instance_id,
            "expireAt": session.cloud.expire_at,
        }

    async def list_models(
        self, session_id: str, owner_id: str
    ) -> tuple[CodexModel, ...]:
        """List visible models for the connected Codex session."""
        session = self._owned(session_id, owner_id)
        try:
            return await session.codex.list_models()
        except CodexAppServerError as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error

    async def set_model(self, session_id: str, owner_id: str, model: str) -> str:
        """Change the model without forwarding slash syntax as a prompt."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                return await session.codex.set_model(model)
            except (TypeError, ValueError) as error:
                raise SandboxValidationError(str(error)) from error
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error

    async def list_skills(
        self,
        session_id: str,
        owner_id: str,
        *,
        force_reload: bool = False,
    ) -> tuple[CodexSkill, ...]:
        """List Skills without exposing server-side paths."""
        session = self._owned(session_id, owner_id)
        try:
            return await session.codex.list_skills(force_reload)
        except CodexAppServerError as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error

    def _public_snapshot(
        self, session: SandboxConversation, snapshot: CodexThreadSnapshot
    ) -> dict[str, object]:
        raw_value = snapshot.public_dict(session.codex.permissions)
        raw_value.pop("messages", None)
        value = _safe_public_value(raw_value)
        if not isinstance(value, dict):
            raise SandboxInvocationError("Codex Thread 响应格式无效。")
        value["messages"] = [
            {
                "id": _redact_public_text(message.id, maximum=500),
                "role": message.role,
                "content": _redact_public_text(message.content, maximum=20_000),
                "timestamp": message.timestamp,
                **(
                    {
                        "skillNames": [
                            _redact_public_text(name, maximum=200)
                            for name in message.skill_names
                        ]
                    }
                    if message.skill_names
                    else {}
                ),
                **(
                    {
                        "images": [
                            {
                                "mimeType": image.mime_type,
                                "data": image.data,
                                **(
                                    {
                                        "name": _redact_public_text(
                                            image.name,
                                            maximum=255,
                                        )
                                    }
                                    if image.name
                                    else {}
                                ),
                                **(
                                    {
                                        "alt": _redact_public_text(
                                            image.alt,
                                            maximum=500,
                                        )
                                    }
                                    if image.alt
                                    else {}
                                ),
                            }
                            for image in message.images
                        ]
                    }
                    if message.images
                    else {}
                ),
            }
            for message in snapshot.messages[-_SANDBOX_THREAD_HISTORY_MAX_MESSAGES:]
        ]
        return value

    async def new_thread(self, session_id: str, owner_id: str) -> dict[str, object]:
        """Create and activate a fresh Codex thread."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                snapshot = await session.codex.new_thread()
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error
        return self._public_snapshot(session, snapshot)

    async def list_threads(
        self,
        session_id: str,
        owner_id: str,
        *,
        cursor: str = "",
        search_term: str = "",
        archived: bool = False,
    ) -> tuple[tuple[CodexThreadSummary, ...], str]:
        """List recent Codex threads."""
        session = self._owned(session_id, owner_id)
        try:
            return await session.codex.list_threads(
                cursor=cursor,
                search_term=search_term,
                archived=archived,
            )
        except CodexAppServerError as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error

    async def resume_thread(
        self, session_id: str, owner_id: str, thread_id: str
    ) -> dict[str, object]:
        """Resume and activate a selected Codex thread."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                snapshot = await session.codex.resume_thread(thread_id)
            except ValueError as error:
                raise SandboxValidationError(str(error)) from error
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error
        return self._public_snapshot(session, snapshot)

    async def read_thread(
        self, session_id: str, owner_id: str, thread_id: str
    ) -> dict[str, object]:
        """Read a Codex thread without changing the active conversation."""
        session = self._owned(session_id, owner_id)
        try:
            snapshot = await session.codex.read_thread(thread_id)
        except ValueError as error:
            raise SandboxValidationError(str(error)) from error
        except CodexAppServerError as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error
        pending_prompt = session.pending_prompt
        pending_timestamp = session.pending_prompt_timestamp
        if pending_prompt and not any(
            message.role == "user"
            and message.content == pending_prompt
            and message.timestamp >= pending_timestamp - 2_000
            for message in snapshot.messages[-4:]
        ):
            snapshot = replace(
                snapshot,
                messages=snapshot.messages
                + (
                    CodexThreadMessage(
                        id=f"pending-{thread_id}-{pending_timestamp}",
                        role="user",
                        content=pending_prompt,
                        timestamp=pending_timestamp,
                    ),
                ),
                workspace_locked=True,
            )
        return self._public_snapshot(session, snapshot)

    async def inject_history(
        self,
        session_id: str,
        owner_id: str,
        messages: tuple[CodexImportedMessage, ...],
    ) -> None:
        """Seed a fresh Codex thread with visible local conversation history."""
        if not messages:
            return
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                await session.codex.inject_history(messages)
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error

    async def fork_thread(self, session_id: str, owner_id: str) -> dict[str, object]:
        """Fork and activate the current Codex thread."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                snapshot = await session.codex.fork_thread()
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error
        return self._public_snapshot(session, snapshot)

    async def archive_thread(
        self, session_id: str, owner_id: str, thread_id: str
    ) -> dict[str, object]:
        """Archive a thread and return a replacement snapshot when needed."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                snapshot = await session.codex.archive_thread(thread_id)
            except ValueError as error:
                raise SandboxValidationError(str(error)) from error
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error
        return {
            "archived": True,
            **(
                self._public_snapshot(session, snapshot) if snapshot is not None else {}
            ),
        }

    async def delete_thread(
        self, session_id: str, owner_id: str, thread_id: str
    ) -> dict[str, object]:
        """Remove a thread from history and replace it when it was active."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                snapshot = await session.codex.delete_thread(thread_id)
            except ValueError as error:
                raise SandboxValidationError(str(error)) from error
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error
        return {
            "deleted": True,
            **(
                self._public_snapshot(session, snapshot) if snapshot is not None else {}
            ),
        }

    async def compact_thread(self, session_id: str, owner_id: str) -> None:
        """Start compacting the current Codex thread."""
        session = self._owned(session_id, owner_id)
        async with session.lock:
            try:
                await session.codex.compact_thread()
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error

    async def update_permissions(
        self,
        session_id: str,
        owner_id: str,
        settings: CodexPermissionSettings,
    ) -> CodexPermissionSettings:
        """Persist permissions and adopt them in every local thread."""
        session = self._owned(session_id, owner_id)
        if session.codex.active:
            raise SandboxSessionUnavailableError("当前任务运行中，暂时不能修改权限。")
        async with session.lock:
            try:
                applied = await session.codex.update_permissions(settings)
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error

        peers = [
            candidate
            for candidate in self._sessions.values()
            if candidate.session_id == session_id and candidate is not session
        ]
        results = await asyncio.gather(
            *(peer.codex.apply_session_permissions(applied) for peer in peers),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    "Failed to hot-apply Sandbox permissions to a peer: %s",
                    _safe_error_message(result),
                )
        return applied

    async def update_workspace(self, session_id: str, owner_id: str, cwd: str) -> str:
        """Change the thread workspace before the first conversation turn."""
        session = self._owned(session_id, owner_id)
        if session.codex.active or session.codex.workspace_locked:
            raise SandboxSessionUnavailableError(
                "当前对话已经开始，工作空间不能再修改。"
            )
        async with session.lock:
            try:
                return await session.codex.update_workspace(cwd)
            except (TypeError, ValueError) as error:
                raise SandboxValidationError(str(error)) from error
            except CodexAppServerError as error:
                raise SandboxInvocationError(_safe_error_message(error)) from error

    async def list_directories(
        self, session_id: str, owner_id: str, path: str
    ) -> CodexDirectoryListing:
        """List directories in the remote Sandbox."""
        session = self._owned(session_id, owner_id)
        try:
            return await session.codex.list_directories(path)
        except (TypeError, ValueError) as error:
            raise SandboxValidationError(str(error)) from error
        except CodexAppServerError as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error

    def resolve_approval(
        self,
        session_id: str,
        owner_id: str,
        approval_id: str,
        decision: ApprovalDecision,
    ) -> None:
        """Resolve an approval without waiting on the active turn lock."""
        session = self._owned(session_id, owner_id)
        try:
            session.codex.resolve_approval(approval_id, decision)
        except CodexAppServerError as error:
            raise SandboxValidationError(str(error)) from error

    async def launch_terminal(
        self, session_id: str, owner_id: str
    ) -> tuple[str, str, str]:
        """Create a shell and return its native browser URL and capability."""
        session = self._owned(session_id, owner_id)
        try:
            url, shell_session_id = await terminal_launch_url(
                session.cloud.endpoint,
                session_id,
                direct=True,
            )
        except (RuntimeError, TypeError, ValueError) as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error
        return url, shell_session_id, session.proxy_token

    def launch_browser(self, session_id: str, owner_id: str) -> tuple[str, str]:
        """Return the Browser UI's native URL and capability."""
        session = self._owned(session_id, owner_id)
        try:
            url = browser_launch_url(
                session_id,
                endpoint=session.cloud.endpoint,
                direct=True,
            )
        except (RuntimeError, TypeError, ValueError) as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error
        return url, session.proxy_token

    async def upload_file(
        self,
        session_id: str,
        owner_id: str,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> str:
        """Upload a browser attachment into the current remote workspace."""
        session = self._owned(session_id, owner_id)
        try:
            return await upload_sandbox_file(
                session.cloud.endpoint,
                session.codex.cwd,
                file_name,
                content_type,
                content,
            )
        except (RuntimeError, TypeError, ValueError) as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error

    def resolve_proxy_target(self, session_id: str, token: str) -> SandboxProxyTarget:
        """Resolve an opaque data-plane capability without browser identity."""
        found = False
        for session in self._sessions.values():
            if session.session_id != session_id:
                continue
            found = True
            if token and secrets.compare_digest(token, session.proxy_token):
                return SandboxProxyTarget(endpoint=session.cloud.endpoint)
        if found:
            raise PermissionError("invalid Sandbox proxy capability")
        raise KeyError(session_id)

    async def close(self, session_id: str, owner_id: str) -> None:
        """Disconnect the local bridge without deleting the cloud Session."""
        session = self._owned(session_id, owner_id)
        if session.background_turn is not None and not session.background_turn.done():
            return
        async with session.lock:
            self._sessions.pop((owner_id, session_id), None)
            await session.codex.close()

    async def delete(
        self,
        session_id: str,
        owner_id: str,
        *,
        is_admin: bool = False,
    ) -> None:
        """Delete a cloud Session and close its local bridge when connected."""
        key = (owner_id, session_id)
        if not is_admin and any(
            candidate_id == session_id and candidate_owner != owner_id
            for candidate_owner, candidate_id in self._sessions
        ):
            raise SandboxSessionNotFoundError("智能体 Session 不存在或不属于当前用户。")
        session = self._sessions.pop(key, None)
        if session is None:
            cloud = await self._cloud_session(session_id)
            _require_session_access(cloud, owner_id, is_admin=is_admin)
        else:
            cloud = session.cloud
            async with session.lock:
                await session.codex.close()
        if is_admin:
            other_sessions = [
                candidate
                for (candidate_owner, candidate_id), candidate in self._sessions.items()
                if candidate_id == session_id and candidate_owner != owner_id
            ]
            for candidate in other_sessions:
                self._sessions.pop((candidate.owner_id, candidate.session_id), None)
                async with candidate.lock:
                    await candidate.codex.close()
        await self._gateway.delete_session(cloud)

    async def cleanup_expired(self) -> None:
        """Drop local connections that exceeded their remote TTL window."""
        now = time.monotonic()
        expired = [
            (session.session_id, session.owner_id)
            for session in self._sessions.values()
            if session.expires_at <= now
        ]
        for session_id, owner_id in expired:
            try:
                await self.close(session_id, owner_id)
            except SandboxError as error:
                logger.warning(
                    "Failed to disconnect expired Sandbox Session %s: %s",
                    session_id,
                    _safe_error_message(error),
                )

    async def close_all(self) -> None:
        """Drop local connections while leaving cloud Sessions reusable."""
        sessions = tuple(self._sessions.values())
        self._sessions.clear()
        if sessions:
            await asyncio.gather(
                *(session.codex.close() for session in sessions),
                return_exceptions=True,
            )
        await self._gateway.drain()


class SandboxAgentSessionService:
    """List, create, and securely open managed branded WebUI Sessions."""

    def __init__(
        self,
        gateway: SandboxCloudGateway,
        *,
        kind: str,
        tool_id: str | None = None,
        snapshot_tool_id: str | None = None,
        surface_path: str | None = None,
        filter_agent_kind: bool = False,
    ) -> None:
        if kind not in _SANDBOX_AGENT_TOOL_ENVS:
            raise ValueError(f"Unsupported Studio sandbox agent kind: {kind}")
        self._gateway = gateway
        self.kind = kind
        surface = (surface_path or f"/{kind}/").strip()
        self.surface_path = f"/{surface.strip('/')}/"
        self._filter_agent_kind = filter_agent_kind
        self._configured_tool_id = (tool_id or "").strip()
        self._configured_snapshot_tool_id = (snapshot_tool_id or "").strip()
        self._workspaces: dict[
            tuple[str, str], tuple[SandboxCloudSession, str, float]
        ] = {}
        self._created_session_ids: set[str] = set()

    def _tools(self) -> SandboxToolPair:
        transient = self._configured_tool_id
        if not transient:
            transient = next(
                (
                    value
                    for env_name in _SANDBOX_AGENT_TOOL_ENVS[self.kind]
                    if (value := (os.getenv(env_name) or "").strip())
                ),
                "",
            )
        persistent = (
            self._configured_snapshot_tool_id
            or (os.getenv(_SANDBOX_AGENT_SNAPSHOT_TOOL_ENVS[self.kind]) or "").strip()
        )
        return SandboxToolPair(transient=transient, persistent=persistent)

    def _tool_id(self, *, persistent: bool = False, required: bool = True) -> str:
        tool_id = self._tools().select(persistent)
        if required and not tool_id:
            detail = "快照版 " if persistent else ""
            raise SandboxConfigurationError(f"管理员未配置{detail}Sandbox Tool。")
        return tool_id

    def capabilities(self) -> dict[str, object]:
        tools = self._tools()
        enabled = bool(tools.configured)
        return {
            "enabled": enabled,
            "reason": "" if enabled else "管理员未配置",
            "persistentEnabled": bool(tools.persistent),
            "persistentReason": "" if tools.persistent else "管理员未配置快照版 Tool",
        }

    async def _cloud_session(self, session_id: str) -> SandboxCloudSession:
        tools = self._tools()
        if not tools.configured:
            self._tool_id()
        for tool_id in tools.configured:
            try:
                cloud = await self._gateway.get_session(tool_id, session_id)
            except SandboxSessionNotFoundError:
                continue
            cloud = _session_for_tools(cloud, tools)
            if (
                self._filter_agent_kind
                and cloud.instance_id not in self._created_session_ids
                and not _session_matches_agent_kind(cloud, self.kind)
            ):
                continue
            if self._filter_agent_kind and not cloud.agent_kind:
                cloud = replace(cloud, agent_kind=self.kind)
            return cloud
        raise SandboxSessionNotFoundError("AgentKit Session 不存在或已过期。")

    async def list_sessions(
        self, owner_id: str, *, is_admin: bool = False
    ) -> list[SandboxCloudSession]:
        tools = self._tools()
        if not tools.configured:
            self._tool_id()
        sessions: dict[str, SandboxCloudSession] = {}
        for tool_id in tools.configured:
            found = await self._gateway.list_sessions(
                tool_id,
                None if is_admin else owner_id,
            )
            for session in found:
                session = _session_for_tools(session, tools)
                if (
                    self._filter_agent_kind
                    and session.instance_id not in self._created_session_ids
                    and not _session_matches_agent_kind(session, self.kind)
                ):
                    continue
                if self._filter_agent_kind and not session.agent_kind:
                    session = replace(session, agent_kind=self.kind)
                sessions[session.instance_id] = session
        return sorted(
            sessions.values(),
            key=lambda session: session.created_at,
            reverse=True,
        )

    async def list_snapshots(
        self, owner_id: str, *, is_admin: bool = False
    ) -> list[SandboxCloudSnapshot]:
        del owner_id
        tools = self._tools()
        if not is_admin or not tools.persistent:
            return []
        return await self._gateway.list_snapshots(tools.persistent)

    async def list_resources(
        self,
        owner_id: str,
        *,
        is_admin: bool = False,
        auto_resume_snapshots: bool = False,
    ) -> tuple[list[SandboxCloudSession], list[SandboxCloudSnapshot]]:
        sessions, snapshots = await asyncio.gather(
            self.list_sessions(owner_id, is_admin=is_admin),
            self.list_snapshots(owner_id, is_admin=is_admin),
        )
        restorable = _restorable_snapshots(sessions, snapshots)
        if auto_resume_snapshots and is_admin and restorable:
            await _auto_resume_snapshot_batch(
                restorable,
                self._resume_snapshot,
            )
            return await self.list_sessions(owner_id, is_admin=is_admin), []
        return sessions, restorable

    async def _resume_snapshot(
        self, snapshot: SandboxCloudSnapshot
    ) -> SandboxCloudSession:
        session = await self._gateway.resume_snapshot(snapshot)
        return _session_for_tools(
            replace(
                session,
                display_name=session.display_name or snapshot.display_name,
                created_by=session.created_by or snapshot.created_by,
            ),
            self._tools(),
        )

    async def resume_snapshot(
        self,
        snapshot_id: str,
        owner_id: str,
        *,
        is_admin: bool = False,
    ) -> SandboxCloudSession:
        snapshots = await self.list_snapshots(owner_id, is_admin=is_admin)
        snapshot = next(
            (item for item in snapshots if item.snapshot_id == snapshot_id),
            None,
        )
        if snapshot is None:
            raise SandboxSessionNotFoundError("智能体快照不存在或不属于当前用户。")
        return await self._resume_snapshot(snapshot)

    async def delete_snapshot(
        self,
        snapshot_id: str,
        owner_id: str,
        *,
        is_admin: bool = False,
    ) -> None:
        snapshots = await self.list_snapshots(owner_id, is_admin=is_admin)
        snapshot = next(
            (item for item in snapshots if item.snapshot_id == snapshot_id),
            None,
        )
        if snapshot is None:
            raise SandboxSessionNotFoundError("智能体快照不存在或不属于当前用户。")
        await self._gateway.delete_snapshot(snapshot)

    async def create(
        self,
        owner_id: str,
        display_name: object = "",
        creator_name: str = "",
        persistent: object = True,
    ) -> SandboxCloudSession:
        if not isinstance(display_name, str):
            raise SandboxValidationError("智能体名称必须是文本。")
        display_name = display_name.strip()
        if len(display_name) > STUDIO_SANDBOX_DISPLAY_NAME_MAX_LENGTH:
            raise SandboxValidationError(
                f"智能体名称不能超过 {STUDIO_SANDBOX_DISPLAY_NAME_MAX_LENGTH} 个字符。"
            )
        if not isinstance(persistent, bool):
            raise SandboxValidationError("persistent 必须是布尔值。")
        tool_id = self._tool_id(persistent=persistent)
        created = await self._gateway.create_session(
            tool_id,
            display_name,
            owner_id,
            creator_name,
            self.kind,
        )
        authoritative = await self._gateway.get_session(tool_id, created.instance_id)
        self._created_session_ids.add(created.instance_id)
        return _session_for_tools(
            replace(authoritative, agent_kind=authoritative.agent_kind or self.kind),
            self._tools(),
        )

    async def open(
        self,
        session_id: str,
        owner_id: str,
        *,
        is_admin: bool = False,
    ) -> tuple[SandboxCloudSession, str]:
        """Resolve one ready Session and issue an opaque WebUI capability."""
        self._cleanup_expired()
        cloud = await self._cloud_session(session_id)
        _require_session_access(cloud, owner_id, is_admin=is_admin)
        if cloud.status.lower() != "ready" or not cloud.endpoint:
            status = cloud.status or "Unknown"
            raise SandboxSessionUnavailableError(
                f"AgentKit Session 尚未就绪，当前状态：{status}。"
            )
        token = secrets.token_urlsafe(32)
        self._workspaces[(owner_id, session_id)] = (
            cloud,
            token,
            time.monotonic() + STUDIO_SANDBOX_TTL_SECONDS,
        )
        return cloud, token

    async def delete(
        self,
        session_id: str,
        owner_id: str,
        *,
        is_admin: bool = False,
    ) -> None:
        """Delete one managed cloud Session and revoke its local workspace."""
        if not is_admin and any(
            candidate_id == session_id and candidate_owner != owner_id
            for candidate_owner, candidate_id in self._workspaces
        ):
            raise SandboxSessionNotFoundError("智能体 Session 不存在或不属于当前用户。")
        workspace = self._workspaces.get((owner_id, session_id))
        cloud = (
            workspace[0]
            if workspace is not None
            else await self._cloud_session(session_id)
        )
        _require_session_access(cloud, owner_id, is_admin=is_admin)
        self._workspaces = {
            key: workspace
            for key, workspace in self._workspaces.items()
            if key[1] != session_id or (not is_admin and key[0] != owner_id)
        }
        self._created_session_ids.discard(session_id)
        await self._gateway.delete_session(cloud)

    async def launch_terminal(
        self,
        session_id: str,
        owner_id: str,
    ) -> tuple[str, str, str]:
        """Create a shell for an opened branded Session."""
        cloud, token, _expires_at = self._workspace(session_id, owner_id)
        try:
            url, shell_session_id = await terminal_launch_url(
                cloud.endpoint,
                session_id,
                direct=True,
            )
        except (RuntimeError, TypeError, ValueError) as error:
            raise SandboxInvocationError(_safe_error_message(error)) from error
        return url, shell_session_id, token

    def resolve_proxy_target(
        self,
        session_id: str,
        token: str,
    ) -> SandboxProxyTarget:
        """Resolve an opaque capability for WebUI or Terminal proxying."""
        self._cleanup_expired()
        found = False
        for cloud, candidate, _expires_at in self._workspaces.values():
            if cloud.instance_id != session_id:
                continue
            found = True
            if token and secrets.compare_digest(token, candidate):
                return SandboxProxyTarget(endpoint=cloud.endpoint)
        if found:
            raise PermissionError("invalid managed agent proxy capability")
        raise KeyError(session_id)

    def _workspace(
        self,
        session_id: str,
        owner_id: str,
    ) -> tuple[SandboxCloudSession, str, float]:
        self._cleanup_expired()
        workspace = self._workspaces.get((owner_id, session_id))
        if workspace is None:
            raise SandboxSessionNotFoundError(
                "智能体 Session 尚未打开，请返回列表后重新进入。"
            )
        return workspace

    def _cleanup_expired(self) -> None:
        now = time.monotonic()
        self._workspaces = {
            key: workspace
            for key, workspace in self._workspaces.items()
            if workspace[2] > now
        }


def _public_snapshot(
    snapshot: SandboxCloudSnapshot,
    tool_name: str,
    owner_id: str | None = None,
) -> dict[str, object]:
    status = (
        "Wakeable"
        if snapshot.status.strip().lower() in _RESTORABLE_SNAPSHOT_STATUSES
        else snapshot.status
    )
    return {
        "snapshotId": snapshot.snapshot_id,
        "sessionId": snapshot.session_id,
        "userSessionId": snapshot.user_session_id,
        "status": status,
        "snapshotStatus": snapshot.status,
        "reason": snapshot.reason,
        "createdAt": snapshot.created_at,
        "createdBy": snapshot.created_by,
        "region": snapshot.region,
        "isMine": bool(owner_id and snapshot.created_by == owner_id),
        "displayName": snapshot.display_name,
        "toolName": tool_name,
    }


def mount_sandbox_agent_routes(
    app: Any,
    services: dict[str, SandboxAgentSessionService],
    owner_resolver: Callable[[Any], str],
    admin_resolver: Callable[[Any], bool] | None = None,
    creator_resolver: Callable[[Any], str] | None = None,
) -> None:
    """Mount list/create/open routes for managed agent Sessions."""
    from fastapi import HTTPException

    from veadk.cli.frontend_agent_proxy import (
        agent_surface_prefix,
        mount_agent_surface_proxy_routes,
    )

    def _service(kind: str) -> SandboxAgentSessionService:
        service = services.get(kind)
        if service is None:
            raise HTTPException(status_code=404, detail="未知的沙箱智能体类型。")
        return service

    def _is_admin(request: Request) -> bool:
        return bool(admin_resolver and admin_resolver(request))

    def _http_error(error: SandboxError) -> HTTPException:
        status_code = 500
        if isinstance(error, SandboxConfigurationError):
            status_code = 503
        elif isinstance(error, SandboxPermissionError):
            status_code = 403
        elif isinstance(error, SandboxValidationError):
            status_code = 422
        elif isinstance(error, SandboxSessionNotFoundError):
            status_code = 404
        elif isinstance(error, SandboxSessionUnavailableError):
            status_code = 409
        elif isinstance(error, SandboxProvisioningError):
            status_code = 502
        return HTTPException(
            status_code=status_code,
            detail={
                "code": error.code,
                "message": str(error),
                "retryable": error.retryable,
            },
        )

    def _public_session(
        session: SandboxCloudSession,
        kind: str,
        owner_id: str | None = None,
    ) -> dict[str, object]:
        return {
            "sessionId": session.instance_id,
            "userSessionId": session.user_session_id,
            "status": session.status,
            "createdAt": session.created_at,
            "expireAt": session.expire_at,
            "toolType": session.tool_type,
            "createdBy": session.creator_name or session.created_by,
            "region": session.region,
            "isMine": bool(owner_id and session.created_by == owner_id),
            "displayName": session.display_name,
            "toolName": kind,
            "persistent": session.persistent,
        }

    @app.get("/web/{kind}/capabilities")
    async def _sandbox_agent_capabilities(
        kind: str,
        request: Request,
    ) -> dict[str, object]:
        owner_resolver(request)
        return _service(kind).capabilities()

    @app.get("/web/{kind}/sessions")
    async def _list_sandbox_agent_sessions(
        kind: str,
        request: Request,
    ) -> dict[str, object]:
        try:
            owner_id = owner_resolver(request)
            sessions, snapshots = await _service(kind).list_resources(
                owner_id,
                is_admin=_is_admin(request),
                auto_resume_snapshots=_request_auto_resume_snapshots(
                    request,
                    default=True,
                ),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        result: dict[str, object] = {
            "sessions": [
                _public_session(session, kind, owner_id) for session in sessions
            ]
        }
        if snapshots:
            result["snapshots"] = [
                _public_snapshot(snapshot, kind, owner_id) for snapshot in snapshots
            ]
        return result

    @app.post("/web/{kind}/sessions")
    async def _create_sandbox_agent_session(
        kind: str,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            body = await request.body()
            if body:
                try:
                    data = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError) as error:
                    raise SandboxValidationError(
                        "创建智能体的请求不是有效 JSON。"
                    ) from error
                if not isinstance(data, dict):
                    raise SandboxValidationError("创建智能体的请求格式无效。")
            else:
                data = {}
            session = await _service(kind).create(
                owner_id,
                data.get("displayName", ""),
                creator_resolver(request) if creator_resolver else owner_id,
                data.get("persistent", True),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return _public_session(session, kind, owner_id)

    @app.post("/web/{kind}/snapshots/{snapshot_id}/resume")
    async def _resume_sandbox_agent_snapshot(
        kind: str,
        snapshot_id: str,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            session = await _service(kind).resume_snapshot(
                snapshot_id,
                owner_id,
                is_admin=_is_admin(request),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return _public_session(session, kind, owner_id)

    @app.delete("/web/{kind}/snapshots/{snapshot_id}")
    async def _delete_sandbox_agent_snapshot(
        kind: str,
        snapshot_id: str,
        request: Request,
    ) -> dict[str, bool]:
        try:
            await _service(kind).delete_snapshot(
                snapshot_id,
                owner_resolver(request),
                is_admin=_is_admin(request),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return {"deleted": True}

    @app.post("/web/{kind}/sessions/{session_id}/open")
    async def _open_sandbox_agent_session(
        kind: str,
        session_id: str,
        request: Request,
    ) -> dict[str, object]:
        service = _service(kind)
        owner_id = owner_resolver(request)
        try:
            session, token = await service.open(
                session_id,
                owner_id,
                is_admin=_is_admin(request),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        prefix = agent_surface_prefix(kind, session_id, token)
        return {
            **_public_session(session, kind, owner_id),
            "webuiUrl": f"{prefix}{service.surface_path}",
        }

    @app.delete("/web/{kind}/sessions/{session_id}")
    async def _delete_sandbox_agent_session(
        kind: str,
        session_id: str,
        request: Request,
    ) -> dict[str, bool]:
        try:
            await _service(kind).delete(
                session_id,
                owner_resolver(request),
                is_admin=_is_admin(request),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return {"deleted": True}

    @app.post("/web/{kind}/sessions/{session_id}/terminal")
    async def _open_sandbox_agent_terminal(
        kind: str,
        session_id: str,
        request: Request,
    ) -> JSONResponse:
        try:
            url, shell_session_id, token = await _service(kind).launch_terminal(
                session_id,
                owner_resolver(request),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        response = JSONResponse({"url": url, "shellSessionId": shell_session_id})
        response.headers["Cache-Control"] = "no-store"
        forwarded_protocol = (
            request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        )
        response.set_cookie(
            proxy_cookie_name(session_id),
            token,
            max_age=STUDIO_SANDBOX_TTL_SECONDS,
            httponly=True,
            secure=(request.url.scheme == "https" or forwarded_protocol == "https"),
            samesite="strict",
            path=proxy_prefix(session_id, "terminal").rsplit("/", 1)[0],
        )
        return response

    def _surface_target(
        kind: str,
        session_id: str,
        token: str,
    ) -> SandboxProxyTarget:
        return _service(kind).resolve_proxy_target(session_id, token)

    mount_agent_surface_proxy_routes(app, _surface_target)


def mount_sandbox_routes(
    app: Any,
    service: SandboxConversationService,
    owner_resolver: Callable[[Any], str],
    proxy_target_resolver: Callable[[str, str], SandboxProxyTarget] | None = None,
    admin_resolver: Callable[[Any], bool] | None = None,
    creator_resolver: Callable[[Any], str] | None = None,
) -> None:
    """Mount Studio HTTP routes for reusable Sandbox Sessions."""
    from fastapi import HTTPException

    def _http_error(error: SandboxError) -> HTTPException:
        status_code = 500
        if isinstance(error, SandboxConfigurationError):
            status_code = 503
        elif isinstance(error, SandboxPermissionError):
            status_code = 403
        elif isinstance(error, SandboxValidationError):
            status_code = 422
        elif isinstance(error, SandboxSessionNotFoundError):
            status_code = 404
        elif isinstance(error, SandboxSessionUnavailableError):
            status_code = 409
        elif isinstance(error, SandboxProvisioningError):
            status_code = 502
        elif isinstance(error, SandboxCapacityError):
            status_code = 409
        return HTTPException(
            status_code=status_code,
            detail={
                "code": error.code,
                "message": str(error),
                "retryable": error.retryable,
            },
        )

    def _is_admin(request: Request) -> bool:
        return bool(admin_resolver and admin_resolver(request))

    def _public_session(
        session: SandboxCloudSession,
        owner_id: str | None = None,
    ) -> dict[str, object]:
        return {
            "sessionId": session.instance_id,
            "userSessionId": session.user_session_id,
            "status": session.status,
            "createdAt": session.created_at,
            "expireAt": session.expire_at,
            "toolType": session.tool_type,
            "createdBy": session.creator_name or session.created_by,
            "region": session.region,
            "isMine": bool(owner_id and session.created_by == owner_id),
            "displayName": session.display_name,
            "persistent": session.persistent,
        }

    async def _request_object(
        request: Request, *, maximum: int = 64 * 1024
    ) -> dict[str, object]:
        body = await request.body()
        if len(body) > maximum:
            raise SandboxValidationError("请求内容过大。")
        try:
            value = json.loads(body) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise SandboxValidationError("请求不是有效 JSON。") from error
        if not isinstance(value, dict):
            raise SandboxValidationError("请求必须是 JSON 对象。")
        return value

    @app.post("/web/sandbox/codex-project-handoff/pairings")
    async def _create_codex_project_handoff_pairing_route(
        request: Request,
    ) -> JSONResponse:
        owner_id = owner_resolver(request)
        creator_name = creator_resolver(request) if creator_resolver else owner_id
        try:
            data = await _request_object(request)
            ttl_seconds = _codex_project_handoff_pairing_ttl_seconds(
                data.get("ttlSeconds")
            )
            pairing_code, expire_at = _create_codex_project_handoff_pairing(
                owner_id,
                creator_name,
                ttl_seconds,
            )
        except SandboxError as error:
            raise _http_error(error) from error
        response = JSONResponse(
            {
                "pairingCode": pairing_code,
                "expireAt": _utc_timestamp(expire_at),
                "studioUrl": _studio_url_for_request(request),
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/web/sandbox/codex-project-handoff/pairings/{pairing_code}")
    async def _get_codex_project_handoff_pairing_route(
        pairing_code: str,
        request: Request,
    ) -> JSONResponse:
        owner_id = owner_resolver(request)
        try:
            pairing = _get_codex_project_handoff_pairing(pairing_code, owner_id)
            expire_at = pairing.get("exp")
            if not isinstance(expire_at, int):
                raise SandboxSessionNotFoundError("端云接力请求不存在或已过期。")
        except SandboxError as error:
            raise _http_error(error) from error
        payload = {
            "state": pairing["state"],
            "expireAt": _utc_timestamp(expire_at),
            **(
                {"projectName": pairing["projectName"]}
                if isinstance(pairing.get("projectName"), str)
                else {}
            ),
            **(
                {"agentName": pairing["agentName"]}
                if isinstance(pairing.get("agentName"), str)
                else {}
            ),
            **(
                {"sessionId": pairing["sessionId"]}
                if isinstance(pairing.get("sessionId"), str)
                else {}
            ),
            **(
                {"error": pairing["error"]}
                if isinstance(pairing.get("error"), str)
                else {}
            ),
            **(
                {"failedStage": pairing["failedStage"]}
                if isinstance(pairing.get("failedStage"), str)
                else {}
            ),
        }
        response = JSONResponse(payload)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/web/sandbox/codex-project-handoff/sessions")
    async def _create_codex_project_upload_session(
        request: Request,
    ) -> JSONResponse:
        try:
            data = await _request_object(request)
            project_name = _codex_project_upload_project_name(data.get("projectName"))
            display_name = _codex_project_handoff_agent_name(data.get("agentName"))
            handoff_id = _codex_project_handoff_id(data.get("handoffId"))
            if data.get("persistent", False) is not False:
                raise SandboxValidationError("云端接力只支持临时 Session。")
            remote_home = _codex_project_upload_remote_home(data.get("remoteHome"))
            remote_repo_dir = posixpath.join(
                remote_home,
                _codex_project_upload_directory_name(project_name),
            )
            pairing_key = _normalize_codex_project_handoff_pairing(
                data.get("pairingCode")
            )
            _cleanup_codex_project_handoff_pairings(int(time.time()))
            pairing = _CODEX_PROJECT_HANDOFF_PAIRINGS.get(pairing_key)
            if pairing is None:
                raise SandboxPermissionError("Codex 云端接力配对码已使用或已过期。")
            pairing_state = pairing.get("state")
            previous_handoff_id = pairing.get("handoffId")
            if previous_handoff_id == handoff_id:
                if (
                    pairing.get("projectName") != project_name
                    or pairing.get("remoteRepoDir") != remote_repo_dir
                ):
                    raise SandboxValidationError(
                        "端云接力请求 ID 不能用于不同的请求参数。"
                    )
                previous_response = pairing.get("sessionResponse")
                reusable_states = {
                    "session-created",
                    "continuing",
                    "running",
                    "completed",
                }
                retryable_failed_stages = {
                    "uploading-project",
                    "restoring-project",
                }
                can_resume_failed_session = (
                    pairing_state == "failed"
                    and pairing.get("failedStage") in retryable_failed_stages
                )
                if isinstance(previous_response, dict) and (
                    pairing_state in reusable_states or can_resume_failed_session
                ):
                    if can_resume_failed_session:
                        pairing["state"] = "session-created"
                        pairing.pop("error", None)
                        pairing.pop("failedStage", None)
                        pairing["requestedAt"] = int(time.time())
                    response = JSONResponse(dict(previous_response))
                    response.headers["Cache-Control"] = "no-store"
                    return response
                if (
                    pairing_state == "failed"
                    and pairing.get("failedStage") == "creating-session"
                ):
                    detail = str(
                        pairing.get("error") or "云端 Session 创建失败。"
                    ).strip()
                    raise SandboxSessionUnavailableError(
                        f"{detail} 请刷新配对码后重试。"
                    )
                if pairing_state == "creating":
                    raise SandboxSessionUnavailableError(
                        "云端 Agent 正在创建，请稍后重试。"
                    )
            if pairing_state != "issued":
                raise SandboxPermissionError("Codex 云端接力配对码已使用或已过期。")
            pairing["state"] = "creating"
            pairing.pop("error", None)
            pairing.pop("failedStage", None)
            pairing.update(
                {
                    "projectName": project_name,
                    "agentName": display_name,
                    "handoffId": handoff_id,
                    "remoteRepoDir": remote_repo_dir,
                    "requestedAt": int(time.time()),
                }
            )
            owner_id = str(pairing["ownerId"])
            creator_name = pairing.get("creatorName")
            if not isinstance(creator_name, str) or not creator_name.strip():
                creator_name = owner_id
            try:
                session = await service.create(
                    owner_id,
                    display_name,
                    creator_name,
                    False,
                )
            except Exception as error:
                pairing.update(
                    {
                        "state": "failed",
                        "failedStage": "creating-session",
                        "error": _safe_error_message(error),
                    }
                )
                raise
            if not session.endpoint:
                pairing.update(
                    {
                        "state": "failed",
                        "failedStage": "creating-session",
                        "error": "AgentKit Session 已创建，但暂无可用 Endpoint。",
                    }
                )
                raise SandboxSessionUnavailableError(
                    "AgentKit Session 已创建，但暂无可用 Endpoint。"
                )
            try:
                conversation = await service.connect(session.instance_id, owner_id)
                session = conversation.cloud
            except Exception as error:
                pairing.update(
                    {
                        "state": "failed",
                        "failedStage": "creating-session",
                        "error": _safe_error_message(error),
                    }
                )
                raise
            pairing.update(
                {
                    "state": "session-created",
                    "sessionId": session.instance_id,
                    "remoteRepoDir": remote_repo_dir,
                    "sessionCreatedAt": int(time.time()),
                }
            )
        except SandboxError as error:
            raise _http_error(error) from error
        session_response = {
            "sessionId": session.instance_id,
            "displayName": session.display_name,
            "endpoint": session.endpoint,
            "remoteRepoDir": remote_repo_dir,
            "expireAt": session.expire_at,
        }
        pairing["sessionResponse"] = session_response
        response = JSONResponse(session_response)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/web/sandbox/codex-project-handoff/sessions/{session_id}/status")
    async def _update_codex_project_handoff_status(
        session_id: str,
        request: Request,
    ) -> JSONResponse:
        try:
            data = await _request_object(request)
            pairing_key = _normalize_codex_project_handoff_pairing(
                data.get("pairingCode")
            )
            handoff_id = _codex_project_handoff_id(data.get("handoffId"))
            failed_stage = data.get("failedStage")
            if failed_stage not in {"uploading-project", "restoring-project"}:
                raise SandboxValidationError("云端接力失败阶段无效。")
            error_message = data.get("error")
            if not isinstance(error_message, str) or not error_message.strip():
                raise SandboxValidationError("云端接力失败原因不能为空。")
            if len(error_message) > 20_000:
                raise SandboxValidationError("云端接力失败原因过长。")

            _cleanup_codex_project_handoff_pairings(int(time.time()))
            pairing = _CODEX_PROJECT_HANDOFF_PAIRINGS.get(pairing_key)
            if pairing is None:
                raise SandboxPermissionError("Codex 云端接力配对码已使用或已过期。")
            if (
                pairing.get("handoffId") != handoff_id
                or pairing.get("sessionId") != session_id
            ):
                raise SandboxPermissionError("配对码与云端接力 Session 不匹配。")
            if pairing.get("state") not in {"session-created", "failed"}:
                raise SandboxPermissionError("当前云端接力状态不能上报该失败。")
            safe_message = _redact_public_text(
                error_message.strip(),
                maximum=2_000,
            )
            pairing.update(
                {
                    "state": "failed",
                    "failedStage": failed_stage,
                    "error": safe_message or "端侧项目迁移失败。",
                    "failedAt": int(time.time()),
                }
            )
        except SandboxError as error:
            raise _http_error(error) from error
        response = JSONResponse({"state": "failed"})
        response.headers["Cache-Control"] = "no-store"
        return response

    def _launch_response(
        request: Request,
        session_id: str,
        token: str,
        value: dict[str, object],
    ) -> JSONResponse:
        response = JSONResponse(value)
        response.headers["Cache-Control"] = "no-store"
        common_path = proxy_prefix(session_id, "terminal").rsplit("/", 1)[0]
        forwarded_protocol = (
            request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        )
        response.set_cookie(
            proxy_cookie_name(session_id),
            token,
            max_age=STUDIO_SANDBOX_TTL_SECONDS,
            httponly=True,
            secure=(request.url.scheme == "https" or forwarded_protocol == "https"),
            samesite="strict",
            path=common_path,
        )
        return response

    @app.get("/web/sandbox/capabilities")
    async def _sandbox_capabilities(request: Request) -> dict[str, object]:
        owner_resolver(request)
        return service.capabilities()

    @app.get("/web/sandbox/sessions")
    async def _list_sandbox_sessions(request: Request) -> dict[str, object]:
        try:
            owner_id = owner_resolver(request)
            sessions, snapshots = await service.list_resources(
                owner_id,
                is_admin=_is_admin(request),
                auto_resume_snapshots=_request_auto_resume_snapshots(
                    request,
                    default=True,
                ),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        result: dict[str, object] = {
            "sessions": [_public_session(session, owner_id) for session in sessions]
        }
        if snapshots:
            result["snapshots"] = [
                _public_snapshot(snapshot, STUDIO_SANDBOX_TOOL_NAME, owner_id)
                for snapshot in snapshots
            ]
        return result

    @app.post("/web/sandbox/sessions")
    async def _start_sandbox_session(request: Request) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            body = await request.body()
            if body:
                try:
                    data = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError) as error:
                    raise SandboxValidationError(
                        "创建智能体的请求不是有效 JSON。"
                    ) from error
                if not isinstance(data, dict):
                    raise SandboxValidationError("创建智能体的请求格式无效。")
            else:
                data = {}
            session = await service.create(
                owner_id,
                data.get("displayName", ""),
                creator_resolver(request) if creator_resolver else owner_id,
                data.get("persistent", True),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return {
            **_public_session(session, owner_id),
            "toolName": STUDIO_SANDBOX_TOOL_NAME,
        }

    @app.post("/web/sandbox/snapshots/{snapshot_id}/resume")
    async def _resume_sandbox_snapshot(
        snapshot_id: str,
        request: Request,
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            session = await service.resume_snapshot(
                snapshot_id,
                owner_id,
                is_admin=_is_admin(request),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return {
            **_public_session(session, owner_id),
            "toolName": STUDIO_SANDBOX_TOOL_NAME,
        }

    @app.delete("/web/sandbox/snapshots/{snapshot_id}")
    async def _delete_sandbox_snapshot(
        snapshot_id: str,
        request: Request,
    ) -> dict[str, bool]:
        try:
            await service.delete_snapshot(
                snapshot_id,
                owner_resolver(request),
                is_admin=_is_admin(request),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return {"deleted": True}

    @app.post("/web/sandbox/sessions/{session_id}/connect")
    async def _connect_sandbox_session(
        session_id: str, request: Request
    ) -> dict[str, object]:
        try:
            session = await service.connect(
                session_id,
                owner_resolver(request),
                is_admin=_is_admin(request),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return {
            **_public_session(session.cloud),
            "toolName": STUDIO_SANDBOX_TOOL_NAME,
            **service.settings(session_id, session.owner_id),
        }

    @app.get("/web/sandbox/sessions/{session_id}/settings")
    async def _sandbox_settings(session_id: str, request: Request) -> dict[str, object]:
        try:
            return service.settings(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error

    @app.get("/web/sandbox/sessions/{session_id}/status")
    async def _sandbox_status(session_id: str, request: Request) -> dict[str, object]:
        try:
            return service.status(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error

    @app.get("/web/sandbox/sessions/{session_id}/endpoint")
    async def _export_sandbox_endpoint(
        session_id: str, request: Request
    ) -> dict[str, object]:
        try:
            return service.export_endpoint(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error

    @app.get("/web/sandbox/sessions/{session_id}/models")
    async def _list_sandbox_models(
        session_id: str, request: Request
    ) -> dict[str, object]:
        try:
            models = await service.list_models(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return {"models": [model.public_dict() for model in models]}

    @app.put("/web/sandbox/sessions/{session_id}/model")
    async def _set_sandbox_model(
        session_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            model = data.get("model")
            if not isinstance(model, str):
                raise SandboxValidationError("模型名称必须是文本。")
            applied = await service.set_model(session_id, owner_id, model)
        except SandboxError as error:
            raise _http_error(error) from error
        return {"model": applied}

    @app.get("/web/sandbox/sessions/{session_id}/skills")
    async def _list_sandbox_skills(
        session_id: str,
        request: Request,
        force_reload: bool = False,
    ) -> dict[str, object]:
        try:
            skills = await service.list_skills(
                session_id,
                owner_resolver(request),
                force_reload=force_reload,
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return {"skills": [skill.public_dict() for skill in skills]}

    @app.get("/web/sandbox/sessions/{session_id}/threads")
    async def _list_sandbox_threads(
        session_id: str,
        request: Request,
        cursor: str = "",
        search: str = "",
        archived: bool = False,
    ) -> dict[str, object]:
        if len(cursor) > 2_000 or len(search) > 500:
            raise _http_error(SandboxValidationError("Thread 查询参数过长。"))
        try:
            threads, next_cursor = await service.list_threads(
                session_id,
                owner_resolver(request),
                cursor=cursor,
                search_term=search,
                archived=archived,
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return {
            "threads": [thread.public_dict() for thread in threads],
            **({"nextCursor": next_cursor} if next_cursor else {}),
        }

    @app.post("/web/sandbox/sessions/{session_id}/threads/new")
    async def _new_sandbox_thread(
        session_id: str, request: Request
    ) -> dict[str, object]:
        try:
            return await service.new_thread(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error

    @app.get("/web/sandbox/sessions/{session_id}/threads/{thread_id}")
    async def _read_sandbox_thread(
        session_id: str, thread_id: str, request: Request
    ) -> dict[str, object]:
        try:
            if not thread_id.strip() or len(thread_id) > 2_000:
                raise SandboxValidationError("Thread ID 格式无效。")
            return await service.read_thread(
                session_id,
                owner_resolver(request),
                thread_id,
            )
        except SandboxError as error:
            raise _http_error(error) from error

    @app.post("/web/sandbox/sessions/{session_id}/threads/resume")
    async def _resume_sandbox_thread(
        session_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            thread_id = data.get("threadId")
            if not isinstance(thread_id, str):
                raise SandboxValidationError("Thread ID 必须是文本。")
            return await service.resume_thread(session_id, owner_id, thread_id)
        except SandboxError as error:
            raise _http_error(error) from error

    @app.post("/web/sandbox/sessions/{session_id}/threads/fork")
    async def _fork_sandbox_thread(
        session_id: str, request: Request
    ) -> dict[str, object]:
        try:
            return await service.fork_thread(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error

    @app.post("/web/sandbox/sessions/{session_id}/threads/archive")
    async def _archive_sandbox_thread(
        session_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            thread_id = data.get("threadId")
            if not isinstance(thread_id, str):
                raise SandboxValidationError("Thread ID 必须是文本。")
            return await service.archive_thread(session_id, owner_id, thread_id)
        except SandboxError as error:
            raise _http_error(error) from error

    @app.post("/web/sandbox/sessions/{session_id}/threads/delete")
    async def _delete_sandbox_thread(
        session_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            thread_id = data.get("threadId")
            if not isinstance(thread_id, str):
                raise SandboxValidationError("Thread ID 必须是文本。")
            return await service.delete_thread(session_id, owner_id, thread_id)
        except SandboxError as error:
            raise _http_error(error) from error

    @app.post("/web/sandbox/sessions/{session_id}/threads/compact")
    async def _compact_sandbox_thread(
        session_id: str, request: Request
    ) -> dict[str, object]:
        try:
            await service.compact_thread(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return {"started": True}

    @app.put("/web/sandbox/sessions/{session_id}/permissions")
    async def _update_sandbox_permissions(
        session_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            try:
                settings = permission_settings_from_payload(data)
            except (TypeError, ValueError) as error:
                raise SandboxValidationError(str(error)) from error
            applied = await service.update_permissions(session_id, owner_id, settings)
        except SandboxError as error:
            raise _http_error(error) from error
        return {"permissions": applied.public_dict()}

    @app.put("/web/sandbox/sessions/{session_id}/workspace")
    async def _update_sandbox_workspace(
        session_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            cwd = data.get("cwd")
            if not isinstance(cwd, str):
                raise SandboxValidationError("工作目录必须是文本。")
            applied = await service.update_workspace(session_id, owner_id, cwd)
        except SandboxError as error:
            raise _http_error(error) from error
        return {"cwd": applied, "workspaceLocked": False}

    @app.get("/web/sandbox/sessions/{session_id}/directories")
    async def _list_sandbox_directories(
        session_id: str, request: Request, path: str = "/"
    ) -> dict[str, object]:
        try:
            listing = await service.list_directories(
                session_id, owner_resolver(request), path
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return listing.public_dict()

    @app.post("/web/sandbox/sessions/{session_id}/approvals/{approval_id}")
    async def _resolve_sandbox_approval(
        session_id: str, approval_id: str, request: Request
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        try:
            data = await _request_object(request)
            try:
                decision = approval_decision_from_payload(data.get("decision"))
            except ValueError as error:
                raise SandboxValidationError(str(error)) from error
            service.resolve_approval(session_id, owner_id, approval_id, decision)
        except SandboxError as error:
            raise _http_error(error) from error
        return {"approvalId": approval_id, "decision": decision}

    @app.post("/web/sandbox/sessions/{session_id}/terminal")
    async def _launch_sandbox_terminal(
        session_id: str, request: Request
    ) -> JSONResponse:
        try:
            url, shell_session_id, token = await service.launch_terminal(
                session_id, owner_resolver(request)
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return _launch_response(
            request,
            session_id,
            token,
            {"url": url, "shellSessionId": shell_session_id},
        )

    @app.post("/web/sandbox/sessions/{session_id}/browser")
    async def _launch_sandbox_browser(
        session_id: str, request: Request
    ) -> JSONResponse:
        try:
            url, token = service.launch_browser(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return _launch_response(request, session_id, token, {"url": url})

    @app.post("/web/sandbox/sessions/{session_id}/files")
    async def _upload_sandbox_file(
        session_id: str,
        request: Request,
        file: Annotated[UploadFile, File()],
    ) -> dict[str, object]:
        owner_id = owner_resolver(request)
        content = bytearray()
        try:
            while chunk := await file.read(1024 * 1024):
                content.extend(chunk)
                if len(content) > SANDBOX_UPLOAD_MAX_BYTES:
                    limit_mb = SANDBOX_UPLOAD_MAX_BYTES // (1024 * 1024)
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件不能超过 {limit_mb} MB。",
                    )
            path = await service.upload_file(
                session_id,
                owner_id,
                file.filename or "attachment",
                file.content_type or "application/octet-stream",
                bytes(content),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        finally:
            await file.close()
        return {
            "id": path,
            "path": path,
            "name": path.rsplit("/", 1)[-1],
            "mimeType": file.content_type or "application/octet-stream",
            "sizeBytes": len(content),
        }

    async def _sandbox_message_stream(
        session_id: str,
        owner_id: str,
        prompt: str,
        skill_ids: tuple[str, ...] = (),
    ) -> AsyncIterator[str]:
        try:
            async for event in service.stream_message(
                session_id, owner_id, prompt, skill_ids
            ):
                if event.kind == "assistant_final":
                    continue
                if event.kind == "text":
                    payload = {"text": event.text}
                    yield f"event: delta\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    continue
                if event.approval is not None:
                    yield (
                        "event: approval\n"
                        f"data: {json.dumps(event.approval, ensure_ascii=False)}\n\n"
                    )
                    continue
                if event.approval_resolved_id:
                    payload = {"approvalId": event.approval_resolved_id}
                    yield (
                        "event: approval_resolved\n"
                        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    )
                    continue
                if event.kind == "usage" and event.usage is not None:
                    payload = {
                        "turnId": event.turn_id,
                        "usage": event.usage.public_dict(),
                        **(
                            {"threadTotal": event.thread_total.public_dict()}
                            if event.thread_total is not None
                            else {}
                        ),
                        **(
                            {"modelContextWindow": (event.model_context_window)}
                            if event.model_context_window is not None
                            else {}
                        ),
                    }
                    yield (
                        "event: usage\n"
                        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    )
                    continue
                payload = {
                    "id": event.item_id,
                    "kind": event.kind,
                    "status": event.status,
                    "text": event.text or None,
                    "name": event.name or None,
                    "args": event.arguments,
                    "response": event.response,
                }
                yield f"event: activity\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"
        except SandboxError as error:
            payload = {
                "code": error.code,
                "message": str(error),
                "retryable": error.retryable,
            }
            yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield 'event: done\ndata: {"reason": "failed"}\n\n'

    def _sandbox_message_response(
        session_id: str,
        owner_id: str,
        prompt: str,
        skill_ids: tuple[str, ...] = (),
    ) -> StreamingResponse:
        return StreamingResponse(
            _sandbox_message_stream(session_id, owner_id, prompt, skill_ids),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/web/sandbox/codex-project-handoff/sessions/{session_id}/messages")
    async def _continue_codex_project_handoff(
        session_id: str, request: Request
    ) -> StreamingResponse:
        try:
            data = await _request_object(request, maximum=12 * 1024 * 1024)
            prompt = data.get("message")
            if not isinstance(prompt, str) or not prompt.strip():
                raise SandboxValidationError("message must not be empty")
            if len(prompt) > _CODEX_PROJECT_HANDOFF_CONTINUATION_MAX_CHARACTERS:
                raise SandboxValidationError("message is too large")
            history = _codex_project_handoff_history(data.get("history"))
            _pairing_key, pairing = _claim_codex_project_handoff_pairing(
                data.get("pairingCode"),
                "session-created",
                "continuing",
            )
            if pairing.get("sessionId") != session_id:
                pairing.update(
                    {
                        "state": "failed",
                        "failedStage": "continuing-task",
                        "error": "配对码与云端接力 Session 不匹配。",
                    }
                )
                raise SandboxPermissionError("配对码与云端接力 Session 不匹配。")
            owner_id = str(pairing["ownerId"])
            remote_repo_dir = pairing.get("remoteRepoDir")
            if not isinstance(remote_repo_dir, str) or not remote_repo_dir:
                pairing.update(
                    {
                        "state": "failed",
                        "failedStage": "continuing-task",
                        "error": "云端接力缺少项目目录。",
                    }
                )
                raise SandboxValidationError("云端接力缺少项目目录。")
        except SandboxError as error:
            raise _http_error(error) from error

        continuation_events: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

        async def _run_continuation() -> None:
            continuation_error = ""
            saw_visible_reply = False
            reported_activity_ids: set[str] = set()
            try:
                events = service.stream_message(
                    session_id,
                    owner_id,
                    prompt.strip(),
                )
                first_event_task = asyncio.ensure_future(anext(events))
                completed, _ = await asyncio.wait(
                    (first_event_task,),
                    timeout=_CODEX_PROJECT_HANDOFF_FIRST_EVENT_TIMEOUT_SECONDS,
                )
                if not completed:
                    first_event_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await first_event_task
                    continuation_error = (
                        "云端模型连接异常，暂未收到响应。请刷新配对码后重试。"
                    )
                    event = None
                else:
                    try:
                        event = first_event_task.result()
                    except StopAsyncIteration:
                        event = None
                while event is not None:
                    approval_id = (
                        event.approval.get("id")
                        if isinstance(event.approval, dict)
                        else None
                    )
                    if isinstance(approval_id, str) and approval_id:
                        service.resolve_approval(
                            session_id,
                            owner_id,
                            approval_id,
                            "acceptForSession",
                        )
                        continuation_events.put_nowait(
                            ("progress", "云端 Codex 已自动批准继续执行")
                        )
                    elif event.kind == "text" and event.text:
                        if not saw_visible_reply:
                            continuation_events.put_nowait(
                                ("progress", "云端 Codex 正在生成回复")
                            )
                        saw_visible_reply = True
                    elif event.kind in {"thinking", "tool"}:
                        activity_id = event.item_id or f"{event.kind}:{event.name}"
                        if activity_id not in reported_activity_ids:
                            reported_activity_ids.add(activity_id)
                            activity = (
                                event.name
                                if event.kind == "tool" and event.name
                                else "云端 Codex 正在分析任务"
                            )
                            continuation_events.put_nowait(("progress", activity))
                    try:
                        event = await anext(events)
                    except StopAsyncIteration:
                        event = None
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - background task boundary
                continuation_error = _safe_error_message(error)
            if not continuation_error and not saw_visible_reply:
                continuation_error = "云端 Codex 已结束，但没有生成可见回复，请重试。"
            if continuation_error:
                pairing.update(
                    {
                        "state": "failed",
                        "failedStage": "continuing-task",
                        "error": continuation_error,
                        "failedAt": int(time.time()),
                    }
                )
                continuation_events.put_nowait(("error", continuation_error))
            else:
                pairing.update(
                    {
                        "state": "completed",
                        "completedAt": int(time.time()),
                    }
                )
                continuation_events.put_nowait(("completed", None))

        async def _start_continuation_stream() -> AsyncIterator[str]:
            progress = {
                "stage": "connecting-session",
                "message": "正在连接云端 Session",
            }
            yield f"event: progress\ndata: {json.dumps(progress, ensure_ascii=False)}\n\n"
            try:
                await service.connect(session_id, owner_id)
                await service.update_workspace(session_id, owner_id, remote_repo_dir)
                await service.update_permissions(
                    session_id,
                    owner_id,
                    _CODEX_PROJECT_HANDOFF_PERMISSIONS,
                )
                if history:
                    progress = {
                        "stage": "importing-history",
                        "message": "正在迁移端侧会话历史",
                    }
                    yield (
                        "event: progress\ndata: "
                        + json.dumps(progress, ensure_ascii=False)
                        + "\n\n"
                    )
                    await service.inject_history(session_id, owner_id, history)
            except Exception as error:  # noqa: BLE001 - stream boundary
                message = _safe_error_message(error)
                pairing.update(
                    {
                        "state": "failed",
                        "failedStage": "continuing-task",
                        "error": message,
                    }
                )
                payload = {
                    "code": getattr(error, "code", "SANDBOX_ERROR"),
                    "message": message,
                    "retryable": getattr(error, "retryable", False),
                }
                yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                yield 'event: done\ndata: {"reason": "failed"}\n\n'
                return

            pairing.update(
                {
                    "state": "running",
                    "taskStartedAt": int(time.time()),
                }
            )
            continuation_task = asyncio.create_task(
                _run_continuation(),
                name=f"codex-project-handoff-{session_id}",
            )
            pairing["continuationTask"] = continuation_task

            def _release_continuation_task(task: asyncio.Task[None]) -> None:
                if pairing.get("continuationTask") is task:
                    pairing.pop("continuationTask", None)
                if task.cancelled():
                    return
                error = task.exception()
                if error is not None:
                    logger.warning(
                        "Codex project handoff task failed for %s: %s",
                        session_id,
                        _safe_error_message(error),
                    )

            continuation_task.add_done_callback(_release_continuation_task)
            accepted = {
                "stage": "task-started",
                "message": "云端 Codex 已接收任务，正在继续执行",
                "sessionId": session_id,
            }
            yield f"event: progress\ndata: {json.dumps(accepted, ensure_ascii=False)}\n\n"
            while True:
                try:
                    event_kind, event_value = await asyncio.wait_for(
                        continuation_events.get(),
                        timeout=_CODEX_PROJECT_HANDOFF_PROGRESS_HEARTBEAT_SECONDS,
                    )
                except TimeoutError:
                    heartbeat = {
                        "stage": "task-running",
                        "message": "云端任务仍在执行",
                        "sessionId": session_id,
                    }
                    yield (
                        "event: progress\ndata: "
                        + json.dumps(heartbeat, ensure_ascii=False)
                        + "\n\n"
                    )
                    continue
                if event_kind == "progress" and isinstance(event_value, str):
                    progress = {
                        "stage": "task-running",
                        "message": _redact_public_text(event_value, maximum=500),
                        "sessionId": session_id,
                    }
                    yield (
                        "event: progress\ndata: "
                        + json.dumps(progress, ensure_ascii=False)
                        + "\n\n"
                    )
                    continue
                if event_kind == "error" and isinstance(event_value, str):
                    payload = {
                        "code": "SANDBOX_INVOCATION_FAILED",
                        "message": event_value,
                        "retryable": False,
                    }
                    yield (
                        "event: error\ndata: "
                        + json.dumps(payload, ensure_ascii=False)
                        + "\n\n"
                    )
                    yield 'event: done\ndata: {"reason": "failed"}\n\n'
                    return
                completed = {
                    "stage": "task-completed",
                    "message": "云端任务已继续执行并生成回复",
                    "sessionId": session_id,
                }
                yield (
                    "event: progress\ndata: "
                    + json.dumps(completed, ensure_ascii=False)
                    + "\n\n"
                )
                yield 'event: done\ndata: {"reason": "completed"}\n\n'
                return

        return StreamingResponse(
            _start_continuation_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/web/sandbox/sessions/{session_id}/messages")
    async def _send_sandbox_message(
        session_id: str, request: Request
    ) -> StreamingResponse:
        try:
            data = await _request_object(request, maximum=128 * 1024)
            prompt = data.get("message")
            if not isinstance(prompt, str) or not prompt.strip():
                raise SandboxValidationError("message must not be empty")
            if len(prompt) > 100_000:
                raise SandboxValidationError("message is too large")
            raw_skill_ids = data.get("skillIds", [])
            if (
                not isinstance(raw_skill_ids, list)
                or len(raw_skill_ids) > 20
                or any(
                    not isinstance(skill_id, str) or not skill_id or len(skill_id) > 500
                    for skill_id in raw_skill_ids
                )
            ):
                raise SandboxValidationError("skillIds 格式无效。")
            skill_ids = tuple(dict.fromkeys(raw_skill_ids))
        except SandboxError as error:
            raise _http_error(error) from error
        owner_id = owner_resolver(request)
        try:
            service.require_owned(session_id, owner_id)
        except SandboxError as error:
            raise _http_error(error) from error
        return _sandbox_message_response(
            session_id, owner_id, prompt.strip(), skill_ids
        )

    @app.post("/web/sandbox/sessions/{session_id}/disconnect")
    async def _disconnect_sandbox_session(
        session_id: str, request: Request
    ) -> dict[str, bool]:
        try:
            await service.close(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return {"disconnected": True}

    @app.post("/web/sandbox/sessions/{session_id}/interrupt")
    async def _interrupt_sandbox_session(
        session_id: str, request: Request
    ) -> dict[str, bool]:
        try:
            await service.interrupt(session_id, owner_resolver(request))
        except SandboxError as error:
            raise _http_error(error) from error
        return {"interrupted": True}

    @app.delete("/web/sandbox/sessions/{session_id}")
    async def _delete_sandbox_session(
        session_id: str, request: Request
    ) -> dict[str, bool]:
        try:
            await service.delete(
                session_id,
                owner_resolver(request),
                is_admin=_is_admin(request),
            )
        except SandboxError as error:
            raise _http_error(error) from error
        return {"deleted": True}

    mount_sandbox_proxy_routes(
        app,
        proxy_target_resolver or service.resolve_proxy_target,
    )

    cleanup_task: asyncio.Task[None] | None = None

    async def _cleanup_loop() -> None:
        while True:
            await asyncio.sleep(60)
            await service.cleanup_expired()

    async def _start_cleanup() -> None:
        nonlocal cleanup_task
        cleanup_task = asyncio.create_task(_cleanup_loop())

    async def _stop_cleanup() -> None:
        if cleanup_task is not None:
            cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cleanup_task
        await service.close_all()

    app.router.on_startup.append(_start_cleanup)
    app.router.on_shutdown.append(_stop_cleanup)
