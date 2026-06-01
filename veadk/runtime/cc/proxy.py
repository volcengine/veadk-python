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

"""Anthropic ``/v1/messages`` translation shim for OpenAI-compatible backends.

The Claude Code SDK only speaks the Anthropic protocol over HTTP
(``ANTHROPIC_BASE_URL``). When the user's model endpoint is OpenAI-compatible
(VeADK's default, e.g. Volcengine Ark), this module stands up a tiny in-process
FastAPI server that accepts Anthropic ``/v1/messages`` requests and forwards them
through :func:`litellm.anthropic_messages` to the OpenAI-compatible backend. The
Claude Code SDK is then pointed at the local server's URL.

:func:`detect_endpoint_kind` decides whether a translation shim is needed at all.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Literal, cast

import litellm
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from litellm.exceptions import APIError

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

EndpointKind = Literal["anthropic", "openai"]

# Parameters accepted by litellm.anthropic_messages; anything else in the inbound
# request body is dropped to avoid leaking unsupported fields into the backend.
_PASSTHROUGH_KEYS = (
    "max_tokens",
    "messages",
    "metadata",
    "stop_sequences",
    "stream",
    "system",
    "temperature",
    "thinking",
    "tool_choice",
    "tools",
    "top_k",
    "top_p",
)


def detect_endpoint_kind(base_url: str | None, provider: str | None) -> EndpointKind:
    """Detect whether a model endpoint speaks the Anthropic or OpenAI protocol.

    Provider is authoritative when present: any provider naming Anthropic/Claude
    maps to ``"anthropic"``; any other explicit provider maps to ``"openai"``.
    When the provider is empty, the endpoint host is probed as a fallback.

    Args:
        base_url (str | None): The model API base URL.
        provider (str | None): The configured model provider (e.g. ``"openai"``).

    Returns:
        EndpointKind: ``"anthropic"`` or ``"openai"``.
    """
    p = (provider or "").lower()
    if "anthropic" in p or "claude" in p:
        return "anthropic"
    if p:
        return "openai"

    host = (base_url or "").lower()
    if "anthropic" in host:
        return "anthropic"
    return "openai"


class AnthropicShim:
    """In-process Anthropic ``/v1/messages`` server backed by an OpenAI endpoint.

    Translates inbound Anthropic requests via :func:`litellm.anthropic_messages`
    and forwards them to ``api_base`` using ``api_key`` with
    ``custom_llm_provider="openai"``. Supports both streaming (SSE) and
    non-streaming responses.

    Attributes:
        api_base (str): OpenAI-compatible backend base URL.
        api_key (str): API key for the backend.
        url (str | None): Local server URL once started.
    """

    def __init__(self, api_base: str, api_key: str) -> None:
        self.api_base = api_base
        self.api_key = api_key
        self.url: str | None = None
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[Any] | None = None
        self._app = self._build_app()

    def _build_app(self) -> FastAPI:
        app = FastAPI()

        @app.post("/v1/messages")
        async def messages(request: Request) -> Any:
            body = await request.json()
            model = body["model"]
            stream = bool(body.get("stream", False))

            call_kwargs: dict[str, Any] = {
                key: body[key] for key in _PASSTHROUGH_KEYS if key in body
            }
            call_kwargs.update(
                model=f"openai/{model}",
                api_base=self.api_base,
                api_key=self.api_key,
                custom_llm_provider="openai",
                # Anthropic-only params (e.g. `thinking`) that the OpenAI-compatible
                # backend doesn't support are dropped rather than erroring.
                drop_params=True,
                # Surface backend errors immediately instead of retrying inside
                # litellm (the SDK has its own retry layer on top).
                num_retries=0,
            )

            result = await litellm.anthropic_messages(**call_kwargs)

            if stream:
                # Pull the first chunk here (still inside the handler) so an
                # immediate backend error like 401 propagates to the exception
                # handler as a proper HTTP status instead of breaking a stream
                # that already returned 200 (which makes the SDK retry).
                stream_iter = cast(AsyncIterator[Any], result).__aiter__()
                first = await anext(stream_iter, None)
                return StreamingResponse(
                    _encode_sse(stream_iter, first),
                    media_type="text/event-stream",
                )
            return JSONResponse(_to_dict(result))

        @app.exception_handler(APIError)
        async def _on_api_error(_request: Request, exc: APIError) -> JSONResponse:
            # Surface backend errors (auth, not-found, ...) as Anthropic-format
            # errors with the right status code, so the SDK fails immediately
            # instead of retrying an opaque 500.
            status = getattr(exc, "status_code", 500) or 500
            return JSONResponse(
                status_code=status,
                content={
                    "type": "error",
                    "error": {
                        "type": _anthropic_error_type(status),
                        "message": getattr(exc, "message", str(exc)),
                    },
                },
            )

        return app

    async def start(self) -> str:
        """Start the server on an ephemeral local port and return its URL."""
        if self.url:
            return self.url

        config = uvicorn.Config(
            self._app, host="127.0.0.1", port=0, log_level="warning"
        )
        server = uvicorn.Server(config)
        # Do not hijack process signal handlers from a library context.
        server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        self._server = server
        self._task = asyncio.create_task(server.serve())

        while not server.started:
            await asyncio.sleep(0.02)

        port = server.servers[0].sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        logger.info(f"Anthropic shim started at {self.url} -> {self.api_base}")
        return self.url

    async def stop(self) -> None:
        """Stop the server and await its task."""
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            await self._task
        self.url = None


def _anthropic_error_type(status: int) -> str:
    """Map an HTTP status code to an Anthropic API error ``type`` string."""
    return {
        400: "invalid_request_error",
        401: "authentication_error",
        403: "permission_error",
        404: "not_found_error",
        429: "rate_limit_error",
        529: "overloaded_error",
    }.get(status, "api_error")


def _to_dict(obj: Any) -> dict[str, Any]:
    """Normalize a litellm Anthropic response object into a plain dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return dict(obj)


def _encode_chunk(chunk: Any) -> bytes:
    """Encode one litellm stream chunk as Anthropic SSE bytes."""
    if isinstance(chunk, (bytes, bytearray)):
        return bytes(chunk)
    if isinstance(chunk, str):
        return chunk.encode()
    data = _to_dict(chunk)
    event_type = data.get("type", "message")
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n".encode()


async def _encode_sse(
    chunks: AsyncIterator[Any], first: Any = None
) -> AsyncIterator[bytes]:
    """Re-encode litellm stream chunks as Anthropic-style SSE bytes.

    ``first`` is the already-pulled leading chunk (or ``None``). A mid-stream
    backend error is emitted as an Anthropic ``error`` SSE event so the client
    sees a terminal error rather than a silently truncated stream.
    """
    if first is not None:
        yield _encode_chunk(first)
    try:
        async for chunk in chunks:
            yield _encode_chunk(chunk)
    except APIError as exc:
        status = getattr(exc, "status_code", 500) or 500
        err = {
            "type": "error",
            "error": {
                "type": _anthropic_error_type(status),
                "message": getattr(exc, "message", str(exc)),
            },
        }
        yield f"event: error\ndata: {json.dumps(err)}\n\n".encode()


# Reuse one shim per (api_base, api_key) for the lifetime of the process.
_SHIMS: dict[tuple[str, str], AnthropicShim] = {}


async def get_shim_url(api_base: str, api_key: str) -> str:
    """Return a started shim URL for the given backend, creating it if needed."""
    key = (api_base, api_key)
    shim = _SHIMS.get(key)
    if shim is None:
        shim = AnthropicShim(api_base=api_base, api_key=api_key)
        _SHIMS[key] = shim
    return await shim.start()
