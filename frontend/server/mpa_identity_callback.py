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

"""Server-side OAuth callback relay for AgentKit MPA runtimes."""

from __future__ import annotations

import base64
import ipaddress
import json
import logging
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

logger = logging.getLogger(__name__)

MPA_CALLBACK_PATH = "/oauth/callback"
MPA_RUNTIME_CALLBACK_PATH = "/identity/oauth/callback"
MAX_STATE_LENGTH = 16 * 1024
MAX_CALLBACK_RESPONSE_BYTES = 64 * 1024
CALLBACK_TIMEOUT_SECONDS = 10.0

_SECURITY_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"
    ),
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


@dataclass(frozen=True)
class MpaCallbackTarget:
    instance_id: str


@dataclass(frozen=True)
class IdentityRelayState:
    request_id: str
    provider_id: str
    target: MpaCallbackTarget


@dataclass(frozen=True)
class MpaRuntimeCredentials:
    endpoint_origin: str
    api_key: str


@dataclass(frozen=True)
class RuntimeCallbackResult:
    http_status: int
    payload: dict[str, Any]


HostedCallbackResolver = Callable[[str], Awaitable[str]]
RuntimeCredentialsResolver = Callable[
    [MpaCallbackTarget], Awaitable[MpaRuntimeCredentials]
]


class MpaIdentityCallbackError(ValueError):
    """A sanitized callback error that is safe to expose through logs."""


def select_mpa_runtime(
    candidates: Iterable[tuple[str, Any]],
    target: MpaCallbackTarget,
) -> tuple[str, Any]:
    """Select exactly one Runtime by trusted control-plane environment metadata."""
    matches: list[tuple[str, Any]] = []
    for region, runtime in candidates:
        envs = {
            str(getattr(item, "key", "") or ""): str(getattr(item, "value", "") or "")
            for item in (getattr(runtime, "envs", None) or [])
        }
        if envs.get("MPA_AGENT_ID", "").strip() == target.instance_id:
            matches.append((region, runtime))
    if len(matches) != 1:
        reason = "not found" if not matches else "not unique"
        raise MpaIdentityCallbackError(f"MPA Runtime {reason}")
    return matches[0]


def _decode_base64url_json(value: str) -> dict[str, Any] | None:
    if not value or len(value) > MAX_STATE_LENGTH:
        return None
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(f"{value}{padding}")
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def parse_identity_relay_state(value: str) -> IdentityRelayState | None:
    """Decode the outer UserPool relay state and its strict MPA target."""
    outer = _decode_base64url_json(value.strip())
    if outer is None:
        return None
    request_id = outer.get("request_id")
    provider_id = outer.get("provider_id")
    request_state = outer.get("request_state")
    if (
        not isinstance(request_id, str)
        or not request_id.strip()
        or not isinstance(provider_id, str)
        or not provider_id.strip()
        or not isinstance(request_state, str)
        or not request_state.strip()
    ):
        return None

    target = parse_mpa_runtime_state(request_state)
    if target is None:
        return None
    return IdentityRelayState(
        request_id=request_id.strip(),
        provider_id=provider_id.strip(),
        target=target,
    )


def parse_mpa_runtime_state(value: str) -> MpaCallbackTarget | None:
    """Decode the UserPool-issued callback state and its strict MPA target."""
    payload = _decode_base64url_json(value.strip())
    if payload is None:
        return None
    target = payload.get("target")
    if (
        not isinstance(target, str)
        or not target.startswith("mi-")
        or len(target) <= len("mi-")
    ):
        return None
    return MpaCallbackTarget(target.strip())


def _normalize_https_origin(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        hostname = (parsed.hostname or "").rstrip(".").lower()
        port = parsed.port
    except ValueError:
        raise ValueError("invalid HTTPS origin") from None
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        is_ip = False
    else:
        is_ip = True
    if (
        parsed.scheme != "https"
        or not hostname
        or is_ip
        or parsed.username
        or parsed.password
        or port
        or len(hostname) > 253
        or any(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) is None
            for label in hostname.split(".")
        )
        or "." not in hostname
    ):
        raise ValueError("invalid HTTPS origin")
    return urlunsplit(("https", hostname, "", "", ""))


def _normalize_runtime_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    origin = _normalize_https_origin(value)
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise MpaIdentityCallbackError("invalid Runtime endpoint")
    return origin


def build_user_pool_hosted_callback_url(
    issuer: str,
    connection_type: str,
) -> str:
    """Build the trusted UserPool relay endpoint from discovered pool metadata."""
    origin = _normalize_https_origin(issuer)
    callback_kind = {
        "oauth": "generic_oauth",
        "oidc": "generic_oidc",
    }.get(connection_type.strip().lower())
    if callback_kind is None:
        raise ValueError("unsupported identity provider connection type")
    return f"{origin}/login/{callback_kind}/callback"


def _validate_hosted_callback_url(value: str) -> str:
    parsed = urlsplit(value)
    origin = _normalize_https_origin(value)
    if (
        parsed.path
        not in {
            "/login/generic_oauth/callback",
            "/login/generic_oidc/callback",
        }
        or parsed.query
        or parsed.fragment
    ):
        raise MpaIdentityCallbackError("invalid UserPool callback endpoint")
    return f"{origin}{parsed.path}"


def _user_pool_redirect_response(
    hosted_callback_url: str,
    code: str,
    state: str,
) -> RedirectResponse:
    callback_url = _validate_hosted_callback_url(hosted_callback_url)
    return RedirectResponse(
        f"{callback_url}?{urlencode({'code': code, 'state': state})}",
        status_code=302,
        headers=_SECURITY_HEADERS,
    )


def _parse_runtime_payload(response: httpx.Response) -> dict[str, Any]:
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_CALLBACK_RESPONSE_BYTES:
                raise MpaIdentityCallbackError("Runtime callback response is too large")
        except ValueError:
            pass
    if len(response.content) > MAX_CALLBACK_RESPONSE_BYTES:
        raise MpaIdentityCallbackError("Runtime callback response is too large")
    try:
        payload = response.json()
    except ValueError as error:
        raise MpaIdentityCallbackError(
            "Runtime returned invalid callback JSON"
        ) from error
    code = payload.get("code") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or not isinstance(code, int)
        or isinstance(code, bool)
        or "message" not in payload
        or "error" not in payload
    ):
        raise MpaIdentityCallbackError("Runtime returned invalid callback payload")
    return payload


async def _call_runtime_callback(
    client: httpx.AsyncClient,
    credentials: MpaRuntimeCredentials,
    code: str,
    state: str,
) -> RuntimeCallbackResult:
    origin = _normalize_runtime_endpoint(credentials.endpoint_origin)
    api_key = credentials.api_key.strip()
    if not api_key:
        raise MpaIdentityCallbackError("Runtime key authentication is unavailable")
    response = await client.get(
        f"{origin}{MPA_RUNTIME_CALLBACK_PATH}",
        params={"code": code, "state": state},
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        follow_redirects=False,
    )
    if 300 <= response.status_code < 400:
        raise MpaIdentityCallbackError("Runtime callback redirected unexpectedly")
    return RuntimeCallbackResult(response.status_code, _parse_runtime_payload(response))


def _result_page(title: str, heading: str, description: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      body {{ margin: 0; color: #1d2129; font-family: Arial, "PingFang SC", sans-serif; }}
      main {{ box-sizing: border-box; min-height: 100vh; padding: 18vh 24px; text-align: center; }}
      h1 {{ margin: 0; font-size: 36px; line-height: 1.35; }}
      p {{ margin: 20px 0 0; font-size: 18px; line-height: 1.5; }}
    </style>
  </head>
  <body><main><h1>{heading}</h1><p>{description}</p></main></body>
</html>"""


def _invalid_request() -> JSONResponse:
    return JSONResponse(
        {"code": 4002, "message": "", "error": "Invalid callback request"},
        status_code=400,
        headers=_SECURITY_HEADERS,
    )


def _internal_error() -> JSONResponse:
    return JSONResponse(
        {"code": 5000, "message": "", "error": "MPA authorization failed"},
        status_code=502,
        headers=_SECURITY_HEADERS,
    )


def _runtime_result_response(result: RuntimeCallbackResult) -> Response:
    code = result.payload["code"]
    if code == 0:
        return HTMLResponse(
            _result_page("授权成功", "授权成功", "您可以关闭本页面并返回会话。"),
            status_code=200,
            headers=_SECURITY_HEADERS,
        )
    if code == 4003:
        return HTMLResponse(
            _result_page(
                "授权链接已失效",
                "授权链接已失效",
                "请返回会话重新触发授权。",
            ),
            status_code=result.http_status,
            headers=_SECURITY_HEADERS,
        )
    return JSONResponse(
        result.payload,
        status_code=result.http_status,
        headers=_SECURITY_HEADERS,
    )


def mount_mpa_identity_callback(
    app: FastAPI,
    *,
    hosted_callback_resolver: HostedCallbackResolver,
    runtime_credentials_resolver: RuntimeCredentialsResolver,
    http_client: httpx.AsyncClient | None = None,
) -> None:
    """Mount the public browser callback for MPA Runtime authorization."""

    @app.get(MPA_CALLBACK_PATH)
    async def mpa_identity_callback(
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> Response:
        if error or not code or not state:
            return _invalid_request()
        relay_state = parse_identity_relay_state(state)
        if relay_state is not None:
            stage = "resolve_userpool_callback"
            try:
                hosted_callback_url = await hosted_callback_resolver(
                    relay_state.provider_id
                )
                return _user_pool_redirect_response(hosted_callback_url, code, state)
            except Exception as callback_error:  # noqa: BLE001 - sanitize route boundary
                safe_error = (
                    str(callback_error)
                    if isinstance(callback_error, MpaIdentityCallbackError)
                    else type(callback_error).__name__
                )
                logger.warning(
                    "MPA identity callback failed stage=%s error=%s "
                    "error_type=%s request_id=%s target=%s",
                    stage,
                    safe_error,
                    type(callback_error).__name__,
                    relay_state.request_id,
                    relay_state.target.instance_id,
                )
                return _internal_error()

        target = parse_mpa_runtime_state(state)
        if target is None:
            return _invalid_request()

        owned_client = http_client is None
        client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(CALLBACK_TIMEOUT_SECONDS),
            follow_redirects=False,
        )
        stage = "resolve_runtime"
        try:
            credentials = await runtime_credentials_resolver(target)
            stage = "runtime_callback"
            result = await _call_runtime_callback(
                client,
                credentials,
                code,
                state,
            )
            response = _runtime_result_response(result)
        except Exception as callback_error:  # noqa: BLE001 - sanitize route boundary
            safe_error = (
                str(callback_error)
                if isinstance(callback_error, MpaIdentityCallbackError)
                else type(callback_error).__name__
            )
            logger.warning(
                "MPA identity callback failed stage=%s error=%s "
                "error_type=%s target=%s",
                stage,
                safe_error,
                type(callback_error).__name__,
                target.instance_id,
            )
            response = _internal_error()
        finally:
            if owned_client:
                await client.aclose()

        return response
