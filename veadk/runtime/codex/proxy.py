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
import os
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


def _shim_num_retries() -> int:
    """Backend retry count for transient errors (429/5xx/overloaded/timeout).

    Previously the backend call used ``num_retries=0`` with no timeout, so a
    transient Ark error or a stalled connection failed the turn outright and
    the eval client's read timeout (default 300s) fired before any recovery.
    Retrying lets litellm apply its built-in exponential backoff. Env-tunable
    via ``CODEX_SHIM_NUM_RETRIES`` (default 2).
    """
    try:
        return max(0, int(os.getenv("CODEX_SHIM_NUM_RETRIES", "2")))
    except ValueError:
        return 2


def _shim_timeout() -> float:
    """Per-backend-call timeout (seconds) so a hung connection cannot exhaust
    the whole client budget. ``0``/unset keeps litellm's default. Env-tunable
    via ``CODEX_SHIM_TIMEOUT``.
    """
    try:
        return max(0.0, float(os.getenv("CODEX_SHIM_TIMEOUT", "0")))
    except ValueError:
        return 0.0


def _shim_max_tool_iters() -> int:
    """Max shim-internal web tool round-trips per request (``0`` = disabled).

    Codex only speaks the Responses API and its hosted ``web_search`` tool is
    stripped before Ark (Ark rejects its schema), so a Codex+Ark agent has no
    web capability. When this is > 0, the shim translates the hosted web tools
    into Ark-accepted ``function`` tools, executes the veADK builtins itself,
    and loops until the model stops calling them. Default ``0`` keeps the path
    byte-identical to before. Env-tunable via ``CODEX_SHIM_MAX_TOOL_ITERS``
    (recommended 6 when enabling).
    """
    try:
        return max(0, int(os.getenv("CODEX_SHIM_MAX_TOOL_ITERS", "0")))
    except ValueError:
        return 0


# Hosted web tools (Codex emits these; Ark rejects their schema) translated to
# plain Responses ``function`` tools that the shim executes against veADK's own
# builtins. Kept minimal — the builtins own the real parameter handling.
_EXECUTABLE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "web_search",
        "description": "Search the web for a query and return result documents.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."}
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "web_fetch",
        "description": (
            "Fetch a public web page or PDF over HTTP(S) and return its "
            "readable main content."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The http(s) URL to fetch."},
                "extract_mode": {
                    "type": "string",
                    "enum": ["markdown", "text"],
                    "description": "Output format; defaults to markdown.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Truncate content to at most this many chars.",
                },
            },
            "required": ["url"],
        },
    },
]

_EXECUTABLE_TOOL_NAMES = {t["name"] for t in _EXECUTABLE_TOOLS}


async def _run_tool(name: str, args: dict[str, Any]) -> str:
    """Execute a veADK built-in web tool and return a JSON string.

    The web builtins use blocking ``requests``, so they run in a worker thread
    to avoid stalling the shim's event loop. Any error is returned as a JSON
    payload (never raised) so the model can recover on the next turn.
    """
    try:
        from veadk.tools import get_builtin_tool

        fn = get_builtin_tool(name)
        result = await asyncio.to_thread(fn, **args)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:  # noqa: BLE001 - surfaced to the model, not raised
        return json.dumps({"error": str(e)})


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
            # the bridged chat backend understands. When the tool loop is enabled
            # (CODEX_SHIM_MAX_TOOL_ITERS > 0), additionally translate the stripped
            # hosted web tools into Ark-accepted `function` tools that the shim
            # executes itself (see the tool loop below), so a Codex+Ark agent
            # regains web search/fetch.
            if isinstance(call_kwargs.get("tools"), list):
                inbound = call_kwargs["tools"]
                wants_web = any(
                    t.get("type") in ("web_search", "web_search_preview")
                    for t in inbound
                )
                kept = [t for t in inbound if t.get("type") == "function"]
                if wants_web and _shim_max_tool_iters() > 0:
                    have = {t.get("name") for t in kept}
                    kept.extend(
                        t for t in _EXECUTABLE_TOOLS if t["name"] not in have
                    )
                call_kwargs["tools"] = kept
            # On multi-step turns Codex replays prior assistant messages in
            # `input` without a `status` field, but Ark's Responses API
            # requires `status` on assistant messages (MissingParameter:
            # input.status). Backfill it so the tool loop survives a model
            # preamble ("let me look...") followed by a tool call.
            if isinstance(call_kwargs.get("input"), list):
                for item in call_kwargs["input"]:
                    if (
                        isinstance(item, dict)
                        and item.get("type") == "message"
                        and item.get("role") == "assistant"
                        and "status" not in item
                    ):
                        item["status"] = "completed"
            call_kwargs.update(
                model=f"openai/{model}",
                api_base=self.api_base,
                api_key=self.api_key,
                custom_llm_provider="openai",
                drop_params=True,
                num_retries=_shim_num_retries(),
                stream=False,
            )
            timeout = _shim_timeout()
            if timeout:
                call_kwargs["timeout"] = timeout

            # Always call the backend non-streaming. litellm's chat->Responses
            # bridge can only emit a single degenerate `response.completed`
            # event when streaming a chat backend, which Codex's strict SSE
            # parser rejects (surfaced as a generic "high demand" error). So we
            # fetch the full result and, when Codex asked for a stream,
            # synthesize the canonical Responses event sequence ourselves.
            # Bounded shim-internal tool loop: call the backend, and while it
            # asks for an executable web tool, run the veADK builtin and feed
            # the result back as a paired function_call + function_call_output
            # (append BOTH so the chat bridge sees [user, assistant(tool_calls),
            # tool] regardless of its internal cache). Exit purely on the absence
            # of executable function_calls in the fresh output — the always-empty
            # `message` item is ignored. The loop is invisible to Codex: only the
            # final, tool-free turn is returned/synthesized.
            max_iters = _shim_max_tool_iters()
            iters = 0
            while True:
                result = await litellm.aresponses(**call_kwargs)
                resp = _to_dict(result)
                if max_iters <= 0 or iters >= max_iters:
                    break
                conv = call_kwargs.get("input")
                if not isinstance(conv, list):
                    break
                calls = [
                    it
                    for it in (resp.get("output") or [])
                    if it.get("type") == "function_call"
                    and it.get("name") in _EXECUTABLE_TOOL_NAMES
                ]
                if not calls:
                    break
                for fc in calls:
                    cid = fc.get("call_id") or fc.get("id")
                    try:
                        args = json.loads(fc.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    out = await _run_tool(fc["name"], args)
                    conv.append(
                        {
                            "type": "function_call",
                            "call_id": cid,
                            "id": fc.get("id") or cid,
                            "name": fc["name"],
                            "arguments": fc.get("arguments") or "{}",
                            "status": "completed",
                        }
                    )
                    conv.append(
                        {
                            "type": "function_call_output",
                            "call_id": cid,
                            "output": out,
                        }
                    )
                iters += 1

            # If we broke at the iteration cap with an executable function_call
            # still pending, strip it so it never leaks to Codex (which cannot
            # run it and would desync the next turn / emit a null delta).
            if max_iters > 0 and isinstance(resp.get("output"), list):
                resp["output"] = [
                    it
                    for it in resp["output"]
                    if not (
                        it.get("type") == "function_call"
                        and it.get("name") in _EXECUTABLE_TOOL_NAMES
                    )
                ]

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
    (``output_item.added`` -> text/reasoning/tool-call deltas ->
    ``output_item.done``) -> ``response.completed``. ``message``,
    ``reasoning`` and ``function_call`` items are emitted; the last is what
    drives Codex's agentic loop (a dropped tool call ends the turn at the
    preamble). The completed response is trimmed to match what was streamed.
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
        if it.get("type") in ("message", "reasoning", "function_call")
    ]
    in_progress = {**resp, "status": "in_progress", "output": []}
    yield ev({"type": "response.created", "response": in_progress})
    yield ev({"type": "response.in_progress", "response": in_progress})

    for idx, item in enumerate(items):
        item_id = item.get("id", f"item_{idx}")
        item_type = item.get("type")
        stub = {**item, "status": "in_progress"}
        if item_type == "message":
            stub = {**stub, "content": []}
        elif item_type == "reasoning":
            stub = {**stub, "summary": []}
        elif item_type == "function_call":
            stub = {**stub, "arguments": ""}
        yield ev(
            {"type": "response.output_item.added", "output_index": idx, "item": stub}
        )

        if item_type == "function_call":
            # Stream the tool call so Codex executes it and continues the loop.
            args = item.get("arguments", "") or ""
            base = {"item_id": item_id, "output_index": idx}
            yield ev(
                {
                    "type": "response.function_call_arguments.delta",
                    **base,
                    "delta": args,
                }
            )
            yield ev(
                {
                    "type": "response.function_call_arguments.done",
                    **base,
                    "arguments": args,
                }
            )
        elif item_type == "message":
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
