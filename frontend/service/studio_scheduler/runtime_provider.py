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

"""AgentKit control-plane resolution and cancellable Runtime SSE invocation."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from .diagnostics import sanitize_diagnostic
from .models import (
    ExecutionRequest,
    ExecutionResult,
    ProviderName,
    RuntimeInvocationError,
    RuntimeTarget,
)
from .ports import CancellationControl

_IAM_CREDENTIAL_PATH = Path("/var/run/secrets/iam/credential")


@dataclass(frozen=True)
class ServiceCredentials:
    access_key: str
    secret_key: str
    session_token: str = ""


@dataclass(frozen=True)
class RuntimeConnection:
    endpoint: str
    api_key: str
    runtime_version: str


class RuntimeConnectionResolver(Protocol):
    async def resolve(self, target: RuntimeTarget) -> RuntimeConnection: ...


def resolve_service_credentials(provider: ProviderName) -> ServiceCredentials:
    """Resolve provider-specific service credentials, falling back to VeFaaS IAM."""
    if provider == "byteplus":
        access_key = os.getenv("BYTEPLUS_ACCESS_KEY", "").strip()
        secret_key = os.getenv("BYTEPLUS_SECRET_KEY", "").strip()
        session_token = os.getenv("BYTEPLUS_SESSION_TOKEN", "").strip()
    else:
        access_key = os.getenv("VOLCENGINE_ACCESS_KEY", "").strip()
        secret_key = os.getenv("VOLCENGINE_SECRET_KEY", "").strip()
        session_token = os.getenv("VOLCENGINE_SESSION_TOKEN", "").strip()
    if bool(access_key) != bool(secret_key):
        raise ValueError(
            f"{provider} access key and secret key must be configured together"
        )
    if access_key:
        return ServiceCredentials(access_key, secret_key, session_token)
    if not _IAM_CREDENTIAL_PATH.is_file():
        raise FileNotFoundError("VeFaaS service identity is unavailable")
    payload = json.loads(_IAM_CREDENTIAL_PATH.read_text(encoding="utf-8"))
    access_key = payload.get("access_key_id") or payload.get("AccessKeyId")
    secret_key = payload.get("secret_access_key") or payload.get("SecretAccessKey")
    session_token = payload.get("session_token") or payload.get("SessionToken") or ""
    if not access_key or not secret_key:
        raise ValueError("VeFaaS service identity credential is incomplete")
    return ServiceCredentials(
        access_key=str(access_key),
        secret_key=str(secret_key),
        session_token=str(session_token),
    )


class AgentKitRuntimeConnectionResolver:
    """Read a Runtime endpoint, key, and current version with service identity."""

    def __init__(
        self,
        *,
        credentials_resolver: Callable[[ProviderName], ServiceCredentials]
        | None = None,
        runtime_loader: Callable[[RuntimeTarget, ServiceCredentials], Any]
        | None = None,
    ) -> None:
        self._credentials_resolver = credentials_resolver or resolve_service_credentials
        self._runtime_loader = runtime_loader or _load_runtime

    async def resolve(self, target: RuntimeTarget) -> RuntimeConnection:
        credentials: ServiceCredentials | None = None
        try:
            credentials = self._credentials_resolver(target.provider)
            runtime = await asyncio.to_thread(
                self._runtime_loader,
                target,
                credentials,
            )
            return _connection_from_runtime(runtime)
        except RuntimeInvocationError:
            raise
        except Exception as error:
            detail = sanitize_diagnostic(
                error,
                secrets=(
                    credentials.access_key if credentials else "",
                    credentials.secret_key if credentials else "",
                    credentials.session_token if credentials else "",
                ),
            )
            raise RuntimeInvocationError(
                "Unable to resolve Runtime service connection"
                + (f". Detail: {detail}" if detail else "")
                + ". Check the Runtime ID, region, and scheduler service identity.",
                acknowledged=False,
                retryable=False,
            ) from error


def _load_runtime(target: RuntimeTarget, credentials: ServiceCredentials) -> Any:
    from agentkit.sdk.runtime import types
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    client = AgentkitRuntimeClient(
        access_key=credentials.access_key,
        secret_key=credentials.secret_key,
        session_token=credentials.session_token,
        region=target.region,
    )
    return client.get_runtime(types.GetRuntimeRequest(RuntimeId=target.runtime_id))


def _connection_from_runtime(runtime: Any) -> RuntimeConnection:
    endpoint = ""
    fallback = ""
    for network in getattr(runtime, "network_configurations", None) or ():
        candidate = str(getattr(network, "endpoint", "") or "").rstrip("/")
        if not candidate:
            continue
        fallback = fallback or candidate
        if str(getattr(network, "network_type", "") or "") == "public":
            endpoint = candidate
            break
    endpoint = endpoint or fallback or str(getattr(runtime, "endpoint", "") or "")
    authorizer = getattr(runtime, "authorizer_configuration", None)
    key_auth = getattr(authorizer, "key_auth", None) if authorizer else None
    api_key = str(getattr(key_auth, "api_key", "") or "")
    if not endpoint:
        raise RuntimeInvocationError(
            "Runtime has no reachable endpoint",
            acknowledged=False,
            retryable=False,
        )
    if not api_key:
        raise RuntimeInvocationError(
            "Runtime does not expose service key authentication",
            acknowledged=False,
            retryable=False,
        )
    version = str(getattr(runtime, "current_version_number", "") or "")
    return RuntimeConnection(endpoint.rstrip("/"), api_key, version)


class AgentKitRuntimeProvider:
    """Invoke one Runtime through its ADK HTTP API with cancellation polling."""

    def __init__(
        self,
        provider: ProviderName,
        resolver: RuntimeConnectionResolver,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        cancel_poll_seconds: float = 1.0,
    ) -> None:
        if cancel_poll_seconds <= 0:
            raise ValueError("cancel_poll_seconds must be positive")
        self.provider: ProviderName = provider
        self._resolver = resolver
        self._transport = transport
        self._cancel_poll_seconds = cancel_poll_seconds

    async def execute(
        self,
        request: ExecutionRequest,
        control: CancellationControl,
    ) -> ExecutionResult:
        connection = await self._resolver.resolve(request.runtime)
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {connection.api_key}",
        }
        timeout = httpx.Timeout(float(request.timeout_seconds), connect=10.0)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                transport=self._transport,
            ) as client:
                session_id = await self._create_session(
                    client,
                    connection,
                    request,
                    headers,
                )
                output = await self._run_sse(
                    client,
                    connection,
                    request,
                    session_id,
                    headers,
                    control,
                )
        except RuntimeInvocationError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:
            raise RuntimeInvocationError(
                "Runtime connection failed before acknowledgement",
                acknowledged=False,
                retryable=True,
            ) from error
        except httpx.HTTPError as error:
            raise RuntimeInvocationError(
                "Runtime stream failed after request delivery",
                acknowledged=True,
                retryable=False,
            ) from error
        return ExecutionResult(
            output=output,
            runtime_version=connection.runtime_version,
            session_id=session_id,
        )

    async def _create_session(
        self,
        client: httpx.AsyncClient,
        connection: RuntimeConnection,
        request: ExecutionRequest,
        headers: dict[str, str],
    ) -> str:
        app = quote(request.runtime.agent_name, safe="")
        user = quote(request.user_id, safe="")
        response = await client.post(
            f"{connection.endpoint}/apps/{app}/users/{user}/sessions",
            headers={**headers, "Content-Type": "application/json"},
            json={"id": request.session_id},
        )
        _raise_for_runtime_status(
            response,
            phase="create session",
            acknowledged=False,
            secrets=(connection.api_key,),
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise RuntimeInvocationError(
                "Runtime returned an invalid session response",
                acknowledged=False,
                retryable=False,
            ) from error
        if not isinstance(payload, dict) or not str(payload.get("id") or ""):
            raise RuntimeInvocationError(
                "Runtime returned an invalid session identity",
                acknowledged=False,
                retryable=False,
            )
        return str(payload["id"])

    async def _run_sse(
        self,
        client: httpx.AsyncClient,
        connection: RuntimeConnection,
        request: ExecutionRequest,
        session_id: str,
        headers: dict[str, str],
        control: CancellationControl,
    ) -> str:
        payload = {
            "app_name": request.runtime.agent_name,
            "user_id": request.user_id,
            "session_id": session_id,
            "new_message": {
                "role": "user",
                "parts": [{"text": request.prompt}],
            },
            "streaming": True,
        }
        async with client.stream(
            "POST",
            f"{connection.endpoint}/run_sse",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        ) as response:
            if response.status_code >= 400:
                await response.aread()
            _raise_for_runtime_status(
                response,
                phase="run",
                acknowledged=False,
                secrets=(connection.api_key,),
            )
            return await self._read_sse(
                response,
                control,
                secrets=(connection.api_key,),
            )

    async def _read_sse(
        self,
        response: httpx.Response,
        control: CancellationControl,
        *,
        secrets: tuple[str, ...] = (),
    ) -> str:
        lines = response.aiter_lines()
        pending: asyncio.Future[str] | None = None
        final_text = ""
        try:
            while True:
                if await control.is_cancel_requested():
                    await response.aclose()
                    raise RuntimeInvocationError(
                        "Runtime execution was cancelled",
                        acknowledged=True,
                        retryable=False,
                    )
                pending = pending or asyncio.ensure_future(anext(lines))
                done, _ = await asyncio.wait(
                    {pending},
                    timeout=self._cancel_poll_seconds,
                )
                if not done:
                    continue
                try:
                    line = pending.result()
                except StopAsyncIteration:
                    break
                finally:
                    pending = None
                event = _parse_sse_line(line)
                if event is None:
                    continue
                error = _event_error(event)
                if error:
                    raise RuntimeInvocationError(
                        "Runtime stream reported an error. Detail: "
                        f"{sanitize_diagnostic(error, secrets=secrets)}. "
                        "Check the Runtime logs, Agent configuration, and model access.",
                        acknowledged=True,
                        retryable=False,
                    )
                text = _event_text(event)
                if text and not bool(event.get("partial")):
                    final_text = text
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
        return final_text


def _raise_for_runtime_status(
    response: httpx.Response,
    *,
    phase: str,
    acknowledged: bool,
    secrets: tuple[str, ...] = (),
) -> None:
    if response.status_code < 400:
        return
    status_code = response.status_code
    retryable = status_code in {502, 503, 504}
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    detail = _runtime_response_detail(response, secrets=secrets)
    if retryable:
        recovery = (
            "The scheduler will retry automatically because the Runtime has not "
            "acknowledged the request."
        )
    elif status_code in {401, 403}:
        recovery = "Check the Runtime service key and scheduler service identity."
    elif status_code == 404:
        recovery = "Check the Runtime Agent name, endpoint, and deployed version."
    else:
        recovery = "Check the Runtime logs, Agent configuration, and model access, then retry this run."
    parts = [f"Runtime {phase} returned HTTP {status_code}."]
    if detail:
        parts.append(f"Detail: {detail}.")
    if content_type and content_type != "application/json":
        parts.append(f"Content-Type: {content_type}.")
    parts.append(recovery)
    raise RuntimeInvocationError(
        " ".join(parts),
        acknowledged=acknowledged,
        retryable=retryable,
    )


def _runtime_response_detail(
    response: httpx.Response,
    *,
    secrets: tuple[str, ...],
) -> str:
    content_type = response.headers.get("content-type", "").lower()
    detail: object = ""
    if "json" in content_type:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            detail = (
                payload.get("detail")
                or payload.get("error")
                or payload.get("message")
                or payload
            )
        elif payload is not None:
            detail = payload
    if not detail:
        detail = response.text
    if isinstance(detail, (dict, list)):
        detail = json.dumps(detail, ensure_ascii=False, separators=(",", ":"))
    return sanitize_diagnostic(detail, secrets=secrets)


def _parse_sse_line(line: str) -> dict[str, Any] | None:
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data or data == "[DONE]":
        return None
    try:
        value = json.loads(data)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _event_error(event: dict[str, Any]) -> str:
    return str(
        event.get("error")
        or event.get("errorMessage")
        or event.get("error_message")
        or ""
    )


def _event_text(event: dict[str, Any]) -> str:
    content = event.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    return "".join(
        str(part.get("text") or "")
        for part in parts
        if isinstance(part, dict) and part.get("text") is not None
    )
