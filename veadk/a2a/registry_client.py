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

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import requests

from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.utils.auth import VE_TIP_TOKEN_HEADER

DEFAULT_ENDPOINT = "http://volcengineapi.byted.org/"
DEFAULT_VERSION = "2025-10-30"
IDENTITY_VERSION = "2025-10-30"
DEFAULT_SERVICE_NAME = "agentkit"
DEFAULT_REGION = "cn-beijing"
DEFAULT_TOP_K = 3
DEFAULT_TIMEOUT_MS = 60000
DEFAULT_POLL_INTERVAL_MS = 5000
SEARCH_PROMPT_MAX_BYTES = 2048
TERMINAL_STATES = {"completed", "failed", "canceled", "rejected"}
_OAUTH_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


class RegistryError(Exception):
    """A safe, structured error from the AgentKit A2A registry client."""

    def __init__(
        self, code: str, message: str, diagnostics: dict[str, Any] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.diagnostics = diagnostics or {}


@dataclass(frozen=True)
class AgentKitA2ARegistryConfig:
    space_id: str = ""
    endpoint: str = DEFAULT_ENDPOINT
    version: str = DEFAULT_VERSION
    service_name: str = DEFAULT_SERVICE_NAME
    region: str = DEFAULT_REGION
    top_k: int = DEFAULT_TOP_K
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS
    upstream_tip_token: str = ""


@dataclass(frozen=True)
class _RegistryCredentials:
    access_key: str
    secret_key: str
    session_token: str = ""


def registry_config_from_env() -> AgentKitA2ARegistryConfig:
    """Read AgentKit A2A registry config from Harness-compatible env vars."""

    return AgentKitA2ARegistryConfig(
        space_id=_first_env(
            ["REGISTRY_SPACE_ID", "AGENTKIT_A2A_SPACE_ID", "A2A_REGISTRY_SPACE_ID"]
        ),
        endpoint=_first_env(
            ["REGISTRY_ENDPOINT", "AGENTKIT_OPENAPI_ENDPOINT"], DEFAULT_ENDPOINT
        ),
        version=_first_env(
            ["REGISTRY_VERSION", "AGENTKIT_OPENAPI_VERSION"], DEFAULT_VERSION
        ),
        service_name=_first_env(
            ["REGISTRY_SERVICE_NAME", "AGENTKIT_SERVICE_NAME"], DEFAULT_SERVICE_NAME
        ),
        region=_first_env(["REGISTRY_REGION", "AGENTKIT_REGION"], DEFAULT_REGION),
        top_k=_int_env("REGISTRY_TOP_K", DEFAULT_TOP_K, minimum=1),
        timeout_ms=_int_env("REGISTRY_TIMEOUT_MS", DEFAULT_TIMEOUT_MS, minimum=1000),
        poll_interval_ms=_int_env(
            "REGISTRY_POLL_INTERVAL_MS", DEFAULT_POLL_INTERVAL_MS, minimum=100
        ),
        upstream_tip_token=_first_env(
            [
                "REGISTRY_UPSTREAM_TIP_TOKEN",
                "AGENTKIT_UPSTREAM_TIP_TOKEN",
                "A2A_REGISTRY_UPSTREAM_TIP_TOKEN",
                "VE_TIP_TOKEN",
                "X_VE_TIP_TOKEN",
                "TIP_TOKEN",
            ]
        ),
    )


def registry_tip_token_from_headers(headers: Mapping[str, str]) -> str:
    """Extract an inbound TIP token from HTTP headers."""

    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    return normalized.get(VE_TIP_TOKEN_HEADER.lower(), "").strip()


def search_agent_cards(
    prompt: str,
    top_k: int | None = None,
    config: AgentKitA2ARegistryConfig | None = None,
    *,
    strip_prompt: bool = True,
) -> dict[str, Any]:
    """Search AgentKit A2A registry by prompt and return sanitized AgentCards."""

    started = time.monotonic()
    config = _resolve_config(config)
    if not prompt or not prompt.strip():
        raise RegistryError("INVALID_ARGUMENT", "prompt is required")
    _require_space_id(config)

    safe_top_k = max(1, min(int(top_k or config.top_k or DEFAULT_TOP_K), 20))
    request_prompt = prompt.strip() if strip_prompt else prompt
    request_prompt = truncate_utf8_bytes(request_prompt, SEARCH_PROMPT_MAX_BYTES)
    response, request_duration_ms = _agentkit_post(
        config,
        "SearchAgentCards",
        {"SpaceId": config.space_id, "Prompt": request_prompt, "TopK": safe_top_k},
    )
    result = response.get("Result") or {}
    raw_cards = result.get("AgentCards") or []

    agents = []
    for index, raw_card in enumerate(raw_cards[:safe_top_k]):
        card = _parse_json_object(
            raw_card, "AGENT_CARD_PARSE_FAILED", f"AgentCards[{index}]"
        )
        agents.append(_sanitize_agent_card(card))

    duration_ms = int((time.monotonic() - started) * 1000)
    if not agents:
        raise RegistryError(
            "AGENT_NOT_FOUND",
            "SearchAgentCards did not return usable agents",
            {"duration_ms": duration_ms},
        )

    return _success(
        {
            "agents": agents,
            "total_count": result.get("TotalCount", len(agents)),
            "diagnostics": {
                "search_request_id": _request_id(response),
                "request_duration_ms": request_duration_ms,
                "duration_ms": duration_ms,
            },
        }
    )


def truncate_utf8_bytes(text: str, max_bytes: int = SEARCH_PROMPT_MAX_BYTES) -> str:
    """Return ``text`` truncated to at most ``max_bytes`` UTF-8 bytes."""

    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def create_task(
    agent_name: str,
    input_text: str,
    task_id: str | None = None,
    config: AgentKitA2ARegistryConfig | None = None,
) -> dict[str, Any]:
    """Create a remote A2A task by AgentKit A2A agent name."""

    started = time.monotonic()
    config = _resolve_config(config)
    if not agent_name or not agent_name.strip():
        raise RegistryError("INVALID_ARGUMENT", "agent_name is required")
    if not input_text or not input_text.strip():
        raise RegistryError("INVALID_ARGUMENT", "input is required")

    result, card, raw_response, get_duration_ms = _get_a2a_agent(
        agent_name.strip(), config
    )
    a2a_result = _send_message(card, input_text, config, task_id=task_id)
    return _task_or_message_success(
        a2a_result,
        _sanitize_get_agent_result(result, card),
        {
            "get_request_id": _request_id(raw_response),
            "get_duration_ms": get_duration_ms,
            "duration_ms": int((time.monotonic() - started) * 1000),
        },
    )


def poll_task(
    agent_name: str,
    task_id: str,
    history_length: int = 10,
    config: AgentKitA2ARegistryConfig | None = None,
) -> dict[str, Any]:
    """Poll a remote A2A task by AgentKit A2A agent name."""

    started = time.monotonic()
    config = _resolve_config(config)
    if not agent_name or not agent_name.strip():
        raise RegistryError("INVALID_ARGUMENT", "agent_name is required")
    if not task_id or not task_id.strip():
        raise RegistryError("INVALID_ARGUMENT", "task_id is required")

    _, card, _, _ = _get_a2a_agent(agent_name.strip(), config)
    return _poll_card(card, task_id, history_length, config, started)


def failure(
    code: str, message: str, diagnostics: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return a safe failure payload suitable for tool output."""

    return {
        "outcome": "failure",
        "error_code": code,
        "error_message": message,
        "diagnostics": diagnostics or {},
    }


def _resolve_config(
    config: AgentKitA2ARegistryConfig | None,
) -> AgentKitA2ARegistryConfig:
    env_config = registry_config_from_env()
    config = config or env_config
    return AgentKitA2ARegistryConfig(
        space_id=config.space_id or env_config.space_id,
        endpoint=config.endpoint or env_config.endpoint or DEFAULT_ENDPOINT,
        version=config.version or env_config.version or DEFAULT_VERSION,
        service_name=config.service_name
        or env_config.service_name
        or DEFAULT_SERVICE_NAME,
        region=config.region or env_config.region or DEFAULT_REGION,
        top_k=max(1, min(int(config.top_k or env_config.top_k or DEFAULT_TOP_K), 20)),
        timeout_ms=max(
            1000, int(config.timeout_ms or env_config.timeout_ms or DEFAULT_TIMEOUT_MS)
        ),
        poll_interval_ms=max(
            100,
            int(
                config.poll_interval_ms
                or env_config.poll_interval_ms
                or DEFAULT_POLL_INTERVAL_MS
            ),
        ),
        upstream_tip_token=(
            config.upstream_tip_token or env_config.upstream_tip_token
        ).strip(),
    )


def _require_space_id(config: AgentKitA2ARegistryConfig) -> None:
    if not config.space_id:
        raise RegistryError(
            "CONFIG_MISSING", "Missing required registry config: space_id"
        )


def _resolve_credentials() -> _RegistryCredentials:
    access_key = _first_env(
        [
            "AGENTKIT_ACCESS_KEY",
            "A2A_REGISTRY_ACCESS_KEY",
            "ACCESS_KEY",
            "VOLCENGINE_ACCESS_KEY",
        ]
    )
    secret_key = _first_env(
        [
            "AGENTKIT_SECRET_KEY",
            "A2A_REGISTRY_SECRET_KEY",
            "SECRET_KEY",
            "VOLCENGINE_SECRET_KEY",
        ]
    )
    session_token = _first_env(
        [
            "AGENTKIT_SESSION_TOKEN",
            "A2A_REGISTRY_SESSION_TOKEN",
            "VOLCENGINE_SESSION_TOKEN",
        ]
    )

    if not (access_key and secret_key):
        try:
            credential = get_credential_from_vefaas_iam()
            access_key = credential.access_key_id
            secret_key = credential.secret_access_key
            session_token = credential.session_token
        except Exception as exc:
            raise RegistryError(
                "CONFIG_MISSING",
                "Missing required registry credentials: access key and secret key",
                {"source": "env_or_iam", "reason": exc.__class__.__name__},
            ) from exc

    return _RegistryCredentials(
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
    )


def _first_env(names: list[str], default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _int_env(name: str, default: int, minimum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _success(payload: dict[str, Any]) -> dict[str, Any]:
    return {"outcome": "success", **payload}


def _timeout_seconds(config: AgentKitA2ARegistryConfig) -> float:
    return max(1, config.timeout_ms) / 1000


def _request_id(response: dict[str, Any]) -> str | None:
    return (response.get("ResponseMetadata") or {}).get("RequestId")


def _agentkit_post(
    config: AgentKitA2ARegistryConfig, action: str, body: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    return _signed_openapi_post(
        config=config,
        endpoint=config.endpoint,
        service_name=config.service_name,
        action=action,
        version=config.version,
        body=body,
    )


def _identity_post(
    config: AgentKitA2ARegistryConfig, action: str, body: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    return _signed_openapi_post(
        config=config,
        endpoint=_identity_endpoint(config),
        service_name="id",
        action=action,
        version=IDENTITY_VERSION,
        body=body,
    )


def _signed_openapi_post(
    *,
    config: AgentKitA2ARegistryConfig,
    endpoint: str,
    service_name: str,
    action: str,
    version: str,
    body: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    _require_space_id(config)
    credentials = _resolve_credentials()
    started = time.monotonic()
    body_str = json.dumps(body, ensure_ascii=False)
    body_bytes = body_str.encode("utf-8")
    parsed = urlparse(endpoint)
    path = parsed.path or "/"
    query = {"Action": action, "Version": version}
    headers_to_sign = {
        "Host": parsed.netloc,
        "Content-Type": "application/json",
    }
    auth_headers = _volc_sign_v4(
        access_key=credentials.access_key,
        secret_key=credentials.secret_key,
        service=service_name,
        region=config.region,
        method="POST",
        path=path,
        query=query,
        headers=headers_to_sign,
        body=body_str,
    )
    request_headers = {
        "Content-Type": "application/json",
        "Host": parsed.netloc,
        **auth_headers,
    }
    if credentials.session_token:
        request_headers["X-Security-Token"] = credentials.session_token

    response = None
    try:
        response = requests.post(
            endpoint,
            params=query,
            headers=request_headers,
            data=body_bytes,
            timeout=_timeout_seconds(config),
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise RegistryError(
            "AGENTKIT_OPENAPI_FAILED",
            f"Agent-A2A center request failed: {exc}",
            _agentkit_http_diagnostics(exc, response),
        ) from exc
    except ValueError as exc:
        raise RegistryError(
            "AGENTKIT_RESPONSE_PARSE_FAILED",
            "Agent-A2A center returned non-JSON response",
        ) from exc

    duration_ms = int((time.monotonic() - started) * 1000)
    if data.get("Error"):
        raise RegistryError(
            "AGENTKIT_OPENAPI_ERROR",
            "Agent-A2A center returned an error",
            {"response": data.get("Error")},
        )
    if "Result" not in data:
        raise RegistryError(
            "AGENTKIT_RESPONSE_INVALID", "Agent-A2A center response missing Result"
        )
    return data, duration_ms


def _identity_endpoint(config: AgentKitA2ARegistryConfig) -> str:
    explicit = _first_env(
        ["REGISTRY_ID_ENDPOINT", "AGENTKIT_ID_ENDPOINT", "ID_OPENAPI_ENDPOINT"]
    )
    if explicit:
        return explicit

    parsed = urlparse(config.endpoint)
    host = parsed.netloc
    if host.startswith("agentkit."):
        host = "id." + host.split(".", 1)[1]
        return urlunparse(parsed._replace(netloc=host))
    return config.endpoint


def _agentkit_http_diagnostics(
    exc: requests.RequestException,
    response: requests.Response | None,
) -> dict[str, Any]:
    response = getattr(exc, "response", None) or response
    if response is None:
        return {}

    diagnostics: dict[str, Any] = {"status_code": response.status_code}
    try:
        data = response.json()
    except ValueError:
        return diagnostics

    metadata = data.get("ResponseMetadata") if isinstance(data, dict) else None
    if not isinstance(metadata, dict):
        return diagnostics

    for source_key, target_key in [
        ("RequestId", "request_id"),
        ("Action", "action"),
        ("Version", "version"),
        ("Service", "service"),
        ("Region", "region"),
    ]:
        value = metadata.get(source_key)
        if value:
            diagnostics[target_key] = value

    error = metadata.get("Error")
    if isinstance(error, dict):
        diagnostics["response_error"] = {
            key: error[key] for key in ["Code", "CodeN", "Message"] if key in error
        }

    return diagnostics


def _get_a2a_agent(
    agent_name: str,
    config: AgentKitA2ARegistryConfig,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], int]:
    response, duration_ms = _agentkit_post(
        config,
        "GetA2aAgent",
        {"Name": agent_name, "SpaceId": config.space_id},
    )
    result = response.get("Result") or {}
    status = result.get("Status", "")
    if status and status != "running":
        raise RegistryError(
            "AGENT_NOT_RUNNING",
            f"Agent {agent_name} status is {status}",
            {"status": status},
        )

    card = _parse_json_object(
        result.get("AgentCard"), "AGENT_CARD_PARSE_FAILED", "Result.AgentCard"
    )
    if "url" in card:
        card["url"] = _clean_config_url(card.get("url", ""))
    if not card.get("url"):
        raise RegistryError(
            "AGENT_URL_MISSING", f"Agent {agent_name} AgentCard missing url"
        )
    return result, card, response, duration_ms


def _send_message(
    card: dict[str, Any],
    input_text: str,
    config: AgentKitA2ARegistryConfig,
    task_id: str | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "kind": "message",
        "messageId": str(uuid.uuid4()),
        "role": "user",
        "parts": [{"kind": "text", "text": input_text}],
    }
    if task_id:
        message["taskId"] = task_id

    try:
        return _a2a_jsonrpc(
            card["url"],
            "message/send",
            {"message": message, "configuration": {"blocking": False}},
            _agent_auth_headers(card, config),
            config,
        )
    except RegistryError as exc:
        if exc.code in {
            "A2A_HTTP_FAILED",
            "A2A_RESPONSE_PARSE_FAILED",
            "A2A_REMOTE_ERROR",
            "A2A_RESPONSE_INVALID",
        }:
            raise RegistryError(
                "A2A_TASK_CREATE_FAILED", exc.message, exc.diagnostics
            ) from exc
        raise


def _poll_card(
    card: dict[str, Any],
    task_id: str,
    history_length: int,
    config: AgentKitA2ARegistryConfig,
    started: float | None = None,
) -> dict[str, Any]:
    started = started or time.monotonic()
    a2a_result = _a2a_jsonrpc(
        card["url"],
        "tasks/get",
        {"id": task_id.strip(), "historyLength": max(0, int(history_length))},
        _agent_auth_headers(card, config),
        config,
    )
    state = _task_state(a2a_result)
    is_terminal = state in TERMINAL_STATES
    payload: dict[str, Any] = {
        "task": _task_summary(a2a_result),
        "is_terminal": is_terminal,
        "diagnostics": {"duration_ms": int((time.monotonic() - started) * 1000)},
    }
    response_text = _task_response_text(a2a_result)
    if response_text:
        payload["response"] = {"text": response_text}

    if not is_terminal:
        sleep_seconds = config.poll_interval_ms / 1000
        time.sleep(sleep_seconds)
        payload["diagnostics"]["sleep_seconds"] = sleep_seconds
        payload["diagnostics"]["next_action"] = (
            "call a2a_registry_task_poll again until task status is terminal"
        )

    return _success(payload)


def _task_or_message_success(
    a2a_result: dict[str, Any],
    selected_agent: dict[str, Any],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    if a2a_result.get("kind") == "message":
        return _success(
            {
                "selected_agent": selected_agent,
                "task": None,
                "response": {"text": _message_text(a2a_result)},
                "diagnostics": diagnostics,
            }
        )

    task = _task_summary(a2a_result)
    if not task["id"]:
        raise RegistryError(
            "A2A_TASK_CREATE_FAILED",
            "A2A task created but response has no task id",
            diagnostics,
        )

    return _success(
        {
            "selected_agent": selected_agent,
            "task": task,
            "diagnostics": diagnostics,
        }
    )


def _a2a_jsonrpc(
    url: str,
    method: str,
    params: dict[str, Any],
    headers: dict[str, str],
    config: AgentKitA2ARegistryConfig,
) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params,
    }
    request_headers = {"Content-Type": "application/json", **headers}
    response = None

    try:
        response = requests.post(
            url,
            headers=request_headers,
            json=payload,
            timeout=_timeout_seconds(config),
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise RegistryError(
            "A2A_HTTP_FAILED",
            f"A2A JSON-RPC request failed: {exc}",
            _http_response_diagnostics(exc, response),
        ) from exc
    except ValueError as exc:
        raise RegistryError(
            "A2A_RESPONSE_PARSE_FAILED", "A2A endpoint returned non-JSON response"
        ) from exc

    if data.get("error"):
        error = data["error"]
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RegistryError("A2A_REMOTE_ERROR", f"A2A JSON-RPC error: {message}")

    result = data.get("result")
    if not isinstance(result, dict):
        raise RegistryError(
            "A2A_RESPONSE_INVALID", "A2A JSON-RPC response missing object result"
        )
    return result


def _http_response_diagnostics(
    exc: requests.RequestException,
    response: requests.Response | None,
) -> dict[str, Any]:
    response = getattr(exc, "response", None) or response
    if response is None:
        return {}
    return {"status_code": response.status_code}


def _volc_sign_v4(
    access_key: str,
    secret_key: str,
    service: str,
    region: str,
    method: str,
    path: str,
    query: dict[str, str],
    headers: dict[str, str],
    body: str,
) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_short = now.strftime("%Y%m%d")

    canonical_query = "&".join(
        f"{_uri_encode(k)}={_uri_encode(v)}" for k, v in sorted(query.items())
    )
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    headers_to_sign = {**headers, "X-Content-Sha256": body_hash, "X-Date": x_date}
    signed_headers_keys: list[str] = []
    canonical_headers_parts: list[str] = []
    for key in sorted(headers_to_sign.keys(), key=str.lower):
        lower_key = key.lower()
        signed_headers_keys.append(lower_key)
        canonical_headers_parts.append(f"{lower_key}:{headers_to_sign[key].strip()}")

    canonical_headers = "\n".join(canonical_headers_parts) + "\n"
    signed_headers = ";".join(signed_headers_keys)
    canonical_request = "\n".join(
        [
            method.upper(),
            path or "/",
            canonical_query,
            canonical_headers,
            signed_headers,
            body_hash,
        ]
    )

    algorithm = "HMAC-SHA256"
    credential_scope = f"{date_short}/{region}/{service}/request"
    string_to_sign = "\n".join(
        [
            algorithm,
            x_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    k_date = _hmac_sha256(secret_key.encode("utf-8"), date_short.encode("utf-8"))
    k_region = _hmac_sha256(k_date, region.encode("utf-8"))
    k_service = _hmac_sha256(k_region, service.encode("utf-8"))
    signing_key = _hmac_sha256(k_service, b"request")
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    authorization = (
        f"{algorithm} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "X-Content-Sha256": body_hash,
        "X-Date": x_date,
        "Authorization": authorization,
    }


def _hmac_sha256(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def _uri_encode(value: str) -> str:
    return quote(value, safe="-_.~")


def _parse_json_object(raw: Any, code: str, label: str) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise RegistryError(code, f"{label} is not a JSON string")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RegistryError(code, f"Failed to parse {label}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RegistryError(code, f"{label} parsed value is not an object")
    return parsed


def _sanitize_skill(skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": skill.get("id", ""),
        "name": skill.get("name", ""),
        "description": skill.get("description", ""),
        "tags": skill.get("tags") or [],
    }


def _sanitize_agent_card(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": card.get("name", ""),
        "description": card.get("description", ""),
        "version": card.get("version") or card.get("latestPublishedVersion") or "",
        "protocol_version": card.get("protocolVersion", ""),
        "preferred_transport": card.get("preferredTransport", ""),
        "registration_type": card.get("registrationType", ""),
        "skills": [
            _sanitize_skill(skill)
            for skill in card.get("skills") or []
            if isinstance(skill, dict)
        ],
    }


def _sanitize_get_agent_result(
    result: dict[str, Any], card: dict[str, Any]
) -> dict[str, Any]:
    runtime_config = result.get("RuntimeConfig") or {}
    return {
        **_sanitize_agent_card(card),
        "id": result.get("Id", ""),
        "status": result.get("Status", ""),
        "source": result.get("Source", ""),
        "default_version": result.get("DefaultVersion", ""),
        "runtime_id": runtime_config.get("RuntimeId", ""),
        "network_type": runtime_config.get("NetworkType", ""),
    }


def _agent_auth_headers(
    card: dict[str, Any], config: AgentKitA2ARegistryConfig | None = None
) -> dict[str, str]:
    resolved_config = _resolve_config(config)
    security = card.get("security") or []
    schemes = card.get("securitySchemes") or {}
    headers: dict[str, str] = {}

    for requirement in security:
        if not isinstance(requirement, dict):
            continue
        for scheme_name, credentials in requirement.items():
            scheme = schemes.get(scheme_name) or {}
            scheme_type = str(scheme.get("type") or "").lower()
            if scheme_type == "apikey" and scheme.get("in") == "header":
                header_name = scheme.get("name") or "Authorization"
                token = (
                    credentials[0]
                    if isinstance(credentials, list) and credentials
                    else credentials
                )
                if isinstance(token, str) and token:
                    headers[header_name] = token
            elif scheme_type == "oauth2":
                headers["Authorization"] = "Bearer " + _oauth2_client_credentials_token(
                    scheme, resolved_config
                )

    tip_token = resolved_config.upstream_tip_token
    if tip_token:
        headers[VE_TIP_TOKEN_HEADER] = tip_token

    if security and not headers:
        raise RegistryError(
            "AGENT_AUTH_MISSING",
            "AgentCard has security config but no usable header credential",
        )
    return headers


def _oauth2_client_credentials_token(
    scheme: dict[str, Any], config: AgentKitA2ARegistryConfig
) -> str:
    token_url = _oauth2_token_url(scheme)
    if not token_url:
        raise RegistryError(
            "AGENT_OAUTH_CONFIG_INVALID",
            "OAuth2 AgentCard missing clientCredentials tokenUrl",
        )

    cached = _OAUTH_TOKEN_CACHE.get(token_url)
    now = time.time()
    if cached and cached[1] > now:
        return cached[0]

    user_pool_id = _user_pool_id_from_token_url(token_url)
    if not user_pool_id:
        raise RegistryError(
            "AGENT_OAUTH_CONFIG_INVALID",
            "OAuth2 tokenUrl does not contain a Volcengine user pool id",
            {"token_url_host": urlparse(token_url).netloc},
        )

    clients_response, _ = _identity_post(
        config,
        "ListUserPoolClients",
        {
            "UserPoolUid": user_pool_id,
            "PageSize": 10,
            "PageNumber": 1,
            "Filter": {"ClientTypes": ["MACHINE_TO_MACHINE"]},
        },
    )
    clients_result = clients_response.get("Result") or {}
    clients = clients_result.get("Data") or clients_result.get("Items") or []
    if not clients:
        raise RegistryError(
            "AGENT_OAUTH_CLIENT_MISSING",
            "OAuth2 user pool has no MACHINE_TO_MACHINE client",
            {"user_pool_id": user_pool_id},
        )

    client_uid = str(clients[0].get("Uid") or clients[0].get("ClientUid") or "")
    if not client_uid:
        raise RegistryError(
            "AGENT_OAUTH_CLIENT_INVALID",
            "OAuth2 MACHINE_TO_MACHINE client response missing Uid",
        )

    client_response, _ = _identity_post(
        config,
        "GetUserPoolClient",
        {"UserPoolUid": user_pool_id, "ClientUid": client_uid},
    )
    client_result = client_response.get("Result") or {}
    client_secret = client_result.get("ClientSecret") or client_result.get("Secret")
    if not client_secret:
        raise RegistryError(
            "AGENT_OAUTH_CLIENT_INVALID",
            "OAuth2 MACHINE_TO_MACHINE client response missing ClientSecret",
        )

    token_response = _fetch_oauth_access_token(
        token_url, client_uid, str(client_secret), config
    )
    access_token = token_response.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RegistryError(
            "AGENT_OAUTH_TOKEN_INVALID",
            "OAuth2 token endpoint response missing access_token",
        )

    expires_in = token_response.get("expires_in", 3600)
    try:
        ttl = max(60, int(expires_in) - 60)
    except (TypeError, ValueError):
        ttl = 3540
    _OAUTH_TOKEN_CACHE[token_url] = (access_token, now + ttl)
    return access_token


def _oauth2_token_url(scheme: dict[str, Any]) -> str:
    flows = scheme.get("flows") or {}
    client_credentials = flows.get("clientCredentials") or flows.get(
        "client_credentials"
    )
    if not isinstance(client_credentials, dict):
        return ""
    return _clean_config_url(
        client_credentials.get("tokenUrl")
        or client_credentials.get("token_url")
        or client_credentials.get("refreshUrl")
        or client_credentials.get("refresh_url")
        or ""
    )


def _clean_config_url(value: Any) -> str:
    if value is None:
        return ""
    cleaned = str(value).strip()
    while cleaned and cleaned[0] in {"`", '"', "'"}:
        cleaned = cleaned[1:].strip()
    while cleaned and cleaned[-1] in {"`", '"', "'"}:
        cleaned = cleaned[:-1].strip()
    return cleaned


def _user_pool_id_from_token_url(token_url: str) -> str:
    host = urlparse(token_url).netloc
    match = re.match(r"userpool-([^.]+)\.userpool\.auth\.id\.", host)
    return match.group(1) if match else ""


def _fetch_oauth_access_token(
    token_url: str,
    client_id: str,
    client_secret: str,
    config: AgentKitA2ARegistryConfig,
) -> dict[str, Any]:
    credentials = f"{client_id}:{client_secret}".encode("utf-8")
    encoded_credentials = base64.b64encode(credentials).decode("ascii")
    response = None
    try:
        response = requests.post(
            token_url,
            headers={
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=_timeout_seconds(config),
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise RegistryError(
            "AGENT_OAUTH_TOKEN_FAILED",
            f"OAuth2 token request failed: {exc}",
            _http_response_diagnostics(exc, response),
        ) from exc
    except ValueError as exc:
        raise RegistryError(
            "AGENT_OAUTH_TOKEN_INVALID",
            "OAuth2 token endpoint returned non-JSON response",
        ) from exc

    if not isinstance(data, dict):
        raise RegistryError(
            "AGENT_OAUTH_TOKEN_INVALID",
            "OAuth2 token endpoint response is not an object",
        )
    return data


def _text_from_parts(parts: list[Any]) -> str:
    texts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        kind = part.get("kind") or part.get("type")
        if kind == "text":
            texts.append(part.get("text", ""))
        elif kind == "data":
            texts.append(json.dumps(part.get("data") or {}, ensure_ascii=False))
        elif kind == "file":
            file_obj = part.get("file") or {}
            texts.append(
                f"File: {file_obj['uri']}" if file_obj.get("uri") else "File attachment"
            )
    return "\n".join(text for text in texts if text)


def _message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        return _text_from_parts(message.get("parts") or [])
    return ""


def _task_state(task: dict[str, Any]) -> str:
    status = task.get("status") or {}
    if isinstance(status, dict):
        return status.get("state") or "unknown"
    if isinstance(status, str):
        return status
    return "unknown"


def _task_response_text(task: dict[str, Any]) -> str:
    artifacts = task.get("artifacts") or []
    artifact_texts = []
    for artifact in artifacts:
        if isinstance(artifact, dict):
            artifact_texts.append(_text_from_parts(artifact.get("parts") or []))
    artifact_text = "\n".join(text for text in artifact_texts if text)
    if artifact_text:
        return artifact_text

    status = task.get("status") or {}
    if isinstance(status, dict):
        return _message_text(status.get("message"))
    return ""


def _task_summary(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id", ""),
        "status": _task_state(task),
    }
