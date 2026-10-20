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

"""Same-origin Terminal and Browser proxies for Studio Sandbox Sessions."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import posixpath
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote, urlencode, urlsplit

import httpx
from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse

from veadk.cli.codex_app_server import sandbox_service_url

SandboxSurface = Literal["terminal", "browser"]

_MAX_PROXY_RESPONSE_BYTES = 16 * 1024 * 1024
_MAX_PROXY_MESSAGE_BYTES = 8 * 1024 * 1024
_PROXY_TIMEOUT_SECONDS = 30
SANDBOX_UPLOAD_MAX_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class SandboxProxyTarget:
    """Private data-plane target resolved from an opaque browser capability."""

    endpoint: str


def proxy_cookie_name(session_id: str) -> str:
    """Return a cookie name that is stable without embedding a Session ID."""
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:20]
    return f"veadk_sandbox_{digest}"


def proxy_prefix(session_id: str, surface: SandboxSurface) -> str:
    """Return the same-origin path prefix for one proxied surface."""
    return f"/web/sandbox/proxy/{quote(session_id, safe='')}/{surface}"


def browser_launch_url(
    session_id: str,
    *,
    endpoint: str = "",
    direct: bool = False,
) -> str:
    """Return the proxied or native browser UI URL exposed to Studio."""
    if direct:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("Sandbox Browser 返回了无效地址。")
        return sandbox_service_url(endpoint, "/browser-ui")
    return f"{proxy_prefix(session_id, 'browser')}/browser-ui"


def terminal_initial_command_url(session_id: str, command: str) -> str:
    """Return a proxied Terminal URL that creates a shell and runs one command."""
    initial_command = command.strip()
    if not initial_command:
        raise ValueError("Sandbox Terminal 初始化命令不能为空。")
    query = urlencode(
        {
            "command": initial_command,
            "font_size": "12",
        }
    )
    return f"{proxy_prefix(session_id, 'terminal')}/terminal?{query}"


async def terminal_launch_url(
    endpoint: str,
    session_id: str,
    *,
    direct: bool = False,
) -> tuple[str, str]:
    """Create a remote shell session and return its browser URL."""
    url = sandbox_service_url(endpoint, "/v1/shell/terminal-url")
    try:
        async with httpx.AsyncClient(
            timeout=_PROXY_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            response = await client.get(url, headers={"accept": "application/json"})
    except httpx.HTTPError as error:
        raise RuntimeError("无法连接 Sandbox Terminal 服务。") from error
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(f"Sandbox Terminal 服务返回 HTTP {response.status_code}。")
    try:
        value = response.json()
    except json.JSONDecodeError as error:
        raise RuntimeError("Sandbox Terminal 返回了无效响应。") from error
    if not isinstance(value, dict) or not isinstance(value.get("data"), str):
        raise TypeError("Sandbox Terminal 未返回有效地址。")
    parsed = urlsplit(value["data"])
    shell_session_id = ""
    from urllib.parse import parse_qs

    values = parse_qs(parsed.query)
    candidates = values.get("session_id")
    if candidates:
        shell_session_id = candidates[0].strip()
    if not shell_session_id or len(shell_session_id) > 1_000:
        raise RuntimeError("Sandbox Terminal 未返回 Shell Session ID。")
    if direct:
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RuntimeError("Sandbox Terminal 返回了无效地址。")
        return (
            sandbox_service_url(
                endpoint,
                "/terminal",
                query={"session_id": shell_session_id},
            ),
            shell_session_id,
        )
    local_url = (
        f"{proxy_prefix(session_id, 'terminal')}/terminal"
        f"?session_id={quote(shell_session_id, safe='')}"
    )
    return local_url, shell_session_id


async def upload_sandbox_file(
    endpoint: str,
    cwd: str,
    file_name: str,
    content_type: str,
    content: bytes,
) -> str:
    """Upload one bounded file into the active Sandbox workspace."""
    if len(content) > SANDBOX_UPLOAD_MAX_BYTES:
        raise ValueError("Sandbox 上传文件超过大小限制。")
    safe_name = _safe_upload_name(file_name)
    if not cwd.startswith("/"):
        raise ValueError("Sandbox 工作目录无效。")
    normalized_cwd = posixpath.normpath(cwd)
    if not normalized_cwd.startswith("/"):
        raise ValueError("Sandbox 工作目录无效。")
    path = posixpath.join(normalized_cwd, safe_name)
    try:
        async with httpx.AsyncClient(
            timeout=5 * 60,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                sandbox_service_url(endpoint, "/v1/file/upload"),
                data={"path": path},
                files={
                    "file": (
                        safe_name,
                        content,
                        content_type or "application/octet-stream",
                    )
                },
            )
    except httpx.HTTPError as error:
        raise RuntimeError("无法连接 Sandbox 文件服务。") from error
    try:
        value = response.json()
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Sandbox 文件服务返回无效响应（HTTP {response.status_code}）。"
        ) from error
    if (
        response.status_code < 200
        or response.status_code >= 300
        or (isinstance(value, dict) and value.get("success") is False)
    ):
        detail = (
            value.get("error")
            if isinstance(value, dict) and isinstance(value.get("error"), str)
            else f"HTTP {response.status_code}"
        )
        raise RuntimeError(f"Sandbox 文件上传失败：{detail}")
    return path


def _safe_upload_name(value: str) -> str:
    """Return a single, control-character-free remote file name."""
    if not isinstance(value, str):
        raise TypeError("Sandbox 上传文件名无效。")
    normalized = "".join(
        character
        for character in value.replace("/", "_").replace("\\", "_")
        if character >= " " and character != "\x7f"
    ).strip()[:255]
    return normalized if normalized and normalized not in {".", ".."} else "attachment"


def mount_sandbox_proxy_routes(
    app: Any,
    target_resolver: Callable[[str, str], SandboxProxyTarget],
) -> None:
    """Mount bounded HTTP and WebSocket proxies on the Studio application."""

    @app.api_route(
        "/web/sandbox/proxy/{session_id}/{surface}/{asset_path:path}",
        methods=["GET", "HEAD"],
    )
    async def _sandbox_proxy_http(
        session_id: str,
        surface: str,
        asset_path: str,
        request: Request,
    ) -> Response:
        target = _resolve_http_target(target_resolver, session_id, request)
        if isinstance(target, Response):
            return target
        if surface not in {"terminal", "browser"}:
            return _proxy_error(404, "Sandbox 工具不存在。")
        typed_surface: SandboxSurface = surface
        upstream_path = _upstream_http_path(typed_surface, asset_path)
        if upstream_path is None:
            return _proxy_error(404, "Sandbox 工具路径不存在。")
        return await _proxy_http_response(
            request,
            target,
            session_id,
            typed_surface,
            asset_path,
            upstream_path,
        )

    @app.websocket("/web/sandbox/proxy/{session_id}/terminal/v1/shell/ws")
    async def _sandbox_terminal_websocket(
        session_id: str, websocket: WebSocket
    ) -> None:
        target = await _resolve_websocket_target(target_resolver, session_id, websocket)
        if target is None:
            return
        shell_session_id = websocket.query_params.get("session_id", "").strip()
        if len(shell_session_id) > 1_000:
            await websocket.close(code=1008, reason="invalid shell session")
            return
        upstream = sandbox_service_url(
            target.endpoint,
            "/v1/shell/ws",
            websocket=True,
            query={"session_id": shell_session_id} if shell_session_id else None,
        )
        await _relay_websocket(websocket, upstream)

    @app.websocket(
        "/web/sandbox/proxy/{session_id}/browser/cdp/devtools/{target_kind}/{target_id}"
    )
    async def _sandbox_browser_websocket(
        session_id: str,
        target_kind: str,
        target_id: str,
        websocket: WebSocket,
    ) -> None:
        target = await _resolve_websocket_target(target_resolver, session_id, websocket)
        if target is None:
            return
        if target_kind not in {"browser", "page"} or not _safe_segment(target_id):
            await websocket.close(code=1008, reason="invalid CDP target")
            return
        upstream = sandbox_service_url(
            target.endpoint,
            f"/cdp/devtools/{target_kind}/{target_id}",
            websocket=True,
        )
        await _relay_websocket(websocket, upstream)


def _resolve_http_target(
    resolver: Callable[[str, str], SandboxProxyTarget],
    session_id: str,
    request: Request,
) -> SandboxProxyTarget | Response:
    token = request.cookies.get(proxy_cookie_name(session_id), "")
    try:
        return resolver(session_id, token)
    except PermissionError:
        return _proxy_error(403, "Sandbox 工具授权已失效。")
    except KeyError:
        return _proxy_error(404, "Sandbox Session 未连接。")


async def _resolve_websocket_target(
    resolver: Callable[[str, str], SandboxProxyTarget],
    session_id: str,
    websocket: WebSocket,
) -> SandboxProxyTarget | None:
    if not _trusted_websocket_origin(websocket):
        await websocket.close(code=1008, reason="untrusted origin")
        return None
    token = websocket.cookies.get(proxy_cookie_name(session_id), "")
    try:
        return resolver(session_id, token)
    except (KeyError, PermissionError):
        await websocket.close(code=1008, reason="invalid capability")
        return None


async def _proxy_http_response(
    request: Request,
    target: SandboxProxyTarget,
    session_id: str,
    surface: SandboxSurface,
    asset_path: str,
    upstream_path: str,
) -> Response:
    prefix = proxy_prefix(session_id, surface)
    headers = {
        name: request.headers[name]
        for name in ("accept", "accept-language", "user-agent")
        if name in request.headers
    }
    if surface == "browser":
        headers.update(
            {
                "x-forwarded-host": request.headers.get("host", "localhost"),
                "x-forwarded-proto": _public_protocol(request),
                "x-forwarded-prefix": prefix,
            }
        )
    client = httpx.AsyncClient(
        timeout=_PROXY_TIMEOUT_SECONDS,
        follow_redirects=False,
    )
    try:
        upstream = await client.send(
            client.build_request(
                request.method,
                sandbox_service_url(target.endpoint, upstream_path),
                headers=headers,
            ),
            stream=True,
        )
    except httpx.HTTPError:
        await client.aclose()
        return _proxy_error(502, "无法连接 Sandbox 工具服务。")
    if upstream.status_code < 200 or upstream.status_code >= 300:
        status = upstream.status_code
        await upstream.aclose()
        await client.aclose()
        return _proxy_error(502, f"Sandbox 工具服务返回 HTTP {status}。")

    content_type = upstream.headers.get("content-type", "application/octet-stream")
    common_headers = _proxy_headers(
        cache_static=asset_path.startswith("static/"),
        content_type=content_type,
    )
    if request.method == "HEAD":
        await upstream.aclose()
        await client.aclose()
        return Response(
            status_code=upstream.status_code,
            headers=common_headers,
        )
    if surface == "browser" and asset_path == "v1/browser/info":
        return await _browser_info_response(request, upstream, client, prefix)
    if content_type.lower().startswith("text/html"):
        font_size = (
            12
            if surface == "terminal" and request.query_params.get("font_size") == "12"
            else None
        )
        return await _html_response(
            upstream,
            client,
            common_headers,
            prefix,
            terminal_font_size=font_size,
        )

    async def _body() -> AsyncIterator[bytes]:
        size = 0
        try:
            async for chunk in upstream.aiter_bytes():
                size += len(chunk)
                if size > _MAX_PROXY_RESPONSE_BYTES:
                    return
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        _body(),
        status_code=upstream.status_code,
        headers=common_headers,
        media_type=None,
    )


async def _browser_info_response(
    request: Request,
    upstream: httpx.Response,
    client: httpx.AsyncClient,
    prefix: str,
) -> Response:
    try:
        content = await upstream.aread()
        if len(content) > 512 * 1024:
            return _proxy_error(502, "Sandbox Browser 信息响应过大。")
        value = json.loads(content)
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("data"), dict)
            or not isinstance(value["data"].get("cdp_url"), str)
        ):
            raise TypeError("missing data.cdp_url")
        data = dict(value["data"])
        upstream_cdp = urlsplit(data["cdp_url"])
        marker = "/cdp/devtools/"
        marker_index = upstream_cdp.path.rfind(marker)
        if marker_index < 0:
            raise ValueError("invalid CDP URL")
        host = request.headers.get("host")
        if not host:
            raise ValueError("missing Host")
        protocol = _public_protocol(request)
        ws_protocol = "wss" if protocol == "https" else "ws"
        cdp_path = upstream_cdp.path[marker_index:]
        data["cdp_url"] = f"{ws_protocol}://{host}{prefix}{cdp_path}"
        data["cdp_ui_url"] = f"{protocol}://{host}{prefix}/browser-ui"
        data.pop("vnc_url", None)
        value = {**value, "data": data}
        return JSONResponse(
            value,
            headers=_proxy_headers(
                cache_static=False,
                content_type="application/json; charset=utf-8",
            ),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return _proxy_error(502, "Sandbox Browser 返回了无效信息。")
    finally:
        await upstream.aclose()
        await client.aclose()


async def _html_response(
    upstream: httpx.Response,
    client: httpx.AsyncClient,
    headers: dict[str, str],
    prefix: str,
    *,
    terminal_font_size: int | None = None,
) -> Response:
    try:
        content = await upstream.aread()
        if len(content) > 2 * 1024 * 1024:
            return _proxy_error(502, "Sandbox 工具页面响应过大。")
        text = content.decode("utf-8")
        for root in (
            "/static/sandbox/",
            "/static/",
            "/v1/shell/ws",
            "/v1/browser/info",
        ):
            text = text.replace(f'"{root}', f'"{prefix}{root}')
            text = text.replace(f"'{root}", f"'{prefix}{root}")
        if terminal_font_size is not None:
            text = text.replace(
                "fontSize: 14,",
                f"fontSize: {terminal_font_size},",
                1,
            )
        return Response(
            text,
            status_code=upstream.status_code,
            headers=headers,
        )
    except UnicodeDecodeError:
        return _proxy_error(502, "Sandbox 工具页面编码无效。")
    finally:
        await upstream.aclose()
        await client.aclose()


async def _relay_websocket(websocket: WebSocket, upstream_url: str) -> None:
    import websockets

    try:
        upstream = await websockets.connect(
            upstream_url,
            open_timeout=_PROXY_TIMEOUT_SECONDS,
            close_timeout=5,
            max_size=_MAX_PROXY_MESSAGE_BYTES,
        )
    except Exception:  # noqa: BLE001 - WebSocket transport boundary
        await websocket.close(code=1011, reason="sandbox connection failed")
        return
    await websocket.accept()

    async def _browser_to_upstream() -> None:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            value = message.get("bytes")
            if value is None:
                value = message.get("text")
            if value is None:
                continue
            if len(value) > _MAX_PROXY_MESSAGE_BYTES:
                await websocket.close(code=1009)
                return
            await upstream.send(value)

    async def _upstream_to_browser() -> None:
        async for value in upstream:
            if isinstance(value, bytes):
                await websocket.send_bytes(value)
            else:
                await websocket.send_text(value)

    tasks = {
        asyncio.create_task(_browser_to_upstream()),
        asyncio.create_task(_upstream_to_browser()),
    }
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            with contextlib.suppress(
                WebSocketDisconnect, RuntimeError, ConnectionError
            ):
                task.result()
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    finally:
        await upstream.close()
        with contextlib.suppress(RuntimeError):
            await websocket.close()


def _upstream_http_path(surface: SandboxSurface, asset_path: str) -> str | None:
    if not _safe_path(asset_path):
        return None
    if surface == "terminal":
        if asset_path == "terminal":
            return "/terminal"
        if asset_path.startswith("static/sandbox/"):
            return f"/{asset_path}"
        return None
    if asset_path in {"browser-ui", "v1/browser/info"}:
        return f"/{asset_path}"
    if asset_path.startswith("static/"):
        return f"/{asset_path}"
    return None


def _safe_path(path: str) -> bool:
    return bool(path) and all(_safe_segment(value) for value in path.split("/"))


def _safe_segment(value: str) -> bool:
    return bool(value) and value not in {".", ".."} and "\0" not in value


def _trusted_websocket_origin(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    parsed = urlsplit(origin)
    return parsed.scheme in {
        "http",
        "https",
    } and parsed.netloc == websocket.headers.get("host")


def _public_protocol(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-proto", "")
    candidate = forwarded.split(",", 1)[0].strip().lower()
    if candidate in {"http", "https"}:
        return candidate
    return "https" if request.url.scheme == "https" else "http"


def _proxy_headers(*, cache_static: bool, content_type: str) -> dict[str, str]:
    return {
        "cache-control": ("private, max-age=3600" if cache_static else "no-store"),
        "content-type": content_type,
        "cross-origin-resource-policy": "same-origin",
        "referrer-policy": "no-referrer",
        "x-content-type-options": "nosniff",
        "x-frame-options": "SAMEORIGIN",
    }


def _proxy_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"detail": message},
        status_code=status_code,
        headers={
            "cache-control": "no-store",
            "referrer-policy": "no-referrer",
            "x-content-type-options": "nosniff",
        },
    )


__all__ = [
    "SANDBOX_UPLOAD_MAX_BYTES",
    "SandboxProxyTarget",
    "browser_launch_url",
    "mount_sandbox_proxy_routes",
    "proxy_cookie_name",
    "proxy_prefix",
    "terminal_initial_command_url",
    "terminal_launch_url",
    "upload_sandbox_file",
]
