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

"""Same-origin WebUI proxy for managed branded agent Sessions."""

from __future__ import annotations

import asyncio
import contextlib
import html
import inspect
import json
import re
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from veadk.cli.codex_app_server import sandbox_service_url
from veadk.cli.frontend_sandbox_proxy import SandboxProxyTarget
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_MAX_BODY_BYTES = 16 * 1024 * 1024
_TEXT_CONTENT_TYPES = ("text/", "javascript", "json", "manifest", "xml")
_GATEWAY_QUERY_KEYS = frozenset({"authorization", "faasinstancename"})
_HERMES_QUERY_URL_PATTERN = re.compile(
    rb"[^\s\"'`<>()]+\?[^\s\"'`<>()]+",
    re.IGNORECASE,
)
_OPENCLAW_RESET_TAG = (
    b"<script>try{for(const key of Object.keys(localStorage)){"
    b"if(key.startsWith('openclaw.control.settings.v1'))localStorage.removeItem(key)"
    b"}}catch{}</script>"
)
_DEEPSEEK_HARNESS_STATIC_PATHS = (
    "/deepseek-harness-auth-query.js",
    "/deepseek-harness",
    "/plugins",
    "/assets",
)
_HERMES_AIO_PATHS = (
    "/code-server",
    "/terminal",
    "/jupyter",
    "/vnc",
    "/proxy",
    "/absproxy",
    "/mcp",
    "/v1",
    "/llms.txt",
    "/cdp",
    "/tickets",
    "/screenshot",
    "/actions",
    "/json",
    "/devtools",
    "/ws",
    "/websockify",
    "/static/sandbox",
)
_HERMES_DASHBOARD_PATHS = (
    "/achievements",
    "/api",
    "/assets",
    "/channels",
    "/chat",
    "/config",
    "/cron",
    "/docs",
    "/env",
    "/files",
    "/favicon.ico",
    "/kanban",
    "/logs",
    "/mcp",
    "/model",
    "/models",
    "/pairing",
    "/plugins",
    "/profiles",
    "/sessions",
    "/skills",
    "/system",
    "/webhooks",
)
_BLOCKED_RESPONSE_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "content-security-policy",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "x-frame-options",
}


def agent_surface_prefix(
    kind: str,
    session_id: str,
    proxy_token: str,
) -> str:
    """Return the opaque same-origin prefix for one branded WebUI."""
    return f"/web/{kind}/sessions/{session_id}/surface/{proxy_token}"


def _target_url(endpoint: str, path: str, incoming_query: str) -> str:
    target = urlsplit(sandbox_service_url(endpoint, f"/{path.lstrip('/')}"))
    query = dict(parse_qsl(incoming_query, keep_blank_values=True))
    query.update(parse_qsl(target.query, keep_blank_values=True))
    return urlunsplit((target.scheme, target.netloc, target.path, urlencode(query), ""))


def _rewrite_body(
    body: bytes,
    content_type: str,
    prefix: str,
    kind: str,
    *,
    upstream_path: str = "",
) -> bytes:
    if not any(marker in content_type for marker in _TEXT_CONTENT_TYPES):
        return body
    if kind in {"hermes", "deepseek-harness"}:
        body = _strip_hermes_gateway_query(body)
    if kind == "hermes" and b"<title>AIO Sandbox</title>" not in body:
        hermes_mount = _hermes_dashboard_mount(upstream_path)
        if hermes_mount:
            for path in _HERMES_DASHBOARD_PATHS:
                body = _rewrite_root_path(
                    body,
                    path,
                    f"{prefix}{hermes_mount}{path}",
                )
        for path in _HERMES_AIO_PATHS:
            body = _rewrite_root_path(body, path, f"{prefix}{path}")
    if kind == "deepseek-harness":
        return _rewrite_deepseek_harness_body(body, content_type, prefix)
    source = f"/{kind}".encode()
    replacement = f"{prefix}/{kind}".encode()
    for quote in (b'"', b"'", b"`"):
        body = body.replace(quote + source, quote + replacement)
    body = body.replace(b"url(" + source, b"url(" + replacement)
    if kind == "openclaw" and "text/html" in content_type:
        body = body.replace(b"<head>", b"<head>" + _OPENCLAW_RESET_TAG, 1)
    return body


def _hermes_dashboard_mount(upstream_path: str) -> str:
    """Return the AIO port-proxy mount hosting the Hermes Dashboard."""
    normalized = f"/{upstream_path.lstrip('/')}"
    match = re.match(r"^/(absproxy|proxy)/(\d+)(?:/|$)", normalized)
    if match is None:
        return ""
    return f"/{match.group(1)}/{match.group(2)}"


def _rewrite_root_path(body: bytes, source_path: str, replacement_path: str) -> bytes:
    source = source_path.encode()
    replacement = replacement_path.encode()
    for quote in (b'"', b"'", b"`"):
        body = body.replace(quote + source, quote + replacement)
    body = body.replace(b"url(" + source, b"url(" + replacement)
    return body


def _javascript_string(value: str) -> bytes:
    """Return an HTML-safe JavaScript string literal."""
    literal = json.dumps(value, ensure_ascii=True)
    return (
        literal.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .encode()
    )


def _deepseek_harness_surface_bootstrap(prefix: str) -> bytes:
    """Build the browser shim that rebases DSH API traffic at request time."""
    return b"".join(
        (
            b"<script>(()=>{",
            b"const surfacePrefix = ",
            _javascript_string(prefix),
            b";const pageUrl=new URL(window.location.href);",
            b"const sameEndpoint=url=>url.hostname===pageUrl.hostname&&",
            b"url.port===pageUrl.port&&(url.protocol===pageUrl.protocol||",
            b"pageUrl.protocol==='https:'&&url.protocol==='wss:'||",
            b"pageUrl.protocol==='http:'&&url.protocol==='ws:');",
            b"const rebase=input=>{try{",
            b"const source=input instanceof Request?input.url:input;",
            b"const url=new URL(source,window.location.href);",
            b"if(sameEndpoint(url)&&(url.pathname==='/api'||",
            b"url.pathname.startsWith('/api/')||url.pathname.startsWith('/api.')))",
            b"{url.pathname = surfacePrefix + url.pathname;}",
            b"if(input instanceof Request)return new Request(url.toString(),input);",
            b"return url;}catch{return input;}};",
            b"const originalFetch=window.fetch.bind(window);",
            b"window.fetch=(input,init)=>originalFetch(rebase(input),init);",
            b"const OriginalWebSocket=window.WebSocket;",
            b"window.WebSocket=function(url,protocols){const next=rebase(url);",
            b"return protocols===undefined?new OriginalWebSocket(next):",
            b"new OriginalWebSocket(next,protocols);};",
            b"Object.setPrototypeOf(window.WebSocket,OriginalWebSocket);",
            b"window.WebSocket.prototype=OriginalWebSocket.prototype;",
            b"})();</script>",
        )
    )


def _rewrite_deepseek_harness_body(
    body: bytes,
    content_type: str,
    prefix: str,
) -> bytes:
    """Route DSH root assets and runtime API traffic through its Studio surface."""
    for path in _DEEPSEEK_HARNESS_STATIC_PATHS:
        body = _rewrite_root_path(body, path, f"{prefix}{path}")
    if "text/html" in content_type:
        bootstrap = _deepseek_harness_surface_bootstrap(prefix)
        body = body.replace(b"<head>", b"<head>" + bootstrap, 1)
    return body


def _strip_hermes_gateway_query(body: bytes) -> bytes:
    """Keep private Hermes endpoint routing parameters out of browser URLs."""

    def _rewrite_url(match: re.Match[bytes]) -> bytes:
        try:
            raw_url = html.unescape(match.group(0).decode("utf-8"))
        except UnicodeDecodeError:
            return match.group(0)
        parsed = urlsplit(raw_url)
        if not parsed.query:
            return match.group(0)
        query = parse_qsl(parsed.query, keep_blank_values=True)
        public_query = [
            (key, value)
            for key, value in query
            if key.lower() not in _GATEWAY_QUERY_KEYS
        ]
        if len(public_query) == len(query):
            return match.group(0)
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(public_query),
                parsed.fragment,
            )
        ).encode("utf-8")

    return _HERMES_QUERY_URL_PATTERN.sub(_rewrite_url, body)


def _rewrite_location(location: str, prefix: str) -> str:
    if not location:
        return location
    parsed = urlsplit(location)
    if not parsed.path.startswith("/"):
        return location
    safe_query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in _GATEWAY_QUERY_KEYS
        ]
    )
    return urlunsplit(("", "", f"{prefix}{parsed.path}", safe_query, parsed.fragment))


def _websocket_origin(kind: str, path: str, target_url: str) -> str:
    """Return the Origin expected by the upstream WebSocket service.

    AIO exposes arbitrary local ports below ``/proxy/<port>``.  Its HTTP proxy
    accepts the public AgentKit origin, but the WebSocket target validates the
    original local-service origin.  Sending the AgentKit endpoint origin makes
    Hermes reject the upgrade and the browser only sees close code 1006.
    """
    normalized = f"/{path.lstrip('/')}"
    if kind == "hermes":
        match = re.match(r"/(?:abs)?proxy/(\d+)(?:/|$)", normalized)
        if match is not None:
            return f"http://localhost:{match.group(1)}"
    parsed = urlsplit(target_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _rewrite_cookie(cookie: str, prefix: str) -> str:
    if re.search(r"(?i);\s*path=", cookie):
        return re.sub(
            r"(?i)(;\s*path=)(/[^;]*)",
            lambda match: f"{match.group(1)}{prefix}{match.group(2)}",
            cookie,
        )
    return f"{cookie}; Path={prefix}/"


def mount_agent_surface_proxy_routes(
    app: object,
    target_resolver: Callable[
        [str, str, str],
        SandboxProxyTarget | Awaitable[SandboxProxyTarget],
    ],
) -> None:
    """Mount bounded HTTP and WebSocket proxies for branded agent WebUIs."""

    @app.api_route(  # type: ignore[attr-defined]
        "/web/{kind}/sessions/{session_id}/surface/{proxy_token}/{path:path}",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def _proxy_agent_webui(
        kind: str,
        session_id: str,
        proxy_token: str,
        path: str,
        request: Request,
    ) -> Response:
        try:
            resolved = target_resolver(kind, session_id, proxy_token)
            target = await resolved if inspect.isawaitable(resolved) else resolved
        except (KeyError, PermissionError):
            return Response("沙箱页面授权已失效。", status_code=403)
        target_url = _target_url(target.endpoint, path, request.url.query)
        parsed = urlsplit(target_url)
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower()
            in {
                "accept",
                "accept-language",
                "content-type",
                "if-none-match",
                "if-modified-since",
                "user-agent",
            }
        }
        if kind == "hermes":
            session_token = request.headers.get("x-hermes-session-token", "").strip()
            if session_token:
                headers["x-hermes-session-token"] = session_token
        headers["origin"] = f"{parsed.scheme}://{parsed.netloc}"
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=httpx.Timeout(60),
            ) as client:
                upstream = await client.request(
                    request.method,
                    target_url,
                    headers=headers,
                    content=await request.body(),
                )
        except httpx.HTTPError:
            return Response("无法连接沙箱页面。", status_code=502)
        if len(upstream.content) > _MAX_BODY_BYTES:
            return Response("沙箱页面响应过大。", status_code=502)

        prefix = agent_surface_prefix(kind, session_id, proxy_token)
        content_type = upstream.headers.get("content-type", "")
        response_headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in _BLOCKED_RESPONSE_HEADERS
            and key.lower() != "set-cookie"
        }
        if "location" in response_headers:
            response_headers["location"] = _rewrite_location(
                response_headers["location"], prefix
            )
        response = Response(
            content=_rewrite_body(
                upstream.content,
                content_type,
                prefix,
                kind,
                upstream_path=path,
            ),
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=None,
        )
        for cookie in upstream.headers.get_list("set-cookie"):
            response.headers.append("set-cookie", _rewrite_cookie(cookie, prefix))
        return response

    @app.websocket(  # type: ignore[attr-defined]
        "/web/{kind}/sessions/{session_id}/surface/{proxy_token}/{path:path}"
    )
    async def _proxy_agent_websocket(
        websocket: WebSocket,
        kind: str,
        session_id: str,
        proxy_token: str,
        path: str,
    ) -> None:
        import websockets
        from websockets.exceptions import WebSocketException

        try:
            resolved = target_resolver(kind, session_id, proxy_token)
            target = await resolved if inspect.isawaitable(resolved) else resolved
        except (KeyError, PermissionError):
            # Complete the WebSocket upgrade before returning an application-level
            # capability error.  VeFaaS treats a rejected upgrade as a transport
            # failure and temporarily puts the entire Function route in backoff,
            # which can make a single-instance Studio return 429 for unrelated
            # HTTP requests.
            await websocket.accept()
            await websocket.close(code=1008, reason="invalid capability")
            return
        target_http_url = _target_url(target.endpoint, path, websocket.url.query)
        parsed = urlsplit(target_http_url)
        target_ws_url = urlunsplit(
            (
                "wss" if parsed.scheme == "https" else "ws",
                parsed.netloc,
                parsed.path,
                parsed.query,
                "",
            )
        )
        protocols = [
            item.strip()
            for item in websocket.headers.get("sec-websocket-protocol", "").split(",")
            if item.strip()
        ]
        try:
            async with websockets.connect(
                target_ws_url,
                origin=_websocket_origin(kind, path, target_http_url),
                subprotocols=protocols or None,
                max_size=None,
            ) as upstream:
                await websocket.accept(subprotocol=upstream.subprotocol)

                async def _to_upstream() -> None:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            return
                        payload = message.get("text")
                        if payload is None:
                            payload = message.get("bytes")
                        if payload is not None:
                            await upstream.send(payload)

                async def _to_browser() -> None:
                    async for payload in upstream:
                        if isinstance(payload, bytes):
                            await websocket.send_bytes(payload)
                        else:
                            await websocket.send_text(payload)

                browser_task = asyncio.create_task(_to_upstream())
                upstream_task = asyncio.create_task(_to_browser())
                done, pending = await asyncio.wait(
                    {browser_task, upstream_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*done, *pending, return_exceptions=True)
        except WebSocketDisconnect:
            return
        except (OSError, TimeoutError, WebSocketException) as error:
            logger.warning("Managed agent WebUI proxy failed: %s", type(error).__name__)
            with contextlib.suppress(RuntimeError):
                # The upstream failure belongs to this logical WebSocket, not to
                # the Studio Function transport.  Finish the browser-side upgrade
                # before closing so the outer VeFaaS gateway does not back off the
                # only Studio instance.
                await websocket.accept()
                await websocket.close(code=1011)
