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

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.config import getenv
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


_SESSION_READY_TIMEOUT = 120.0
_SESSION_POLL_INTERVAL = 1.0
_SESSION_TERMINAL_STATUSES = frozenset({"failed", "terminating", "terminated"})
_SESSION_REUSABLE_STATUSES = frozenset({"starting", "ready"})
_SESSION_LIST_PAGE_SIZE = 100
_SESSION_USER_ID_MAX_LENGTH = 200
_SESSION_ROTATION_SUFFIX_LENGTH = 15
_SESSION_LOCK_STRIPE_COUNT = 64
_AGENTKIT_REQUEST_CONNECT_TIMEOUT = 10.0
_AGENTKIT_REQUEST_MIN_READ_TIMEOUT = 60.0
_AGENTKIT_REQUEST_TIMEOUT_BUFFER = 30.0

_session_locks = tuple(threading.Lock() for _ in range(_SESSION_LOCK_STRIPE_COUNT))


@dataclass(frozen=True)
class AgentKitSessionLease:
    """A resolved AgentKit Session and its session-scoped data-plane endpoints."""

    tool_id: str
    logical_user_session_id: str
    user_session_id: str
    session_id: str
    status: str
    endpoint: str
    internal_endpoint: str
    created_at: str
    expire_at: str

    def select_endpoint(self, *, prefer_internal_endpoint: bool = False) -> str:
        if prefer_internal_endpoint:
            return self.internal_endpoint or self.endpoint
        return self.endpoint or self.internal_endpoint

    def remaining_seconds(self, *, now: datetime | None = None) -> float | None:
        expires_at = _parse_agentkit_timestamp(self.expire_at)
        if expires_at is None:
            return None
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return (expires_at - current.astimezone(timezone.utc)).total_seconds()


def _agentkit_request_timeout(operation_timeout: int) -> tuple[float, float]:
    """Keep the synchronous request alive longer than the tool operation."""
    return (
        _AGENTKIT_REQUEST_CONNECT_TIMEOUT,
        max(
            _AGENTKIT_REQUEST_MIN_READ_TIMEOUT,
            float(operation_timeout) + _AGENTKIT_REQUEST_TIMEOUT_BUFFER,
        ),
    )


def _parse_agentkit_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        logger.warning("Invalid AgentKit Session timestamp: %s", value)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_agentkit_user_session_id(logical_user_session_id: str) -> str:
    """Return a contract-compliant, stable base for physical UserSessionIds."""
    if not logical_user_session_id:
        raise ValueError("tool_user_session_id must not be empty")
    normalized = re.sub(r"[^A-Za-z0-9_-]", "_", logical_user_session_id)
    digest = hashlib.sha256(logical_user_session_id.encode("utf-8")).hexdigest()[:12]
    if normalized != logical_user_session_id:
        normalized = f"{normalized}_{digest}"
    max_base_length = _SESSION_USER_ID_MAX_LENGTH - _SESSION_ROTATION_SUFFIX_LENGTH
    if len(normalized) > max_base_length:
        normalized = f"{normalized[: max_base_length - 13]}_{digest}"
    return normalized


def _session_lock(tool_id: str, logical_user_session_id: str) -> threading.Lock:
    digest = hashlib.sha256(
        f"{tool_id}\0{logical_user_session_id}".encode("utf-8")
    ).digest()
    index = int.from_bytes(digest[:4], "big") % _SESSION_LOCK_STRIPE_COUNT
    return _session_locks[index]


def _session_has_enough_time(
    session: object,
    *,
    min_remaining_seconds: float,
    now: datetime,
) -> bool:
    expires_at = _parse_agentkit_timestamp(getattr(session, "expire_at", None))
    if expires_at is None:
        return min_remaining_seconds <= 0
    return (expires_at - now).total_seconds() > min_remaining_seconds


def _session_is_reusable(
    session: object,
    *,
    physical_user_session_id_base: str,
    min_remaining_seconds: float,
    now: datetime,
) -> bool:
    user_session_id = getattr(session, "user_session_id", None)
    if not isinstance(user_session_id, str) or not (
        user_session_id == physical_user_session_id_base
        or user_session_id.startswith(f"{physical_user_session_id_base}_r_")
    ):
        return False
    status = (getattr(session, "status", None) or "").strip().lower()
    return status in _SESSION_REUSABLE_STATUSES and _session_has_enough_time(
        session,
        min_remaining_seconds=min_remaining_seconds,
        now=now,
    )


def _rotated_user_session_id(
    physical_user_session_id_base: str,
    sessions: list[object],
) -> str:
    existing_ids = sorted(
        str(getattr(session, "session_id", "") or "") for session in sessions
    )
    generation = hashlib.sha256("\n".join(existing_ids).encode("utf-8")).hexdigest()[
        :12
    ]
    suffix = f"_r_{generation}"
    return f"{physical_user_session_id_base[: _SESSION_USER_ID_MAX_LENGTH - len(suffix)]}{suffix}"


def resolve_agentkit_tool_id(*preferred_env_names: str) -> str:
    """Resolve the first configured AgentKit tool id with AGENTKIT_TOOL_ID fallback."""
    for env_name in [*preferred_env_names, "AGENTKIT_TOOL_ID"]:
        tool_id = os.getenv(env_name)
        if tool_id:
            return tool_id

    return getenv("AGENTKIT_TOOL_ID")


def get_agentkit_endpoint_config(
    host_env_name: str = "AGENTKIT_TOOL_HOST",
) -> tuple[str, str, str, str]:
    """Return service, region, host and scheme for AgentKit tool invocation."""
    service = getenv("AGENTKIT_TOOL_SERVICE_CODE", "agentkit")

    cloud_provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
    if cloud_provider == "byteplus":
        sld = "bytepluses"
        default_region = "ap-southeast-1"
    else:
        sld = "volces"
        default_region = "cn-beijing"

    region = getenv(
        "AGENTKIT_TOOL_REGION",
        (os.getenv("REGION") if cloud_provider != "byteplus" else None)
        or default_region,
    )
    host = getenv(host_env_name, service + "." + region + f".{sld}.com")
    scheme = getenv("AGENTKIT_TOOL_SCHEME", "https", allow_false_values=True).lower()
    if scheme not in {"http", "https"}:
        scheme = "https"

    return service, region, host, scheme


def get_agentkit_credentials(
    tool_state: Optional[dict[str, Any]] = None,
) -> tuple[str, str, dict[str, str]]:
    """Resolve AgentKit invocation credentials from tool state, env, or IAM."""
    ak = tool_state.get("VOLCENGINE_ACCESS_KEY") if tool_state else None
    sk = tool_state.get("VOLCENGINE_SECRET_KEY") if tool_state else None
    header: dict[str, str] = {}

    if not (ak and sk):
        logger.debug("Get AK/SK from tool context failed.")
        ak = os.getenv("VOLCENGINE_ACCESS_KEY")
        sk = os.getenv("VOLCENGINE_SECRET_KEY")
        if not (ak and sk):
            logger.debug(
                "Get AK/SK from environment variables failed. Try to use credential from Iam."
            )
            credential = get_credential_from_vefaas_iam()
            ak = credential.access_key_id
            sk = credential.secret_access_key
            header = {"X-Security-Token": credential.session_token}
        else:
            logger.debug("Successfully get AK/SK from environment variables.")
    else:
        logger.debug("Successfully get AK/SK from tool context.")

    return ak, sk, header


def get_agentkit_account_id(tool_state: Optional[dict[str, Any]] = None) -> str:
    """Get the current caller account id for remote skills sandbox setup."""
    cloud_provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
    if cloud_provider == "vestack":
        return ""

    _, region, _, _ = get_agentkit_endpoint_config()
    ak, sk, header = get_agentkit_credentials(tool_state)
    host = (
        "open.byteplusapi.com"
        if cloud_provider == "byteplus"
        else "sts.volcengineapi.com"
    )
    res = ve_request(
        request_body={},
        action="GetCallerIdentity",
        ak=ak,
        sk=sk,
        service="sts",
        version="2018-01-01",
        region=region,
        host=host,
        header=header,
    )
    return res["Result"]["AccountId"]


def invoke_agentkit_run_code(
    *,
    tool_id: str,
    tool_user_session_id: str,
    code: str,
    timeout: int,
    kernel_name: str,
    tool_state: Optional[dict[str, Any]] = None,
    ttl: Optional[int] = None,
) -> dict[str, Any]:
    """Invoke the AgentKit RunCode operation."""
    service, region, host, scheme = get_agentkit_endpoint_config()
    ak, sk, header = get_agentkit_credentials(tool_state)

    request_body: dict[str, Any] = {
        "ToolId": tool_id,
        "UserSessionId": tool_user_session_id,
        "OperationType": "RunCode",
        "OperationPayload": json.dumps(
            {
                "code": code,
                "timeout": timeout,
                "kernel_name": kernel_name,
            }
        ),
    }
    if ttl is not None:
        request_body["Ttl"] = ttl

    return ve_request(
        request_body=request_body,
        action="InvokeTool",
        ak=ak,
        sk=sk,
        service=service,
        version="2025-10-30",
        region=region,
        host=host,
        header=header,
        scheme=scheme,
        timeout=_agentkit_request_timeout(timeout),
    )


def invoke_agentkit_exec_bash(
    *,
    tool_id: str,
    tool_user_session_id: str,
    command: str,
    exec_dir: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    timeout: int = 30,
    hard_timeout: Optional[int] = None,
    max_output_length: Optional[int] = None,
    tool_state: Optional[dict[str, Any]] = None,
    ttl: Optional[int] = None,
) -> dict[str, Any]:
    """Invoke AgentKit's Bash execution operation through InvokeTool."""
    service, region, host, scheme = get_agentkit_endpoint_config()
    ak, sk, header = get_agentkit_credentials(tool_state)

    operation_payload: dict[str, Any] = {
        "command": command,
        "timeout": timeout,
    }
    if exec_dir is not None:
        operation_payload["exec_dir"] = exec_dir
    if env is not None:
        operation_payload["env"] = env
    if hard_timeout is not None:
        operation_payload["hard_timeout"] = hard_timeout
    if max_output_length is not None:
        operation_payload["max_output_length"] = max_output_length

    request_body: dict[str, Any] = {
        "ToolId": tool_id,
        "OperationType": "ExecBash",
        "UserSessionId": tool_user_session_id,
        "OperationPayload": json.dumps(operation_payload),
    }
    if ttl is not None:
        request_body["Ttl"] = ttl

    operation_timeout = max(timeout, hard_timeout or timeout)

    return ve_request(
        request_body=request_body,
        action="InvokeTool",
        ak=ak,
        sk=sk,
        service=service,
        version="2025-10-30",
        region=region,
        host=host,
        header=header,
        scheme=scheme,
        timeout=_agentkit_request_timeout(operation_timeout),
    )


def _get_or_create_agentkit_session(
    *,
    client,
    tool_id: str,
    tool_user_session_id: str,
    ttl: int,
    min_remaining_seconds: float = 0,
):
    """Return a reusable physical Session for a stable logical session key."""
    from agentkit.sdk.tools import types as tools_types

    physical_user_session_id_base = _safe_agentkit_user_session_id(tool_user_session_id)
    candidates = _list_agentkit_sessions(
        client=client,
        tool_id=tool_id,
        physical_user_session_id_base=physical_user_session_id_base,
    )
    now = datetime.now(timezone.utc)
    reusable = [
        info
        for info in candidates
        if _session_is_reusable(
            info,
            physical_user_session_id_base=physical_user_session_id_base,
            min_remaining_seconds=min_remaining_seconds,
            now=now,
        )
    ]
    if reusable:
        reusable.sort(
            key=lambda info: getattr(info, "created_at", "") or "", reverse=True
        )
        chosen = reusable[0]
        logger.debug(
            f"Reusing AgentKit session {getattr(chosen, 'session_id', None)} "
            f"for logical UserSessionId={tool_user_session_id}"
        )
        return chosen

    physical_user_session_id = (
        physical_user_session_id_base
        if not candidates
        else _rotated_user_session_id(
            physical_user_session_id_base,
            candidates,
        )
    )
    try:
        return client.create_session(
            tools_types.CreateSessionRequest(
                ToolId=tool_id,
                UserSessionId=physical_user_session_id,
                Ttl=ttl,
            )
        )
    except Exception:
        # CreateSession may have succeeded even if its response was lost. Recover
        # the physical Session before deciding whether the operation failed.
        refreshed = _list_agentkit_sessions(
            client=client,
            tool_id=tool_id,
            physical_user_session_id_base=physical_user_session_id_base,
        )
        recovered = [
            info
            for info in refreshed
            if getattr(info, "user_session_id", None) == physical_user_session_id
            and (getattr(info, "status", None) or "").strip().lower()
            in _SESSION_REUSABLE_STATUSES
        ]
        if recovered:
            recovered.sort(
                key=lambda info: getattr(info, "created_at", "") or "",
                reverse=True,
            )
            return recovered[0]
        raise


def _list_agentkit_sessions(
    *,
    client,
    tool_id: str,
    physical_user_session_id_base: str,
) -> list[object]:
    """List every physical Session associated with one logical key."""
    if not hasattr(client, "list_sessions"):
        # Compatibility for older clients and lightweight test doubles. Current
        # AgentKit SDK versions expose ListSessions and use the paginated path.
        return []

    from agentkit.sdk.tools import types as tools_types

    sessions: list[object] = []
    next_token: str | None = None
    seen_tokens: set[str] = set()
    while True:
        request_kwargs: dict[str, object] = {
            "ToolId": tool_id,
            "Filters": [
                tools_types.FiltersItemForListSessions(
                    NameContains="UserSessionId",
                    Values=[physical_user_session_id_base],
                )
            ],
            "MaxResults": _SESSION_LIST_PAGE_SIZE,
        }
        if next_token:
            request_kwargs["NextToken"] = next_token
        listing = client.list_sessions(
            tools_types.ListSessionsRequest(**request_kwargs)
        )
        for info in getattr(listing, "session_infos", None) or []:
            user_session_id = getattr(info, "user_session_id", None)
            if user_session_id == physical_user_session_id_base or (
                isinstance(user_session_id, str)
                and user_session_id.startswith(f"{physical_user_session_id_base}_r_")
            ):
                sessions.append(info)

        next_token = getattr(listing, "next_token", None) or None
        if not next_token:
            return sessions
        if next_token in seen_tokens:
            raise RuntimeError("AgentKit ListSessions returned a repeated NextToken")
        seen_tokens.add(next_token)


def _agentkit_session_lease(
    *,
    session: object,
    fallback_session: object | None,
    tool_id: str,
    logical_user_session_id: str,
) -> AgentKitSessionLease:
    def value(name: str) -> str:
        current = getattr(session, name, None)
        fallback = getattr(fallback_session, name, None) if fallback_session else None
        return str(current or fallback or "")

    return AgentKitSessionLease(
        tool_id=tool_id,
        logical_user_session_id=logical_user_session_id,
        user_session_id=value("user_session_id")
        or _safe_agentkit_user_session_id(logical_user_session_id),
        session_id=value("session_id"),
        status=value("status"),
        endpoint=value("endpoint"),
        internal_endpoint=value("internal_endpoint"),
        created_at=value("created_at"),
        expire_at=value("expire_at"),
    )


def ensure_agentkit_session_lease(
    *,
    tool_id: str,
    tool_user_session_id: str,
    tool_state: Optional[dict[str, Any]] = None,
    ttl: int = 1800,
    min_remaining_seconds: float = 0,
    wait_until_ready: bool = True,
    ready_timeout: float = _SESSION_READY_TIMEOUT,
    poll_interval: float = _SESSION_POLL_INTERVAL,
) -> AgentKitSessionLease:
    """Resolve a live Session lease for a stable logical UserSessionId."""
    from agentkit.sdk.tools import types as tools_types
    from agentkit.sdk.tools.client import AgentkitToolsClient

    if not 60 <= ttl <= 86400:
        raise ValueError("ttl must be between 60 and 86400 seconds")
    if min_remaining_seconds < 0:
        raise ValueError("min_remaining_seconds must be greater than or equal to 0")
    if min_remaining_seconds >= 86400:
        raise ValueError("min_remaining_seconds must be less than 86400 seconds")
    if ready_timeout < 0:
        raise ValueError("ready_timeout must be greater than or equal to 0")
    if poll_interval <= 0:
        raise ValueError("poll_interval must be greater than 0")

    required_ttl = max(ttl, int(min_remaining_seconds) + 1)
    _, region, _, _ = get_agentkit_endpoint_config()
    ak, sk, header = get_agentkit_credentials(tool_state)
    client = AgentkitToolsClient(
        access_key=ak,
        secret_key=sk,
        region=region,
        session_token=header.get("X-Security-Token", ""),
    )

    with _session_lock(tool_id, tool_user_session_id):
        session = _get_or_create_agentkit_session(
            client=client,
            tool_id=tool_id,
            tool_user_session_id=tool_user_session_id,
            ttl=required_ttl,
            min_remaining_seconds=min_remaining_seconds,
        )
        session_id = getattr(session, "session_id", None)
        if not session_id:
            raise RuntimeError("AgentKit CreateSession response is missing SessionId")

        if not wait_until_ready:
            lease = _agentkit_session_lease(
                session=session,
                fallback_session=None,
                tool_id=tool_id,
                logical_user_session_id=tool_user_session_id,
            )
            if lease.endpoint or lease.internal_endpoint:
                return lease

        deadline = time.monotonic() + ready_timeout
        last_status = "Unknown"
        while True:
            current_session = client.get_session(
                tools_types.GetSessionRequest(
                    ToolId=tool_id,
                    SessionId=session_id,
                )
            )
            status = (getattr(current_session, "status", None) or "").strip()
            last_status = status or "Unknown"
            logger.debug("AgentKit session %s status: %s", session_id, last_status)
            normalized_status = status.lower()
            if normalized_status == "ready":
                lease = _agentkit_session_lease(
                    session=current_session,
                    fallback_session=session,
                    tool_id=tool_id,
                    logical_user_session_id=tool_user_session_id,
                )
                if not lease.select_endpoint():
                    raise RuntimeError(
                        f"AgentKit session {session_id} is Ready but has no endpoint"
                    )
                if not _session_has_enough_time(
                    current_session,
                    min_remaining_seconds=min_remaining_seconds,
                    now=datetime.now(timezone.utc),
                ):
                    raise RuntimeError(
                        f"AgentKit session {session_id} became Ready without enough "
                        "remaining lifetime"
                    )
                return lease
            if normalized_status in _SESSION_TERMINAL_STATUSES:
                raise RuntimeError(
                    f"AgentKit session {session_id} entered terminal status {last_status}"
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for AgentKit session {session_id} to become "
                    f"Ready; last status: {last_status}"
                )
            time.sleep(min(poll_interval, remaining))


def ensure_agentkit_session_endpoint(
    *,
    tool_id: str,
    tool_user_session_id: str,
    tool_state: Optional[dict[str, Any]] = None,
    ttl: int = 1800,
    prefer_internal_endpoint: bool = False,
    wait_until_ready: bool = False,
    ready_timeout: float = _SESSION_READY_TIMEOUT,
    poll_interval: float = _SESSION_POLL_INTERVAL,
    min_remaining_seconds: float = 0,
) -> str:
    """Create or reuse an AgentKit tool session and return its endpoint."""
    lease = ensure_agentkit_session_lease(
        tool_id=tool_id,
        tool_user_session_id=tool_user_session_id,
        tool_state=tool_state,
        ttl=ttl,
        min_remaining_seconds=min_remaining_seconds,
        wait_until_ready=wait_until_ready,
        ready_timeout=ready_timeout,
        poll_interval=poll_interval,
    )
    return lease.select_endpoint(prefer_internal_endpoint=prefer_internal_endpoint)
