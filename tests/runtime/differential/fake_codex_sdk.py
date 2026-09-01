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
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tomllib
import types as pytypes
from typing import Any, AsyncIterator

import httpx

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

    class Personality(_StrEnum):
        none = "none"
        friendly = "friendly"
        pragmatic = "pragmatic"

    class ReasoningEffort(_StrEnum):
        minimal = "minimal"
        low = "low"
        medium = "medium"
        high = "high"
        xhigh = "xhigh"

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
    generated = pytypes.ModuleType("openai_codex.generated")
    generated.__veadk_stub__ = True  # type: ignore[attr-defined]
    v2_all = pytypes.ModuleType("openai_codex.generated.v2_all")
    v2_all.__veadk_stub__ = True  # type: ignore[attr-defined]

    for name, value in (
        ("ApprovalMode", ApprovalMode),
        ("Sandbox", Sandbox),
        ("CodexConfig", CodexConfig),
        ("TextInput", TextInput),
        ("ImageInput", ImageInput),
        ("LocalImageInput", LocalImageInput),
        ("MentionInput", MentionInput),
        ("AsyncCodex", ShimDrivingCodex),
    ):
        setattr(module, name, value)
    for name, value in (
        ("Personality", Personality),
        ("ReasoningEffort", ReasoningEffort),
    ):
        setattr(v2_all, name, value)
    for name in _NOTIFICATION_NAMES:
        setattr(v2_all, name, _shim_notification_class(name))
    module.generated = generated  # type: ignore[attr-defined]
    generated.v2_all = v2_all  # type: ignore[attr-defined]

    sys.modules["openai_codex"] = module
    sys.modules["openai_codex.generated"] = generated
    sys.modules["openai_codex.generated.v2_all"] = v2_all
    return True


_NOTIFICATION_NAMES = (
    "TurnStartedNotification",
    "TurnCompletedNotification",
    "ItemStartedNotification",
    "ItemCompletedNotification",
    "AgentMessageDeltaNotification",
    "ReasoningSummaryTextDeltaNotification",
    "ThreadTokenUsageUpdatedNotification",
    "ErrorNotification",
)

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
        value = getattr(item, "value", None)
        if isinstance(value, str) and type(item).__name__ == "TextInput":
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
            _Note(
                make_notification(
                    "ItemStartedNotification",
                    {
                        "turn_id": turn_id,
                        "item": {"id": item_id, "type": "agentMessage", "text": ""},
                    },
                )
            ),
            _Note(
                make_notification(
                    "AgentMessageDeltaNotification",
                    {"turn_id": turn_id, "item_id": item_id, "delta": text},
                )
            ),
            _Note(
                make_notification(
                    "ItemCompletedNotification",
                    {"turn_id": turn_id, "item": thread_item},
                )
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
            _Note(
                make_notification(
                    "ItemStartedNotification",
                    {
                        "turn_id": turn_id,
                        "item": {"id": item_id, "type": "reasoning", "summary": []},
                    },
                )
            )
        ]
        for entry in summary:
            notes.append(
                _Note(
                    make_notification(
                        "ReasoningSummaryTextDeltaNotification",
                        {
                            "turn_id": turn_id,
                            "item_id": item_id,
                            "delta": entry["text"],
                        },
                    )
                )
            )
        notes.append(
            _Note(
                make_notification(
                    "ItemCompletedNotification",
                    {"turn_id": turn_id, "item": thread_item},
                )
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
            _Note(
                make_notification(
                    "ItemStartedNotification",
                    {"turn_id": turn_id, "item": {**thread_item, "status": None}},
                )
            ),
            _Note(
                make_notification(
                    "ItemCompletedNotification",
                    {"turn_id": turn_id, "item": thread_item},
                )
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
