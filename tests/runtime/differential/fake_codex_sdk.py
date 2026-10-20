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

"""A Codex SDK double that actually drives the Responses shim over HTTP.

Every previous Codex test cut OpenClaw at one of three mock boundaries:
``litellm.aresponses`` (never exercising the shim), a fake ``AsyncCodex``
(never exercising the shim *or* the wire), or ``httpx.ASGITransport`` against
the shim alone (never exercising the runtime). Each boundary hid a different
class of bug, and the union of the three hid the interesting ones entirely.

:class:`ShimDrivingCodex` collapses all three. It replaces ``AsyncCodex`` in
:mod:`veadk.runtime.codex.runtime` and then behaves like the real Codex CLI:

* it reads its bearer token from ``config.env["VEADK_CODEX_API_KEY"]`` and its
  endpoint from the ``config.toml`` that ``_prepare_codex_home`` generated under
  ``config.env["CODEX_HOME"]`` -- so config generation is under test rather than
  stubbed out;
* it POSTs a real ``/v1/responses`` request with ``stream: True`` through
  ``httpx.ASGITransport`` (in-process, no socket, xdist-safe), which means
  ``proxy._synth_sse`` runs on every differential test for free;
* it parses the synthesized SSE stream back into items;
* it implements the minimal Codex agentic loop: a ``function_call`` item it has
  no executor for is answered locally and the turn is re-POSTed with the call
  and its output appended -- a second request under one token;
* it emits real ``openai_codex`` notification models when the SDK is importable
  and name-compatible shims when it is not.

:class:`DirectDrivingCodex` is the counterpart for the direct mode, where Codex
calls the model provider itself and reaches ADK tools through VeADK's local
streamable-HTTP MCP bridge: no shim, a real ``mcp`` client, and ``mcpToolCall``
thread items shaped like codex 0.159.2's.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import types as pytypes
from typing import Any, AsyncIterator

import httpx

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib

#: ``{shim_url: ResponsesShim}``. The runtime writes the shim URL into
#: ``config.toml``; the fake reads it back and needs the ASGI app behind it.
SHIM_REGISTRY: dict[str, Any] = {}

#: Recorded POST bodies, in order, for tests that assert on the wire shape.
REQUEST_LOG: list[dict[str, Any]] = []


def openai_codex_available() -> bool:
    """Whether the real ``openai-codex`` distribution is importable."""
    if "openai_codex" in sys.modules:
        return not getattr(sys.modules["openai_codex"], "__veadk_stub__", False)
    try:
        return importlib.util.find_spec("openai_codex") is not None
    except (ImportError, ValueError):
        return False


class CodexError(Exception):
    """Stub of ``openai_codex.errors.CodexError`` (used when the SDK is absent)."""


class JsonRpcError(CodexError):
    """Stub of ``openai_codex.errors.JsonRpcError``: same ``code``/``message``."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"JSON-RPC error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class CodexRpcError(JsonRpcError):
    """Stub of ``openai_codex.errors.CodexRpcError``."""


class InvalidRequestError(CodexRpcError):
    """Stub of ``openai_codex.errors.InvalidRequestError`` (JSON-RPC -32600)."""


class InternalRpcError(CodexRpcError):
    """Stub of ``openai_codex.errors.InternalRpcError`` (JSON-RPC -32603)."""


def invalid_request_error_class() -> type:
    """``openai_codex.InvalidRequestError`` if the SDK is real, else the stub's.

    This is what the fake raises for a request real Codex rejects with
    JSON-RPC ``-32600`` (for example ``thread/resume`` of an unknown thread).
    """
    module = sys.modules.get("openai_codex")
    if module is not None and hasattr(module, "InvalidRequestError"):
        return module.InvalidRequestError
    if openai_codex_available():
        from openai_codex import InvalidRequestError as real  # type: ignore

        return real
    return InvalidRequestError


def internal_rpc_error_class() -> type:
    """``openai_codex.InternalRpcError`` if the SDK is real, else the stub's.

    What the fake raises for a request real Codex rejects with JSON-RPC
    ``-32603`` (for example ``turn()`` while a compaction turn is running).
    """
    module = sys.modules.get("openai_codex")
    if module is not None and hasattr(module, "InternalRpcError"):
        return module.InternalRpcError
    if openai_codex_available():
        from openai_codex import InternalRpcError as real  # type: ignore

        return real
    return InternalRpcError


def install_openai_codex_stub() -> bool:
    """Register a minimal ``openai_codex`` stub when the real SDK is absent.

    ``veadk.runtime.codex.runtime`` imports the SDK at module scope, so without
    this the whole differential suite would silently skip on any machine that
    did not ``uv sync --all-extras``. The stub only has to satisfy the names the
    runtime imports; ``AsyncCodex`` itself is always replaced by
    :class:`ShimDrivingCodex`.

    Call this from a *fixture*, never at module import time: pytest finishes
    collecting (and therefore evaluating every ``importorskip("openai_codex")``)
    before the first test runs, so installing it here cannot turn a legitimate
    skip into a spurious pass.

    Returns:
        bool: ``True`` if a stub is now in ``sys.modules``.
    """
    if openai_codex_available():
        return False
    if isinstance(sys.modules.get("openai_codex"), pytypes.ModuleType) and getattr(
        sys.modules["openai_codex"], "__veadk_stub__", False
    ):
        return True

    from enum import Enum

    class _StrEnum(str, Enum):
        pass

    class ApprovalMode(_StrEnum):
        deny_all = "deny_all"
        auto_review = "auto_review"

    class Sandbox(_StrEnum):
        read_only = "read_only"
        workspace_write = "workspace_write"
        full_access = "full_access"

    class CodexConfig:
        def __init__(self, *, cwd: str | None = None, env: dict | None = None) -> None:
            self.cwd = cwd
            self.env = dict(env or {})

    class _Input:
        def __init__(self, value: Any, name: Any = None) -> None:
            if name is None:
                self.value = value
            else:
                self.name, self.value = value, name

    class TextInput(_Input):
        pass

    class ImageInput(_Input):
        pass

    class LocalImageInput(_Input):
        pass

    class MentionInput(_Input):
        pass

    module = pytypes.ModuleType("openai_codex")
    module.__veadk_stub__ = True  # type: ignore[attr-defined]

    for name, value in (
        ("ApprovalMode", ApprovalMode),
        ("Sandbox", Sandbox),
        ("CodexConfig", CodexConfig),
        ("TextInput", TextInput),
        ("ImageInput", ImageInput),
        ("LocalImageInput", LocalImageInput),
        ("MentionInput", MentionInput),
        ("AsyncCodex", ShimDrivingCodex),
        ("CodexError", CodexError),
        ("JsonRpcError", JsonRpcError),
        ("CodexRpcError", CodexRpcError),
        ("InvalidRequestError", InvalidRequestError),
        ("InternalRpcError", InternalRpcError),
    ):
        setattr(module, name, value)

    sys.modules["openai_codex"] = module
    return True


_SHIM_CLASSES: dict[str, type] = {}


def _shim_notification_class(name: str) -> type:
    """A name-compatible stand-in; ``translate`` dispatches on the class name."""
    existing = _SHIM_CLASSES.get(name)
    if existing is not None:
        return existing

    def __init__(self: Any, payload: dict[str, Any]) -> None:
        self._payload = dict(payload)
        for key, value in payload.items():
            setattr(self, key, value)

    def model_dump(self: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return dict(self._payload)

    def __repr__(self: Any) -> str:
        return f"{name}({self._payload!r})"

    cls = type(
        name, (), {"__init__": __init__, "model_dump": model_dump, "__repr__": __repr__}
    )
    _SHIM_CLASSES[name] = cls
    return cls


def make_notification(name: str, payload: dict[str, Any]) -> Any:
    """Build ``name`` from the real SDK when possible, else a shim.

    Real construction is attempted through ``model_validate`` so this stays
    schema-agnostic: if the SDK's model rejects the payload we fall back rather
    than fail, and :mod:`tests.runtime.codex.test_codex_sdk_protocol` is the
    place that asserts real construction actually works.
    """
    if openai_codex_available():
        try:
            from openai_codex.generated import v2_all  # type: ignore

            model = getattr(v2_all, name, None)
            if model is not None and hasattr(model, "model_validate"):
                return model.model_validate(payload)
        except Exception:  # noqa: BLE001 - a schema drift must not break tests
            pass
    return _shim_notification_class(name)(payload)


class _Note:
    """The ``note`` wrapper the SDK stream yields; the runtime reads ``payload``."""

    def __init__(self, payload: Any) -> None:
        self.payload = payload


class ShimDrivingCodex:
    """``AsyncCodex`` replacement that speaks HTTP to the in-process shim."""

    #: Set by tests to make the fake ask for a tool the shim cannot execute,
    #: forcing the two-requests-under-one-token path.
    max_agent_loops = 4

    def __init__(self, *, config: Any) -> None:
        self.config = config

    async def __aenter__(self) -> "ShimDrivingCodex":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def thread_start(self, **kwargs: Any) -> "_Thread":
        return _Thread(self.config, kwargs)


class _Thread:
    def __init__(self, config: Any, start_kwargs: dict[str, Any]) -> None:
        self.config = config
        self.start_kwargs = start_kwargs

    async def turn(self, input_items: Any, **kwargs: Any) -> "_Turn":
        return _Turn(self.config, self.start_kwargs, input_items, kwargs)


class _Turn:
    id = "turn-1"

    def __init__(
        self,
        config: Any,
        start_kwargs: dict[str, Any],
        input_items: Any,
        turn_kwargs: dict[str, Any],
    ) -> None:
        self.config = config
        self.start_kwargs = start_kwargs
        self.input_items = input_items
        self.turn_kwargs = turn_kwargs

    def stream(self) -> AsyncIterator[_Note]:
        return _drive(self)

    async def interrupt(self) -> None:
        return None


def _prompt_text(input_items: Any) -> str:
    texts: list[str] = []
    for item in input_items or []:
        if type(item).__name__ != "TextInput":
            continue
        value = getattr(item, "text", None)
        if value is None:
            value = getattr(item, "value", None)
        if isinstance(value, str):
            texts.append(value)
    return "\n".join(texts)


def shim_endpoint_from_codex_home(codex_home: str) -> str:
    """Read the provider ``base_url`` back out of the generated ``config.toml``.

    Doing this (rather than being handed the URL) is what puts
    ``runtime._prepare_codex_home`` under test.
    """
    with open(os.path.join(codex_home, "config.toml"), "rb") as handle:
        config = tomllib.load(handle)
    return str(config["model_providers"]["veadk"]["base_url"])


async def _drive(turn: _Turn) -> AsyncIterator[_Note]:
    env = dict(getattr(turn.config, "env", None) or {})
    token = env["VEADK_CODEX_API_KEY"]
    base_url = shim_endpoint_from_codex_home(env["CODEX_HOME"])
    shim_url = base_url[: -len("/v1")] if base_url.endswith("/v1") else base_url
    shim = SHIM_REGISTRY.get(shim_url)
    if shim is None:
        raise AssertionError(
            f"no registered shim for {shim_url!r} (from config.toml {base_url!r}); "
            f"known: {sorted(SHIM_REGISTRY)}"
        )

    instructions = "\n\n".join(
        part
        for part in (
            turn.start_kwargs.get("base_instructions"),
            turn.start_kwargs.get("developer_instructions"),
        )
        if part
    )
    conversation: list[dict[str, Any]] = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": _prompt_text(turn.input_items)}],
        }
    ]

    yield _Note(
        make_notification(
            "TurnStartedNotification",
            {"turn": {"id": turn.id, "status": "in_progress"}},
        )
    )

    transport = httpx.ASGITransport(app=shim._app)
    # `ThreadTokenUsage.last` is the model call that just finished; `total` is
    # cumulative for the thread. Keeping them distinct is what lets the suite
    # tell a per-call design apart from a cumulative one -- a fake that sets
    # both to the same block cannot detect double counting in either direction.
    running: dict[str, int] = {}
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url=shim_url, timeout=30.0
        ) as client:
            for _ in range(ShimDrivingCodex.max_agent_loops):
                body = {
                    "model": str(turn.start_kwargs.get("model") or "scripted-model"),
                    "stream": True,
                    "instructions": instructions,
                    "input": conversation,
                    "tools": [],
                    "store": False,
                }
                REQUEST_LOG.append(json.loads(json.dumps(body)))
                response = await client.post(
                    "/v1/responses",
                    headers={"Authorization": f"Bearer {token}"},
                    json=body,
                )
                if response.status_code != 200:
                    yield _Note(
                        make_notification(
                            "ErrorNotification",
                            {
                                "error": {
                                    "code": str(response.status_code),
                                    "message": response.text,
                                },
                                "will_retry": False,
                            },
                        )
                    )
                    break

                items, completed = _parse_sse(response.text)
                last = _usage_block(dict((completed or {}).get("usage") or {}))
                if any(last.values()):
                    for key, value in last.items():
                        running[key] = running.get(key, 0) + value
                    yield _Note(
                        make_notification(
                            "ThreadTokenUsageUpdatedNotification",
                            {
                                "turn_id": turn.id,
                                "model_context_window": 128000,
                                "token_usage": {
                                    "last": last,
                                    "total": dict(running),
                                },
                            },
                        )
                    )

                pending: list[dict[str, Any]] = []
                for item in items:
                    if item.get("type") == "function_call":
                        pending.append(item)
                    for note in _item_notifications(turn.id, item):
                        yield note

                if not pending:
                    break

                # Minimal Codex agentic loop: answer the call locally and
                # re-POST with the pair appended -- a second request under the
                # same turn token, which is the shape that breaks tool history.
                for call in pending:
                    call_id = call.get("call_id") or call.get("id")
                    conversation.append(
                        {
                            "type": "function_call",
                            "call_id": call_id,
                            "id": call.get("id") or call_id,
                            "name": call.get("name"),
                            "arguments": call.get("arguments") or "{}",
                            "status": "completed",
                        }
                    )
                    conversation.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps(
                                {"status": "completed", "output": "codex-executed"}
                            ),
                        }
                    )
    finally:
        pass

    yield _Note(
        make_notification(
            "TurnCompletedNotification",
            {"turn": {"id": turn.id, "status": "completed", "error": None}},
        )
    )


def _usage_block(usage: dict[str, Any]) -> dict[str, int]:
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": int(usage.get("cached_input_tokens") or 0),
        "output_tokens": output_tokens,
        "reasoning_output_tokens": int(usage.get("reasoning_output_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or input_tokens + output_tokens),
    }


def _item_notifications(turn_id: str, item: dict[str, Any]) -> list[_Note]:
    """Map one Responses output item onto the Codex thread-item lifecycle."""
    return [
        _Note(make_notification(name, payload))
        for name, payload in _item_payloads(turn_id, item)
    ]


def _item_payloads(
    turn_id: str, item: dict[str, Any]
) -> list[tuple[str, dict[str, Any]]]:
    """``(notification class name, payload)`` pairs for one output item."""
    item_id = str(item.get("id") or "item")
    itype = item.get("type")

    if itype == "message":
        text = "\n".join(
            str(part.get("text") or "")
            for part in item.get("content") or []
            if isinstance(part, dict)
        )
        thread_item = {"id": item_id, "type": "agentMessage", "text": text}
        return [
            (
                "ItemStartedNotification",
                {
                    "turn_id": turn_id,
                    "item": {"id": item_id, "type": "agentMessage", "text": ""},
                },
            ),
            (
                "AgentMessageDeltaNotification",
                {"turn_id": turn_id, "item_id": item_id, "delta": text},
            ),
            (
                "ItemCompletedNotification",
                {"turn_id": turn_id, "item": thread_item},
            ),
        ]

    if itype == "reasoning":
        summary = [
            {"text": str(entry.get("text") or "")}
            for entry in item.get("summary") or []
            if isinstance(entry, dict)
        ]
        thread_item = {"id": item_id, "type": "reasoning", "summary": summary}
        notes = [
            (
                "ItemStartedNotification",
                {
                    "turn_id": turn_id,
                    "item": {"id": item_id, "type": "reasoning", "summary": []},
                },
            )
        ]
        for entry in summary:
            notes.append(
                (
                    "ReasoningSummaryTextDeltaNotification",
                    {
                        "turn_id": turn_id,
                        "item_id": item_id,
                        "delta": entry["text"],
                    },
                )
            )
        notes.append(
            (
                "ItemCompletedNotification",
                {"turn_id": turn_id, "item": thread_item},
            )
        )
        return notes

    if itype == "function_call":
        thread_item = {
            "id": item_id,
            "type": "dynamicToolCall",
            "namespace": "codex",
            "tool": str(item.get("name") or "tool"),
            "arguments": item.get("arguments") or "{}",
            "content_items": [{"text": "codex-executed"}],
            "success": True,
            "status": "completed",
        }
        return [
            (
                "ItemStartedNotification",
                {"turn_id": turn_id, "item": {**thread_item, "status": None}},
            ),
            (
                "ItemCompletedNotification",
                {"turn_id": turn_id, "item": thread_item},
            ),
        ]

    return []


def _parse_sse(text: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Parse a ``text/event-stream`` body into (done items, completed response).

    Items are taken from ``response.output_item.done`` -- i.e. what Codex would
    actually act on -- not from the terminal payload, so a tool call dropped by
    the synthesizer is invisible to the fake exactly as it would be to Codex.
    """
    items: list[dict[str, Any]] = []
    completed: dict[str, Any] | None = None
    for frame in text.split("\n\n"):
        payload = None
        for line in frame.splitlines():
            if line.startswith("data:"):
                payload = json.loads(line[len("data:") :].strip())
        if not isinstance(payload, dict):
            continue
        if payload.get("type") == "response.output_item.done":
            item = payload.get("item")
            if isinstance(item, dict):
                items.append(item)
        elif payload.get("type") == "response.completed":
            completed = payload.get("response") or {}
    return items, completed


def parse_sse_events(text: str) -> list[dict[str, Any]]:
    """Every SSE frame as ``{"event": name, "data": {...}}``, in wire order."""
    events: list[dict[str, Any]] = []
    for frame in text.split("\n\n"):
        if not frame.strip():
            continue
        name = None
        data = None
        for line in frame.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        events.append({"event": name, "data": data})
    return events


# ===================================================================== direct
#
# The Codex "direct" mode: Codex talks to the model provider itself (thread
# config ``model_providers.<id>``) and reaches ADK tools through VeADK's local
# streamable-HTTP MCP bridge (thread config ``mcp_servers.<name>``). There is no
# Responses shim in the loop, so the double below must not use one either.

#: Every model request any :class:`DirectDrivingCodex` made, in order.
DIRECT_REQUEST_LOG: list[dict[str, Any]] = []

#: Text Codex puts in ``function_call_output`` when an MCP tool needs approval
#: under a never-ask policy (verbatim from codex 0.159.2).
MCP_APPROVAL_DENIED = "MCP tool call requires approval, but approval policy is never"

_END = object()

#: Final user message of a compaction request (verbatim from codex 0.159.2).
COMPACTION_PROMPT = (
    "You are performing a CONTEXT CHECKPOINT COMPACTION. Create a handoff "
    "summary for another LLM that will resume the task.\n\nInclude:\n"
    "- Current progress and key decisions made\n"
    "- Important context, constraints, or user preferences\n"
    "- What remains to be done (clear next steps)\n"
    "- Any critical data, examples, or references needed to continue\n\n"
    "Be concise, structured, and focused on helping the next LLM seamlessly "
    "continue the work.\n"
)
#: Prefix of the user message carrying a compaction summary (codex 0.159.2);
#: the summary text follows after a newline.
SUMMARY_PREFIX = (
    "Another language model started to solve this problem and produced a "
    "summary of its thinking process. You also have access to the state of "
    "the tools that were used by that language model. Use this to build on "
    "the work that has already been done and avoid duplicating work. Here is "
    "the summary produced by the other language model, use the information in "
    "this summary to assist with your own analysis:"
)
#: Thread config key enabling Codex-native auto-compaction.
AUTO_COMPACT_LIMIT_KEY = "model_auto_compact_token_limit"
#: ``-32603`` message for a ``turn()`` racing a compaction turn.
NOT_STEERABLE_COMPACT = "ActiveTurnNotSteerable { turn_kind: Compact }"


def _message(role: str, text: str) -> dict[str, Any]:
    return {
        "type": "message",
        "role": role,
        "content": [{"type": "input_text", "text": text}],
    }


def _message_text(item: dict[str, Any]) -> str:
    return "".join(
        str(part.get("text") or "")
        for part in item.get("content") or []
        if isinstance(part, dict)
    )


def _is_user_message(item: dict[str, Any]) -> bool:
    return item.get("type") == "message" and item.get("role") == "user"


def _is_summary_message(item: dict[str, Any]) -> bool:
    return _is_user_message(item) and _message_text(item).startswith(SUMMARY_PREFIX)


def _steer_text(value: Any) -> str:
    """Text of a ``turn.steer`` input: a str, one input item or a list.

    Items may be ``TextInput``-named objects (as for ``turn()``) or wire dicts
    (``{"type": "text", "text": ...}``); other kinds carry no text here.
    """
    if isinstance(value, str):
        return value
    items = value if isinstance(value, (list, tuple)) else [value]
    texts: list[str] = []
    for item in items:
        if isinstance(item, dict):
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                texts.append(item["text"])
        else:
            text = _prompt_text([item])
            if text:
                texts.append(text)
    return "\n".join(texts)


def _usage_total(usage: dict[str, Any]) -> int:
    """``total_tokens`` of one response (what the auto-compact limit reads)."""
    usage = _normalize_usage(usage)
    total = usage.get("total_tokens")
    if total is None:
        total = int(usage.get("input_tokens") or 0) + int(
            usage.get("output_tokens") or 0
        )
    return int(total or 0)


def _default_model_call() -> Any:
    """The *currently patched* ``litellm.aresponses`` the shim would have used.

    Resolved per call rather than at import so a ``monkeypatch.setattr`` made
    after the fake was constructed still wins -- which keeps
    ``ScriptedBackend.as_aresponses()`` a drop-in model for this fake.
    """
    from veadk.runtime.codex import proxy

    return proxy.litellm.aresponses


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dict(dump())
    return dict(value)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _strip_schema_titles(schema: Any) -> Any:
    """Drop JSON-schema ``title`` annotations the way Codex does before
    advertising an MCP tool (``properties`` keys are data, never stripped)."""
    if isinstance(schema, list):
        return [_strip_schema_titles(entry) for entry in schema]
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "title" and isinstance(value, str):
            continue
        if key in ("properties", "$defs", "definitions") and isinstance(value, dict):
            out[key] = {k: _strip_schema_titles(v) for k, v in value.items()}
        else:
            out[key] = _strip_schema_titles(value)
    return out


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


class DirectDrivingCodex:
    """``AsyncCodex`` replacement for the direct-provider + MCP-bridge mode.

    Select it the same way as :class:`ShimDrivingCodex`::

        monkeypatch.setattr(runtime_module, "AsyncCodex", DirectDrivingCodex)

    or, to override knobs without touching the class, ``DirectDrivingCodex
    .configured(model_call=..., max_agent_loops=...)``, which returns a fresh
    subclass whose ``instances`` list records every client the runtime built.

    Per thread it reads ``model_provider`` / ``config["model_providers"]`` and
    ``config["mcp_servers"]`` from ``thread_start`` kwargs and credentials from
    ``CodexConfig.env``; per turn it connects to every MCP server with the real
    ``mcp`` streamable-HTTP client, advertises its tools as a
    ``{"type": "namespace", "name": "mcp__<server>"}`` tool, and loops model
    call -> namespaced ``function_call`` -> MCP ``tools/call`` ->
    ``function_call_output`` until the model stops calling tools.

    Turn control mirrors codex 0.159.2: ``turn.steer(input)`` adds a user
    message to the running turn's *next* model request (forcing one more
    request even after a final answer); ``thread.compact()`` runs a separate
    compaction turn in the background; and a thread config
    ``model_auto_compact_token_limit`` compacts automatically once the last
    model response's ``total_tokens`` reaches the limit -- before the next
    turn's first request, or mid-turn before a follow-up request, never at the
    end of a turn (see :meth:`_DirectThread.run_compaction`).
    """

    #: Model requests per turn before the loop gives up (Codex has no such
    #: cap; a scripted plan that never stops must still terminate).
    max_agent_loops = 8
    model_context_window = 128000
    #: Async callable taking Responses kwargs; ``None`` = patched litellm.
    model_call: Any = None
    #: Mirror codex's ``Wall time: ...\nOutput:`` framing of MCP outputs.
    wall_time_framing = True
    #: Clients built from a ``configured()`` subclass (``None`` on the base
    #: class, so nothing accumulates process-wide; use ``DIRECT_REQUEST_LOG``).
    instances: list["DirectDrivingCodex"] | None = None

    def __init__(self, *, config: Any, model_call: Any = None) -> None:
        self.config = config
        self.env: dict[str, str] = dict(getattr(config, "env", None) or {})
        if model_call is not None:
            self.model_call = model_call
        #: Every model request body this client sent (plus ``_provider``).
        self.requests: list[dict[str, Any]] = []
        #: Every MCP ``tools/call`` this client issued.
        self.mcp_calls: list[dict[str, Any]] = []
        #: Every notification payload this client streamed, in order.
        self.notifications: list[Any] = []
        self.threads: list[_DirectThread] = []
        #: ``thread_start`` kwargs, one dict per call.
        self.thread_starts: list[dict[str, Any]] = []
        #: ``thread_resume`` kwargs (plus ``thread_id``), one dict per call.
        self.thread_resumes: list[dict[str, Any]] = []
        #: Every accepted ``turn.steer``: ``{"thread_id", "turn_id", "text",
        #: "input"}``.
        self.steers: list[dict[str, Any]] = []
        #: Every compaction request body (also in ``requests``), plus
        #: ``_provider``, ``_trigger`` (``"manual"`` / ``"pre_turn"`` /
        #: ``"mid_turn"``) and ``_turn_id``.
        self.compactions: list[dict[str, Any]] = []
        if type(self).instances is not None:
            type(self).instances.append(self)

    @classmethod
    def configured(cls, **overrides: Any) -> type["DirectDrivingCodex"]:
        """A subclass with class attributes overridden and its own registry."""
        attrs = dict(overrides)
        if "model_call" in attrs and attrs["model_call"] is not None:
            attrs["model_call"] = staticmethod(attrs["model_call"])
        attrs["instances"] = []
        return type(f"Configured{cls.__name__}", (cls,), attrs)

    async def __aenter__(self) -> "DirectDrivingCodex":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def thread_start(self, **kwargs: Any) -> "_DirectThread":
        """Start a thread; a non-ephemeral one persists a rollout file.

        Real Codex defaults to a persisted thread, so ``ephemeral`` omitted or
        ``False`` both write ``$CODEX_HOME/sessions/.../rollout-*-<id>.jsonl``
        (only when ``CodexConfig.env`` names a ``CODEX_HOME``: the fake never
        falls back to ``~/.codex``).
        """
        self.thread_starts.append(dict(kwargs))
        thread = _DirectThread(self, kwargs)
        self.threads.append(thread)
        return thread

    async def thread_resume(self, thread_id: str, **kwargs: Any) -> "_DirectThread":
        """Resume ``thread_id`` from its rollout under this client's CODEX_HOME.

        Mirrors real Codex: only the rollout file is needed; the restored
        history (developer message included) is the prefix of every later
        model request; a new ``developer_instructions`` is ignored; other
        kwargs (``model``, ``model_provider``, ``config``, ``approval_mode``,
        ...) apply from now on. An unknown id raises
        :func:`invalid_request_error_class` (JSON-RPC ``-32600``).
        """
        from veadk.runtime.codex import rollout_io

        self.thread_resumes.append({"thread_id": thread_id, **kwargs})
        home = self.env.get("CODEX_HOME")
        path = None
        try:
            rollout_io.validate_thread_id(thread_id)
        except ValueError:
            pass
        else:
            if home:
                path = rollout_io.find_rollout(home, thread_id)
        if path is None:
            raise invalid_request_error_class()(
                -32600, f"no rollout found for thread id {thread_id}"
            )
        thread = _DirectThread.from_rollout(self, thread_id, path, kwargs)
        self.threads.append(thread)
        return thread

    # ------------------------------------------------------------ resolution

    def _resolve_model_call(self) -> Any:
        call = self.model_call
        return call if call is not None else _default_model_call()


#: Keys a rollout's ``session_meta`` persists so a resume in a fresh process
#: can rebuild the thread's settings (real Codex keeps these in the rollout).
_PERSISTED_START_KEYS = (
    "model",
    "model_provider",
    "base_instructions",
    "developer_instructions",
    "approval_mode",
    "sandbox",
    "cwd",
    "personality",
)


class _DirectThread:
    def __init__(
        self,
        client: DirectDrivingCodex,
        start_kwargs: dict[str, Any],
        *,
        thread_id: str | None = None,
        history: list[dict[str, Any]] | None = None,
        turn_log: list[dict[str, Any]] | None = None,
        rollout_path: str | None = None,
    ):
        import uuid

        self.client = client
        self.start_kwargs = start_kwargs
        # Real thread ids are UUIDs (and must pass rollout_io.validate_thread_id).
        self.id = thread_id or str(uuid.uuid4())
        self.ephemeral = bool(start_kwargs.get("ephemeral"))
        config = dict(start_kwargs.get("config") or {})
        self.provider_id = str(start_kwargs.get("model_provider") or "")
        providers = dict(config.get("model_providers") or {})
        self.provider: dict[str, Any] = dict(providers.get(self.provider_id) or {})
        if not self.provider and "CODEX_HOME" in client.env:
            # Tolerate a provider still written to config.toml.
            path = os.path.join(client.env["CODEX_HOME"], "config.toml")
            if os.path.exists(path):
                with open(path, "rb") as handle:
                    home = tomllib.load(handle)
                self.provider = dict(
                    (home.get("model_providers") or {}).get(self.provider_id) or {}
                )
        self.mcp_servers: dict[str, dict[str, Any]] = {
            str(name): dict(value or {})
            for name, value in dict(config.get("mcp_servers") or {}).items()
        }
        #: Thread history carried across turns, as real Codex does: exactly
        #: the Responses ``input`` items the next model request starts with.
        self.history: list[dict[str, Any]] = list(history or [])
        #: ``{"id", "status"}`` per finished turn (restored on resume).
        self.turn_log: list[dict[str, Any]] = list(turn_log or [])
        self.turns: list[_DirectTurn] = []
        #: Absolute rollout path; set on resume, created lazily on first write.
        self.rollout_path: str | None = rollout_path
        # History items already on disk (a resumed rollout holds them all).
        self._persisted = len(self.history)
        limit = config.get(AUTO_COMPACT_LIMIT_KEY)
        #: ``model_auto_compact_token_limit`` from this thread's config
        #: (``thread_start`` or ``thread_resume``); ``None`` = never auto.
        self.auto_compact_limit: int | None = None if limit is None else int(limit)
        #: ``total_tokens`` of the last model response (persisted, so a
        #: resumed thread can compact before its first turn, as Codex does).
        self.last_total_tokens = 0
        #: Set by a manual / pre-turn compaction: the next turn re-injects the
        #: developer message after the summary (Codex's initial context).
        self.reinject_initial_context = False
        #: Developer instructions a re-injection uses: on resume, Codex takes
        #: the resume call's value (the original stays in the old history).
        self.developer_instructions = start_kwargs.get("developer_instructions")
        #: The turn that is running (created and not yet finished), if any.
        self.active_turn: _DirectTurn | None = None
        #: The running (or last) manual compaction task.
        self.compaction: asyncio.Task[None] | None = None
        self._compaction_turn: dict[str, Any] | None = None

    @classmethod
    def from_rollout(
        cls,
        client: DirectDrivingCodex,
        thread_id: str,
        path: str,
        resume_kwargs: dict[str, Any],
    ) -> "_DirectThread":
        meta: dict[str, Any] = {}
        history: list[dict[str, Any]] = []
        turn_log: list[dict[str, Any]] = []
        last_total = 0
        reinject = False
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                kind, payload = record.get("type"), record.get("payload")
                if kind == "session_meta":
                    meta = dict(payload or {})
                elif kind == "response_item":
                    history.append(payload)
                    if (payload or {}).get("role") == "developer":
                        reinject = False
                elif kind == "turn_completed":
                    turn_log.append(dict(payload or {}))
                elif kind == "compacted":
                    # Like Codex's ``compacted`` record: the history is
                    # replaced wholesale, not appended to.
                    payload = dict(payload or {})
                    history = list(payload.get("replacement_history") or [])
                    reinject = bool(payload.get("reinject_initial_context"))
                    last_total = 0
                elif kind == "token_count":
                    last_total = int((payload or {}).get("last_total_tokens") or 0)
        if meta.get("id") != thread_id:
            raise invalid_request_error_class()(
                -32600, f"rollout for {thread_id} has mismatched session id"
            )
        effective = {k: meta[k] for k in _PERSISTED_START_KEYS if k in meta}
        for key, value in resume_kwargs.items():
            # The original developer message stays in history; real Codex
            # does not swap it for the one passed on resume.
            if key in ("developer_instructions", "include_turns") or value is None:
                continue
            effective[key] = value
        effective["ephemeral"] = False
        thread = cls(
            client,
            effective,
            thread_id=thread_id,
            history=history,
            turn_log=turn_log,
            rollout_path=path,
        )
        thread.last_total_tokens = last_total
        thread.reinject_initial_context = reinject
        thread.developer_instructions = resume_kwargs.get(
            "developer_instructions"
        ) or meta.get("developer_instructions")
        return thread

    async def turn(self, input_items: Any, **kwargs: Any) -> "_DirectTurn":
        if self.compacting:
            raise internal_rpc_error_class()(-32603, NOT_STEERABLE_COMPACT)
        turn = _DirectTurn(self, input_items, kwargs)
        self.turns.append(turn)
        self.active_turn = turn
        return turn

    # ----------------------------------------------------------- compaction

    @property
    def compacting(self) -> bool:
        return self.compaction is not None and not self.compaction.done()

    def over_auto_compact_limit(self) -> bool:
        """Codex's trigger: the last response's ``total_tokens`` >= limit
        (cumulative usage across responses never counts)."""
        limit = self.auto_compact_limit
        return limit is not None and self.last_total_tokens >= limit

    def record_usage(self, usage: dict[str, Any]) -> None:
        self.last_total_tokens = _usage_total(usage)
        self._write_record("token_count", {"last_total_tokens": self.last_total_tokens})

    async def compact(self) -> Any:
        """Start a compaction turn and return at once (``thread/compact/start``).

        Like real Codex, the compaction turn's events reach no turn handle;
        ``read(include_turns=True)`` shows it (``inProgress``, then final) as a
        turn holding one ``contextCompaction`` item, and a ``turn()`` while it
        runs fails with ``-32603`` ``ActiveTurnNotSteerable``. Await
        ``thread.compaction`` (or poll ``read``) to see it finish.
        """
        import uuid
        from types import SimpleNamespace

        if self.compacting:
            raise internal_rpc_error_class()(-32603, NOT_STEERABLE_COMPACT)
        turn_id = f"turn-{uuid.uuid4().hex[:12]}"
        item = {"type": "contextCompaction", "id": f"compact-{uuid.uuid4().hex[:12]}"}
        self._compaction_turn = {"id": turn_id, "status": "inProgress", "items": [item]}
        self.compaction = asyncio.create_task(self._manual_compaction(turn_id, item))
        return SimpleNamespace()

    async def _manual_compaction(self, turn_id: str, item: dict[str, Any]) -> None:
        status = "completed"
        try:
            await self.run_compaction("manual", turn_id=turn_id)
        except asyncio.CancelledError:
            status = "interrupted"
            raise
        except Exception:  # noqa: BLE001 - a failed compaction turn
            status = "failed"
        finally:
            # Record the finished turn before dropping the in-progress view,
            # with no await in between, so ``read`` never misses it.
            self.persist({"id": turn_id, "status": status, "items": [item]})
            self._compaction_turn = None

    async def run_compaction(
        self, trigger: str, *, turn_id: str | None = None
    ) -> dict[str, Any]:
        """One compaction pass; returns the compaction response's usage.

        Verified against codex 0.159.2: the request re-sends the whole history
        plus a final :data:`COMPACTION_PROMPT` user message with ``tools=[]``
        and ``parallel_tool_calls=False``. The new history keeps only the
        earlier *user* messages (previous summaries dropped) followed by
        :data:`SUMMARY_PREFIX` + the model's text; assistant replies, tool
        calls and tool outputs are dropped. After a manual or pre-turn
        compaction the next turn re-injects the developer message after the
        summary; a mid-turn compaction (``trigger="mid_turn"``) puts it at the
        front immediately, since the turn keeps sampling. The rewrite is
        persisted as a ``compacted`` rollout record, so a resume sees it.
        """
        self.persist()
        provider = self.provider
        env_key = provider.get("env_key")
        api_key = self.client.env.get(str(env_key)) if env_key else None
        body = {
            "model": str(self.start_kwargs.get("model") or "scripted-model"),
            "instructions": str(self.start_kwargs.get("base_instructions") or ""),
            "input": json.loads(json.dumps(self.history))
            + [_message("user", COMPACTION_PROMPT)],
            "tools": [],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "store": False,
            "stream": False,
        }
        record = json.loads(json.dumps(body))
        record["_provider"] = {
            "id": self.provider_id,
            "base_url": provider.get("base_url"),
            "env_key": env_key,
            "wire_api": provider.get("wire_api"),
            "api_key": api_key,
        }
        record["_trigger"] = trigger
        record["_turn_id"] = turn_id
        self.client.requests.append(record)
        self.client.compactions.append(record)
        DIRECT_REQUEST_LOG.append(record)
        response = _as_dict(
            await self.client._resolve_model_call()(
                **body, api_base=provider.get("base_url"), api_key=api_key
            )
        )
        summary = "".join(
            _message_text(item)
            for item in (_as_dict(i) for i in response.get("output") or [])
            if item.get("type") == "message"
        )
        replacement: list[dict[str, Any]] = []
        if trigger == "mid_turn" and self.developer_instructions:
            replacement.append(_message("developer", str(self.developer_instructions)))
        replacement.extend(
            item
            for item in self.history
            if _is_user_message(item) and not _is_summary_message(item)
        )
        replacement.append(_message("user", f"{SUMMARY_PREFIX}\n{summary}"))
        self.history = replacement
        self.reinject_initial_context = trigger != "mid_turn"
        self.last_total_tokens = 0
        self._write_record(
            "compacted",
            {
                "message": f"{SUMMARY_PREFIX}\n{summary}",
                "replacement_history": replacement,
                "reinject_initial_context": self.reinject_initial_context,
            },
            flush=False,
        )
        self._persisted = len(self.history)
        return dict(response.get("usage") or {})

    async def read(self, *, include_turns: bool = False) -> Any:
        """A ``ThreadReadResponse``-shaped ``SimpleNamespace``.

        Like real Codex, ``include_turns=True`` on an ephemeral thread is an
        invalid request.
        """
        from types import SimpleNamespace

        if include_turns and self.ephemeral:
            raise invalid_request_error_class()(
                -32600, "ephemeral threads do not support includeTurns"
            )
        turns: list[Any] = []
        if include_turns:
            log = list(self.turn_log)
            if self._compaction_turn is not None:
                log.append(self._compaction_turn)
            for entry in log:
                entry = dict(entry)
                # Only ``contextCompaction`` items are recorded per turn.
                items = [SimpleNamespace(**i) for i in entry.pop("items", None) or []]
                turns.append(SimpleNamespace(items=items, **entry))
        return SimpleNamespace(
            thread=SimpleNamespace(id=self.id, ephemeral=self.ephemeral, turns=turns)
        )

    # -------------------------------------------------------------- rollout

    def _rollout_writable(self) -> bool:
        return not self.ephemeral and bool(self.client.env.get("CODEX_HOME"))

    def _open_rollout(self) -> Any:
        """Append handle on the rollout, creating it (with meta) on first use."""
        from datetime import datetime

        if self.rollout_path is None:
            now = datetime.now()
            directory = os.path.join(
                self.client.env["CODEX_HOME"],
                "sessions",
                now.strftime("%Y"),
                now.strftime("%m"),
                now.strftime("%d"),
            )
            os.makedirs(directory, exist_ok=True)
            self.rollout_path = os.path.join(
                directory,
                f"rollout-{now.strftime('%Y-%m-%dT%H-%M-%S')}-{self.id}.jsonl",
            )
            meta = {
                "id": self.id,
                "timestamp": now.isoformat(),
                **{
                    k: _enum_value(self.start_kwargs[k])
                    for k in _PERSISTED_START_KEYS
                    if self.start_kwargs.get(k) is not None
                },
            }
            with open(self.rollout_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"type": "session_meta", "payload": meta}))
                handle.write("\n")
        return open(self.rollout_path, "a", encoding="utf-8")

    def persist(self, turn_status: dict[str, Any] | None = None) -> None:
        """Append new history items (and a turn marker) to the rollout.

        Called after the user message is recorded, after every model response
        and after every batch of tool outputs, so the file holds the whole
        thread at each point -- as real Codex's rollout recorder does.
        """
        if not self._rollout_writable():
            if turn_status is not None:
                self.turn_log.append(turn_status)
            return
        with self._open_rollout() as handle:
            for item in self.history[self._persisted :]:
                handle.write(json.dumps({"type": "response_item", "payload": item}))
                handle.write("\n")
            if turn_status is not None:
                handle.write(
                    json.dumps({"type": "turn_completed", "payload": turn_status})
                )
                handle.write("\n")
        self._persisted = len(self.history)
        if turn_status is not None:
            self.turn_log.append(turn_status)

    def _write_record(
        self, kind: str, payload: dict[str, Any], *, flush: bool = True
    ) -> None:
        """Append one non-history record, after pending history if ``flush``."""
        if flush:
            self.persist()
        if not self._rollout_writable():
            return
        with self._open_rollout() as handle:
            handle.write(json.dumps({"type": kind, "payload": payload}))
            handle.write("\n")


class _McpServer:
    """One connected MCP server for the lifetime of a turn."""

    def __init__(self, name: str, config: dict[str, Any], session: Any) -> None:
        self.name = name
        self.config = config
        self.session = session
        self.namespace = f"mcp__{name}"
        self.tools: dict[str, Any] = {}

    @property
    def parallel(self) -> bool:
        return bool(self.config.get("supports_parallel_tool_calls"))

    def approved(self, tool: str) -> bool:
        per_tool = dict((self.config.get("tools") or {}).get(tool) or {})
        mode = per_tool.get("approval_mode") or self.config.get(
            "default_tools_approval_mode"
        )
        return mode == "approve"

    def namespace_tool(self) -> dict[str, Any]:
        return {
            "type": "namespace",
            "name": self.namespace,
            "description": f"Tools in the {self.namespace} namespace.",
            "tools": [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description or "",
                    "strict": False,
                    "parameters": _strip_schema_titles(
                        dict(tool.inputSchema or {"type": "object"})
                    ),
                }
                for tool in self.tools.values()
            ],
        }


class _DirectTurn:
    def __init__(
        self, thread: _DirectThread, input_items: Any, turn_kwargs: dict[str, Any]
    ) -> None:
        import uuid

        self.thread = thread
        self.client = thread.client
        self.input_items = input_items
        self.turn_kwargs = turn_kwargs
        self.id = f"turn-{uuid.uuid4().hex[:12]}"
        self._worker: asyncio.Task[None] | None = None
        self._interrupted = False
        #: Steered texts not yet added to a model request.
        self._pending_steers: list[str] = []
        #: False once the turn can no longer take steered input.
        self._accepting = True
        #: ``contextCompaction`` items of auto-compactions in this turn.
        self.items: list[dict[str, Any]] = []

    async def steer(self, input: Any) -> Any:
        """Add user input to this running turn (``turn/steer``).

        As in codex 0.159.2 the input becomes a user message (and a
        ``userMessage`` item) in the turn's *next* model request -- never the
        one in flight -- and forces that request even when the in-flight one
        ends the turn. The turn id is unchanged. A finished turn raises
        ``-32600`` "no active turn to steer" (or "expected active turn id ...
        but found ..." when another turn of the thread is running).
        """
        from types import SimpleNamespace

        if not self._accepting:
            active = self.thread.active_turn
            if active is not None and active is not self and active._accepting:
                raise invalid_request_error_class()(
                    -32600,
                    f"expected active turn id {self.id} but found {active.id}",
                )
            raise invalid_request_error_class()(-32600, "no active turn to steer")
        text = _steer_text(input)
        self._pending_steers.append(text)
        self.client.steers.append(
            {
                "thread_id": self.thread.id,
                "turn_id": self.id,
                "text": text,
                "input": input,
            }
        )
        return SimpleNamespace(turn_id=self.id)

    def _close(self) -> None:
        self._accepting = False
        if self.thread.active_turn is self:
            self.thread.active_turn = None

    def _status_record(self, status: str) -> dict[str, Any]:
        record: dict[str, Any] = {"id": self.id, "status": status}
        if self.items:
            record["items"] = [dict(item) for item in self.items]
        return record

    def _user_item_notes(self, text: str, emit: Any) -> None:
        import uuid

        item = {
            "id": f"user-{uuid.uuid4().hex[:12]}",
            "type": "userMessage",
            "content": [{"type": "text", "text": text, "text_elements": []}],
        }
        emit(self._note("ItemStartedNotification", {"item": item}))
        emit(self._note("ItemCompletedNotification", {"item": item}))

    def _drain_steers(self, emit: Any) -> bool:
        """Move pending steers into history; True if there were any."""
        steers, self._pending_steers = self._pending_steers, []
        for text in steers:
            self._user_item_notes(text, emit)
            self.thread.history.append(_message("user", text))
        if steers:
            self.thread.persist()
        return bool(steers)

    async def _auto_compact(
        self, trigger: str, emit: Any, running: dict[str, int]
    ) -> dict[str, Any] | None:
        """Run an auto-compaction inside this turn; an error dict on failure.

        Its ``contextCompaction`` item (and the compaction's token usage) is
        streamed on this turn's handle, as real Codex does.
        """
        import uuid

        item = {"type": "contextCompaction", "id": f"compact-{uuid.uuid4().hex[:12]}"}
        emit(self._note("ItemStartedNotification", {"item": dict(item)}))
        try:
            usage = await self.thread.run_compaction(trigger, turn_id=self.id)
        except Exception as e:  # noqa: BLE001 - becomes a failed turn
            return {"message": f"{type(e).__name__}: {e}"}
        self.items.append(item)
        last = _usage_block(_normalize_usage(usage))
        for key, value in last.items():
            running[key] = running.get(key, 0) + value
        emit(
            self._note(
                "ThreadTokenUsageUpdatedNotification",
                {
                    "token_usage": {
                        "last": last,
                        "total": dict(running),
                        "model_context_window": self.client.model_context_window,
                    }
                },
            )
        )
        emit(self._note("ItemCompletedNotification", {"item": dict(item)}))
        return None

    async def interrupt(self) -> None:
        """Cancel the in-flight model / MCP calls; the stream then closes
        with a ``turn/completed`` whose status is ``interrupted``."""
        self._interrupted = True
        worker = self._worker
        if worker is not None and not worker.done():
            worker.cancel()

    def stream(self) -> AsyncIterator[_Note]:
        return self._stream()

    # ------------------------------------------------------------- plumbing

    def _note(self, name: str, payload: dict[str, Any]) -> _Note:
        payload = dict(payload)
        if name != "TurnStartedNotification" and name != "TurnCompletedNotification":
            payload.setdefault("turn_id", self.id)
        payload.setdefault("thread_id", self.thread.id)
        if name == "ItemStartedNotification":
            payload.setdefault("started_at_ms", _now_ms())
        elif name == "ItemCompletedNotification":
            payload.setdefault("completed_at_ms", _now_ms())
        elif name == "ReasoningSummaryTextDeltaNotification":
            payload.setdefault("summary_index", 0)
        note = _Note(make_notification(name, payload))
        self.client.notifications.append(note.payload)
        return note

    def _turn_note(self, status: str, error: dict[str, Any] | None) -> _Note:
        return self._note(
            "TurnCompletedNotification",
            {
                "turn": {
                    "id": self.id,
                    "items": [],
                    "status": status,
                    "error": error,
                }
            },
        )

    async def _stream(self) -> AsyncIterator[_Note]:
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._worker = asyncio.create_task(self._run(queue))
        if self._interrupted:
            self._worker.cancel()
        try:
            while True:
                note = await queue.get()
                if note is _END:
                    break
                yield note
            try:
                await self._worker
            except asyncio.CancelledError:
                if not self._interrupted:
                    raise
                self.thread.persist(self._status_record("interrupted"))
                yield self._turn_note("interrupted", None)
        finally:
            self._close()
            if not self._worker.done():
                self._worker.cancel()
                await asyncio.gather(self._worker, return_exceptions=True)

    async def _run(self, queue: asyncio.Queue[Any]) -> None:
        from contextlib import AsyncExitStack

        emit = queue.put_nowait
        try:
            emit(
                self._note(
                    "TurnStartedNotification",
                    {"turn": {"id": self.id, "items": [], "status": "inProgress"}},
                )
            )
            async with AsyncExitStack() as stack:
                servers = await self._connect(stack)
                error = await self._loop(servers, emit)
            self._close()
            self.thread.persist(
                self._status_record("completed" if error is None else "failed")
            )
            if error is None:
                emit(self._turn_note("completed", None))
            else:
                emit(
                    self._note(
                        "ErrorNotification", {"error": error, "will_retry": False}
                    )
                )
                emit(self._turn_note("failed", error))
        finally:
            self._close()
            emit(_END)

    async def _connect(self, stack: Any) -> dict[str, _McpServer]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        servers: dict[str, _McpServer] = {}
        for name, config in self.thread.mcp_servers.items():
            if config.get("enabled") is False:
                continue
            headers = dict(config.get("http_headers") or {})
            token_var = config.get("bearer_token_env_var")
            if token_var:
                token = self.client.env.get(str(token_var))
                if token is None:
                    raise AssertionError(
                        f"mcp_servers.{name}.bearer_token_env_var={token_var!r} "
                        "is not set in CodexConfig.env"
                    )
                headers["Authorization"] = f"Bearer {token}"
            http = await stack.enter_async_context(
                httpx.AsyncClient(
                    headers=headers,
                    timeout=httpx.Timeout(30.0, read=300.0),
                )
            )
            read, write, _ = await stack.enter_async_context(
                streamable_http_client(str(config["url"]), http_client=http)
            )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            server = _McpServer(name, config, session)
            enabled = config.get("enabled_tools")
            disabled = set(config.get("disabled_tools") or ())
            for tool in (await session.list_tools()).tools:
                if enabled is not None and tool.name not in enabled:
                    continue
                if tool.name in disabled:
                    continue
                server.tools[tool.name] = tool
            servers[server.namespace] = server
        return servers

    def _request_body(self, servers: dict[str, _McpServer]) -> dict[str, Any]:
        start = self.thread.start_kwargs
        return {
            "model": str(start.get("model") or "scripted-model"),
            "instructions": str(start.get("base_instructions") or ""),
            "input": json.loads(json.dumps(self.thread.history)),
            "tools": [s.namespace_tool() for s in servers.values() if s.tools],
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "store": False,
            "stream": False,
        }

    def _seed_history(self) -> None:
        history = self.thread.history
        developer = self.thread.start_kwargs.get("developer_instructions")
        if self.thread.reinject_initial_context:
            # After a manual / pre-turn compaction Codex re-sends its initial
            # context (developer message) after the summary.
            self.thread.reinject_initial_context = False
            if self.thread.developer_instructions:
                history.append(
                    _message("developer", str(self.thread.developer_instructions))
                )
        elif developer and not history:
            history.append(
                {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": str(developer)}],
                }
            )
        history.append(
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": _prompt_text(self.input_items)}
                ],
            }
        )

    async def _loop(
        self, servers: dict[str, _McpServer], emit: Any
    ) -> dict[str, Any] | None:
        import uuid

        running: dict[str, int] = {}
        if self.thread.over_auto_compact_limit():
            # Pre-turn auto-compaction: before the new user message exists.
            error = await self._auto_compact("pre_turn", emit, running)
            if error is not None:
                return error

        user_item_id = f"user-{uuid.uuid4().hex[:12]}"
        user_item = {
            "id": user_item_id,
            "type": "userMessage",
            "content": [
                {
                    "type": "text",
                    "text": _prompt_text(self.input_items),
                    "text_elements": [],
                }
            ],
        }
        emit(self._note("ItemStartedNotification", {"item": user_item}))
        emit(self._note("ItemCompletedNotification", {"item": user_item}))
        self._seed_history()
        self.thread.persist()

        provider = self.thread.provider
        env_key = provider.get("env_key")
        api_key = self.client.env.get(str(env_key)) if env_key else None

        for _ in range(self.client.max_agent_loops):
            body = self._request_body(servers)
            record = json.loads(json.dumps(body))
            record["_provider"] = {
                "id": self.thread.provider_id,
                "base_url": provider.get("base_url"),
                "env_key": env_key,
                "wire_api": provider.get("wire_api"),
                "api_key": api_key,
            }
            self.client.requests.append(record)
            DIRECT_REQUEST_LOG.append(record)
            try:
                response = _as_dict(
                    await self.client._resolve_model_call()(
                        **body, api_base=provider.get("base_url"), api_key=api_key
                    )
                )
            except Exception as e:  # noqa: BLE001 - becomes a failed turn
                return {"message": f"{type(e).__name__}: {e}"}

            output = [_as_dict(item) for item in response.get("output") or []]
            calls: list[dict[str, Any]] = []
            for item in output:
                itype = item.get("type")
                if itype == "function_call":
                    calls.append(item)
                    self.thread.history.append(
                        {
                            key: item[key]
                            for key in (
                                "type",
                                "id",
                                "name",
                                "namespace",
                                "arguments",
                                "call_id",
                            )
                            if key in item
                        }
                    )
                    continue
                if itype in ("message", "reasoning"):
                    self.thread.history.append(item)
                for name, payload in _item_payloads(self.id, item):
                    emit(self._note(name, payload))
            self.thread.persist()

            outputs = await self._execute(calls, servers, emit)
            self.thread.history.extend(outputs)
            self.thread.persist()
            steered = self._drain_steers(emit)
            self.thread.record_usage(dict(response.get("usage") or {}))

            last = _usage_block(_normalize_usage(response.get("usage") or {}))
            for key, value in last.items():
                running[key] = running.get(key, 0) + value
            emit(
                self._note(
                    "ThreadTokenUsageUpdatedNotification",
                    {
                        "token_usage": {
                            "last": last,
                            "total": dict(running),
                            "model_context_window": self.client.model_context_window,
                        }
                    },
                )
            )
            if not calls and not steered:
                self._accepting = False
                break
            if self.thread.over_auto_compact_limit():
                # Mid-turn auto-compaction, before the follow-up request.
                error = await self._auto_compact("mid_turn", emit, running)
                if error is not None:
                    return error
        self._accepting = False
        return None

    # ------------------------------------------------------------ tool calls

    async def _execute(
        self, calls: list[dict[str, Any]], servers: dict[str, _McpServer], emit: Any
    ) -> list[dict[str, Any]]:
        """Run one response's calls; return outputs in call order."""
        results: list[dict[str, Any] | None] = [None] * len(calls)

        async def run(index: int, call: dict[str, Any]) -> None:
            results[index] = await self._execute_one(call, servers, emit)

        concurrent: list[asyncio.Task[None]] = []
        for index, call in enumerate(calls):
            server = servers.get(str(call.get("namespace") or ""))
            if server is not None and server.parallel:
                # Codex starts every parallel-safe call before awaiting any.
                concurrent.append(asyncio.ensure_future(run(index, call)))
                await asyncio.sleep(0)
            else:
                await run(index, call)
        if concurrent:
            try:
                await asyncio.gather(*concurrent)
            except BaseException:
                for task in concurrent:
                    task.cancel()
                await asyncio.gather(*concurrent, return_exceptions=True)
                raise
        return [r for r in results if r is not None]

    async def _execute_one(
        self, call: dict[str, Any], servers: dict[str, _McpServer], emit: Any
    ) -> dict[str, Any]:
        import time
        from datetime import timedelta

        call_id = str(call.get("call_id") or call.get("id") or "call")
        namespace = call.get("namespace")
        server = servers.get(str(namespace or ""))
        if server is None:
            # Not an MCP call: behave like ShimDrivingCodex's native tools.
            for name, payload in _item_payloads(self.id, call):
                emit(self._note(name, payload))
            return {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(
                    {"status": "completed", "output": "codex-executed"}
                ),
            }

        tool = str(call.get("name") or "")
        raw_args = call.get("arguments") or "{}"
        try:
            arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            arguments = raw_args
        item = {
            "id": call_id,
            "type": "mcpToolCall",
            "server": server.name,
            "tool": tool,
            "arguments": arguments,
            "status": "inProgress",
        }
        emit(self._note("ItemStartedNotification", {"item": dict(item)}))
        started = time.monotonic()

        result: dict[str, Any] | None = None
        error: dict[str, Any] | None = None
        texts: list[str] = []
        failed = False
        if not isinstance(arguments, dict):
            error = {"message": f"failed to parse function arguments: {raw_args}"}
        elif tool not in server.tools:
            error = {"message": f"unknown MCP tool {tool!r} on server {server.name!r}"}
        elif not server.approved(tool) and (
            _enum_value(self.turn_kwargs.get("approval_mode"))
            or _enum_value(self.thread.start_kwargs.get("approval_mode"))
        ) in ("deny_all", "never"):
            error = {"message": MCP_APPROVAL_DENIED}
        else:
            meta = {
                "callId": call_id,
                "threadId": self.thread.id,
                "sessionId": self.thread.id,
                "x-codex-turn-metadata": {
                    "session_id": self.thread.id,
                    "thread_id": self.thread.id,
                    "turn_id": self.id,
                    "model": self.thread.start_kwargs.get("model"),
                },
            }
            record = {
                "server": server.name,
                "tool": tool,
                "arguments": arguments,
                "meta": meta,
                "status": "started",
            }
            self.client.mcp_calls.append(record)
            timeout = server.config.get("tool_timeout_sec")
            try:
                outcome = await server.session.call_tool(
                    tool,
                    arguments,
                    read_timeout_seconds=(
                        timedelta(seconds=float(timeout)) if timeout else None
                    ),
                    meta=meta,
                )
            except asyncio.CancelledError:
                record["status"] = "cancelled"
                raise
            except Exception as e:  # noqa: BLE001 - transport errors fail the call
                record["status"] = "error"
                error = {"message": f"tool call error: {e}"}
            else:
                record["status"] = "completed"
                content = [c.model_dump(mode="json") for c in outcome.content]
                result = {"content": content}
                if outcome.structuredContent is not None:
                    result["structured_content"] = outcome.structuredContent
                texts = [str(c.get("text")) for c in content if c.get("type") == "text"]
                failed = bool(outcome.isError)
                record["is_error"] = failed

        duration_ms = int((time.monotonic() - started) * 1000)
        done = {**item, "duration_ms": duration_ms}
        if error is not None:
            done.update(status="failed", error=error)
        else:
            done.update(status="failed" if failed else "completed", result=result)
        emit(self._note("ItemCompletedNotification", {"item": done}))

        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": self._frame_output(
                started, result, error, texts, failed or error is not None
            ),
        }

    def _frame_output(
        self,
        started: float,
        result: dict[str, Any] | None,
        error: dict[str, Any] | None,
        texts: list[str],
        failed: bool,
    ) -> Any:
        """Shape the model-facing output the way codex 0.159.2 does."""
        import time

        if error is not None:
            body = str(error.get("message") or "")
        elif not failed and result and result.get("structured_content") is not None:
            body = json.dumps(result["structured_content"], separators=(",", ":"))
        else:
            body = "\n".join(texts)
        if not self.client.wall_time_framing:
            return body
        header = f"Wall time: {time.monotonic() - started:.4f} seconds\nOutput:"
        if failed:
            return [
                {"type": "input_text", "text": header},
                {"type": "input_text", "text": body},
            ]
        return f"{header}\n{body}"


def _normalize_usage(usage: dict[str, Any]) -> dict[str, Any]:
    """Fold Responses ``*_details`` into the flat keys ``_usage_block`` reads."""
    usage = _as_dict(usage)
    flat = dict(usage)
    details = usage.get("input_tokens_details") or {}
    if isinstance(details, dict) and "cached_input_tokens" not in flat:
        flat["cached_input_tokens"] = details.get("cached_tokens") or 0
    details = usage.get("output_tokens_details") or {}
    if isinstance(details, dict) and "reasoning_output_tokens" not in flat:
        flat["reasoning_output_tokens"] = details.get("reasoning_tokens") or 0
    return flat


def mcp_output_body(output: Any) -> str:
    """The payload of a framed ``function_call_output`` (wall-time stripped)."""
    if isinstance(output, list):
        return "\n".join(
            str(part.get("text") or "") for part in output[1:] if isinstance(part, dict)
        )
    text = str(output)
    marker = "\nOutput:\n"
    return text.split(marker, 1)[1] if marker in text else text
