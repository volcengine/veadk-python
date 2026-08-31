# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Studio BFF helpers for resolving and streaming Runtime instance logs."""

from __future__ import annotations

import asyncio
import base64
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from time import time
from typing import Any
from urllib.parse import quote_plus, unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

STUDIO_INSTANCE_HEADER = "X-Studio-FaaS-Instance"
STUDIO_REQUEST_ID_HEADER = "X-Studio-FaaS-Request-Id"
_INSTANCE_KEYS = {
    "x-faas-instance-name",
    "x_faas_instance_name",
    "instance-name",
    "instance_name",
}
_INSTANCE_VALUE_RE = re.compile(
    r"(?:x-faas-instance-name|x_faas_instance_name|instance-name|instance_name)"
    r"[\s\"']*[:=][\s\"']*([A-Za-z0-9][A-Za-z0-9._:-]{0,255})",
    re.IGNORECASE,
)
_VALID_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


@dataclass(frozen=True, slots=True)
class RuntimeRequestContext:
    instance_name: str
    request_id: str = ""


def _header(headers: Mapping[str, str], name: str) -> str:
    direct = headers.get(name)
    if direct is not None:
        return str(direct).strip()
    normalized = name.lower()
    for key, value in headers.items():
        if str(key).lower() == normalized:
            return str(value).strip()
    return ""


def _instance_from_value(value: Any) -> str:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _INSTANCE_KEYS:
                candidate = str(item or "").strip()
                if _VALID_IDENTIFIER_RE.fullmatch(candidate):
                    return candidate
            nested = _instance_from_value(item)
            if nested:
                return nested
    elif isinstance(value, list):
        for item in value:
            nested = _instance_from_value(item)
            if nested:
                return nested
    return ""


def _decoded_session_candidates(value: str) -> list[str]:
    candidates = [value, unquote(value)]
    for part in value.split("."):
        if not part:
            continue
        try:
            padding = "=" * (-len(part) % 4)
            decoded = base64.urlsafe_b64decode(part + padding).decode(
                "utf-8", errors="strict"
            )
        except (ValueError, UnicodeDecodeError):
            continue
        candidates.append(decoded)
    return candidates


def runtime_request_context(
    headers: Mapping[str, str],
) -> RuntimeRequestContext | None:
    """Extract safe routing metadata from trusted Runtime response headers."""

    instance_name = _header(headers, "x-faas-instance-name")
    if not _VALID_IDENTIFIER_RE.fullmatch(instance_name):
        instance_name = ""
    if not instance_name:
        session_header = _header(headers, "x-session-id")
        for candidate in _decoded_session_candidates(session_header):
            try:
                payload = json.loads(candidate)
            except (TypeError, ValueError):
                payload = None
            instance_name = _instance_from_value(payload)
            if not instance_name:
                match = _INSTANCE_VALUE_RE.search(candidate)
                instance_name = match.group(1) if match else ""
            if instance_name:
                break
    if not instance_name:
        return None
    request_id = _header(headers, "x-faas-request-id")
    return RuntimeRequestContext(
        instance_name=instance_name,
        request_id=request_id[:256],
    )


def studio_runtime_context_headers(
    context: RuntimeRequestContext | None,
) -> dict[str, str]:
    """Build the only Runtime routing headers that may reach the browser."""

    if context is None:
        return {}
    headers = {
        STUDIO_INSTANCE_HEADER: context.instance_name,
        "Cache-Control": "no-store",
    }
    if context.request_id:
        headers[STUDIO_REQUEST_ID_HEADER] = context.request_id
    return headers


def console_runtime_url(
    *,
    provider: str,
    region: str,
    project_name: str,
    runtime_id: str,
    instance_name: str,
) -> str:
    origin = (
        "https://console.byteplus.com"
        if provider == "byteplus"
        else "https://console.volcengine.com"
    )
    query = "&".join(
        (
            f"projectName={quote_plus(project_name or 'default')}",
            f"runtimeId={quote_plus(runtime_id)}",
            f"instanceName={quote_plus(instance_name)}",
        )
    )
    return f"{origin}/agentkit/region:agentkit+{quote_plus(region)}/runtime?{query}"


class RuntimeLogService:
    """Read one authorized Runtime instance's bounded log tail via AgentKit."""

    def __init__(
        self,
        *,
        provider: str,
        resolve_credentials: Callable[[], tuple[str, str, str | None]],
        create_client: Callable[..., Any] | None = None,
        sanitize: Callable[[str], str] | None = None,
    ) -> None:
        self.provider = provider
        self._resolve_credentials = resolve_credentials
        self._create_client = create_client
        self._sanitize = sanitize or (lambda value: value)

    def client(self, region: str) -> Any:
        access_key, secret_key, session_token = self._resolve_credentials()
        if self._create_client is not None:
            return self._create_client(
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token or "",
                region=region,
            )
        from agentkit.sdk.runtime.client import AgentkitRuntimeClient

        return AgentkitRuntimeClient(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token or "",
            region=region,
        )

    async def list_instances(
        self,
        client: Any,
        *,
        runtime_id: str,
    ) -> list[Any]:
        from agentkit.sdk.runtime import types as runtime_types

        response = await asyncio.to_thread(
            client.list_runtime_instances,
            runtime_types.ListRuntimeInstancesRequest(RuntimeId=runtime_id),
        )
        return list(response.instance_items or [])

    async def resolve_instance(
        self,
        client: Any,
        *,
        runtime_id: str,
        instance_name: str = "",
        session_id: str = "",
    ) -> str:
        instances = await self.list_instances(client, runtime_id=runtime_id)
        valid_instances = [
            str(getattr(item, "instance_name", "") or "")
            for item in instances
            if str(getattr(item, "runtime_id", runtime_id) or runtime_id) == runtime_id
        ]
        if instance_name:
            if instance_name not in valid_instances:
                raise ValueError("instance_not_found")
            return instance_name
        if len(valid_instances) == 1:
            return valid_instances[0]
        if session_id and valid_instances:
            matches: list[tuple[int, str]] = []
            for candidate in valid_instances:
                logs = await self.read_logs(
                    client,
                    runtime_id=runtime_id,
                    instance_name=candidate,
                )
                match_position = logs.rfind(session_id)
                if match_position >= 0:
                    matches.append((match_position, candidate))
            if matches:
                return max(matches)[1]
        raise ValueError("instance_not_resolved")

    async def validate_instance(
        self,
        client: Any,
        *,
        runtime_id: str,
        instance_name: str,
    ) -> None:
        instances = await self.list_instances(client, runtime_id=runtime_id)
        if not any(
            str(getattr(item, "instance_name", "") or "") == instance_name
            and str(getattr(item, "runtime_id", runtime_id) or runtime_id) == runtime_id
            for item in instances
        ):
            raise ValueError("instance_not_found")

    async def read_logs(
        self,
        client: Any,
        *,
        runtime_id: str,
        instance_name: str,
    ) -> str:
        from agentkit.sdk.runtime import types as runtime_types

        response = await asyncio.to_thread(
            client.get_runtime_instance_logs,
            runtime_types.GetRuntimeInstanceLogsRequest(
                RuntimeId=runtime_id,
                InstanceName=instance_name,
                Limit=500,
            ),
        )
        return self._sanitize(str(response.logs or ""))

    async def snapshot(
        self,
        *,
        runtime_id: str,
        instance_name: str,
        region: str,
    ) -> str:
        client = self.client(region)
        await self.validate_instance(
            client,
            runtime_id=runtime_id,
            instance_name=instance_name,
        )
        return await self.read_logs(
            client,
            runtime_id=runtime_id,
            instance_name=instance_name,
        )


def _sse(payload: Mapping[str, Any]) -> bytes:
    return (
        "data: "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "\n\n"
    ).encode("utf-8")


def mount_runtime_log_routes(
    app: FastAPI,
    *,
    service: RuntimeLogService,
    authorize_runtime: Callable[[Request, str, str], Any],
    normalize_region: Callable[[str | None], str],
    safe_error: Callable[[BaseException], str],
) -> None:
    """Mount BFF-only log streaming without requiring a Runtime application API."""

    @app.get("/web/runtime-logs/{runtime_id}/stream")
    async def _stream_runtime_logs(
        runtime_id: str,
        request: Request,
        instance_name: str = "",
        session_id: str = "",
        region: str = "",
        follow: bool = True,
    ) -> StreamingResponse:
        instance_name = instance_name.strip()
        session_id = session_id.strip()[:256]
        if instance_name and not _VALID_IDENTIFIER_RE.fullmatch(instance_name):
            raise HTTPException(status_code=400, detail="invalid_instance_name")
        if session_id and not _VALID_IDENTIFIER_RE.fullmatch(session_id):
            raise HTTPException(status_code=400, detail="invalid_session_id")
        if not instance_name and not session_id:
            raise HTTPException(status_code=400, detail="missing_runtime_context")
        normalized_region = normalize_region(region)
        try:
            runtime = await asyncio.to_thread(
                authorize_runtime,
                request,
                runtime_id,
                normalized_region,
            )
            client = service.client(normalized_region)
            instance_name = await service.resolve_instance(
                client,
                runtime_id=runtime_id,
                instance_name=instance_name,
                session_id=session_id,
            )
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(
                status_code=502,
                detail=safe_error(error),
            ) from error

        project_name = str(getattr(runtime, "project_name", "") or "default")
        console_url = console_runtime_url(
            provider=service.provider,
            region=normalized_region,
            project_name=project_name,
            runtime_id=runtime_id,
            instance_name=instance_name,
        )

        async def _events():
            yield _sse(
                {
                    "type": "context",
                    "instanceName": instance_name,
                    "consoleUrl": console_url,
                }
            )
            previous: str | None = None
            while True:
                if await request.is_disconnected():
                    return
                try:
                    logs = await service.read_logs(
                        client,
                        runtime_id=runtime_id,
                        instance_name=instance_name,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as error:  # noqa: BLE001 - streaming boundary
                    yield _sse(
                        {
                            "type": "error",
                            "message": "日志连接暂时中断，正在重试。",
                            "detail": safe_error(error),
                        }
                    )
                else:
                    if logs != previous:
                        previous = logs
                        yield _sse(
                            {
                                "type": "logs",
                                "text": logs,
                                "updatedAt": int(time() * 1000),
                            }
                        )
                if not follow:
                    yield _sse({"type": "done"})
                    return
                await asyncio.sleep(1)

        return StreamingResponse(
            _events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )
