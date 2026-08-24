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

"""`veadk frontend` -- serve the A2UI web UI together with the agent API server.

This is a self-contained launcher built on Google ADK's supported
`get_fast_api_app`. In the default mode it serves both the agent API
(`/list-apps`, `/run_sse`, sessions, ...) and the built React UI from a single
process, so there is no cross-origin setup. In `--vite` mode it serves only the
API (with CORS allowing the Vite dev server) for React hot reload. `--dev` is a
separate toggle: it sources the agent picker from local agents instead of cloud
runtimes (the UI is still served).
"""

import asyncio
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
import zipfile
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

import click
from pydantic import BaseModel, Field

from veadk.cli.agentkit_sandbox_region import is_agentkit_resource_not_found
from veadk.cli.frontend_branding import normalize_site_title, resolve_site_logo
from veadk.cli.managed_sidecar_source import (
    ManagedSidecarSourceError,
    stage_managed_sidecar_veadk_source,
)
from veadk.cli.studio_model_catalog import (
    is_byteplus_model,
    is_provider_modelark_base_url,
    modelark_base_url,
    provider_allows_model,
    studio_agent_model_name,
)
from veadk.cli.studio_telemetry import studio_telemetry_config
from veadk.utils.cloud_provider import (
    DEFAULT_BYTEPLUS_REGION,
    DEFAULT_BYTEPLUS_VIKING_MEMORY_HOST,
    DEFAULT_BYTEPLUS_VIKING_MEMORY_REGION,
    DEFAULT_CLOUD_PROVIDER,
    CloudProvider,
    agentkit_openapi_base,
    default_region,
    default_vefaas_application_template_id,
    normalize_cloud_provider,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_BYTEPLUS_VEFAAS_APPLICATION_NAME_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$"
)
_CLOUD_ACCOUNT_ID_RE = re.compile(r"[0-9]+")
_IAM_ACCOUNT_ID_RE = re.compile(r"\biam::(?P<account_id>[0-9]+):")
_BUILD_ERROR_MARKERS = (
    "no solution found",
    "unsatisfiable",
    "failed to solve",
    "did not complete successfully",
    "exit code:",
    "error:",
    "no matching distribution",
    "modulenotfounderror",
    "command not found",
    "permission denied",
    "traceback (most recent call last)",
)
_SENSITIVE_LOG_PATTERNS = (
    re.compile(r"authorization\s*[:=]", re.IGNORECASE),
    re.compile(r"\bbearer\s+\S+", re.IGNORECASE),
    re.compile(
        r'"?(?:accessKeyId|secretAccessKey|apiKey|clientSecret|privateKey|'
        r"accessToken|sessionToken|securityToken|refreshToken|idToken|jwtToken|"
        r'crToken|password|credential|signature|signingKey)"?\s*[:=]',
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:access[_ -]?key(?:[_ -]?id)?|secret[_ -]?key|api[_ -]?key|"
        r"client[_ -]?secret|private[_ -]?key|(?:access|session|security|refresh|"
        r"id|jwt|cr)[_ -]?token|password|credential|signature|"
        r"signing[_ -]?key)"
        r"\s*(?:=|:|\s)\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\." r"[A-Za-z0-9_-]{10,}\b"
    ),
)
_CP_BUILD_LOG_MAX_CHARS = 50000
_CP_BUILD_LOG_MAX_LINES = 1000
_CP_BUILD_LOG_FINAL_ERROR_RETRIES = 5
_CP_BUILD_LOG_FINAL_ERROR_RETRY_INTERVAL_SECONDS = 2.0
_CP_BUILD_LOG_ERROR_TAIL_CHECK_CHARS = 1024
_DEPLOY_PHASE_ORDER = {"build": 0, "deploy": 1, "publish": 2, "update": 3}
_DEPLOY_PHASE_MARKERS = (
    "step 2/2",
    "deploy failed",
    "deploying service",
    "creating runtime",
    "create runtime",
    "waiting for runtime",
    "runtime status is error",
    "runtime status: error",
    "initialization failed",
    "runtime_not_ready",
)
_PUBLISH_PHASE_MARKERS = (
    "launch successful",
    "service endpoint:",
    "runtime status: ready",
    "endpoint: http",
)
_SANDBOX_TOOL_CREATE_STAGGER_SECONDS = 0.5
_CP_PIPELINE_CREATED_RE = re.compile(
    r"Pipeline created successfully:\s*(?P<name>.*?)\s*\(ID:\s*(?P<id>[^)]+)\)"
)
_CP_PIPELINE_REUSED_RE = re.compile(r"Reusing pipeline by name:\s*(?P<name>.+)$")
_CP_PIPELINE_CREATING_RE = re.compile(r"Creating new pipeline:\s*(?P<name>.+)$")
_CP_PIPELINE_RUN_RE = re.compile(
    r"Pipeline triggered successfully,\s*run ID:\s*(?P<id>\S+)"
)
_CP_STRUCTURED_PIPELINE_RE = re.compile(
    r"triggering build\s*\(pipeline=(?P<id>[^)\s]+)\)",
    re.IGNORECASE,
)
_CP_STRUCTURED_RUN_RE = re.compile(
    r"\brun id\s+(?P<id>[^;\s]+);\s*waiting",
    re.IGNORECASE,
)
_RUNTIME_DESCRIPTION_MAX_BYTES = 255
_RUNTIME_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_RUNTIME_NAME_MIN_LENGTH = 4
_RUNTIME_NAME_MAX_LENGTH = 64
_STUDIO_STORAGE_ENV_KEYS = (
    "VEADK_STUDIO_TOS_BUCKET",
    "VEADK_STUDIO_TOS_REGION",
    "VEADK_VIDEO_ASSET_STORAGE",
    "VEADK_VIDEO_TOS_BUCKET",
    "VEADK_VIDEO_TOS_REGION",
    "VEADK_VIDEO_TOS_ENDPOINT",
    "VEADK_VIDEO_TOS_PREFIX",
    "VEADK_VIDEO_MAX_FILE_BYTES",
    "VEADK_MEDIA_STORAGE",
    "VEADK_MEDIA_TOS_PREFIX",
    "DATABASE_TOS_BUCKET",
    "DATABASE_TOS_REGION",
    "DATABASE_TOS_ENDPOINT",
)


def _adapt_migration_model_envs(
    runtime_envs: dict[str, str],
    provider: str,
) -> None:
    """Keep inherited migration model defaults on the Studio cloud provider."""
    current_base = runtime_envs.get("MODEL_AGENT_API_BASE", "").strip()
    other_provider = "volcengine" if provider == "byteplus" else "byteplus"
    base_is_missing = not current_base
    base_is_other_provider = bool(current_base) and is_provider_modelark_base_url(
        other_provider,
        current_base,
    )
    if base_is_missing or base_is_other_provider:
        runtime_envs["MODEL_AGENT_API_BASE"] = modelark_base_url(provider)
        runtime_envs["MODEL_AGENT_NAME"] = studio_agent_model_name(provider)
    elif not is_provider_modelark_base_url(provider, current_base):
        current_model = runtime_envs.get("MODEL_AGENT_NAME", "").strip()
        if current_model and not runtime_envs.get("MODEL_NAME", "").strip():
            runtime_envs["MODEL_NAME"] = current_model
        return

    else:
        current_model = runtime_envs.get("MODEL_AGENT_NAME", "").strip()
        model_is_other_provider = (
            is_byteplus_model(current_model)
            if provider == "volcengine"
            else not provider_allows_model(provider, current_model)
        )
        if not current_model or model_is_other_provider:
            runtime_envs["MODEL_AGENT_NAME"] = studio_agent_model_name(provider)

    selected_model = runtime_envs["MODEL_AGENT_NAME"]
    legacy_model = runtime_envs.get("MODEL_NAME", "").strip()
    legacy_is_other_provider = (
        is_byteplus_model(legacy_model)
        if provider == "volcengine"
        else not provider_allows_model(provider, legacy_model)
    )
    if not legacy_model or legacy_is_other_provider:
        runtime_envs["MODEL_NAME"] = selected_model


def _prepare_managed_sidecar_runtime_envs(
    runtime_envs: dict[str, str],
    provider: str,
    sidecar_plan: Mapping[str, Any] | None,
) -> str | None:
    """Normalize and validate env required by a managed Sidecar revision."""

    _adapt_migration_model_envs(runtime_envs, provider)
    if any(
        not runtime_envs.get(key, "").strip()
        for key in (
            "MODEL_AGENT_API_BASE",
            "MODEL_AGENT_API_KEY",
            "MODEL_AGENT_NAME",
        )
    ):
        return (
            "Harness Sidecar 需要完整的模型地址、API Key 和模型名称，"
            "请返回模型配置后重新发布。"
        )
    runtime_envs.setdefault("MODEL_NAME", runtime_envs["MODEL_AGENT_NAME"])
    effective_components = set(
        sidecar_plan.get("effectiveComponents") or []
        if isinstance(sidecar_plan, Mapping)
        else []
    )
    if effective_components & {"mcp_resilience", "sql_readonly"} and any(
        not runtime_envs.get(key, "").strip() for key in ("MCP_URLS", "MCP_API_KEY")
    ):
        return "已选择 MCP 稳定性治理，请在发布配置中填写 MCP_URLS 和 MCP_API_KEY。"
    return None


def _studio_storage_environment(
    source: Mapping[str, str | None],
) -> dict[str, str]:
    """Return only the non-secret Studio storage settings safe for VeFaaS."""
    return {
        key: str(source[key]) for key in _STUDIO_STORAGE_ENV_KEYS if source.get(key)
    }


def _byteplus_vefaas_application_name_suggestion(name: str) -> str:
    suggestion = re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")
    suggestion = re.sub(r"-{2,}", "-", suggestion)
    if not suggestion:
        return "studio"
    if len(suggestion) > 64:
        suggestion = suggestion[:64].strip("-")
    return suggestion or "studio"


def _validate_byteplus_vefaas_application_name(name: str) -> None:
    if _BYTEPLUS_VEFAAS_APPLICATION_NAME_RE.fullmatch(name):
        return
    suggestion = _byteplus_vefaas_application_name_suggestion(name)
    raise click.ClickException(
        "BytePlus VeFaaS application name must start and end with a lowercase "
        "letter or digit, contain only lowercase letters, digits, and hyphens, "
        "and be 1-64 characters long. "
        f"Got {name!r}. Suggested value: {suggestion!r}."
    )


def _validate_distinct_sandbox_tool_ids(tool_ids: Mapping[str, object]) -> None:
    """Reject one Tool id serving both transient and snapshot sessions."""
    labels = {
        "codex": "Codex",
        "openclaw": "OpenClaw",
        "hermes": "Hermes",
    }
    for kind, label in labels.items():
        transient = str(tool_ids.get(kind) or "").strip()
        snapshot = str(tool_ids.get(f"{kind}_snapshot") or "").strip()
        if transient and transient == snapshot:
            raise click.ClickException(
                f"AgentKit {label} Tool and {label} Snapshot Tool must use "
                "different Tool IDs."
            )


def _runtime_regions(provider: str, requested_region: str) -> list[str]:
    """Resolve the Runtime control-plane regions for a list request."""
    if requested_region not in {"all", "", "*"}:
        return [requested_region]
    if provider == "byteplus":
        return [os.getenv("BYTEPLUS_REGION") or DEFAULT_BYTEPLUS_REGION]
    return ["cn-beijing", "cn-shanghai"]


def _vikingdb_openapi_host(provider: str) -> str:
    """Return the Vector Database Cloud OpenAPI host."""
    return (
        "open.byteplusapi.com" if provider == "byteplus" else "open.volcengineapi.com"
    )


def _candidate_vikingdb_projects(project: str | None) -> list[str | None]:
    """Return likely Vector Database projects to list when Studio has no picker."""
    explicit = (project or "").strip()
    if explicit:
        return [explicit]
    candidates: list[str | None] = [
        os.getenv("DATABASE_VIKING_PROJECT"),
        os.getenv("VEADK_STUDIO_PROJECT"),
        "default",
        None,
    ]
    result: list[str | None] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = (candidate or "").strip()
        key = normalized or "<account-default>"
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized or None)
    return result


def _candidate_viking_memory_projects(project: str | None) -> list[str]:
    """Return likely VikingDB Memory projects to list when Studio has no picker."""
    explicit = (project or "").strip()
    if explicit:
        return [explicit]
    candidates = [
        os.getenv("DATABASE_VIKINGMEM_PROJECT"),
        os.getenv("VEADK_STUDIO_PROJECT"),
        "default",
    ]
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = (candidate or "").strip() or "default"
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _normalize_runtime_description(value: object) -> str:
    """Return a conservative AgentKit Runtime description."""
    single_line = re.sub(
        r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))
    ).strip()
    normalized: list[str] = []
    byte_length = 0
    for character in single_line:
        category = unicodedata.category(character)
        if category[0] not in {"L", "M", "N", "P"} and category != "Zs":
            continue
        character_bytes = len(character.encode("utf-8"))
        if byte_length + character_bytes > _RUNTIME_DESCRIPTION_MAX_BYTES:
            break
        normalized.append(character)
        byte_length += character_bytes
    return re.sub(r" +", " ", "".join(normalized)).rstrip()


def _cloud_account_id_from_value(value: object) -> str:
    normalized = str(value or "").strip()
    return normalized if _CLOUD_ACCOUNT_ID_RE.fullmatch(normalized) else ""


def _studio_account_id_from_remote_function(function: object) -> str:
    for attribute in ("owner", "Owner"):
        account_id = _cloud_account_id_from_value(getattr(function, attribute, ""))
        if account_id:
            return account_id
    for attribute in ("role", "Role"):
        role = str(getattr(function, attribute, "") or "")
        match = _IAM_ACCOUNT_ID_RE.search(role)
        if match:
            return match.group("account_id")
    return ""


def _is_malformed_runtime_description_error(error: object) -> bool:
    return "invaliddescription.malformed" in str(error or "").lower()


def _runtime_name_validation_error(name: str) -> str | None:
    if not name:
        return "Runtime 名称为必填项"
    if not _RUNTIME_NAME_RE.fullmatch(name):
        return "Runtime 名称只能包含英文字母、数字、下划线和连字符"
    if not _RUNTIME_NAME_MIN_LENGTH <= len(name) <= _RUNTIME_NAME_MAX_LENGTH:
        return "Runtime 名称长度须为 4-64 个字符"
    return None


def _runtime_deploy_error_detail(error: object, runtime_name: str) -> str:
    detail = str(error or "")
    if "invalidparameter.duplicatename" not in detail.lower():
        return detail
    return f"Runtime 名称“{runtime_name}”已存在，请修改名称后重新部署。"


def _create_runtime_with_description_fallback(
    create_runtime, client: object, request: Any
):
    try:
        return create_runtime(client, request)
    except Exception as create_error:
        if not _is_malformed_runtime_description_error(create_error):
            raise
        logger.warning("Runtime description was rejected; retrying without it")
        request.description = None
        return create_runtime(client, request)


def _extract_build_error_excerpt(
    lines: Iterable[object] | str, max_lines: int = 30
) -> str:
    """Return a credential-safe excerpt around high-signal build errors."""
    if max_lines <= 0:
        return ""
    raw_lines = lines.splitlines() if isinstance(lines, str) else lines
    clean_lines = []
    for raw_line in raw_lines:
        line = _ANSI_ESCAPE_RE.sub("", str(raw_line)).strip()
        if not line or any(pattern.search(line) for pattern in _SENSITIVE_LOG_PATTERNS):
            continue
        clean_lines.append(line[:1000])

    error_indexes = [
        index
        for index, line in enumerate(clean_lines)
        if any(marker in line.lower() for marker in _BUILD_ERROR_MARKERS)
    ]
    if not error_indexes:
        return ""

    selected_indexes = set()
    for index in error_indexes:
        selected_indexes.update(
            range(max(0, index - 3), min(len(clean_lines), index + 4))
        )
    return "\n".join(
        clean_lines[index] for index in sorted(selected_indexes)[:max_lines]
    )


def _build_log_tail_has_error_marker(
    text: object,
    *,
    tail_chars: int = _CP_BUILD_LOG_ERROR_TAIL_CHECK_CHARS,
) -> bool:
    """Return whether the retained log tail contains a known build error marker."""
    value = str(text or "").lower()
    if tail_chars > 0:
        value = value[-tail_chars:]
    return any(marker in value for marker in _BUILD_ERROR_MARKERS)


def _wait_for_cp_build_error_log_snapshot(
    read_snapshot: Callable[[], dict[str, Any]],
    *,
    attempts: int = _CP_BUILD_LOG_FINAL_ERROR_RETRIES,
    interval_seconds: float = _CP_BUILD_LOG_FINAL_ERROR_RETRY_INTERVAL_SECONDS,
    sleep_fn: Callable[[float], None] = sleep,
) -> dict[str, Any]:
    """Read CodePipeline logs until the retained tail includes an error marker."""
    max_attempts = max(1, attempts)
    snapshot: dict[str, Any] = {}
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            snapshot = read_snapshot()
            last_error = None
        except Exception as error:
            last_error = error
            if attempt >= max_attempts - 1 and not snapshot:
                raise
            if attempt < max_attempts - 1:
                sleep_fn(interval_seconds)
            continue
        if _build_log_tail_has_error_marker(snapshot.get("text", "")):
            return snapshot
        if attempt < max_attempts - 1:
            sleep_fn(interval_seconds)
    if last_error is not None and not snapshot:
        raise last_error
    return snapshot


def _advance_deploy_phase(current: str, message: object) -> str:
    """Advance the deployment phase from textual AgentKit progress or errors."""
    m = str(message or "").lower()
    if any(marker in m for marker in _PUBLISH_PHASE_MARKERS):
        candidate = "publish"
    elif any(marker in m for marker in _DEPLOY_PHASE_MARKERS):
        candidate = "deploy"
    elif "step 1/2" in m:
        candidate = "build"
    else:
        candidate = current
    return (
        candidate
        if _DEPLOY_PHASE_ORDER.get(candidate, 0) >= _DEPLOY_PHASE_ORDER.get(current, 0)
        else current
    )


def _sanitize_build_log_snapshot(
    text: object,
    *,
    max_chars: int = _CP_BUILD_LOG_MAX_CHARS,
    max_lines: int = _CP_BUILD_LOG_MAX_LINES,
) -> dict[str, Any]:
    """Return a redacted, bounded tail of build logs for browser display."""
    if max_chars <= 0 or max_lines <= 0:
        return {"text": "", "lineCount": 0, "truncated": False}
    raw_text = str(text or "")
    raw_lines = raw_text.splitlines()
    clean_lines: list[str] = []
    skipped = 0
    for raw_line in raw_lines:
        line = _ANSI_ESCAPE_RE.sub("", str(raw_line)).rstrip()
        line = _redact_debug_text(line)
        if any(pattern.search(line) for pattern in _SENSITIVE_LOG_PATTERNS):
            skipped += 1
            continue
        clean_lines.append(line[:1200])

    selected = clean_lines[-max_lines:]
    body = "\n".join(selected)
    char_truncated = len(body) > max_chars
    if char_truncated:
        body = body[-max_chars:]
        first_newline = body.find("\n")
        if first_newline >= 0:
            body = body[first_newline + 1 :]
    truncated = (
        skipped > 0
        or len(clean_lines) > len(selected)
        or char_truncated
        or len(raw_lines) != len(clean_lines)
    )
    return {
        "text": body,
        "lineCount": len(clean_lines),
        "truncated": truncated,
    }


def _cp_metadata_from_reporter_message(message: object) -> dict[str, str]:
    """Extract Code Pipeline identifiers from AgentKit reporter messages."""
    text = _ANSI_ESCAPE_RE.sub("", str(message or "")).strip()
    if not text:
        return {}
    if match := _CP_PIPELINE_CREATED_RE.search(text):
        return {
            "pipeline_name": match.group("name").strip(),
            "pipeline_id": match.group("id").strip(),
        }
    if match := _CP_PIPELINE_REUSED_RE.search(text):
        return {"pipeline_name": match.group("name").strip()}
    if match := _CP_PIPELINE_CREATING_RE.search(text):
        return {"pipeline_name": match.group("name").strip()}
    if match := _CP_PIPELINE_RUN_RE.search(text):
        return {"pipeline_run_id": match.group("id").strip()}
    if match := _CP_STRUCTURED_PIPELINE_RE.search(text):
        return {"pipeline_id": match.group("id").strip()}
    if match := _CP_STRUCTURED_RUN_RE.search(text):
        return {"pipeline_run_id": match.group("id").strip()}
    return {}


def _redact_debug_text(text: str) -> str:
    """Redact credentials before debug details leave the server process."""
    redacted = text
    for key, value in os.environ.items():
        upper = key.upper()
        if (
            value
            and len(value) >= 8
            and any(s in upper for s in ("KEY", "SECRET", "TOKEN", "PASSWORD"))
        ):
            redacted = redacted.replace(value, "***")
    redacted = re.sub(
        r"(?i)(\bbearer\s+)[a-z0-9._~+/=-]+",
        r"\1***",
        redacted,
    )
    return re.sub(
        r"(?i)((?:api[_-]?key|access[_-]?key(?:[_-]?id)?|secret[_-]?key|"
        r"auth[_-]?token|access[_-]?token|client[_-]?secret|credential|"
        r"signature|signing[_-]?key|secret|password|token)\s*[:=]\s*)"
        r"(?:[\"'][^\"']*[\"']|[^\s,;]+)",
        r"\1***",
        redacted,
    )


def _service_error_payload(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, Mapping) else None
    json_method = getattr(value, "json", None)
    if callable(json_method):
        try:
            parsed = json_method()
        except Exception:
            return None
        return parsed if isinstance(parsed, Mapping) else None
    return None


def _service_error_context(error: BaseException) -> tuple[str, dict[str, str]]:
    """Extract native cloud error fields without replacing its original message."""
    metadata: dict[str, str] = {}
    attribute_names = {
        "error_code": ("error_code", "code"),
        "status_code": ("status_code",),
        "request_id": ("request_id", "requestId", "requestid"),
    }
    for field, names in attribute_names.items():
        for name in names:
            value = getattr(error, name, None)
            if value is None or callable(value):
                continue
            text = str(getattr(value, "value", value)).strip()
            if text:
                metadata[field] = text
                break

    service_message = ""
    payloads = []
    for candidate in (
        getattr(error, "response", None),
        getattr(error, "body", None),
        getattr(error, "data", None),
    ):
        payload = _service_error_payload(candidate)
        if payload is not None:
            payloads.append(payload)
        if candidate is not None and "status_code" not in metadata:
            status_code = getattr(candidate, "status_code", None)
            if status_code is not None:
                metadata["status_code"] = str(status_code)
        headers = getattr(candidate, "headers", None)
        if isinstance(headers, Mapping) and "request_id" not in metadata:
            for key in ("x-request-id", "x-tt-logid", "x-response-id"):
                request_id = headers.get(key)
                if request_id:
                    metadata["request_id"] = str(request_id)
                    break

    for payload in payloads:
        response_metadata = payload.get("ResponseMetadata")
        if not isinstance(response_metadata, Mapping):
            response_metadata = payload.get("response_metadata")
        if isinstance(response_metadata, Mapping):
            request_id = response_metadata.get("RequestId") or response_metadata.get(
                "RequestID"
            )
            if request_id and "request_id" not in metadata:
                metadata["request_id"] = str(request_id)
            error_payload = response_metadata.get("Error")
        else:
            error_payload = payload.get("Error") or payload.get("error")
        if not isinstance(error_payload, Mapping):
            error_payload = payload

        code = error_payload.get("Code") or error_payload.get("code")
        if code and "error_code" not in metadata:
            metadata["error_code"] = str(code)
        message = error_payload.get("Message") or error_payload.get("message")
        if message and not service_message:
            service_message = str(message).strip()
        request_id = error_payload.get("RequestId") or error_payload.get("request_id")
        if request_id and "request_id" not in metadata:
            metadata["request_id"] = str(request_id)

    return service_message, metadata


def _safe_exception_detail(
    error: BaseException,
    *,
    secrets: Iterable[str | None] = (),
) -> str:
    """Return exception messages verbatim except for credential redaction."""
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = _ANSI_ESCAPE_RE.sub("", str(current)).strip()
        service_message, service_metadata = _service_error_context(current)
        if service_message and service_message not in message:
            message = f"{message}\nServer message: {service_message}".strip()
        if service_metadata:
            metadata_text = ", ".join(
                f"{key}={value}" for key, value in service_metadata.items()
            )
            message = f"{message}\nServer metadata: {metadata_text}".strip()
        for secret in secrets:
            if secret:
                message = message.replace(secret, "***")
        message = _redact_debug_text(message)
        if not message:
            message = type(current).__name__
        if message not in parts:
            parts.append(message)
        current = current.__cause__ or current.__context__
    return "\nCaused by:\n".join(parts)


def _new_studio_deploy_id() -> str:
    return f"stddep_{uuid4().hex}"


def _claims_from_forwarded_jwt(authorization: str | None) -> dict | None:
    """Decode the JWT an upstream API gateway forwarded in the Authorization
    header, WITHOUT re-verifying its signature.

    Used only in ``--auth-mode gateway``: the AgentKit runtime gateway has
    already authenticated the user and validated the token against the user
    pool before forwarding it, so this server trusts the payload for identity.
    Returns the claims dict, or None when there is no usable bearer JWT.
    """
    if not authorization:
        return None
    from veadk.utils.auth import strip_bearer_prefix

    token = strip_bearer_prefix(authorization)
    parts = token.split(".")
    if len(parts) != 3:
        return None
    import base64
    import json

    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except Exception:
        return None


DEV_SERVER_ORIGIN = "http://localhost:5173"
DEV_SERVER_LOOPBACK_ORIGIN = "http://127.0.0.1:5173"
DEV_SERVER_FALLBACK_ORIGIN = "http://localhost:5174"
DEV_SERVER_FALLBACK_LOOPBACK_ORIGIN = "http://127.0.0.1:5174"


def _frontend_allow_origins(vite: bool) -> list[str]:
    """Return browser origins accepted by the local Vite development server."""
    if not vite:
        return []
    return [
        DEV_SERVER_ORIGIN,
        DEV_SERVER_LOOPBACK_ORIGIN,
        DEV_SERVER_FALLBACK_ORIGIN,
        DEV_SERVER_FALLBACK_LOOPBACK_ORIGIN,
    ]


# Built UI shipped inside the package (output of `npm run build`).
PACKAGED_WEBUI = Path(__file__).resolve().parent.parent / "webui"


class _MessageFeedbackRequest(BaseModel):
    """One rating change for a persisted assistant Event."""

    runtime_id: str = Field(alias="runtimeId", min_length=1)
    region: str = Field(default="", min_length=0)
    app_name: str = Field(alias="appName", min_length=1)
    user_id: str = Field(alias="userId", min_length=1)
    session_id: str = Field(alias="sessionId", min_length=1)
    event_id: str = Field(alias="eventId", min_length=1)
    rating: Literal["good", "bad"] | None
    comment: str = Field(default="", max_length=2000)


class _DeleteFeedbackCasesRequest(BaseModel):
    """Feedback-derived evaluation cases to remove from AgentKit."""

    runtime_id: str = Field(alias="runtimeId", min_length=1)
    region: str = Field(default="", min_length=0)
    app_name: str = Field(alias="appName", min_length=1)
    item_ids: list[str] = Field(alias="itemIds", min_length=1, max_length=100)


def _mount_session_trace_route(app: Any, memory_exporter: Any) -> None:
    """Expose the session trace endpoint used by the VeADK frontend."""

    @app.get("/dev/apps/{app_name}/debug/trace/session/{session_id}")
    async def _get_session_trace(app_name: str, session_id: str) -> list[dict]:
        del app_name
        return [
            {
                "name": span.name,
                "span_id": span.context.span_id,
                "trace_id": span.context.trace_id,
                "start_time": span.start_time,
                "end_time": span.end_time,
                "attributes": dict(span.attributes),
                "parent_span_id": span.parent.span_id if span.parent else None,
            }
            for span in memory_exporter.get_finished_spans(session_id)
        ]


def _resolve_frontend_dir(arg: str | None) -> Path:
    """Resolve the built-UI directory.

    Priority: explicit ``--frontend-dir`` > packaged ``veadk/webui`` (works for
    pip-installed users) > ``./frontend/dist`` relative to cwd (dev fallback).
    """
    if arg:
        return Path(arg).resolve()
    if (PACKAGED_WEBUI / "index.html").is_file():
        return PACKAGED_WEBUI
    return (Path.cwd() / "frontend" / "dist").resolve()


def _open_browser_when_ready(
    url: str, host: str, port: int, timeout: float = 30.0
) -> None:
    """Open ``url`` in the default browser once the server responds to HTTP.

    Polls the Studio HTTP endpoint (up to ``timeout`` seconds) so the tab lands
    on a ready server rather than a connection error. Runs on a daemon thread;
    any failure is logged and ignored — a browser that will not open must never
    block the server from serving.
    """
    import time
    import urllib.error
    import urllib.request
    import webbrowser

    ready_urls = (f"http://{host}:{port}/web/ui-config", url)
    deadline = time.time() + timeout
    last_error = ""
    logger.info(
        "Waiting up to "
        f"{timeout:.0f}s for Studio HTTP readiness before opening {url} "
        f"(host={host}, port={port}, pid={os.getpid()})"
    )
    while time.time() < deadline:
        for ready_url in ready_urls:
            try:
                request = urllib.request.Request(ready_url, method="GET")
                with urllib.request.urlopen(request, timeout=1.0) as response:
                    status = getattr(response, "status", 200)
                    if 200 <= status < 500:
                        break
                    last_error = f"{ready_url} returned HTTP {status}"
            except urllib.error.HTTPError as error:
                if 200 <= error.code < 500:
                    break
                last_error = f"{ready_url} returned HTTP {error.code}"
            except (OSError, urllib.error.URLError) as error:
                last_error = f"{ready_url}: {error}"
        else:
            time.sleep(0.5)
            continue
        break
    else:
        logger.warning(
            "Server not ready in time; skipped opening the browser. "
            f"Open {url} manually. Last error: {last_error or 'unknown'}"
        )
        return
    try:
        if not webbrowser.open(url):
            logger.warning(
                f"Could not open the browser automatically. Open {url} manually."
            )
    except Exception as e:  # noqa: BLE001 - opening a browser is best-effort
        logger.warning(
            f"Could not open the browser automatically: {e}. Open {url} manually."
        )


# Built-in provider presets so users only need to supply client id/secret.
# Google is OIDC (endpoints come from discovery via OAUTH2_ISSUER); GitHub is
# not OIDC, so its endpoints are explicit and it needs Accept: application/json
# on the token request plus a non-"sub" id field.
_PROVIDER_PRESETS: dict[str, dict] = {
    "github": {
        "label": "GitHub",
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scope": "read:user user:email",
        "user_id_field": "login",
        "extra_token_headers": {"Accept": "application/json"},
    },
    "google": {
        "label": "Google",
        "issuer": "https://accounts.google.com",
        "scope": "openid email profile",
        "user_id_field": "sub",
    },
}

_PROVIDER_LABELS = {
    "veidentity": "火山引擎 Identity",
    "github": "GitHub",
    "google": "Google",
}


def _agentkit_authorization_header(api_key: str) -> str:
    """Normalize AgentKit credential input to an Authorization header value."""
    value = api_key.strip()
    if value.lower().startswith("bearer "):
        return value
    return f"Bearer {value}"


def _build_agentkit_proxy_headers(
    incoming_headers: dict[str, str],
    api_key: str | None,
    validated_authorization: str | None = None,
) -> dict[str, str]:
    """Return headers safe to forward from the local proxy to AgentKit.

    ``validated_authorization`` must only contain a credential already validated
    by the frontend OAuth middleware or its trusted upstream gateway.
    """
    excluded_headers = {
        # Host/proxy control.
        "host",
        "connection",
        "content-length",
        "x-agentkit-base",
        "x-agentkit-key",
        # Local VeADK/SSO credentials must not leak to the remote runtime.
        "authorization",
        "cookie",
        # Browser-only CORS/fetch metadata for the local origin.
        "origin",
        "referer",
        "sec-fetch-site",
        "sec-fetch-mode",
        "sec-fetch-dest",
        "sec-fetch-user",
    }
    headers = {
        key: value
        for key, value in incoming_headers.items()
        if key.lower() not in excluded_headers
    }
    if api_key and api_key.strip():
        headers["Authorization"] = _agentkit_authorization_header(api_key)
    elif validated_authorization and validated_authorization.strip():
        headers["Authorization"] = _agentkit_authorization_header(
            validated_authorization
        )
    return headers


def _build_generic_oauth2(provider_id: str, redirect_uri: str):
    """Build an OAuth2Config from env vars for a non-VeIdentity provider.

    Returns None when no generic provider is configured (no OAUTH2_CLIENT_ID).
    Endpoints come from a built-in preset, OAUTH2_ISSUER (OIDC discovery), or
    explicit OAUTH2_AUTHORIZE_URL / OAUTH2_TOKEN_URL / OAUTH2_USERINFO_URL.
    """
    client_id = os.getenv("OAUTH2_CLIENT_ID")
    if not client_id:
        return None

    from veadk.auth.middleware.oauth2_auth import OAuth2Config

    preset = _PROVIDER_PRESETS.get(provider_id, {})
    issuer = os.getenv("OAUTH2_ISSUER") or preset.get("issuer")
    authorize_url = os.getenv("OAUTH2_AUTHORIZE_URL") or preset.get("authorize_url")
    token_url = os.getenv("OAUTH2_TOKEN_URL") or preset.get("token_url")
    userinfo_url = os.getenv("OAUTH2_USERINFO_URL") or preset.get("userinfo_url")
    scope = os.getenv("OAUTH2_SCOPE") or preset.get("scope") or "openid profile email"

    # For an OIDC issuer, discover the endpoints we don't already have.
    if issuer and not (authorize_url and token_url):
        from veadk.auth.middleware.oauth2_auth import _fetch_oidc_discovery

        disc = _fetch_oidc_discovery(issuer.rstrip("/"))
        authorize_url = authorize_url or disc.authorization_endpoint
        token_url = token_url or disc.token_endpoint
        userinfo_url = userinfo_url or disc.userinfo_endpoint

    if not (authorize_url and token_url):
        raise click.ClickException(
            f"OAuth2 provider '{provider_id}': set OAUTH2_ISSUER (OIDC discovery) or "
            "OAUTH2_AUTHORIZE_URL + OAUTH2_TOKEN_URL (+ OAUTH2_USERINFO_URL)."
        )

    return OAuth2Config(
        authorize_url=authorize_url,
        token_url=token_url,
        userinfo_url=userinfo_url,
        client_id=client_id,
        client_secret=os.getenv("OAUTH2_CLIENT_SECRET"),
        scope=scope,
        redirect_uri=redirect_uri,
        issuer=issuer,
        user_id_field=preset.get("user_id_field", "sub"),
        extra_token_headers=preset.get("extra_token_headers", {}),
    )


def _serve_options(f):
    """Shared CLI options for the `frontend` and `studio` serve commands."""
    options = [
        click.option(
            "--agents-dir",
            default=".",
            show_default=True,
            help="Directory containing agent apps (like `adk web`): run from the "
            "parent folder of your agent directories — each subdir with an "
            "`agent.py` exposing a `root_agent` becomes a selectable app in the "
            "UI. Defaults to the current directory.",
        ),
        click.option(
            "--frontend-dir",
            default=None,
            help="Override the built React UI directory. Defaults to the UI shipped "
            "with the package (veadk/webui), falling back to ./frontend/dist.",
        ),
        click.option(
            "--site-logo",
            default=None,
            envvar="VEADK_SITE_LOGO",
            help="Studio logo as a local image path or HTTP(S) URL "
            "(env: VEADK_SITE_LOGO).",
        ),
        click.option(
            "--site-title",
            default=None,
            envvar="VEADK_SITE_TITLE",
            help="Studio title, at most 16 characters (env: VEADK_SITE_TITLE).",
        ),
        click.option("--host", default="127.0.0.1", show_default=True),
        click.option("--port", default=8000, show_default=True, type=int),
        click.option(
            "--provider",
            type=click.Choice(["volcengine", "byteplus"]),
            default="volcengine",
            show_default=True,
            help=(
                "Cloud provider for AgentKit services. BytePlus is used only "
                "when explicitly selected."
            ),
        ),
        click.option(
            "--dev",
            is_flag=True,
            default=False,
            help=(
                "Load LOCAL agents (this server's /list-apps) in the agent picker "
                "instead of your cloud AgentKit runtimes. The UI is still served "
                "normally; this only changes where the picker sources agents."
            ),
        ),
        click.option(
            "--vite",
            is_flag=True,
            default=False,
            help=(
                "Frontend hot-reload mode: serve the API only (no bundled UI) and "
                f"allow CORS from the Vite dev server ({DEV_SERVER_ORIGIN}). Run "
                "`npm run dev` in ./frontend and open that URL. For hacking on the "
                "React app; combine with --dev to also use local agents."
            ),
        ),
        click.option(
            "--oauth2-user-pool",
            default=None,
            help="VeIdentity User Pool NAME. When set (or its UID), enables SSO: "
            "unauthenticated browsers see a login page and the UI uses the signed-in user.",
        ),
        click.option(
            "--oauth2-user-pool-client",
            default=None,
            help="VeIdentity User Pool client NAME.",
        ),
        click.option(
            "--oauth2-user-pool-uid",
            default=None,
            envvar="OAUTH2_USER_POOL_ID",
            help="VeIdentity User Pool UID (env: OAUTH2_USER_POOL_ID). Use instead of "
            "the pool name.",
        ),
        click.option(
            "--oauth2-user-pool-client-uid",
            default=None,
            envvar="OAUTH2_USER_POOL_CLIENT_ID",
            help="VeIdentity client UID (env: OAUTH2_USER_POOL_CLIENT_ID). Use instead "
            "of the client name.",
        ),
        click.option(
            "--oauth2-redirect-uri",
            default=None,
            envvar="OAUTH2_REDIRECT_URI",
            help="OAuth2 callback URL (env: OAUTH2_REDIRECT_URI). Set this when deploying "
            "behind a public host/runtime; defaults to http://{host}:{port}/oauth2/callback.",
        ),
        click.option(
            "--oauth2-provider",
            default=None,
            envvar="OAUTH2_PROVIDER",
            help="SSO provider id (env: OAUTH2_PROVIDER), e.g. veidentity, github, google, "
            "or a custom name. For github/google, only client id/secret env vars are needed; "
            "for any OIDC provider set OAUTH2_ISSUER; otherwise set OAUTH2_AUTHORIZE_URL/"
            "OAUTH2_TOKEN_URL/OAUTH2_USERINFO_URL. Client creds via OAUTH2_CLIENT_ID/"
            "OAUTH2_CLIENT_SECRET. Defaults to veidentity when a user pool is configured.",
        ),
        click.option(
            "--oauth2-provider-label",
            default=None,
            envvar="OAUTH2_PROVIDER_LABEL",
            help="Display label for the SSO login button (env: OAUTH2_PROVIDER_LABEL).",
        ),
        click.option(
            "--auth-mode",
            type=click.Choice(["frontend", "gateway"]),
            default="frontend",
            show_default=True,
            envvar="VEADK_FRONTEND_AUTH_MODE",
            help="How the UI obtains the signed-in user (env: VEADK_FRONTEND_AUTH_MODE). "
            "'frontend' (default): this server runs its own OAuth2 login. 'gateway': "
            "trust the identity an upstream API gateway already authenticated and "
            "forwards as an Authorization: Bearer <JWT> — parse the user from it and run "
            "no in-app login (use when deployed behind the AgentKit runtime gateway).",
        ),
        click.option(
            "--generated-agent-test-run-ttl",
            default=1800,
            show_default=True,
            type=int,
            help="Seconds before a generated-agent debug runner is cleaned up.",
        ),
        click.option(
            "--sandbox-chat-codex-tool-id",
            default=None,
            envvar="SANDBOX_CHAT_CODEX",
            help="AgentKit CodeEnv Tool ID used by temporary chats "
            "(env: SANDBOX_CHAT_CODEX).",
        ),
        click.option(
            "--sandbox-chat-openclaw-tool-id",
            default=None,
            envvar="SANDBOX_CHAT_OPENCLAW",
            help="AgentKit ArkClawEnv Tool ID used by OpenClaw agents "
            "(env: SANDBOX_CHAT_OPENCLAW).",
        ),
        click.option(
            "--sandbox-chat-hermes-tool-id",
            default=None,
            envvar="SANDBOX_CHAT_HERMES",
            help="AgentKit HermesEnv Tool ID used by Hermes agents "
            "(env: SANDBOX_CHAT_HERMES).",
        ),
        click.option(
            "--sandbox-chat-codex-snapshot-tool-id",
            default=None,
            envvar="SANDBOX_CHAT_CODEX_SNAPSHOT",
            help="Snapshot-enabled AgentKit CodeEnv Tool ID used by persistent chats "
            "(env: SANDBOX_CHAT_CODEX_SNAPSHOT).",
        ),
        click.option(
            "--sandbox-chat-openclaw-snapshot-tool-id",
            default=None,
            envvar="SANDBOX_CHAT_OPENCLAW_SNAPSHOT",
            help="Snapshot-enabled AgentKit ArkClawEnv Tool ID used by persistent "
            "OpenClaw agents (env: SANDBOX_CHAT_OPENCLAW_SNAPSHOT).",
        ),
        click.option(
            "--sandbox-chat-hermes-snapshot-tool-id",
            default=None,
            envvar="SANDBOX_CHAT_HERMES_SNAPSHOT",
            help="Snapshot-enabled AgentKit HermesEnv Tool ID used by persistent "
            "Hermes agents (env: SANDBOX_CHAT_HERMES_SNAPSHOT).",
        ),
        click.option(
            "--admin",
            "studio_admins",
            default=None,
            envvar="VEADK_STUDIO_ADMINS",
            help="Comma-separated Studio admin usernames or OAuth emails "
            "(env: VEADK_STUDIO_ADMINS). Omit both role options to grant "
            "every user admin access.",
        ),
        click.option(
            "--developer",
            "studio_developers",
            default=None,
            envvar="VEADK_STUDIO_DEVELOPERS",
            help="Comma-separated Studio developer usernames or OAuth emails "
            "(env: VEADK_STUDIO_DEVELOPERS).",
        ),
        click.option(
            "--open/--no-open",
            "open_browser",
            default=False,
            show_default=True,
            help="Open the web UI in your default browser once the server is ready. "
            "Off by default (typical server-hosted deployments have no local browser); "
            "pass --open for local use. Ignored with --vite.",
        ),
    ]
    for opt in reversed(options):
        f = opt(f)
    return f


@click.group(invoke_without_command=True)
@_serve_options
@click.pass_context
def frontend(
    ctx: click.Context,
    agents_dir: str,
    frontend_dir: str | None,
    site_logo: str | None,
    site_title: str | None,
    host: str,
    port: int,
    provider: Literal["volcengine", "byteplus"],
    dev: bool,
    vite: bool,
    oauth2_user_pool: str | None,
    oauth2_user_pool_client: str | None,
    oauth2_user_pool_uid: str | None,
    oauth2_user_pool_client_uid: str | None,
    oauth2_redirect_uri: str | None,
    oauth2_provider: str | None,
    oauth2_provider_label: str | None,
    auth_mode: str,
    generated_agent_test_run_ttl: int,
    sandbox_chat_codex_tool_id: str | None,
    sandbox_chat_openclaw_tool_id: str | None,
    sandbox_chat_hermes_tool_id: str | None,
    sandbox_chat_codex_snapshot_tool_id: str | None,
    sandbox_chat_openclaw_snapshot_tool_id: str | None,
    sandbox_chat_hermes_snapshot_tool_id: str | None,
    studio_admins: str | None,
    studio_developers: str | None,
    open_browser: bool,
) -> None:
    """Launch the A2UI web UI backed by the ADK agent API server."""
    if ctx.invoked_subcommand is not None:
        return
    _run_frontend_server(
        agents_dir=agents_dir,
        frontend_dir=frontend_dir,
        site_logo=site_logo,
        site_title=site_title,
        host=host,
        port=port,
        provider=provider,
        dev=dev,
        vite=vite,
        oauth2_user_pool=oauth2_user_pool,
        oauth2_user_pool_client=oauth2_user_pool_client,
        oauth2_user_pool_uid=oauth2_user_pool_uid,
        oauth2_user_pool_client_uid=oauth2_user_pool_client_uid,
        oauth2_redirect_uri=oauth2_redirect_uri,
        oauth2_provider=oauth2_provider,
        oauth2_provider_label=oauth2_provider_label,
        auth_mode=auth_mode,
        generated_agent_test_run_ttl=generated_agent_test_run_ttl,
        sandbox_chat_codex_tool_id=sandbox_chat_codex_tool_id,
        sandbox_chat_openclaw_tool_id=sandbox_chat_openclaw_tool_id,
        sandbox_chat_hermes_tool_id=sandbox_chat_hermes_tool_id,
        sandbox_chat_codex_snapshot_tool_id=sandbox_chat_codex_snapshot_tool_id,
        sandbox_chat_openclaw_snapshot_tool_id=(sandbox_chat_openclaw_snapshot_tool_id),
        sandbox_chat_hermes_snapshot_tool_id=sandbox_chat_hermes_snapshot_tool_id,
        studio_admins=studio_admins,
        studio_developers=studio_developers,
        open_browser=open_browser,
        studio=False,
    )


@click.group(invoke_without_command=True)
@_serve_options
@click.pass_context
def studio(
    ctx: click.Context,
    agents_dir: str,
    frontend_dir: str | None,
    site_logo: str | None,
    site_title: str | None,
    host: str,
    port: int,
    provider: Literal["volcengine", "byteplus"],
    dev: bool,
    vite: bool,
    oauth2_user_pool: str | None,
    oauth2_user_pool_client: str | None,
    oauth2_user_pool_uid: str | None,
    oauth2_user_pool_client_uid: str | None,
    oauth2_redirect_uri: str | None,
    oauth2_provider: str | None,
    oauth2_provider_label: str | None,
    auth_mode: str,
    generated_agent_test_run_ttl: int,
    sandbox_chat_codex_tool_id: str | None,
    sandbox_chat_openclaw_tool_id: str | None,
    sandbox_chat_hermes_tool_id: str | None,
    sandbox_chat_codex_snapshot_tool_id: str | None,
    sandbox_chat_openclaw_snapshot_tool_id: str | None,
    sandbox_chat_hermes_snapshot_tool_id: str | None,
    studio_admins: str | None,
    studio_developers: str | None,
    open_browser: bool,
) -> None:
    """Launch AgentKit Studio — the frontend trimmed to add & manage agents.

    Same server as `veadk frontend`, but studio mode: the UI feature-gates off
    chat/search/skill-center/history and lands on the add-agent page.
    `veadk studio deploy` deploys this to VeFaaS.
    """
    if ctx.invoked_subcommand is not None:
        return
    _run_frontend_server(
        agents_dir=agents_dir,
        frontend_dir=frontend_dir,
        site_logo=site_logo,
        site_title=site_title,
        host=host,
        port=port,
        provider=provider,
        dev=dev,
        vite=vite,
        oauth2_user_pool=oauth2_user_pool,
        oauth2_user_pool_client=oauth2_user_pool_client,
        oauth2_user_pool_uid=oauth2_user_pool_uid,
        oauth2_user_pool_client_uid=oauth2_user_pool_client_uid,
        oauth2_redirect_uri=oauth2_redirect_uri,
        oauth2_provider=oauth2_provider,
        oauth2_provider_label=oauth2_provider_label,
        auth_mode=auth_mode,
        generated_agent_test_run_ttl=generated_agent_test_run_ttl,
        sandbox_chat_codex_tool_id=sandbox_chat_codex_tool_id,
        sandbox_chat_openclaw_tool_id=sandbox_chat_openclaw_tool_id,
        sandbox_chat_hermes_tool_id=sandbox_chat_hermes_tool_id,
        sandbox_chat_codex_snapshot_tool_id=sandbox_chat_codex_snapshot_tool_id,
        sandbox_chat_openclaw_snapshot_tool_id=(sandbox_chat_openclaw_snapshot_tool_id),
        sandbox_chat_hermes_snapshot_tool_id=sandbox_chat_hermes_snapshot_tool_id,
        studio_admins=studio_admins,
        studio_developers=studio_developers,
        open_browser=open_browser,
        studio=True,
    )


def _run_frontend_server(
    *,
    agents_dir: str,
    frontend_dir: str | None,
    site_logo: str | None,
    site_title: str | None,
    host: str,
    port: int,
    dev: bool,
    vite: bool = False,
    oauth2_user_pool: str | None,
    oauth2_user_pool_client: str | None,
    oauth2_user_pool_uid: str | None,
    oauth2_user_pool_client_uid: str | None,
    oauth2_redirect_uri: str | None,
    oauth2_provider: str | None,
    oauth2_provider_label: str | None,
    auth_mode: str,
    generated_agent_test_run_ttl: int,
    sandbox_chat_codex_tool_id: str | None = None,
    sandbox_chat_openclaw_tool_id: str | None = None,
    sandbox_chat_hermes_tool_id: str | None = None,
    sandbox_chat_codex_snapshot_tool_id: str | None = None,
    sandbox_chat_openclaw_snapshot_tool_id: str | None = None,
    sandbox_chat_hermes_snapshot_tool_id: str | None = None,
    studio_admins: str | None = None,
    studio_developers: str | None = None,
    open_browser: bool,
    provider: Literal["volcengine", "byteplus"] = "volcengine",
    studio: bool = False,
) -> None:
    """Launch the A2UI web UI backed by the ADK agent API server."""

    try:
        branding_title = normalize_site_title(site_title)
        branding_logo = resolve_site_logo(site_logo)
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    # Explicitly load .env file before any agent code runs
    # find_dotenv() searches upward from current directory to find .env
    from dotenv import find_dotenv, load_dotenv

    env_file_path = find_dotenv()
    if env_file_path:
        load_dotenv(env_file_path)
        logger.info(f"Loaded .env file from {env_file_path}")
    else:
        logger.warning("No .env file found in current directory or parent directories")

    # The local CLI is Volcengine-first even when a shell or global AgentKit
    # config previously selected BytePlus. BytePlus requires the explicit
    # ``--provider byteplus`` opt-in.
    os.environ["AGENTKIT_CLOUD_PROVIDER"] = provider
    os.environ["CLOUD_PROVIDER"] = provider
    from agentkit.platform.context import set_default_cloud_provider

    set_default_cloud_provider(provider)

    if sandbox_chat_codex_tool_id:
        os.environ["SANDBOX_CHAT_CODEX"] = sandbox_chat_codex_tool_id
    if sandbox_chat_openclaw_tool_id:
        os.environ["SANDBOX_CHAT_OPENCLAW"] = sandbox_chat_openclaw_tool_id
    if sandbox_chat_hermes_tool_id:
        os.environ["SANDBOX_CHAT_HERMES"] = sandbox_chat_hermes_tool_id
    if sandbox_chat_codex_snapshot_tool_id:
        os.environ["SANDBOX_CHAT_CODEX_SNAPSHOT"] = sandbox_chat_codex_snapshot_tool_id
    if sandbox_chat_openclaw_snapshot_tool_id:
        os.environ["SANDBOX_CHAT_OPENCLAW_SNAPSHOT"] = (
            sandbox_chat_openclaw_snapshot_tool_id
        )
    if sandbox_chat_hermes_snapshot_tool_id:
        os.environ["SANDBOX_CHAT_HERMES_SNAPSHOT"] = (
            sandbox_chat_hermes_snapshot_tool_id
        )

    from google.adk.cli.fast_api import get_fast_api_app

    agents_dir = os.path.abspath(agents_dir)
    allow_origins = _frontend_allow_origins(vite)

    app = get_fast_api_app(
        agents_dir=agents_dir,
        allow_origins=allow_origins,
        extra_plugins=[
            "veadk.multimodal.plugin.MultimodalMediaPlugin",
            "veadk.cli.frontend_invocation.FrontendInvocationPlugin",
        ],
        web=False,  # we serve our own UI, not the bundled ADK dev UI
    )

    from contextlib import asynccontextmanager

    from frontend.server.studio_routes import (
        StudioRouteChannelManager,
        build_studio_route_registry,
    )
    from frontend.server.studio_tools import build_studio_tool_registry
    from veadk.multimodal.service import MediaService
    from veadk.multimodal.storage import create_media_storage

    media_service = MediaService(create_media_storage())
    studio_tool_registry = build_studio_tool_registry(media_service=media_service)
    app.state.studio_tool_registry = studio_tool_registry
    if studio_tool_registry.enabled:
        logger.info(
            "Studio reverse tool channel enabled tools=%s revision=%s",
            [item["name"] for item in studio_tool_registry.manifests()],
            studio_tool_registry.revision,
        )

    studio_route_registry = build_studio_route_registry(provider=provider)
    studio_route_channels = StudioRouteChannelManager(studio_route_registry)
    app.state.studio_route_registry = studio_route_registry
    app.state.studio_route_channels = studio_route_channels
    if studio_route_registry.enabled:
        logger.info(
            "Studio reverse route channel enabled routes=%s revision=%s",
            [
                f"{item['method']} {item['path']}"
                for item in studio_route_registry.manifests()
            ],
            studio_route_registry.revision,
        )

    route_channel_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def _studio_route_channel_lifespan(current_app: Any):
        async with route_channel_lifespan(current_app):
            try:
                yield
            finally:
                await studio_route_channels.close()

    app.router.lifespan_context = _studio_route_channel_lifespan

    # Studio's production bundle includes large CSS assets. Compress them at
    # the application boundary so cloud API gateways do not have to stream the
    # uncompressed response to every browser. Starlette automatically skips
    # responses that must not be buffered, including server-sent events.
    from starlette.middleware.gzip import GZipMiddleware

    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)

    adk_server = None
    for route in app.routes:
        if getattr(route, "path", "") != "/run_sse":
            continue
        endpoint = getattr(route, "endpoint", None)
        for cell in getattr(endpoint, "__closure__", None) or ():
            candidate = cell.cell_contents
            if all(
                hasattr(candidate, attr)
                for attr in (
                    "agent_loader",
                    "session_service",
                    "artifact_service",
                    "get_runner_async",
                )
            ):
                adk_server = candidate
                break
        if adk_server is not None:
            break
    if adk_server is None:
        raise RuntimeError("Unable to access the ADK API server services")

    # ``web=False`` deliberately keeps ADK's full development API disabled,
    # but the VeADK trace drawer needs this one read-only endpoint. Register a
    # dedicated in-memory exporter instead of enabling eval/builder endpoints.
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from veadk.cli.frontend_trace import SessionTraceExporter

    tracer_provider = trace.get_tracer_provider()
    if not isinstance(tracer_provider, TracerProvider):
        raise RuntimeError("ADK did not initialize an SDK tracer provider")
    trace_exporter = SessionTraceExporter()
    tracer_provider.add_span_processor(SimpleSpanProcessor(trace_exporter))
    _mount_session_trace_route(app, trace_exporter)

    # Agent introspection for the UI's agent picker (name, model, tools). Reuses
    # ADK's AgentLoader, which caches each loaded `root_agent`.
    from fastapi import HTTPException, Query, Request
    from fastapi.responses import Response
    from google.adk.cli.utils.agent_loader import AgentLoader
    import httpx

    from frontend.server.evaluation_automation import (
        EvaluationAutomationService,
        RunSseActivity,
        RunSseObservation,
        observed_sse_stream,
    )
    from frontend.server.evaluation_automation import (
        create_service as create_evaluation_automation_service,
    )
    from frontend.server.evaluation_automation import (
        mount_routes as mount_evaluation_automation_routes,
    )
    from veadk.agent_metadata import (
        agent_component_summaries,
        agent_search_sources,
        agent_skill_summaries,
    )
    from veadk.agent_search import search_agent_component
    from veadk.cli.studio_rbac import (
        StudioAccessPolicy,
        StudioPrincipal,
        StudioRole,
        runtime_belongs_to,
    )
    from veadk.multimodal.api import mount_media_routes
    from veadk.multimodal.transport import resolve_runtime_media

    _agent_loader = AgentLoader(agents_dir)
    mount_media_routes(app, media_service)

    # Generated-agent debug is intentionally feature-complete in both local and
    # remote Studio deployments: the backend receives AgentDraft JSON, generates
    # the same project content as "Generate project", writes it to a temp dir,
    # and starts a runner for the debug session.
    generated_agent_test_run_allows_local_resources = True

    generated_agent_test_run_ttl = max(60, generated_agent_test_run_ttl)
    access_policy = StudioAccessPolicy.from_csv(
        studio_admins,
        studio_developers,
    )

    def _current_principal(request: Request) -> StudioPrincipal | None:
        """Resolve identity only from a trusted auth source.

        ``X-VeADK-Local-User`` is a local-development convenience and is not a
        production authentication boundary. It is ignored whenever OAuth or a
        trusted gateway is active.
        """
        if auth_mode == "gateway":
            claims = _claims_from_forwarded_jwt(request.headers.get("authorization"))
            return StudioPrincipal.from_claims(claims) if claims else None

        oauth2_handler = getattr(app.state, "oauth2_handler", None)
        if oauth2_handler is not None:
            session = oauth2_handler.get_session_from_request(request)
            if session and session.user_info:
                return StudioPrincipal.from_claims(session.user_info)
            if getattr(request.state, "oauth2_access_token_validated", False):
                claims = _claims_from_forwarded_jwt(
                    request.headers.get("authorization")
                )
                if claims:
                    return StudioPrincipal.from_claims(claims)
            scope_user = request.scope.get("user")
            display_name = str(getattr(scope_user, "display_name", "") or "")
            return StudioPrincipal.local(display_name)

        return StudioPrincipal.local(request.headers.get("X-VeADK-Local-User", ""))

    def _request_role(request: Request) -> StudioRole:
        principal = _current_principal(request)
        if access_policy.enabled and principal is None:
            raise HTTPException(status_code=401, detail="Studio identity is required")
        return access_policy.role_for(principal)

    from veadk.cli.frontend_issue_feedback import mount_issue_feedback_route

    async def _load_runtime_apmplus_trace(
        runtime: Any,
        *,
        runtime_id: str,
        region: str,
        session_id: str,
        invocation_id: str = "",
        end_time_ms: int | None = None,
    ) -> list[dict]:
        access_key, secret_key, session_token = _resolve_ve_credentials()
        from veadk.cli.frontend_apmplus_trace import load_apmplus_trace

        return await asyncio.to_thread(
            load_apmplus_trace,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token or "",
            provider=provider,
            region=region,
            project_name=str(getattr(runtime, "project_name", "") or "default"),
            runtime_id=runtime_id,
            session_id=session_id,
            invocation_id=invocation_id,
            now_ms=end_time_ms,
        )

    async def _load_issue_feedback_trace(report: Any, request: Request) -> list[dict]:
        runtime = _authorized_runtime(
            request,
            report.runtime_id,
            report.region,
            coded_access_error=True,
        )
        try:
            return await _load_runtime_apmplus_trace(
                runtime,
                runtime_id=report.runtime_id,
                region=report.region,
                session_id=report.session_id,
                invocation_id=report.invocation_id,
            )
        except Exception as error:  # noqa: BLE001 - feedback must remain usable
            logger.warning(
                "APMPlus issue-feedback trace query failed runtime_id=%s: %s",
                report.runtime_id,
                _redact_debug_text(str(error)),
            )
            return []

    @app.get("/web/runtime-trace")
    async def _web_runtime_trace(
        request: Request,
        runtimeId: str = "",
        sessionId: str = "",
        region: str = "cn-beijing",
        endTimeMs: int | None = None,
    ) -> list[dict]:
        if not runtimeId or not sessionId:
            raise HTTPException(
                status_code=400,
                detail="runtimeId and sessionId are required",
            )
        runtime = _authorized_runtime(
            request,
            runtimeId,
            region,
            coded_access_error=True,
        )
        try:
            spans = await _load_runtime_apmplus_trace(
                runtime,
                runtime_id=runtimeId,
                region=region,
                session_id=sessionId,
                end_time_ms=endTimeMs,
            )
        except Exception as error:
            logger.warning(
                "APMPlus Studio trace query failed runtime_id=%s: %s",
                runtimeId,
                _redact_debug_text(str(error)),
            )
            raise HTTPException(
                status_code=502,
                detail="加载调用链路失败，请稍后重试。",
            ) from error
        if not spans:
            raise HTTPException(
                status_code=404,
                detail="该 Agent 暂未开启链路观测，请到控制台打开后使用。",
            )
        from veadk.cli.frontend_apmplus_trace import normalize_apmplus_trace

        return normalize_apmplus_trace(spans)

    mount_issue_feedback_route(
        app,
        authorize=_request_role,
        trace_loader=_load_issue_feedback_trace,
    )

    def _require_agent_management(request: Request) -> StudioPrincipal | None:
        principal = _current_principal(request)
        if access_policy.enabled and principal is None:
            raise HTTPException(status_code=401, detail="Studio identity is required")
        if access_policy.role_for(principal) == StudioRole.USER:
            raise HTTPException(
                status_code=403, detail="Agent management is not allowed"
            )
        return principal

    from frontend.server.skills.devenv import mount_skill_workbench_routes
    from frontend.server.skills.models import SkillIdentity

    def _skill_identity(request: Request) -> SkillIdentity:
        principal = _current_principal(request)
        if access_policy.enabled and principal is None:
            raise HTTPException(status_code=401, detail="Studio identity is required")
        author = (
            (principal.display_name or principal.owner_id).strip()
            if principal is not None
            else "local"
        )
        return SkillIdentity(
            author=author,
            is_admin=access_policy.role_for(principal) == StudioRole.ADMIN,
        )

    def _skill_workbench_tools_client(region: str):
        from agentkit.sdk.tools.client import AgentkitToolsClient

        access_key, secret_key, session_token = _resolve_ve_credentials()
        client = AgentkitToolsClient(
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            session_token=session_token or "",
        )
        if provider != "byteplus":
            client.set_host("open.volcengineapi.com")
        return client

    def _skill_workbench_skills_client(region: str):
        from agentkit.sdk.skills.client import AgentkitSkillsClient

        access_key, secret_key, session_token = _resolve_ve_credentials()
        return AgentkitSkillsClient(
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            session_token=session_token or "",
        )

    mount_skill_workbench_routes(
        app,
        lambda request: _skill_identity(request).author,
        lambda request: _skill_identity(request).author,
        tools_client_factory=_skill_workbench_tools_client,
        skills_client_factory=_skill_workbench_skills_client,
    )

    def _intelligent_development_owner(request: Request) -> str:
        principal = _require_agent_management(request)
        return principal.owner_id if principal is not None else "local"

    from veadk.cli.frontend_coding_agents import mount_coding_agent_routes

    mount_coding_agent_routes(
        app,
        authorize=_require_agent_management,
    )

    @app.get("/web/access")
    async def _web_access(request: Request):
        principal = _current_principal(request)
        if access_policy.enabled and principal is None:
            raise HTTPException(status_code=401, detail="Studio identity is required")
        payload = access_policy.access_payload(principal)
        payload["telemetry"] = {
            "userId": principal.owner_id if principal else "",
            "accountId": os.getenv("VEADK_STUDIO_ACCOUNT_ID", "").strip(),
        }
        return payload

    def _resolve_ve_credentials() -> tuple[str, str, str | None]:
        """Resolve cloud credentials as (access_key, secret_key, session_token).

        Environment credentials support local development. When Studio runs in
        VeFaaS, the frontend function should use the IAM role's injected STS
        credential file so long-lived deployer AK/SK do not need to be shipped
        as function env vars.
        """

        def _read_vefaas_iam_credentials() -> tuple[str, str, str | None] | None:
            try:
                with open("/var/run/secrets/iam/credential", encoding="utf-8") as f:
                    data = json.load(f)
                ak = data.get("access_key_id") or data.get("AccessKeyId")
                sk = data.get("secret_access_key") or data.get("SecretAccessKey")
                token = data.get("session_token") or data.get("SessionToken")
                if ak and sk:
                    return ak, sk, token or None
            except (OSError, ValueError):
                pass
            return None

        if provider == "byteplus":
            ak = os.getenv("BYTEPLUS_ACCESS_KEY")
            sk = os.getenv("BYTEPLUS_SECRET_KEY")
            token = os.getenv("BYTEPLUS_SESSION_TOKEN")
            if ak and sk:
                return ak, sk, token or None
            credentials = _read_vefaas_iam_credentials()
            if credentials is not None:
                return credentials
            raise HTTPException(
                status_code=400,
                detail="BytePlus credentials not found (set BYTEPLUS_ACCESS_KEY/"
                "BYTEPLUS_SECRET_KEY, or run inside a VeFaaS function with an "
                "IAM role)",
            )

        ak = os.getenv("VOLCENGINE_ACCESS_KEY")
        sk = os.getenv("VOLCENGINE_SECRET_KEY")
        if ak and sk:
            # STS / temporary credentials carry a session token; don't drop it.
            token = os.getenv("VOLCENGINE_SESSION_TOKEN") or os.getenv(
                "VOLC_SESSIONTOKEN"
            )
            return ak, sk, token or None
        credentials = _read_vefaas_iam_credentials()
        if credentials is not None:
            return credentials
        raise HTTPException(
            status_code=400,
            detail="Volcengine credentials not found (set VOLCENGINE_ACCESS_KEY/"
            "SECRET_KEY, or run inside a VeFaaS function with an IAM role)",
        )

    def _default_cloud_region() -> str:
        return default_region(provider)

    def _coerce_cloud_region(region: str | None) -> str:
        candidate = (region or "").strip()
        if provider == "byteplus" and candidate.startswith("cn-"):
            return _default_cloud_region()
        if provider == "volcengine" and candidate.startswith("ap-"):
            return _default_cloud_region()
        return candidate or _default_cloud_region()

    def _knowledge_regions() -> tuple[str, ...]:
        return (
            ("ap-southeast-1",)
            if provider == "byteplus"
            else ("cn-beijing", "cn-shanghai")
        )

    def _knowledge_create_regions() -> tuple[str, ...]:
        return ("ap-southeast-1",) if provider == "byteplus" else ("cn-beijing",)

    from frontend.server.knowledge import (
        KnowledgeIdentity,
        KnowledgeService,
        SdkAgentKitKnowledgeGateway,
        TosKnowledgeUploadStore,
        VikingKnowledgeBaseProvisioner,
        build_viking_document_gateway_factory,
        mount_knowledge_routes,
    )

    def _knowledge_identity(request: Request) -> KnowledgeIdentity:
        principal = _current_principal(request)
        if access_policy.enabled and principal is None:
            raise HTTPException(status_code=401, detail="Studio identity is required")
        owner_id = principal.owner_id if principal is not None else "local"
        owner_label = (
            (principal.display_name or principal.owner_id).strip()
            if principal is not None
            else "local"
        )
        role = access_policy.role_for(principal)
        return KnowledgeIdentity(
            owner_id=owner_id,
            owner_label=owner_label,
            is_admin=role == StudioRole.ADMIN,
            can_bind_provider=role in (StudioRole.ADMIN, StudioRole.DEVELOPER),
        )

    def _knowledge_signing_key() -> bytes:
        explicit = os.getenv("VEADK_STUDIO_KNOWLEDGE_SIGNING_KEY", "").strip()
        if explicit:
            return explicit.encode("utf-8")
        oauth_secret = os.getenv("OAUTH2_CLIENT_SECRET", "").strip()
        if oauth_secret:
            return oauth_secret.encode("utf-8")
        try:
            _, cloud_secret, _ = _resolve_ve_credentials()
        except HTTPException:
            # Keep Studio bootable without cloud credentials. Knowledge writes
            # already require those credentials, so an ephemeral key is only
            # used by local or test instances that cannot persist cloud data.
            return os.urandom(32)
        return hashlib.sha256(
            b"veadk-studio-knowledge-signing-v1\0" + cloud_secret.encode("utf-8")
        ).digest()

    def _knowledge_client(region: str):
        from agentkit.sdk.knowledge.client import AgentkitKnowledgeClient

        access_key, secret_key, session_token = _resolve_ve_credentials()
        return AgentkitKnowledgeClient(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token or "",
            region=region,
        )

    mount_knowledge_routes(
        app,
        service=KnowledgeService(
            SdkAgentKitKnowledgeGateway(_knowledge_client),
            build_viking_document_gateway_factory(
                provider=provider,
                resolve_credentials=_resolve_ve_credentials,
            ),
            signing_key=_knowledge_signing_key(),
            provisioner=VikingKnowledgeBaseProvisioner(
                provider=provider,
                resolve_credentials=_resolve_ve_credentials,
            ),
            upload_store=TosKnowledgeUploadStore(
                provider=provider,
                resolve_credentials=_resolve_ve_credentials,
            ),
        ),
        identity_resolver=_knowledge_identity,
        region_resolver=_coerce_cloud_region,
        region_candidates_resolver=_knowledge_regions,
        create_region_candidates_resolver=_knowledge_create_regions,
    )

    from frontend.server.video.routes import (
        build_video_service,
        mount_video_routes,
    )

    def _video_owner(request: Request) -> str:
        principal = _current_principal(request)
        if access_policy.enabled and principal is None:
            raise HTTPException(status_code=401, detail="Studio identity is required")
        return principal.owner_id if principal is not None else "local"

    mount_video_routes(
        app,
        service=build_video_service(
            provider=provider,
            resolve_credentials=_resolve_ve_credentials,
        ),
        identity_resolver=_video_owner,
    )

    from frontend.server.artifacts import (
        create_service as create_artifact_service,
    )
    from frontend.server.artifacts import mount_routes as mount_artifact_routes

    mount_artifact_routes(
        app,
        service=create_artifact_service(
            provider=provider,
            resolve_credentials=_resolve_ve_credentials,
        ),
        identity_resolver=_video_owner,
    )

    from frontend.server.model_catalog import (
        build_model_catalog_service,
        mount_model_catalog_routes,
    )

    mount_model_catalog_routes(
        app,
        service=build_model_catalog_service(
            provider=provider,
            resolve_credentials=_resolve_ve_credentials,
        ),
        authorize=_require_agent_management,
    )

    from frontend.server.deployment_resources import (
        mount_deployment_resource_routes,
    )

    mount_deployment_resource_routes(
        app,
        authorize=_require_agent_management,
        provider=provider,
        resolve_credentials=_resolve_ve_credentials,
    )

    def _require_studio_admin(request: Request) -> None:
        if _request_role(request) != StudioRole.ADMIN:
            raise HTTPException(
                status_code=403,
                detail="Only Studio administrators can update Studio",
            )

    from veadk.cli.studio_self_update import (
        StudioSelfUpdater,
        StudioUpdateSettings,
        current_studio_display_version,
        mount_studio_update_routes,
    )

    mount_studio_update_routes(
        app,
        StudioSelfUpdater(
            settings=StudioUpdateSettings.from_env(provider=provider),
            credential_resolver=_resolve_ve_credentials,
            branding_logo=branding_logo,
        ),
        _require_studio_admin,
    )

    from veadk.cli.agentkit_sandbox_region import (
        resolve_sandbox_client_region,
        sandbox_region_candidates,
    )
    from veadk.cli.frontend_sandbox import (
        AgentkitSandboxGateway,
        SandboxAgentSessionService,
        SandboxConfigurationError,
        SandboxConversationService,
        SandboxProxyTarget,
        mount_sandbox_agent_routes,
        mount_sandbox_routes,
    )

    def _sandbox_client(region: str):
        from agentkit.sdk.tools.client import AgentkitToolsClient

        try:
            access_key, secret_key, session_token = _resolve_ve_credentials()
        except HTTPException as error:
            raise SandboxConfigurationError(str(error.detail)) from error
        resolved_region = resolve_sandbox_client_region(region, provider=provider)
        return AgentkitToolsClient(
            access_key=access_key,
            secret_key=secret_key,
            region=resolved_region,
            session_token=session_token or "",
        )

    def _sandbox_owner(request: Request) -> str:
        principal = _current_principal(request)
        if principal is None:
            raise HTTPException(status_code=401, detail="Studio identity is required")
        return principal.owner_id

    def _sandbox_creator(request: Request) -> str:
        principal = _current_principal(request)
        if principal is None:
            raise HTTPException(status_code=401, detail="Studio identity is required")
        return principal.display_name

    def _sandbox_is_admin(request: Request) -> bool:
        return _request_role(request) == StudioRole.ADMIN

    from frontend.server.migration.gateway import MigrationSandboxGateway
    from frontend.server.migration.routes import mount_migration_routes
    from frontend.server.migration.service import MigrationError, MigrationService

    def _migration_owner(request: Request) -> str:
        principal = _require_agent_management(request)
        return principal.owner_id if principal is not None else "local"

    def _migration_creator(request: Request) -> str:
        principal = _require_agent_management(request)
        return (
            (principal.display_name or principal.owner_id)
            if principal is not None
            else "local"
        )

    migration_service = MigrationService(
        MigrationSandboxGateway(
            tools_client_factory=_sandbox_client,
            region=os.getenv("AGENTKIT_SANDBOX_REGION"),
        )
    )
    # Register exact migration routes before the dynamic sandbox-agent routes.
    mount_migration_routes(
        app,
        migration_service,
        owner_resolver=_migration_owner,
        creator_resolver=_migration_creator,
    )

    sandbox_gateway = AgentkitSandboxGateway(
        _sandbox_client,
        region_candidates=sandbox_region_candidates(
            os.getenv("AGENTKIT_SANDBOX_REGION"),
            provider=provider,
        ),
    )
    from frontend.server.intelligent_development import StudioCredentials
    from frontend.server.intelligent_development_routes import (
        IntelligentDevelopmentGateway,
        mount_intelligent_development_routes,
    )

    intelligent_development_tool_id = (os.getenv("SANDBOX_DEV") or "").strip()
    intelligent_development_service = SandboxConversationService(
        IntelligentDevelopmentGateway(sandbox_gateway),
        tool_id=(
            intelligent_development_tool_id
            if intelligent_development_tool_id
            else "__intelligent-development-not-configured__"
        ),
        snapshot_tool_id=None,
        agent_kind="intelligent-development",
    )
    sandbox_service = SandboxConversationService(
        sandbox_gateway,
        tool_id=sandbox_chat_codex_tool_id,
        snapshot_tool_id=sandbox_chat_codex_snapshot_tool_id,
    )
    sandbox_agent_services = {
        "deepseek-harness": SandboxAgentSessionService(
            sandbox_gateway,
            kind="deepseek-harness",
            tool_id=sandbox_chat_codex_tool_id,
            snapshot_tool_id=sandbox_chat_codex_snapshot_tool_id,
            surface_path="/deepseek-harness/",
            filter_agent_kind=True,
        ),
        "openclaw": SandboxAgentSessionService(
            sandbox_gateway,
            kind="openclaw",
            tool_id=sandbox_chat_openclaw_tool_id,
            snapshot_tool_id=sandbox_chat_openclaw_snapshot_tool_id,
        ),
        "hermes": SandboxAgentSessionService(
            sandbox_gateway,
            kind="hermes",
            tool_id=sandbox_chat_hermes_tool_id,
            snapshot_tool_id=sandbox_chat_hermes_snapshot_tool_id,
        ),
    }

    def _sandbox_proxy_target(session_id: str, token: str) -> SandboxProxyTarget:
        resolvers = (
            sandbox_service.resolve_proxy_target,
            *(
                service.resolve_proxy_target
                for service in sandbox_agent_services.values()
            ),
        )
        found = False
        for resolver in resolvers:
            try:
                return resolver(session_id, token)
            except PermissionError:
                found = True
            except KeyError:
                continue
        if found:
            raise PermissionError("invalid Sandbox proxy capability")
        raise KeyError(session_id)

    mount_sandbox_routes(
        app,
        sandbox_service,
        _sandbox_owner,
        _sandbox_proxy_target,
        _sandbox_is_admin,
        _sandbox_creator,
    )

    def _intelligent_development_credentials() -> StudioCredentials:
        access_key, secret_key, session_token = _resolve_ve_credentials()
        return StudioCredentials(access_key, secret_key, session_token)

    mount_intelligent_development_routes(
        app,
        intelligent_development_service,
        _intelligent_development_owner,
        _sandbox_creator,
        _intelligent_development_credentials,
        configured=bool(intelligent_development_tool_id),
        validation_region=(
            os.getenv("VEADK_STUDIO_DEPLOY_REGION")
            or os.getenv("AGENTKIT_SANDBOX_REGION")
            or default_region(provider)
        ),
        validation_project=os.getenv("VEADK_STUDIO_PROJECT") or "default",
    )
    mount_sandbox_agent_routes(
        app,
        sandbox_agent_services,
        _sandbox_owner,
        _sandbox_is_admin,
        _sandbox_creator,
    )

    # Prefixes (and a few exact keys) we copy from the server's environment
    # into a created AgentKit runtime. Anything NOT in this list is left out
    # so we never ship unrelated host env (PATH, HOME, IAM_ROLE, _FAAS_*, etc.).
    _ENV_PREFIXES: tuple[str, ...] = (
        "MODEL_AGENT_",
        "MODEL_EMBEDDING_",
        "MODEL_IMAGE_",
        "MODEL_EDIT_",
        "MODEL_VIDEO_",
        "MODEL_REALTIME_",
        "TOOL_",
        "VOLCENGINE_",
        "BYTEPLUS_",
        "DATABASE_MEM0_",
        "DATABASE_VIKING",
        "DATABASE_TOS_",
        "DATABASE_CONTEXT_SEARCH_",
        "OBSERVABILITY_",
        "AGENTKIT_",
        "ARK_",
        "OPENAI_",
        "GOOGLE_",
        "CUSTOM_MODEL_",
    )
    _ENV_EXACT: frozenset[str] = frozenset(
        {
            "CLOUD_PROVIDER",
            "REGISTRY_SPACE_ID",
            "REGISTRY_ENDPOINT",
            "REGISTRY_VERSION",
            "REGISTRY_SERVICE_NAME",
            "REGISTRY_REGION",
            "REGISTRY_TOP_K",
            "REGISTRY_TIMEOUT_MS",
            "REGISTRY_POLL_INTERVAL_MS",
            "REGISTRY_UPSTREAM_TIP_TOKEN",
            "REGISTRY_ID_ENDPOINT",
            "A2A_REGISTRY_SPACE_ID",
            "A2A_REGISTRY_UPSTREAM_TIP_TOKEN",
            "A2A_REGISTRY_ACCESS_KEY",
            "A2A_REGISTRY_SECRET_KEY",
            "A2A_REGISTRY_SESSION_TOKEN",
            "MCP_URLS",
            "MCP_API_KEY",
            *_STUDIO_STORAGE_ENV_KEYS,
        }
    )
    _RESERVED_RUNTIME_ENV_KEYS = frozenset({"VEADK_DISABLE_EXPIRE_AT"})

    def _collect_runtime_envs() -> dict[str, str]:
        """Return env vars that should be injected into a deployed runtime."""
        try:
            from veadk.config import veadk_environments as _src
        except Exception:  # pragma: no cover
            _src = os.environ
        out: dict[str, str] = {}
        for k, v in _src.items():
            if not v:
                continue
            if k in _ENV_EXACT or any(k.startswith(p) for p in _ENV_PREFIXES):
                out[str(k)] = str(v)
        if provider == "byteplus":
            out["CLOUD_PROVIDER"] = "byteplus"
            out["AGENTKIT_CLOUD_PROVIDER"] = "byteplus"
            out["DATABASE_VIKING_REGION"] = DEFAULT_BYTEPLUS_VIKING_MEMORY_REGION
        return out

    def _resolve_ark_model_api_key(
        *,
        api_key_id: str = "",
        api_key_name: str = "",
    ) -> str:
        """Resolve one explicitly selected key without exposing it to the UI."""
        from veadk.auth.veauth.ark_veauth import get_ark_token

        access_key, secret_key, session_token = _resolve_ve_credentials()
        return get_ark_token(
            region=("ap-southeast-1" if provider == "byteplus" else "cn-beijing"),
            api_key_name=api_key_name.strip() or None,
            api_key_id=api_key_id.strip() or None,
            cloud_provider=provider,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
        )

    def _model_name(model: object) -> str:
        if isinstance(model, str):
            return model
        # ADK BaseLlm subclasses (incl. LiteLlm) carry the id on `.model`.
        return str(getattr(model, "model", None) or type(model).__name__)

    def _tool_label(tool: object) -> str:
        # FunctionTool / BaseTool expose `.name`; a bare function has
        # `__name__`; a toolset (e.g. MCP) has neither -> use its class name.
        name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
        return str(name or type(tool).__name__)

    def _agent_type(agent: object) -> str:
        # Map an ADK agent instance to the same type vocabulary the create
        # wizard uses: llm | sequential | parallel | loop | a2a.
        try:
            from google.adk.agents import (
                LoopAgent,
                ParallelAgent,
                SequentialAgent,
            )

            if isinstance(agent, LoopAgent):
                return "loop"
            if isinstance(agent, SequentialAgent):
                return "sequential"
            if isinstance(agent, ParallelAgent):
                return "parallel"
        except Exception:
            pass
        try:
            from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

            if isinstance(agent, RemoteA2aAgent):
                return "a2a"
        except Exception:
            pass
        return "llm"

    def _agent_node(
        agent: object, depth: int = 0, parent_path: tuple[str, ...] = ()
    ) -> dict:
        # Recursive typed tree for the conversation topology panel. Depth is
        # bounded so a pathological sub_agents cycle can't spin forever.
        name = getattr(agent, "name", "") or ""
        path = (*parent_path, name) if name else parent_path
        children = []
        if depth < 8:
            children = [
                _agent_node(s, depth + 1, path)
                for s in getattr(agent, "sub_agents", []) or []
            ]
        mode = getattr(agent, "mode", None)
        instruction = getattr(agent, "instruction", "")
        return {
            "id": name,
            "name": name,
            "description": getattr(agent, "description", "") or "",
            "instruction": instruction if isinstance(instruction, str) else "",
            "type": _agent_type(agent),
            "model": _model_name(getattr(agent, "model", "")),
            "tools": [_tool_label(t) for t in getattr(agent, "tools", []) or []],
            "skills": agent_skill_summaries(agent),
            "components": agent_component_summaries(agent),
            "path": list(path),
            "mentionable": mode not in ("task", "single_turn"),
            "children": children,
        }

    if branding_logo is not None:

        @app.get("/web/site-logo")
        async def _web_site_logo():
            return Response(
                content=branding_logo.content,
                media_type=branding_logo.media_type,
                headers={"Cache-Control": "no-cache"},
            )

    @app.get("/web/ui-config")
    async def _web_ui_config():
        """Feature gates the SPA reads at startup. Studio now serves the SAME UI
        as `veadk frontend` — all modules (chat/search/skill-center/history +
        add/manage agent) enabled, landing on the chat view. The `studio` flag
        is informational."""
        version = current_studio_display_version()
        return {
            "studio": studio,
            "version": version,
            "provider": provider,
            "branding": {
                "title": branding_title,
                "logoUrl": "/web/site-logo" if branding_logo is not None else "",
            },
            # Agent source for the picker: --dev serves local agents (/list-apps),
            # otherwise the deployed UI lists the user's cloud AgentKit runtimes.
            "agentsSource": "local" if dev else "cloud",
            "features": {
                "newChat": True,
                "search": True,
                "skillCenter": True,
                "history": True,
                "addAgent": True,
                "manageAgents": True,
                "agentUsage": studio,
                "addAgentkit": True,
                "generatedAgentTestRun": True,
                "generatedAgentTestRunDisabledReason": "",
            },
            "defaultView": "chat",
            "telemetry": studio_telemetry_config(version, enabled=studio),
        }

    system_info_sandbox_tools = (
        ("codex", "Codex Sandbox", "SANDBOX_CHAT_CODEX", False),
        (
            "codex_snapshot",
            "Codex Sandbox",
            "SANDBOX_CHAT_CODEX_SNAPSHOT",
            True,
        ),
        (
            "deepseek_harness",
            "DeepSeek Harness Sandbox",
            "SANDBOX_CHAT_CODEX",
            False,
        ),
        (
            "deepseek_harness_snapshot",
            "DeepSeek Harness Sandbox",
            "SANDBOX_CHAT_CODEX_SNAPSHOT",
            True,
        ),
        ("openclaw", "OpenClaw Sandbox", "SANDBOX_CHAT_OPENCLAW", False),
        (
            "openclaw_snapshot",
            "OpenClaw Sandbox",
            "SANDBOX_CHAT_OPENCLAW_SNAPSHOT",
            True,
        ),
        ("hermes", "Hermes Sandbox", "SANDBOX_CHAT_HERMES", False),
        (
            "hermes_snapshot",
            "Hermes Sandbox",
            "SANDBOX_CHAT_HERMES_SNAPSHOT",
            True,
        ),
        ("dev", "Dev Sandbox", "SANDBOX_DEV", False),
    )

    def _default_model_env_state() -> dict[str, object]:
        return {
            "needsModelEnvUpdate": False,
            "canUpdateModelEnv": False,
            "modelEnvError": "",
            "modelEnvErrorCode": "",
        }

    def _model_env_error_code_state(error_code: str) -> dict[str, object]:
        state = _default_model_env_state()
        state["modelEnvErrorCode"] = error_code
        return state

    def _log_codex_model_env_check_warning(
        *,
        error_code: str,
        kind: str,
        label: str,
        tool_id: str,
        region: str = "",
        detail: str = "",
        timeout_seconds: float | None = None,
    ) -> None:
        logger.warning(
            "Codex Sandbox model env check failed: "
            "error_code=%s kind=%s label=%s tool_id=%s region=%s "
            "timeout_seconds=%s detail=%s",
            error_code,
            kind,
            label,
            tool_id,
            region,
            timeout_seconds if timeout_seconds is not None else "",
            detail,
        )

    system_info_codex_model_env_states = {
        kind: _default_model_env_state()
        for kind, _label, _environment_key, _snapshot in system_info_sandbox_tools
        if kind in {"codex", "codex_snapshot"}
    }

    async def _inspect_system_info_codex_model_env_state(
        *,
        kind: str,
        tool_id: str,
        label: str,
    ) -> dict[str, object]:
        model_env_state = _default_model_env_state()
        if not tool_id:
            return model_env_state

        from veadk.cli.studio_sandbox_tools import (
            inspect_studio_codex_model_environment,
        )

        try:
            access_key, secret_key, session_token = _resolve_ve_credentials()
        except Exception as error:
            detail = _safe_exception_detail(error)
            _log_codex_model_env_check_warning(
                error_code="codex_model_env_credentials_unavailable",
                kind=kind,
                label=label,
                tool_id=tool_id,
                detail=detail,
            )
            return _model_env_error_code_state(
                "codex_model_env_credentials_unavailable"
            )

        last_not_found: Exception | None = None
        for sandbox_region in sandbox_region_candidates(
            os.getenv("AGENTKIT_SANDBOX_REGION"),
            provider=provider,
        ):
            try:
                status = await asyncio.to_thread(
                    inspect_studio_codex_model_environment,
                    tool_id=tool_id,
                    access_key=access_key,
                    secret_key=secret_key,
                    session_token=session_token,
                    region=sandbox_region,
                )
                return {
                    "needsModelEnvUpdate": status.needs_model_env_update,
                    "canUpdateModelEnv": status.can_update_model_env,
                    "modelEnvError": status.model_env_error,
                    "modelEnvErrorCode": "",
                }
            except Exception as error:
                if is_agentkit_resource_not_found(error):
                    last_not_found = error
                    continue
                detail = _safe_exception_detail(
                    error,
                    secrets=(access_key, secret_key, session_token),
                )
                _log_codex_model_env_check_warning(
                    error_code="codex_model_env_check_failed",
                    kind=kind,
                    label=label,
                    tool_id=tool_id,
                    region=sandbox_region,
                    detail=detail,
                )
                return _model_env_error_code_state("codex_model_env_check_failed")

        detail = (
            _safe_exception_detail(
                last_not_found,
                secrets=(access_key, secret_key, session_token),
            )
            if last_not_found
            else f"{label} Tool 不存在"
        )
        _log_codex_model_env_check_warning(
            error_code="codex_model_env_tool_not_found",
            kind=kind,
            label=label,
            tool_id=tool_id,
            detail=detail,
        )
        return _model_env_error_code_state("codex_model_env_tool_not_found")

    async def _refresh_system_info_codex_model_env_states() -> None:
        async def _refresh_one(
            kind: str,
            label: str,
            environment_key: str,
        ) -> None:
            tool_id = (os.getenv(environment_key) or "").strip()
            if not tool_id:
                system_info_codex_model_env_states[kind] = _default_model_env_state()
                return
            try:
                timeout_seconds = 8.0
                state = await asyncio.wait_for(
                    _inspect_system_info_codex_model_env_state(
                        kind=kind,
                        tool_id=tool_id,
                        label=label,
                    ),
                    timeout=timeout_seconds,
                )
            except TimeoutError:
                _log_codex_model_env_check_warning(
                    error_code="codex_model_env_check_timeout",
                    kind=kind,
                    label=label,
                    tool_id=tool_id,
                    timeout_seconds=timeout_seconds,
                    detail="timed out while reading Tool envs",
                )
                state = _model_env_error_code_state("codex_model_env_check_timeout")
            system_info_codex_model_env_states[kind] = state

        await asyncio.gather(
            *(
                _refresh_one(kind, label, environment_key)
                for kind, label, environment_key, _snapshot in system_info_sandbox_tools
                if kind in {"codex", "codex_snapshot"}
            )
        )

    @app.get("/web/system-info")
    async def _web_system_info(request: Request):
        """Return non-secret Studio resource identifiers for system diagnostics."""
        _require_studio_admin(request)
        from frontend.server.storage import StudioStorageConfig

        storage_config = StudioStorageConfig.from_env(provider)
        sandbox_tools = []
        for kind, label, environment_key, snapshot in system_info_sandbox_tools:
            tool_id = (os.getenv(environment_key) or "").strip()
            model_env_state = (
                dict(
                    system_info_codex_model_env_states.get(
                        kind,
                        _default_model_env_state(),
                    )
                )
                if kind in {"codex", "codex_snapshot"}
                else _default_model_env_state()
            )
            sandbox_tools.append(
                {
                    "kind": kind,
                    "label": label,
                    "toolId": tool_id,
                    "snapshot": snapshot,
                    **model_env_state,
                }
            )
        return {
            "storage": {
                "tosAddress": storage_config.object_host,
            },
            "sandboxTools": sandbox_tools,
        }

    @app.post("/web/system-info/sandbox-tools/{kind}/model-env")
    async def _web_update_system_info_sandbox_tool_model_env(
        kind: str,
        request: Request,
    ):
        """Backfill Codex Sandbox model envs without exposing secrets."""
        _require_studio_admin(request)
        codex_tools = {
            tool_kind: (label, environment_key)
            for tool_kind, label, environment_key, _snapshot in system_info_sandbox_tools
            if tool_kind in {"codex", "codex_snapshot"}
        }
        if kind not in codex_tools:
            raise HTTPException(status_code=400, detail="Unsupported Sandbox Tool kind")
        label, environment_key = codex_tools[kind]
        tool_id = (os.getenv(environment_key) or "").strip()
        if not tool_id:
            raise HTTPException(status_code=400, detail=f"{label} 未配置 Tool ID")

        from veadk.cli.studio_sandbox_tools import (
            ensure_studio_codex_model_environment,
        )

        access_key, secret_key, session_token = _resolve_ve_credentials()
        last_not_found: Exception | None = None
        for sandbox_region in sandbox_region_candidates(
            os.getenv("AGENTKIT_SANDBOX_REGION"),
            provider=provider,
        ):
            try:
                updated = await asyncio.to_thread(
                    ensure_studio_codex_model_environment,
                    tool_id=tool_id,
                    access_key=access_key,
                    secret_key=secret_key,
                    session_token=session_token,
                    region=sandbox_region,
                )
                system_info_codex_model_env_states[kind] = _default_model_env_state()
                return {"kind": kind, "toolId": tool_id, "updated": updated}
            except Exception as error:
                if is_agentkit_resource_not_found(error):
                    last_not_found = error
                    continue
                if isinstance(error, ValueError):
                    state = _default_model_env_state()
                    state["needsModelEnvUpdate"] = True
                    state["modelEnvError"] = str(error)
                    system_info_codex_model_env_states[kind] = state
                    raise HTTPException(status_code=400, detail=str(error)) from error
                raise HTTPException(
                    status_code=502,
                    detail=_safe_exception_detail(
                        error,
                        secrets=(access_key, secret_key, session_token),
                    ),
                ) from error

        detail = (
            _safe_exception_detail(
                last_not_found,
                secrets=(access_key, secret_key, session_token),
            )
            if last_not_found
            else f"{label} Tool 不存在"
        )
        state = _default_model_env_state()
        state["modelEnvError"] = detail
        system_info_codex_model_env_states[kind] = state
        raise HTTPException(status_code=404, detail=detail)

    @app.get("/web/agent-info/{app_name}")
    async def _web_agent_info(app_name: str):
        try:
            agent = _agent_loader.load_agent(app_name)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"unknown agent: {app_name}")
        return {
            "name": getattr(agent, "name", app_name),
            "description": getattr(agent, "description", "") or "",
            "type": _agent_type(agent),
            "model": _model_name(getattr(agent, "model", "")),
            "tools": [_tool_label(t) for t in getattr(agent, "tools", []) or []],
            "skills": agent_skill_summaries(agent),
            "components": agent_component_summaries(agent),
            "searchSources": agent_search_sources(agent),
            "subAgents": [
                getattr(s, "name", "") for s in getattr(agent, "sub_agents", []) or []
            ],
            # Recursive typed tree used by the conversation topology panel.
            "graph": _agent_node(agent),
        }

    def _web_search_aksk() -> tuple[str | None, str | None]:
        ak = os.getenv("TOOL_WEB_SEARCH_ACCESS_KEY") or os.getenv(
            "VOLCENGINE_ACCESS_KEY"
        )
        sk = os.getenv("TOOL_WEB_SEARCH_SECRET_KEY") or os.getenv(
            "VOLCENGINE_SECRET_KEY"
        )
        return ak, sk

    @app.get("/web/search")
    async def _web_search(
        source: str,
        app_name: str,
        q: str,
        user_id: str = "",
    ):
        """Search the web or retrieval components mounted on a local Agent."""
        if source not in {"web", "knowledge", "memory"}:
            raise HTTPException(status_code=400, detail=f"unsupported source: {source}")

        try:
            agent = _agent_loader.load_agent(app_name)
        except ValueError:
            agent = None
        if source in {"knowledge", "memory"}:
            if agent is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"unknown agent: {app_name}",
                )
            if source == "memory" and not user_id:
                raise HTTPException(
                    status_code=400,
                    detail="user_id is required for long-term memory search",
                )
            return await search_agent_component(
                agent,
                source,
                q,
                app_name=app_name,
                user_id=user_id,
            )

        if not q.strip():
            return {"mounted": True, "results": []}
        if provider == "byteplus":
            if not os.getenv("BYTEPLUS_WEB_SEARCH_API_KEY"):
                return {
                    "mounted": True,
                    "results": [],
                    "error": "服务端未配置 BYTEPLUS_WEB_SEARCH_API_KEY",
                }
            try:
                from veadk.tools.builtin_tools.web_search import (
                    _byteplus_web_search,
                    _extract_web_results,
                    _result_summary,
                )

                resp = _byteplus_web_search(q[:100], count=8)
                results = []
                for item in _extract_web_results(resp):
                    results.append(
                        {
                            "title": str(item.get("Title") or item.get("title") or ""),
                            "url": str(
                                item.get("Url")
                                or item.get("url")
                                or item.get("Link")
                                or item.get("link")
                                or ""
                            ),
                            "siteName": str(
                                item.get("SiteName")
                                or item.get("siteName")
                                or item.get("site_name")
                                or ""
                            ),
                            "summary": _result_summary(item),
                        }
                    )
                return {"mounted": True, "results": results}
            except Exception as e:
                logger.error(f"BytePlus web search error: {e}", exc_info=True)
                return {
                    "mounted": True,
                    "results": [],
                    "error": str(e),
                }

        # Gate on the agent's tools only when we can introspect it locally.
        if agent is not None:
            if "web" not in agent_search_sources(agent):
                return {"mounted": False, "results": []}

        ak, sk = _web_search_aksk()
        if not (ak and sk):
            return {
                "mounted": True,
                "results": [],
                "error": "服务端未配置 Volcengine AK/SK",
            }

        from veadk.utils.volcengine_sign import ve_request

        resp = ve_request(
            request_body={
                "Query": q[:100],
                "SearchType": "web",
                "Count": 8,
                "NeedSummary": True,
                "Filter": {"NeedUrl": True},
            },
            action="WebSearch",
            ak=ak,
            sk=sk,
            service="volc_torchlight_api",
            version="2025-01-01",
            region="cn-beijing",
            host="mercury.volcengineapi.com",
            header={"X-Security-Token": ""},
        )
        err = (
            (resp.get("ResponseMetadata") or {}).get("Error")
            if isinstance(resp, dict)
            else None
        )
        if err:
            return {
                "mounted": True,
                "results": [],
                "error": str(err.get("Message") or err),
            }
        items = (
            ((resp.get("Result") or {}).get("WebResults") or [])
            if isinstance(resp, dict)
            else []
        )
        results = [
            {
                "title": it.get("Title", "") or "",
                "url": it.get("Url", "") or "",
                "siteName": it.get("SiteName", "") or "",
                "summary": (it.get("Summary") or it.get("Snippet") or "").strip(),
            }
            for it in items
        ]
        return {"mounted": True, "results": results}

    # ---- Skill Hub proxy: proxy /skillhub/* to skills.volces.com ----
    SKILLHUB_TARGET = "https://skills.volces.com"

    @app.api_route(
        "/skillhub/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
    )
    async def _skillhub_proxy(request: Request, path: str):
        """Proxy requests to Volcengine Skill Hub API to avoid CORS issues."""
        target_url = f"{SKILLHUB_TARGET}/{path}"
        if request.url.query:
            target_url += f"?{request.url.query}"

        headers = dict(request.headers)
        headers.pop("host", None)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=await request.body(),
                    timeout=30.0,
                )
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )
        except Exception as e:
            logger.error(f"Skillhub proxy error: {e}")
            raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")

    @app.get("/harness/skills/findskill")
    async def _studio_search_findskill(
        query: str = "",
        page_number: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=50),
    ) -> dict[str, Any]:
        """Expose the public Skill Hub search contract used by Agent creation."""
        try:
            from frontend.server.studio_routes.skill_catalog import (
                StudioSkillCatalog,
            )

            return await StudioSkillCatalog(provider).search_findskill(
                query=query,
                page_number=page_number,
                page_size=page_size,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="暂时无法搜索 Skill Hub，请稍后重试。",
            ) from exc

    # ---- AgentKit proxy: proxy /agentkit-proxy/* to remote AgentKit ----
    @app.api_route(
        "/agentkit-proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
    )
    async def _agentkit_proxy(request: Request, path: str):
        """Proxy requests to remote AgentKit APIs to avoid CORS issues.

        This proxy makes server-side requests to a URL supplied by the client,
        so it is locked down to prevent SSRF: the target host must be an
        AgentKit domain (``*.volceapi.com``) over HTTPS, and a credential
        (``X-AgentKit-Key``) must be present. Without both, we refuse rather
        than let the server reach arbitrary internal/external URLs.
        """
        _require_agent_management(request)
        from urllib.parse import urlparse

        target_base = request.headers.get("X-AgentKit-Base")
        api_key = request.headers.get("X-AgentKit-Key")
        if not target_base:
            raise HTTPException(status_code=400, detail="Missing X-AgentKit-Base")
        # Require a credential — an unauthenticated proxy is an open relay.
        if not api_key or not api_key.strip():
            raise HTTPException(status_code=401, detail="Missing X-AgentKit-Key")

        # SSRF guard: only HTTPS AgentKit domains may be targeted.
        parsed = urlparse(target_base)
        host = (parsed.hostname or "").lower()
        allowed = host == "volceapi.com" or host.endswith(".volceapi.com")
        if parsed.scheme != "https" or not allowed:
            raise HTTPException(
                status_code=403,
                detail="X-AgentKit-Base must be an https://*.volceapi.com URL",
            )

        # The local frontend may append SSO gateway query params to authenticate
        # this same-origin proxy request. Do not forward those params to the
        # remote AgentKit runtime, where names such as "token" can be interpreted
        # as the runtime credential and cause a false 401.
        target_url = f"{target_base.rstrip('/')}/{path}"

        headers = _build_agentkit_proxy_headers(dict(request.headers), api_key)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=await request.body(),
                    timeout=30.0,
                )
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )
        except Exception as e:
            logger.error(f"AgentKit proxy error: {e}")
            raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")

    # ---- Generated-agent debug runs -----------------------------------------
    # This replaces the old in-process temp-agent loader. Generated Python code
    # is only loaded by a short-lived subprocess runner.
    import atexit
    import importlib.util
    import secrets
    import shutil
    import socket
    import subprocess
    import threading as _test_threading
    import time
    from dataclasses import dataclass
    from pathlib import Path as PathlibPath
    from urllib.parse import quote
    from pydantic import ValidationError

    from veadk.cli.generated_agent_codegen import (
        AgentDraft,
        GeneratedAgentProjectRequest,
        GeneratedAgentTestRunRequest,
        GeneratedFile,
        GeneratedProject,
        debug_runtime_env_from_draft,
        generate_project_from_draft,
        normalize_and_validate_draft,
    )
    from veadk.cli.generated_agent_security import (
        DebugPolicyError,
        trusted_debug_model_api_base,
        validate_debug_policy,
        validate_project_policy,
    )
    from veadk.cli.generated_agent_planner import (
        GeneratedAgentDraftRequest,
        generate_agent_draft,
    )
    from veadk.cli.generated_agent_mcp import (
        McpDebugConnectionError,
        resolve_debug_mcp_endpoints,
    )
    from veadk.cli.generated_agent_skills import (
        _files_from_zip,
        _is_macos_metadata,
        materialize_selected_skills,
    )
    from veadk.extensions.harness.sidecar import (
        HarnessSidecarDependencyError,
        agentkit_cli_executable,
        get_studio_harness_sidecar_catalog,
        normalize_studio_harness_intent,
        resolve_studio_harness_sidecar_selection,
        studio_harness_deployment_config,
        studio_harness_runtime_env,
    )

    _TEST_RUN_MAX_FILES = 300
    _TEST_RUN_MAX_FILE_BYTES = 256 * 1024
    _TEST_RUN_MAX_TOTAL_BYTES = 2 * 1024 * 1024
    _TEST_RUN_MAX_ACTIVE = 3
    _TEST_RUN_READY_TIMEOUT = 30.0

    def _enabled_env_flag(name: str) -> bool:
        value = os.getenv(name, "")
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def _managed_sidecar_regions() -> list[str]:
        return [
            item.strip()
            for item in os.getenv(
                "VEADK_STUDIO_HARNESS_SIDECAR_REGIONS",
                "",
            ).split(",")
            if item.strip()
        ]

    def _harness_sidecar_debug_capability() -> dict[str, Any]:
        import platform

        if not _enabled_env_flag("VEADK_STUDIO_HARNESS_SIDECAR_DEBUG_ENABLED"):
            return {
                "available": False,
                "reason": "当前 Studio 环境未启用 Harness Sidecar 调试能力。",
            }
        supported_platform = (
            sys.version_info[:2] == (3, 12)
            and sys.platform.startswith("linux")
            and platform.machine().lower() in {"x86_64", "amd64"}
        )
        if not supported_platform:
            return {
                "available": False,
                "reason": (
                    "Harness Sidecar 调试当前仅支持 CPython 3.12 / linux/amd64。"
                ),
            }
        if not all(
            os.getenv(name, "").strip()
            for name in (
                "HARNESS_SIDECAR_APIG_ENDPOINT",
                "HARNESS_SIDECAR_APIG_API_KEY",
            )
        ):
            return {
                "available": False,
                "reason": (
                    "当前 Studio Runtime 尚未完成 Harness Sidecar APIG 自调用绑定。"
                ),
            }
        return {"available": True, "reason": ""}

    def _harness_sidecar_deployment_capability() -> dict[str, Any]:
        regions = _managed_sidecar_regions()
        try:
            agentkit_cli_executable()
            cli_available = True
        except HarnessSidecarDependencyError:
            cli_available = False
        available = bool(
            cli_available
            and regions
            and os.getenv("VEADK_STUDIO_HARNESS_SIDECAR_BASE_IMAGE", "").strip()
        )
        return {
            "available": available,
            "reason": (
                ""
                if available
                else "当前 Studio 尚未配置受控 Harness Sidecar Runtime artifact。"
            ),
            "regions": regions,
            "platform": "linux/amd64",
            "pythonVersion": "3.12",
            "maxInstances": 1,
        }

    @app.get("/web/harness-sidecar/catalog")
    async def _get_harness_sidecar_catalog(request: Request):
        _require_agent_management(request)
        return get_studio_harness_sidecar_catalog()

    @app.post("/web/harness-sidecar/resolve")
    async def _resolve_harness_sidecar(request: Request):
        _require_agent_management(request)
        data = await request.json()
        intent = data.get("intent") if isinstance(data, dict) else None
        try:
            return resolve_studio_harness_sidecar_selection(intent)
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except HarnessSidecarDependencyError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @dataclass
    class _GeneratedAgentTestRun:
        run_id: str
        app_name: str
        temp_dir: str
        base_url: str
        process: subprocess.Popen
        expires_at: float
        owner_id: str
        plan_hash: str = ""

    _test_runs: dict[str, _GeneratedAgentTestRun] = {}
    _test_runs_creating: dict[str, int] = {}
    _test_runs_lock = _test_threading.Lock()

    def _terminate_test_run(run: _GeneratedAgentTestRun) -> None:
        if run.process.poll() is None:
            run.process.terminate()
            try:
                run.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                run.process.kill()
                run.process.wait(timeout=3)
        shutil.rmtree(run.temp_dir, ignore_errors=True)

    def _cleanup_expired_test_runs() -> None:
        now = time.time()
        expired: list[_GeneratedAgentTestRun] = []
        with _test_runs_lock:
            for run_id, run in list(_test_runs.items()):
                if run.expires_at <= now or run.process.poll() is not None:
                    expired.append(_test_runs.pop(run_id))
        for run in expired:
            _terminate_test_run(run)

    def _cleanup_all_test_runs() -> None:
        with _test_runs_lock:
            runs = list(_test_runs.values())
            _test_runs.clear()
        for run in runs:
            _terminate_test_run(run)

    atexit.register(_cleanup_all_test_runs)

    _cleanup_interval = min(30, max(5, generated_agent_test_run_ttl // 2))

    def _test_run_cleanup_loop() -> None:
        while True:
            time.sleep(_cleanup_interval)
            try:
                _cleanup_expired_test_runs()
            except Exception as e:
                logger.warning(f"Generated-agent test-run cleanup failed: {e}")

    _test_threading.Thread(
        target=_test_run_cleanup_loop,
        name="generated-agent-test-run-cleanup",
        daemon=True,
    ).start()

    def _get_test_run(
        run_id: str,
        request: Request,
    ) -> _GeneratedAgentTestRun:
        _cleanup_expired_test_runs()
        with _test_runs_lock:
            run = _test_runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="test run not found")
        principal = _require_agent_management(request)
        if _request_role(request) != StudioRole.ADMIN and (
            principal is None or run.owner_id != principal.owner_id
        ):
            raise HTTPException(status_code=404, detail="test run not found")
        return run

    def _safe_runner_env() -> dict[str, str]:
        """Whitelisted environment for the child runner.

        Do not inherit full os.environ. The debug runner gets model credentials
        plus Volcengine/tool credentials so generated agents can exercise real
        tool calls during local debugging.
        """
        env: dict[str, str] = {
            "OTEL_SDK_DISABLED": "false",
            "VEADK_DISABLE_EXPIRE_AT": "true",
            "ENABLE_APMPLUS": "false",
            "ENABLE_COZELOOP": "false",
            "ENABLE_TLS": "false",
        }
        for key in (
            "MODEL_AGENT_API_KEY",
            "MODEL_AGENT_API_BASE",
            "MODEL_AGENT_BASE_URL",
            "MODEL_AGENT_NAME",
            "MODEL_AGENT_PROVIDER",
            "MODEL_AGENT_API_KEY_NAME",
            "MODEL_EMBEDDING_API_KEY",
            "MODEL_IMAGE_API_KEY",
            "MODEL_EDIT_API_KEY",
            "MODEL_VIDEO_API_KEY",
            "MODEL_REALTIME_API_KEY",
            "ARK_API_KEY",
            "VOLCENGINE_ACCESS_KEY",
            "VOLCENGINE_SECRET_KEY",
            "VOLCENGINE_SESSION_TOKEN",
            "VOLCENGINE_REGION",
            "BYTEPLUS_ACCESS_KEY",
            "BYTEPLUS_SECRET_KEY",
            "BYTEPLUS_SESSION_TOKEN",
            "BYTEPLUS_REGION",
            "TOOL_WEB_SEARCH_ACCESS_KEY",
            "TOOL_WEB_SEARCH_SECRET_KEY",
            "TOOL_VESPEECH_APP_ID",
            "TOOL_VESPEECH_ACCESS_TOKEN",
            "TOOL_VESEARCH_ENDPOINT",
            "TOOL_WEB_SCRAPER_ENDPOINT",
            "DATABASE_MEM0_API_KEY",
            "CLOUD_PROVIDER",
            "AGENTKIT_CLOUD_PROVIDER",
            "BYTEPLUS_WEB_SEARCH_API_KEY",
            "OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY",
            *_STUDIO_STORAGE_ENV_KEYS,
        ):
            if os.getenv(key):
                env[key] = os.environ[key]
        for key in (
            "PATH",
            "HOME",
            "USER",
            "LOGNAME",
            "SHELL",
            "TMPDIR",
            "TEMP",
            "TMP",
            "VIRTUAL_ENV",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "NO_PROXY",
        ):
            if os.getenv(key):
                env[key] = os.environ[key]
        repo_root = str(Path(__file__).resolve().parents[2])
        pythonpath = os.getenv("PYTHONPATH")
        env["PYTHONPATH"] = (
            f"{repo_root}{os.pathsep}{pythonpath}" if pythonpath else repo_root
        )
        return env

    _DEBUG_PROTECTED_MODEL_ENV_KEYS = frozenset(
        {
            "ARK_API_KEY",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "CLOUD_PROVIDER",
            "AGENTKIT_CLOUD_PROVIDER",
        }
    )

    def _is_debug_protected_model_env(key: str) -> bool:
        """Keep Runtime env from replacing the Studio model credential bundle."""
        return key.startswith("MODEL_AGENT_") or key in _DEBUG_PROTECTED_MODEL_ENV_KEYS

    def _read_runner_log_tail(path: PathlibPath, max_chars: int = 6000) -> str:
        try:
            with path.open("rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - max_chars * 4))
                text = f.read().decode("utf-8", "replace")
        except OSError:
            return ""
        return _redact_debug_text(text[-max_chars:].strip())

    def _runner_log_detail(
        prefix: str,
        stdout_path: PathlibPath,
        stderr_path: PathlibPath,
    ) -> str:
        parts = [prefix]
        stderr_tail = _read_runner_log_tail(stderr_path)
        stdout_tail = _read_runner_log_tail(stdout_path)
        if stderr_tail:
            parts.append(f"stderr:\n{stderr_tail}")
        if stdout_tail:
            parts.append(f"stdout:\n{stdout_tail}")
        if len(parts) == 1:
            parts.append("No runner logs were captured.")
        return "\n\n".join(parts)

    def _unexpected_debug_error_detail(prefix: str, exc: Exception) -> str:
        """Log an unexpected error and return a safe, traceable UI summary."""
        error_id = secrets.token_hex(4)
        message = _redact_debug_text(str(exc).strip()) or "No error message"
        logger.exception(
            "Generated-agent debug error %s (%s): %s",
            error_id,
            type(exc).__name__,
            message,
        )
        return (
            f"{prefix}（错误 ID：{error_id}）\n"
            f"异常类型：{type(exc).__name__}\n"
            "详细信息已记录在 Studio 服务端日志中。"
        )

    def _test_run_log_detail(run: _GeneratedAgentTestRun, prefix: str) -> str:
        temp_dir = PathlibPath(run.temp_dir)
        return _runner_log_detail(
            prefix,
            temp_dir / "runner.stdout.log",
            temp_dir / "runner.stderr.log",
        )

    def _runner_response_error_detail(
        run: _GeneratedAgentTestRun,
        operation: str,
        status_code: int,
        response_text: str,
    ) -> str:
        response_detail = _redact_debug_text(response_text.strip())
        prefix = f"{operation}失败（临时运行环境返回 HTTP {status_code}）"
        if response_detail and response_detail.lower() != "internal server error":
            prefix += f"\n响应：{response_detail[:2000]}"
        return _test_run_log_detail(run, prefix)

    def _http_policy_error(exc: Exception) -> HTTPException:
        return HTTPException(status_code=400, detail=str(exc))

    def _skill_version_attr(resp: object, *names: str) -> str:
        for name in names:
            value = getattr(resp, name, None)
            if value:
                return str(value)
        return ""

    def _read_skill_md_from_zip(zip_path: Path, skill_id: str) -> str:
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                candidates = [
                    info
                    for info in archive.infolist()
                    if (
                        not info.is_dir()
                        and not _is_macos_metadata(info.filename)
                        and info.filename.lower().endswith("skill.md")
                        and not info.filename.startswith(("/", "\\"))
                        and ".." not in Path(info.filename).parts
                    )
                ]
                if not candidates:
                    raise HTTPException(
                        status_code=404,
                        detail="Skill version package has no SKILL.md content",
                    )
                chosen = sorted(
                    candidates,
                    key=lambda info: (len(Path(info.filename).parts), info.filename),
                )[0]
                raw = archive.read(chosen)
        except HTTPException:
            raise
        except zipfile.BadZipFile as e:
            raise HTTPException(
                status_code=502,
                detail=f"Skill version package for {skill_id} is not a valid zip",
            ) from e
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                pass
        raise HTTPException(
            status_code=502,
            detail=f"Skill version package for {skill_id} has unsupported encoding",
        )

    def _skill_md_from_version_response(
        *,
        space_id: str,
        skill_id: str,
        version: str | None,
        resp: object,
    ) -> str:
        skill_md = _skill_version_attr(resp, "skill_md", "skillMd")
        if skill_md:
            return skill_md
        bucket_name = _skill_version_attr(resp, "bucket_name", "bucketName")
        tos_path = _skill_version_attr(resp, "tos_path", "tosPath", "path")
        if not bucket_name or not tos_path:
            raise HTTPException(
                status_code=404, detail="Skill version has no SKILL.md content"
            )
        from veadk.skills.materializer import _download_legacy_skill_space_skill
        from veadk.skills.skill import Skill as VeADKSkill

        remote_skill = VeADKSkill(
            name=_skill_version_attr(resp, "name") or skill_id,
            description=_skill_version_attr(resp, "description"),
            path=tos_path,
            skill_space_id=space_id,
            bucket_name=bucket_name,
            id=skill_id,
            version_id=version or _skill_version_attr(resp, "version"),
        )
        with tempfile.TemporaryDirectory(prefix="veadk_skillspace_") as temp_dir:
            zip_path = Path(temp_dir) / "skill.zip"
            if not _download_legacy_skill_space_skill(remote_skill, zip_path):
                raise HTTPException(
                    status_code=502,
                    detail="Failed to download SkillSpace skill package",
                )
            return _read_skill_md_from_zip(zip_path, skill_id)

    def _skill_files_from_version_response(
        *,
        space_id: str,
        skill_id: str,
        version: str | None,
        resp: object,
        folder: str,
        region: str | None = None,
    ) -> str | list[GeneratedFile]:
        skill_md = _skill_version_attr(resp, "skill_md", "skillMd")
        bucket_name = _skill_version_attr(resp, "bucket_name", "bucketName")
        tos_path = _skill_version_attr(resp, "tos_path", "tosPath", "path")
        if not bucket_name or not tos_path:
            if skill_md:
                return skill_md
            raise HTTPException(
                status_code=404, detail="Skill version has no SKILL.md content"
            )
        from veadk.skills.materializer import _download_legacy_skill_space_skill
        from veadk.skills.skill import Skill as VeADKSkill

        remote_skill = VeADKSkill(
            name=_skill_version_attr(resp, "name") or skill_id,
            description=_skill_version_attr(resp, "description"),
            path=tos_path,
            skill_space_id=space_id,
            bucket_name=bucket_name,
            id=skill_id,
            version_id=version or _skill_version_attr(resp, "version"),
        )
        with tempfile.TemporaryDirectory(prefix="veadk_skillspace_") as temp_dir:
            zip_path = Path(temp_dir) / "skill.zip"
            if not _download_legacy_skill_space_skill(
                remote_skill,
                zip_path,
                region=region,
                raise_on_error=True,
            ):
                if skill_md:
                    return skill_md
                raise HTTPException(
                    status_code=502,
                    detail="Failed to download SkillSpace skill package",
                )
            return _files_from_zip(
                zip_path.read_bytes(),
                folder,
                f"SkillSpace skill {skill_id}",
                ignore_binary=True,
            )

    async def _resolve_skillspace_skill_materialization(
        space_id: str,
        skill_id: str,
        version: str | None,
        region: str | None = None,
        *,
        skill_space_name: str | None = None,
        skill_name: str | None = None,
    ) -> str | list[GeneratedFile]:
        resolved_region = _coerce_cloud_region(region)
        client = _skills_client(resolved_region)
        try:
            resp = await asyncio.to_thread(
                resolve_skill_response,
                client,
                space_id=space_id,
                skill_id=skill_id,
                version=version,
                skill_space_name=skill_space_name,
                skill_name=skill_name,
            )
        except Exception as error:
            logger.error(
                f"Skill detail lookup ({skill_id}@{version}) error for region "
                f"{resolved_region}: {error}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=502,
                detail=f"SkillSpaces API error: {error}",
            ) from error
        try:
            return await asyncio.to_thread(
                _skill_files_from_version_response,
                space_id=space_id,
                skill_id=skill_id,
                version=version,
                resp=resp,
                folder=skill_name or skill_id,
                region=resolved_region,
            )
        except HTTPException:
            raise
        except Exception as error:
            logger.error(
                f"Skill package download ({skill_id}@{version}) error for region "
                f"{resolved_region}: {error}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=502,
                detail=f"SkillSpace package download error: {error}",
            ) from error

    def _draft_for_debug_run(draft: AgentDraft) -> AgentDraft:
        """Return a debug-safe draft by omitting stdio MCP tools recursively."""
        return draft.model_copy(
            deep=True,
            update={
                "mcpTools": [
                    tool for tool in draft.mcpTools if tool.transport != "stdio"
                ],
                "subAgents": [
                    _draft_for_debug_run(sub_agent) for sub_agent in draft.subAgents
                ],
            },
        )

    async def _generate_project_and_draft_from_request(
        data: dict,
        *,
        debug: bool,
    ) -> tuple[GeneratedProject, AgentDraft]:
        try:
            if debug:
                req = GeneratedAgentTestRunRequest.model_validate(data)
            else:
                req = GeneratedAgentProjectRequest.model_validate(data)
            draft = normalize_and_validate_draft(req.draft)
            if debug:
                draft = _draft_for_debug_run(draft)
                validate_debug_policy(
                    draft,
                    allow_local_runtime_resources=(
                        generated_agent_test_run_allows_local_resources
                    ),
                    managed_cloud_provider=provider,
                )
                draft = await resolve_debug_mcp_endpoints(draft)
            else:
                validate_project_policy(draft)
            project = generate_project_from_draft(draft)
            await materialize_selected_skills(
                draft,
                project,
                resolve_skillspace_detail=_resolve_skillspace_skill_materialization,
            )
            return project, draft
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors()) from e
        except DebugPolicyError as e:
            raise _http_policy_error(e) from e
        except McpDebugConnectionError as e:
            raise HTTPException(status_code=422, detail=str(e)) from None

    async def _generate_project_from_request(
        data: dict,
        *,
        debug: bool,
    ) -> GeneratedProject:
        project, _ = await _generate_project_and_draft_from_request(
            data,
            debug=debug,
        )
        return project

    def _write_generated_project(project: GeneratedProject, temp_dir: str) -> str:
        if not project.name:
            raise HTTPException(status_code=400, detail="Agent name is required")
        files = project.files
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        if len(files) > _TEST_RUN_MAX_FILES:
            raise HTTPException(
                status_code=400,
                detail=f"Too many files ({len(files)} > {_TEST_RUN_MAX_FILES})",
            )

        base = PathlibPath(temp_dir).resolve()
        total = 0
        for item in files:
            file_path = item.path
            content = item.content
            if not isinstance(file_path, str) or not file_path.strip():
                raise HTTPException(status_code=400, detail="Invalid file path")
            if not isinstance(content, str):
                raise HTTPException(
                    status_code=400, detail=f"Invalid content: {file_path}"
                )
            encoded = content.encode("utf-8")
            if len(encoded) > _TEST_RUN_MAX_FILE_BYTES:
                raise HTTPException(
                    status_code=400, detail=f"File too large: {file_path}"
                )
            total += len(encoded)
            if total > _TEST_RUN_MAX_TOTAL_BYTES:
                raise HTTPException(status_code=400, detail="Project is too large")

            path_obj = PathlibPath(file_path)
            if path_obj.is_absolute() or "\x00" in file_path:
                raise HTTPException(
                    status_code=400, detail=f"Illegal file path: {file_path}"
                )
            if any(part in ("", ".", "..") for part in path_obj.parts):
                raise HTTPException(
                    status_code=400, detail=f"Illegal file path: {file_path}"
                )

            full = (base / file_path).resolve()
            if not full.is_relative_to(base):
                raise HTTPException(
                    status_code=400, detail=f"Illegal file path: {file_path}"
                )
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")

        agents_dir = base / "agents"
        apps = (
            sorted(
                p.name
                for p in agents_dir.iterdir()
                if p.is_dir() and (p / "agent.py").is_file()
            )
            if agents_dir.is_dir()
            else []
        )
        if project.name in apps:
            app_name = project.name
        elif len(apps) == 1:
            app_name = apps[0]
        else:
            raise HTTPException(
                status_code=400,
                detail="Generated project must contain exactly one agents/<name>/agent.py",
            )

        # ADK imports an app as ``<app_name>.agent``. Names such as ``abc``
        # collide with already-importable Python modules and are then reported
        # by ADK as if the generated root_agent did not exist.
        try:
            conflicts_with_module = importlib.util.find_spec(app_name) is not None
        except (ImportError, AttributeError, ValueError):
            conflicts_with_module = app_name in sys.modules
        if conflicts_with_module:
            debug_app_name = f"veadk_debug_{app_name}"
            (agents_dir / app_name).rename(agents_dir / debug_app_name)
            return debug_app_name
        return app_name

    def _free_local_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    async def _wait_for_runner_ready(
        base_url: str,
        app_name: str,
        proc: subprocess.Popen,
        stdout_path: PathlibPath,
        stderr_path: PathlibPath,
    ) -> None:
        import asyncio

        deadline = time.time() + _TEST_RUN_READY_TIMEOUT
        last_error = ""
        async with httpx.AsyncClient(timeout=2.0) as client:
            while time.time() < deadline:
                if proc.poll() is not None:
                    raise HTTPException(
                        status_code=400,
                        detail=_runner_log_detail(
                            "Debug runner exited before becoming ready "
                            f"(exit code {proc.returncode}).",
                            stdout_path,
                            stderr_path,
                        ),
                    )
                try:
                    res = await client.get(f"{base_url}/list-apps")
                    if res.status_code == 200 and app_name in (res.json() or []):
                        return
                    last_error = f"list-apps returned {res.status_code}"
                except Exception as e:
                    last_error = str(e)
                await asyncio.sleep(0.25)
        raise HTTPException(
            status_code=504,
            detail=_runner_log_detail(
                f"Debug runner did not become ready: {last_error}",
                stdout_path,
                stderr_path,
            ),
        )

    async def _wait_for_debug_harness_sidecar_ready(
        base_url: str,
        plan: Mapping[str, Any],
    ) -> None:
        """Verify the generated app and Runtime APIG expose the same active plan."""

        import asyncio

        expected_hash = str(plan.get("planHash") or "")
        expected_components = {
            str(item) for item in plan.get("effectiveComponents") or []
        }
        gateway_endpoint = os.environ["HARNESS_SIDECAR_APIG_ENDPOINT"].rstrip("/")
        gateway_key = os.environ["HARNESS_SIDECAR_APIG_API_KEY"]
        required_ports = [18787]
        if "mcp_resilience" in expected_components:
            required_ports.append(18788)
        deadline = time.time() + _TEST_RUN_READY_TIMEOUT
        last_stage = "application status"
        async with httpx.AsyncClient(timeout=None) as client:
            while time.time() < deadline:
                try:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        break
                    status_response = await client.get(
                        f"{base_url}/web/harness-sidecar/status",
                        timeout=min(3.0, remaining),
                    )
                    status_payload = status_response.json()
                    if (
                        status_response.status_code != 200
                        or not isinstance(status_payload, Mapping)
                        or status_payload.get("status") not in {"ready", "ok"}
                        or status_payload.get("planHash") != expected_hash
                        or not expected_components.issubset(
                            {
                                str(item)
                                for item in status_payload.get(
                                    "effectiveComponents", []
                                )
                            }
                        )
                    ):
                        last_stage = "application active plan"
                        await asyncio.sleep(0.25)
                        continue
                    gateway_ready = True
                    for port in required_ports:
                        remaining = deadline - time.time()
                        if remaining <= 0:
                            gateway_ready = False
                            break
                        gateway_response = await client.get(
                            f"{gateway_endpoint}/healthz",
                            headers={
                                "Authorization": _agentkit_authorization_header(
                                    gateway_key
                                ),
                                "X-Faas-Proxy-Port": str(port),
                            },
                            timeout=min(3.0, remaining),
                        )
                        if gateway_response.status_code != 200:
                            gateway_ready = False
                            last_stage = f"Runtime APIG port {port}"
                            break
                    if gateway_ready:
                        return
                except (httpx.HTTPError, TypeError, ValueError):
                    last_stage = "Runtime APIG readiness"
                await asyncio.sleep(0.25)
        raise HTTPException(
            status_code=504,
            detail=f"Harness Sidecar 启动检查超时（{last_stage}）。",
        )

    @app.post("/web/generated-agent-projects")
    async def _generate_agent_project(request: Request):
        _require_agent_management(request)
        data = await request.json()
        project = await _generate_project_from_request(data, debug=False)
        return project.model_dump()

    @app.post("/web/github-delivery/source-sync")
    async def _create_github_source_sync(request: Request):
        """Push Studio-generated Agent source to the configured GitHub branch."""
        _require_agent_management(request)
        data = await request.json()
        try:
            from veadk.cli.github_cicd import (
                GitHubCicdError,
                create_github_cicd_pipeline,
            )

            return create_github_cicd_pipeline(
                project=data.get("project") or {},
                github_url=str(data.get("githubUrl") or ""),
                github_token=str(data.get("githubToken") or ""),
                base_branch=str(data.get("baseBranch") or "main"),
                region=str(data.get("region") or "cn-beijing"),
                cloud_provider=str(data.get("cloudProvider") or provider),
            )
        except GitHubCicdError as error:
            raise HTTPException(status_code=400, detail=error.to_response()) from error
        except Exception as error:
            logger.exception("Failed to sync GitHub source")
            raise HTTPException(
                status_code=502,
                detail=_safe_exception_detail(
                    error,
                    secrets=(str(data.get("githubToken") or ""),),
                ),
            ) from error

    @app.post("/web/github-delivery/cicd-pipeline")
    async def _create_github_delivery_cicd_pipeline(request: Request):
        """Create or update the GitHub Actions workflow for Runtime delivery."""
        _require_agent_management(request)
        data = await request.json()
        try:
            from veadk.cli.github_cicd import (
                GitHubCicdError,
                create_github_delivery_cicd_pipeline,
            )

            return create_github_delivery_cicd_pipeline(
                github_url=str(data.get("githubUrl") or ""),
                github_token=str(data.get("githubToken") or ""),
                base_branch=str(data.get("baseBranch") or "main"),
                runtime_name=str(data.get("runtimeName") or ""),
                runtime_id=str(data.get("runtimeId") or ""),
                region=str(data.get("region") or "cn-beijing"),
                cloud_provider=str(data.get("cloudProvider") or provider),
                project_path=str(data.get("projectPath") or "."),
                volcengine_access_key=str(data.get("volcengineAccessKey") or ""),
                volcengine_secret_key=str(data.get("volcengineSecretKey") or ""),
                volcengine_session_token=str(data.get("volcengineSessionToken") or ""),
            )
        except GitHubCicdError as error:
            raise HTTPException(status_code=400, detail=error.to_response()) from error
        except Exception as error:
            logger.exception("Failed to create GitHub delivery CICD pipeline")
            raise HTTPException(
                status_code=502,
                detail=_safe_exception_detail(
                    error,
                    secrets=(
                        str(data.get("githubToken") or ""),
                        str(data.get("volcengineAccessKey") or ""),
                        str(data.get("volcengineSecretKey") or ""),
                        str(data.get("volcengineSessionToken") or ""),
                    ),
                ),
            ) from error

    @app.post("/web/github-delivery/init-main")
    async def _initialize_github_delivery_main(request: Request):
        """Initialize target branch with Agent source and Runtime delivery workflow."""
        _require_agent_management(request)
        data = await request.json()
        try:
            from veadk.cli.github_cicd import (
                GitHubCicdError,
                initialize_github_delivery_main,
            )

            return initialize_github_delivery_main(
                project=data.get("project") or {},
                github_url=str(data.get("githubUrl") or ""),
                github_token=str(data.get("githubToken") or ""),
                base_branch=str(data.get("baseBranch") or "main"),
                runtime_name=str(data.get("runtimeName") or ""),
                runtime_id=str(data.get("runtimeId") or ""),
                region=str(data.get("region") or "cn-beijing"),
                cloud_provider=str(data.get("cloudProvider") or provider),
                project_path=str(data.get("projectPath") or "."),
                volcengine_access_key=str(data.get("volcengineAccessKey") or ""),
                volcengine_secret_key=str(data.get("volcengineSecretKey") or ""),
                volcengine_session_token=str(data.get("volcengineSessionToken") or ""),
            )
        except GitHubCicdError as error:
            raise HTTPException(status_code=400, detail=error.to_response()) from error
        except Exception as error:
            logger.exception("Failed to initialize GitHub delivery main")
            raise HTTPException(
                status_code=502,
                detail=_safe_exception_detail(
                    error,
                    secrets=(
                        str(data.get("githubToken") or ""),
                        str(data.get("volcengineAccessKey") or ""),
                        str(data.get("volcengineSecretKey") or ""),
                        str(data.get("volcengineSessionToken") or ""),
                    ),
                ),
            ) from error

    @app.post("/web/github-delivery/source-sync/cicd")
    async def _attach_github_delivery_cicd_to_source_sync(request: Request):
        """Attach Runtime delivery workflow to an existing source sync branch."""
        _require_agent_management(request)
        data = await request.json()
        try:
            from veadk.cli.github_cicd import (
                GitHubCicdError,
                attach_github_delivery_cicd_pipeline,
            )

            return attach_github_delivery_cicd_pipeline(
                pipeline_id=str(data.get("pipelineId") or ""),
                runtime_name=str(data.get("runtimeName") or ""),
                runtime_id=str(data.get("runtimeId") or ""),
                region=str(data.get("region") or "cn-beijing"),
                cloud_provider=str(data.get("cloudProvider") or provider),
                project_path=str(data.get("projectPath") or "."),
                github_token=str(data.get("githubToken") or ""),
                volcengine_access_key=str(data.get("volcengineAccessKey") or ""),
                volcengine_secret_key=str(data.get("volcengineSecretKey") or ""),
                volcengine_session_token=str(data.get("volcengineSessionToken") or ""),
            )
        except GitHubCicdError as error:
            raise HTTPException(status_code=400, detail=error.to_response()) from error
        except Exception as error:
            logger.exception("Failed to attach GitHub delivery CICD pipeline")
            raise HTTPException(
                status_code=502,
                detail=_safe_exception_detail(
                    error,
                    secrets=(
                        str(data.get("githubToken") or ""),
                        str(data.get("volcengineAccessKey") or ""),
                        str(data.get("volcengineSecretKey") or ""),
                        str(data.get("volcengineSessionToken") or ""),
                    ),
                ),
            ) from error

    @app.get("/web/github-delivery/versions")
    async def _list_github_delivery_versions(
        request: Request,
        runtimeId: str = "",
    ):
        """Return GitHub delivery versions for a Runtime."""
        _require_agent_management(request)
        try:
            from veadk.cli.github_cicd import (
                GitHubCicdError,
                list_github_delivery_versions,
            )

            return list_github_delivery_versions(runtime_id=runtimeId)
        except GitHubCicdError as error:
            raise HTTPException(status_code=400, detail=error.to_response()) from error

    @app.post("/web/github-delivery/rollback-pr")
    async def _create_github_delivery_rollback_pr(request: Request):
        """Create a GitHub rollback PR for a Runtime-bound delivery branch."""
        _require_agent_management(request)
        data = await request.json()
        try:
            from veadk.cli.github_cicd import (
                GitHubCicdError,
                create_github_delivery_rollback_pr,
            )

            return create_github_delivery_rollback_pr(
                runtime_id=str(data.get("runtimeId") or ""),
                target_commit_sha=str(data.get("targetCommitSha") or ""),
                github_token=str(data.get("githubToken") or ""),
            )
        except GitHubCicdError as error:
            raise HTTPException(status_code=400, detail=error.to_response()) from error
        except Exception as error:
            logger.exception("Failed to create GitHub delivery rollback PR")
            raise HTTPException(
                status_code=502,
                detail=_safe_exception_detail(
                    error,
                    secrets=(str(data.get("githubToken") or ""),),
                ),
            ) from error

    @app.get("/web/github-cicd/runtime-binding")
    async def _get_github_cicd_runtime_binding(
        request: Request,
        runtimeId: str = "",
    ):
        """Return the GitHub CI/CD binding for a Runtime, when present."""
        _require_agent_management(request)
        try:
            from veadk.cli.github_cicd import (
                GitHubCicdError,
                get_github_cicd_runtime_binding,
            )

            return get_github_cicd_runtime_binding(runtime_id=runtimeId)
        except GitHubCicdError as error:
            raise HTTPException(status_code=400, detail=error.to_response()) from error

    @app.post("/web/github-cicd/runtime-binding")
    async def _bind_github_cicd_runtime(request: Request):
        """Bind a GitHub CI/CD pipeline record to an AgentKit Runtime."""
        _require_agent_management(request)
        data = await request.json()
        try:
            from veadk.cli.github_cicd import (
                GitHubCicdError,
                bind_github_cicd_runtime,
            )

            return bind_github_cicd_runtime(
                pipeline_id=str(data.get("pipelineId") or ""),
                runtime_id=str(data.get("runtimeId") or ""),
                region=str(data.get("region") or "cn-beijing"),
                cloud_provider=str(data.get("cloudProvider") or provider),
            )
        except GitHubCicdError as error:
            raise HTTPException(status_code=400, detail=error.to_response()) from error

    @app.post("/web/github-cicd/runtime-sync")
    async def _sync_github_cicd_runtime(request: Request):
        """Sync current AgentProject files to the PR bound to a Runtime."""
        _require_agent_management(request)
        data = await request.json()
        try:
            from veadk.cli.github_cicd import (
                GitHubCicdError,
                sync_github_cicd_runtime,
            )

            return sync_github_cicd_runtime(
                runtime_id=str(data.get("runtimeId") or ""),
                project=data.get("project") or {},
                github_token=str(data.get("githubToken") or ""),
            )
        except GitHubCicdError as error:
            raise HTTPException(status_code=400, detail=error.to_response()) from error
        except Exception as error:
            logger.exception("Failed to sync GitHub CI/CD pipeline")
            raise HTTPException(
                status_code=502,
                detail=_safe_exception_detail(
                    error,
                    secrets=(str(data.get("githubToken") or ""),),
                ),
            ) from error

    @app.post("/web/generated-agent-drafts")
    async def _generate_agent_draft(request: Request):
        _require_agent_management(request)
        try:
            payload = GeneratedAgentDraftRequest.model_validate(await request.json())
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=error.errors()) from error

        try:
            return await generate_agent_draft(payload.requirement)
        except TimeoutError as error:
            raise HTTPException(
                status_code=504,
                detail="生成配置超时，请稍后重试。",
            ) from error
        except Exception as error:
            logger.exception("Failed to generate Agent draft from requirement")
            raise HTTPException(
                status_code=502,
                detail=_safe_exception_detail(error),
            ) from error

    @app.post("/web/generated-agent-test-runs")
    async def _create_generated_agent_test_run(request: Request):
        principal = _require_agent_management(request)
        owner_id = principal.owner_id if principal else ""
        _cleanup_expired_test_runs()
        data = await request.json()

        reserved = False
        with _test_runs_lock:
            active_count = sum(
                1 for run in _test_runs.values() if run.owner_id == owner_id
            ) + _test_runs_creating.get(owner_id, 0)
            if active_count >= _TEST_RUN_MAX_ACTIVE:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        "调试环境并发数已达上限 "
                        f"({active_count}/{_TEST_RUN_MAX_ACTIVE})，"
                        "请稍后重试或关闭不再使用的调试页面。"
                    ),
                )
            _test_runs_creating[owner_id] = _test_runs_creating.get(owner_id, 0) + 1
            reserved = True

        temp_dir = ""
        proc = None
        try:
            project, draft = await _generate_project_and_draft_from_request(
                data,
                debug=True,
            )
            sidecar_env: dict[str, str] = {}
            sidecar_plan: dict[str, Any] | None = None
            if draft.harnessSidecar and draft.harnessSidecar.enabled:
                capability = _harness_sidecar_debug_capability()
                if not capability["available"]:
                    raise HTTPException(
                        status_code=409,
                        detail=capability["reason"],
                    )
                try:
                    sidecar_env, sidecar_plan = studio_harness_runtime_env(
                        draft.harnessSidecar,
                        transport="apig_runtime_port",
                    )
                except (HarnessSidecarDependencyError, ValueError) as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error
                sidecar_env.update(
                    {
                        "HARNESS_SIDECAR_APIG_ENDPOINT": os.environ[
                            "HARNESS_SIDECAR_APIG_ENDPOINT"
                        ],
                        "HARNESS_SIDECAR_APIG_API_KEY": os.environ[
                            "HARNESS_SIDECAR_APIG_API_KEY"
                        ],
                    }
                )
                requested_plan_hash = draft.harnessSidecar.planHash or ""
                if (
                    requested_plan_hash
                    and requested_plan_hash != sidecar_plan["planHash"]
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Harness Sidecar 配置已更新，请重新解析后再启动调试。",
                    )
            runtime_envs: dict[str, str] = {}
            runtime_id = str(data.get("runtimeId") or "").strip()
            if runtime_id:
                runtime_region = (
                    str(data.get("runtimeRegion") or "cn-beijing").strip()
                    or "cn-beijing"
                )
                runtime = _authorized_runtime(
                    request,
                    runtime_id,
                    runtime_region,
                    coded_access_error=True,
                )
                runtime_envs = {
                    str(item.key): str(item.value or "")
                    for item in (getattr(runtime, "envs", None) or [])
                    if getattr(item, "key", None)
                    and not _is_debug_protected_model_env(str(item.key))
                }
            temp_dir = tempfile.mkdtemp(prefix="veadk_generated_agent_test_")
            app_name = _write_generated_project(project, temp_dir)
            port = _free_local_port()
            base_url = f"http://127.0.0.1:{port}"
            stdout_path = PathlibPath(temp_dir) / "runner.stdout.log"
            stderr_path = PathlibPath(temp_dir) / "runner.stderr.log"
            cmd = [
                sys.executable,
                "-m",
                "veadk.cli.generated_agent_test_runner",
                "--agents-dir",
                str(PathlibPath(temp_dir) / "agents"),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ]
            runner_env = _safe_runner_env()
            runner_env.update(runtime_envs)
            for key in list(runner_env):
                if key.startswith("HARNESS_"):
                    runner_env.pop(key)
            runner_env.update(sidecar_env)
            runner_env.update(debug_runtime_env_from_draft(draft))
            selected_api_key_id = draft.deployment.modelApiKeyId.strip()
            selected_api_key_name = draft.deployment.modelApiKeyName.strip()

            def _draft_uses_ark_model(node: AgentDraft) -> bool:
                return (
                    node.agentType == "llm" and node.modelSource != "custom"
                ) or any(_draft_uses_ark_model(child) for child in node.subAgents)

            draft_uses_ark = _draft_uses_ark_model(draft)
            if draft_uses_ark and (selected_api_key_id or selected_api_key_name):
                try:
                    runner_env["MODEL_AGENT_API_KEY"] = await asyncio.to_thread(
                        _resolve_ark_model_api_key,
                        api_key_id=selected_api_key_id,
                        api_key_name=selected_api_key_name,
                    )
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail="所选 Ark API Key 不可用，请刷新后重新选择。",
                    ) from e
            runner_env["MODEL_AGENT_API_BASE"] = trusted_debug_model_api_base(
                draft,
                managed_cloud_provider=provider,
            )
            runner_env.pop("MODEL_AGENT_BASE_URL", None)
            runner_env["CLOUD_PROVIDER"] = provider
            runner_env["AGENTKIT_CLOUD_PROVIDER"] = provider
            with stdout_path.open("w", encoding="utf-8") as stdout_file:
                with stderr_path.open("w", encoding="utf-8") as stderr_file:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=temp_dir,
                        env=runner_env,
                        stdout=stdout_file,
                        stderr=stderr_file,
                    )
            await _wait_for_runner_ready(
                base_url,
                app_name,
                proc,
                stdout_path,
                stderr_path,
            )
            if sidecar_plan is not None:
                await _wait_for_debug_harness_sidecar_ready(base_url, sidecar_plan)

            run_id = "tr_" + secrets.token_urlsafe(18)
            expires_at = time.time() + generated_agent_test_run_ttl
            run = _GeneratedAgentTestRun(
                run_id=run_id,
                app_name=app_name,
                temp_dir=temp_dir,
                base_url=base_url,
                process=proc,
                expires_at=expires_at,
                owner_id=owner_id,
                plan_hash=(sidecar_plan or {}).get("planHash", ""),
            )
            with _test_runs_lock:
                _test_runs[run_id] = run
            return {
                "runId": run_id,
                "appName": app_name,
                "expiresAt": int(expires_at),
                "planHash": run.plan_hash,
            }
        except Exception as exc:
            if proc is not None:
                _terminate_test_run(
                    _GeneratedAgentTestRun("", "", temp_dir, "", proc, 0, "")
                )
            else:
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(
                status_code=500,
                detail=_unexpected_debug_error_detail(
                    "创建调试环境失败",
                    exc,
                ),
            ) from exc
        finally:
            if reserved:
                with _test_runs_lock:
                    creating_count = max(
                        0,
                        _test_runs_creating.get(owner_id, 0) - 1,
                    )
                    if creating_count:
                        _test_runs_creating[owner_id] = creating_count
                    else:
                        _test_runs_creating.pop(owner_id, None)

    @app.post("/web/generated-agent-test-runs/{run_id}/sessions")
    async def _create_generated_agent_test_session(run_id: str, request: Request):
        run = _get_test_run(run_id, request)
        data = await request.json()
        user_id = (data.get("userId") or "test_user").strip() or "test_user"
        url = (
            f"{run.base_url}/apps/{run.app_name}/users/"
            f"{quote(user_id, safe='')}/sessions"
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json={})
        except httpx.HTTPError as exc:
            detail = _unexpected_debug_error_detail(
                "连接临时运行环境以创建会话时失败",
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail=_test_run_log_detail(run, detail),
            ) from exc
        if res.status_code >= 400:
            raise HTTPException(
                status_code=res.status_code,
                detail=_runner_response_error_detail(
                    run,
                    "创建调试会话",
                    res.status_code,
                    res.text,
                ),
            )
        try:
            return res.json()
        except ValueError as exc:
            detail = _unexpected_debug_error_detail(
                "解析临时运行环境的会话响应时失败",
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail=_test_run_log_detail(run, detail),
            ) from exc

    @app.post("/web/generated-agent-test-runs/{run_id}/run_sse")
    async def _run_generated_agent_test_sse(run_id: str, request: Request):
        from fastapi.responses import StreamingResponse

        run = _get_test_run(run_id, request)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Invalid run_sse payload")
        payload["app_name"] = run.app_name

        async def _stream():
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        "POST",
                        f"{run.base_url}/run_sse",
                        json=payload,
                        timeout=None,
                    ) as res:
                        if res.status_code >= 400:
                            text = (await res.aread()).decode("utf-8", "replace")
                            detail = _runner_response_error_detail(
                                run,
                                "调试对话",
                                res.status_code,
                                text,
                            )
                            logger.warning(
                                "test-run run_sse %s (%s): %s",
                                res.status_code,
                                run.base_url,
                                detail[:500],
                            )
                            err = json.dumps(
                                {
                                    "error": detail,
                                    "status_code": res.status_code,
                                },
                                ensure_ascii=False,
                            )
                            yield f"data: {err}\n\n"
                            return
                        async for chunk in res.aiter_bytes():
                            yield chunk
            except httpx.HTTPError as exc:
                detail = _unexpected_debug_error_detail(
                    "连接临时运行环境进行调试对话时失败",
                    exc,
                )
                detail = _test_run_log_detail(run, detail)
                err = json.dumps({"error": detail}, ensure_ascii=False)
                yield f"data: {err}\n\n"

        return StreamingResponse(_stream(), media_type="text/event-stream")

    @app.get("/web/generated-agent-test-runs/{run_id}/trace/session/{session_id}")
    async def _get_generated_agent_test_trace(
        run_id: str,
        session_id: str,
        request: Request,
    ):
        run = _get_test_run(run_id, request)
        url = (
            f"{run.base_url}/dev/apps/{quote(run.app_name, safe='')}"
            f"/debug/trace/session/{quote(session_id, safe='')}"
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url)
        except httpx.HTTPError as exc:
            detail = _unexpected_debug_error_detail(
                "连接临时运行环境以读取调用链路时失败",
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail=_test_run_log_detail(run, detail),
            ) from exc
        if res.status_code >= 400:
            raise HTTPException(
                status_code=res.status_code,
                detail=_runner_response_error_detail(
                    run,
                    "读取调用链路",
                    res.status_code,
                    res.text,
                ),
            )
        try:
            spans = res.json()
        except ValueError as exc:
            detail = _unexpected_debug_error_detail(
                "解析临时运行环境的调用链路响应时失败",
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail=_test_run_log_detail(run, detail),
            ) from exc
        if not isinstance(spans, list):
            raise HTTPException(status_code=502, detail="调用链路响应格式无效")
        return spans

    @app.delete("/web/generated-agent-test-runs/{run_id}")
    async def _delete_generated_agent_test_run(run_id: str, request: Request):
        _get_test_run(run_id, request)
        with _test_runs_lock:
            run = _test_runs.pop(run_id, None)
        if run is not None:
            _terminate_test_run(run)
        return {"success": True}

    import threading as _threading

    _deploy_lock = _threading.Lock()
    _deploy_tasks_lock = _threading.Lock()
    _deploy_tasks: dict[str, dict[str, Any]] = {}

    def _delete_agentkit_runtime(runtime_id: str, region: str) -> None:
        """Delete one AgentKit Runtime through the control plane."""
        from agentkit.sdk.runtime import types as _rt
        from agentkit.sdk.runtime.client import AgentkitRuntimeClient

        ak, sk, token = _resolve_ve_credentials()
        client = AgentkitRuntimeClient(
            access_key=ak,
            secret_key=sk,
            session_token=token or "",
            region=region,
        )
        client.delete_runtime(_rt.DeleteRuntimeRequest(RuntimeId=runtime_id))

    def _set_agentkit_runtime_instance_range(
        runtime_id: str,
        region: str,
        min_instance: int,
        max_instance: int,
    ) -> None:
        """Set a Runtime instance range and publish the configuration update."""
        from agentkit.sdk.runtime import types as _rt
        from agentkit.sdk.runtime.client import AgentkitRuntimeClient

        ak, sk, token = _resolve_ve_credentials()
        client = AgentkitRuntimeClient(
            access_key=ak,
            secret_key=sk,
            session_token=token or "",
            region=region,
        )
        client.update_runtime(
            _rt.UpdateRuntimeRequest(
                RuntimeId=runtime_id,
                MinInstance=min_instance,
                MaxInstance=max_instance,
                ReleaseEnable=True,
            )
        )

    def _destroy_deploy_task_runtime(task: dict[str, Any]) -> bool:
        """Destroy a task's Runtime once, if creation has reached that stage."""
        with _deploy_tasks_lock:
            if not task.get("destroy_on_cancel", True):
                return False
            runtime_id = str(task.get("runtime_id") or "")
            if not runtime_id or task.get("destroyed") or task.get("destroying"):
                return False
            task["destroying"] = True
            region = str(task.get("region") or _default_cloud_region())

        try:
            _delete_agentkit_runtime(runtime_id, region)
        except Exception:
            with _deploy_tasks_lock:
                task["destroying"] = False
            raise

        with _deploy_tasks_lock:
            task["destroying"] = False
            task["destroyed"] = True
        return True

    def _identity_region() -> str:
        return (
            os.getenv("VEIDENTITY_REGION", _default_cloud_region()).strip()
            or _default_cloud_region()
        )

    def _identity_client():
        from veadk.integrations.ve_identity.identity_client import IdentityClient

        ak, sk, token = _resolve_ve_credentials()
        return IdentityClient(
            access_key=ak,
            secret_key=sk,
            session_token=token or "",
            region=_identity_region(),
            provider=provider,
        )

    def _current_studio_identity_ids(client: Any) -> tuple[str, str]:
        current_pool_uid = str(oauth2_user_pool_uid or "").strip()
        if not current_pool_uid and oauth2_user_pool:
            pool = client.get_user_pool(name=oauth2_user_pool)
            if pool:
                current_pool_uid = str(pool[0] or "").strip()

        current_client_uid = str(oauth2_user_pool_client_uid or "").strip()
        if current_pool_uid and not current_client_uid and oauth2_user_pool_client:
            user_pool_client = client.get_user_pool_client(
                current_pool_uid,
                name=oauth2_user_pool_client,
            )
            if user_pool_client:
                current_client_uid = str(user_pool_client[0] or "").strip()
        return current_pool_uid, current_client_uid

    def _user_pool_runtime_authentication(
        authentication: Any,
    ) -> dict[str, Any]:
        if authentication is None:
            return {"runtime_auth_type": "key_auth"}
        if not isinstance(authentication, dict):
            raise HTTPException(
                status_code=400,
                detail="authentication must be an object",
            )

        authentication_type = str(authentication.get("type") or "api_key").strip()
        if authentication_type == "api_key":
            return {"runtime_auth_type": "key_auth"}
        if authentication_type != "user_pool":
            raise HTTPException(
                status_code=400,
                detail="Unsupported deployment authentication type",
            )

        user_pool_uid = str(authentication.get("userPoolUid") or "").strip()
        if not user_pool_uid:
            raise HTTPException(
                status_code=400,
                detail="userPoolUid is required for user-pool authentication",
            )
        client = _identity_client()
        user_pool = client.get_user_pool(uid=user_pool_uid)
        if not user_pool:
            raise HTTPException(
                status_code=400,
                detail="Selected Identity user pool was not found",
            )
        resolved_uid, domain = user_pool
        issuer = str(domain or "").strip().rstrip("/")
        if not issuer:
            raise HTTPException(
                status_code=400,
                detail="Selected Identity user pool has no domain",
            )
        if not issuer.startswith(("https://", "http://")):
            issuer = f"https://{issuer}"

        current_pool_uid, current_client_uid = _current_studio_identity_ids(client)
        allowed_clients: list[str] = []
        if str(resolved_uid) == current_pool_uid:
            if not current_client_uid:
                raise HTTPException(
                    status_code=400,
                    detail="Current Studio user-pool client UID is unavailable",
                )
            allowed_clients.append(current_client_uid)
        return {
            "runtime_auth_type": "custom_jwt",
            "runtime_jwt_discovery_url": (f"{issuer}/.well-known/openid-configuration"),
            "runtime_jwt_allowed_clients": allowed_clients,
        }

    def _existing_runtime_authentication(runtime: Any) -> dict[str, Any]:
        authorizer = getattr(runtime, "authorizer_configuration", None)
        custom_jwt = (
            getattr(authorizer, "custom_jwt_authorizer", None) if authorizer else None
        )
        if custom_jwt:
            return {
                "runtime_auth_type": "custom_jwt",
                "runtime_jwt_discovery_url": str(
                    getattr(custom_jwt, "discovery_url", "") or ""
                ),
                "runtime_jwt_allowed_clients": list(
                    getattr(custom_jwt, "allowed_clients", None) or []
                ),
            }
        return {"runtime_auth_type": "key_auth"}

    @app.post("/web/cancel-deploy-agentkit")
    async def _cancel_deploy_to_agentkit(request: Request):
        """Cancel a deployment and destroy any Runtime it already created."""
        principal = _require_agent_management(request)
        data = await request.json()
        task_id = str(data.get("taskId") or "").strip()
        if not task_id:
            raise HTTPException(status_code=400, detail="taskId is required")
        with _deploy_tasks_lock:
            task = _deploy_tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Deployment task not found")
        if _request_role(request) != StudioRole.ADMIN and (
            principal is None or task.get("owner_id") != principal.owner_id
        ):
            raise HTTPException(status_code=404, detail="Deployment task not found")

        task["cancel_event"].set()
        process = task.get("process")
        if process is not None and process.poll() is None:
            process.terminate()
        try:
            destroyed = _destroy_deploy_task_runtime(task)
        except Exception as e:
            logger.error("cancel deployment cleanup failed: %s", e, exc_info=True)
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {
            "success": True,
            "runtimeId": str(task.get("runtime_id") or ""),
            "destroyed": destroyed or bool(task.get("destroyed")),
        }

    def _validate_harness_sidecar_project_files(
        files: list[Any],
        *,
        enabled: bool,
    ) -> None:
        by_path = {
            str(item.get("path") or ""): str(item.get("content") or "")
            for item in files
            if isinstance(item, dict)
        }
        all_source = "\n".join(by_path.values())
        private_markers = (
            "bytedance-agentkit-harness-sidecar",
            "bytedance_agentkit_harness_sidecar",
        )
        if any(marker in all_source for marker in private_markers):
            raise HTTPException(
                status_code=422,
                detail="生成项目不得包含 Harness Sidecar 私有 Runtime 包。",
            )
        requirements = by_path.get("requirements.txt", "")
        agent_sources = "\n".join(
            content
            for path, content in by_path.items()
            if path.startswith("agents/") and path.endswith("/agent.py")
        )
        app_source = by_path.get("app.py", "")
        has_sidecar_source = any(
            (
                "veadk-python[harness-sidecar]" in requirements,
                "HarnessExtension.from_env()" in agent_sources,
                "plugins=harness_extension.plugins()" in agent_sources,
                "harness_extension=harness_extension" in app_source,
            )
        )
        if enabled and not all(
            (
                "veadk-python[harness-sidecar]" in requirements,
                "HarnessExtension.from_env()" in agent_sources,
                "plugins=harness_extension.plugins()" in agent_sources,
                "harness_extension=harness_extension" in app_source,
            )
        ):
            raise HTTPException(
                status_code=409,
                detail="Harness Sidecar 配置与生成项目不一致，请重新生成发布快照。",
            )
        if not enabled and has_sidecar_source:
            raise HTTPException(
                status_code=409,
                detail="普通 Runtime 配置与生成项目不一致，请重新生成发布快照。",
            )

    def _redact_managed_artifact_text(text: str, artifacts: list[str]) -> str:
        redacted = str(text)
        for artifact in artifacts:
            if artifact:
                redacted = redacted.replace(artifact, "<managed-sidecar-artifact>")
        return redacted

    @app.post("/web/deploy-agentkit")
    async def _deploy_to_agentkit(request: Request):
        """Deploy to AgentKit, streaming per-stage progress as Server-Sent Events.

        Body: {name, files:[{path,content}], config:{region,projectName}}.
        While building/deploying, streams `data: {level, phase, message, pct?}`
        frames (phase = build|deploy|publish|evaluation); ends with a terminal
        `data: {done:true, success, agentName?, runtimeName?, url?, apikey?,
        runtimeId?, consoleUrl?, error?, phase?}` frame. `agentName` is the ADK
        app name while `runtimeName` is the platform Runtime resource name.
        Ordinary deployments keep the AgentKit Python SDK path. Managed Harness
        Sidecar deployments use the configured AgentKit CLI structured release
        path. Both paths tag the Runtime with the deploying user.
        """
        import tempfile
        import shutil
        import queue as _queue
        import json as _json
        import asyncio
        import yaml as _yaml
        from pathlib import Path as PathlibPath
        from contextlib import contextmanager

        principal = _require_agent_management(request)
        data = await request.json()
        agent_name = (data.get("name") or "").strip()
        runtime_id = (data.get("runtimeId") or "").strip()
        requested_runtime_name = (data.get("runtimeName") or agent_name).strip()
        files = data.get("files", [])
        migration_task_id = str(data.get("migrationTaskId") or "").strip()
        source = data.get("source") or (
            {"kind": "migration", "migrationId": migration_task_id}
            if migration_task_id
            else {"kind": "inlineFiles"}
        )
        if not isinstance(source, dict) or source.get("kind") not in {
            "inlineFiles",
            "migration",
            "intelligentDevelopment",
        }:
            raise HTTPException(status_code=400, detail="Invalid deployment source")
        trusted_intelligent_source = source.get("kind") == "intelligentDevelopment"
        config = data.get("config", {})
        task_id = str(data.get("taskId") or f"deploy-{id(request)}").strip()
        create_evaluation_sets = data.get("createEvaluationSets", True)
        author = principal.display_name if principal else ""
        owner_id = principal.owner_id if principal else ""
        if not agent_name:
            raise HTTPException(status_code=400, detail="Agent name is required")
        if trusted_intelligent_source and (
            len(agent_name) < 4
            or len(agent_name) > 64
            or re.fullmatch(r"[A-Za-z0-9_-]+", agent_name) is None
        ):
            raise HTTPException(status_code=400, detail="Invalid Runtime name")
        if trusted_intelligent_source:
            if files:
                raise HTTPException(
                    status_code=400,
                    detail="Trusted deployment source does not accept browser files",
                )
            if runtime_id:
                raise HTTPException(
                    status_code=400,
                    detail="Intelligent development source can only create a new Runtime",
                )
        elif source.get("kind") == "migration":
            if not migration_task_id:
                raise HTTPException(
                    status_code=400,
                    detail="Migration deployment source is invalid",
                )
        elif not files:
            raise HTTPException(status_code=400, detail="No files provided")
        if not isinstance(create_evaluation_sets, bool):
            raise HTTPException(
                status_code=400,
                detail="createEvaluationSets must be a boolean",
            )
        if provider == "byteplus":
            create_evaluation_sets = False

        min_instance = data.get("minInstance", 1)
        max_instance = data.get("maxInstance", 5)
        if (
            isinstance(min_instance, bool)
            or isinstance(max_instance, bool)
            or not isinstance(min_instance, int)
            or not isinstance(max_instance, int)
            or min_instance < 1
            or max_instance < 1
        ):
            raise HTTPException(
                status_code=400,
                detail="Runtime instance range must use positive integers",
            )
        if min_instance > max_instance:
            raise HTTPException(
                status_code=400,
                detail="Runtime minInstance cannot exceed maxInstance",
            )
        try:
            sidecar_intent = normalize_studio_harness_intent(data.get("harnessSidecar"))
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        sidecar_enabled = sidecar_intent.enabled
        sidecar_cli_config: dict[str, Any] = {}
        sidecar_plan: dict[str, Any] | None = None
        sidecar_base_image = ""
        sidecar_cli_runtime_env: dict[str, str] = {}
        if sidecar_enabled:
            capability = _harness_sidecar_deployment_capability()
            if not capability["available"]:
                raise HTTPException(status_code=409, detail=capability["reason"])
            if provider != "volcengine":
                raise HTTPException(
                    status_code=409,
                    detail="Harness Sidecar 首期仅支持 Volcengine。",
                )
            if min_instance != 1 or max_instance != 1:
                raise HTTPException(
                    status_code=409,
                    detail="Harness Sidecar 首期仅支持 Runtime 单实例 1～1。",
                )
            try:
                sidecar_cli_config, sidecar_plan = studio_harness_deployment_config(
                    sidecar_intent
                )
            except (HarnessSidecarDependencyError, ValueError) as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            if (
                sidecar_intent.plan_hash
                and sidecar_intent.plan_hash != sidecar_plan.get("planHash")
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Harness Sidecar 配置已更新，请重新解析后再部署。",
                )
            sidecar_base_image = os.getenv(
                "VEADK_STUDIO_HARNESS_SIDECAR_BASE_IMAGE",
                "",
            ).strip()
        _validate_harness_sidecar_project_files(files, enabled=sidecar_enabled)
        needs_instance_update = (
            not sidecar_enabled
            and not runtime_id
            and (min_instance != 1 or max_instance != 5)
        )

        region = config.get("region") or _default_cloud_region()
        project_name = config.get("projectName", "default")
        if sidecar_enabled and region not in _managed_sidecar_regions():
            raise HTTPException(
                status_code=409,
                detail=f"Harness Sidecar 当前不支持地域 {region}。",
            )
        try:
            from frontend.server.deployment_resources import (
                DeploymentResourceService,
                ManagedSidecarRegistryError,
                agentkit_code_pipeline_resources,
                deployment_resource_tags,
                deployment_resources_from_tags,
            )

            deployment_resource_service = DeploymentResourceService(
                provider, region, _resolve_ve_credentials()
            )
            deployment_resource_config = {}
            deployment_resource_tag_values: dict[str, str] = {}
            if not runtime_id:
                deployment_resource_config = await asyncio.to_thread(
                    deployment_resource_service.resolve_deployment_config,
                    data.get("resources"),
                )
                deployment_resource_tag_values = deployment_resource_tags(
                    data.get("resources")
                )
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.exception("resolve deployment resources failed: %s", e)
            raise HTTPException(status_code=502, detail=str(e)) from e
        existing_runtime = None
        if runtime_id:
            try:
                (
                    update_capability,
                    existing_runtime,
                ) = await _runtime_update_capability_details(
                    request,
                    runtime_id=runtime_id,
                    region=region,
                    app_name=str(data.get("appName") or agent_name).strip(),
                )
                if not update_capability["canUpdate"]:
                    raise HTTPException(
                        status_code=409,
                        detail=update_capability["reason"],
                    )
                tagged_resources = deployment_resources_from_tags(
                    _runtime_tags(existing_runtime)
                )
                if tagged_resources is not None:
                    deployment_resource_config = await asyncio.to_thread(
                        deployment_resource_service.resolve_deployment_config,
                        tagged_resources,
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error("resolve update runtime failed: %s", e, exc_info=True)
                raise HTTPException(status_code=502, detail=str(e)) from e
        if sidecar_enabled:
            try:
                deployment_resource_config = await asyncio.to_thread(
                    deployment_resource_service.anchor_managed_sidecar_registry,
                    sidecar_base_image,
                    deployment_resource_config,
                )
            except ManagedSidecarRegistryError as e:
                raise HTTPException(status_code=409, detail=str(e)) from e
        runtime_authentication = (
            _existing_runtime_authentication(existing_runtime)
            if existing_runtime is not None
            else _user_pool_runtime_authentication(data.get("authentication"))
        )
        if (
            sidecar_enabled
            and runtime_authentication.get("runtime_auth_type") != "key_auth"
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Harness Sidecar 当前要求 Runtime 使用 API Key 鉴权，"
                    "以完成 APIG 固定端口和 active plan 的发布验收。"
                ),
            )
        # Network config (advanced): optional VPC/private networking.
        # Shape: { mode: "public"|"private"|"both", vpc_id?, subnet_ids?, enable_shared_internet_access? }
        # When absent or mode=public, use the default public endpoint.
        net_cfg = (
            config.get("network") if isinstance(config.get("network"), dict) else {}
        )
        runtime_network: dict | None = None
        if net_cfg:
            mode = str(net_cfg.get("mode") or "").strip().lower()
            if mode and mode != "public":
                runtime_network = dict(net_cfg)
        im_config: dict[str, Any] = (
            data.get("im") if isinstance(data.get("im"), dict) else {}
        )
        raw_feishu_config = im_config.get("feishu")
        feishu_config: dict[str, Any] = (
            raw_feishu_config if isinstance(raw_feishu_config, dict) else {}
        )
        feishu_enabled = bool(feishu_config.get("enabled"))
        requested_envs = data.get("envs") if isinstance(data.get("envs"), list) else []
        requested_runtime_envs: dict[str, str] = {}
        for item in requested_envs:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            if not key.replace("_", "").isalnum() or key[0].isdigit():
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid environment variable name: {key}",
                )
            if key in _RESERVED_RUNTIME_ENV_KEYS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Reserved runtime environment variable: {key}",
                )
            requested_runtime_envs[key] = str(item.get("value") or "")
        extra_runtime_envs = {
            key: value
            for key, value in requested_runtime_envs.items()
            if not key.startswith("TOOL_FEISHU_CHANNEL_")
        }
        feishu_app_id = (
            requested_runtime_envs.get("FEISHU_APP_ID", "").strip()
            or requested_runtime_envs.get("TOOL_FEISHU_CHANNEL_APP_ID", "").strip()
            or os.getenv("FEISHU_APP_ID", "").strip()
        )
        feishu_app_secret = (
            requested_runtime_envs.get("FEISHU_APP_SECRET", "").strip()
            or requested_runtime_envs.get("TOOL_FEISHU_CHANNEL_APP_SECRET", "").strip()
            or os.getenv("FEISHU_APP_SECRET", "").strip()
        )
        if feishu_enabled and (not feishu_app_id or not feishu_app_secret):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Feishu Channel is enabled but FEISHU_APP_ID "
                    "/ FEISHU_APP_SECRET are missing."
                ),
            )

        @contextmanager
        def _agentkit_sdk_credential_env():
            """Expose provider credentials only while AgentKit SDK deploys.

            The deployed Studio reads temporary IAM credentials from VeFaaS at
            runtime. AgentKit SDK's template renderer reads provider credentials
            from process env, so bridge the IAM creds into env for the launch
            call without copying them into the agent runtime environment.
            """
            if provider != "byteplus":
                yield
                return

            keys = (
                "BYTEPLUS_ACCESS_KEY",
                "BYTEPLUS_SECRET_KEY",
                "BYTEPLUS_SESSION_TOKEN",
                "VOLCENGINE_ACCESS_KEY",
                "VOLCENGINE_SECRET_KEY",
                "VOLCENGINE_SESSION_TOKEN",
                "VOLC_SESSIONTOKEN",
            )
            original = {key: os.environ.get(key) for key in keys}
            ak, sk, token = _resolve_ve_credentials()
            try:
                os.environ["BYTEPLUS_ACCESS_KEY"] = ak
                os.environ["BYTEPLUS_SECRET_KEY"] = sk
                os.environ["VOLCENGINE_ACCESS_KEY"] = ak
                os.environ["VOLCENGINE_SECRET_KEY"] = sk
                if token:
                    os.environ["BYTEPLUS_SESSION_TOKEN"] = token
                    os.environ["VOLCENGINE_SESSION_TOKEN"] = token
                    os.environ["VOLC_SESSIONTOKEN"] = token
                else:
                    for key in (
                        "BYTEPLUS_SESSION_TOKEN",
                        "VOLCENGINE_SESSION_TOKEN",
                        "VOLC_SESSIONTOKEN",
                    ):
                        os.environ.pop(key, None)
                yield
            finally:
                for key, value in original.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        # Materialize one validated source tree. Migration source is resolved
        # server-side from the caller-owned Session; browser files are ignored.
        from frontend.server.deployment_source import (
            DeploymentSourceError,
            write_inline_source,
        )
        from frontend.server.intelligent_development_source import (
            IntelligentDevelopmentSourceIntegrityError,
            IntelligentDevelopmentSourceNotFound,
            IntelligentDevelopmentSourceStale,
        )

        temp_dir = tempfile.mkdtemp(prefix=f"agentkit_deploy_{agent_name}_")
        base = PathlibPath(temp_dir).resolve()
        try:
            if source.get("kind") == "migration":
                entry_point = await asyncio.to_thread(
                    migration_service.materialize_deployment,
                    migration_task_id,
                    owner_id or "local",
                    base,
                )
                trusted_agent_name = agent_name
            elif trusted_intelligent_source:
                from frontend.server.intelligent_development_source import (
                    materialize_intelligent_development_source,
                )

                materialized = await materialize_intelligent_development_source(
                    base,
                    source,
                    owner_id=owner_id,
                    service=intelligent_development_service,
                )
                entry_point = materialized.entry_point
                trusted_agent_name = materialized.agent_name
            else:
                entry_point = write_inline_source(base, files)
                trusted_agent_name = agent_name
        except MigrationError as error:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.warning(
                "migration deployment source rejected task_id=%s code=%s",
                migration_task_id,
                error.code,
            )
            raise HTTPException(
                status_code=error.status_code,
                detail=str(error),
            ) from error
        except IntelligentDevelopmentSourceNotFound as error:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=404, detail=str(error)) from error
        except IntelligentDevelopmentSourceStale as error:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=409, detail=str(error)) from error
        except IntelligentDevelopmentSourceIntegrityError as error:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=502, detail=str(error)) from error
        except DeploymentSourceError as error:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            shutil.rmtree(temp_dir, ignore_errors=True)
            if trusted_intelligent_source:
                raise HTTPException(
                    status_code=502,
                    detail="Trusted deployment source is unavailable",
                ) from error
            raise

        if sidecar_enabled:
            try:
                await asyncio.to_thread(
                    stage_managed_sidecar_veadk_source,
                    base,
                )
            except ManagedSidecarSourceError as error:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.error(
                    "prepare managed Sidecar VeADK source failed: %s",
                    error,
                )
                raise HTTPException(
                    status_code=409,
                    detail="无法准备受管 Harness Sidecar 的 VeADK 公有源码快照。",
                ) from error

        # Collect env vars from the deployer's environment to forward into the
        # created runtime. The AgentKit platform only injects what we pass here,
        # so we explicitly forward the VeADK/Volcengine/tool-related vars the
        # agent needs at boot. User-provided custom model endpoints take priority;
        # official endpoints from the other provider are corrected below.
        runtime_envs = _collect_runtime_envs()
        if existing_runtime is not None:
            for item in getattr(existing_runtime, "envs", None) or []:
                key = str(getattr(item, "key", "") or "").strip()
                if key and key not in _RESERVED_RUNTIME_ENV_KEYS:
                    runtime_envs[key] = str(getattr(item, "value", "") or "")
        for k, v in extra_runtime_envs.items():
            runtime_envs[k] = v
        explicit_model_key_requested = bool(
            extra_runtime_envs.get("MODEL_AGENT_API_KEY", "").strip()
        )
        selected_model_key_requested = bool(
            extra_runtime_envs.get("MODEL_AGENT_API_KEY_ID", "").strip()
            or extra_runtime_envs.get("MODEL_AGENT_API_KEY_NAME", "").strip()
        )
        if not explicit_model_key_requested and (
            selected_model_key_requested
            or not runtime_envs.get("MODEL_AGENT_API_KEY", "").strip()
        ):
            try:
                runtime_envs["MODEL_AGENT_API_KEY"] = await asyncio.to_thread(
                    _resolve_ark_model_api_key,
                    api_key_id=runtime_envs.get("MODEL_AGENT_API_KEY_ID", ""),
                    api_key_name=runtime_envs.get("MODEL_AGENT_API_KEY_NAME", ""),
                )
            except Exception as e:
                if selected_model_key_requested:
                    raise HTTPException(
                        status_code=400,
                        detail="所选 Ark API Key 不可用，请刷新后重新选择。",
                    ) from e
                logger.warning(
                    "Could not auto-resolve MODEL_AGENT_API_KEY for the runtime: "
                    "%s. The deployed agent may fail to start without this key; "
                    "set MODEL_AGENT_API_KEY before deploying.",
                    e,
                )
        if migration_task_id and not sidecar_enabled:
            _adapt_migration_model_envs(runtime_envs, provider)
        if sidecar_enabled:
            sidecar_env_error = _prepare_managed_sidecar_runtime_envs(
                runtime_envs,
                provider,
                sidecar_plan,
            )
            if sidecar_env_error:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=409,
                    detail=sidecar_env_error,
                )
        if feishu_enabled:
            runtime_envs.update(
                {
                    "FEISHU_APP_ID": feishu_app_id,
                    "FEISHU_APP_SECRET": feishu_app_secret,
                }
            )
        if provider == "byteplus":
            runtime_envs["CLOUD_PROVIDER"] = "byteplus"
            runtime_envs["AGENTKIT_CLOUD_PROVIDER"] = "byteplus"
            runtime_envs["DATABASE_VIKING_REGION"] = (
                DEFAULT_BYTEPLUS_VIKING_MEMORY_REGION
            )
        # Harness settings are platform-owned. Always remove a previous
        # Sidecar deployment's values before either deployment path materializes
        # the next Runtime environment. The CLI adds the authoritative resolved
        # plan back only for Sidecar deployments.
        runtime_envs = {
            key: value
            for key, value in runtime_envs.items()
            if not key.startswith("HARNESS_")
        }
        # TOS build-artifact buckets are region-scoped. The SDK default template
        # ("agentkit-platform-<account_id>") produces a single global name, which
        # collides once a bucket exists in cn-beijing and the user targets
        # cn-shanghai (TOS refuses cross-region reuse). For non-Beijing regions,
        # set a region-suffixed bucket name so each region gets its own
        # auto-created bucket.
        cloud_config: dict = {
            "region": region,
            "project_name": project_name,
            **({"runtime_name": agent_name} if trusted_intelligent_source else {}),
            "image_tag": (
                f"veadk-v{(getattr(existing_runtime, 'current_version_number', 0) or 0) + 1}"
                if existing_runtime is not None
                else "latest"
            ),
            "runtime_envs": runtime_envs,
            "python_version": "3.12",
        }
        cloud_config.update(runtime_authentication)
        if existing_runtime is not None:
            cloud_config.update(
                {
                    "runtime_id": runtime_id,
                    "runtime_name": getattr(existing_runtime, "name", "") or agent_name,
                    "runtime_role_name": getattr(existing_runtime, "role_name", "")
                    or "Auto",
                }
            )
        else:
            # AgentKit auto-generates "<agent>-<random>" when runtime_name is
            # absent or Auto. Always provide an explicit name so Studio keeps
            # Agent and Runtime naming deterministic.
            cloud_config["runtime_name"] = requested_runtime_name or agent_name
            if runtime_network:
                cloud_config["runtime_network"] = runtime_network
        if region and region != "cn-beijing":
            region_suffix = (
                region.split("-", 1)[1] if region.startswith("cn-") else region
            )
            try:
                from agentkit.utils.template_utils import render_template

                with _agentkit_sdk_credential_env():
                    bucket_base = render_template("agentkit-platform-{{account_id}}")
            except Exception as e:
                logger.warning(
                    "Could not resolve account_id for TOS bucket naming: %s; "
                    "falling back to 'agentkit-platform-%s'",
                    e,
                    region_suffix,
                )
                bucket_base = "agentkit-platform"
            cloud_config["tos_bucket"] = f"{bucket_base}-{region_suffix}"
            if provider == "byteplus":
                cloud_config["cr_instance_name"] = bucket_base
        cloud_config.update(deployment_resource_config)

        deployment_runtime_name = (
            str(getattr(existing_runtime, "name", "") or "").strip()
            if existing_runtime is not None
            else requested_runtime_name
        ) or agent_name
        sidecar_build_overrides: dict[str, Any] | None = None
        agentkit_config: dict[str, Any] | None = None
        if sidecar_enabled:
            configured_runtime_name = os.getenv(
                "VEADK_STUDIO_HARNESS_SIDECAR_RUNTIME_NAME",
                "",
            ).strip()
            if existing_runtime is None and configured_runtime_name:
                if not re.fullmatch(
                    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?",
                    configured_runtime_name,
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="受控 Harness Sidecar Runtime 名称不符合平台规则。",
                    )
                deployment_runtime_name = configured_runtime_name
            sidecar_yaml_envs: dict[str, str] = {}
            for index, (key, value) in enumerate(sorted(runtime_envs.items())):
                placeholder = f"VEADK_STUDIO_RUNTIME_ENV_{index:04d}"
                sidecar_yaml_envs[key] = "${" + placeholder + "}"
                sidecar_cli_runtime_env[placeholder] = value
            runtime_tags = {
                "veadk:managed": "true",
                **({"veadk:author": author} if author else {}),
                **({"veadk:owner": owner_id} if owner_id else {}),
                **deployment_resource_tag_values,
            }
            sidecar_runtime: dict[str, Any] = {
                "region": region,
                "project": project_name,
                "min_instance": 1,
                "max_instance": 1,
                "max_concurrency": 20,
                "tags": runtime_tags,
            }
            if runtime_network:
                mode = str(runtime_network.get("mode") or "public").lower()
                subnet_ids = [
                    item.strip()
                    for item in str(runtime_network.get("subnet_ids") or "").split(",")
                    if item.strip()
                ]
                sidecar_runtime["network"] = {
                    "enable_public_network": mode in {"public", "both"},
                    "enable_private_network": mode in {"private", "both"},
                    "vpc_id": runtime_network.get("vpc_id"),
                    "subnet_ids": subnet_ids,
                    "enable_shared_internet_access": bool(
                        runtime_network.get("enable_shared_internet_access", True)
                    ),
                }
            sidecar_agentkit_config = {
                "name": deployment_runtime_name,
                "description": _normalize_runtime_description(data.get("description")),
                "cloud_provider": "volcengine",
                "region": region,
                "project": project_name,
                "runtime": sidecar_runtime,
                "harness_sidecar": sidecar_cli_config,
                "envs": sidecar_yaml_envs,
                "auth": {"type": "key_auth"},
                "apmplus": True,
                "dockerfile": ".agentkit/Dockerfile",
                "infrastructure": {
                    "container_registry": {
                        "region": region,
                        "project": project_name,
                        "instance_name": deployment_resource_config.get(
                            "cr_instance_name", "Auto"
                        ),
                        "namespace_name": deployment_resource_config.get(
                            "cr_namespace_name", "agentkit"
                        ),
                        "repo_name": deployment_resource_config.get(
                            "cr_repo_name", deployment_runtime_name
                        ),
                    },
                    "tos": {
                        "region": region,
                        "project": project_name,
                        "bucket_name": deployment_resource_config.get(
                            "tos_bucket", "Auto"
                        ),
                        "object_prefix": "agentkit-builds",
                    },
                    "code_pipeline": {
                        "workspace_name": deployment_resource_config.get(
                            "cp_workspace_name"
                        ),
                        "workspace_id": deployment_resource_config.get(
                            "cp_workspace_id"
                        ),
                        "pipeline_name": deployment_resource_config.get(
                            "cp_pipeline_name"
                        ),
                        "pipeline_id": deployment_resource_config.get("cp_pipeline_id"),
                    },
                },
            }
            agentkit_dir = base / ".agentkit"
            agentkit_dir.mkdir(parents=True, exist_ok=True)
            (agentkit_dir / "agentkit.yaml").write_text(
                _yaml.safe_dump(
                    sidecar_agentkit_config,
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
        else:
            agentkit_config = {
                "common": {
                    "agent_name": trusted_agent_name,
                    "entry_point": entry_point,
                    "description": _normalize_runtime_description(
                        data.get("description")
                    ),
                    "python_version": "3.12",
                    "launch_type": "cloud",
                },
                "launch_types": {"cloud": cloud_config},
            }
            (base / "agentkit.yaml").write_text(
                _yaml.dump(agentkit_config, allow_unicode=True), encoding="utf-8"
            )

        task_state: dict[str, Any] = {
            "cancel_event": _threading.Event(),
            "runtime_id": runtime_id,
            "runtime_name": (
                deployment_runtime_name
                if sidecar_enabled or existing_runtime is not None
                else ""
            ),
            "region": region,
            "destroyed": False,
            "destroying": False,
            "destroy_on_cancel": not bool(runtime_id) and not sidecar_enabled,
            "owner_id": owner_id,
            "cp_workspace_id": str(
                (
                    ((data.get("resources") or {}).get("codePipeline") or {}).get(
                        "workspaceId"
                    )
                )
                or ""
            ),
            "cp_pipeline_id": str(
                deployment_resource_config.get("cp_pipeline_id") or ""
            ),
            "cp_pipeline_name": str(
                deployment_resource_config.get("cp_pipeline_name") or ""
            ),
        }
        events: _queue.Queue = _queue.Queue()
        state = {"phase": "build", "build_error_excerpt": ""}
        cp_log_stop_event = _threading.Event()
        task_state["cp_log_stop_event"] = cp_log_stop_event

        _CP_WORKSPACE_NAME = str(
            deployment_resource_config.get("cp_workspace_name")
            or "agentkit-cli-workspace"
        )
        _CP_LOG_POLL_INTERVAL = 5.0

        def _result_error_text(result) -> str:
            parts = []
            for obj in (
                result,
                getattr(result, "build_result", None),
                getattr(result, "deploy_result", None),
            ):
                if obj is None:
                    continue
                for attr in ("error", "error_code"):
                    value = getattr(obj, attr, None)
                    if value:
                        parts.append(
                            _redact_managed_artifact_text(
                                str(value),
                                [sidecar_base_image],
                            )
                        )
            return "\n".join(parts)

        def _is_tos_request_expired(error_text: str) -> bool:
            lower = (error_text or "").lower()
            return "request has expired" in lower and (
                "accessdenied" in lower or "access denied" in lower
            )

        def _friendly_error(error_text: str) -> str:
            duplicate_detail = _runtime_deploy_error_detail(
                error_text, requested_runtime_name
            )
            if duplicate_detail != error_text:
                return duplicate_detail
            if _is_tos_request_expired(error_text):
                return (
                    "云构建拉取源码包时 TOS 临时下载签名已过期。"
                    "已自动重试一次仍失败，请稍后重新点击部署。\n"
                    f"原始错误：\n{error_text}"
                )
            return error_text

        def _error_with_build_excerpt(error_text: str) -> str:
            error_text = _friendly_error(error_text)
            excerpt = state["build_error_excerpt"]
            if not excerpt or excerpt in error_text:
                return error_text
            return f"{error_text}\n\n构建日志关键错误：\n{excerpt}"

        def _classify(message: str) -> str:
            """Map a reporter message to a deploy phase, monotonically.

            The SDK usually prints high-level markers such as "Step 1/2:
            Building image" and "Step 2/2: Deploying service". Some failures
            only surface in the final error, so deployment/runtime failure
            markers also advance to the deploy phase. The phase never regresses.
            """
            return _advance_deploy_phase(state["phase"], message)

        from agentkit.toolkit.reporter import Reporter, TaskHandle

        def _update_cp_metadata(message: object) -> None:
            metadata = _cp_metadata_from_reporter_message(message)
            if not metadata:
                return
            with _deploy_tasks_lock:
                if metadata.get("pipeline_name"):
                    task_state["cp_pipeline_name"] = metadata["pipeline_name"]
                if metadata.get("pipeline_id"):
                    task_state["cp_pipeline_id"] = metadata["pipeline_id"]
                if metadata.get("pipeline_run_id"):
                    task_state["cp_pipeline_run_id"] = metadata["pipeline_run_id"]
            if metadata.get("pipeline_run_id"):
                _ensure_cp_log_thread()

        def _cp_log_event(
            *,
            status: str,
            message: str,
            snapshot: dict[str, Any] | None = None,
            error: str = "",
        ) -> dict[str, Any]:
            import time as _time

            with _deploy_tasks_lock:
                pipeline_id = str(task_state.get("cp_pipeline_id") or "")
                pipeline_name = str(task_state.get("cp_pipeline_name") or "")
                pipeline_run_id = str(task_state.get("cp_pipeline_run_id") or "")
                workspace_id = str(task_state.get("cp_workspace_id") or "")
                runtime_name = str(task_state.get("runtime_name") or "")
            payload = {
                "source": "code-pipeline",
                "status": status,
                "text": (snapshot or {}).get("text", ""),
                "lineCount": int((snapshot or {}).get("lineCount", 0) or 0),
                "truncated": bool((snapshot or {}).get("truncated", False)),
                "updatedAt": int(_time.time() * 1000),
                "pipelineId": pipeline_id,
                "pipelineName": pipeline_name,
                "pipelineRunId": pipeline_run_id,
                "workspaceId": workspace_id,
                "workspaceName": _CP_WORKSPACE_NAME,
            }
            if error:
                payload["error"] = _safe_exception_detail(Exception(error))
            event = {
                "level": "warning" if status == "error" else "info",
                "phase": "build",
                "message": message,
                "buildLog": payload,
            }
            if runtime_name:
                event["runtimeName"] = runtime_name
            return event

        def _resolve_cp_workspace_id(cp_client) -> str:
            with _deploy_tasks_lock:
                cached = str(task_state.get("cp_workspace_id") or "")
            if cached:
                return cached
            result = cp_client.get_workspaces_by_name(_CP_WORKSPACE_NAME, page_size=5)
            items = result.get("Items", [])
            workspace = next(
                (
                    item
                    for item in items
                    if str(item.get("Name") or "") == _CP_WORKSPACE_NAME
                ),
                items[0] if items else None,
            )
            workspace_id = str((workspace or {}).get("Id") or "")
            if not workspace_id:
                raise RuntimeError("Code Pipeline workspace not found")
            with _deploy_tasks_lock:
                task_state["cp_workspace_id"] = workspace_id
            return workspace_id

        def _resolve_cp_pipeline_id(cp_client, workspace_id: str) -> str:
            with _deploy_tasks_lock:
                pipeline_id = str(task_state.get("cp_pipeline_id") or "")
                pipeline_name = str(task_state.get("cp_pipeline_name") or "")
            if pipeline_id:
                return pipeline_id
            if not pipeline_name:
                raise RuntimeError("Code Pipeline id is not available yet")
            result = cp_client.list_pipelines(
                workspace_id=workspace_id,
                name_filter=pipeline_name,
                page_size=10,
            )
            items = result.get("Items", [])
            pipeline = next(
                (
                    item
                    for item in items
                    if str(item.get("Name") or "") == pipeline_name
                ),
                items[0] if items else None,
            )
            pipeline_id = str((pipeline or {}).get("Id") or "")
            if not pipeline_id:
                raise RuntimeError("Code Pipeline id could not be resolved")
            with _deploy_tasks_lock:
                task_state["cp_pipeline_id"] = pipeline_id
            return pipeline_id

        def _download_cp_build_log_text(
            cp_client,
            *,
            workspace_id: str,
            pipeline_id: str,
            pipeline_run_id: str,
        ) -> str:
            import requests

            stages_data = cp_client.list_pipeline_run_stages_inner(
                workspace_id=workspace_id,
                pipeline_id=pipeline_id,
                pipeline_run_id=pipeline_run_id,
            )
            parts: list[str] = []
            for stage in stages_data.get("Items", []):
                stage_name = str(
                    stage.get("DisplayName") or stage.get("Name") or "stage"
                )
                for task in stage.get("Tasks", []):
                    task_id = str(task.get("Id") or "")
                    task_run_id = str(task.get("TaskRunID") or "")
                    task_name = str(
                        task.get("DisplayName") or task.get("Name") or "task"
                    )
                    if not task_id or not task_run_id:
                        continue
                    for step in task.get("Steps", []):
                        step_name = str(step.get("Name") or "")
                        if not step_name:
                            continue
                        try:
                            log_url = cp_client.get_task_run_log_download_uri(
                                workspace_id=workspace_id,
                                pipeline_id=pipeline_id,
                                pipeline_run_id=pipeline_run_id,
                                task_run_id=task_run_id,
                                task_id=task_id,
                                step_name=step_name,
                            )
                            response = requests.get(log_url, timeout=20)
                            response.raise_for_status()
                        except requests.RequestException as log_error:
                            logger.debug(
                                "skip Code Pipeline step log download %s/%s/%s: %s",
                                stage_name,
                                task_name,
                                step_name,
                                log_error,
                            )
                            continue
                        content = response.text.strip("\n")
                        if content:
                            parts.append(
                                f"[{stage_name} / {task_name} / {step_name}]\n{content}"
                            )
            return "\n\n".join(parts)

        def _new_cp_client():
            from agentkit.toolkit.volcengine.code_pipeline import VeCodePipeline

            ak, sk, token = _resolve_ve_credentials()
            return VeCodePipeline(
                access_key=ak,
                secret_key=sk,
                session_token=token or "",
                region=region,
                provider=provider,
            )

        def _read_cp_build_log_snapshot(cp_client) -> dict[str, Any]:
            workspace_id = _resolve_cp_workspace_id(cp_client)
            pipeline_id = _resolve_cp_pipeline_id(cp_client, workspace_id)
            with _deploy_tasks_lock:
                pipeline_run_id = str(task_state.get("cp_pipeline_run_id") or "")
            if not pipeline_run_id:
                raise RuntimeError("Code Pipeline run id is not available yet")

            text = _download_cp_build_log_text(
                cp_client,
                workspace_id=workspace_id,
                pipeline_id=pipeline_id,
                pipeline_run_id=pipeline_run_id,
            )
            snapshot = _sanitize_build_log_snapshot(
                _redact_managed_artifact_text(
                    text,
                    [sidecar_base_image],
                )
            )
            current_text = str(snapshot.get("text") or "")
            if current_text:
                with _deploy_tasks_lock:
                    task_state["cp_build_log"] = snapshot
            return snapshot

        def _refresh_cp_build_log_event(status: str) -> dict[str, Any] | None:
            try:
                cp_client = _new_cp_client()
                if status == "error":
                    snapshot = _wait_for_cp_build_error_log_snapshot(
                        lambda: _read_cp_build_log_snapshot(cp_client)
                    )
                else:
                    snapshot = _read_cp_build_log_snapshot(cp_client)
            except Exception as log_error:
                if cp_log_stop_event.is_set():
                    logger.debug(
                        "final Code Pipeline build log refresh skipped: %s",
                        log_error,
                    )
                    return None
                logger.warning(
                    "final Code Pipeline build log refresh failed: %s",
                    log_error,
                    exc_info=True,
                )
                return _cp_log_event(
                    status="error",
                    message="暂时无法读取最终构建日志。",
                    error=_safe_exception_detail(log_error),
                )
            if not str(snapshot.get("text") or ""):
                return None
            message = (
                "构建镜像失败，已同步最终构建日志。"
                if status == "error"
                else "构建日志同步完成。"
            )
            return _cp_log_event(status=status, message=message, snapshot=snapshot)

        def _poll_cp_build_logs() -> None:
            last_text = ""
            try:
                cp_client = _new_cp_client()

                while not cp_log_stop_event.is_set():
                    snapshot = _read_cp_build_log_snapshot(cp_client)
                    current_text = str(snapshot.get("text") or "")
                    if current_text and current_text != last_text:
                        last_text = current_text
                        events.put(
                            _cp_log_event(
                                status="running",
                                message="正在构建镜像，已同步构建日志。",
                                snapshot=snapshot,
                            )
                        )
                    cp_log_stop_event.wait(_CP_LOG_POLL_INTERVAL)

                if last_text:
                    events.put(
                        _cp_log_event(
                            status="complete",
                            message="构建日志同步完成。",
                            snapshot={
                                "text": last_text,
                                "lineCount": len(last_text.splitlines()),
                                "truncated": False,
                            },
                        )
                    )
            except Exception as log_error:
                if cp_log_stop_event.is_set():
                    return
                logger.warning(
                    "Code Pipeline build log polling failed: %s",
                    log_error,
                    exc_info=True,
                )
                events.put(
                    _cp_log_event(
                        status="error",
                        message="暂时无法读取构建日志。",
                        error=_safe_exception_detail(log_error),
                    )
                )

        def _ensure_cp_log_thread() -> None:
            with _deploy_tasks_lock:
                thread = task_state.get("cp_log_thread")
                if thread is not None and thread.is_alive():
                    return
                thread = _threading.Thread(target=_poll_cp_build_logs, daemon=True)
                task_state["cp_log_thread"] = thread
            thread.start()

        def _emit(level: str, message: str, pct=None):
            message = _redact_debug_text(
                _redact_managed_artifact_text(
                    str(message),
                    [sidecar_base_image],
                )
            )
            _update_cp_metadata(message)
            state["phase"] = _classify(message)
            ev = {"level": level, "phase": state["phase"], "message": message}
            for marker in ("Generated Runtime name:", "Creating Runtime:"):
                if marker in message:
                    runtime_name = message.split(marker, 1)[1].strip()
                    if runtime_name:
                        task_state["runtime_name"] = runtime_name
                    break
            if task_state["runtime_name"]:
                ev["runtimeName"] = task_state["runtime_name"]
            if pct is not None:
                ev["pct"] = pct
            events.put(ev)

        class _QReporter(Reporter):
            def info(self, message, **k):
                _emit("info", str(message))

            def success(self, message, **k):
                _emit("success", str(message))

            def warning(self, message, **k):
                _emit("warning", str(message))

            def error(self, message, **k):
                _emit("error", str(message))

            def progress(self, message, current, total=100, **k):
                _emit(
                    "info", str(message), int(current / total * 100) if total else None
                )

            def confirm(self, message, default=False, **k):
                return default

            @contextmanager
            def long_task(self, description, total=100):
                _emit("info", str(description))

                class _H(TaskHandle):
                    def update(self, description=None, completed=None):
                        if description:
                            pct = (
                                int(completed / total * 100)
                                if (completed is not None and total)
                                else None
                            )
                            _emit("info", str(description), pct)

                yield _H()

            def show_logs(self, title, lines, max_lines=100):
                _emit("info", str(title))
                excerpt = _extract_build_error_excerpt(lines, min(max_lines, 30))
                if excerpt:
                    safe_excerpt = _redact_managed_artifact_text(
                        excerpt,
                        [sidecar_base_image],
                    )
                    state["build_error_excerpt"] = safe_excerpt
                    _emit("error", safe_excerpt)

        result_box: dict = {}

        def _finish_deploy_thread() -> None:
            cp_log_stop_event.set()
            cp_log_thread = task_state.get("cp_log_thread")
            if (
                cp_log_thread is not None
                and cp_log_thread.is_alive()
                and cp_log_thread is not _threading.current_thread()
            ):
                cp_log_thread.join(timeout=1.0)
            with _deploy_tasks_lock:
                _deploy_tasks.pop(task_id, None)
            events.put(None)

        def _run_cli() -> None:
            """Run the authorized AgentKit CLI MR structured release once."""

            with _deploy_lock:
                try:
                    cli_env = os.environ.copy()
                    access_key, secret_key, session_token = _resolve_ve_credentials()
                    cli_env["VOLCENGINE_ACCESS_KEY"] = access_key
                    cli_env["VOLCENGINE_SECRET_KEY"] = secret_key
                    cli_env["VOLCENGINE_REGION"] = region
                    if session_token:
                        cli_env["VOLCENGINE_SESSION_TOKEN"] = session_token
                    else:
                        cli_env.pop("VOLCENGINE_SESSION_TOKEN", None)
                    cli_env["AGENTKIT_HARNESS_SIDECAR_BASE_IMAGE"] = sidecar_base_image
                    if not runtime_id:
                        cli_env["AGENTKIT_HARNESS_SIDECAR_REQUIRE_ABSENT"] = "true"
                    cli_env.update(sidecar_cli_runtime_env)
                    process = subprocess.Popen(
                        [agentkit_cli_executable(), "release", "--json"],
                        cwd=base,
                        env=cli_env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                    )
                    with _deploy_tasks_lock:
                        task_state["process"] = process
                    cli_result: dict[str, Any] | None = None
                    assert process.stdout is not None
                    for raw_line in process.stdout:
                        if task_state["cancel_event"].is_set():
                            process.terminate()
                            break
                        safe_line = _redact_debug_text(
                            _redact_managed_artifact_text(
                                raw_line.strip(),
                                [sidecar_base_image],
                            )
                        )
                        if not safe_line:
                            continue
                        try:
                            payload = _json.loads(safe_line)
                        except (TypeError, ValueError) as error:
                            raise RuntimeError(
                                "AgentKit CLI 返回了无效的结构化部署事件。"
                            ) from error
                        if not isinstance(payload, dict):
                            raise RuntimeError(
                                "AgentKit CLI 返回了无效的结构化部署事件。"
                            )
                        event_type = payload.get("type")
                        if event_type == "runtime":
                            resolved_runtime_id = str(
                                payload.get("runtimeId") or ""
                            ).strip()
                            if resolved_runtime_id:
                                with _deploy_tasks_lock:
                                    task_state["runtime_id"] = resolved_runtime_id
                                    task_state["runtime_name"] = str(
                                        payload.get("runtimeName")
                                        or deployment_runtime_name
                                    )
                            continue
                        if event_type == "progress":
                            phase = str(payload.get("phase") or "deploy")
                            state["phase"] = phase
                            message = str(payload.get("message") or "")
                            _update_cp_metadata(message)
                            event: dict[str, Any] = {
                                "level": str(payload.get("level") or "info"),
                                "phase": phase,
                                "message": message,
                            }
                            if payload.get("pct") is not None:
                                event["pct"] = payload["pct"]
                            runtime_name = str(
                                payload.get("runtimeName")
                                or task_state.get("runtime_name")
                                or deployment_runtime_name
                            )
                            if runtime_name:
                                event["runtimeName"] = runtime_name
                            events.put(event)
                            continue
                        if event_type == "result":
                            cli_result = payload
                    return_code = process.wait(timeout=30)
                    with _deploy_tasks_lock:
                        task_state["process"] = None
                    if task_state["cancel_event"].is_set():
                        raise RuntimeError("Deployment cancelled")
                    if cli_result is None:
                        raise RuntimeError("AgentKit CLI 部署结束但未返回最终结果。")
                    if return_code != 0 or not cli_result.get("success"):
                        raise RuntimeError(
                            str(cli_result.get("error") or "AgentKit CLI 部署失败")
                        )
                    result_box["cli_result"] = cli_result
                except Exception as error:
                    safe_error = _redact_debug_text(
                        _redact_managed_artifact_text(
                            str(error),
                            [sidecar_base_image],
                        )
                    )
                    logger.error("AgentKit CLI structured deployment failed")
                    result_box["error"] = safe_error or "AgentKit CLI 部署失败"
                finally:
                    process = task_state.get("process")
                    if process is not None and process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                    _finish_deploy_thread()

        def _verify_sdk_sidecar_release(result: Any) -> None:
            if not sidecar_enabled or sidecar_plan is None:
                return
            import time as _time

            import requests

            deploy_result = getattr(result, "deploy_result", None)
            metadata = (
                deploy_result.metadata
                if deploy_result is not None and deploy_result.metadata
                else {}
            )
            deployed_runtime_id = str(
                metadata.get("runtime_id") or task_state.get("runtime_id") or ""
            )
            if not deployed_runtime_id:
                raise RuntimeError("Sidecar 发布成功但未返回 Runtime ID")
            _rt_conn_cache.pop((region, deployed_runtime_id), None)
            runtime_detail = _get_runtime(deployed_runtime_id, region)
            if getattr(runtime_detail, "status", "") != "Ready":
                raise RuntimeError("Sidecar Runtime 尚未达到 Ready")
            if (
                getattr(runtime_detail, "min_instance", None) != 1
                or getattr(runtime_detail, "max_instance", None) != 1
            ):
                raise RuntimeError("Sidecar Runtime 必须保持单实例 1～1")
            endpoint, api_key, auth_type, _network_type = _resolve_runtime_conn(
                deployed_runtime_id,
                region,
                runtime_detail,
            )
            if auth_type != "key_auth":
                raise RuntimeError("Sidecar Runtime 必须使用 API Key 鉴权")
            expected_hash = str(sidecar_plan.get("planHash") or "")
            expected_components = {
                str(item) for item in sidecar_plan.get("effectiveComponents") or []
            }
            required_ports = [18787]
            if "mcp_resilience" in expected_components:
                required_ports.append(18788)
            deadline = _time.monotonic() + 120.0
            headers = {"Authorization": _agentkit_authorization_header(api_key)}

            def _get(url: str, request_headers: Mapping[str, str]):
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    raise requests.Timeout("Sidecar readiness deadline exceeded")
                return requests.get(
                    url,
                    headers=dict(request_headers),
                    timeout=min(5.0, remaining),
                )

            while _time.monotonic() < deadline:
                try:
                    status_response = _get(
                        f"{endpoint.rstrip('/')}/web/harness-sidecar/status",
                        headers,
                    )
                    status_payload = status_response.json()
                    active_plan = (
                        status_response.status_code == 200
                        and isinstance(status_payload, Mapping)
                        and status_payload.get("status") in {"ready", "ok"}
                        and status_payload.get("planHash") == expected_hash
                        and expected_components.issubset(
                            {
                                str(item)
                                for item in status_payload.get(
                                    "effectiveComponents", []
                                )
                            }
                        )
                    )
                    ports_ready = active_plan
                    if active_plan:
                        for port in required_ports:
                            port_response = _get(
                                f"{endpoint.rstrip('/')}/healthz",
                                {
                                    **headers,
                                    "X-Faas-Proxy-Port": str(port),
                                },
                            )
                            if port_response.status_code != 200:
                                ports_ready = False
                                break
                    if ports_ready:
                        return
                except (requests.RequestException, TypeError, ValueError):
                    pass
                _time.sleep(min(1.0, max(0.0, deadline - _time.monotonic())))
            raise RuntimeError(
                "Sidecar Runtime active plan 或 APIG 固定端口未在时限内就绪"
            )

        def _run_sdk():
            from agentkit.toolkit import sdk
            from agentkit.toolkit.models import PreflightMode

            with _deploy_lock:
                # Tag the created runtime with the deploying user so "管理 Agent"
                # can filter by author. Restored right after.
                rt_client = None
                orig_create = None
                orig_update = None
                try:
                    sdk_agentkit_config = agentkit_config
                    if sdk_agentkit_config is None:
                        raise RuntimeError(
                            "AgentKit SDK deployment config is unavailable"
                        )
                    from agentkit.sdk.runtime.client import (
                        AgentkitRuntimeClient as rt_client,
                    )
                    from agentkit.sdk.runtime import types as _rt

                    orig_create = rt_client.create_runtime
                    orig_update = rt_client.update_runtime
                    extra = [
                        _rt.TagsItemForCreateRuntime.model_validate(
                            {"Key": "veadk:managed", "Value": "true"}
                        )
                    ]
                    if author:
                        extra.append(
                            _rt.TagsItemForCreateRuntime.model_validate(
                                {"Key": "veadk:author", "Value": author}
                            )
                        )
                    if owner_id:
                        extra.append(
                            _rt.TagsItemForCreateRuntime.model_validate(
                                {"Key": "veadk:owner", "Value": owner_id}
                            )
                        )
                    extra.extend(
                        _rt.TagsItemForCreateRuntime.model_validate(
                            {"Key": key, "Value": value}
                        )
                        for key, value in deployment_resource_tag_values.items()
                    )
                    if trusted_intelligent_source:
                        extra.extend(
                            _rt.TagsItemForCreateRuntime.model_validate(
                                {"Key": key, "Value": value}
                            )
                            for key, value in {
                                "veadk:lifecycle": "production",
                                "veadk:source": "intelligent-development",
                                "veadk:artifact": str(source["artifactSha256"]),
                                "veadk:validation-report": str(
                                    source["validationReportSha256"]
                                ),
                            }.items()
                        )

                    def _tagged_create(self, req, _orig=orig_create, _extra=extra):
                        if task_state["cancel_event"].is_set():
                            raise RuntimeError("Deployment cancelled")
                        req.tags = [*(req.tags or []), *_extra]
                        req.apmplus_enable = True
                        created = _create_runtime_with_description_fallback(
                            _orig, self, req
                        )
                        runtime_id = str(
                            getattr(created, "runtime_id", "")
                            or getattr(
                                getattr(created, "agent_kit_runtime", None),
                                "runtime_id",
                                "",
                            )
                        )
                        if runtime_id:
                            with _deploy_tasks_lock:
                                task_state["runtime_id"] = runtime_id
                        if task_state["cancel_event"].is_set():
                            _destroy_deploy_task_runtime(task_state)
                            raise RuntimeError("Deployment cancelled")
                        return created

                    def _apmplus_update(self, req, _orig=orig_update):
                        req.apmplus_enable = True
                        return _orig(self, req)

                    rt_client.create_runtime = _tagged_create
                    rt_client.update_runtime = _apmplus_update
                except Exception as e:
                    logger.error("Could not prepare Runtime ownership tags: %s", e)
                    result_box["error"] = _safe_exception_detail(e)
                    return

                try:
                    import copy

                    def _launch_config(config: dict[str, Any]):
                        config_path = base / "agentkit.yaml"
                        persisted_config = config
                        in_memory_config = None
                        if sidecar_enabled:
                            persisted_config = copy.deepcopy(config)
                            persisted_config["launch_types"]["cloud"][
                                "runtime_envs"
                            ] = {}
                            in_memory_config = copy.deepcopy(config)
                            in_memory_config.update(sidecar_build_overrides or {})
                        config_path.write_text(
                            _yaml.dump(persisted_config, allow_unicode=True),
                            encoding="utf-8",
                        )
                        launch_result = None
                        for attempt in range(1, 3):
                            state["build_error_excerpt"] = ""
                            if attempt > 1:
                                state["phase"] = "build"
                                _emit(
                                    "warning",
                                    (
                                        "TOS 临时下载签名已过期，"
                                        "正在重新打包上传并重试部署 "
                                        f"({attempt}/2)..."
                                    ),
                                )
                            with (
                                _agentkit_sdk_credential_env(),
                                agentkit_code_pipeline_resources(
                                    deployment_resource_config
                                ),
                            ):
                                launch_result = sdk.launch(
                                    config_file=str(config_path),
                                    config_dict=in_memory_config,
                                    platform=(
                                        "linux/amd64" if sidecar_enabled else "auto"
                                    ),
                                    preflight_mode=PreflightMode.WARN,
                                    reporter=_QReporter(),
                                )
                            if getattr(launch_result, "success", False):
                                break
                            error_text = _result_error_text(launch_result)
                            if attempt >= 2 or not _is_tos_request_expired(error_text):
                                break
                            _emit(
                                "warning",
                                (
                                    "云构建使用的 TOS 源码包签名超过 900 秒有效期，"
                                    "自动重试一次。"
                                ),
                            )
                        return launch_result

                    if sidecar_enabled and existing_runtime is None:
                        bootstrap_config = copy.deepcopy(sdk_agentkit_config)
                        bootstrap_cloud = bootstrap_config["launch_types"]["cloud"]
                        bootstrap_cloud["runtime_envs"] = {
                            key: value
                            for key, value in bootstrap_cloud["runtime_envs"].items()
                            if not key.startswith("HARNESS_")
                        }
                        _emit(
                            "info",
                            "正在创建 Sidecar Runtime 并建立 APIG 自调用绑定。",
                        )
                        result = _launch_config(bootstrap_config)
                        if getattr(result, "success", False):
                            bootstrap_deploy = getattr(result, "deploy_result", None)
                            bootstrap_metadata = (
                                bootstrap_deploy.metadata
                                if bootstrap_deploy is not None
                                and bootstrap_deploy.metadata
                                else {}
                            )
                            created_runtime_id = str(
                                task_state.get("runtime_id")
                                or bootstrap_metadata.get("runtime_id")
                                or ""
                            )
                            if not created_runtime_id:
                                raise RuntimeError(
                                    "Runtime 创建成功，但未返回 Runtime ID"
                                )
                            with _deploy_tasks_lock:
                                task_state["runtime_id"] = created_runtime_id
                            _rt_conn_cache.pop((region, created_runtime_id), None)
                            runtime_detail = _get_runtime(created_runtime_id, region)
                            (
                                runtime_endpoint,
                                runtime_api_key,
                                runtime_auth_type,
                                _runtime_network_type,
                            ) = _resolve_runtime_conn(
                                created_runtime_id,
                                region,
                                runtime_detail,
                            )
                            if runtime_auth_type != "key_auth":
                                raise RuntimeError(
                                    "Harness Sidecar Runtime 必须使用 API Key 鉴权"
                                )
                            final_config = copy.deepcopy(sdk_agentkit_config)
                            final_cloud = final_config["launch_types"]["cloud"]
                            final_cloud.update(
                                {
                                    "runtime_id": created_runtime_id,
                                    "runtime_name": (
                                        getattr(runtime_detail, "name", "")
                                        or deployment_runtime_name
                                    ),
                                    "runtime_role_name": (
                                        getattr(runtime_detail, "role_name", "")
                                        or "Auto"
                                    ),
                                    "image_tag": (
                                        "veadk-v"
                                        f"{(getattr(runtime_detail, 'current_version_number', 0) or 0) + 1}"
                                    ),
                                }
                            )
                            final_cloud["runtime_envs"].update(
                                {
                                    "HARNESS_SIDECAR_APIG_ENDPOINT": runtime_endpoint,
                                    "HARNESS_SIDECAR_APIG_API_KEY": runtime_api_key,
                                }
                            )
                            state["phase"] = "update"
                            _emit(
                                "info",
                                "APIG 自调用绑定已建立，正在发布最终 Sidecar 配置。",
                            )
                            result = _launch_config(final_config)
                    else:
                        result = _launch_config(sdk_agentkit_config)
                    if (
                        result is not None
                        and getattr(result, "success", False)
                        and needs_instance_update
                    ):
                        created_runtime_id = str(task_state.get("runtime_id") or "")
                        if not created_runtime_id:
                            raise RuntimeError("Runtime 创建成功，但未返回 Runtime ID")
                        state["phase"] = "update"
                        _emit(
                            "info",
                            f"正在将 Runtime 实例数调整为 {min_instance}～{max_instance}",
                            0,
                        )
                        _set_agentkit_runtime_instance_range(
                            created_runtime_id,
                            region,
                            min_instance,
                            max_instance,
                        )
                        _emit(
                            "success",
                            f"Runtime 实例数已调整为 {min_instance}～{max_instance}",
                            100,
                        )
                    if result is not None and getattr(result, "success", False):
                        _verify_sdk_sidecar_release(result)
                    result_box["result"] = result
                except Exception as e:
                    safe_error = _redact_managed_artifact_text(
                        _safe_exception_detail(e),
                        [sidecar_base_image],
                    )
                    logger.error("AgentKit SDK launch failed: %s", safe_error)
                    result_box["error"] = safe_error
                finally:
                    if rt_client is not None and orig_create is not None:
                        rt_client.create_runtime = orig_create
                    if rt_client is not None and orig_update is not None:
                        rt_client.update_runtime = orig_update
                    if task_state["cancel_event"].is_set():
                        try:
                            _destroy_deploy_task_runtime(task_state)
                        except Exception as e:
                            logger.error(
                                "cancelled deployment cleanup failed: %s",
                                e,
                                exc_info=True,
                            )
                    _finish_deploy_thread()

        with _deploy_tasks_lock:
            if task_id in _deploy_tasks:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=409, detail="Deployment task already exists"
                )
            _deploy_tasks[task_id] = task_state

        _threading.Thread(
            target=_run_cli if sidecar_enabled else _run_sdk,
            daemon=True,
        ).start()

        async def _stream():
            loop = asyncio.get_event_loop()
            try:
                while True:
                    ev = await loop.run_in_executor(None, events.get)
                    if ev is None:
                        break
                    yield f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"

                if result_box.get("error"):
                    state["phase"] = _classify(str(result_box["error"]))

                if result_box.get("error") and state["phase"] == "build":
                    cp_error_event = await loop.run_in_executor(
                        None,
                        _refresh_cp_build_log_event,
                        "error",
                    )
                    if cp_error_event is not None:
                        yield (
                            f"data: "
                            f"{_json.dumps(cp_error_event, ensure_ascii=False)}\n\n"
                        )

                final: dict[str, Any] = {"done": True}
                if result_box.get("error"):
                    error_text = str(result_box["error"])
                    final.update(
                        {
                            "success": False,
                            "error": _error_with_build_excerpt(error_text),
                            "phase": state["phase"],
                        }
                    )
                else:
                    deployment_meta: dict[str, Any] | None = None
                    cli_result = result_box.get("cli_result")
                    if isinstance(cli_result, dict):
                        deployed_runtime_id = str(
                            cli_result.get("runtimeId")
                            or task_state.get("runtime_id")
                            or runtime_id
                        )
                        try:
                            _rt_conn_cache.pop((region, deployed_runtime_id), None)
                            runtime_detail = _get_runtime(deployed_runtime_id, region)
                            (
                                endpoint,
                                runtime_api_key,
                                auth_type,
                                _network_type,
                            ) = _resolve_runtime_conn(
                                deployed_runtime_id,
                                region,
                                runtime_detail,
                            )
                            if auth_type != "key_auth":
                                raise RuntimeError(
                                    "Harness Sidecar Runtime 必须使用 API Key 鉴权。"
                                )
                            deployment_meta = {
                                "runtime_id": deployed_runtime_id,
                                "runtime_name": str(
                                    cli_result.get("runtimeName")
                                    or task_state.get("runtime_name")
                                    or deployment_runtime_name
                                ),
                                "runtime_apikey": runtime_api_key,
                                "endpoint_url": endpoint,
                                "version": cli_result.get("version"),
                            }
                        except Exception as error:
                            final.update(
                                {
                                    "success": False,
                                    "error": _redact_debug_text(str(error)),
                                    "phase": "publish",
                                }
                            )
                    else:
                        res = result_box.get("result")
                        dr = getattr(res, "deploy_result", None) if res else None
                        if res is not None and getattr(res, "success", False):
                            meta = (dr.metadata if (dr and dr.metadata) else {}) or {}
                            deployment_meta = {
                                "runtime_id": str(meta.get("runtime_id") or runtime_id),
                                "runtime_name": str(
                                    meta.get("runtime_name")
                                    or task_state.get("runtime_name")
                                    or agent_name
                                ),
                                "runtime_apikey": meta.get("runtime_apikey", ""),
                                "endpoint_url": (
                                    getattr(dr, "endpoint_url", None) if dr else None
                                ),
                            }
                        else:
                            err = getattr(res, "error", None) if res else None
                            err_text = (
                                _result_error_text(res)
                                if res is not None
                                else str(err or "Deployment failed")
                            )
                            final.update(
                                {
                                    "success": False,
                                    "error": _error_with_build_excerpt(err_text)
                                    or err
                                    or "Deployment failed",
                                    "phase": state["phase"],
                                }
                            )
                    if deployment_meta is not None:
                        deployed_runtime_id = str(
                            deployment_meta.get("runtime_id") or runtime_id
                        )
                        runtime_name = str(
                            task_state.get("runtime_name")
                            or deployment_meta.get("runtime_name")
                            or agent_name
                        )
                        final.update(
                            {
                                "success": True,
                                "agentName": agent_name,
                                "runtimeName": runtime_name,
                                "url": deployment_meta.get("endpoint_url"),
                                "apikey": deployment_meta.get(
                                    "runtime_apikey",
                                    "",
                                ),
                                "runtimeId": deployed_runtime_id,
                                "feishuChannel": {
                                    "enabled": True,
                                    "transport": "ws",
                                    "runtimeId": deployed_runtime_id,
                                }
                                if feishu_enabled
                                else None,
                                "consoleUrl": (
                                    "https://console.volcengine.com/agentkit/"
                                    f"region:agentkit+{region}/runtime?projectName={project_name}"
                                ),
                                "region": region,
                            }
                        )
                        if create_evaluation_sets:
                            evaluation_start = {
                                "level": "info",
                                "phase": "evaluation",
                                "message": ("正在创建 Good Case 和 Bad Case 评测集"),
                                "pct": 95,
                            }
                            yield (
                                "data: "
                                f"{_json.dumps(evaluation_start, ensure_ascii=False)}"
                                "\n\n"
                            )
                            try:
                                from frontend.server.evaluation_automation.datasets import (
                                    ensure_feedback_sets,
                                )

                                await ensure_feedback_sets(
                                    openapi_post=_agentkit_openapi_post,
                                    region=region,
                                    project_name=project_name,
                                    agent_name=agent_name,
                                )
                                evaluation_complete = {
                                    "level": "success",
                                    "phase": "evaluation",
                                    "message": ("Good Case 和 Bad Case 评测集已创建"),
                                    "pct": 100,
                                }
                                yield (
                                    "data: "
                                    f"{_json.dumps(evaluation_complete, ensure_ascii=False)}"
                                    "\n\n"
                                )
                            except Exception as e:  # noqa: BLE001 - optional setup.
                                warning = _redact_debug_text(str(e).strip())
                                warning = warning or "未知错误"
                                logger.warning(
                                    "Runtime deployed but evaluation-set initialization "
                                    "failed: %s",
                                    warning,
                                )
                                final["warnings"] = [
                                    f"Runtime 已部署，但评测集创建失败：{warning}"
                                ]
                                evaluation_warning = {
                                    "level": "warning",
                                    "phase": "evaluation",
                                    "message": ("Good Case 和 Bad Case 评测集创建失败"),
                                    "pct": 100,
                                }
                                yield (
                                    "data: "
                                    f"{_json.dumps(evaluation_warning, ensure_ascii=False)}"
                                    "\n\n"
                                )
                        if deployed_runtime_id:
                            _rt_conn_cache.pop((region, deployed_runtime_id), None)
                        try:
                            refreshed_runtime = _get_runtime(
                                deployed_runtime_id,
                                region,
                            )
                            final["version"] = deployment_meta.get(
                                "version"
                            ) or getattr(
                                refreshed_runtime,
                                "current_version_number",
                                None,
                            )
                        except Exception as e:
                            logger.warning(
                                "read deployed runtime version failed: %s", e
                            )
                yield f"data: {_json.dumps(final, ensure_ascii=False)}\n\n"
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        from fastapi.responses import StreamingResponse

        return StreamingResponse(_stream(), media_type="text/event-stream")

    def _runtime_tags(runtime: Any) -> dict[str, str]:
        return {
            str(tag.key): str(tag.value)
            for tag in (getattr(runtime, "tags", None) or [])
        }

    def _get_runtime(runtime_id: str, region: str) -> Any:
        from agentkit.sdk.runtime import types as _rt
        from agentkit.sdk.runtime.client import AgentkitRuntimeClient

        ak, sk, token = _resolve_ve_credentials()
        client = AgentkitRuntimeClient(
            access_key=ak,
            secret_key=sk,
            session_token=token or "",
            region=region,
        )
        return client.get_runtime(_rt.GetRuntimeRequest(runtime_id=runtime_id))

    def _authorized_runtime(
        request: Request,
        runtime_id: str,
        region: str,
        *,
        managed_only: bool = False,
        coded_access_error: bool = False,
    ) -> Any:
        principal = _current_principal(request)
        role = _request_role(request)
        runtime = _get_runtime(runtime_id, region)
        tags = _runtime_tags(runtime)
        if role != StudioRole.ADMIN and not runtime_belongs_to(tags, principal):
            raise HTTPException(
                status_code=404,
                detail=(
                    "runtime_access_denied"
                    if coded_access_error
                    else "Runtime not found"
                ),
            )
        if managed_only and tags.get("veadk:managed") != "true":
            raise HTTPException(status_code=404, detail="Runtime not found")
        return runtime

    from frontend.server.cronjobs import (
        CronjobAccessDenied,
        CronjobIdentity,
        CronjobService,
        TosCronjobRepository,
    )
    from frontend.server.cronjobs import mount_routes as mount_cronjob_routes
    from frontend.server.storage import StudioStorageConfig
    from frontend.server.storage.tos import create_tos_client_factory
    from frontend.service.studio_scheduler import (
        AgentKitRuntimeConnectionResolver,
        AgentKitRuntimeProvider,
        Dispatcher,
        DuePublisher,
        ProviderRuntimeExecutor,
        TosSchedulerRepository,
        run_local_scheduler,
    )
    from frontend.service.studio_scheduler.runtime_provider import ServiceCredentials

    class _StudioCronjobAccessPolicy:
        def resolve_owner(
            self,
            identity: CronjobIdentity,
            requested_owner_id: str | None,
        ) -> str:
            requested = (requested_owner_id or "").strip()
            if not requested or requested == identity.owner_id:
                return identity.owner_id
            if identity.is_admin:
                return requested
            raise CronjobAccessDenied("无权访问其他用户的定时任务。")

    def _cronjob_identity(request: Request) -> CronjobIdentity:
        principal = _current_principal(request)
        role = _request_role(request)
        return CronjobIdentity(
            ownerId=principal.owner_id if principal is not None else "local",
            isAdmin=role == StudioRole.ADMIN,
        )

    cronjob_local_dispatcher: Dispatcher | None = None
    cronjob_storage = StudioStorageConfig.from_env(provider)
    if cronjob_storage.configured:
        cronjob_tos_client_factory = create_tos_client_factory(
            cronjob_storage,
            _resolve_ve_credentials,
        )
        cronjob_scheduler_repository = TosSchedulerRepository(
            bucket=cronjob_storage.bucket,
            client_factory=cronjob_tos_client_factory,
            provider=provider,
        )
        mount_cronjob_routes(
            app,
            CronjobService(
                TosCronjobRepository(
                    bucket=cronjob_storage.bucket,
                    client_factory=cronjob_tos_client_factory,
                ),
                access_policy=_StudioCronjobAccessPolicy(),
                due_publisher=DuePublisher(cronjob_scheduler_repository),
            ),
            _cronjob_identity,
            lambda request, runtime_id, region: _authorized_runtime(
                request,
                runtime_id,
                region,
                coded_access_error=True,
            ),
        )
        if studio and vite:

            def _cronjob_service_credentials(
                _provider: str,
            ) -> ServiceCredentials:
                access_key, secret_key, session_token = _resolve_ve_credentials()
                return ServiceCredentials(
                    access_key=access_key,
                    secret_key=secret_key,
                    session_token=session_token or "",
                )

            runtime_resolver = AgentKitRuntimeConnectionResolver(
                credentials_resolver=_cronjob_service_credentials,
            )
            cronjob_local_dispatcher = Dispatcher(
                cronjob_scheduler_repository,
                ProviderRuntimeExecutor(
                    [AgentKitRuntimeProvider(provider, runtime_resolver)]
                ),
                replica_id=f"studio-local-{os.getpid()}",
            )

    @app.get("/web/my-runtimes")
    async def _web_my_runtimes(request: Request, region: str = "all"):
        """List AgentKit runtimes created via this UI (tagged veadk:managed),
        filtered to the trusted current identity for non-admin users.
        `region=all` queries every supported region and merges results."""
        principal = _current_principal(request)
        role = _request_role(request)
        ak, sk, token = _resolve_ve_credentials()
        regions = _runtime_regions(provider, region)

        async def _list_one(reg: str) -> list[dict]:
            from agentkit.sdk.runtime.client import AgentkitRuntimeClient
            from agentkit.sdk.runtime import types as _rt

            client = AgentkitRuntimeClient(
                access_key=ak,
                secret_key=sk,
                session_token=token or "",
                region=reg,
            )
            out: list[dict] = []
            next_token = None
            for _ in range(20):  # page cap
                kw: dict = {"page_size": 100}
                if next_token:
                    kw["next_token"] = next_token
                resp = client.list_runtimes(_rt.ListRuntimesRequest(**kw))
                for r in resp.agent_kit_runtimes or []:
                    tags = _runtime_tags(r)
                    if tags.get("veadk:managed") != "true":
                        continue
                    if role != StudioRole.ADMIN and not runtime_belongs_to(
                        tags, principal
                    ):
                        continue
                    out.append(
                        {
                            "name": r.name,
                            "runtimeId": r.runtime_id,
                            "status": r.status,
                            "createdAt": r.created_at,
                            "currentVersion": getattr(
                                r, "current_version_number", None
                            ),
                            "author": tags.get("veadk:author", ""),
                            "region": reg,
                        }
                    )
                next_token = getattr(resp, "next_token", None)
                if not next_token:
                    break
            return out

        try:
            results = await asyncio.gather(*[_list_one(r) for r in regions])
            out: list[dict] = [item for sub in results for item in sub]
            out.sort(key=lambda x: x.get("createdAt") or "", reverse=True)
            return {"runtimes": out}
        except Exception as e:
            logger.error(f"list my-runtimes failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

    @app.post("/web/delete-runtime")
    async def _web_delete_runtime(request: Request):
        """Delete an AgentKit runtime by id (used by the '管理 Agent' view)."""
        _require_agent_management(request)
        data = await request.json()
        runtime_id = (data.get("runtimeId") or "").strip()
        region = _coerce_cloud_region(data.get("region"))
        if not runtime_id:
            raise HTTPException(status_code=400, detail="runtimeId is required")
        try:
            _authorized_runtime(
                request,
                runtime_id,
                region,
                managed_only=True,
            )
            _delete_agentkit_runtime(runtime_id, region)
            return {"success": True}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"delete runtime failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/web/runtime-detail")
    async def _web_runtime_detail(
        request: Request,
        runtimeId: str = "",
        region: str = "",
    ):
        """Control-plane detail for one runtime (used by the '管理 Agent' view).

        Returns config/status metadata from GetRuntime. This is NOT the in-container
        agent graph (that lives on the runtime's data plane). Runtime visibility
        authorization also grants access to its environment-variable values.
        """
        if not runtimeId:
            raise HTTPException(status_code=400, detail="runtimeId is required")
        region = _coerce_cloud_region(region)

        try:
            r = _authorized_runtime(request, runtimeId, region)
            network_configurations = list(
                getattr(r, "network_configurations", None) or []
            )
            endpoint = ""
            for item in network_configurations:
                candidate = getattr(item, "endpoint", "") or ""
                if not candidate:
                    continue
                if not endpoint:
                    endpoint = candidate
                if getattr(item, "network_type", "") == "public":
                    endpoint = candidate
                    break
            authorizer = getattr(r, "authorizer_configuration", None)
            if getattr(authorizer, "key_auth", None):
                auth_type = "key_auth"
            elif getattr(authorizer, "custom_jwt_authorizer", None):
                auth_type = "custom_jwt"
            elif authorizer is None:
                auth_type = "none"
            else:
                auth_type = "unknown"
            envs = [
                {"key": e.key, "value": e.value or ""}
                for e in (getattr(r, "envs", None) or [])
            ]
            return {
                "runtimeId": getattr(r, "runtime_id", runtimeId),
                "name": getattr(r, "name", "") or "",
                "description": getattr(r, "description", "") or "",
                "status": getattr(r, "status", "") or "",
                "statusMessage": getattr(r, "status_message", "") or "",
                "model": getattr(r, "model_agent_name", "") or "",
                "project": getattr(r, "project_name", "") or "",
                "region": region,
                "createdAt": getattr(r, "created_at", "") or "",
                "updatedAt": getattr(r, "updated_at", "") or "",
                "currentVersion": getattr(r, "current_version_number", None),
                "resources": {
                    "cpuMilli": getattr(r, "cpu_milli", None),
                    "memoryMb": getattr(r, "memory_mb", None),
                    "minInstance": getattr(r, "min_instance", None),
                    "maxInstance": getattr(r, "max_instance", None),
                    "maxConcurrency": getattr(r, "max_concurrency", None),
                },
                "envs": envs,
                "memoryId": getattr(r, "memory_id", "") or "",
                "toolId": getattr(r, "tool_id", "") or "",
                "knowledgeId": getattr(r, "knowledge_id", "") or "",
                "mcpToolsetId": getattr(r, "mcp_toolset_id", "") or "",
                "artifactUrl": getattr(r, "artifact_url", "") or "",
                "artifactType": getattr(r, "artifact_type", "") or "",
                "networkTypes": [
                    getattr(item, "network_type", "") or ""
                    for item in network_configurations
                    if getattr(item, "network_type", "")
                ],
                "endpoint": endpoint,
                "authType": auth_type,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"get runtime detail failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

    @app.post("/web/runtime-api-key/reveal")
    async def _web_runtime_api_key_reveal(
        request: Request,
        response: Response,
        runtimeId: str = "",
        region: str = "cn-beijing",
    ):
        """Return one authorized Runtime API Key after an explicit UI action.

        The regular Runtime detail payload deliberately excludes credentials. This
        endpoint is separate so the browser only receives the key when the user
        asks to reveal it, and the response is never cacheable.
        """
        if not runtimeId:
            raise HTTPException(status_code=400, detail="runtimeId is required")
        runtime = _authorized_runtime(request, runtimeId, region)
        authorizer = getattr(runtime, "authorizer_configuration", None)
        key_auth = getattr(authorizer, "key_auth", None) if authorizer else None
        api_key = getattr(key_auth, "api_key", "") or ""
        if not api_key:
            raise HTTPException(status_code=404, detail="Runtime API Key not found")
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return {"apiKey": api_key}

    _runtime_list_cache_ttl_seconds = 30.0
    _runtime_list_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
    _runtime_list_locks: dict[tuple[Any, ...], asyncio.Lock] = {}

    @app.get("/web/runtime-name-availability")
    async def _web_runtime_name_availability(
        request: Request,
        response: Response,
        name: str = "",
        region: str = "",
    ):
        """Check one candidate name without exposing other Runtime details."""
        _require_agent_management(request)
        normalized_name = name.strip()
        validation_error = _runtime_name_validation_error(normalized_name)
        if validation_error:
            raise HTTPException(status_code=400, detail=validation_error)
        normalized_region = _coerce_cloud_region(region)
        try:
            from agentkit.sdk.runtime.client import AgentkitRuntimeClient
            from agentkit.sdk.runtime import types as _rt

            ak, sk, token = _resolve_ve_credentials()
            client = AgentkitRuntimeClient(
                access_key=ak,
                secret_key=sk,
                session_token=token or "",
                region=normalized_region,
            )
            runtime_filter = _rt.FiltersItemForListRuntimes.model_validate(
                {"Name": "Name", "Values": [normalized_name]}
            )
            result = await asyncio.to_thread(
                client.list_runtimes,
                _rt.ListRuntimesRequest(
                    max_results=1,
                    filters=[runtime_filter],
                ),
            )
            available = not any(
                str(getattr(runtime, "name", "") or "") == normalized_name
                for runtime in (result.agent_kit_runtimes or [])
            )
        except Exception as error:
            logger.error("check Runtime name availability failed: %s", error)
            raise HTTPException(
                status_code=502,
                detail="暂时无法检查 Runtime 名称，请稍后重试。",
            ) from error
        response.headers["Cache-Control"] = "no-store"
        return {"available": available}

    @app.get("/web/runtimes")
    async def _web_runtimes(
        request: Request,
        scope: str = "all",
        page_size: int = 30,
        next_token: str = "",
        region: str = "all",
    ):
        """One page of AgentKit runtimes for the agent selector. Lists ALL
        runtimes (server-side paginated); each item is flagged `isMine` when its
        ownership tags match the trusted current identity. Non-admin users are
        always restricted to their own runtimes.
        region=all merges runtimes across all supported regions."""
        principal = _current_principal(request)
        role = _request_role(request)
        ak, sk, svc_token = _resolve_ve_credentials()
        regions = _runtime_regions(provider, region)
        page_size = max(1, min(page_size, 100))
        restrict_to_owner = scope == "mine" or role != StudioRole.ADMIN
        principal_key = (
            getattr(principal, "owner_id", ""),
            getattr(principal, "display_name", ""),
        )
        cache_key = (
            principal_key,
            role,
            scope,
            page_size,
            next_token,
            region,
        )
        cached = _runtime_list_cache.get(cache_key)
        if cached and monotonic() - cached[0] < _runtime_list_cache_ttl_seconds:
            return cached[1]
        list_lock = _runtime_list_locks.setdefault(cache_key, asyncio.Lock())

        # next_token format for cross-region mode: "all:<offset>".
        async def _list_region(
            reg: str,
            tok: str,
            max_results: int = page_size,
            tag_filter: tuple[str, str] | None = None,
        ) -> tuple[list[dict], str]:
            from agentkit.sdk.runtime.client import AgentkitRuntimeClient
            from agentkit.sdk.runtime import types as _rt

            client = AgentkitRuntimeClient(
                access_key=ak,
                secret_key=sk,
                session_token=svc_token or "",
                region=reg,
            )
            out: list[dict] = []
            current_token = tok
            next_page_token = ""
            target_size = max(1, min(max_results, 100))
            for _ in range(20):
                kw: dict = {"max_results": max(1, target_size - len(out))}
                if tag_filter is not None:
                    kw["tag_filters"] = [
                        _rt.TagFiltersItemForListRuntimes.model_validate(
                            {"Key": tag_filter[0], "Values": [tag_filter[1]]}
                        )
                    ]
                if current_token:
                    kw["next_token"] = current_token
                request = _rt.ListRuntimesRequest(**kw)
                resp = await asyncio.to_thread(
                    client.list_runtimes,
                    request,
                )
                for runtime in resp.agent_kit_runtimes or []:
                    tags = _runtime_tags(runtime)
                    is_mine = runtime_belongs_to(tags, principal)
                    if (scope == "mine" or role != StudioRole.ADMIN) and not is_mine:
                        continue
                    can_delete = (
                        role != StudioRole.USER
                        and tags.get("veadk:managed") == "true"
                        and (role == StudioRole.ADMIN or is_mine)
                    )
                    out.append(
                        {
                            "name": runtime.name,
                            "runtimeId": runtime.runtime_id,
                            "status": runtime.status,
                            "createdAt": runtime.created_at,
                            "description": getattr(runtime, "description", "") or "",
                            "cpuMilli": getattr(runtime, "cpu_milli", None),
                            "memoryMb": getattr(runtime, "memory_mb", None),
                            "currentVersion": getattr(
                                runtime, "current_version_number", None
                            ),
                            "region": reg,
                            "author": tags.get("veadk:author", ""),
                            "isMine": is_mine,
                            "canDelete": can_delete,
                        }
                    )
                    if len(out) >= target_size:
                        break
                next_page_token = getattr(resp, "next_token", "") or ""
                if len(out) >= target_size or not next_page_token:
                    break
                current_token = next_page_token
            return out[:target_size], next_page_token

        await list_lock.acquire()
        cached = _runtime_list_cache.get(cache_key)
        if cached and monotonic() - cached[0] < _runtime_list_cache_ttl_seconds:
            list_lock.release()
            return cached[1]

        def _cache_result(payload: dict[str, Any]) -> dict[str, Any]:
            _runtime_list_cache[cache_key] = (monotonic(), payload)
            return payload

        try:
            if restrict_to_owner and principal is not None:
                if next_token:
                    match = re.fullmatch(r"mine:(\d+)", next_token)
                    if match is None:
                        raise HTTPException(
                            status_code=400,
                            detail="invalid owned runtime page token",
                        )
                    offset = int(match.group(1))
                else:
                    offset = 0
                window_end = offset + page_size
                owned_by_id: dict[str, dict] = {}
                owned_has_more = False
                owned_results = await asyncio.gather(
                    *(
                        _list_region(
                            reg,
                            "",
                            window_end,
                            ("veadk:owner", principal.owner_id),
                        )
                        for reg in regions
                    )
                )
                for items, following_token in owned_results:
                    for item in items:
                        owned_by_id[item["runtimeId"]] = item
                    owned_has_more = owned_has_more or bool(following_token)
                owned_runtimes = sorted(
                    owned_by_id.values(),
                    key=lambda item: item.get("createdAt") or "",
                    reverse=True,
                )
                page_end = min(window_end, len(owned_runtimes))
                page = owned_runtimes[offset:page_end]
                has_more = page_end < len(owned_runtimes) or owned_has_more
                following_token = f"mine:{page_end}" if has_more else ""
                return _cache_result({"runtimes": page, "nextToken": following_token})

            if len(regions) == 1:
                out, nxt = await _list_region(regions[0], next_token)
                return _cache_result({"runtimes": out, "nextToken": nxt})

            if next_token:
                match = re.fullmatch(r"all:(\d+)", next_token)
                if match is None:
                    raise HTTPException(
                        status_code=400,
                        detail="invalid cross-region runtime page token",
                    )
                offset = int(match.group(1))
            else:
                offset = 0

            # Pull only the regional prefixes needed to produce this merged
            # page. Fetching ``offset + page_size`` items per region is enough
            # to preserve the global created-at ordering without exhausting
            # every regional cursor on the first request.
            window_end = offset + page_size

            async def _list_region_window(reg: str) -> tuple[list[dict], bool]:
                items: list[dict] = []
                regional_token = ""
                seen_tokens: set[str] = set()
                following_token = ""
                while len(items) < window_end:
                    page, following_token = await _list_region(
                        reg,
                        regional_token,
                        window_end - len(items),
                    )
                    items.extend(page)
                    if not following_token:
                        break
                    if following_token in seen_tokens:
                        raise RuntimeError(f"repeated runtime page token for {reg}")
                    seen_tokens.add(following_token)
                    regional_token = following_token
                return items, bool(following_token)

            all_runtimes: list[dict] = []
            regional_has_more = False
            regional_results = await asyncio.gather(
                *(_list_region_window(reg) for reg in regions),
                return_exceptions=True,
            )
            regional_errors: list[str] = []
            for reg, result in zip(regions, regional_results):
                if isinstance(result, BaseException):
                    if isinstance(result, asyncio.CancelledError):
                        raise result
                    error_detail = _safe_exception_detail(
                        result,
                        secrets=(ak, sk, svc_token),
                    )
                    logger.warning("list runtimes [%s] failed: %s", reg, error_detail)
                    regional_errors.append(f"{reg}: {error_detail}")
                    continue
                items, has_more = result
                all_runtimes.extend(items)
                regional_has_more = regional_has_more or has_more
            if len(regional_errors) == len(regions):
                raise RuntimeError(
                    "all regional runtime requests failed: "
                    + "; ".join(regional_errors)
                )
            all_runtimes.sort(
                key=lambda x: x.get("createdAt") or "",
                reverse=True,
            )
            page_end = min(offset + page_size, len(all_runtimes))
            page = all_runtimes[offset:page_end]
            has_more = page_end < len(all_runtimes) or regional_has_more
            following_token = f"all:{page_end}" if has_more else ""
            return _cache_result({"runtimes": page, "nextToken": following_token})
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"list runtimes failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=502,
                detail=_safe_exception_detail(e, secrets=(ak, sk, svc_token)),
            )
        finally:
            list_lock.release()

    # Cache resolved (endpoint, apikey, auth type) per runtime so the data-plane
    # proxy does not call GetRuntime on every request. Short TTL; cleared on a 401.
    _rt_conn_cache: dict[tuple[str, str], tuple[str, str, str, str, float]] = {}

    def _runtime_endpoint_host(endpoint: str) -> str:
        parsed = urlparse(endpoint or "")
        return parsed.hostname or parsed.netloc or ""

    def _runtime_proxy_is_retryable_read(method: str) -> bool:
        return method.upper() in {"GET", "HEAD"}

    def _runtime_proxy_retry_delay(attempt: int) -> float:
        return min(5.0, float(2 ** max(0, attempt - 1)))

    def _runtime_proxy_attempts(
        method: str,
        endpoint_network_type: str,
    ) -> int:
        if endpoint_network_type == "private":
            return 1
        return 3 if _runtime_proxy_is_retryable_read(method) else 1

    def _runtime_network_error_detail(
        endpoint_network_type: str,
        *,
        timeout: bool,
        json_request: bool = False,
    ) -> str:
        if endpoint_network_type == "private":
            return "runtime_private_endpoint_unreachable"
        if json_request:
            return "runtime_json_timeout" if timeout else "runtime_json_connect_error"
        return "runtime_proxy_timeout" if timeout else "runtime_proxy_connect_error"

    def _runtime_network_log_items(runtime: Any) -> list[dict[str, Any]]:
        items = []
        for index, nc in enumerate(
            getattr(runtime, "network_configurations", None) or []
        ):
            endpoint = getattr(nc, "endpoint", "") or ""
            items.append(
                {
                    "index": index,
                    "network_type": getattr(nc, "network_type", "") or "",
                    "endpoint_present": bool(endpoint),
                    "endpoint_host": _runtime_endpoint_host(endpoint),
                }
            )
        return items

    def _resolve_runtime_conn(
        runtime_id: str,
        region: str,
        runtime: Any | None = None,
    ) -> tuple[str, str, str, str]:
        import time as _time

        cache_key = (region, runtime_id)
        cached = _rt_conn_cache.get(cache_key)
        if cached and cached[4] > _time.time():
            logger.info(
                "runtime conn cache hit runtime_id=%s region=%s endpoint_host=%s "
                "auth_type=%s network_type=%s",
                runtime_id,
                region,
                _runtime_endpoint_host(cached[0]),
                cached[2],
                cached[3],
            )
            return cached[0], cached[1], cached[2], cached[3]
        r = runtime if runtime is not None else _get_runtime(runtime_id, region)
        endpoint = ""
        endpoint_source = ""
        endpoint_network_type = ""
        for nc in getattr(r, "network_configurations", None) or []:
            ep = getattr(nc, "endpoint", "") or ""
            if ep:
                endpoint_network_type = getattr(nc, "network_type", "") or ""
                endpoint = ep
                endpoint_source = f"network_config:{endpoint_network_type or 'unknown'}"
                if endpoint_network_type == "public":
                    break
        apikey = ""
        auth = getattr(r, "authorizer_configuration", None)
        key_auth = getattr(auth, "key_auth", None) if auth else None
        custom_jwt_auth = getattr(auth, "custom_jwt_authorizer", None) if auth else None
        auth_type = "none"
        if key_auth:
            apikey = getattr(key_auth, "api_key", "") or ""
            auth_type = "key_auth"
        elif custom_jwt_auth:
            auth_type = "custom_jwt"
        top_level_endpoint = getattr(r, "endpoint", "") or ""
        logger.info(
            "resolved runtime metadata runtime_id=%s region=%s runtime_name=%s "
            "status=%s version=%s top_endpoint_present=%s top_endpoint_host=%s "
            "network_configs=%s selected_endpoint_source=%s "
            "selected_endpoint_host=%s auth_type=%s",
            runtime_id,
            region,
            getattr(r, "name", "") or "",
            getattr(r, "status", "") or "",
            getattr(r, "current_version_number", "") or "",
            bool(top_level_endpoint),
            _runtime_endpoint_host(top_level_endpoint),
            _runtime_network_log_items(r),
            endpoint_source or "none",
            _runtime_endpoint_host(endpoint),
            auth_type,
        )
        if not endpoint:
            logger.warning(
                "runtime has no selected endpoint runtime_id=%s region=%s "
                "status=%s top_endpoint_present=%s top_endpoint_host=%s "
                "network_configs=%s",
                runtime_id,
                region,
                getattr(r, "status", "") or "",
                bool(top_level_endpoint),
                _runtime_endpoint_host(top_level_endpoint),
                _runtime_network_log_items(r),
            )
            raise HTTPException(
                status_code=502, detail="runtime has no public endpoint"
            )
        _rt_conn_cache[cache_key] = (
            endpoint,
            apikey,
            auth_type,
            endpoint_network_type,
            _time.time() + 300,
        )
        return endpoint, apikey, auth_type, endpoint_network_type

    def _runtime_request_headers(
        request: Request,
        *,
        apikey: str,
        auth_type: str,
    ) -> dict[str, str]:
        """Build data-plane headers without exposing Runtime credentials."""
        validated_authorization = None
        if auth_type == "custom_jwt":
            access_token = getattr(request.state, "oauth2_access_token", None)
            if (
                getattr(request.state, "oauth2_access_token_validated", False)
                and access_token
            ):
                validated_authorization = access_token
            elif auth_mode == "gateway":
                incoming_authorization = request.headers.get("authorization")
                if _claims_from_forwarded_jwt(incoming_authorization):
                    validated_authorization = incoming_authorization
            if not validated_authorization:
                raise HTTPException(
                    status_code=401,
                    detail="OAuth runtime requires an authenticated frontend session",
                )
        return _build_agentkit_proxy_headers(
            dict(request.headers), apikey, validated_authorization
        )

    @app.get("/web/runtime-tool-channel/{runtime_id}/capabilities")
    async def _runtime_tool_channel_capabilities(runtime_id: str, request: Request):
        """Return local BFF tools and whether this Runtime accepts them."""

        region = _coerce_cloud_region(request.query_params.get("region"))
        try:
            runtime = _authorized_runtime(
                request,
                runtime_id,
                region,
                coded_access_error=True,
            )
            endpoint, apikey, auth_type, _ = _resolve_runtime_conn(
                runtime_id,
                region,
                runtime,
            )
            headers = _runtime_request_headers(
                request,
                apikey=apikey,
                auth_type=auth_type,
            )
            supported = False
            if studio_tool_registry.enabled:
                from frontend.server.studio_tools import runtime_supports_bff_tools

                supported = await runtime_supports_bff_tools(
                    endpoint=endpoint,
                    authorization=headers.get("Authorization", ""),
                )
        except HTTPException:
            raise
        except Exception as error:  # noqa: BLE001 - capability boundary
            logger.exception(
                "Studio tool capability query failed runtime_id=%s region=%s",
                runtime_id,
                region,
            )
            raise HTTPException(
                status_code=502,
                detail="studio_tool_capability_query_error",
            ) from error
        return {
            "enabled": studio_tool_registry.enabled,
            "supported": supported,
            "tools": studio_tool_registry.public_items(),
        }

    @app.post("/web/runtime-route-channel/{runtime_id}/connect")
    async def _connect_runtime_route_channel(runtime_id: str, request: Request):
        """Ensure the local BFF is the active dynamic-route provider."""

        region = _coerce_cloud_region(request.query_params.get("region"))
        try:
            runtime = _authorized_runtime(
                request,
                runtime_id,
                region,
                coded_access_error=True,
            )
            endpoint, apikey, auth_type, _ = _resolve_runtime_conn(
                runtime_id,
                region,
                runtime,
            )
            headers = _runtime_request_headers(
                request,
                apikey=apikey,
                auth_type=auth_type,
            )
            supported = await studio_route_channels.ensure_connected(
                runtime_id=runtime_id,
                endpoint=endpoint,
                authorization=headers.get("Authorization", ""),
            )
        except HTTPException:
            raise
        except Exception as error:  # noqa: BLE001 - reverse-channel boundary
            logger.exception(
                "Studio route channel connection failed runtime_id=%s region=%s",
                runtime_id,
                region,
            )
            raise HTTPException(
                status_code=502,
                detail="studio_route_channel_connect_error",
            ) from error
        return {
            "enabled": studio_route_registry.enabled,
            "supported": supported,
            "connected": supported and studio_route_channels.connected(runtime_id),
            "catalogRevision": (
                studio_route_registry.revision
                if studio_route_registry.enabled
                else None
            ),
        }

    evaluation_automation: EvaluationAutomationService | None = None
    agent_usage_service: Any | None = None
    if studio:
        from contextlib import asynccontextmanager, suppress
        from frontend.server.agent_usage import (
            create_service as create_agent_usage_service,
        )
        from frontend.server.agent_usage import (
            mount_routes as mount_agent_usage_routes,
        )

        async def _evaluation_automation_openapi_post(
            *,
            region: str,
            action: str,
            payload: dict[str, Any],
            query: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            return await _agentkit_openapi_post(
                region=region,
                action=action,
                payload=payload,
                query=query,
            )

        evaluation_automation = create_evaluation_automation_service(
            openapi_post=_evaluation_automation_openapi_post,
            provider=provider,
            resolve_credentials=_resolve_ve_credentials,
        )
        agent_usage_service = create_agent_usage_service(
            provider=provider,
            resolve_credentials=_resolve_ve_credentials,
        )
        app.state.evaluation_automation = evaluation_automation
        app.state.agent_usage = agent_usage_service
        original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def _studio_services_lifespan(current_app: Any):
            codex_model_env_task: asyncio.Task[None] | None = None
            cronjob_scheduler_task: asyncio.Task[None] | None = None
            async with original_lifespan(current_app):
                if not getattr(
                    current_app.state,
                    "disable_system_info_codex_model_env_prefetch",
                    False,
                ):
                    codex_model_env_task = asyncio.create_task(
                        _refresh_system_info_codex_model_env_states()
                    )
                if cronjob_local_dispatcher is not None:
                    cronjob_scheduler_task = asyncio.create_task(
                        run_local_scheduler(cronjob_local_dispatcher)
                    )
                try:
                    yield
                finally:
                    if (
                        cronjob_scheduler_task is not None
                        and not cronjob_scheduler_task.done()
                    ):
                        cronjob_scheduler_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await cronjob_scheduler_task
                    if (
                        codex_model_env_task is not None
                        and not codex_model_env_task.done()
                    ):
                        codex_model_env_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await codex_model_env_task
                    try:
                        await evaluation_automation.close()
                    finally:
                        await agent_usage_service.close()

        app.router.lifespan_context = _studio_services_lifespan
        mount_evaluation_automation_routes(
            app,
            evaluation_automation,
            lambda request, runtime_id, region: _authorized_runtime(
                request,
                runtime_id,
                region,
                coded_access_error=True,
            ),
        )

        def _authorize_agent_usage(
            request: Request,
            runtime_id: str,
            region: str,
        ) -> Any:
            _require_agent_management(request)
            return _authorized_runtime(
                request,
                runtime_id,
                region,
                coded_access_error=True,
            )

        mount_agent_usage_routes(
            app,
            agent_usage_service,
            _authorize_agent_usage,
        )

        from frontend.server.website_integration import (
            create_service as create_website_integration_service,
        )
        from frontend.server.website_integration import (
            mount_routes as mount_website_integration_routes,
        )
        from frontend.server.website_integration.models import WebsiteIntegration
        from frontend.server.website_integration.runtime import (
            invoke_agentkit_runtime,
        )

        website_integration_service = create_website_integration_service(
            provider=provider,
            resolve_credentials=_resolve_ve_credentials,
            signing_key=_knowledge_signing_key(),
        )
        app.state.website_integrations = website_integration_service

        def _website_integration_owner(request: Request) -> str:
            principal = _require_agent_management(request)
            return principal.owner_id if principal is not None else "local"

        def _authorize_website_integration_runtime(
            request: Request,
            runtime_id: str,
            region: str,
        ) -> Any:
            _require_agent_management(request)
            return _authorized_runtime(
                request,
                runtime_id,
                _coerce_cloud_region(region),
                coded_access_error=True,
            )

        async def _invoke_website_integration_runtime(
            integration: WebsiteIntegration,
            payload: dict[str, Any],
        ):
            return await invoke_agentkit_runtime(
                integration,
                payload,
                get_runtime=_get_runtime,
                resolve_connection=_resolve_runtime_conn,
                build_headers=_build_agentkit_proxy_headers,
            )

        mount_website_integration_routes(
            app,
            website_integration_service,
            owner_id=_website_integration_owner,
            authorize_runtime=_authorize_website_integration_runtime,
            invoke_runtime=_invoke_website_integration_runtime,
        )

    @app.api_route(
        "/web/runtime-proxy/{runtime_id}/{path:path}",
        methods=["GET", "HEAD", "POST", "PATCH", "DELETE"],
    )
    async def _runtime_proxy(runtime_id: str, path: str, request: Request):
        """Proxy a data-plane call with its runtime credential injected server-side.

        The browser never sees an API key. Streams the response so /run_sse works.
        """
        method_override = request.query_params.get("_method", "").upper()
        if method_override and not (
            request.method == "POST" and method_override == "DELETE"
        ):
            raise HTTPException(status_code=400, detail="invalid method override")
        upstream_method = method_override or request.method
        # `_runtime_region` selects the Runtime and is never forwarded. Keep
        # accepting `region` for older Studio bundles, where it was a proxy-only
        # parameter. New bundles leave `region` available to upstream APIs such
        # as the Skill Catalog endpoints.
        proxy_region = request.query_params.get("_runtime_region")
        region = _coerce_cloud_region(
            proxy_region or request.query_params.get("region")
        )
        try:
            runtime = _authorized_runtime(
                request,
                runtime_id,
                region,
                coded_access_error=True,
            )
            endpoint, apikey, auth_type, endpoint_network_type = _resolve_runtime_conn(
                runtime_id,
                region,
                runtime,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"resolve runtime conn failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

        # Drop Studio-only query params; keep any real API query params.
        studio_query_params = {"probe_retry", "_method", "_runtime_region"}
        if proxy_region is None:
            studio_query_params.add("region")
        qs = {
            k: v
            for k, v in request.query_params.items()
            if k not in studio_query_params
        }
        target = f"{endpoint.rstrip('/')}/{path}"
        target_host = _runtime_endpoint_host(target)
        logger.info(
            "runtime-proxy upstream request runtime_id=%s region=%s method=%s "
            "path=%s target_host=%s query_keys=%s auth_type=%s",
            runtime_id,
            region,
            upstream_method,
            path,
            target_host,
            sorted(qs.keys()),
            auth_type,
        )
        # Use the shared proxy header builder so Origin/Referer and other
        # browser-only headers are stripped (the ADK server rejects them with
        # "origin not allowed" / 403 otherwise).
        headers = _runtime_request_headers(
            request,
            apikey=apikey,
            auth_type=auth_type,
        )
        body = await request.body()
        run_sse_activity: RunSseActivity | None = None
        run_sse_principal: StudioPrincipal | None = None
        run_sse_payload: dict[str, Any] | None = None
        studio_tool_catalog: Any | None = None
        usage_invocation_id = ""
        if request.method == "POST" and path == "run_sse":
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as error:
                raise HTTPException(
                    status_code=400, detail="run_sse request body must be JSON"
                ) from error
            if not isinstance(payload, dict):
                raise HTTPException(
                    status_code=400, detail="run_sse request body must be an object"
                )
            selected_tool_ids: list[str] = []
            if "platform_tools" in payload:
                raw_tool_ids = payload.pop("platform_tools")
                if not isinstance(raw_tool_ids, list) or any(
                    not isinstance(tool_id, str) or not tool_id.strip()
                    for tool_id in raw_tool_ids
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="platform_tools must be a list of non-empty tool IDs",
                    )
                selected_tool_ids = [tool_id.strip() for tool_id in raw_tool_ids]
            try:
                studio_tool_catalog = studio_tool_registry.snapshot(selected_tool_ids)
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            try:
                payload = await resolve_runtime_media(payload, media_service)
                run_sse_payload = payload
                body = json.dumps(payload).encode("utf-8")
            except FileNotFoundError as error:
                raise HTTPException(
                    status_code=404, detail="Media not found."
                ) from error
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
            if agent_usage_service is not None:
                run_sse_principal = _current_principal(request)
                if run_sse_principal is None:
                    logger.info(
                        "agent usage skipped runtime_id=%s path=%s reason=no_principal",
                        runtime_id,
                        path,
                    )
                else:
                    usage_invocation_id = str(uuid4())
            if evaluation_automation is not None or run_sse_principal is not None:
                try:
                    run_sse_activity = RunSseActivity.from_proxy(
                        payload,
                        runtime_id=runtime_id,
                        region=region,
                        project_name=str(
                            getattr(runtime, "project_name", "") or "default"
                        ),
                        runtime_endpoint=endpoint,
                        runtime_authorization=headers.get("Authorization", ""),
                    )
                except ValueError as error:
                    logger.info(
                        "run_sse completion tracking skipped runtime_id=%s "
                        "path=%s reason=%s",
                        runtime_id,
                        path,
                        error,
                    )
                else:
                    if evaluation_automation is not None:
                        evaluation_automation.session_started(run_sse_activity)

        from fastapi.responses import StreamingResponse

        observation = (
            RunSseObservation(run_sse_activity)
            if run_sse_activity is not None
            else None
        )

        def _run_sse_completed(activity: RunSseActivity) -> None:
            if evaluation_automation is not None:
                evaluation_automation.session_completed(activity)
            if agent_usage_service is None or run_sse_principal is None:
                return
            try:
                agent_usage_service.record_success(
                    invocation_id=usage_invocation_id,
                    runtime_id=runtime_id,
                    app_name=activity.app_name,
                    user_id=run_sse_principal.owner_id,
                    display_name=run_sse_principal.display_name,
                )
            except Exception:
                logger.exception(
                    "agent usage record failed runtime_id=%s app_name=%s",
                    runtime_id,
                    activity.app_name,
                )

        if (
            studio_tool_catalog is not None
            and studio_tool_catalog.enabled
            and run_sse_payload is not None
            and request.method == "POST"
            and path == "run_sse"
        ):
            from frontend.server.studio_tools import (
                StudioChannelError,
                open_studio_tool_run,
                runtime_supports_bff_tools,
            )

            try:
                bff_tools_enabled = await runtime_supports_bff_tools(
                    endpoint=endpoint,
                    authorization=headers.get("Authorization", ""),
                )
                studio_run = (
                    await open_studio_tool_run(
                        endpoint=endpoint,
                        authorization=headers.get("Authorization", ""),
                        runtime_id=runtime_id,
                        payload=run_sse_payload,
                        catalog=studio_tool_catalog,
                    )
                    if bff_tools_enabled
                    else None
                )
            except StudioChannelError as error:
                logger.warning(
                    "Studio tool channel connection failed runtime_id=%s "
                    "target_host=%s error=%s",
                    runtime_id,
                    target_host,
                    error,
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"studio_tool_channel_connect_error: {error}",
                ) from error
            except Exception as error:  # noqa: BLE001 - WebSocket boundary
                logger.exception(
                    "Studio tool channel connection failed runtime_id=%s "
                    "target_host=%s",
                    runtime_id,
                    target_host,
                )
                raise HTTPException(
                    status_code=502,
                    detail="studio_tool_channel_connect_error",
                ) from error

            if studio_run is None:
                logger.info(
                    "runtime does not support BFF tools; using plain run_sse "
                    "runtime_id=%s target_host=%s",
                    runtime_id,
                    target_host,
                )
            else:

                async def _studio_channel_body():
                    source = studio_run.stream()
                    try:
                        if observation is None:
                            async for chunk in source:
                                yield chunk
                        else:
                            async for chunk in observed_sse_stream(
                                source,
                                observation,
                                _run_sse_completed,
                            ):
                                yield chunk
                    except StudioChannelError as error:
                        logger.warning(
                            "Studio tool channel stream failed runtime_id=%s error=%s",
                            runtime_id,
                            error,
                        )
                        yield (
                            "data: "
                            + json.dumps(
                                {"error": f"Studio tool channel failed: {error}"}
                            )
                            + "\n\n"
                        ).encode("utf-8")

                return StreamingResponse(
                    _studio_channel_body(),
                    status_code=200,
                    media_type="text/event-stream",
                )

        is_retryable_read = _runtime_proxy_is_retryable_read(upstream_method)
        max_attempts = _runtime_proxy_attempts(
            upstream_method,
            endpoint_network_type,
        )
        timeout = httpx.Timeout(10.0, connect=5.0) if is_retryable_read else None

        # Open the upstream stream so we can forward status + body incrementally.
        client = httpx.AsyncClient(timeout=timeout)
        upstream = None
        for attempt in range(1, max_attempts + 1):
            req = client.build_request(
                upstream_method, target, params=qs, headers=headers, content=body
            )
            try:
                upstream = await client.send(req, stream=True)
                if attempt > 1:
                    logger.info(
                        "runtime-proxy request succeeded after retry "
                        "runtime_id=%s region=%s path=%s target_host=%s "
                        "attempt=%s max_attempts=%s",
                        runtime_id,
                        region,
                        path,
                        target_host,
                        attempt,
                        max_attempts,
                    )
                break
            except (httpx.ConnectError, httpx.TimeoutException) as error:
                timed_out = isinstance(error, httpx.TimeoutException)
                if attempt < max_attempts:
                    delay = _runtime_proxy_retry_delay(attempt)
                    logger.warning(
                        "runtime-proxy request retry runtime_id=%s region=%s "
                        "method=%s path=%s target_host=%s network_type=%s "
                        "attempt=%s max_attempts=%s delay=%.1fs error=%s",
                        runtime_id,
                        region,
                        upstream_method,
                        path,
                        target_host,
                        endpoint_network_type,
                        attempt,
                        max_attempts,
                        delay,
                        error,
                    )
                    await asyncio.sleep(delay)
                    continue
                await client.aclose()
                logger.error(
                    "runtime-proxy %s runtime_id=%s region=%s method=%s "
                    "path=%s target_host=%s query_keys=%s network_type=%s "
                    "attempt=%s max_attempts=%s error=%s",
                    "timeout" if timed_out else "connect failed",
                    runtime_id,
                    region,
                    upstream_method,
                    path,
                    target_host,
                    sorted(qs.keys()),
                    endpoint_network_type,
                    attempt,
                    max_attempts,
                    error,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=504 if timed_out else 502,
                    detail=_runtime_network_error_detail(
                        endpoint_network_type,
                        timeout=timed_out,
                    ),
                ) from error
            except httpx.HTTPError as error:
                await client.aclose()
                logger.error(
                    "runtime-proxy request failed runtime_id=%s region=%s "
                    "method=%s path=%s target_host=%s query_keys=%s error=%s",
                    runtime_id,
                    region,
                    upstream_method,
                    path,
                    target_host,
                    sorted(qs.keys()),
                    error,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=502, detail="runtime_proxy_request_error"
                ) from error
        if upstream is None:
            await client.aclose()
            raise HTTPException(status_code=502, detail="runtime_proxy_request_error")
        if upstream.status_code == 401:
            _rt_conn_cache.pop((region, runtime_id), None)
        logger.info(
            "runtime-proxy upstream response runtime_id=%s region=%s method=%s "
            "path=%s target_host=%s status=%s",
            runtime_id,
            region,
            upstream_method,
            path,
            target_host,
            upstream.status_code,
        )
        if upstream.status_code >= 400:
            # Buffer error responses so we can log the body and still forward it.
            body_chunks = []
            async for chunk in upstream.aiter_raw():
                body_chunks.append(chunk)
            body_bytes = b"".join(body_chunks)
            logger.warning(
                "runtime-proxy %s %s -> %s (%s): %s",
                upstream_method,
                path,
                upstream.status_code,
                target,
                body_bytes.decode("utf-8", errors="replace")[:500],
            )
            from fastapi.responses import Response as _Resp

            media = upstream.headers.get("content-type", "application/octet-stream")
            await upstream.aclose()
            await client.aclose()
            return _Resp(
                content=body_bytes,
                status_code=upstream.status_code,
                media_type=media,
            )

        async def _body():
            try:
                if observation is None:
                    async for chunk in upstream.aiter_raw():
                        yield chunk
                else:
                    async for chunk in observed_sse_stream(
                        upstream.aiter_raw(),
                        observation,
                        _run_sse_completed,
                    ):
                        yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        media = upstream.headers.get("content-type", "application/octet-stream")
        return StreamingResponse(
            _body(), status_code=upstream.status_code, media_type=media
        )

    # ---- Auth ----------------------------------------------------------------
    # 'gateway' mode: an upstream API gateway (the AgentKit runtime gateway) has
    # already authenticated the user and forwards the identity as an
    # `Authorization: Bearer <JWT>`. Trust it — resolve the user from the token's
    # claims and run no in-app login. 'frontend' (default) keeps the existing
    # behavior where this server runs its own OAuth2 login.
    if auth_mode == "gateway":
        from fastapi.responses import JSONResponse

        @app.get("/oauth2/userinfo")
        async def _userinfo_gateway(request: Request):
            claims = _claims_from_forwarded_jwt(request.headers.get("authorization"))
            if not claims:
                # Gateway should always forward a token; if absent, report
                # unauthenticated so the SPA's auth check resolves cleanly.
                return JSONResponse({"status": "unauthenticated"}, status_code=401)
            uid = claims.get("sub") or claims.get("user_id") or claims.get("email")
            return {
                "sub": uid,
                "user_id": uid,
                "email": claims.get("email"),
                "name": claims.get("name") or claims.get("preferred_username"),
            }

        @app.get("/web/auth-config")
        async def _web_auth_config_gateway():
            # The gateway already authenticated the user — no in-app login buttons.
            return {"providers": []}

        logger.info("Auth mode: gateway (trusting upstream-forwarded JWT identity)")
    else:
        # ---- SSO (optional): VeIdentity user pool, or a generic provider via env ----
        redirect_uri = oauth2_redirect_uri or f"http://{host}:{port}/oauth2/callback"
        pool_ok = oauth2_user_pool or oauth2_user_pool_uid
        client_ok = oauth2_user_pool_client or oauth2_user_pool_client_uid
        provider_id = oauth2_provider or ""

        oauth2_config = None
        if pool_ok and client_ok:
            from veadk.auth.middleware.oauth2_auth import OAuth2Config

            oauth2_config = OAuth2Config.from_veidentity(
                user_pool_name=oauth2_user_pool,
                user_pool_uid=oauth2_user_pool_uid,
                client_name=oauth2_user_pool_client,
                client_uid=oauth2_user_pool_client_uid,
                redirect_uri=redirect_uri,
            )
            provider_id = provider_id or "veidentity"
        else:
            # Generic provider (github / google / any OIDC / custom) from env vars.
            oauth2_config = _build_generic_oauth2(provider_id or "custom", redirect_uri)
            provider_id = provider_id or "custom"

        # The SPA fetches /web/auth-config and /oauth2/userinfo on every startup, so
        # both must always return JSON. With SSO off we answer with an empty provider
        # list and a 404, which is the client contract for local username mode;
        # otherwise the SPA fallback serves HTML and `res.json()` leaves a white screen.
        providers: list[dict] = []

        if oauth2_config is not None:
            from urllib.parse import urlsplit

            from veadk.auth.middleware.oauth2_auth import setup_oauth2

            # Cookies require Secure over HTTPS (runtime deploys) but must also work
            # over plain HTTP for local serving.
            oauth2_config.cookie_secure = redirect_uri.lower().startswith("https://")
            # After logout, return to the app root derived from the callback origin
            # (so it is correct behind a public host), skipping the IdP end-session
            # redirect (its post-logout URL must be whitelisted by the IdP).
            origin = urlsplit(redirect_uri)
            oauth2_config.logout_redirect_url = f"{origin.scheme}://{origin.netloc}/"
            oauth2_config.end_session_url = None

            # Expose the configured provider to the login page (unauthenticated).
            label = (
                oauth2_provider_label
                or (
                    "BytePlus Identity"
                    if provider == "byteplus" and provider_id == "veidentity"
                    else _PROVIDER_LABELS.get(provider_id)
                )
                or provider_id.replace("_", " ").title()
            )
            providers = [
                {"id": provider_id, "label": label, "loginUrl": "/oauth2/login"}
            ]

            # Protect the API but exempt the SPA shell + this config endpoint so the
            # app can load and render its own login page when not signed in.
            setup_oauth2(
                app,
                oauth2_config,
                exempt_paths={
                    "/",
                    "/index.html",
                    "/favicon.ico",
                    "/website-integration.js",
                    "/embed/session",
                    "/embed/run_sse",
                    "/web/auth-config",
                    "/web/site-logo",
                    "/web/sandbox/codex-project-handoff/sessions",
                    "/web/sandbox/codex-project-upload/sessions",
                    "/web/ui-config",
                },
                exempt_prefixes={
                    "/assets",
                    "/skillhub",
                    "/web/sandbox/codex-project-handoff/sessions/",
                },
            )
            logger.info(
                f"OAuth2 SSO enabled (provider={provider_id}, redirect_uri={redirect_uri})"
            )
        else:
            from fastapi.responses import JSONResponse

            @app.get("/oauth2/userinfo")
            async def _userinfo_no_sso():
                # A JSON 404 is the SPA contract for local username mode and avoids
                # parsing the HTML fallback while preserving 401 for real auth failures.
                return JSONResponse({"status": "unauthenticated"}, status_code=404)

        @app.get("/web/auth-config")
        async def _web_auth_config():
            # Empty provider list when SSO is off -> the SPA shows its normal UI.
            return {"providers": providers}

    @app.get("/web/runtime-config")
    async def _web_runtime_config():
        # Report whether cloud AK/SK are present in the server environment.
        # The agent-creation workbench needs them to call cloud services, so
        # the SPA shows a "set AK/SK" notice when they are absent.
        if provider == "byteplus":
            has_creds = bool(
                os.getenv("BYTEPLUS_ACCESS_KEY") and os.getenv("BYTEPLUS_SECRET_KEY")
            )
        else:
            has_creds = bool(
                os.getenv("VOLCENGINE_ACCESS_KEY")
                and os.getenv("VOLCENGINE_SECRET_KEY")
            )
        has_creds = has_creds or os.path.exists("/var/run/secrets/iam/credential")
        return {"credentials": has_creds}

    @app.get("/web/identity/user-pools")
    async def _web_identity_user_pools(request: Request):
        """List deployable Identity user pools without exposing cloud credentials."""
        _require_agent_management(request)
        try:
            client = _identity_client()
            current_pool_uid, _ = _current_studio_identity_ids(client)
            region = _identity_region()
            return {
                "items": [
                    {
                        **pool,
                        "region": region,
                        "isCurrent": pool["uid"] == current_pool_uid,
                    }
                    for pool in client.list_user_pools()
                ]
            }
        except HTTPException:
            raise
        except Exception as error:
            logger.error("list Identity user pools failed: %s", error, exc_info=True)
            raise HTTPException(status_code=502, detail=str(error)) from error

    # ---- AgentKit account-scoped resources (A2A Spaces / Skills) ----------
    # These routes sign requests with the SERVER's Volcengine credentials (same
    # chain /web/deploy-agentkit uses) and sit under /web/* so the OAuth2
    # middleware gates them by SSO session when SSO is enabled. The browser
    # never sees AK/SK.

    def _agentkit_openapi_endpoint(region: str) -> str:
        host = os.getenv("AGENTKIT_OPENAPI_HOST", "").strip()
        endpoint = os.getenv("AGENTKIT_OPENAPI_ENDPOINT", "").strip()
        if endpoint:
            return endpoint.rstrip("/")
        if host:
            return "https://" + host.removeprefix("https://").removeprefix(
                "http://"
            ).rstrip("/")
        return agentkit_openapi_base(region, provider)

    def _agentkit_openapi_headers(
        *,
        region: str,
        action: str,
        body: str,
        endpoint: str,
        query: dict[str, str] | None = None,
    ) -> dict[str, str]:
        from veadk.a2a.registry_client import _volc_sign_v4

        ak, sk, token = _resolve_ve_credentials()
        parsed = urlparse(endpoint)
        host = parsed.netloc
        content_type = "application/json; charset=UTF-8"
        headers_to_sign = {
            "Host": host,
            "Content-Type": content_type,
        }
        signed_query = {
            "Action": action,
            "Version": "2025-10-30",
            **(query or {}),
        }
        signed_headers = _volc_sign_v4(
            access_key=ak,
            secret_key=sk,
            service="agentkit",
            region=region,
            method="POST",
            path=parsed.path or "/",
            query=signed_query,
            headers=headers_to_sign,
            body=body,
        )
        headers = {
            "Content-Type": content_type,
            "Host": host,
            **signed_headers,
        }
        if token:
            headers["X-Security-Token"] = token
        return headers

    async def _agentkit_openapi_post(
        *,
        region: str,
        action: str,
        payload: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        endpoint = _agentkit_openapi_endpoint(region)
        body = json.dumps(payload, ensure_ascii=False)
        request_query = {
            "Action": action,
            "Version": "2025-10-30",
            **(query or {}),
        }
        headers = _agentkit_openapi_headers(
            region=region,
            action=action,
            body=body,
            endpoint=endpoint,
            query=query,
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    params=request_query,
                    headers=headers,
                    content=body.encode("utf-8"),
                )
        except HTTPException:
            raise
        except httpx.HTTPError as exc:
            raise RuntimeError(f"AgentKit OpenAPI request failed: {exc}") from exc

        if response.status_code >= 400:
            request_id = ""
            try:
                metadata = response.json().get("ResponseMetadata") or {}
                request_id = metadata.get("RequestId") or ""
            except ValueError:
                pass
            suffix = f" request_id={request_id}" if request_id else ""
            raise RuntimeError(
                f"AgentKit OpenAPI returned HTTP {response.status_code}{suffix}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("AgentKit OpenAPI returned non-JSON response") from exc
        error = data.get("ResponseMetadata", {}).get("Error") or data.get("Error")
        if error:
            from veadk.integrations.agentkit.evaluation import AgentKitOpenApiError

            if isinstance(error, dict):
                code = str(error.get("Code") or "unknown")
                message = str(error.get("Message") or "")
            else:
                code = str(error)
                message = ""
            raise AgentKitOpenApiError(code, message)
        return data

    async def _runtime_json_request(
        request: Request,
        *,
        runtime: Any,
        runtime_id: str,
        region: str,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        expected_type: type = dict,
    ) -> Any:
        """Call one authorized Runtime JSON endpoint from the Studio server."""
        endpoint, apikey, auth_type, endpoint_network_type = _resolve_runtime_conn(
            runtime_id,
            region,
            runtime,
        )
        headers = _runtime_request_headers(
            request,
            apikey=apikey,
            auth_type=auth_type,
        )
        headers["Accept"] = "application/json"
        if payload is not None:
            headers["Content-Type"] = "application/json"
        target = f"{endpoint.rstrip('/')}/{path.lstrip('/')}"
        target_host = _runtime_endpoint_host(target)
        logger.info(
            "runtime json request runtime_id=%s region=%s method=%s path=%s "
            "target_host=%s payload_present=%s auth_type=%s",
            runtime_id,
            region,
            method,
            path,
            target_host,
            payload is not None,
            auth_type,
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.request(
                    method,
                    target,
                    headers=headers,
                    json=payload,
                )
            except httpx.ConnectError as error:
                logger.error(
                    "runtime json connect failed runtime_id=%s region=%s "
                    "method=%s path=%s target_host=%s error=%s",
                    runtime_id,
                    region,
                    method,
                    path,
                    target_host,
                    error,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=502,
                    detail=_runtime_network_error_detail(
                        endpoint_network_type,
                        timeout=False,
                        json_request=True,
                    ),
                ) from error
            except httpx.TimeoutException as error:
                logger.error(
                    "runtime json timeout runtime_id=%s region=%s method=%s "
                    "path=%s target_host=%s error=%s",
                    runtime_id,
                    region,
                    method,
                    path,
                    target_host,
                    error,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=504,
                    detail=_runtime_network_error_detail(
                        endpoint_network_type,
                        timeout=True,
                        json_request=True,
                    ),
                ) from error
            except httpx.HTTPError as error:
                logger.error(
                    "runtime json request failed runtime_id=%s region=%s "
                    "method=%s path=%s target_host=%s error=%s",
                    runtime_id,
                    region,
                    method,
                    path,
                    target_host,
                    error,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=502, detail="runtime_json_request_error"
                ) from error
        if response.status_code >= 400:
            detail = response.text.strip()[:2000]
            logger.warning(
                "runtime json upstream error runtime_id=%s region=%s method=%s "
                "path=%s target_host=%s status=%s body=%s",
                runtime_id,
                region,
                method,
                path,
                target_host,
                response.status_code,
                detail[:500],
            )
            raise HTTPException(
                status_code=response.status_code,
                detail=detail or f"Runtime returned HTTP {response.status_code}",
            )
        try:
            data = response.json()
        except ValueError as error:
            content_type = response.headers.get("content-type", "unknown")
            raise RuntimeError(
                "Runtime returned a non-JSON response "
                f"(HTTP {response.status_code}, Content-Type: {content_type})"
            ) from error
        if not isinstance(data, expected_type):
            raise RuntimeError("Runtime returned an invalid JSON response")
        return data

    def _runtime_network_payload(runtime: Any) -> dict[str, Any]:
        network_configurations = list(
            getattr(runtime, "network_configurations", None) or []
        )
        network_types = {
            str(getattr(item, "network_type", "") or "").strip().lower()
            for item in network_configurations
        }
        private_network = next(
            (
                item
                for item in network_configurations
                if str(getattr(item, "network_type", "") or "").strip().lower()
                == "private"
            ),
            None,
        )
        mode = (
            "both"
            if "public" in network_types and private_network is not None
            else "private"
            if private_network is not None
            else "public"
        )
        payload: dict[str, Any] = {"mode": mode}
        vpc_configuration = getattr(private_network, "vpc_configuration", None)
        if vpc_configuration is None:
            return payload

        vpc_id = str(getattr(vpc_configuration, "vpc_id", "") or "").strip()
        if vpc_id:
            payload["vpcId"] = vpc_id
        subnet_ids = getattr(vpc_configuration, "subnet_ids", None) or []
        if subnet_ids:
            payload["subnetIds"] = ",".join(str(item) for item in subnet_ids)
        shared_internet = getattr(
            vpc_configuration,
            "enable_shared_internet_access",
            None,
        )
        if shared_internet is not None:
            payload["enableSharedInternetAccess"] = bool(shared_internet)
        return payload

    def _runtime_update_payload(runtime: Any, region: str) -> dict[str, Any]:
        tags = _runtime_tags(runtime)
        return {
            "runtimeId": str(getattr(runtime, "runtime_id", "") or ""),
            "name": str(getattr(runtime, "name", "") or ""),
            "status": str(getattr(runtime, "status", "") or ""),
            "region": region,
            "currentVersion": getattr(runtime, "current_version_number", None),
            "managed": tags.get("veadk:managed") == "true",
            "envs": [
                {
                    "key": str(getattr(item, "key", "") or ""),
                    "value": str(getattr(item, "value", "") or ""),
                }
                for item in (getattr(runtime, "envs", None) or [])
                if getattr(item, "key", None)
                and str(getattr(item, "key", "") or "") != "MODEL_AGENT_API_KEY"
            ],
            "network": _runtime_network_payload(runtime),
        }

    def _runtime_update_result(
        runtime: Any,
        runtime_payload: dict[str, Any],
        app_name: str | None,
        *,
        can_update: bool,
        reason: str = "",
        reason_code: str = "",
        agent: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], Any]:
        agent_payload = {**(agent or {}), "appName": app_name} if app_name else None
        return (
            {
                "canUpdate": can_update,
                "reason": reason,
                "reasonCode": reason_code,
                "runtime": runtime_payload,
                "agent": agent_payload,
            },
            runtime,
        )

    async def _runtime_update_capability_details(
        request: Request,
        *,
        runtime_id: str,
        region: str,
        app_name: str | None = None,
    ) -> tuple[dict[str, Any], Any]:
        try:
            runtime = _authorized_runtime(
                request,
                runtime_id,
                region,
                coded_access_error=True,
            )
        except HTTPException:
            raise
        except Exception as error:
            if is_agentkit_resource_not_found(error):
                raise HTTPException(
                    status_code=404,
                    detail="runtime_not_found",
                ) from error
            logger.error(
                "resolve runtime update capability failed runtime_id=%s region=%s",
                runtime_id,
                region,
                exc_info=True,
            )
            raise HTTPException(
                status_code=502,
                detail="runtime_lookup_failed",
            ) from error

        runtime_payload = _runtime_update_payload(runtime, region)

        try:
            apps = await _runtime_json_request(
                request,
                runtime=runtime,
                runtime_id=runtime_id,
                region=region,
                method="GET",
                path="list-apps",
                expected_type=list,
            )
        except HTTPException as error:
            if error.status_code == 404:
                return _runtime_update_result(
                    runtime,
                    runtime_payload,
                    app_name,
                    can_update=False,
                    reason="该 Runtime 不支持 list-apps 接口，无法更新。",
                    reason_code="runtime_list_apps_unsupported",
                )
            if error.status_code >= 500:
                return _runtime_update_result(
                    runtime,
                    runtime_payload,
                    app_name,
                    can_update=False,
                    reason="暂时无法读取该 Runtime 的 Agent 信息，请稍后重试。",
                    reason_code="runtime_list_apps_unavailable",
                )
            raise HTTPException(
                status_code=error.status_code,
                detail="runtime_update_capability_failed",
            ) from error
        except RuntimeError:
            return _runtime_update_result(
                runtime,
                runtime_payload,
                app_name,
                can_update=False,
                reason="该 Runtime 的 list-apps 返回格式不兼容，无法更新。",
                reason_code="runtime_list_apps_invalid",
            )

        if not all(isinstance(app, str) and app for app in apps):
            return _runtime_update_result(
                runtime,
                runtime_payload,
                app_name,
                can_update=False,
                reason="该 Runtime 的 list-apps 返回格式不兼容，无法更新。",
                reason_code="runtime_list_apps_invalid",
            )
        if not apps:
            return _runtime_update_result(
                runtime,
                runtime_payload,
                app_name,
                can_update=False,
                reason="该 Runtime 未提供可更新 Agent。",
                reason_code="runtime_no_apps",
            )
        if len(apps) > 1:
            return _runtime_update_result(
                runtime,
                runtime_payload,
                app_name,
                can_update=False,
                reason="该 Runtime 包含多个 Agent，暂不支持原地更新。",
                reason_code="runtime_multiple_apps",
            )
        runtime_app_name = str(apps[0])
        if app_name and app_name != runtime_app_name:
            return _runtime_update_result(
                runtime,
                runtime_payload,
                app_name,
                can_update=False,
                reason="该 Runtime 中不存在当前 Agent，无法更新。",
                reason_code="runtime_app_not_found",
            )

        app_name = runtime_app_name

        agent_info_path = f"web/agent-info/{quote(app_name, safe='')}"
        try:
            agent = await _runtime_json_request(
                request,
                runtime=runtime,
                runtime_id=runtime_id,
                region=region,
                method="GET",
                path=agent_info_path,
            )
        except HTTPException as error:
            if error.status_code == 404:
                return _runtime_update_result(
                    runtime,
                    runtime_payload,
                    app_name,
                    can_update=False,
                    reason="该 Runtime 不支持 Agent 信息接口，无法更新。",
                    reason_code="runtime_agent_info_unsupported",
                )
            if error.status_code >= 500:
                return _runtime_update_result(
                    runtime,
                    runtime_payload,
                    app_name,
                    can_update=False,
                    reason="暂时无法读取该 Runtime 的 Agent 配置，请稍后重试。",
                    reason_code="runtime_agent_info_unavailable",
                )
            raise HTTPException(
                status_code=error.status_code,
                detail="runtime_update_capability_failed",
            ) from error
        except RuntimeError:
            return _runtime_update_result(
                runtime,
                runtime_payload,
                app_name,
                can_update=False,
                reason="该 Runtime 的 Agent 信息返回格式不兼容，无法更新。",
                reason_code="runtime_agent_info_invalid",
            )

        return _runtime_update_result(
            runtime,
            runtime_payload,
            app_name,
            can_update=True,
            agent=agent,
        )

    @app.get("/web/runtime-update-capability")
    async def _web_runtime_update_capability(
        request: Request,
        runtimeId: str = Query(..., min_length=1),
        appName: str | None = Query(default=None, min_length=1),
        region: str = Query(default="", min_length=0),
    ) -> dict[str, Any]:
        _require_agent_management(request)
        region = _coerce_cloud_region(region)
        capability, _runtime = await _runtime_update_capability_details(
            request,
            runtime_id=runtimeId,
            region=region,
            app_name=appName,
        )
        return capability

    @app.post("/web/evaluation/feedback")
    async def _web_message_feedback(
        feedback: _MessageFeedbackRequest,
        request: Request,
    ) -> dict[str, Any]:
        """Persist one message rating in ADK state and AgentKit evaluation sets."""
        feedback.region = _coerce_cloud_region(feedback.region)
        principal = _current_principal(request)
        if (
            principal is None
            or feedback.user_id.casefold() not in principal.identifiers
        ):
            raise HTTPException(
                status_code=403,
                detail="Feedback can only be submitted for the current user",
            )
        runtime = _authorized_runtime(
            request,
            feedback.runtime_id,
            feedback.region,
            coded_access_error=True,
        )
        if provider == "byteplus":
            return {
                "rating": None,
                "evaluationSetId": None,
                "evaluationSetName": None,
                "workspaceId": None,
                "evaluationItemId": None,
                "syncStatus": "synced",
                "statePersistence": "browser",
                "updatedAt": time.time(),
            }
        session_path = (
            f"apps/{quote(feedback.app_name, safe='')}/users/"
            f"{quote(feedback.user_id, safe='')}/sessions/"
            f"{quote(feedback.session_id, safe='')}"
        )
        agent_info_path = f"web/agent-info/{quote(feedback.app_name, safe='')}"

        async def _feedback_agent_info() -> dict[str, Any]:
            try:
                return await _runtime_json_request(
                    request,
                    runtime=runtime,
                    runtime_id=feedback.runtime_id,
                    region=feedback.region,
                    method="GET",
                    path=agent_info_path,
                )
            except HTTPException as error:
                if error.status_code != 404:
                    raise
                logger.info(
                    "Runtime %s does not expose Agent info; using app name %s "
                    "for evaluation feedback",
                    feedback.runtime_id,
                    feedback.app_name,
                )
                return {}

        try:
            session, agent_info = await asyncio.gather(
                _runtime_json_request(
                    request,
                    runtime=runtime,
                    runtime_id=feedback.runtime_id,
                    region=feedback.region,
                    method="GET",
                    path=session_path,
                ),
                _feedback_agent_info(),
            )
            from veadk.integrations.agentkit.evaluation import (
                AgentKitEvaluationDatasetsClient,
            )
            from veadk.integrations.agentkit.evaluation.feedback import (
                extract_feedback_sample,
                feedback_item_key,
                feedback_state_key,
            )

            agent_name = str(agent_info.get("name") or feedback.app_name)
            project_name = str(getattr(runtime, "project_name", "") or "default")
            sample = extract_feedback_sample(
                session,
                target_event_id=feedback.event_id,
                runtime_id=feedback.runtime_id,
                agent_name=agent_name,
                user_id=feedback.user_id,
            )
            state_key = feedback_state_key(feedback.event_id)
            session_state = session.get("state")
            previous_value = (
                session_state.get(state_key)
                if isinstance(session_state, dict)
                else None
            )
            previous: dict[str, Any] = (
                previous_value if isinstance(previous_value, dict) else {}
            )

            async def _evaluation_post(
                *,
                action: str,
                payload: dict[str, Any],
                query: dict[str, str] | None = None,
            ) -> dict[str, Any]:
                return await _agentkit_openapi_post(
                    region=feedback.region,
                    action=action,
                    payload=payload,
                    query=query,
                )

            evaluation = AgentKitEvaluationDatasetsClient(
                _evaluation_post,
                project_name=project_name,
            )
            item_key = feedback_item_key(
                project_name=project_name,
                runtime_id=feedback.runtime_id,
                session_id=feedback.session_id,
                message_id=feedback.event_id,
            )
            deleted_previous_item_ids: set[str] = set()
            evaluation_set = None
            evaluation_item = None
            if feedback.rating is not None:
                evaluation_set = await evaluation.ensure_feedback_set(
                    agent_name,
                    feedback.rating,
                )
                evaluation_item = await evaluation.upsert_item(
                    evaluation_set_id=evaluation_set.id,
                    workspace_id=evaluation_set.workspace_id,
                    item_key=item_key,
                    fields=sample.fields(
                        rating=feedback.rating,
                        comment=feedback.comment,
                    ),
                )

            previous_rating = str(previous.get("rating") or "")
            previous_item_id = str(previous.get("evaluationItemId") or "")
            previous_set_id = str(previous.get("evaluationSetId") or "")
            previous_workspace_id = str(previous.get("workspaceId") or "")
            replacing_previous = previous_item_id and (
                feedback.rating is None or previous_rating != feedback.rating
            )
            if replacing_previous and previous_set_id and previous_workspace_id:
                await evaluation.delete_item(
                    evaluation_set_id=previous_set_id,
                    workspace_id=previous_workspace_id,
                    item_id=previous_item_id,
                )
                deleted_previous_item_ids.add(previous_item_id)

            fallback_delete_ratings: tuple[str, ...] = ()
            if feedback.rating is None:
                fallback_delete_ratings = ("good", "bad")
            elif feedback.rating == "good":
                fallback_delete_ratings = ("bad",)
            elif feedback.rating == "bad":
                fallback_delete_ratings = ("good",)
            for stale_rating in fallback_delete_ratings:
                stale_set, stale_items = await evaluation.list_feedback_items(
                    agent_name=agent_name,
                    rating=stale_rating,
                    page_size=200,
                )
                if stale_set is None:
                    continue
                for stale_item in stale_items:
                    if (
                        stale_item.item_key != item_key
                        or stale_item.id in deleted_previous_item_ids
                    ):
                        continue
                    await evaluation.delete_item(
                        evaluation_set_id=stale_set.id,
                        workspace_id=stale_set.workspace_id,
                        item_id=stale_item.id,
                    )
                    deleted_previous_item_ids.add(stale_item.id)

            feedback_state = {
                "rating": feedback.rating,
                "comment": feedback.comment if feedback.rating is not None else "",
                "evaluationSetId": evaluation_set.id if evaluation_set else None,
                "evaluationSetName": evaluation_set.name if evaluation_set else None,
                "workspaceId": (
                    evaluation_set.workspace_id if evaluation_set else None
                ),
                "evaluationItemId": evaluation_item.id if evaluation_item else None,
                "syncStatus": "synced",
                "statePersistence": "runtime",
                "updatedAt": time.time(),
            }
            try:
                await _runtime_json_request(
                    request,
                    runtime=runtime,
                    runtime_id=feedback.runtime_id,
                    region=feedback.region,
                    method="PATCH",
                    path=session_path,
                    payload={"state_delta": {state_key: feedback_state}},
                )
            except HTTPException as error:
                if error.status_code != 404:
                    raise
                feedback_state["statePersistence"] = "browser"
                logger.warning(
                    "Runtime %s does not expose Session PATCH through its gateway; "
                    "feedback state will use the browser compatibility cache",
                    feedback.runtime_id,
                )
            return feedback_state
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(
                status_code=502,
                detail=(
                    "同步反馈到 AgentKit 评测集失败：" + _safe_exception_detail(error)
                ),
            ) from error

    @app.get("/web/evaluation/feedback-cases")
    async def _web_feedback_cases(
        request: Request,
        runtimeId: str = Query(..., min_length=1),
        appName: str = Query(..., min_length=1),
        region: str = Query(default="", min_length=0),
        page_size: int = Query(default=100, ge=1, le=200),
    ) -> dict[str, Any]:
        """List AgentKit evaluation-set items created from message feedback."""
        region = _coerce_cloud_region(region)
        runtime = _authorized_runtime(
            request,
            runtimeId,
            region,
            coded_access_error=True,
        )
        agent_info_path = f"web/agent-info/{quote(appName, safe='')}"
        try:
            try:
                agent_info = await _runtime_json_request(
                    request,
                    runtime=runtime,
                    runtime_id=runtimeId,
                    region=region,
                    method="GET",
                    path=agent_info_path,
                )
            except HTTPException as error:
                if error.status_code != 404:
                    raise
                agent_info = {"name": appName}
            from frontend.server.evaluation_automation.repository import (
                AgentKitAutoEvaluationRepository,
            )
            from veadk.integrations.agentkit.evaluation import (
                AgentKitEvaluationDatasetsClient,
            )

            agent_name = str(agent_info.get("name") or appName)
            project_name = str(getattr(runtime, "project_name", "") or "default")

            async def _evaluation_post(
                *,
                action: str,
                payload: dict[str, Any],
                query: dict[str, str] | None = None,
            ) -> dict[str, Any]:
                return await _agentkit_openapi_post(
                    region=region,
                    action=action,
                    payload=payload,
                    query=query,
                )

            evaluation = AgentKitEvaluationDatasetsClient(
                _evaluation_post,
                project_name=project_name,
            )
            response_sets: list[dict[str, Any]] = []
            response_items: list[dict[str, Any]] = []
            for rating in ("good", "bad"):
                evaluation_set, items = await evaluation.list_feedback_items(
                    agent_name=agent_name,
                    rating=rating,
                    page_size=page_size,
                )
                if evaluation_set is None:
                    response_sets.append(
                        {
                            "kind": rating,
                            "evaluationSetId": None,
                            "evaluationSetName": None,
                            "workspaceId": None,
                            "itemCount": 0,
                        }
                    )
                    continue
                response_sets.append(
                    {
                        "kind": rating,
                        "evaluationSetId": evaluation_set.id,
                        "evaluationSetName": evaluation_set.name,
                        "workspaceId": evaluation_set.workspace_id,
                        "itemCount": len(items),
                    }
                )
                for item in items:
                    fields = item.fields
                    comment = fields.get("feedback_comment", "")
                    is_annotated_bad_case = rating == "bad" and bool(comment.strip())
                    response_items.append(
                        {
                            "id": item.id or item.item_key,
                            "itemKey": item.item_key,
                            "kind": rating,
                            "input": fields.get("input", ""),
                            "output": fields.get("output", ""),
                            "referenceOutput": fields.get("reference_output", ""),
                            "comment": comment,
                            "agentName": fields.get("agent_name", agent_name),
                            "sessionId": fields.get("session_id", ""),
                            "messageId": fields.get("message_id", ""),
                            "runtimeId": fields.get("runtime_id", runtimeId),
                            "invocationId": fields.get("invocation_id", ""),
                            "userId": fields.get("user_id", ""),
                            "createdAt": fields.get("created_at", ""),
                            "evaluationSetId": evaluation_set.id,
                            "evaluationSetName": evaluation_set.name,
                            "workspaceId": evaluation_set.workspace_id,
                            "source": "user",
                            "score": 0 if is_annotated_bad_case else None,
                            "reason": comment if is_annotated_bad_case else "",
                        }
                    )
            if studio:
                automatic = AgentKitAutoEvaluationRepository(
                    _evaluation_post,
                    project_name=project_name,
                )
                automatic_cases = await automatic.list_cases(
                    agent_name=agent_name,
                    page_size=page_size,
                )
                response_items.extend(
                    case.model_dump(mode="json", by_alias=True)
                    for case in automatic_cases
                )
                for item in response_sets:
                    item["itemCount"] = sum(
                        case["kind"] == item["kind"] for case in response_items
                    )
            return {
                "agentName": agent_name,
                "runtimeId": runtimeId,
                "region": region,
                "projectName": project_name,
                "sets": response_sets,
                "items": response_items,
            }
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            if provider == "byteplus" and "AgentKit OpenAPI returned HTTP 404" in str(
                error
            ):
                return {
                    "agentName": appName,
                    "runtimeId": runtimeId,
                    "region": region,
                    "projectName": getattr(runtime, "project_name", "") or "default",
                    "sets": [],
                    "items": [],
                    "unsupported": True,
                    "unsupportedMessage": "BytePlus 暂不支持 AgentKit 评测集。",
                }
            raise HTTPException(
                status_code=502,
                detail="读取 AgentKit 评测集失败：" + _safe_exception_detail(error),
            ) from error

    @app.post("/web/evaluation/feedback-cases/delete")
    async def _web_delete_feedback_cases(
        deletion: _DeleteFeedbackCasesRequest,
        request: Request,
    ) -> dict[str, Any]:
        """Remove feedback cases and clear their thumbs state without deleting chat."""
        deletion.region = _coerce_cloud_region(deletion.region)
        requested_ids = {
            item_id.strip()
            for item_id in deletion.item_ids
            if item_id and item_id.strip()
        }
        if not requested_ids:
            raise HTTPException(status_code=400, detail="No feedback cases selected")
        runtime = _authorized_runtime(
            request,
            deletion.runtime_id,
            deletion.region,
            coded_access_error=True,
        )
        agent_info_path = f"web/agent-info/{quote(deletion.app_name, safe='')}"
        try:
            try:
                agent_info = await _runtime_json_request(
                    request,
                    runtime=runtime,
                    runtime_id=deletion.runtime_id,
                    region=deletion.region,
                    method="GET",
                    path=agent_info_path,
                )
            except HTTPException as error:
                if error.status_code != 404:
                    raise
                agent_info = {"name": deletion.app_name}
            from frontend.server.evaluation_automation.repository import (
                AgentKitAutoEvaluationRepository,
            )
            from veadk.integrations.agentkit.evaluation import (
                AgentKitEvaluationDatasetsClient,
            )
            from veadk.integrations.agentkit.evaluation.feedback import (
                feedback_state_key,
            )

            agent_name = str(agent_info.get("name") or deletion.app_name)
            project_name = str(getattr(runtime, "project_name", "") or "default")

            async def _evaluation_post(
                *,
                action: str,
                payload: dict[str, Any],
                query: dict[str, str] | None = None,
            ) -> dict[str, Any]:
                return await _agentkit_openapi_post(
                    region=deletion.region,
                    action=action,
                    payload=payload,
                    query=query,
                )

            evaluation = AgentKitEvaluationDatasetsClient(
                _evaluation_post,
                project_name=project_name,
            )
            matched: list[tuple[str, str, dict[str, str]]] = []
            for rating in ("good", "bad"):
                evaluation_set, items = await evaluation.list_feedback_items(
                    agent_name=agent_name,
                    rating=rating,
                    page_size=200,
                )
                if evaluation_set is None:
                    continue
                for item in items:
                    if item.id not in requested_ids:
                        continue
                    matched.append(
                        (evaluation_set.id, evaluation_set.workspace_id, item.fields)
                    )
                    await evaluation.delete_item(
                        evaluation_set_id=evaluation_set.id,
                        workspace_id=evaluation_set.workspace_id,
                        item_id=item.id,
                    )

            automatic_deleted = 0
            if studio:
                automatic = AgentKitAutoEvaluationRepository(
                    _evaluation_post,
                    project_name=project_name,
                )
                automatic_cases = await automatic.list_cases(
                    agent_name=agent_name,
                    page_size=200,
                )
                for case in automatic_cases:
                    if case.id not in requested_ids:
                        continue
                    await evaluation.delete_item(
                        evaluation_set_id=case.evaluation_set_id,
                        workspace_id=case.workspace_id,
                        item_id=case.id,
                    )
                    automatic_deleted += 1

            for _set_id, _workspace_id, fields in matched:
                session_id = str(fields.get("session_id") or "")
                message_id = str(fields.get("message_id") or "")
                user_id = str(fields.get("user_id") or "")
                if not session_id or not message_id or not user_id:
                    continue
                session_path = (
                    f"apps/{quote(deletion.app_name, safe='')}/users/"
                    f"{quote(user_id, safe='')}/sessions/"
                    f"{quote(session_id, safe='')}"
                )
                feedback_state = {
                    "rating": None,
                    "evaluationSetId": None,
                    "evaluationSetName": None,
                    "workspaceId": None,
                    "evaluationItemId": None,
                    "syncStatus": "synced",
                    "statePersistence": "runtime",
                    "updatedAt": time.time(),
                }
                try:
                    await _runtime_json_request(
                        request,
                        runtime=runtime,
                        runtime_id=deletion.runtime_id,
                        region=deletion.region,
                        method="PATCH",
                        path=session_path,
                        payload={
                            "state_delta": {
                                feedback_state_key(message_id): feedback_state,
                            }
                        },
                    )
                except HTTPException as error:
                    if error.status_code != 404:
                        raise
                    logger.warning(
                        "Runtime %s does not expose Session PATCH; feedback case "
                        "was deleted but message state could not be cleared",
                        deletion.runtime_id,
                    )
            return {"deletedCount": len(matched) + automatic_deleted}
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(
                status_code=502,
                detail="删除 AgentKit 评测案例失败：" + _safe_exception_detail(error),
            ) from error

    @app.get("/web/a2a-spaces")
    async def _web_list_a2a_spaces(
        region: str = "",
        page_size: int = Query(default=100, ge=1, le=100),
        project: str | None = None,
    ):
        """List all AgentKit A2A Spaces visible to server credentials."""
        region = _coerce_cloud_region(region)
        try:
            _resolve_ve_credentials()
        except HTTPException:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Server BytePlus credentials not configured "
                    "(set BYTEPLUS_ACCESS_KEY/BYTEPLUS_SECRET_KEY)."
                    if provider == "byteplus"
                    else "Server Volcengine credentials not configured "
                    "(set VOLCENGINE_ACCESS_KEY/SECRET_KEY)."
                ),
            )

        all_items: list[dict[str, Any]] = []
        total_count = 0
        page = 1
        project_name = (project or "").strip() or None

        try:
            while True:
                payload: dict[str, Any] = {
                    "PageNumber": page,
                    "PageSize": page_size,
                }
                if project_name:
                    payload["ProjectName"] = project_name
                data = await _agentkit_openapi_post(
                    region=region,
                    action="ListA2aSpaces",
                    payload=payload,
                )
                result = data.get("Result") or {}
                total_count = int(result.get("TotalCount") or 0)
                items = result.get("Items") or []
                item_count = len(items)
                for space in items:
                    if not isinstance(space, dict):
                        continue
                    all_items.append(
                        {
                            "id": space.get("Id") or "",
                            "name": space.get("Name") or "",
                            "intentEnabled": bool(space.get("IntentEnabled")),
                            "projectName": space.get("ProjectName") or "",
                            "tags": [
                                {
                                    "key": tag.get("Key") or "",
                                    "value": tag.get("Value") or "",
                                }
                                for tag in space.get("Tags") or []
                                if isinstance(tag, dict)
                            ],
                            "isDefault": bool(space.get("IsDefault")),
                            "region": region,
                        }
                    )
                if (
                    item_count == 0
                    or (total_count > 0 and len(all_items) >= total_count)
                    or (total_count <= 0 and item_count < page_size)
                ):
                    break
                page += 1
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"ListA2aSpaces error for {region}: {e}", exc_info=True)
            raise HTTPException(
                status_code=502,
                detail="暂时无法加载 AgentKit 智能体中心，请稍后重试。",
            )

        return {
            "items": all_items,
            "totalCount": total_count or len(all_items),
            "page": 1,
            "pageSize": page_size,
        }

    def _viking_knowledgebase_host(region: str) -> tuple[str, str]:
        if provider == "byteplus":
            return (
                f"api-knowledgebase.mlp.{region}.bytepluses.com",
                "https",
            )
        return (f"api-knowledgebase.mlp.{region}.volces.com", "https")

    def _viking_memory_host(region: str) -> tuple[str, str]:
        if provider == "byteplus":
            return (DEFAULT_BYTEPLUS_VIKING_MEMORY_HOST, "https")
        return (f"api-knowledgebase.mlp.{region}.volces.com", "https")

    def _collection_attr(collection: Any, name: str, fallback: Any = "") -> Any:
        value = getattr(collection, name, None)
        if value is not None:
            return value
        data = getattr(collection, "__dict__", {})
        if isinstance(data, dict):
            return data.get(name, fallback)
        return fallback

    def _append_unique_viking_collection_item(
        items: list[dict[str, Any]],
        seen: set[tuple[str, str, str, str]],
        item: dict[str, Any],
    ) -> None:
        key = (
            str(item.get("sourceKind") or ""),
            str(item.get("projectName") or ""),
            str(item.get("region") or ""),
            str(item.get("id") or ""),
        )
        if not key[-1] or key in seen:
            return
        seen.add(key)
        items.append(item)

    def _viking_memory_response_items(response: Any) -> list[Any]:
        if not isinstance(response, dict):
            return []
        result = (
            response.get("Result")
            or response.get("result")
            or response.get("Data")
            or response.get("data")
            or response
        )
        if isinstance(result, list):
            return result
        if not isinstance(result, dict):
            return []
        for key in (
            "Collections",
            "collections",
            "CollectionList",
            "collection_list",
            "Items",
            "items",
            "List",
            "list",
            "ResultList",
            "result_list",
        ):
            value = result.get(key)
            if isinstance(value, list):
                return value
        return []

    def _viking_memory_response_total(response: Any, item_count: int) -> int:
        if not isinstance(response, dict):
            return item_count
        result = (
            response.get("Result")
            or response.get("result")
            or response.get("Data")
            or response.get("data")
            or response
        )
        if not isinstance(result, dict):
            return item_count
        for key in ("TotalCount", "total_count", "Total", "total"):
            try:
                return int(result.get(key) or item_count)
            except (TypeError, ValueError):
                continue
        return item_count

    def _viking_memory_field(collection: Any, *names: str) -> Any:
        for name in names:
            if isinstance(collection, dict):
                value = collection.get(name)
                if value is not None:
                    return value
                snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
                value = collection.get(snake)
                if value is not None:
                    return value
            value = getattr(collection, name, None)
            if value is not None:
                return value
            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
            value = getattr(collection, snake, None)
            if value is not None:
                return value
        return None

    def _normalize_viking_memory_item(
        collection: Any,
        *,
        project_name: str,
        region: str,
    ) -> dict[str, Any] | None:
        name = str(
            _viking_memory_field(
                collection,
                "CollectionName",
                "collection_name",
                "Name",
                "name",
            )
            or ""
        ).strip()
        if not name:
            return None
        memory_types = _viking_memory_field(
            collection,
            "BuiltinEventTypes",
            "builtin_event_types",
            "MemoryTypes",
            "memory_types",
        )
        if isinstance(memory_types, str):
            memory_types = [
                item.strip() for item in memory_types.split(",") if item.strip()
            ]
        elif not isinstance(memory_types, list):
            memory_types = []
        return {
            "id": name,
            "name": name,
            "description": str(
                _viking_memory_field(collection, "Description", "description") or ""
            ),
            "projectName": str(
                _viking_memory_field(
                    collection,
                    "ProjectName",
                    "project_name",
                    "Project",
                    "project",
                )
                or project_name
            ),
            "region": region,
            "resourceId": str(
                _viking_memory_field(
                    collection,
                    "ResourceId",
                    "resource_id",
                    "ID",
                    "id",
                )
                or ""
            ),
            "updatedAt": str(
                _viking_memory_field(
                    collection,
                    "UpdateTime",
                    "update_time",
                    "UpdatedAt",
                    "updated_at",
                )
                or ""
            ),
            "memoryTypes": memory_types,
        }

    def _agentkit_viking_index(name: str, provider_knowledge_id: str) -> str:
        provider_id = (provider_knowledge_id or "").strip()
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", provider_id):
            return provider_id
        return name

    def _list_agentkit_viking_knowledge_bases(
        *,
        access_key: str,
        secret_key: str,
        session_token: str | None,
        region: str,
        project: str | None,
    ) -> list[dict[str, Any]]:
        from agentkit.sdk.knowledge.client import AgentkitKnowledgeClient
        from agentkit.sdk.knowledge import types as knowledge_types

        client = AgentkitKnowledgeClient(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token or "",
            region=region,
        )
        items: list[dict[str, Any]] = []
        next_token = ""
        seen_tokens: set[str] = set()
        for _ in range(100):
            request = knowledge_types.ListKnowledgeBasesRequest(
                max_results=100,
                next_token=next_token or None,
                project_name=project,
                filters=[
                    knowledge_types.FiltersItemForListKnowledgeBases(
                        name="provider_type",
                        values=["VIKINGDB_KNOWLEDGE"],
                    )
                ],
            )
            response = client.list_knowledge_bases(request)
            for knowledge in response.knowledge_bases or []:
                name = str(getattr(knowledge, "name", "") or "").strip()
                knowledge_id = str(getattr(knowledge, "knowledge_id", "") or "").strip()
                provider_id = str(
                    getattr(knowledge, "provider_knowledge_id", "") or ""
                ).strip()
                index = _agentkit_viking_index(name, provider_id)
                if not index:
                    continue
                resource_id = provider_id if provider_id.startswith("kb-") else ""
                if not resource_id and knowledge_id.startswith("kb-"):
                    resource_id = knowledge_id
                items.append(
                    {
                        "id": index,
                        "name": name or index,
                        "description": str(getattr(knowledge, "description", "") or ""),
                        "projectName": str(
                            getattr(knowledge, "project_name", "") or project or ""
                        ),
                        "region": str(getattr(knowledge, "region", "") or region),
                        "updatedAt": str(
                            getattr(knowledge, "last_update_time", "") or ""
                        ),
                        "resourceId": resource_id,
                        "agentkitKnowledgeId": knowledge_id,
                        "providerKnowledgeId": provider_id,
                        "providerType": str(
                            getattr(knowledge, "provider_type", "") or ""
                        ),
                        "status": str(getattr(knowledge, "status", "") or ""),
                        "sourceKind": "agentkit",
                        "sourceLabel": "AgentKit Knowledge Base",
                    }
                )
            token = str(getattr(response, "next_token", "") or "")
            if not token or token in seen_tokens:
                break
            seen_tokens.add(token)
            next_token = token
        return items

    def _list_vikingdb_vector_collections(
        *,
        access_key: str,
        secret_key: str,
        session_token: str | None,
        region: str,
        project: str | None,
    ) -> list[dict[str, Any]]:
        from volcenginesdkcore import ApiClient
        from volcenginesdkcore.configuration import Configuration
        from volcenginesdkvikingdb import ListVikingdbCollectionRequest, VIKINGDBApi

        config = Configuration()
        config.ak = access_key
        config.sk = secret_key
        config.session_token = session_token or ""
        config.region = region
        config.host = _vikingdb_openapi_host(provider)
        client = VIKINGDBApi(ApiClient(config))

        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for project_name in _candidate_vikingdb_projects(project):
            page_number = 1
            page_size = 100
            while True:
                request = ListVikingdbCollectionRequest(
                    page_number=page_number,
                    page_size=page_size,
                    project_name=project_name,
                )
                try:
                    response = client.list_vikingdb_collection(request)
                except Exception:
                    logger.debug(
                        "skip VikingDB vector collection project %s in %s",
                        project_name or "<account-default>",
                        region,
                        exc_info=True,
                    )
                    break
                collections = list(getattr(response, "collections", None) or [])
                for collection in collections:
                    name = str(getattr(collection, "collection_name", "") or "")
                    if not name:
                        continue
                    resolved_project = str(
                        getattr(collection, "project_name", "") or project_name or ""
                    )
                    key = (resolved_project, region, name)
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(
                        {
                            "id": name,
                            "name": name,
                            "description": str(
                                getattr(collection, "description", "") or ""
                            ),
                            "projectName": resolved_project,
                            "region": region,
                            "updatedAt": str(
                                getattr(collection, "update_time", "") or ""
                            ),
                            "resourceId": str(
                                getattr(collection, "resource_id", "") or ""
                            ),
                            "sourceKind": "vector",
                            "sourceLabel": "Vector DB",
                            "indexCount": getattr(collection, "index_count", None),
                        }
                    )
                total_count = int(getattr(response, "total_count", 0) or 0)
                if not collections or page_number * page_size >= total_count:
                    break
                page_number += 1
        return items

    def _list_viking_memory_collections(
        *,
        access_key: str,
        secret_key: str,
        session_token: str | None,
        region: str,
        project: str | None,
    ) -> list[dict[str, Any]]:
        from veadk.integrations.ve_viking_db_memory.ve_viking_db_memory import (
            VikingDBMemoryClient,
        )

        host, scheme = _viking_memory_host(region)
        client = VikingDBMemoryClient(
            host=host,
            region=region,
            ak=access_key,
            sk=secret_key,
            sts_token=session_token or "",
            scheme=scheme,
        )

        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        attempts = 0
        failures = 0
        page_size = 100
        for project_name in _candidate_viking_memory_projects(project):
            page_number = 1
            for _ in range(100):
                attempts += 1
                try:
                    response = client.list_collections(
                        project=project_name,
                        page_number=page_number,
                        page_size=page_size,
                    )
                except Exception:
                    failures += 1
                    logger.debug(
                        "skip VikingDB memory project %s in %s",
                        project_name,
                        region,
                        exc_info=True,
                    )
                    break
                collections = _viking_memory_response_items(response)
                for collection in collections:
                    item = _normalize_viking_memory_item(
                        collection,
                        project_name=project_name,
                        region=region,
                    )
                    if not item:
                        continue
                    key = (item["projectName"], item["region"], item["id"])
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(item)
                total_count = _viking_memory_response_total(
                    response,
                    len(collections),
                )
                if (
                    not collections
                    or page_number * page_size >= total_count
                    or len(collections) < page_size
                ):
                    break
                page_number += 1
        if attempts > 0 and failures == attempts and not items:
            raise RuntimeError("all VikingDB memory list requests failed")
        return items

    @app.get("/web/viking-memories")
    async def _web_list_viking_memories(
        region: str = "",
        project: str = "",
    ):
        """List VikingDB Memory collections visible to server creds."""
        region = _coerce_cloud_region(region)

        try:
            ak, sk, token = _resolve_ve_credentials()
        except HTTPException:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Server BytePlus credentials not configured "
                    "(set BYTEPLUS_ACCESS_KEY/BYTEPLUS_SECRET_KEY)."
                    if provider == "byteplus"
                    else "Server Volcengine credentials not configured "
                    "(set VOLCENGINE_ACCESS_KEY/SECRET_KEY)."
                ),
            )

        project_name = (project or "").strip() or None
        try:
            items = await asyncio.to_thread(
                _list_viking_memory_collections,
                access_key=ak,
                secret_key=sk,
                session_token=token,
                region=region,
                project=project_name,
            )
        except Exception as e:
            logger.warning(
                f"List VikingDB memories error for {region}: {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=502,
                detail="暂时无法加载 VikingDB 记忆库，请稍后重试。",
            ) from e

        items.sort(
            key=lambda item: (
                str(item.get("projectName") or ""),
                str(item.get("name") or ""),
            )
        )
        return {"items": items, "totalCount": len(items)}

    @app.get("/web/viking-knowledgebases")
    async def _web_list_viking_knowledgebases(
        region: str = "",
        project: str = "",
    ):
        """List VikingDB KnowledgeBase collections visible to server creds."""
        from volcengine.viking_knowledgebase import VikingKnowledgeBaseService

        region = _coerce_cloud_region(region)

        try:
            ak, sk, token = _resolve_ve_credentials()
        except HTTPException:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Server BytePlus credentials not configured "
                    "(set BYTEPLUS_ACCESS_KEY/BYTEPLUS_SECRET_KEY)."
                    if provider == "byteplus"
                    else "Server Volcengine credentials not configured "
                    "(set VOLCENGINE_ACCESS_KEY/SECRET_KEY)."
                ),
            )

        project_name = (project or "").strip() or None
        host, scheme = _viking_knowledgebase_host(region)
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        try:
            client = VikingKnowledgeBaseService(
                host=host,
                region=region,
                ak=ak,
                sk=sk,
                sts_token=token or "",
                scheme=scheme,
            )
            collections = await asyncio.to_thread(
                client.list_collections,
                project=project_name,
                brief=True,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(
                f"List VikingDB knowledgebases error for {region}: {e}",
                exc_info=True,
            )
            collections = []

        for collection in collections or []:
            name = str(_collection_attr(collection, "collection_name", "") or "")
            if not name:
                continue
            _append_unique_viking_collection_item(
                items,
                seen,
                {
                    "id": name,
                    "name": name,
                    "description": str(
                        _collection_attr(collection, "description", "") or ""
                    ),
                    "projectName": str(
                        _collection_attr(collection, "project", project_name or "")
                        or ""
                    ),
                    "region": region,
                    "docCount": _collection_attr(collection, "doc_num", None),
                    "updatedAt": str(
                        _collection_attr(collection, "update_time", "") or ""
                    ),
                    "resourceId": str(
                        _collection_attr(collection, "resource_id", "") or ""
                    ),
                    "sourceKind": "knowledge",
                    "sourceLabel": "Knowledge Engine",
                },
            )

        try:
            agentkit_items = await asyncio.to_thread(
                _list_agentkit_viking_knowledge_bases,
                access_key=ak,
                secret_key=sk,
                session_token=token,
                region=region,
                project=project_name,
            )
            for item in agentkit_items:
                _append_unique_viking_collection_item(items, seen, item)
        except Exception as e:
            logger.warning(
                f"List AgentKit Viking knowledgebases error for {region}: {e}",
                exc_info=True,
            )

        try:
            vector_items = await asyncio.to_thread(
                _list_vikingdb_vector_collections,
                access_key=ak,
                secret_key=sk,
                session_token=token,
                region=region,
                project=project_name,
            )
            for item in vector_items:
                _append_unique_viking_collection_item(items, seen, item)
        except Exception as e:
            logger.warning(
                f"List VikingDB vector collections error for {region}: {e}",
                exc_info=True,
            )

        if not items:
            raise HTTPException(
                status_code=502,
                detail="暂时无法加载 VikingDB 知识库或向量库，请稍后重试。",
            )
        items.sort(
            key=lambda item: (
                str(item.get("sourceKind") or ""),
                str(item.get("projectName") or ""),
                str(item.get("name") or ""),
            )
        )
        return {"items": items, "totalCount": len(items)}

    # SkillSpace routes run sync SDK calls in worker threads. Detail responses
    # include full package files when the version exposes a TOS zip.

    def _skills_client(region: str):
        """Build an AgentkitSkillsClient using server-side creds, or raise
        HTTPException(409) if creds aren't configured."""
        from agentkit.sdk.skills.client import AgentkitSkillsClient

        try:
            ak, sk, token = _resolve_ve_credentials()
        except HTTPException:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Server BytePlus credentials not configured "
                    "(set BYTEPLUS_ACCESS_KEY/BYTEPLUS_SECRET_KEY)."
                    if provider == "byteplus"
                    else "Server Volcengine credentials not configured "
                    "(set VOLCENGINE_ACCESS_KEY/SECRET_KEY)."
                ),
            )
        return AgentkitSkillsClient(
            access_key=ak,
            secret_key=sk,
            region=region,
            session_token=token or "",
        )

    from frontend.server.skills.repository import (
        AgentKitSkillRepository,
        resolve_skill_response,
    )
    from frontend.server.skills.routes import _convert_error, mount_skill_routes
    from frontend.server.skills.service import SkillService

    mount_skill_routes(
        app,
        SkillService(AgentKitSkillRepository(_skills_client)),
        _skill_identity,
    )

    @app.get("/web/skill-spaces")
    async def _web_list_skill_spaces(
        region: str = "all",
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=100),
        project: str | None = None,
    ):
        """List SkillSpaces visible to the server's credentials.

        In Volcengine mode, region=all spans Beijing and Shanghai. In BytePlus
        mode it resolves to the BytePlus Studio region configured for this
        server (currently ap-southeast-1).
        """
        from agentkit.sdk.skills.types import ListSkillSpacesRequest

        aggregate_regions = region in {"all", "", "*"}
        regions = _runtime_regions(provider, region)
        all_items = []
        total_count = 0
        project_name = (project or "").strip() or None

        for reg in regions:
            try:
                client = _skills_client(reg)
                request_page = 1 if aggregate_regions else page
                request_page_size = 50 if aggregate_regions else page_size
                resp = await asyncio.to_thread(
                    client.list_skill_spaces,
                    ListSkillSpacesRequest(
                        PageNumber=request_page,
                        PageSize=request_page_size,
                        ProjectName=project_name,
                    ),
                )
                for s in resp.items or []:
                    all_items.append(
                        {
                            "id": s.id or "",
                            "name": s.name or "",
                            "description": s.description or "",
                            "status": s.status or "",
                            "region": reg,
                            "projectName": s.project_name or "",
                            "updatedAt": s.update_time_stamp or "",
                            "skillCount": len(s.relations or []),
                        }
                    )
                if not aggregate_regions:
                    total_count = (
                        resp.total_count
                        if resp.total_count is not None
                        else len(all_items)
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"ListSkillSpaces error for {reg}: {e}", exc_info=True)
                raise _convert_error(e) from e

        return {
            "items": all_items,
            "totalCount": len(all_items) if aggregate_regions else total_count,
            "page": 1 if aggregate_regions else page,
            "pageSize": 50 if aggregate_regions else page_size,
        }

    @app.get("/web/skill-spaces/{space_id}/skills")
    async def _web_list_skills_in_space(
        space_id: str,
        region: str = "",
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=100, ge=1, le=100),
        project: str | None = None,
    ):
        """List skills in one SkillSpace (relation view: id/name/description/
        version/status per skill)."""
        from agentkit.sdk.skills.types import ListSkillsBySkillSpaceRequest

        del project  # SkillSpace ID is already globally scoped by AgentKit.
        region = _coerce_cloud_region(region)
        try:
            client = _skills_client(region)
            resp = await asyncio.to_thread(
                client.list_skills_by_skill_space,
                ListSkillsBySkillSpaceRequest(
                    SkillSpaceId=space_id,
                    PageNumber=page,
                    PageSize=page_size,
                ),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"ListSkillsBySkillSpace({space_id}) error for {region}: {e}",
                exc_info=True,
            )
            raise _convert_error(e) from e

        items = list(resp.items or [])
        return {
            "items": [
                {
                    "skillId": r.skill_id or "",
                    "skillName": r.skill_name or "",
                    "skillDescription": r.skill_description or "",
                    "version": r.version or "",
                    "skillStatus": r.skill_status or "",
                }
                for r in items
            ],
            "totalCount": (
                resp.total_count if resp.total_count is not None else len(items)
            ),
            "page": page,
            "pageSize": page_size,
        }

    @app.get("/web/skill-spaces/{space_id}/skills/{skill_id}")
    async def _web_get_skill_detail(
        space_id: str,
        skill_id: str,
        version: str | None = None,
        region: str = "",
        skill_space_name: str | None = None,
        skill_name: str | None = None,
    ):
        """Fetch a specific skill version's SKILL.md content plus package files."""
        region = _coerce_cloud_region(region)
        try:
            client = _skills_client(region)
            resp = await asyncio.to_thread(
                resolve_skill_response,
                client,
                space_id=space_id,
                skill_id=skill_id,
                version=version,
                skill_space_name=(skill_space_name or "").strip() or None,
                skill_name=(skill_name or "").strip() or None,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"GetSkillVersion({skill_id}@{version}) error: {e}", exc_info=True
            )
            raise _convert_error(e) from e

        try:
            resolved = await asyncio.to_thread(
                _skill_files_from_version_response,
                space_id=space_id,
                skill_id=skill_id,
                version=version,
                resp=resp,
                folder=_skill_version_attr(resp, "name", "skill_name") or skill_id,
                region=region,
            )
        except HTTPException:
            raise
        except Exception as error:
            logger.error(
                f"Skill package download ({skill_id}@{version}) error for region "
                f"{region}: {error}",
                exc_info=True,
            )
            raise _convert_error(error) from error
        if isinstance(resolved, str):
            skill_md = resolved
            files = []
        else:
            files = [{"path": file.path, "content": file.content} for file in resolved]
            skill_md = next(
                (
                    file.content
                    for file in resolved
                    if file.path.lower().endswith("/skill.md")
                ),
                "",
            )

        return {
            "skillId": skill_id,
            "skillSpaceId": space_id,
            "name": _skill_version_attr(resp, "name", "skill_name"),
            "description": _skill_version_attr(resp, "description"),
            "version": _skill_version_attr(resp, "version") or version or "",
            "skillMd": skill_md,
            "files": files,
            "bucketName": _skill_version_attr(resp, "bucket_name", "bucketName"),
            "tosPath": _skill_version_attr(resp, "tos_path", "tosPath", "path"),
        }

    if vite:
        logger.info(
            f"A2UI Vite mode: API on http://{host}:{port} (no bundled UI), "
            f"run `cd frontend && npm run dev` and open {DEV_SERVER_ORIGIN}"
        )
    else:
        import re as _re

        from fastapi.responses import FileResponse, HTMLResponse
        from fastapi.staticfiles import StaticFiles

        webui = _resolve_frontend_dir(frontend_dir)
        if not (webui / "index.html").is_file():
            raise click.ClickException(
                f"Built UI not found at {webui}. Build it with: "
                "cd frontend && npm install && npm run build "
                "(or use --dev for the Vite dev server)."
            )

        _index_html = (webui / "index.html").read_text(encoding="utf-8")
        _ASSET_REF = _re.compile(r'((?:src|href)=")(/[^"?]+)(")')

        def _render_index(request: Request) -> HTMLResponse:
            # When behind a query-string API gateway (e.g. an AgentKit runtime
            # with the key in the query string), the browser's subresource
            # requests for /assets/* must also carry the key. The key arrives as
            # the page's querystring; forward it onto every same-origin asset URL
            # in the served HTML so those requests pass the gateway too. (The
            # app's own API/navigation requests already forward it via auth.ts.)
            qs = request.url.query
            if not qs:
                return HTMLResponse(_index_html)
            html = _ASSET_REF.sub(
                lambda m: f"{m.group(1)}{m.group(2)}?{qs}{m.group(3)}", _index_html
            )
            return HTMLResponse(html)

        # Built assets (the gateway has already authorized the request).
        app.mount(
            "/assets", StaticFiles(directory=str(webui / "assets")), name="assets"
        )

        @app.get("/")
        async def _spa_root(request: Request):
            return _render_index(request)

        # SPA fallback: serve real static files as-is, otherwise return the
        # (querystring-injected) HTML shell. Registered last so it never shadows
        # the API routes above.
        _webui_root = webui.resolve()

        @app.get("/{path:path}")
        async def _spa_fallback(path: str, request: Request):
            # Resolve and confine to the UI directory — a path like
            # "../../etc/passwd" must NOT escape `webui` (arbitrary file read).
            candidate = (webui / path).resolve()
            if path and candidate.is_relative_to(_webui_root) and candidate.is_file():
                return FileResponse(str(candidate))
            return _render_index(request)

        logger.info(
            f"A2UI UI + API serving on http://{host}:{port} (UI: {webui}, agents: {agents_dir})"
        )

    # Open the UI in the browser once the server is up. Only when this server
    # serves the UI; with --vite the Vite dev server owns it.
    if open_browser and not vite:
        import threading

        browse_host = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
        url = f"http://{browse_host}:{port}"
        threading.Thread(
            target=_open_browser_when_ready,
            args=(url, browse_host, port),
            daemon=True,
        ).start()
        logger.info(f"Opening {url} in your browser…")

    import uvicorn

    uvicorn.run(app, host=host, port=port)


def _studio_deploy_run_script(site_logo_filename: str | None = None) -> str:
    """Return the authenticated VeFaaS entrypoint used by ``studio deploy``."""
    from veadk.cli.studio_package import studio_run_script

    return studio_run_script(site_logo_filename)


def _resolve_studio_identity_region(
    *,
    access_key: str,
    secret_key: str,
    user_pool_id: str,
    client_id: str,
    deployment_region: str,
    session_token: str = "",
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
) -> str:
    """Locate a Studio user-pool client across supported Identity regions."""
    from veadk.integrations.ve_identity.identity_client import IdentityClient

    supported_regions = (
        (default_region(provider),)
        if provider == "byteplus"
        else ("cn-beijing", "cn-shanghai")
    )
    candidate_regions = (deployment_region,) + tuple(
        region for region in supported_regions if region != deployment_region
    )
    for candidate_region in candidate_regions:
        identity_client = IdentityClient(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            region=candidate_region,
            provider=provider,
            enable_vefaas_iam_fallback=False,
        )
        if identity_client.user_pool_client_exists(
            user_pool_uid=user_pool_id,
            client_uid=client_id,
        ):
            return candidate_region
    if provider == "byteplus":
        raise click.ClickException(
            f"Agent Identity user pool/client not found in {deployment_region}."
        )
    raise click.ClickException(
        "VeIdentity user pool/client not found in cn-beijing or cn-shanghai."
    )


def _resolve_or_create_studio_identity_resources(
    *,
    access_key: str,
    secret_key: str,
    user_pool_id: str | None,
    client_id: str | None,
    application_name: str,
    region: str,
    session_token: str = "",
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
) -> tuple[str, str, str]:
    """Resolve or create the Studio user pool and web client in one region."""
    from veadk.integrations.ve_identity.identity_client import IdentityClient

    resolved_pool_id = (user_pool_id or "").strip()
    resolved_client_id = (client_id or "").strip()
    if resolved_client_id and not resolved_pool_id:
        raise click.ClickException(
            "--allowed-client-id requires --user-pool-id so the client can be "
            "resolved within its user pool."
        )

    identity_client = IdentityClient(
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
        provider=provider,
        enable_vefaas_iam_fallback=False,
    )

    if resolved_pool_id:
        user_pool = identity_client.get_user_pool(uid=resolved_pool_id)
        if user_pool is None:
            raise click.ClickException(
                f"Identity user pool '{resolved_pool_id}' was not found in {region}."
            )
        resolved_pool_id, user_pool_domain = user_pool
        click.echo(f"Using Identity user pool '{resolved_pool_id}' in {region}.")
    else:
        user_pool_name = f"veadk-studio-{application_name}"
        user_pool = identity_client.get_user_pool(name=user_pool_name)
        if user_pool is None:
            click.echo(f"Creating Identity user pool '{user_pool_name}' in {region}…")
            user_pool = identity_client.create_user_pool(name=user_pool_name)
        else:
            click.echo(f"Reusing Identity user pool '{user_pool_name}' in {region}.")
        resolved_pool_id, user_pool_domain = user_pool

    if resolved_client_id:
        return resolved_pool_id, user_pool_domain, resolved_client_id

    client_name = f"veadk-studio-{application_name}-web"
    user_pool_client = identity_client.get_user_pool_client(
        user_pool_uid=resolved_pool_id,
        name=client_name,
    )
    if user_pool_client is None:
        click.echo(f"Creating Identity client '{client_name}' in {region}…")
        user_pool_client = identity_client.create_user_pool_client(
            user_pool_uid=resolved_pool_id,
            name=client_name,
            client_type="WEB_APPLICATION",
        )
    else:
        click.echo(f"Reusing Identity client '{client_name}' in {region}.")
    resolved_client_id, _client_secret = user_pool_client
    return resolved_pool_id, user_pool_domain, resolved_client_id


def _resolve_studio_cloud_credentials(
    access_key: str | None,
    secret_key: str | None,
    credentials_path: Path | None = None,
    session_token: str | None = None,
    *,
    provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
) -> tuple[str, str, str]:
    """Resolve Studio deploy credentials as AK, SK, and token."""
    import configparser

    if provider == "byteplus":
        resolved_access_key = (
            access_key
            or os.getenv("BYTEPLUS_ACCESS_KEY", "")
            or os.getenv("VOLCENGINE_ACCESS_KEY", "")
        )
        resolved_secret_key = (
            secret_key
            or os.getenv("BYTEPLUS_SECRET_KEY", "")
            or os.getenv("VOLCENGINE_SECRET_KEY", "")
        )
        resolved_session_token = (
            session_token
            or os.getenv("BYTEPLUS_SESSION_TOKEN", "")
            or os.getenv("VOLCENGINE_SESSION_TOKEN", "")
            or os.getenv("VOLC_SESSIONTOKEN", "")
        )
    else:
        resolved_access_key = access_key or os.getenv("VOLCENGINE_ACCESS_KEY", "")
        resolved_secret_key = secret_key or os.getenv("VOLCENGINE_SECRET_KEY", "")
        resolved_session_token = (
            session_token
            or os.getenv("VOLCENGINE_SESSION_TOKEN", "")
            or os.getenv("VOLC_SESSIONTOKEN", "")
        )
    if resolved_access_key and resolved_secret_key:
        return resolved_access_key, resolved_secret_key, resolved_session_token

    if provider == "byteplus":
        raise click.ClickException(
            "BytePlus credentials required: pass --byteplus-access-key/"
            "--byteplus-secret-key, or set BYTEPLUS_ACCESS_KEY/"
            "BYTEPLUS_SECRET_KEY."
        )

    path = credentials_path or Path.home() / ".volc" / "credentials"
    if path.is_file():
        parser = configparser.ConfigParser(interpolation=None)
        try:
            with path.open(encoding="utf-8") as credentials_file:
                parser.read_file(credentials_file)
        except (OSError, UnicodeError, configparser.Error) as error:
            raise click.ClickException(
                f"Failed to read Volcengine credentials file '{path}': {error}"
            ) from error
        default_profile = parser["default"] if parser.has_section("default") else {}
        resolved_access_key = (
            resolved_access_key or str(default_profile.get("access_key_id", "")).strip()
        )
        resolved_secret_key = (
            resolved_secret_key
            or str(default_profile.get("secret_access_key", "")).strip()
        )
        resolved_session_token = (
            resolved_session_token
            or str(default_profile.get("session_token", "")).strip()
        )

    if resolved_access_key and resolved_secret_key:
        return resolved_access_key, resolved_secret_key, resolved_session_token
    raise click.ClickException(
        "Volcengine credentials required: pass --volcengine-access-key/"
        "--volcengine-secret-key, set VOLCENGINE_ACCESS_KEY/"
        "VOLCENGINE_SECRET_KEY, or configure the [default] profile in "
        "~/.volc/credentials."
    )


@studio.command("deploy")
@click.option(
    "--user-pool-id",
    default=None,
    help="Existing Identity User Pool UID. When omitted, Studio creates or "
    "reuses a pool in the deployment region.",
)
@click.option(
    "--allowed-client-id",
    default=None,
    help="Existing Identity client UID used for SSO. When omitted, Studio "
    "creates or reuses a web client in the deployment region.",
)
@click.option(
    "--client-secret",
    default="",
    help="Client secret, if it cannot be read back from the client UID.",
)
@click.option(
    "--allow-dangerous-login",
    is_flag=True,
    default=False,
    help="Enable local password, passwordless, sign-up, recovery, and "
    "unconfirmed-user login flows on a Studio-managed Identity user pool. "
    "Ignored when --user-pool-id is provided.",
)
@click.option(
    "--vefaas-app-name",
    required=True,
    help="VeFaaS application/function name (4-64 chars, letters/digits/-, no underscore).",
)
@click.option(
    "--provider",
    type=click.Choice(["volcengine", "byteplus"]),
    default="volcengine",
    show_default=True,
    help="Cloud provider for Studio deployment.",
)
@click.option(
    "--region",
    default=None,
    type=click.Choice(["cn-beijing", "cn-shanghai", DEFAULT_BYTEPLUS_REGION]),
    help="Cloud region for Studio deployment. Defaults to the provider region.",
)
@click.option(
    "--project",
    default="default",
    show_default=True,
    help="Cloud project for the VeFaaS function.",
)
@click.option(
    "--iam-role",
    default=None,
    help="Pre-existing IAM role TRN to bind to the function. If omitted, a role "
    "is auto-created with the frontend deploy policy.",
)
@click.option(
    "--vefaas-application-template-id",
    "--application-template-id",
    default=None,
    envvar="VEFAAS_APPLICATION_TEMPLATE_ID",
    help="Override the built-in VeFaaS Application Center TemplateId.",
)
@click.option(
    "--gateway-name",
    default="",
    help="Serverless APIG gateway name to use. Default: auto-discover an "
    "existing serverless gateway and reuse it, creating one only if none exists.",
)
@click.option("--gateway-service-name", default="")
@click.option("--gateway-upstream-name", default="")
@click.option("--volcengine-access-key", default=None)
@click.option("--volcengine-secret-key", default=None)
@click.option("--volcengine-session-token", default=None)
@click.option("--byteplus-access-key", default=None, envvar="BYTEPLUS_ACCESS_KEY")
@click.option("--byteplus-secret-key", default=None, envvar="BYTEPLUS_SECRET_KEY")
@click.option("--byteplus-session-token", default=None, envvar="BYTEPLUS_SESSION_TOKEN")
@click.option(
    "--veadk-version",
    default="",
    help="Pin the veadk-python version in the function's requirements.txt "
    "(default: latest). The deployed UI is that version's veadk/webui.",
)
@click.option(
    "--from-source",
    is_flag=True,
    default=False,
    help="Build a wheel from THIS checkout (incl. uncommitted changes + the "
    "current veadk/webui) and ship it, instead of installing veadk-python from "
    "PyPI. Use to deploy unreleased frontend/backend changes.",
)
@click.option(
    "--keep-failed-deploy",
    is_flag=True,
    default=False,
    help="Keep created VeFaaS application/function resources when deploy fails, "
    "so release logs can be inspected in the console.",
)
@click.option(
    "--precheck-only",
    is_flag=True,
    default=False,
    help="Run the read-only IAM permission pre-check and exit without creating "
    "cloud resources.",
)
@click.option(
    "--site-logo",
    default=None,
    help="Studio logo as a local image path or HTTP(S) URL; the image is "
    "bundled into the deployed function.",
)
@click.option(
    "--site-title",
    default=None,
    help="Studio title, at most 16 characters.",
)
@click.option(
    "--admin",
    "studio_admins",
    default=None,
    envvar="VEADK_STUDIO_ADMINS",
    help="Comma-separated Studio admin usernames or OAuth emails. Omit both "
    "role options to grant every user admin access.",
)
@click.option(
    "--developer",
    "studio_developers",
    default=None,
    envvar="VEADK_STUDIO_DEVELOPERS",
    help="Comma-separated Studio developer usernames or OAuth emails.",
)
@click.option(
    "--sandbox-dev-tool-id",
    "sandbox_dev_tool_id",
    default=None,
    envvar="SANDBOX_DEV",
    help="Dedicated ready AgentKit DevEnv Tool ID for Studio development. "
    "Default: create one during deployment.",
)
@click.option(
    "--sandbox-chat-codex-tool-id",
    "sandbox_chat_codex_tool_id",
    default=None,
    envvar="SANDBOX_CHAT_CODEX",
    help="Dedicated ready AgentKit CodeEnv Tool ID used by temporary chats. "
    "Default: create one during deployment.",
)
@click.option(
    "--sandbox-chat-openclaw-tool-id",
    "sandbox_chat_openclaw_tool_id",
    default=None,
    envvar="SANDBOX_CHAT_OPENCLAW",
    help="Dedicated ready AgentKit ArkClawEnv Tool ID. "
    "Default: create one during deployment.",
)
@click.option(
    "--sandbox-chat-hermes-tool-id",
    "sandbox_chat_hermes_tool_id",
    default=None,
    envvar="SANDBOX_CHAT_HERMES",
    help="Dedicated ready AgentKit HermesEnv Tool ID. "
    "Default: create one during deployment.",
)
@click.option(
    "--sandbox-chat-codex-snapshot-tool-id",
    "sandbox_chat_codex_snapshot_tool_id",
    default=None,
    envvar="SANDBOX_CHAT_CODEX_SNAPSHOT",
    help="Dedicated snapshot-enabled AgentKit CodeEnv Tool ID. "
    "Default: create one during deployment.",
)
@click.option(
    "--sandbox-chat-openclaw-snapshot-tool-id",
    "sandbox_chat_openclaw_snapshot_tool_id",
    default=None,
    envvar="SANDBOX_CHAT_OPENCLAW_SNAPSHOT",
    help="Dedicated snapshot-enabled AgentKit ArkClawEnv Tool ID. "
    "Default: create one during deployment.",
)
@click.option(
    "--sandbox-chat-hermes-snapshot-tool-id",
    "sandbox_chat_hermes_snapshot_tool_id",
    default=None,
    envvar="SANDBOX_CHAT_HERMES_SNAPSHOT",
    help="Dedicated snapshot-enabled AgentKit HermesEnv Tool ID. "
    "Default: create one during deployment.",
)
@click.option(
    "--studio-update-bucket",
    default="veadk-studio",
    show_default=True,
    envvar="VEADK_STUDIO_UPDATE_BUCKET",
    help="TOS bucket containing immutable Studio release bundles.",
)
@click.option(
    "--studio-update-prefix",
    default="veadk/studio/main",
    show_default=True,
    envvar="VEADK_STUDIO_UPDATE_PREFIX",
    help="TOS object prefix for the Studio main release channel.",
)
def frontend_deploy(
    user_pool_id: str | None,
    allowed_client_id: str | None,
    client_secret: str,
    allow_dangerous_login: bool,
    vefaas_app_name: str,
    provider: str,
    region: str | None,
    project: str,
    iam_role: str | None,
    vefaas_application_template_id: str | None,
    gateway_name: str,
    gateway_service_name: str,
    gateway_upstream_name: str,
    volcengine_access_key: str | None,
    volcengine_secret_key: str | None,
    volcengine_session_token: str | None,
    byteplus_access_key: str | None,
    byteplus_secret_key: str | None,
    byteplus_session_token: str | None,
    veadk_version: str,
    from_source: bool,
    keep_failed_deploy: bool,
    precheck_only: bool,
    site_logo: str | None,
    site_title: str | None,
    studio_admins: str | None,
    studio_developers: str | None,
    sandbox_dev_tool_id: str | None,
    sandbox_chat_codex_tool_id: str | None,
    sandbox_chat_openclaw_tool_id: str | None,
    sandbox_chat_hermes_tool_id: str | None,
    sandbox_chat_codex_snapshot_tool_id: str | None,
    sandbox_chat_openclaw_snapshot_tool_id: str | None,
    sandbox_chat_hermes_snapshot_tool_id: str | None,
    studio_update_bucket: str,
    studio_update_prefix: str,
) -> None:
    """Deploy the SSO web frontend to VeFaaS.

    Builds a minimal function that runs `veadk studio --auth-mode frontend`,
    with in-app SSO bound to a resolved Identity user pool + client, and prints
    the public URL. Inside the function the frontend uses the bound IAM role's
    STS credentials to manage AgentKit runtimes.
    """
    import shutil

    from veadk.cli.studio_knowledge_signing import (
        STUDIO_KNOWLEDGE_SIGNING_KEY_ENV,
        resolve_studio_knowledge_signing_key,
        studio_knowledge_signing_namespace,
    )
    from veadk.config import veadk_environments

    provider_id = normalize_cloud_provider(provider)
    if provider_id == "byteplus":
        region = region or DEFAULT_BYTEPLUS_REGION
    else:
        region = region or default_region(provider_id)
    os.environ["CLOUD_PROVIDER"] = provider_id
    os.environ["AGENTKIT_CLOUD_PROVIDER"] = provider_id
    if provider_id == "byteplus":
        _validate_byteplus_vefaas_application_name(vefaas_app_name)
        if region != DEFAULT_BYTEPLUS_REGION:
            raise click.ClickException(
                "BytePlus Studio deployment currently supports only "
                f"{DEFAULT_BYTEPLUS_REGION}; got {region}."
            )
        os.environ["BYTEPLUS_REGION"] = region
    resolved_application_template_id = (
        vefaas_application_template_id or ""
    ).strip() or default_vefaas_application_template_id(provider_id, region)

    try:
        branding_title = normalize_site_title(site_title)
        branding_logo = resolve_site_logo(site_logo)
    except ValueError as error:
        raise click.ClickException(str(error)) from error
    ak, sk, session_token = _resolve_studio_cloud_credentials(
        byteplus_access_key if provider_id == "byteplus" else volcengine_access_key,
        byteplus_secret_key if provider_id == "byteplus" else volcengine_secret_key,
        session_token=(
            byteplus_session_token
            if provider_id == "byteplus"
            else volcengine_session_token
        ),
        provider=provider_id,
    )
    if provider_id == "byteplus":
        os.environ["BYTEPLUS_ACCESS_KEY"] = ak
        os.environ["BYTEPLUS_SECRET_KEY"] = sk
        if session_token:
            os.environ["BYTEPLUS_SESSION_TOKEN"] = session_token

    manage_user_pool_settings = not bool((user_pool_id or "").strip())
    auto_identity_resources = not (user_pool_id and allowed_client_id)
    auto_storage = not str(
        veadk_environments.get("VEADK_STUDIO_TOS_BUCKET") or ""
    ).strip()
    auto_sandbox_tools = any(
        not tool_id
        for tool_id in (
            sandbox_dev_tool_id,
            sandbox_chat_codex_tool_id,
            sandbox_chat_openclaw_tool_id,
            sandbox_chat_hermes_tool_id,
            sandbox_chat_codex_snapshot_tool_id,
            sandbox_chat_openclaw_snapshot_tool_id,
            sandbox_chat_hermes_snapshot_tool_id,
        )
    )
    from veadk.cli.studio_deploy_permissions import (
        IAM_CONFIG_URLS,
        required_permission_specs,
        run_studio_deploy_permission_precheck,
    )

    permission_specs = required_permission_specs(
        auto_identity_resources=auto_identity_resources,
        auto_function_role=not iam_role,
        auto_storage=auto_storage,
        auto_sandbox_tools=auto_sandbox_tools,
        auto_gateway=not gateway_name,
        keep_failed_deploy=keep_failed_deploy,
    )
    try:
        permission_results = run_studio_deploy_permission_precheck(
            provider=provider_id,
            access_key=ak,
            secret_key=sk,
            session_token=session_token,
            specs=permission_specs,
        )
    except Exception as error:
        detail = _safe_exception_detail(error, secrets=(ak, sk, session_token))
        label = (
            "Configure permissions in BytePlus IAM"
            if provider_id == "byteplus"
            else "前往火山引擎 IAM 配置权限"
        )
        click.echo(f"{label}: {IAM_CONFIG_URLS[provider_id]}")
        raise click.ClickException(
            f"IAM permission pre-check failed: {detail}"
        ) from error
    if any(not result.satisfied for result in permission_results):
        message = (
            "Studio deployment stopped before creating cloud resources because "
            "required IAM Actions are missing."
            if provider_id == "byteplus"
            else "缺少 Studio 部署所需的 IAM 权限，已在创建云资源前终止。"
        )
        if precheck_only:
            raise click.ClickException(message)
        prompt = (
            "Some required IAM Actions are missing. Continue deployment anyway?"
            if provider_id == "byteplus"
            else "部分 Studio 部署所需的 IAM 权限未满足，是否仍要继续部署？"
        )
        if not click.confirm(prompt, default=False):
            raise click.ClickException(message)
        click.echo(
            "Continuing deployment despite missing IAM Actions."
            if provider_id == "byteplus"
            else "已确认忽略缺失的 IAM 权限，继续部署。"
        )
    if precheck_only:
        click.echo(
            "Pre-check only: no cloud resources were created."
            if provider_id == "byteplus"
            else "仅执行权限预检，未创建任何云资源。"
        )
        return

    user_pool_domain = ""
    if user_pool_id and allowed_client_id:
        identity_region = _resolve_studio_identity_region(
            access_key=ak,
            secret_key=sk,
            user_pool_id=user_pool_id,
            client_id=allowed_client_id,
            deployment_region=region,
            session_token=session_token,
            provider=provider_id,
        )
    else:
        identity_region = region
        user_pool_id, user_pool_domain, allowed_client_id = (
            _resolve_or_create_studio_identity_resources(
                access_key=ak,
                secret_key=sk,
                session_token=session_token,
                user_pool_id=user_pool_id,
                client_id=allowed_client_id,
                application_name=vefaas_app_name,
                region=identity_region,
                provider=provider_id,
            )
        )
    if identity_region != region:
        click.secho(
            f"Warning: Studio deploys to {region}, but the Identity user "
            f"pool/client was found in {identity_region}. Continuing with "
            f"Identity region {identity_region}.",
            fg="yellow",
        )

    # 1) Ensure VeFaaS has its service role before provisioning cloud resources.
    if provider_id in {"volcengine", "byteplus"}:
        from veadk.cli.studio_deploy_serverless_iam import (
            ensure_serverless_application_role,
        )

        ensure_serverless_application_role(
            ak,
            sk,
            session_token=session_token,
            provider=provider_id,
        )

    # 2) Ensure the IAM role the function runs as (auto-create unless provided).
    if iam_role:
        role_trn = iam_role
        click.echo(f"Using provided IAM role: {role_trn}")
    else:
        from veadk.cli.frontend_deploy_iam import ensure_frontend_role

        click.echo("Ensuring IAM role + policy…")
        role_trn = ensure_frontend_role(
            ak,
            sk,
            session_token=session_token,
            provider=provider_id,
        )
        click.echo(f"IAM role ready: {role_trn}")
    # Consumed by VeFaaS._create_function as the function's Role (STS creds are
    # then injected into the instance); read via getenv from os.environ, NOT
    # shipped as a plain env var.
    os.environ["IAM_ROLE"] = role_trn

    from frontend.server.storage.provisioning import (
        StudioStorageProvisioningError,
        resolve_studio_account_id_for_deploy,
        resolve_studio_storage_for_deploy,
    )

    studio_account_id = ""
    try:
        studio_account_id = resolve_studio_account_id_for_deploy(
            access_key=ak,
            secret_key=sk,
            session_token=session_token or "",
            region=region,
            provider=provider_id,
        )
    except StudioStorageProvisioningError as error:
        detail = _safe_exception_detail(
            error,
            secrets=(ak, sk, session_token),
        )
        click.echo(
            "Warning: Could not resolve Studio cloud account ID for telemetry: "
            f"{detail}"
        )

    click.echo("Ensuring Studio persistent storage…")
    try:
        storage_config = resolve_studio_storage_for_deploy(
            provider=provider_id,
            region=region,
            access_key=ak,
            secret_key=sk,
            session_token=session_token or "",
            source=veadk_environments,
        )
    except StudioStorageProvisioningError as error:
        detail = _safe_exception_detail(
            error,
            secrets=(ak, sk, session_token),
        )
        raise click.ClickException(
            f"Failed to provision Studio persistent storage.\n{detail}"
        ) from error
    studio_storage_environment = _studio_storage_environment(veadk_environments)
    studio_storage_environment.update(
        {
            "VEADK_STUDIO_TOS_BUCKET": storage_config.bucket,
            "VEADK_STUDIO_TOS_REGION": storage_config.region,
        }
    )
    click.echo(f"Studio persistent storage ready: {storage_config.object_host}")

    sandbox_tool_ids = {
        "codex": sandbox_chat_codex_tool_id,
        "codex_snapshot": sandbox_chat_codex_snapshot_tool_id,
        "openclaw": sandbox_chat_openclaw_tool_id,
        "openclaw_snapshot": sandbox_chat_openclaw_snapshot_tool_id,
        "hermes": sandbox_chat_hermes_tool_id,
        "hermes_snapshot": sandbox_chat_hermes_snapshot_tool_id,
        "dev": sandbox_dev_tool_id,
    }
    sandbox_tool_labels = {
        "codex": "Codex",
        "codex_snapshot": "Codex Snapshot",
        "openclaw": "OpenClaw",
        "openclaw_snapshot": "OpenClaw Snapshot",
        "hermes": "Hermes",
        "hermes_snapshot": "Hermes Snapshot",
        "dev": "Dev Sandbox",
    }
    sandbox_tool_purposes = {
        "codex": "codex",
        "codex_snapshot": "codex",
        "openclaw": "openclaw",
        "openclaw_snapshot": "openclaw",
        "hermes": "hermes",
        "hermes_snapshot": "hermes",
        "dev": "dev",
    }
    from veadk.cli.studio_sandbox_tools import (
        ensure_studio_agent_model_credential,
        ensure_studio_agent_tool,
        ensure_studio_code_env_tool,
        ensure_studio_dev_env_tool,
        studio_sandbox_agent_model_name,
        studio_sandbox_model_base_url,
        studio_sandbox_tool_name_candidates,
    )

    sandbox_agent_model_name = studio_sandbox_agent_model_name(provider_id)
    sandbox_model_base_url = studio_sandbox_model_base_url(provider_id)

    missing_sandbox_tools: dict[str, tuple[str, ...]] = {}
    for kind, tool_id in sandbox_tool_ids.items():
        label = sandbox_tool_labels[kind]
        if tool_id:
            click.echo(f"Using configured AgentKit {label} Tool '{tool_id}'.")
            continue
        tool_names = studio_sandbox_tool_name_candidates(
            vefaas_app_name,
            sandbox_tool_purposes[kind],
            snapshot=kind.endswith("_snapshot"),
        )
        click.echo(f"Creating AgentKit {label} Tool '{tool_names[0]}'…")
        missing_sandbox_tools[kind] = tool_names

    if missing_sandbox_tools:
        with ThreadPoolExecutor(max_workers=len(missing_sandbox_tools)) as executor:
            tool_futures = {}
            for kind, tool_names in missing_sandbox_tools.items():
                if tool_futures:
                    sleep(_SANDBOX_TOOL_CREATE_STAGGER_SECONDS)
                tool_name = tool_names[0]
                base_kind = kind.removesuffix("_snapshot")
                enable_snapshot = kind.endswith("_snapshot")
                if base_kind == "codex":
                    future = executor.submit(
                        ensure_studio_code_env_tool,
                        name=tool_name,
                        legacy_names=tool_names[1:],
                        enable_snapshot=enable_snapshot,
                        create_min_interval=_SANDBOX_TOOL_CREATE_STAGGER_SECONDS,
                        region=region,
                        access_key=ak,
                        secret_key=sk,
                        session_token=session_token or "",
                    )
                elif base_kind == "dev":
                    future = executor.submit(
                        ensure_studio_dev_env_tool,
                        name=tool_name,
                        create_min_interval=_SANDBOX_TOOL_CREATE_STAGGER_SECONDS,
                        region=region,
                        access_key=ak,
                        secret_key=sk,
                        session_token=session_token or "",
                    )
                else:
                    future = executor.submit(
                        ensure_studio_agent_tool,
                        name=tool_name,
                        kind=base_kind,
                        enable_snapshot=enable_snapshot,
                        model_name=sandbox_agent_model_name,
                        create_min_interval=_SANDBOX_TOOL_CREATE_STAGGER_SECONDS,
                        region=region,
                        access_key=ak,
                        secret_key=sk,
                        session_token=session_token or "",
                    )
                tool_futures[kind] = future

            for kind, future in tool_futures.items():
                label = sandbox_tool_labels[kind]
                try:
                    sandbox_tool_ids[kind] = future.result()
                except Exception as error:
                    detail = _safe_exception_detail(
                        error,
                        secrets=(ak, sk, session_token),
                    )
                    raise click.ClickException(
                        f"Failed to provision the AgentKit {label} Tool. "
                        f"Underlying error:\n{detail}"
                    ) from error
                click.echo(f"AgentKit {label} Tool is ready.")

    from veadk.cli.frontend_skill_creator import (
        ensure_skill_creator_model_credential,
    )

    resolved_sandbox_tool_ids: dict[str, str] = {}
    for kind, tool_id in sandbox_tool_ids.items():
        if not tool_id:
            raise click.ClickException(
                f"AgentKit {sandbox_tool_labels[kind]} Tool did not return a Tool ID."
            )
        resolved_sandbox_tool_ids[kind] = tool_id
        click.echo(f"Creating AgentKit {sandbox_tool_labels[kind]} model credential…")

    _validate_distinct_sandbox_tool_ids(resolved_sandbox_tool_ids)

    if resolved_sandbox_tool_ids:
        max_workers = len(resolved_sandbox_tool_ids)
    else:
        max_workers = 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        credential_futures = {}
        for kind, tool_id in resolved_sandbox_tool_ids.items():
            base_kind = kind.removesuffix("_snapshot")
            if base_kind in {"codex", "dev"}:
                code_model_name = (
                    sandbox_agent_model_name if base_kind == "codex" else None
                )
                future = executor.submit(
                    ensure_skill_creator_model_credential,
                    tool_id=tool_id,
                    region=region,
                    access_key=ak,
                    secret_key=sk,
                    session_token=session_token,
                    provider=provider_id,
                    model_name=code_model_name,
                )
            else:
                future = executor.submit(
                    ensure_studio_agent_model_credential,
                    tool_id=tool_id,
                    kind=base_kind,
                    model_name=sandbox_agent_model_name,
                    model_base_url=sandbox_model_base_url,
                    region=region,
                    access_key=ak,
                    secret_key=sk,
                    session_token=session_token,
                    provider=provider_id,
                )
            credential_futures[kind] = future

        for kind, future in credential_futures.items():
            label = sandbox_tool_labels[kind]
            try:
                future.result()
            except Exception as error:
                detail = _safe_exception_detail(
                    error,
                    secrets=(ak, sk, session_token),
                )
                raise click.ClickException(
                    f"Failed to provision the AgentKit {label} model credential. "
                    f"Underlying error:\n{detail}"
                ) from error
            click.echo(f"AgentKit {label} model credential is ready.")

    chat_codex_tool_id = resolved_sandbox_tool_ids.get("codex", "")
    chat_codex_snapshot_tool_id = resolved_sandbox_tool_ids.get("codex_snapshot", "")
    openclaw_tool_id = resolved_sandbox_tool_ids.get("openclaw", "")
    openclaw_snapshot_tool_id = resolved_sandbox_tool_ids.get("openclaw_snapshot", "")
    hermes_tool_id = resolved_sandbox_tool_ids.get("hermes", "")
    hermes_snapshot_tool_id = resolved_sandbox_tool_ids.get("hermes_snapshot", "")
    dev_tool_id = resolved_sandbox_tool_ids.get("dev", "")

    knowledge_signing_key = resolve_studio_knowledge_signing_key(
        {
            STUDIO_KNOWLEDGE_SIGNING_KEY_ENV: (
                veadk_environments.get(STUDIO_KNOWLEDGE_SIGNING_KEY_ENV)
                or os.getenv(STUDIO_KNOWLEDGE_SIGNING_KEY_ENV, "")
            )
        },
        seed=sk,
        namespace=studio_knowledge_signing_namespace(
            provider_id,
            studio_account_id,
            user_pool_id,
            allowed_client_id,
            vefaas_app_name,
        ),
    )

    # SECURITY: VeFaaS._create_function uploads *everything* in veadk_environments
    # (i.e. the deployer's whole .env) as function env vars. The frontend must
    # NOT receive the deployer's secrets (VOLCENGINE_ACCESS_KEY/SECRET_KEY, model
    # API keys, DB passwords). It authenticates to Volcengine via its IAM role's
    # STS credentials (see _resolve_ve_credentials — env AK/SK would otherwise
    # wrongly take precedence). So reset to a minimal, explicit, non-secret env.
    #
    # The frontend does SSO itself (--auth-mode frontend): a serverless APIG
    # gateway can only carry veFaaS upstreams, so the gateway-plugin OAuth path
    # (which needs a domain upstream to the user pool) can't run on VeFaaS.
    # `veadk frontend` resolves the client secret + registers the callback from
    # the pool/client UID via from_veidentity, so we only ship the UIDs here.
    veadk_environments.clear()
    veadk_environments["CLOUD_PROVIDER"] = provider_id
    veadk_environments["AGENTKIT_CLOUD_PROVIDER"] = provider_id
    if provider_id == "byteplus":
        veadk_environments["BYTEPLUS_REGION"] = region
        veadk_environments["DATABASE_VIKING_REGION"] = (
            DEFAULT_BYTEPLUS_VIKING_MEMORY_REGION
        )
        byteplus_web_search_api_key = os.getenv(
            "BYTEPLUS_WEB_SEARCH_API_KEY",
            "",
        ).strip()
        if byteplus_web_search_api_key:
            veadk_environments["BYTEPLUS_WEB_SEARCH_API_KEY"] = (
                byteplus_web_search_api_key
            )
        byteplus_web_search_url = os.getenv("BYTEPLUS_WEB_SEARCH_URL", "").strip()
        if byteplus_web_search_url:
            veadk_environments["BYTEPLUS_WEB_SEARCH_URL"] = byteplus_web_search_url
    veadk_environments["OAUTH2_USER_POOL_ID"] = user_pool_id
    veadk_environments["OAUTH2_USER_POOL_CLIENT_ID"] = allowed_client_id
    veadk_environments["OAUTH2_PROVIDER"] = "veidentity"
    veadk_environments["VEIDENTITY_REGION"] = identity_region
    if site_title is not None:
        veadk_environments["VEADK_SITE_TITLE"] = branding_title
    if studio_admins:
        veadk_environments["VEADK_STUDIO_ADMINS"] = studio_admins
    if studio_developers:
        veadk_environments["VEADK_STUDIO_DEVELOPERS"] = studio_developers
    veadk_environments["SANDBOX_CHAT_CODEX"] = chat_codex_tool_id
    veadk_environments["SANDBOX_CHAT_CODEX_SNAPSHOT"] = chat_codex_snapshot_tool_id
    veadk_environments["SANDBOX_CHAT_OPENCLAW"] = openclaw_tool_id
    veadk_environments["SANDBOX_CHAT_OPENCLAW_SNAPSHOT"] = openclaw_snapshot_tool_id
    veadk_environments["SANDBOX_CHAT_HERMES"] = hermes_tool_id
    veadk_environments["SANDBOX_CHAT_HERMES_SNAPSHOT"] = hermes_snapshot_tool_id
    veadk_environments["SANDBOX_DEV"] = dev_tool_id
    veadk_environments["AGENTKIT_SANDBOX_REGION"] = region
    veadk_environments["VEADK_STUDIO_UPDATE_BUCKET"] = studio_update_bucket
    veadk_environments["VEADK_STUDIO_UPDATE_PREFIX"] = studio_update_prefix
    veadk_environments["VEADK_STUDIO_PROJECT"] = project
    studio_deploy_id = _new_studio_deploy_id()
    veadk_environments["VEADK_STUDIO_DEPLOY_ID"] = studio_deploy_id
    veadk_environments[STUDIO_KNOWLEDGE_SIGNING_KEY_ENV] = knowledge_signing_key
    veadk_environments["VEADK_STUDIO_USER_POOL_ID"] = user_pool_id
    veadk_environments["VEADK_STUDIO_DEPLOY_REGION"] = region
    if studio_account_id:
        veadk_environments["VEADK_STUDIO_ACCOUNT_ID"] = studio_account_id
    veadk_environments.update(studio_storage_environment)
    if client_secret:
        veadk_environments["OAUTH2_CLIENT_SECRET"] = client_secret

    # 3) Build the function project (zip): run.sh launches the frontend server on
    #    the FaaS-assigned port; requirements.txt pulls veadk-python (ships the UI).
    requirements = (
        f"veadk-python=={veadk_version}\n" if veadk_version else "veadk-python\n"
    )
    # 3b) Resolve the serverless APIG gateway: use --gateway-name if given, else
    #     reuse an existing serverless gateway, creating one only if none exists.
    #     (VeFaaS applications can only attach to a serverless gateway; reusing
    #     avoids the per-account gateway quota.)
    from veadk.integrations.ve_apig.ve_apig import APIGateway

    if not gateway_name:
        apig = APIGateway(
            ak,
            sk,
            region,
            session_token=session_token,
            provider=provider_id,
        )
        gw = apig.find_serverless_gateway()
        if gw is not None:
            gateway_name = getattr(gw, "name")
            click.echo(f"Reusing serverless gateway: {gateway_name}")
        else:
            gateway_name = "veadk-frontend-gw"
            click.echo(f"No serverless gateway found; creating '{gateway_name}'…")
            apig.create_serverless_gateway(gateway_name)
            click.echo(f"Created serverless gateway: {gateway_name}")

    tmp = tempfile.mkdtemp(prefix=f"veadk_frontend_deploy_{vefaas_app_name}_")
    try:
        # When --from-source, build a wheel from this checkout (picks up
        # uncommitted changes + the current veadk/webui) and install it instead
        # of the PyPI release, so the deployed frontend runs this branch's code.
        if from_source:
            import veadk

            from veadk.cli.studio_package import build_local_studio_requirements

            repo_root = Path(veadk.__file__).resolve().parent.parent
            click.echo(f"Building wheel from source at {repo_root}…")
            try:
                requirements = build_local_studio_requirements(
                    repo_root,
                    Path(tmp),
                    provider=provider_id,
                )
            except ValueError as error:
                raise click.ClickException(f"--from-source: {error}") from error
        else:
            from veadk.cli.studio_package import stage_studio_provider_requirements

            try:
                requirements = (
                    stage_studio_provider_requirements(Path(tmp), provider_id)
                    + requirements
                )
            except ValueError as error:
                raise click.ClickException(str(error)) from error

        from veadk.cli.studio_package import write_studio_package

        write_studio_package(
            Path(tmp),
            requirements=requirements,
            site_logo=branding_logo,
            provider=provider_id,
        )

        # 3) Deploy the function + a plain public APIG trigger on the serverless
        #    gateway (auth_method="none" — no gateway SSO plugin / domain upstream).
        from veadk.cloud.cloud_agent_engine import CloudAgentEngine

        engine = CloudAgentEngine(
            volcengine_access_key=ak,
            volcengine_secret_key=sk,
            volcengine_session_token=session_token,
            region=region,
            project=project,
            provider=provider_id,
            vefaas_application_template_id=resolved_application_template_id,
        )
        click.echo(
            f"Deploying frontend to VeFaaS as '{vefaas_app_name}' "
            f"in {region}/{project}…"
        )
        app = engine.deploy(
            application_name=vefaas_app_name,
            path=tmp,
            gateway_name=gateway_name,
            gateway_service_name=gateway_service_name,
            gateway_upstream_name=gateway_upstream_name,
            use_adk_web=False,
            auth_method="none",
            enable_mcp_session=False,
            keep_failed_deploy=keep_failed_deploy,
        )
        url = (app.vefaas_endpoint or "").rstrip("/")
        redirect_uri = f"{url}/oauth2/callback"

        from veadk.integrations.ve_identity.identity_client import IdentityClient

        identity_client = IdentityClient(
            access_key=ak,
            secret_key=sk,
            session_token=session_token,
            region=identity_region,
            provider=provider_id,
            enable_vefaas_iam_fallback=False,
        )

        # 4) Register the SSO callback on the user-pool client HERE, with the
        #    deployer's full credentials — the function's IAM role is granted
        #    only read access to Identity (id:GetUserPoolClient), not
        #    id:UpdateUserPoolClient, so it can't register the callback itself.
        if url:
            try:
                identity_client.register_callback_for_user_pool_client(
                    user_pool_uid=user_pool_id,
                    client_uid=allowed_client_id,
                    callback_url=redirect_uri,
                    web_origin=url,
                    dismiss_login_page_enabled=False,
                    skip_consent_enabled=True,
                )
                click.echo(f"Registered SSO callback: {redirect_uri}")
            except Exception as e:
                click.echo(
                    f"⚠️  Could not register the SSO callback ({e}). Add "
                    f"{redirect_uri} to the user-pool client's allowed callback URLs manually."
                )

        # 5) Two-phase: now that the public URL is known, inject the correct
        #    OAuth redirect and re-release so in-app SSO points at this endpoint.
        function_id = getattr(app, "vefaas_function_id", "")
        if url and function_id:
            click.echo(f"Setting OAUTH2_REDIRECT_URI={redirect_uri} and re-releasing…")
            release_environment = {
                "OAUTH2_REDIRECT_URI": redirect_uri,
                "VEADK_STUDIO_DEPLOY_ID": studio_deploy_id,
                "VEADK_STUDIO_CRONJOB_SCHEDULER_BASE": vefaas_app_name,
                "VEADK_STUDIO_USER_POOL_ID": veadk_environments[
                    "VEADK_STUDIO_USER_POOL_ID"
                ],
                "VEADK_STUDIO_DEPLOY_REGION": region,
            }
            if studio_account_id:
                release_environment["VEADK_STUDIO_ACCOUNT_ID"] = studio_account_id
            if studio_update_bucket:
                release_environment.update(
                    {
                        "VEADK_STUDIO_APPLICATION_ID": app.vefaas_application_id,
                        "VEADK_STUDIO_FUNCTION_ID": function_id,
                        "VEADK_STUDIO_RELEASE_VERSION": veadk_version or "bundled",
                    }
                )
            engine._vefaas_service.update_function_envs_and_release(
                function_id,
                release_environment,
            )

        # The scheduler is deliberately a separate stateless VeFaaS process.
        # A fixed cloud timer wakes it once per minute; user schedules and all
        # execution state remain in the shared TOS bucket.
        from frontend.service.studio_scheduler.deploy import deploy_scheduler

        click.echo("Deploying the Studio cronjob scheduler and minute timer…")
        try:
            (
                scheduler_function_id,
                scheduler_timer_id,
                scheduler_worker_function_id,
                scheduler_worker_timer_id,
            ) = deploy_scheduler(
                getattr(engine, "_vefaas_service", None),
                studio_application_name=vefaas_app_name,
                package_root=Path(tmp),
                role_trn=role_trn,
                environment={
                    "CLOUD_PROVIDER": provider_id,
                    "AGENTKIT_CLOUD_PROVIDER": provider_id,
                    "VEADK_STUDIO_TOS_BUCKET": storage_config.bucket,
                    "VEADK_STUDIO_TOS_REGION": storage_config.region,
                    "VEADK_STUDIO_TOS_ENDPOINT": getattr(
                        storage_config, "endpoint", ""
                    ),
                    "VEADK_STUDIO_PROJECT": project,
                },
            )
        except Exception as error:
            detail = _safe_exception_detail(
                error,
                secrets=(ak, sk, session_token),
            )
            raise click.ClickException(
                f"Failed to deploy the Studio cronjob scheduler.\n{detail}"
            ) from error
        click.echo(
            "Studio cronjob scheduler ready: "
            f"scanner={scheduler_function_id}, scanner_timer={scheduler_timer_id}, "
            f"worker={scheduler_worker_function_id}, "
            f"worker_timer={scheduler_worker_timer_id}"
        )

        # 6) Only configure login flows on a Studio-managed user pool. Explicit
        #    --user-pool-id values are customer-managed and must be preserved.
        if manage_user_pool_settings:
            if allow_dangerous_login:
                identity_client.configure_user_pool_for_local_login(user_pool_id)
                click.echo(
                    "WARNING: Enabled dangerous local account flows on the "
                    "Studio-managed user pool."
                )
            else:
                identity_client.configure_user_pool_for_idp_only(user_pool_id)
                click.echo("Configured the user pool for IdP-only sign-in.")
        else:
            click.echo("Preserved the existing Identity user pool login settings.")

        click.echo("")
        click.echo(f"✅ Frontend deployed: {url}")
        click.echo(f"   application id: {app.vefaas_application_id}")
        click.echo(f"   identity region: {identity_region}")
        click.echo(f"   user pool id: {user_pool_id}")
        if user_pool_domain:
            click.echo(f"   user pool domain: {user_pool_domain}")
        click.echo(f"   client id: {allowed_client_id}")
        if auto_identity_resources or auto_storage or missing_sandbox_tools:
            identity_console = (
                "https://console.byteplus.com/identity"
                if provider_id == "byteplus"
                else "https://console.volcengine.com/identity"
            )
            click.echo("")
            click.echo("   Cloud resources configured for this Studio:")
            for kind, tool_id in resolved_sandbox_tool_ids.items():
                click.echo(f"   [{sandbox_tool_labels[kind]}]: {tool_id}")
            click.echo(f"   TOS (private): https://{storage_config.object_host}")
            click.echo(f"   user pool id: {user_pool_id}")
            click.echo(f"   client id: {allowed_client_id}")
            click.echo(f"   Identity console: {identity_console}")
            if manage_user_pool_settings and allow_dangerous_login:
                click.echo("   Local account login flows are enabled.")
            elif manage_user_pool_settings:
                click.echo("   Password sign-in is disabled by default for security.")
                click.echo(
                    "   Configure an SSO identity provider before inviting users."
                )
        click.echo("   (open the URL — you'll be redirected through SSO login)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@studio.command("update")
@click.option(
    "--provider",
    default=DEFAULT_CLOUD_PROVIDER,
    type=click.Choice(["volcengine", "byteplus"]),
    show_default=True,
    help="Cloud provider for the existing Studio deployment.",
)
@click.option(
    "--vefaas-app-name",
    required=True,
    help="Existing VeFaaS Application name to update.",
)
@click.option(
    "--region",
    default=None,
    type=click.Choice(["cn-beijing", "cn-shanghai", DEFAULT_BYTEPLUS_REGION]),
    help="Limit Application lookup to one region.",
)
@click.option(
    "--project",
    default=None,
    help="Limit Application lookup to one project (default: search all visible projects).",
)
@click.option(
    "--path",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="VeADK source checkout whose frontend will be built and uploaded.",
)
@click.option(
    "--site-logo",
    default=None,
    help="Replace the deployed Studio logo with a local image or HTTP(S) URL.",
)
@click.option(
    "--site-title",
    default=None,
    help="Replace the deployed Studio title, at most 16 characters.",
)
@click.option(
    "--sandbox-dev-tool-id",
    "sandbox_dev_tool_id",
    default=None,
    help="Replace the Studio DevEnv Tool ID.",
)
@click.option(
    "--sandbox-chat-codex-tool-id",
    "sandbox_chat_codex_tool_id",
    default=None,
    help="Replace the temporary-chat AgentKit CodeEnv Tool ID.",
)
@click.option(
    "--sandbox-chat-openclaw-tool-id",
    "sandbox_chat_openclaw_tool_id",
    default=None,
    help="Replace the OpenClaw AgentKit Tool ID.",
)
@click.option(
    "--sandbox-chat-hermes-tool-id",
    "sandbox_chat_hermes_tool_id",
    default=None,
    help="Replace the Hermes AgentKit Tool ID.",
)
@click.option(
    "--sandbox-chat-codex-snapshot-tool-id",
    "sandbox_chat_codex_snapshot_tool_id",
    default=None,
    help="Replace the snapshot-enabled temporary-chat AgentKit CodeEnv Tool ID.",
)
@click.option(
    "--sandbox-chat-openclaw-snapshot-tool-id",
    "sandbox_chat_openclaw_snapshot_tool_id",
    default=None,
    help="Replace the snapshot-enabled OpenClaw AgentKit Tool ID.",
)
@click.option(
    "--sandbox-chat-hermes-snapshot-tool-id",
    "sandbox_chat_hermes_snapshot_tool_id",
    default=None,
    help="Replace the snapshot-enabled Hermes AgentKit Tool ID.",
)
@click.option("--volcengine-access-key", default=None)
@click.option("--volcengine-secret-key", default=None)
@click.option("--volcengine-session-token", default=None)
@click.option("--byteplus-access-key", default=None, envvar="BYTEPLUS_ACCESS_KEY")
@click.option("--byteplus-secret-key", default=None, envvar="BYTEPLUS_SECRET_KEY")
@click.option("--byteplus-session-token", default=None, envvar="BYTEPLUS_SESSION_TOKEN")
def frontend_update(
    provider: str,
    vefaas_app_name: str,
    region: str | None,
    project: str | None,
    path: Path,
    site_logo: str | None,
    site_title: str | None,
    sandbox_dev_tool_id: str | None,
    sandbox_chat_codex_tool_id: str | None,
    sandbox_chat_openclaw_tool_id: str | None,
    sandbox_chat_hermes_tool_id: str | None,
    sandbox_chat_codex_snapshot_tool_id: str | None,
    sandbox_chat_openclaw_snapshot_tool_id: str | None,
    sandbox_chat_hermes_snapshot_tool_id: str | None,
    volcengine_access_key: str | None,
    volcengine_secret_key: str | None,
    volcengine_session_token: str | None,
    byteplus_access_key: str | None,
    byteplus_secret_key: str | None,
    byteplus_session_token: str | None,
) -> None:
    """Build local Studio sources and update an existing VeFaaS Application."""
    import shutil
    from functools import partial

    from veadk.cli.studio_package import (
        build_frontend_assets,
        build_local_studio_requirements,
        write_studio_package,
    )
    from veadk.cli.studio_update import (
        _is_retryable_cloud_read_error,
        find_studio_deployments,
        load_deployed_site_logo,
        retry_transient_cloud_operation,
    )
    from veadk.cli.studio_knowledge_signing import (
        STUDIO_KNOWLEDGE_SIGNING_KEY_ENV,
        resolve_studio_knowledge_signing_key,
    )
    from veadk.integrations.ve_faas.ve_faas import VeFaaS

    provider_id = normalize_cloud_provider(provider)
    if provider_id == "byteplus":
        if region is not None and region != DEFAULT_BYTEPLUS_REGION:
            raise click.ClickException(
                "BytePlus Studio update currently supports only "
                f"{DEFAULT_BYTEPLUS_REGION}; got {region}."
            )
        region = region or DEFAULT_BYTEPLUS_REGION
    elif region == DEFAULT_BYTEPLUS_REGION:
        raise click.ClickException(
            f"{DEFAULT_BYTEPLUS_REGION} is a BytePlus region. Use "
            "--provider byteplus for BytePlus Studio updates."
        )

    ak, sk, session_token = _resolve_studio_cloud_credentials(
        byteplus_access_key if provider_id == "byteplus" else volcengine_access_key,
        byteplus_secret_key if provider_id == "byteplus" else volcengine_secret_key,
        session_token=(
            byteplus_session_token
            if provider_id == "byteplus"
            else volcengine_session_token
        ),
        provider=provider_id,
    )

    try:
        targets = find_studio_deployments(
            access_key=ak,
            secret_key=sk,
            session_token=session_token,
            application_name=vefaas_app_name,
            region=region,
            project=project,
            provider=provider_id,
        )
    except Exception as error:
        detail = _safe_exception_detail(error, secrets=(ak, sk, session_token))
        raise click.ClickException(
            "Could not query the existing Studio deployment after retrying "
            f"transient cloud errors: {detail}"
        ) from error
    if not targets:
        default_scope = (
            DEFAULT_BYTEPLUS_REGION
            if provider_id == "byteplus"
            else "cn-beijing and cn-shanghai across all visible projects"
        )
        scope = "/".join(value for value in (region, project) if value) or default_scope
        raise click.ClickException(
            f"VeFaaS Application '{vefaas_app_name}' was not found in {scope}."
        )
    if len(targets) > 1:
        candidates = "\n".join(
            f"  - {target.region}/{target.project} "
            f"(Application ID: {target.application_id})"
            for target in targets
        )
        raise click.ClickException(
            f"Multiple VeFaaS Applications named '{vefaas_app_name}' were found. "
            "Specify --region and/or --project:\n"
            f"{candidates}"
        )
    target = targets[0]

    try:
        branding_logo = (
            resolve_site_logo(site_logo)
            if site_logo is not None
            else load_deployed_site_logo(target)
        )
        branding_title = (
            normalize_site_title(site_title) if site_title is not None else None
        )
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    source_root = path.expanduser().resolve()
    tmp = Path(tempfile.mkdtemp(prefix=f"veadk_studio_update_{vefaas_app_name}_"))
    package_dir = tmp / "package"
    try:
        click.echo(f"Building Studio frontend from {source_root}…")
        frontend_assets = tmp / "frontend"
        try:
            build_frontend_assets(source_root, frontend_assets)
            requirements = build_local_studio_requirements(
                source_root,
                package_dir,
                frontend_assets=frontend_assets,
                provider=provider_id,
            )
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        write_studio_package(
            package_dir,
            requirements=requirements,
            site_logo=branding_logo,
            provider=provider_id,
        )

        click.echo(f"Updating '{vefaas_app_name}' in {target.region}/{target.project}…")
        service = VeFaaS(
            access_key=ak,
            secret_key=sk,
            session_token=session_token,
            region=target.region,
            project_name=target.project,
            provider=provider_id,
        )
        environment_overrides = {"AGENTKIT_SANDBOX_REGION": target.region}
        service_client = getattr(service, "client", None)
        current_env: dict[str, str] = {}
        remote_function: object | None = None
        user_pool_id = ""
        user_pool_client_id = ""
        if service_client is not None:
            import volcenginesdkvefaas

            remote_function = service_client.get_function(
                volcenginesdkvefaas.GetFunctionRequest(id=target.function_id)
            )
            from veadk.cli.frontend_deploy_iam import (
                ensure_default_frontend_role_policy,
            )

            if ensure_default_frontend_role_policy(
                str(getattr(remote_function, "role", "") or ""),
                access_key=ak,
                secret_key=sk,
                session_token=session_token,
                provider=provider_id,
            ):
                click.echo("Studio IAM role policy updated.")
            current_env = {
                item.key: item.value
                for item in (getattr(remote_function, "envs", None) or [])
            }
            user_pool_id = str(
                current_env.get("VEADK_STUDIO_USER_POOL_ID")
                or current_env.get("OAUTH2_USER_POOL_ID")
                or ""
            ).strip()
            user_pool_client_id = str(
                current_env.get("OAUTH2_USER_POOL_CLIENT_ID") or ""
            ).strip()
            if user_pool_id:
                environment_overrides.update(
                    {
                        "VEADK_STUDIO_DEPLOY_ID": str(
                            current_env.get("VEADK_STUDIO_DEPLOY_ID")
                            or _new_studio_deploy_id()
                        ).strip(),
                        "VEADK_STUDIO_USER_POOL_ID": user_pool_id,
                        "VEADK_STUDIO_APPLICATION_ID": target.application_id,
                        "VEADK_STUDIO_FUNCTION_ID": target.function_id,
                        "VEADK_STUDIO_DEPLOY_REGION": target.region,
                        "VEADK_STUDIO_PROJECT": target.project,
                    }
                )

        environment_overrides[STUDIO_KNOWLEDGE_SIGNING_KEY_ENV] = (
            resolve_studio_knowledge_signing_key(current_env)
        )

        public_url = target.url.rstrip("/")
        if public_url and user_pool_id and user_pool_client_id:
            redirect_uri = f"{public_url}/oauth2/callback"
            environment_overrides["OAUTH2_REDIRECT_URI"] = redirect_uri
            from veadk.integrations.ve_identity.identity_client import IdentityClient

            identity_client = IdentityClient(
                access_key=ak,
                secret_key=sk,
                session_token=session_token,
                region=str(current_env.get("VEIDENTITY_REGION") or target.region),
                provider=provider_id,
            )
            try:
                identity_client.register_callback_for_user_pool_client(
                    user_pool_uid=user_pool_id,
                    client_uid=user_pool_client_id,
                    callback_url=redirect_uri,
                    web_origin=public_url,
                    dismiss_login_page_enabled=False,
                    skip_consent_enabled=True,
                )
                click.echo(f"Registered SSO callback: {redirect_uri}")
            except Exception as error:
                click.echo(
                    f"Warning: Could not register the SSO callback ({error}). Add "
                    f"{redirect_uri} to the user-pool client's allowed callback URLs manually."
                )

        studio_account_id = str(
            current_env.get("VEADK_STUDIO_ACCOUNT_ID") or ""
        ).strip()
        if not studio_account_id and remote_function is not None:
            studio_account_id = _studio_account_id_from_remote_function(remote_function)
        if not studio_account_id and service_client is not None:
            from frontend.server.storage.provisioning import (
                StudioStorageProvisioningError,
                resolve_studio_account_id_for_deploy,
            )

            try:
                studio_account_id = resolve_studio_account_id_for_deploy(
                    access_key=ak,
                    secret_key=sk,
                    session_token=session_token or "",
                    region=target.region,
                    provider=provider_id,
                )
            except StudioStorageProvisioningError as error:
                detail = _safe_exception_detail(
                    error,
                    secrets=(ak, sk, session_token),
                )
                click.echo(
                    "Warning: Could not resolve Studio cloud account ID for telemetry: "
                    f"{detail}"
                )
        if studio_account_id:
            environment_overrides["VEADK_STUDIO_ACCOUNT_ID"] = studio_account_id

        snapshot_tool_ids = {
            "codex_snapshot": sandbox_chat_codex_snapshot_tool_id
            if sandbox_chat_codex_snapshot_tool_id is not None
            else current_env.get("SANDBOX_CHAT_CODEX_SNAPSHOT", ""),
            "openclaw_snapshot": sandbox_chat_openclaw_snapshot_tool_id
            if sandbox_chat_openclaw_snapshot_tool_id is not None
            else current_env.get("SANDBOX_CHAT_OPENCLAW_SNAPSHOT", ""),
            "hermes_snapshot": sandbox_chat_hermes_snapshot_tool_id
            if sandbox_chat_hermes_snapshot_tool_id is not None
            else current_env.get("SANDBOX_CHAT_HERMES_SNAPSHOT", ""),
        }
        if service_client is not None:
            from veadk.cli.frontend_skill_creator import (
                ensure_skill_creator_model_credential,
            )
            from veadk.cli.studio_sandbox_tools import (
                ensure_studio_agent_model_credential,
                ensure_studio_agent_tool,
                ensure_studio_code_env_tool,
                studio_sandbox_agent_model_name,
                studio_sandbox_model_base_url,
                studio_sandbox_tool_name_candidates,
            )

            snapshot_labels = {
                "codex_snapshot": "Codex Snapshot",
                "openclaw_snapshot": "OpenClaw Snapshot",
                "hermes_snapshot": "Hermes Snapshot",
            }
            snapshot_purposes = {
                "codex_snapshot": "codex",
                "openclaw_snapshot": "openclaw",
                "hermes_snapshot": "hermes",
            }
            sandbox_agent_model_name = studio_sandbox_agent_model_name(provider_id)
            sandbox_model_base_url = studio_sandbox_model_base_url(provider_id)
            missing_snapshot_tools = {
                kind: studio_sandbox_tool_name_candidates(
                    vefaas_app_name,
                    snapshot_purposes[kind],
                    snapshot=True,
                )
                for kind, tool_id in snapshot_tool_ids.items()
                if not str(tool_id or "").strip()
            }
            if missing_snapshot_tools:
                with ThreadPoolExecutor(
                    max_workers=len(missing_snapshot_tools)
                ) as executor:
                    tool_futures = {}
                    for kind, tool_names in missing_snapshot_tools.items():
                        if tool_futures:
                            sleep(_SANDBOX_TOOL_CREATE_STAGGER_SECONDS)
                        tool_name = tool_names[0]
                        label = snapshot_labels[kind]
                        click.echo(f"Creating AgentKit {label} Tool '{tool_name}'…")
                        base_kind = kind.removesuffix("_snapshot")
                        if base_kind == "codex":
                            future = executor.submit(
                                ensure_studio_code_env_tool,
                                name=tool_name,
                                legacy_names=tool_names[1:],
                                enable_snapshot=True,
                                create_min_interval=(
                                    _SANDBOX_TOOL_CREATE_STAGGER_SECONDS
                                ),
                                region=target.region,
                                access_key=ak,
                                secret_key=sk,
                                session_token=session_token or "",
                            )
                        else:
                            future = executor.submit(
                                ensure_studio_agent_tool,
                                name=tool_name,
                                kind=base_kind,
                                enable_snapshot=True,
                                model_name=sandbox_agent_model_name,
                                create_min_interval=(
                                    _SANDBOX_TOOL_CREATE_STAGGER_SECONDS
                                ),
                                region=target.region,
                                access_key=ak,
                                secret_key=sk,
                                session_token=session_token or "",
                            )
                        tool_futures[kind] = future
                    for kind, future in tool_futures.items():
                        label = snapshot_labels[kind]
                        try:
                            snapshot_tool_ids[kind] = future.result()
                        except Exception as error:
                            detail = _safe_exception_detail(
                                error,
                                secrets=(ak, sk, session_token),
                            )
                            raise click.ClickException(
                                f"Failed to provision the AgentKit {label} Tool. "
                                f"Underlying error:\n{detail}"
                            ) from error
                        click.echo(f"AgentKit {label} Tool is ready.")

                with ThreadPoolExecutor(
                    max_workers=len(missing_snapshot_tools)
                ) as executor:
                    credential_futures = {}
                    for kind in missing_snapshot_tools:
                        tool_id = snapshot_tool_ids[kind]
                        base_kind = kind.removesuffix("_snapshot")
                        label = snapshot_labels[kind]
                        click.echo(f"Creating AgentKit {label} model credential…")
                        if base_kind == "codex":
                            future = executor.submit(
                                ensure_skill_creator_model_credential,
                                tool_id=tool_id,
                                region=target.region,
                                access_key=ak,
                                secret_key=sk,
                                session_token=session_token,
                                provider=provider_id,
                                model_name=sandbox_agent_model_name,
                            )
                        else:
                            future = executor.submit(
                                ensure_studio_agent_model_credential,
                                tool_id=tool_id,
                                kind=base_kind,
                                model_name=sandbox_agent_model_name,
                                model_base_url=sandbox_model_base_url,
                                region=target.region,
                                access_key=ak,
                                secret_key=sk,
                                session_token=session_token,
                                provider=provider_id,
                            )
                        credential_futures[kind] = future
                    for kind, future in credential_futures.items():
                        label = snapshot_labels[kind]
                        try:
                            future.result()
                        except Exception as error:
                            detail = _safe_exception_detail(
                                error,
                                secrets=(ak, sk, session_token),
                            )
                            raise click.ClickException(
                                f"Failed to provision the AgentKit {label} model "
                                f"credential. Underlying error:\n{detail}"
                            ) from error
                        click.echo(f"AgentKit {label} model credential is ready.")

            environment_overrides["SANDBOX_CHAT_CODEX_SNAPSHOT"] = str(
                snapshot_tool_ids["codex_snapshot"] or ""
            )
            environment_overrides["SANDBOX_CHAT_OPENCLAW_SNAPSHOT"] = str(
                snapshot_tool_ids["openclaw_snapshot"] or ""
            )
            environment_overrides["SANDBOX_CHAT_HERMES_SNAPSHOT"] = str(
                snapshot_tool_ids["hermes_snapshot"] or ""
            )
        if provider_id == "byteplus":
            environment_overrides["CLOUD_PROVIDER"] = provider_id
            environment_overrides["AGENTKIT_CLOUD_PROVIDER"] = provider_id
            environment_overrides["BYTEPLUS_REGION"] = target.region
            environment_overrides["DATABASE_VIKING_REGION"] = (
                DEFAULT_BYTEPLUS_VIKING_MEMORY_REGION
            )
            has_explicit_sandbox_tool = any(
                tool_id is not None
                for tool_id in (
                    sandbox_dev_tool_id,
                    sandbox_chat_codex_tool_id,
                    sandbox_chat_openclaw_tool_id,
                    sandbox_chat_hermes_tool_id,
                )
            )
            repair_sandbox_tools = (
                service_client is not None or has_explicit_sandbox_tool
            )
            byteplus_sandbox_tool_ids = {
                "dev": sandbox_dev_tool_id
                if sandbox_dev_tool_id is not None
                else current_env.get("SANDBOX_DEV", ""),
                "codex": sandbox_chat_codex_tool_id
                if sandbox_chat_codex_tool_id is not None
                else current_env.get("SANDBOX_CHAT_CODEX", ""),
                "openclaw": sandbox_chat_openclaw_tool_id
                if sandbox_chat_openclaw_tool_id is not None
                else current_env.get("SANDBOX_CHAT_OPENCLAW", ""),
                "hermes": sandbox_chat_hermes_tool_id
                if sandbox_chat_hermes_tool_id is not None
                else current_env.get("SANDBOX_CHAT_HERMES", ""),
            }
            byteplus_sandbox_labels = {
                "dev": "Dev Sandbox",
                "codex": "Codex",
                "openclaw": "OpenClaw",
                "hermes": "Hermes",
            }
            byteplus_sandbox_purposes = {
                "dev": "dev",
                "codex": "codex",
                "openclaw": "openclaw",
                "hermes": "hermes",
            }
            if repair_sandbox_tools:
                from veadk.cli.frontend_skill_creator import (
                    ensure_skill_creator_model_credential,
                )
                from veadk.cli.studio_sandbox_tools import (
                    ensure_studio_agent_model_credential,
                    ensure_studio_agent_tool,
                    ensure_studio_code_env_tool,
                    ensure_studio_dev_env_tool,
                    studio_sandbox_agent_model_name,
                    studio_sandbox_model_base_url,
                    studio_sandbox_tool_name_candidates,
                )

                sandbox_agent_model_name = studio_sandbox_agent_model_name(provider_id)
                sandbox_model_base_url = studio_sandbox_model_base_url(provider_id)
                missing_sandbox_tools: dict[str, tuple[str, ...]] = {}
                for kind, tool_id in byteplus_sandbox_tool_ids.items():
                    label = byteplus_sandbox_labels[kind]
                    if str(tool_id or "").strip():
                        click.echo(f"Using AgentKit {label} Tool '{tool_id}'.")
                        continue
                    tool_names = studio_sandbox_tool_name_candidates(
                        vefaas_app_name,
                        byteplus_sandbox_purposes[kind],
                        snapshot=kind.endswith("_snapshot"),
                    )
                    click.echo(f"Creating AgentKit {label} Tool '{tool_names[0]}'…")
                    missing_sandbox_tools[kind] = tool_names

                if missing_sandbox_tools:
                    with ThreadPoolExecutor(
                        max_workers=len(missing_sandbox_tools)
                    ) as ex:
                        tool_futures = {}
                        for kind, tool_names in missing_sandbox_tools.items():
                            if tool_futures:
                                sleep(_SANDBOX_TOOL_CREATE_STAGGER_SECONDS)
                            tool_name = tool_names[0]
                            base_kind = kind.removesuffix("_snapshot")
                            enable_snapshot = kind.endswith("_snapshot")
                            if base_kind == "codex":
                                future = ex.submit(
                                    ensure_studio_code_env_tool,
                                    name=tool_name,
                                    legacy_names=tool_names[1:],
                                    enable_snapshot=enable_snapshot,
                                    create_min_interval=(
                                        _SANDBOX_TOOL_CREATE_STAGGER_SECONDS
                                    ),
                                    region=target.region,
                                    access_key=ak,
                                    secret_key=sk,
                                    session_token=session_token or "",
                                )
                            elif base_kind == "dev":
                                future = ex.submit(
                                    ensure_studio_dev_env_tool,
                                    name=tool_name,
                                    create_min_interval=(
                                        _SANDBOX_TOOL_CREATE_STAGGER_SECONDS
                                    ),
                                    region=target.region,
                                    access_key=ak,
                                    secret_key=sk,
                                    session_token=session_token or "",
                                )
                            else:
                                future = ex.submit(
                                    ensure_studio_agent_tool,
                                    name=tool_name,
                                    kind=base_kind,
                                    enable_snapshot=enable_snapshot,
                                    model_name=sandbox_agent_model_name,
                                    create_min_interval=(
                                        _SANDBOX_TOOL_CREATE_STAGGER_SECONDS
                                    ),
                                    region=target.region,
                                    access_key=ak,
                                    secret_key=sk,
                                    session_token=session_token or "",
                                )
                            tool_futures[kind] = future
                        for kind, future in tool_futures.items():
                            label = byteplus_sandbox_labels[kind]
                            try:
                                byteplus_sandbox_tool_ids[kind] = future.result()
                            except Exception as error:
                                detail = _safe_exception_detail(
                                    error,
                                    secrets=(ak, sk, session_token),
                                )
                                raise click.ClickException(
                                    f"Failed to provision the AgentKit {label} Tool. "
                                    f"Underlying error:\n{detail}"
                                ) from error
                            click.echo(f"AgentKit {label} Tool is ready.")

                credential_futures = {}
                with ThreadPoolExecutor(
                    max_workers=len(byteplus_sandbox_tool_ids)
                ) as ex:
                    for kind, tool_id in byteplus_sandbox_tool_ids.items():
                        tool_id = str(tool_id or "").strip()
                        if not tool_id:
                            continue
                        label = byteplus_sandbox_labels[kind]
                        click.echo(f"Creating AgentKit {label} model credential…")
                        base_kind = kind.removesuffix("_snapshot")
                        if base_kind in {"codex", "dev"}:
                            code_model_name = (
                                sandbox_agent_model_name
                                if base_kind == "codex"
                                else None
                            )
                            future = ex.submit(
                                retry_transient_cloud_operation,
                                partial(
                                    ensure_skill_creator_model_credential,
                                    tool_id=tool_id,
                                    region=target.region,
                                    access_key=ak,
                                    secret_key=sk,
                                    session_token=session_token,
                                    provider=provider_id,
                                    model_name=code_model_name,
                                ),
                            )
                        else:
                            future = ex.submit(
                                retry_transient_cloud_operation,
                                partial(
                                    ensure_studio_agent_model_credential,
                                    tool_id=tool_id,
                                    kind=base_kind,
                                    model_name=sandbox_agent_model_name,
                                    model_base_url=sandbox_model_base_url,
                                    region=target.region,
                                    access_key=ak,
                                    secret_key=sk,
                                    session_token=session_token,
                                    provider=provider_id,
                                ),
                            )
                        credential_futures[kind] = future
                    for kind, future in credential_futures.items():
                        label = byteplus_sandbox_labels[kind]
                        try:
                            future.result()
                        except Exception as error:
                            detail = _safe_exception_detail(
                                error,
                                secrets=(ak, sk, session_token),
                            )
                            raise click.ClickException(
                                f"Failed to provision the AgentKit {label} model "
                                f"credential. Underlying error:\n{detail}"
                            ) from error
                        click.echo(f"AgentKit {label} model credential is ready.")

                environment_overrides["SANDBOX_CHAT_CODEX"] = str(
                    byteplus_sandbox_tool_ids["codex"] or ""
                )
                environment_overrides["SANDBOX_CHAT_OPENCLAW"] = str(
                    byteplus_sandbox_tool_ids["openclaw"] or ""
                )
                environment_overrides["SANDBOX_CHAT_HERMES"] = str(
                    byteplus_sandbox_tool_ids["hermes"] or ""
                )
                environment_overrides["SANDBOX_DEV"] = str(
                    byteplus_sandbox_tool_ids["dev"] or ""
                )
        if branding_title is not None:
            environment_overrides["VEADK_SITE_TITLE"] = branding_title
        if sandbox_dev_tool_id is not None:
            environment_overrides["SANDBOX_DEV"] = sandbox_dev_tool_id
        if sandbox_chat_codex_tool_id is not None:
            environment_overrides["SANDBOX_CHAT_CODEX"] = sandbox_chat_codex_tool_id
        if sandbox_chat_openclaw_tool_id is not None:
            environment_overrides["SANDBOX_CHAT_OPENCLAW"] = (
                sandbox_chat_openclaw_tool_id
            )
        if sandbox_chat_hermes_tool_id is not None:
            environment_overrides["SANDBOX_CHAT_HERMES"] = sandbox_chat_hermes_tool_id
        if sandbox_chat_codex_snapshot_tool_id is not None:
            environment_overrides["SANDBOX_CHAT_CODEX_SNAPSHOT"] = (
                sandbox_chat_codex_snapshot_tool_id
            )
        if sandbox_chat_openclaw_snapshot_tool_id is not None:
            environment_overrides["SANDBOX_CHAT_OPENCLAW_SNAPSHOT"] = (
                sandbox_chat_openclaw_snapshot_tool_id
            )
        if sandbox_chat_hermes_snapshot_tool_id is not None:
            environment_overrides["SANDBOX_CHAT_HERMES_SNAPSHOT"] = (
                sandbox_chat_hermes_snapshot_tool_id
            )
        _validate_distinct_sandbox_tool_ids(
            {
                "codex": environment_overrides.get(
                    "SANDBOX_CHAT_CODEX", current_env.get("SANDBOX_CHAT_CODEX", "")
                ),
                "codex_snapshot": environment_overrides.get(
                    "SANDBOX_CHAT_CODEX_SNAPSHOT",
                    current_env.get("SANDBOX_CHAT_CODEX_SNAPSHOT", ""),
                ),
                "openclaw": environment_overrides.get(
                    "SANDBOX_CHAT_OPENCLAW",
                    current_env.get("SANDBOX_CHAT_OPENCLAW", ""),
                ),
                "openclaw_snapshot": environment_overrides.get(
                    "SANDBOX_CHAT_OPENCLAW_SNAPSHOT",
                    current_env.get("SANDBOX_CHAT_OPENCLAW_SNAPSHOT", ""),
                ),
                "hermes": environment_overrides.get(
                    "SANDBOX_CHAT_HERMES",
                    current_env.get("SANDBOX_CHAT_HERMES", ""),
                ),
                "hermes_snapshot": environment_overrides.get(
                    "SANDBOX_CHAT_HERMES_SNAPSHOT",
                    current_env.get("SANDBOX_CHAT_HERMES_SNAPSHOT", ""),
                ),
            }
        )
        from frontend.service.studio_scheduler.deploy import (
            deploy_scheduler_for_studio_update,
        )

        click.echo("Updating the Studio cronjob scheduler and minute timer…")
        try:
            _, _, _, _, scheduler_base = deploy_scheduler_for_studio_update(
                service,
                studio_function_id=target.function_id,
                package_root=package_dir,
                provider=provider_id,
                project=target.project,
                environment_overrides=environment_overrides,
            )
            environment_overrides["VEADK_STUDIO_CRONJOB_SCHEDULER_BASE"] = (
                scheduler_base
            )
            url = service.update_application_code_bundle(
                application_id=target.application_id,
                function_id=target.function_id,
                path=str(package_dir),
                environment_overrides=environment_overrides or None,
            )
        except Exception as error:
            if _is_retryable_cloud_read_error(error):
                raise click.ClickException(
                    "Studio update was interrupted by a temporary cloud network "
                    "error after retrying. The cloud release may still be running; "
                    "wait briefly and run the same update command again."
                ) from error
            detail = _safe_exception_detail(
                error,
                secrets=(ak, sk, session_token),
            )
            raise click.ClickException(
                f"Could not finish the Studio update.\n{detail}"
            ) from error
        click.echo("")
        click.echo(f"✅ Studio updated: {url}")
        click.echo(f"   application id: {target.application_id}")
        click.echo(f"   function id: {target.function_id}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
