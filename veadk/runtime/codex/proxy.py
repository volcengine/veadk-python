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

"""OpenAI Responses ``/v1/responses`` translation shim for chat backends.

OpenAI Codex only speaks the Responses API (its model providers require
``wire_api = "responses"``). When the user's model endpoint is a plain
OpenAI-compatible *chat-completions* endpoint (VeADK's default, e.g. Volcengine
Ark), this module stands up a tiny in-process FastAPI server that accepts
Responses requests and forwards them through :func:`litellm.aresponses` — whose
completion-transformation bridge converts Responses ⇄ chat-completions — to the
backend. Codex is then pointed at the local server.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import litellm
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from litellm.exceptions import APIError

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

# Parameters accepted by litellm.aresponses; everything else in the inbound
# request body is dropped to avoid forwarding unsupported fields.
_PASSTHROUGH_KEYS = (
    "input",
    "include",
    "instructions",
    "max_output_tokens",
    "metadata",
    "parallel_tool_calls",
    "previous_response_id",
    "reasoning",
    "store",
    "stream",
    "temperature",
    "text",
    "tool_choice",
    "tools",
    "top_p",
    "truncation",
    "user",
)


class ResponsesShim:
    """In-process Responses ``/v1/responses`` server backed by a chat endpoint.

    Translates inbound Responses requests via :func:`litellm.aresponses` and
    forwards them to ``api_base`` using ``api_key`` with
    ``custom_llm_provider="openai"``. Supports streaming (SSE) and non-streaming.

    Attributes:
        api_base (str): OpenAI-compatible (chat) backend base URL.
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

        @app.post("/v1/responses")
        async def responses(request: Request) -> Any:
            body = await request.json()
            model = body["model"]
            stream = bool(body.get("stream", False))

            call_kwargs: dict[str, Any] = {
                key: body[key] for key in _PASSTHROUGH_KEYS if key in body
            }
            # Codex injects its built-in tools (e.g. `web_search`) whose schema
            # carries fields like `external_web_access` that non-OpenAI Responses
            # backends (Ark) reject. Keep only standard `function` tools, which
            # the bridged chat backend understands.
            if isinstance(call_kwargs.get("tools"), list):
                call_kwargs["tools"] = [
                    t for t in call_kwargs["tools"] if t.get("type") == "function"
                ]
            call_kwargs.update(
                model=f"openai/{model}",
                api_base=self.api_base,
                api_key=self.api_key,
                custom_llm_provider="openai",
                drop_params=True,
                num_retries=0,
                stream=False,
            )

            # Always call the backend non-streaming. litellm's chat->Responses
            # bridge can only emit a single degenerate `response.completed`
            # event when streaming a chat backend, which Codex's strict SSE
            # parser rejects (surfaced as a generic "high demand" error). So we
            # fetch the full result and, when Codex asked for a stream,
            # synthesize the canonical Responses event sequence ourselves.
            result = await litellm.aresponses(**call_kwargs)
            resp = _to_dict(result)

            if stream:
                return StreamingResponse(
                    _synth_sse(resp), media_type="text/event-stream"
                )
            return JSONResponse(resp)

        @app.exception_handler(APIError)
        async def _on_api_error(_request: Request, exc: APIError) -> JSONResponse:
            status = getattr(exc, "status_code", 500) or 500
            return JSONResponse(
                status_code=status,
                content={
                    "error": {
                        "type": _error_type(status),
                        "message": getattr(exc, "message", str(exc)),
                    }
                },
            )

        return app

    async def start(self) -> str:
        """Start the server on an ephemeral local port and return its URL."""
        if self.url:
            return self.url

        # The shim app has no startup/shutdown hooks, so disable the lifespan
        # protocol; otherwise its task lingers and logs a CancelledError
        # traceback when the event loop is torn down at process exit.
        config = uvicorn.Config(
            self._app,
            host="127.0.0.1",
            port=0,
            log_level="warning",
            lifespan="off",
        )
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        self._server = server
        self._task = asyncio.create_task(server.serve())

        while not server.started:
            await asyncio.sleep(0.02)

        port = server.servers[0].sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        logger.info(f"Responses shim started at {self.url} -> {self.api_base}")
        return self.url

    async def stop(self) -> None:
        """Stop the server and await its task."""
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            await self._task
        self.url = None


def _error_type(status: int) -> str:
    """Map an HTTP status code to an error ``type`` string."""
    return {
        400: "invalid_request_error",
        401: "authentication_error",
        403: "permission_error",
        404: "not_found_error",
        429: "rate_limit_error",
    }.get(status, "api_error")


def _to_dict(obj: Any) -> dict[str, Any]:
    """Normalize a litellm Responses object into a plain dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return dict(obj)


def _sse(event: dict[str, Any]) -> bytes:
    """Encode one Responses event dict as an SSE frame."""
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()


async def _synth_sse(resp: dict[str, Any]) -> AsyncIterator[bytes]:
    """Synthesize a canonical Responses event stream from a final result.

    litellm's chat->Responses bridge cannot produce a real streamed event
    sequence for a chat backend, so we expand the completed response into the
    ordered events Codex expects: ``response.created`` -> per output item
    (``output_item.added`` -> text/reasoning deltas -> ``output_item.done``) ->
    ``response.completed``. Only ``message`` and ``reasoning`` items are
    emitted (the only kinds the bridged chat backend returns); the completed
    response is trimmed to match what was streamed.
    """
    seq = 0

    def ev(payload: dict[str, Any]) -> bytes:
        nonlocal seq
        payload["sequence_number"] = seq
        seq += 1
        return _sse(payload)

    items = [
        it
        for it in (resp.get("output") or [])
        if it.get("type") in ("message", "reasoning")
    ]
    in_progress = {**resp, "status": "in_progress", "output": []}
    yield ev({"type": "response.created", "response": in_progress})
    yield ev({"type": "response.in_progress", "response": in_progress})

    for idx, item in enumerate(items):
        item_id = item.get("id", f"item_{idx}")
        stub = {**item, "status": "in_progress"}
        if item.get("type") == "message":
            stub = {**stub, "content": []}
        else:
            stub = {**stub, "summary": []}
        yield ev(
            {"type": "response.output_item.added", "output_index": idx, "item": stub}
        )

        if item.get("type") == "message":
            for cidx, part in enumerate(item.get("content") or []):
                text = part.get("text", "")
                base = {"item_id": item_id, "output_index": idx, "content_index": cidx}
                yield ev(
                    {
                        "type": "response.content_part.added",
                        **base,
                        "part": {"type": "output_text", "text": "", "annotations": []},
                    }
                )
                yield ev({"type": "response.output_text.delta", **base, "delta": text})
                yield ev({"type": "response.output_text.done", **base, "text": text})
                yield ev({"type": "response.content_part.done", **base, "part": part})
        else:  # reasoning
            for sidx, summary in enumerate(item.get("summary") or []):
                text = summary.get("text", "")
                base = {"item_id": item_id, "output_index": idx, "summary_index": sidx}
                yield ev(
                    {
                        "type": "response.reasoning_summary_part.added",
                        **base,
                        "part": {"type": "summary_text", "text": ""},
                    }
                )
                yield ev(
                    {
                        "type": "response.reasoning_summary_text.delta",
                        **base,
                        "delta": text,
                    }
                )
                yield ev(
                    {
                        "type": "response.reasoning_summary_text.done",
                        **base,
                        "text": text,
                    }
                )
                yield ev(
                    {
                        "type": "response.reasoning_summary_part.done",
                        **base,
                        "part": summary,
                    }
                )

        yield ev(
            {"type": "response.output_item.done", "output_index": idx, "item": item}
        )

    completed = {**resp, "status": "completed", "output": items}
    yield ev({"type": "response.completed", "response": completed})


# Reuse one shim per (api_base, api_key) for the lifetime of the process.
_SHIMS: dict[tuple[str, str], ResponsesShim] = {}


async def get_shim_url(api_base: str, api_key: str) -> str:
    """Return a started shim URL for the given backend, creating it if needed."""
    key = (api_base, api_key)
    shim = _SHIMS.get(key)
    if shim is None:
        shim = ResponsesShim(api_base=api_base, api_key=api_key)
        _SHIMS[key] = shim
    return await shim.start()
