#!/usr/bin/env python3
"""Smoke-test the Studio custom A/B debug -> deploy -> chat workflow.

The script mirrors the UI journey, but calls the backend APIs directly:

1. Studio opens and confirms backend Volcengine credentials.
2. User creates a custom agent draft.
3. User starts baseline and comparison debug environments.
4. User sends a debug message to both.
5. User deploys the chosen configuration.
6. User opens the deployed runtime and chats with it.

This tests the product boundary that matters for E2E confidence: the frontend's
intended backend calls, the backend behavior, and the real AgentKit Runtime /
VeFaaS effects observable through Studio's runtime proxy.
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml as _yaml
except ImportError:  # pragma: no cover
    _yaml = None


DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "custom_ab_deploy_chat.local.yaml"
)

SENSITIVE_KEY_RE = re.compile(
    r"(cookie|token|secret|password|apikey|api_key|access_key|secret_key|credential)",
    re.IGNORECASE,
)
SENSITIVE_ENV_NAME_RE = re.compile(
    r"(access_?key|secret_?key|api_?key|password|passwd|token|authorization|"
    r"cookie|credential|private_?key)",
    re.IGNORECASE,
)
SENSITIVE_URL_PARAMETER_RE = re.compile(
    r"(?i)([?&](?:authorization|access_?key|secret_?key|api_?key|token|signature|"
    r"credential)=)([^&#\s\"'<>\{\},\\]+)"
)
BEARER_TOKEN_RE = re.compile(r"(?i)(\bbearer\s+)([^\s,;]+)")
STRUCTURED_SECRET_RE = re.compile(
    r"(?i)((?:[\"']?(?:authorization|access_?key|secret_?key|api_?key|password|"
    r"passwd|token|cookie|credential)[\"']?)\s*[:=]\s*[\"'])([^\"']+)([\"'])"
)
REDACTED = "***REDACTED***"
SUPPORTED_CLOUD_PROVIDERS = {"volcengine", "byteplus"}
VOLCENGINE_DEFAULT_REGION = "cn-beijing"
BYTEPLUS_DEFAULT_REGION = "ap-southeast-1"
VOLCENGINE_DEFAULT_MODEL_NAME = "doubao-seed-2-1-pro-260628"
BYTEPLUS_DEFAULT_MODEL_NAME = "seed-2-0-lite-260228"
BYTEPLUS_MODEL_API_BASE = "https://ark.ap-southeast.bytepluses.com/api/v3"


class SmokeError(RuntimeError):
    """Raised for workflow assertion failures."""


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.text())


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SmokeError(
            f"Config file not found: {path}. Copy the example config first."
        )
    text = path.read_text(encoding="utf-8")
    data = _yaml.safe_load(text) if _yaml is not None else parse_simple_yaml(text)
    data = data or {}
    if not isinstance(data, dict):
        raise SmokeError("Config root must be a YAML mapping.")
    return data


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the simple mapping-only YAML shape used by Studio E2E configs.

    PyYAML is preferred when installed. This fallback intentionally supports
    only nested mappings plus simple inline scalars/lists so dry-runs work in a
    minimal Python environment.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = strip_yaml_comment(raw_line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if stripped.startswith("- "):
            raise SmokeError(
                "PyYAML is required for block-list config syntax "
                f"(line {lineno}). Use inline lists or install PyYAML."
            )
        if ":" not in stripped:
            raise SmokeError(f"Invalid config line {lineno}: {raw_line}")
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        if not key:
            raise SmokeError(f"Invalid empty config key on line {lineno}.")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise SmokeError(f"Invalid indentation on line {lineno}.")
        parent = stack[-1][1]
        value_text = raw_value.strip()
        if value_text == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_simple_yaml_scalar(value_text)
    return root


def strip_yaml_comment(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "#":
            return line[:index]
    return line


def parse_simple_yaml_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    if value.startswith(("[", "{")) and value.endswith(("]", "}")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            pass
    if value in {"[]", "{}"}:
        return [] if value == "[]" else {}
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return ast.literal_eval(value)
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_simple_yaml_scalar(item.strip()) for item in inner.split(",")]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def deep_get(data: dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def configured_cloud_provider(config: dict[str, Any]) -> str:
    value = str(
        deep_get(config, "studio.provider", "")
        or deep_get(config, "agent.cloud_provider", "")
        or ""
    ).strip().lower()
    return value


def cloud_provider(config: dict[str, Any]) -> str:
    return configured_cloud_provider(config) or "volcengine"


def provider_default_region(provider: str) -> str:
    return BYTEPLUS_DEFAULT_REGION if provider == "byteplus" else VOLCENGINE_DEFAULT_REGION


def config_region(config: dict[str, Any]) -> str:
    return str(
        deep_get(config, "deploy.region", "")
        or provider_default_region(cloud_provider(config))
    )


def provider_default_model_name(provider: str) -> str:
    return BYTEPLUS_DEFAULT_MODEL_NAME if provider == "byteplus" else VOLCENGINE_DEFAULT_MODEL_NAME


def redact_mapping(mapping: dict[str, Any]) -> dict[str, str]:
    result = {}
    for key, value in mapping.items():
        text = "" if value is None else str(value)
        result[str(key)] = REDACTED if SENSITIVE_KEY_RE.search(str(key)) and text else redact_text(text)
    return result


def redact_text(value: str, extra_secrets: Iterable[str] = ()) -> str:
    redacted = value
    for name, secret in os.environ.items():
        if SENSITIVE_ENV_NAME_RE.search(name) and secret:
            redacted = redacted.replace(str(secret), REDACTED)
    for secret in extra_secrets:
        if secret:
            redacted = redacted.replace(str(secret), REDACTED)
    redacted = SENSITIVE_URL_PARAMETER_RE.sub(r"\1" + REDACTED, redacted)
    redacted = BEARER_TOKEN_RE.sub(r"\1" + REDACTED, redacted)
    return STRUCTURED_SECRET_RE.sub(r"\1" + REDACTED + r"\3", redacted)


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            text_key = str(key)
            result[text_key] = REDACTED if SENSITIVE_KEY_RE.search(text_key) else redact_value(child)
        return result
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def assert_contains(actual: str, expected: str, label: str) -> None:
    if expected and normalize_text(expected) not in normalize_text(actual):
        raise SmokeError(f"{label}: expected text not found: {expected!r}")


def print_json(label: str, payload: Any) -> None:
    print(f"{label}: {json.dumps(redact_value(payload), ensure_ascii=False, indent=2)}")


class StepLogger:
    def __init__(self) -> None:
        self.index = 0

    def step(self, ui_action: str, api: str) -> None:
        self.index += 1
        print(f"\n[{self.index:02d}] UI: {ui_action}")
        print(f"     API: {api}")

    def ok(self, message: str) -> None:
        print(f"     OK: {message}")


class StudioClient:
    def __init__(self, config: dict[str, Any]) -> None:
        studio = config.get("studio") or {}
        raw_base_url = str(studio.get("base_url") or "").strip()
        parsed_base_url = urllib.parse.urlsplit(raw_base_url)
        base_url = urllib.parse.urlunsplit(
            (
                parsed_base_url.scheme,
                parsed_base_url.netloc,
                parsed_base_url.path.rstrip("/"),
                "",
                "",
            )
        )
        if not base_url:
            raise SmokeError("studio.base_url is required.")
        self.base_url = base_url
        self.timeout = float(studio.get("timeout_seconds") or 900)
        auth = studio.get("auth") or {}
        self.headers = self._build_headers(auth)
        self.auth_query = self._build_auth_query(parsed_base_url.query, auth)

    def _build_auth_query(self, base_query: str, auth: dict[str, Any]) -> str:
        params = urllib.parse.parse_qsl(base_query, keep_blank_values=True)
        configured = auth.get("query") or auth.get("query_params") or ""
        if isinstance(configured, dict):
            params.extend(
                (str(key), str(value))
                for key, value in configured.items()
                if value is not None
            )
        elif str(configured).strip():
            query_text = str(configured).strip()
            if "?" in query_text:
                query_text = urllib.parse.urlsplit(query_text).query
            query_text = query_text[1:] if query_text.startswith("?") else query_text
            params.extend(urllib.parse.parse_qsl(query_text, keep_blank_values=True))
        return urllib.parse.urlencode(params)

    def _with_auth_query(self, path: str) -> str:
        if not self.auth_query:
            return path
        parsed = urllib.parse.urlsplit(path)
        incoming = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        existing = {key for key, _ in incoming}
        merged = list(incoming)
        for key, value in urllib.parse.parse_qsl(self.auth_query, keep_blank_values=True):
            if key not in existing:
                merged.append((key, value))
        return urllib.parse.urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urllib.parse.urlencode(merged),
                parsed.fragment,
            )
        )

    def _build_headers(self, auth: dict[str, Any]) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        extra = auth.get("headers") or {}
        if isinstance(extra, dict):
            headers.update({str(k): str(v) for k, v in extra.items() if v is not None})
        cookie = str(auth.get("cookie") or "").strip()
        if cookie:
            headers["Cookie"] = cookie
        bearer = str(auth.get("bearer_token") or "").strip()
        if bearer:
            headers["Authorization"] = (
                bearer if bearer.lower().startswith("bearer ") else f"Bearer {bearer}"
            )
        local_user = str(auth.get("local_user") or "").strip()
        if local_user:
            headers["X-VeADK-Local-User"] = local_user
        return headers

    def request(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        *,
        accept_sse: bool = False,
        timeout: float | None = None,
        allow_statuses: Iterable[int] = (),
    ) -> HttpResponse:
        path = self._with_auth_query(path)
        url = self.base_url + path
        data = None
        headers = dict(self.headers)
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if accept_sse:
            headers["Accept"] = "text/event-stream"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        allowed = set(allow_statuses)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return HttpResponse(
                    status=int(resp.status),
                    headers={k.lower(): v for k, v in resp.headers.items()},
                    body=resp.read(),
                )
        except urllib.error.HTTPError as exc:
            body_bytes = exc.read()
            if exc.code in allowed:
                return HttpResponse(
                    status=int(exc.code),
                    headers={k.lower(): v for k, v in exc.headers.items()},
                    body=body_bytes,
                )
            detail = body_bytes.decode("utf-8", "replace")
            hint = ""
            if exc.code in {401, 403}:
                hint = (
                    "\nAuthentication or Studio RBAC failed. Check studio.auth and "
                    "the signed-in user's create/manage-agent permissions."
                )
            header_secrets = [
                str(value)
                for key, value in self.headers.items()
                if SENSITIVE_KEY_RE.search(key) or key.lower() in {"authorization", "cookie"}
            ]
            raise SmokeError(
                f"{method} {path} failed: HTTP {exc.code}\n"
                + redact_text(detail + hint, header_secrets)
            ) from exc
        except urllib.error.URLError as exc:
            raise SmokeError(f"{method} {path} failed: {exc}") from exc

    def json_request(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        return self.request(method, path, body, timeout=timeout).json()

    def stream_sse(
        self,
        method: str,
        path: str,
        body: Any,
        *,
        timeout: float | None = None,
        echo_messages: bool = True,
        return_events_on_timeout: bool = False,
    ) -> list[dict[str, Any]]:
        path = self._with_auth_query(path)
        url = self.base_url + path
        headers = dict(self.headers)
        headers["Accept"] = "text/event-stream"
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        events: list[dict[str, Any]] = []
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                pending: list[str] = []
                for raw in resp:
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if not line:
                        event = parse_sse_data(pending)
                        pending = []
                        if event is not None:
                            events.append(event)
                            if echo_messages and event.get("message"):
                                print(
                                    f"     stream[{event.get('phase') or 'event'}]: "
                                    f"{event.get('message')}",
                                    flush=True,
                                )
                        continue
                    if line.startswith("data:"):
                        pending.append(line[5:].lstrip())
                event = parse_sse_data(pending)
                if event is not None:
                    events.append(event)
        except (TimeoutError, socket.timeout) as exc:
            if return_events_on_timeout and events:
                return events
            raise SmokeError(f"{method} {path} timed out while reading SSE") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            header_secrets = [
                str(value)
                for key, value in headers.items()
                if SENSITIVE_KEY_RE.search(key) or key.lower() in {"authorization", "cookie"}
            ]
            raise SmokeError(
                f"{method} {path} failed: HTTP {exc.code}\n"
                + redact_text(detail, header_secrets)
            ) from exc
        except urllib.error.URLError as exc:
            raise SmokeError(f"{method} {path} failed: {exc}") from exc
        return events


def parse_sse_data(lines: list[str]) -> dict[str, Any] | None:
    if not lines:
        return None
    payload = "\n".join(lines)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {"raw": payload}
    return data if isinstance(data, dict) else {"data": data}


def collect_event_text(events: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for event in events:
        content = event.get("content")
        if not isinstance(content, dict):
            continue
        for part in content.get("parts") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "".join(chunks)


def assert_no_event_errors(events: list[dict[str, Any]], label: str) -> None:
    for event in events:
        error = event.get("error") or event.get("errorMessage") or event.get("error_message")
        if error:
            raise SmokeError(f"{label}: runtime returned error event: {error}")


def clean_env(config_value: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(config_value, list):
        for item in config_value:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            value = str(item.get("value") or "")
            if key and value.strip():
                rows.append({"key": key, "value": value})
        return rows
    if isinstance(config_value, dict):
        for key, value in config_value.items():
            value_str = "" if value is None else str(value)
            if str(key).strip() and value_str.strip():
                rows.append({"key": str(key), "value": value_str})
    return rows


def network_config(config: dict[str, Any]) -> dict[str, Any] | None:
    network = deep_get(config, "deploy.network", {}) or {}
    if not isinstance(network, dict):
        return None
    mode = str(network.get("mode") or "public").strip()
    if not mode or mode == "public":
        return None

    subnet_ids = network.get("subnet_ids") or network.get("subnetIds")
    if isinstance(subnet_ids, str):
        subnet_ids = [item.strip() for item in subnet_ids.split(",") if item.strip()]

    result: dict[str, Any] = {"mode": mode}
    vpc_id = network.get("vpc_id") or network.get("vpcId")
    if vpc_id:
        result["vpc_id"] = str(vpc_id)
    if subnet_ids:
        result["subnet_ids"] = [str(item) for item in subnet_ids]
    if "enable_shared_internet_access" in network:
        result["enable_shared_internet_access"] = truthy(
            network["enable_shared_internet_access"]
        )
    elif "enableSharedInternetAccess" in network:
        result["enable_shared_internet_access"] = truthy(
            network["enableSharedInternetAccess"]
        )
    return result


def runtime_proxy_path(runtime_id: str, region: str, path: str) -> str:
    sep = "&" if "?" in path else "?"
    return (
        f"/web/runtime-proxy/{urllib.parse.quote(runtime_id, safe='')}{path}"
        f"{sep}region={urllib.parse.quote(region, safe='')}"
    )


def agent_name(config: dict[str, Any]) -> str:
    explicit = str(deep_get(config, "agent.name", "") or "").strip()
    if explicit:
        return explicit
    prefix = str(deep_get(config, "agent.name_prefix", "studio-e2e-custom") or "").strip()
    return f"{prefix}-{int(time.time())}"


def build_agent_draft(config: dict[str, Any], name: str) -> dict[str, Any]:
    baseline = config.get("baseline") or {}
    memory = deep_get(config, "agent.memory", {}) or {}
    knowledge = deep_get(config, "agent.knowledgebase", {}) or {}
    tracing = deep_get(config, "agent.tracing", {}) or {}
    deploy = config.get("deploy") or {}
    provider = cloud_provider(config)
    env_values = {
        row["key"]: row["value"] for row in clean_env(deploy.get("env") or {})
    }
    project_name = str(deploy.get("project_name") or "").strip()
    if provider == "byteplus" and project_name and "ARK_PROJECT_NAME" not in env_values:
        env_values["ARK_PROJECT_NAME"] = project_name
    return {
        "name": name,
        "description": str(baseline.get("description") or "Studio E2E assistant."),
        "instruction": str(baseline.get("instruction") or "Reply concisely."),
        "cloudProvider": provider,
        "agentType": str(deep_get(config, "agent.agent_type", "llm") or "llm"),
        "maxIterations": int(deep_get(config, "agent.max_iterations", 3) or 3),
        "a2aUrl": str(deep_get(config, "agent.a2a_url", "") or ""),
        "model": str(baseline.get("model") or ""),
        "modelName": str(baseline.get("model_name") or provider_default_model_name(provider)),
        "modelProvider": str(baseline.get("model_provider") or ""),
        "modelApiBase": str(baseline.get("model_api_base") or ""),
        "tools": [str(item) for item in as_list(deep_get(config, "agent.tools", []))],
        "skills": [str(item) for item in as_list(deep_get(config, "agent.skills", []))],
        "memory": {
            "shortTerm": truthy(memory.get("short_term")),
            "longTerm": truthy(memory.get("long_term")),
        },
        "knowledgebase": truthy(knowledge.get("enabled")),
        "tracing": truthy(tracing.get("enabled")),
        "subAgents": [],
        "builtinTools": [
            str(item) for item in as_list(deep_get(config, "agent.builtin_tools", []))
        ],
        "customTools": [
            item for item in as_list(deep_get(config, "agent.custom_tools", []))
            if isinstance(item, dict)
        ],
        "mcpTools": [
            item for item in as_list(deep_get(config, "agent.mcp_tools", []))
            if isinstance(item, dict)
        ],
        "shortTermBackend": str(memory.get("short_term_backend") or "local"),
        "longTermBackend": str(memory.get("long_term_backend") or "local"),
        "autoSaveSession": truthy(memory.get("auto_save_session")),
        "knowledgebaseBackend": str(knowledge.get("backend") or "local"),
        "knowledgebaseIndex": str(knowledge.get("index") or ""),
        "tracingExporters": [
            str(item) for item in as_list(tracing.get("exporters") or [])
        ],
        "selectedSkills": [
            item for item in as_list(deep_get(config, "agent.selected_skills", []))
            if isinstance(item, dict)
        ],
        "deployment": {
            "feishuEnabled": truthy(deep_get(config, "deploy.im.feishu.enabled")),
            "envValues": env_values,
        },
    }


def apply_variant(draft: dict[str, Any], config: dict[str, Any], variant_key: str) -> dict[str, Any]:
    variant = config.get(variant_key) or {}
    next_draft = copy.deepcopy(draft)
    if variant.get("model_name") is not None:
        next_draft["modelName"] = str(variant.get("model_name") or "")
    if variant.get("model_provider") is not None:
        next_draft["modelProvider"] = str(variant.get("model_provider") or "")
    if variant.get("model_api_base") is not None:
        next_draft["modelApiBase"] = str(variant.get("model_api_base") or "")
    if variant.get("description") is not None:
        next_draft["description"] = str(variant.get("description") or "")
    if variant.get("instruction") is not None:
        next_draft["instruction"] = str(variant.get("instruction") or "")
    return next_draft


def codegen_draft(draft: dict[str, Any]) -> dict[str, Any]:
    next_draft = copy.deepcopy(draft)
    deployment = next_draft.get("deployment") if isinstance(next_draft.get("deployment"), dict) else {}
    next_draft["deployment"] = {
        "feishuEnabled": truthy(deployment.get("feishuEnabled")),
    }
    return next_draft


def deploy_env(config: dict[str, Any]) -> list[dict[str, str]]:
    return clean_env(deep_get(config, "deploy.env", {}) or {})


def validate_config(config: dict[str, Any]) -> None:
    errors: list[str] = []
    if not str(deep_get(config, "studio.base_url", "") or "").strip():
        errors.append("studio.base_url is required.")
    provider = configured_cloud_provider(config)
    if provider and provider not in SUPPORTED_CLOUD_PROVIDERS:
        errors.append(
            "studio.provider or agent.cloud_provider must be one of "
            + ", ".join(sorted(SUPPORTED_CLOUD_PROVIDERS))
            + "."
        )
    winner = str(deep_get(config, "deploy.winner", "variant") or "variant")
    if winner not in {"baseline", "variant"}:
        errors.append("deploy.winner must be baseline or variant.")
    network = deep_get(config, "deploy.network", {}) or {}
    if isinstance(network, dict) and str(network.get("mode") or "public") in {"private", "both"}:
        if not str(network.get("vpc_id") or network.get("vpcId") or "").strip():
            errors.append("deploy.network.vpc_id is required for private/both mode.")
    if errors:
        raise SmokeError("Invalid config:\n- " + "\n- ".join(errors))


def verify_studio_ready(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any] | None = None,
) -> None:
    log.step(
        "Open Studio with backend cloud credentials",
        "GET /web/runtime-config, GET /web/access, GET /web/ui-config",
    )
    runtime_config = client.json_request("GET", "/web/runtime-config")
    if not isinstance(runtime_config, dict) or not runtime_config.get("credentials"):
        provider = cloud_provider(config or {})
        credential_hint = (
            "Set BYTEPLUS_ACCESS_KEY/BYTEPLUS_SECRET_KEY or run Studio with "
            "a BytePlus IAM role/STS credential."
            if provider == "byteplus"
            else "Set VOLCENGINE_ACCESS_KEY/VOLCENGINE_SECRET_KEY or run Studio with "
            "an IAM role/STS credential."
        )
        raise SmokeError(
            f"Studio backend does not report {provider} credentials. "
            + credential_hint
        )
    access = client.json_request("GET", "/web/access")
    capabilities = access.get("capabilities") if isinstance(access, dict) else {}
    if not capabilities.get("createAgents"):
        raise SmokeError(f"Signed-in user cannot create agents: {access}")
    ui_config = client.json_request("GET", "/web/ui-config")
    if not isinstance(ui_config, dict):
        raise SmokeError(f"/web/ui-config returned invalid payload: {ui_config}")
    expected_provider = configured_cloud_provider(config or {})
    actual_provider = str(ui_config.get("provider") or "").strip().lower()
    if expected_provider and actual_provider and actual_provider != expected_provider:
        raise SmokeError(
            f"/web/ui-config provider mismatch: expected {expected_provider}, got {actual_provider}"
        )
    log.ok(
        "backend credentials present; user can create agents; UI config loaded"
    )


def create_debug_run(
    client: StudioClient,
    log: StepLogger,
    variant_name: str,
    draft: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    log.step(
        f"Click start environment for {variant_name}",
        "POST /web/generated-agent-test-runs, POST /web/generated-agent-test-runs/{runId}/sessions",
    )
    run = client.json_request("POST", "/web/generated-agent-test-runs", {"draft": draft})
    if not isinstance(run, dict) or not run.get("runId") or not run.get("appName"):
        raise SmokeError(f"Invalid generated-agent test run response: {run}")
    session = client.json_request(
        "POST",
        f"/web/generated-agent-test-runs/{urllib.parse.quote(str(run['runId']), safe='')}/sessions",
        {"userId": user_id},
    )
    if not isinstance(session, dict) or not session.get("id"):
        raise SmokeError(f"Invalid generated-agent test session response: {session}")
    result = {
        "variant": variant_name,
        "runId": str(run["runId"]),
        "appName": str(run["appName"]),
        "sessionId": str(session["id"]),
    }
    log.ok(f"temporary debug environment ready: {result['runId']}")
    return result


def run_debug_message(
    client: StudioClient,
    log: StepLogger,
    runtime: dict[str, Any],
    user_id: str,
    message: str,
    expected: str,
    verify_trace: bool,
) -> dict[str, Any]:
    log.step(
        f"Send debug message to {runtime['variant']}",
        "POST /web/generated-agent-test-runs/{runId}/run_sse",
    )
    path = f"/web/generated-agent-test-runs/{urllib.parse.quote(runtime['runId'], safe='')}/run_sse"
    events = client.stream_sse(
        "POST",
        path,
        {
            "user_id": user_id,
            "session_id": runtime["sessionId"],
            "new_message": {"role": "user", "parts": [{"text": message}]},
            "streaming": True,
        },
        echo_messages=False,
    )
    assert_no_event_errors(events, f"debug {runtime['variant']}")
    text = collect_event_text(events)
    if not text.strip():
        raise SmokeError(f"debug {runtime['variant']}: empty assistant response")
    assert_contains(text, expected, f"debug {runtime['variant']}")
    trace_count = None
    if verify_trace:
        trace_path = (
            f"/web/generated-agent-test-runs/{urllib.parse.quote(runtime['runId'], safe='')}"
            f"/trace/session/{urllib.parse.quote(runtime['sessionId'], safe='')}"
        )
        trace = client.json_request("GET", trace_path)
        if not isinstance(trace, list):
            raise SmokeError(f"debug trace returned invalid payload: {trace}")
        trace_count = len(trace)
    log.ok(
        f"assistant responded; events={len(events)}"
        + (f"; trace_spans={trace_count}" if trace_count is not None else "")
    )
    return {
        "variant": runtime["variant"],
        "eventCount": len(events),
        "response": text,
        "traceSpanCount": trace_count,
    }


def generate_project_for_winner(
    client: StudioClient,
    log: StepLogger,
    winner: str,
    draft: dict[str, Any],
) -> dict[str, Any]:
    log.step(
        f"Click deploy this configuration for {winner}",
        "POST /web/generated-agent-projects",
    )
    project = client.json_request(
        "POST",
        "/web/generated-agent-projects",
        {"draft": codegen_draft(draft)},
    )
    if not isinstance(project, dict) or not project.get("name") or not project.get("files"):
        raise SmokeError(f"Invalid generated project response: {project}")
    files = project.get("files") or []
    paths = {str(item.get("path") or "") for item in files if isinstance(item, dict)}
    if "app.py" not in paths:
        raise SmokeError(f"Generated project missing app.py. Paths: {sorted(paths)}")
    if not any(path.endswith("/agent.py") or path == "agent.py" for path in paths):
        raise SmokeError(f"Generated project missing agent.py. Paths: {sorted(paths)}")
    log.ok(f"project generated: {project['name']} ({len(files)} files)")
    return project


def deploy_project(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
    project: dict[str, Any],
) -> dict[str, Any]:
    log.step(
        "Choose deployment options and click deploy",
        "POST /web/deploy-agentkit (SSE)",
    )
    deploy = config.get("deploy") or {}
    task_prefix = str(deploy.get("task_id_prefix") or "studio-e2e-custom")
    payload: dict[str, Any] = {
        "name": project["name"],
        "files": project["files"],
        "config": {
            "region": config_region(config),
            "projectName": str(deploy.get("project_name") or "default"),
            "network": network_config(config),
        },
        "taskId": f"{task_prefix}-{int(time.time())}",
        "sessionStorage": str(deploy.get("session_storage") or "persistent"),
        "description": str(deploy.get("description") or ""),
        "envs": deploy_env(config),
    }
    if deploy.get("min_instance") is not None:
        payload["minInstance"] = int(deploy["min_instance"])
    if deploy.get("max_instance") is not None:
        payload["maxInstance"] = int(deploy["max_instance"])
    if deploy.get("create_evaluation_sets") is not None:
        payload["createEvaluationSets"] = truthy(deploy.get("create_evaluation_sets"))
    im = deploy.get("im")
    if isinstance(im, dict):
        payload["im"] = im

    events = client.stream_sse("POST", "/web/deploy-agentkit", payload)
    final = next((event for event in reversed(events) if event.get("done")), None)
    if not final:
        raise SmokeError("Deployment stream ended without a terminal frame.")
    if not final.get("success"):
        raise SmokeError(f"Deployment failed: {final.get('error') or final}")
    if not final.get("runtimeId"):
        raise SmokeError(f"Deployment succeeded but did not return runtimeId: {final}")
    if not final.get("agentName"):
        raise SmokeError(f"Deployment succeeded but did not return agentName: {final}")
    log.ok(
        f"runtime deployed: runtimeId={final['runtimeId']} agentName={final['agentName']}"
    )
    return final


def request_with_retries(
    client: StudioClient,
    method: str,
    path: str,
    body: Any | None = None,
    *,
    attempts: int = 12,
    delay_seconds: float = 10.0,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return client.json_request(method, path, body)
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                print(f"     retry {attempt}/{attempts}: {exc}")
                time.sleep(delay_seconds)
    assert last_error is not None
    raise last_error


def connect_deployed_agent(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
    final: dict[str, Any],
    preferred_app: str,
) -> dict[str, Any]:
    log.step(
        "Open deployed agent from Studio",
        "GET /web/runtime-detail, GET /web/runtime-proxy/{runtimeId}/list-apps, GET /web/runtime-proxy/{runtimeId}/web/agent-info/{app}",
    )
    runtime_id = str(final["runtimeId"])
    region = str(final.get("region") or config_region(config))
    detail = client.json_request(
        "GET",
        f"/web/runtime-detail?runtimeId={urllib.parse.quote(runtime_id, safe='')}"
        f"&region={urllib.parse.quote(region, safe='')}",
    )
    if not isinstance(detail, dict) or detail.get("runtimeId") not in {runtime_id, ""}:
        raise SmokeError(f"Runtime detail returned invalid payload: {detail}")

    apps = request_with_retries(
        client,
        "GET",
        runtime_proxy_path(runtime_id, region, "/list-apps"),
    )
    if not isinstance(apps, list) or not apps:
        raise SmokeError(f"Runtime returned no apps: {apps}")
    app = preferred_app if preferred_app in apps else str(apps[0])
    info = request_with_retries(
        client,
        "GET",
        runtime_proxy_path(
            runtime_id,
            region,
            f"/web/agent-info/{urllib.parse.quote(app, safe='')}",
        ),
    )
    if not isinstance(info, dict) or not info.get("name"):
        raise SmokeError(f"Runtime agent-info returned invalid payload: {info}")
    log.ok(f"runtime data plane reachable; app={app}; status={detail.get('status')}")
    return {
        "runtimeId": runtime_id,
        "region": region,
        "app": app,
        "detail": detail,
        "agentInfo": info,
    }


def chat_with_deployed_agent(
    client: StudioClient,
    log: StepLogger,
    config: dict[str, Any],
    deployed: dict[str, Any],
) -> dict[str, Any]:
    log.step(
        "Send message to deployed agent",
        "POST /web/runtime-proxy/{runtimeId}/apps/{app}/users/{user}/sessions, POST /web/runtime-proxy/{runtimeId}/run_sse",
    )
    user_id = str(deep_get(config, "chat.user_id", "studio_e2e_chat_user") or "studio_e2e_chat_user")
    message = str(deep_get(config, "chat.message", "Hello") or "Hello")
    runtime_id = deployed["runtimeId"]
    region = deployed["region"]
    app = deployed["app"]
    session_path = (
        f"/apps/{urllib.parse.quote(app, safe='')}/users/"
        f"{urllib.parse.quote(user_id, safe='')}/sessions"
    )
    session = client.json_request(
        "POST",
        runtime_proxy_path(runtime_id, region, session_path),
        {},
    )
    session_id = str(session.get("id") or f"studio-e2e-session-{int(time.time())}") if isinstance(session, dict) else f"studio-e2e-session-{int(time.time())}"
    events = client.stream_sse(
        "POST",
        runtime_proxy_path(runtime_id, region, "/run_sse"),
        {
            "app_name": app,
            "user_id": user_id,
            "session_id": session_id,
            "new_message": {"role": "user", "parts": [{"text": message}]},
            "streaming": True,
        },
        timeout=float(deep_get(config, "chat.sse_idle_timeout_seconds", 60) or 60),
        echo_messages=False,
        return_events_on_timeout=True,
    )
    assert_no_event_errors(events, "deployed chat")
    text = collect_event_text(events)
    if not text.strip():
        raise SmokeError("deployed chat returned empty assistant response")
    assert_contains(text, str(deep_get(config, "chat.expected_contains", "") or ""), "deployed chat")
    log.ok(f"deployed agent responded; session={session_id}; events={len(events)}")
    return {
        "userId": user_id,
        "sessionId": session_id,
        "eventCount": len(events),
        "response": text,
    }


def delete_debug_runs(
    client: StudioClient,
    log: StepLogger,
    runtimes: list[dict[str, Any]],
) -> None:
    if not runtimes:
        return
    log.step(
        "Clean up temporary debug environments",
        "DELETE /web/generated-agent-test-runs/{runId}",
    )
    for runtime in runtimes:
        client.request(
            "DELETE",
            f"/web/generated-agent-test-runs/{urllib.parse.quote(runtime['runId'], safe='')}",
            allow_statuses={404},
        )
    log.ok(f"deleted {len(runtimes)} temporary debug run(s)")


def delete_runtime(
    client: StudioClient,
    log: StepLogger,
    runtime_id: str,
    region: str,
    *,
    verify: bool,
) -> None:
    log.step(
        "Delete deployed agent runtime",
        "POST /web/delete-runtime" + (", verify with GET /web/runtime-detail" if verify else ""),
    )
    client.json_request(
        "POST",
        "/web/delete-runtime",
        {"runtimeId": runtime_id, "region": region},
    )
    if verify:
        deadline = time.time() + 180
        while time.time() < deadline:
            response = client.request(
                "GET",
                f"/web/runtime-detail?runtimeId={urllib.parse.quote(runtime_id, safe='')}"
                f"&region={urllib.parse.quote(region, safe='')}",
                allow_statuses={403, 404, 502},
            )
            if response.status in {403, 404}:
                log.ok("runtime no longer accessible through control plane")
                return
            if response.status == 502 and "not found" in response.text().lower():
                log.ok("runtime no longer exists in AgentKit control plane")
                return
            time.sleep(10)
        raise SmokeError(f"Runtime deletion was not observable within timeout: {runtime_id}")
    log.ok(f"delete requested for runtime {runtime_id}")


def print_plan(config: dict[str, Any], base_draft: dict[str, Any]) -> None:
    deploy = config.get("deploy") or {}
    print("Studio:", deep_get(config, "studio.base_url", ""))
    print("Provider:", cloud_provider(config))
    print("Agent:", base_draft["name"])
    print("Winner:", deploy.get("winner") or "variant")
    print("Region:", config_region(config))
    print("Project:", deploy.get("project_name") or "default")
    print("Network:", json.dumps(network_config(config), ensure_ascii=False))
    print("Deploy env:", json.dumps(redact_mapping({row["key"]: row["value"] for row in deploy_env(config)}), ensure_ascii=False))


def run_workflow(config: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    validate_config(config)
    log = StepLogger()
    name = agent_name(config)
    base_draft = build_agent_draft(config, name)
    baseline_draft = apply_variant(base_draft, config, "baseline")
    variant_draft = apply_variant(base_draft, config, "variant")
    print_plan(config, base_draft)
    if dry_run:
        return {"success": True, "dryRun": True, "agentName": name}

    client = StudioClient(config)
    debug_runs: list[dict[str, Any]] = []
    deployed_runtime: dict[str, str] | None = None
    delete_runtime_on_failure = truthy(deep_get(config, "cleanup.delete_runtime_on_failure"))
    try:
        verify_studio_ready(client, log, config)

        log.step(
            "Click Agents -> Add Agent -> Quick Create -> Custom and fill options",
            "client-side draft assembly; next backend assertion uses the same AgentDraft shape",
        )
        log.ok("custom AgentDraft assembled with configured baseline options")

        log.step(
            "Click Start Debug and add comparison group",
            "client-side variant assembly; next backend calls start isolated debug runtimes",
        )
        log.ok("baseline and comparison variant prepared")

        debug_user = str(deep_get(config, "debug.user_id", "test_user") or "test_user")
        baseline_runtime = create_debug_run(
            client, log, "baseline", baseline_draft, debug_user
        )
        debug_runs.append(baseline_runtime)
        variant_runtime = create_debug_run(
            client, log, "variant", variant_draft, debug_user
        )
        debug_runs.append(variant_runtime)

        debug_message = str(deep_get(config, "debug.message", "Hello") or "Hello")
        expected_baseline = str(deep_get(config, "debug.expected_contains.baseline", "") or "")
        expected_variant = str(deep_get(config, "debug.expected_contains.variant", "") or "")
        verify_trace = truthy(deep_get(config, "debug.verify_trace"), default=True)
        debug_results = [
            run_debug_message(
                client,
                log,
                baseline_runtime,
                debug_user,
                debug_message,
                expected_baseline,
                verify_trace,
            ),
            run_debug_message(
                client,
                log,
                variant_runtime,
                debug_user,
                debug_message,
                expected_variant,
                verify_trace,
            ),
        ]

        winner = str(deep_get(config, "deploy.winner", "variant") or "variant")
        winner_draft = variant_draft if winner == "variant" else baseline_draft
        project = generate_project_for_winner(client, log, winner, winner_draft)
        final = deploy_project(client, log, config, project)
        deployed_runtime = {
            "runtimeId": str(final["runtimeId"]),
            "region": str(final.get("region") or config_region(config)),
        }
        deployed = connect_deployed_agent(
            client,
            log,
            config,
            final,
            preferred_app=str(project.get("name") or final.get("agentName") or ""),
        )
        chat = chat_with_deployed_agent(client, log, config, deployed)

        if truthy(deep_get(config, "cleanup.delete_debug_runs"), default=True):
            delete_debug_runs(client, log, debug_runs)
            debug_runs = []
        if truthy(deep_get(config, "cleanup.delete_runtime_on_success")):
            delete_runtime(
                client,
                log,
                deployed_runtime["runtimeId"],
                deployed_runtime["region"],
                verify=truthy(deep_get(config, "cleanup.verify_runtime_deleted"), default=True),
            )

        return {
            "success": True,
            "agentName": name,
            "winner": winner,
            "debug": debug_results,
            "deployment": {
                "runtimeId": deployed_runtime["runtimeId"],
                "region": deployed_runtime["region"],
                "app": deployed["app"],
                "agentName": final.get("agentName"),
            },
            "chat": chat,
        }
    except Exception:
        if deployed_runtime and delete_runtime_on_failure:
            try:
                delete_runtime(
                    client,
                    log,
                    deployed_runtime["runtimeId"],
                    deployed_runtime["region"],
                    verify=truthy(deep_get(config, "cleanup.verify_runtime_deleted"), default=True),
                )
            except Exception as cleanup_error:
                print(f"Runtime cleanup after failure failed: {cleanup_error}", file=sys.stderr)
        raise
    finally:
        if debug_runs and truthy(deep_get(config, "cleanup.delete_debug_runs"), default=True):
            try:
                delete_debug_runs(client, log, debug_runs)
            except Exception as cleanup_error:
                print(f"Debug cleanup failed: {cleanup_error}", file=sys.stderr)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to workflow config YAML.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and print planned workflow without API calls.",
    )
    args = parser.parse_args(argv)

    config = load_config(Path(args.config).expanduser().resolve())
    result = run_workflow(config, dry_run=args.dry_run)
    print("\n=== Summary ===")
    print_json("result", result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SmokeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
