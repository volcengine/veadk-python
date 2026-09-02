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

The agent's ADK tools are deliberately *not* exposed to Codex: they are
advertised to the backend as plain ``function`` tools and executed by the shim
itself in a bounded internal loop (see :class:`TurnToolState`). Codex never sees
them, so the shim — not Codex — owns their conversation history.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import hashlib
import json
import os
import secrets
import threading
import time
import weakref
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

import litellm
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from litellm import exceptions as litellm_exceptions

from veadk.utils.logger import get_logger

try:  # OpenTelemetry is optional; the shim must import without it.
    from opentelemetry import context as otel_context_api
except Exception:  # pragma: no cover - depends on the install extras
    otel_context_api = None  # type: ignore[assignment]

logger = get_logger(__name__)
_TRANSFERRED_STATUS = "transferred"

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

    These are retries of a *failed* attempt, so they multiply HTTP requests but
    not model calls: one charge against ``max_llm_calls`` can cost up to
    ``1 + CODEX_SHIM_NUM_RETRIES`` requests, doubled again if
    :func:`_call_backend_tolerating_reasoning` has to repair the request. See
    ``ShimTurnContext.on_model_call`` for why the budget counts calls rather
    than attempts.
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


def _shim_start_timeout() -> float:
    """Deadline (seconds) for the local server to bind its ephemeral port.

    Without a deadline ``start()`` polls ``server.started`` forever, so an
    environment where uvicorn cannot bind (no loopback, port exhaustion, a
    restricted network namespace) hangs the whole invocation instead of failing
    it. Env-tunable via ``CODEX_SHIM_START_TIMEOUT`` (default 10s).
    """
    try:
        return max(0.5, float(os.getenv("CODEX_SHIM_START_TIMEOUT", "10")))
    except ValueError:
        return 10.0


def _shim_cache_max() -> int:
    """Maximum number of cached shims (one local server + port each).

    The process-wide cache is keyed by backend + credential, so in a
    multi-tenant server a per-tenant key would otherwise allocate an unbounded
    number of servers and ports. Env-tunable via ``CODEX_SHIM_CACHE_MAX``.
    """
    try:
        return max(1, int(os.getenv("CODEX_SHIM_CACHE_MAX", "8")))
    except ValueError:
        return 8


def _shim_reserve_seconds() -> float:
    """Floor on how long a shim handed out by :func:`get_shim` counts as busy.

    ``get_shim`` returns well before the caller can ``register_turn``: the Codex
    runtime first prepares a workspace, reaps stale ones (up to 16 ``rmtree``\ s
    in a worker thread), prepares a ``CODEX_HOME``, syncs skills, and
    builds/resumes its toolsets (which connects MCP servers). Across that whole
    window the shim has no registered turn, so a concurrent ``get_shim`` for a
    different backend could evict it — stopping its server and releasing its
    port — and the turn would then register on a corpse and point Codex at a
    dead URL for its entire duration.

    This value alone cannot close that window, because the window has no bound
    the shim can know: MCP connect timeouts and workspace reaping are the
    caller's business, and any constant is a guess that a slow setup outlives.
    What actually holds the reservation open is the :class:`ShimLease`
    ``get_shim`` returns — the shim keeps only a weak reference to it, so the
    reservation lives exactly as long as the caller's own reference does, for
    any setup duration. This deadline is the *floor* underneath that, for a
    caller that keeps only the URL and drops the lease (:func:`get_shim_url`)
    or that never held one at all.

    Neither half is a caller-released counter, and that is deliberate: a release
    call would have to survive every exit path of an async generator (including
    a consumer abandoning it mid-setup), and one missed release would pin a shim
    in the cache forever. Dropping the last reference to a lease is not a call
    that can be missed — the interpreter always makes it, on every exit path —
    and :meth:`register_turn` consumes the reservation atomically with inserting
    the turn, so the normal path never waits for the floor to expire.
    Env-tunable via ``CODEX_SHIM_RESERVE_SECONDS``; ``0`` disables reservations.
    """
    try:
        return max(0.0, float(os.getenv("CODEX_SHIM_RESERVE_SECONDS", "60")))
    except ValueError:
        return 60.0


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def _openai_error(*, status_code: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"type": error_type, "message": message}},
    )


# Fallback cap on shim-internal tool round-trips per Codex *turn*, used only
# when `register_turn` is called without `max_tool_iterations`. The product
# default is `CodexRuntimeConfig.max_tool_iterations` (32), which the Codex
# runtime always passes explicitly; this value exists so a direct
# `register_turn` caller (tests, embedders) still gets a bounded loop.
_AGENT_TOOL_MAX_ITERS = 8

# Hard ceiling on retained per-turn tool transcript items (function_call +
# function_call_output pairs replayed to the backend). Purely a memory guard:
# the iteration budget already bounds the number of rounds.
_TURN_TRANSCRIPT_MAX_ITEMS = 256

# Grace period for a shim's uvicorn server to drain on stop().
_SHIM_STOP_TIMEOUT = 5.0

# SSE `response.failed` error code used for every terminal shim failure.
#
# Codex classifies a `response.failed` frame by `response.error.code`
# (`codex-rs/codex-api/src/sse/responses.rs`, the `"response.failed"` arm):
# `context_length_exceeded`, `insufficient_quota`, `usage_not_included`,
# `cyber_policy` and `invalid_prompt` map to *fatal* `ApiError` variants, and
# **everything else falls through to `ApiError::Retryable`** — which becomes
# `CodexErr::Stream`, whose `is_retryable()` is true, so Codex re-sends the
# request `stream_max_retries` times with backoff. A descriptive code such as
# `tool_iteration_limit` therefore buys N pointless retries, each one a fresh
# backend call. `invalid_prompt` is the only fatal code that *keeps* our message
# (it maps to `CodexErr::InvalidRequest(message)`); the others discard it. On a
# Codex build without that mapping the behaviour is simply today's retry-then-
# fail, so this is a strict improvement or a no-op, never a regression.
_FATAL_STREAM_ERROR_CODE = "invalid_prompt"


class TurnToolState:
    """Mutable, concurrency-safe per-turn state for the shim's tool loop.

    Two things must outlive a single HTTP request but stay scoped to one Codex
    turn:

    * the **iteration budget** — Codex sends one request per native tool
      round, so a per-request counter let the shim run ``max_tool_iterations``
      backend round-trips *per request* (N x 8 per turn);
    * the **tool transcript** — the ``function_call``/``function_call_output``
      pairs the shim executed itself. Codex never sees those items (they are
      not streamed to it), and Codex rebuilds the whole ``input`` array from
      its own thread on every request, so without replaying them the model
      would see a conversation in which it never called the tool and would
      re-issue the call (re-running its side effects).

    The shim is shared process-wide and serves concurrent turns; a plain
    ``threading.Lock`` is used rather than an ``asyncio`` primitive so the state
    is safe from any thread/event loop (``register_turn`` runs on the caller's
    loop, the handler on the server's).
    """

    __slots__ = (
        "_lock",
        "_transcript",
        "_iterations",
        "_dropped",
        "_error",
        "_anchor_texts",
        "_marker_delivered",
    )

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._transcript: list[dict[str, Any]] = []
        self._iterations = 0
        self._dropped = 0
        self._error: BaseException | None = None
        # Turn identity, latched on the first request this turn serves. `None`
        # means "no request seen yet"; see `identify_request`.
        self._anchor_texts: frozenset[str] | None = None
        self._marker_delivered = False

    @property
    def iterations(self) -> int:
        """Tool round-trips consumed so far in this turn."""
        with self._lock:
            return self._iterations

    @property
    def error(self) -> BaseException | None:
        """Exception that aborted the turn from inside the shim, if any.

        The shim runs on the server's task, so an exception raised here (for
        example ADK's ``LlmCallsLimitExceededError`` from the per-model-call
        budget) cannot propagate to the caller of ``run_async``. It is recorded
        instead, and the runtime re-raises it once the turn ends so the normal
        ADK handling in ``veadk.runner`` still applies.
        """
        with self._lock:
            return self._error

    def record_error(self, error: BaseException) -> None:
        """Remember the first shim-side exception that aborted this turn."""
        with self._lock:
            if self._error is None:
                self._error = error

    @property
    def transcript(self) -> list[dict[str, Any]]:
        """Copy of the executed tool items recorded for this turn."""
        with self._lock:
            return [dict(item) for item in self._transcript]

    def consume_iteration(self, budget: int) -> bool:
        """Reserve one tool round-trip; ``False`` when the turn budget is gone."""
        with self._lock:
            if self._iterations >= budget:
                return False
            self._iterations += 1
            return True

    def identify_request(
        self, marker: str, user_texts: list[str], *, tools_advertised: bool
    ) -> bool:
        """Decide whether this inbound request is the agent's own turn.

        Codex reuses one provider block — and therefore one bearer token — for
        work that is *not* the agent turn: auto/manual compaction
        (``codex-rs/core/src/compact.rs::run_compact_task_inner_impl``, which
        re-sends the whole history plus a summarization instruction with an
        empty ``tools`` list) and code review (``session/review.rs``, which
        clones the parent turn's provider into a *fresh* delegate thread). If
        the shim advertised the agent's ADK tools to those passes, or replayed
        the turn's tool transcript into them, the summarizer could emit a
        ``function_call`` and the shim would execute a real tool a second time.

        Identification is positive, never by exclusion:

        * **Marker path** (production). The runtime embeds this turn's
          ``turn_marker`` in the Codex prompt, so the marker travels in the
          turn's own user message. Compaction *preserves* that message — it
          re-sends the full history — so the marker alone is not enough; the
          request must additionally look like a *sampling* pass rather than a
          summarization one. Two independent signals say so, and either
          suffices: the marker is in the **last** user message (compaction
          appends its instruction after it, so this is false there), or the
          request advertises a non-empty ``tools`` list (compaction always
          sends ``[]``; this is the arm that keeps ADK tools working for the
          rest of a turn *after* a mid-turn compaction has appended its summary
          as a trailing user message).
        * **Anchor path** (fallback). If the marker never arrives on the first
          request — an SDK or Codex version that reshapes the prompt — the shim
          degrades to matching the first request's user-message texts instead of
          failing the turn's tools closed for good. The first request under a
          freshly registered token is by construction the turn's opening
          sampling request: nothing exists yet to compact and no review thread
          can have been spawned. Later requests are then held to the same
          two-signal test as the marker path, because a compaction pass re-sends
          the whole history and so always carries the anchor texts.

        Residual risk, stated rather than hidden: both paths lean on compaction
        sending an empty ``tools`` list. A Codex version that advertises tools
        on a summarization pass would satisfy the ``tools_advertised`` arm and
        be treated as the agent turn. That arm cannot simply be dropped — it is
        what keeps ADK tools working for the rest of a turn after a mid-turn
        compaction appends its summary as a trailing user message.

        Returns:
            bool: ``True`` when tool injection, transcript replay and the
            shim's tool loop may run for this request.
        """
        with self._lock:
            first = self._anchor_texts is None
            if first:
                self._anchor_texts = frozenset(user_texts)
                self._marker_delivered = bool(marker) and any(
                    marker in text for text in user_texts
                )
            anchors = self._anchor_texts or frozenset()
            marker_delivered = self._marker_delivered
        if marker and marker_delivered:
            if not any(marker in text for text in user_texts):
                return False
            return tools_advertised or (bool(user_texts) and marker in user_texts[-1])
        if first:
            return True
        # Anchored on the *last* user message only. Matching any remembered
        # text would admit a compaction pass, which re-sends the whole history
        # and so always carries the turn's opening message. The marker path's
        # `tools_advertised` arm is deliberately not mirrored here: without a
        # marker it would also admit a review pass, which runs in a fresh
        # delegate thread but does advertise tools. Losing ADK tools for the
        # rest of a turn after a mid-turn compaction is a degradation; running
        # a real tool inside a summarization or review pass is a wrong answer
        # with side effects, so this fallback fails closed.
        return bool(user_texts) and user_texts[-1] in anchors

    def marker_was_delivered(self) -> bool:
        """Whether the turn marker was seen on this turn's first request."""
        with self._lock:
            return self._marker_delivered

    def record(self, items: list[dict[str, Any]]) -> None:
        """Append executed ``function_call``/``function_call_output`` items."""
        if not items:
            return
        with self._lock:
            self._transcript.extend(dict(item) for item in items)
            overflow = len(self._transcript) - _TURN_TRANSCRIPT_MAX_ITEMS
            if overflow <= 0:
                return
            # Trim to whole pairs. The cap is even and items are appended two at
            # a time, so an even prefix is pair-aligned today — but that is an
            # accident of the caller, not a property of this method. A lone
            # `function_call_output` at the head would reach the backend as a
            # `tool` message with no preceding `assistant(tool_calls)`, which
            # Ark rejects outright, so the boundary is advanced explicitly until
            # the head is not an orphaned result.
            while overflow < len(self._transcript) and (
                self._transcript[overflow].get("type") == "function_call_output"
            ):
                overflow += 1
            del self._transcript[:overflow]
            self._dropped += overflow

    def replay_items(self, seen_call_ids: set[str]) -> list[dict[str, Any]]:
        """Items to re-append to a fresh request's ``input``.

        Anything whose ``call_id`` is already present in the inbound request is
        skipped, so the pairs can never be duplicated (both items of a pair
        share a ``call_id``, so a pair is always kept or dropped whole).
        """
        with self._lock:
            return [
                dict(item)
                for item in self._transcript
                if item.get("call_id") not in seen_call_ids
            ]


@dataclass(frozen=True)
class ShimTurnContext:
    """Tool routing data for one Codex invocation.

    The dataclass itself stays frozen (routing data is fixed for the turn);
    mutable per-turn state lives in :attr:`state`.
    """

    specs: tuple[dict[str, Any], ...]
    executors: dict[str, Any]
    max_tool_iterations: int
    invocation_id: str = ""
    # Opaque per-turn string the runtime embeds in the Codex prompt so the shim
    # can tell this turn's own sampling requests from Codex-internal passes
    # (compaction, review) that arrive on the same bearer token. See
    # `TurnToolState.identify_request`.
    turn_marker: str = ""
    # Per-turn backend attribution/caching config (Ark prompt caching,
    # veadk-source/version headers, ...). Attached per turn rather than to the
    # shim because one shim instance is shared by every turn on a backend.
    extra_headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)
    # OTel context captured on the invocation's own task, re-attached around
    # tool execution so ADK `execute_tool` spans keep their real parent.
    otel_context: Any = None
    # Charged once per *model call* — one iteration of the shim's tool loop —
    # not once per HTTP request. ADK's `max_llm_calls` budget lives on the
    # InvocationContext, and the real model calls happen here rather than in the
    # runtime, so the runtime hands the counter down. Raising from it aborts the
    # turn (see `TurnToolState.error`).
    #
    # Calls, not attempts, is the deliberate reading and it matches the `adk`
    # arm: ADK charges `increment_llm_call_count` once per `BaseLlmFlow` call
    # while litellm's own `num_retries` re-attempts underneath it, so counting
    # HTTP requests here would make the same agent hit `max_llm_calls` at
    # different points on the two runtimes and break the differential parity the
    # suite asserts. It is also the reading that means something: a retried
    # attempt produced no response and (on a completion-billed backend such as
    # Ark) no charge, so counting it would spend a budget the user is not
    # paying. The fan-out is bounded and worth stating -- one charge admits at
    # most `1 + CODEX_SHIM_NUM_RETRIES` requests, and up to twice that if
    # `_call_backend_tolerating_reasoning` retries the request without Codex's
    # replayed reasoning items (that repair is the *same* logical call: the
    # first attempt was rejected outright, so it never produced a response).
    on_model_call: Callable[[], None] | None = None
    state: TurnToolState = field(default_factory=TurnToolState)


@dataclass
class _Reservation:
    """One outstanding ``get_shim`` -> ``register_turn`` handoff.

    Two independent things keep it alive, and either suffices:

    * ``holder`` — a weak reference to the :class:`ShimLease` handed to the
      caller. While that reference is alive the handoff is still in progress,
      however long the caller's setup takes.
    * ``deadline`` — the ``CODEX_SHIM_RESERVE_SECONDS`` floor, for a caller that
      kept only the shim's URL and dropped the lease.
    """

    deadline: float
    holder: "weakref.ReferenceType[ShimLease]"

    def is_live(self, now: float) -> bool:
        return self.holder() is not None or self.deadline > now


class ShimLease:
    """A shim borrowed from the process-wide cache, plus its reservation.

    :func:`get_shim` returns one of these rather than the bare
    :class:`ResponsesShim`. Every attribute access delegates to the shim, so a
    caller uses it exactly as it used the shim; what the lease adds is
    *liveness*. The shim holds only a weak reference back, so the reservation
    that keeps it un-evictable lasts precisely as long as the caller's own
    reference to this object — the entire ``get_shim`` -> ``register_turn``
    setup, whatever that costs on the day, and not one moment past the frame
    that owns it.

    That is deliberately not a release call: there is nothing to call, so there
    is nothing to miss on an exception, a ``GeneratorExit``, or a consumer that
    abandons the runtime's async generator mid-setup — the interpreter drops the
    reference on every one of those paths. The only way to pin a shim is to keep
    a lease alive on purpose, which is an explicit strong reference and no
    different from keeping the shim itself.

    :meth:`register_turn` is overridden so the turn consumes *this* caller's
    reservation and no one else's; see :meth:`ResponsesShim.register_turn`.
    """

    __slots__ = ("_shim", "_reservation_id", "__weakref__")

    def __init__(self, shim: ResponsesShim) -> None:
        self._shim = shim
        self._reservation_id: int | None = None

    @property
    def shim(self) -> ResponsesShim:
        """The leased shim itself, for a caller that needs it unwrapped."""
        return self._shim

    def register_turn(self, *args: Any, **kwargs: Any) -> str:
        """:meth:`ResponsesShim.register_turn`, consuming this reservation."""
        kwargs.setdefault("reservation", self)
        return self._shim.register_turn(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        # Both slots are assigned in `__init__`, so normal lookup finds them and
        # this is never reached for them on a built object. Guarding anyway:
        # on a half-built one (unpickling, a subclass that skips `__init__`)
        # delegating `_shim` would recurse until the stack ran out.
        if name in ("_shim", "_reservation_id"):
            raise AttributeError(name)
        return getattr(self._shim, name)

    def __repr__(self) -> str:
        return f"ShimLease(url={getattr(self._shim, 'url', None)!r})"


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
        self._loop: asyncio.AbstractEventLoop | None = None
        # Serializes cold start: `start()` polls until the socket is bound, and
        # without the lock two concurrent invocations (serverless cold start
        # with a burst) each build and serve a uvicorn.Server, leaking the
        # loser's socket forever.
        self._start_lock: asyncio.Lock | None = None
        self._start_lock_loop: asyncio.AbstractEventLoop | None = None
        # Invocation-scoped registry. The opaque token is supplied to the Codex
        # subprocess as its provider API key and arrives as a Bearer token, so
        # concurrent turns can never overwrite one another's tools/context.
        self._turns: dict[str, ShimTurnContext] = {}
        # Outstanding `get_shim` handoffs whose turn has not been registered
        # yet, keyed by an id that is never reused so one caller can only ever
        # consume its own; see `_shim_reserve_seconds` and `ShimLease`.
        self._reservations: dict[int, _Reservation] = {}
        self._reservation_seq = 0
        self._turns_lock = threading.Lock()
        self._app = self._build_app()

    @property
    def busy(self) -> bool:
        """True while this shim has a registered turn or a live reservation.

        The reservation half is what makes the ``get_shim`` -> ``register_turn``
        handoff safe: without it the shim reports idle across the caller's whole
        setup window and the LRU can evict (and stop) it out from under a turn
        that is about to register.
        """
        with self._turns_lock:
            if self._turns:
                return True
            self._prune_reservations_locked()
            return bool(self._reservations)

    def _prune_reservations_locked(self) -> None:
        """Drop reservations whose lease is gone *and* whose floor has passed."""
        now = time.monotonic()
        for reservation_id in [
            key
            for key, reservation in self._reservations.items()
            if not reservation.is_live(now)
        ]:
            del self._reservations[reservation_id]

    def reserve(self) -> ShimLease:
        """Borrow this shim, keeping it un-evictable while the caller sets up.

        Returns:
            ShimLease: A handle that delegates every attribute to this shim.
            Hold it for the whole ``get_shim`` -> ``register_turn`` handoff: the
            handle *is* the reservation, and the shim tracks it weakly, so
            letting go of it releases the reservation (no sooner than the
            ``CODEX_SHIM_RESERVE_SECONDS`` floor, which covers a caller that
            keeps only the URL). Registering a turn through the handle consumes
            it immediately.
        """
        lease = ShimLease(self)
        window = _shim_reserve_seconds()
        if window <= 0:
            # Reservations disabled by config. The lease is still returned so
            # callers need no branch of their own; it simply protects nothing.
            return lease
        with self._turns_lock:
            self._prune_reservations_locked()
            self._reservation_seq += 1
            reservation_id = self._reservation_seq
            self._reservations[reservation_id] = _Reservation(
                deadline=time.monotonic() + window, holder=weakref.ref(lease)
            )
            lease._reservation_id = reservation_id
        return lease

    def register_turn(
        self,
        specs: list[dict[str, Any]],
        executors: dict[str, Any],
        *,
        max_tool_iterations: int = _AGENT_TOOL_MAX_ITERS,
        invocation_id: str = "",
        model_extra_config: dict[str, Any] | None = None,
        on_model_call: Callable[[], None] | None = None,
        reservation: ShimLease | None = None,
    ) -> str:
        """Register one invocation's routing state; returns its bearer token.

        Args:
            specs: ADK tool specs advertised to the backend as ``function`` tools.
            executors: ``name -> async (args, call_id) -> str`` tool executors.
            max_tool_iterations: Tool round-trip budget for the whole turn.
            invocation_id: ADK invocation id, for logs.
            model_extra_config: The agent's ``model_extra_config``
                (``extra_headers``/``extra_body``), forwarded to the backend on
                every call of this turn. Defaults to no extra config.
            on_model_call: Charged once per backend model call, before the call
                is made -- per *call*, not per HTTP attempt; see
                ``ShimTurnContext.on_model_call``. Used to enforce ADK's
                ``RunConfig.max_llm_calls``, whose counter lives on the
                invocation the runtime owns. Raising from it aborts the turn;
                the exception is recorded on the turn state and surfaced to
                Codex as a ``429``.
            reservation: The lease :func:`get_shim` handed this caller, whose
                reservation the new turn takes over. Callers that never reserved
                (tests, embedders) leave it unset and consume nothing.
        """
        token = secrets.token_urlsafe(32)
        headers, body = _split_model_extra_config(model_extra_config)
        context = ShimTurnContext(
            specs=tuple(specs or ()),
            executors=dict(executors or {}),
            max_tool_iterations=max(1, max_tool_iterations),
            invocation_id=invocation_id,
            # Generated here, not derived from `token`: the marker is embedded
            # in the model-visible prompt, and the token is the shim's bearer
            # credential.
            turn_marker=f"veadk-turn-{secrets.token_hex(12)}",
            extra_headers=headers,
            extra_body=body,
            # Captured here because register_turn runs on the invocation's own
            # task; the server task's context was snapshotted at shim start.
            otel_context=(
                otel_context_api.get_current() if otel_context_api is not None else None
            ),
            on_model_call=on_model_call,
        )
        with self._turns_lock:
            # Consume *this caller's* reservation -- and only it -- in the same
            # critical section that publishes the turn, so the shim is
            # continuously `busy` across the handoff and can never be evicted
            # between the two. Popping an arbitrary reservation instead would
            # make a caller that never reserved (registering directly, which is
            # supported) cancel the protection of whichever *other* caller is in
            # setup right now, re-opening for that turn exactly the window this
            # exists to close.
            self._prune_reservations_locked()
            reservation_id = getattr(reservation, "_reservation_id", None)
            if reservation_id is not None:
                self._reservations.pop(reservation_id, None)
            self._turns[token] = context
        logger.debug(
            "codex_shim_turn_registered invocation_id=%s tool_count=%d "
            "extra_header_count=%d extra_body_count=%d",
            invocation_id,
            len(executors or {}),
            len(headers),
            len(body),
        )
        return token

    def unregister_turn(self, token: str) -> None:
        """Remove one invocation's routing state."""
        with self._turns_lock:
            context = self._turns.pop(token, None)
        if context is not None:
            logger.debug(
                "codex_shim_turn_unregistered invocation_id=%s tool_iterations=%d",
                context.invocation_id,
                context.state.iterations,
            )

    def _turn(self, token: str) -> ShimTurnContext | None:
        with self._turns_lock:
            return self._turns.get(token)

    def turn_marker(self, token: str) -> str:
        """Opaque marker the caller must embed in this turn's Codex prompt.

        The shim uses it to tell the agent's own sampling requests apart from
        Codex-internal passes that arrive on the same bearer token (compaction,
        review). Returns ``""`` for an unknown token, in which case the shim
        falls back to matching the turn's first request; see
        :meth:`TurnToolState.identify_request`.
        """
        context = self._turn(token)
        return context.turn_marker if context is not None else ""

    def turn_error(self, token: str) -> BaseException | None:
        """Exception raised inside the shim that aborted this turn, if any.

        Read it *before* :meth:`unregister_turn`, which drops the turn state.
        The shim serves requests on the server's task, so an exception from
        ``on_model_call`` cannot reach the runtime by propagation; the runtime
        re-raises whatever is returned here once the Codex turn ends.
        """
        context = self._turn(token)
        return context.state.error if context is not None else None

    def _build_app(self) -> FastAPI:
        app = FastAPI()

        # Registered on `app` by the decorator; the name is never referenced
        # again, and must stay as-is because FastAPI derives the route's
        # OpenAPI operation id from it.
        @app.post("/v1/responses")
        async def responses(request: Request) -> Any:
            token = _bearer_token(request)
            turn_context = self._turn(token)
            if turn_context is None:
                return _openai_error(
                    status_code=401,
                    error_type="authentication_error",
                    message="Unknown or expired Codex invocation token.",
                )
            try:
                body = await request.json()
            except Exception:  # noqa: BLE001 - malformed client payload
                return _openai_error(
                    status_code=400,
                    error_type="invalid_request_error",
                    message="Request body is not valid JSON.",
                )
            if not isinstance(body, dict) or not body.get("model"):
                return _openai_error(
                    status_code=400,
                    error_type="invalid_request_error",
                    message="Request body must be an object with a `model`.",
                )
            model = body["model"]
            stream = bool(body.get("stream", False))

            def _fail(
                *,
                status_code: int,
                error_type: str,
                message: str,
                template: dict[str, Any] | None = None,
            ) -> Any:
                """Terminal shim error, in the shape the client can parse.

                A streaming client cannot consume an HTTP error body: it is
                parsing an event stream, so the status code is all it sees and a
                4xx/5xx is classified purely by Codex's transport rules. It gets
                ``response.failed`` instead, which carries a real message — and
                :data:`_FATAL_STREAM_ERROR_CODE`, so Codex treats the failure as
                terminal rather than replaying the request `stream_max_retries`
                times. ``error_type`` stays the caller's own name; it is what the
                non-streaming JSON body reports.
                """
                if stream:
                    return StreamingResponse(
                        _synth_failed_sse(
                            template or {"model": model},
                            code=_FATAL_STREAM_ERROR_CODE,
                            message=f"{error_type}: {message}",
                        ),
                        media_type="text/event-stream",
                    )
                return _openai_error(
                    status_code=status_code,
                    error_type=error_type,
                    message=message,
                )

            call_kwargs: dict[str, Any] = {
                key: body[key] for key in _PASSTHROUGH_KEYS if key in body
            }
            # Is this the agent's own turn, or a Codex-internal pass (auto
            # compaction / review) on the same bearer token? Only the former may
            # be handed the agent's tools, the turn's tool transcript, or the
            # shim's tool loop; see `TurnToolState.identify_request`.
            inbound_tools = call_kwargs.get("tools")
            is_agent_turn = turn_context.state.identify_request(
                turn_context.turn_marker,
                _user_message_texts(call_kwargs.get("input")),
                tools_advertised=isinstance(inbound_tools, list)
                and bool(inbound_tools),
            )
            # Identification is done; the marker is shim-internal routing data
            # and must not reach the model.
            _strip_turn_marker(call_kwargs.get("input"), turn_context.turn_marker)
            if not is_agent_turn:
                logger.info(
                    "codex_shim_internal_pass_forwarded invocation_id=%s "
                    "detail=request is not this turn's sampling pass; ADK tools "
                    "and tool history are withheld.",
                    turn_context.invocation_id,
                )
            elif turn_context.turn_marker and not (
                turn_context.state.marker_was_delivered()
            ):
                logger.warning(
                    "codex_shim_turn_marker_missing invocation_id=%s "
                    "detail=the turn marker never reached the model request; "
                    "falling back to first-request matching to identify this "
                    "turn's own passes.",
                    turn_context.invocation_id,
                )
            # Drop Codex's own non-`function` tools unconditionally: Ark rejects
            # their schema (e.g. the hosted `web_search`'s `external_web_access`),
            # and that is a backend-compatibility concern rather than part of
            # tool advertisement. Only *adding* the agent's ADK tools — which
            # the shim executes itself, see the tool loop below — is gated on
            # this being the agent turn.
            agent_executors = turn_context.executors if is_agent_turn else {}
            if isinstance(inbound_tools, list):
                kept = [t for t in inbound_tools if t.get("type") == "function"]
                if is_agent_turn:
                    have = {t.get("name") for t in kept}
                    kept.extend(
                        t for t in turn_context.specs if t.get("name") not in have
                    )
                call_kwargs["tools"] = kept
            elif is_agent_turn and turn_context.specs:
                call_kwargs["tools"] = list(turn_context.specs)
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

            # Replay this turn's shim-executed tool history. Codex rebuilds
            # `input` from its own thread on every request and never saw the
            # ADK function_call/function_call_output pairs (they are not
            # streamed to it, precisely so Codex does not try to dispatch tools
            # it does not own), so without this the model would see a
            # conversation in which it never called the tool and would re-issue
            # the call — re-running its side effects. Pairs are appended at the
            # tail (never spliced mid-array) so the chat bridge always sees an
            # assistant(tool_calls) message immediately followed by its tool
            # result, and are skipped when their call_id is already present.
            conversation = call_kwargs.get("input")
            if is_agent_turn and isinstance(conversation, list):
                replay = turn_context.state.replay_items(_call_ids(conversation))
                if replay:
                    conversation.extend(replay)
                    logger.debug(
                        "codex_shim_tool_history_replayed invocation_id=%s items=%d",
                        turn_context.invocation_id,
                        len(replay),
                    )

            call_kwargs.update(
                model=f"openai/{model}",
                api_base=self.api_base,
                api_key=self.api_key,
                custom_llm_provider="openai",
                drop_params=True,
                num_retries=_shim_num_retries(),
                stream=False,
            )
            # Ark prompt caching / attribution headers, mirroring what the
            # `adk` runtime path sends (veadk/agent.py merges
            # DEFAULT_MODEL_EXTRA_CONFIG into model_extra_config).
            if turn_context.extra_headers:
                call_kwargs["extra_headers"] = dict(turn_context.extra_headers)
            if turn_context.extra_body:
                call_kwargs["extra_body"] = dict(turn_context.extra_body)
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
            # The shim resolves the agent's tools itself; with none registered
            # the loop is disabled and the path is unchanged for tool-less runs.
            exec_names = set(agent_executors)
            max_iters = turn_context.max_tool_iterations if agent_executors else 0
            # Codex reads a request's token cost off `response.completed`, and
            # only the final backend response is returned to it. Every
            # intermediate call the tool loop makes is just as billable, so the
            # blocks are summed and the total replaces the last one's usage
            # before either return path.
            usage_acc: dict[str, int] = {}
            resp: dict[str, Any] = {}
            while True:
                # Charge ADK's per-invocation model-call budget here: this is
                # where the calls actually happen — including on a Codex-internal
                # pass, which is just as billable and just as capable of looping,
                # so leaving it uncharged would put a hole in the very budget
                # `max_llm_calls` exists to enforce.
                #
                # Raising aborts the turn. It must be reported the same way every
                # other terminal shim failure is: a streaming client is parsing
                # an event stream and cannot read an HTTP error body, so a bare
                # 429 is classified by transport rules alone and the message is
                # lost. (The abort is *not* dangerous to retry — `on_model_call`
                # raises before the backend call and before any tool runs, so a
                # retry is a pure no-op 429; the cost is latency and log noise,
                # and the fatal `response.failed` code avoids paying it.)
                if turn_context.on_model_call is not None:
                    try:
                        turn_context.on_model_call()
                    except Exception as e:  # noqa: BLE001 - relayed to the runtime
                        turn_context.state.record_error(e)
                        logger.warning(
                            "codex_shim_turn_aborted invocation_id=%s error_type=%s",
                            turn_context.invocation_id,
                            type(e).__name__,
                        )
                        return _fail(
                            status_code=429,
                            error_type="llm_calls_limit",
                            message=str(e),
                            template=_with_total_usage(
                                resp or {"model": model}, usage_acc
                            ),
                        )
                result = await _call_backend_tolerating_reasoning(call_kwargs)
                resp = _to_dict(result)
                _accumulate_usage(usage_acc, resp.get("usage"))
                if max_iters <= 0:
                    break
                conv = call_kwargs.get("input")
                if not isinstance(conv, list):
                    break
                calls = [
                    it
                    for it in (resp.get("output") or [])
                    if it.get("type") == "function_call"
                    and it.get("name") in exec_names
                ]
                if not calls:
                    break

                # Budget is per turn, not per request: Codex issues a fresh
                # request after every native tool call, so a per-request counter
                # allowed max_iters round-trips each time.
                if not turn_context.state.consume_iteration(max_iters):
                    logger.warning(
                        "codex_tool_iteration_limit invocation_id=%s limit=%d",
                        turn_context.invocation_id,
                        max_iters,
                    )
                    return _fail(
                        status_code=409,
                        error_type="tool_iteration_limit",
                        message=(
                            "Codex tool iteration budget exhausted "
                            f"after {max_iters} round(s) this turn."
                        ),
                        template=_with_total_usage(resp, usage_acc),
                    )

                async def _execute(
                    fc: dict[str, Any],
                ) -> tuple[dict[str, Any], str, bool]:
                    cid = fc.get("call_id") or fc.get("id")
                    try:
                        args = json.loads(fc.get("arguments") or "{}")
                    except json.JSONDecodeError as e:
                        return (
                            fc,
                            json.dumps(
                                {
                                    "error": f"Invalid JSON tool arguments: {e}",
                                    "status": "failed",
                                }
                            ),
                            False,
                        )
                    if not isinstance(args, dict):
                        return (
                            fc,
                            json.dumps(
                                {
                                    "error": "Tool arguments must decode to an object.",
                                    "status": "failed",
                                }
                            ),
                            False,
                        )
                    # Re-attach the invocation's OTel context: this coroutine
                    # runs in a task descended from the uvicorn server task,
                    # whose contextvars were snapshotted when the shim first
                    # started, so ADK's `execute_tool` span would otherwise be
                    # an orphan root with a foreign trace_id.
                    with _otel_scope(turn_context.otel_context):
                        out = await agent_executors[fc["name"]](args, str(cid))
                    return fc, out, _is_transfer_output(out)

                # `return_exceptions=True` so a sibling is never left running
                # detached: a bare `gather` re-raises the first failure and
                # abandons the rest, which then keep executing real tools and
                # pushing ADK events into the runtime's queue long after this
                # handler returned — possibly after the done sentinel. Every
                # coroutine is awaited to completion here, then the first
                # failure (if any) is reported.
                settled = await asyncio.gather(
                    *(_execute(fc) for fc in calls), return_exceptions=True
                )
                cancelled = next(
                    (r for r in settled if isinstance(r, asyncio.CancelledError)), None
                )
                if cancelled is not None:
                    raise cancelled
                failure = next(
                    (r for r in settled if isinstance(r, BaseException)), None
                )
                if failure is not None:
                    logger.error(
                        "codex_tool_execution_failed invocation_id=%s error_type=%s",
                        turn_context.invocation_id,
                        type(failure).__name__,
                    )
                    return _fail(
                        status_code=500,
                        error_type="tool_execution_error",
                        message=(
                            f"Tool execution failed: {type(failure).__name__}: "
                            f"{failure}"
                        ),
                        template=_with_total_usage(resp, usage_acc),
                    )
                executed: list[tuple[dict[str, Any], str, bool]] = [
                    r for r in settled if not isinstance(r, BaseException)
                ]
                pairs: list[dict[str, Any]] = []
                transferred = False
                for fc, out, did_transfer in executed:
                    cid = fc.get("call_id") or fc.get("id")
                    transferred = transferred or did_transfer
                    pairs.append(
                        {
                            "type": "function_call",
                            "call_id": cid,
                            "id": fc.get("id") or cid,
                            "name": fc["name"],
                            "arguments": fc.get("arguments") or "{}",
                            "status": "completed",
                        }
                    )
                    pairs.append(
                        {
                            "type": "function_call_output",
                            "call_id": cid,
                            "output": out,
                        }
                    )
                conv.extend(pairs)
                if transferred:
                    resp = _completed_transfer_response(resp)
                    break
                # Remember them for the *next* request of this same turn.
                turn_context.state.record(pairs)

            resp = _with_total_usage(resp, usage_acc)
            if stream:
                return StreamingResponse(
                    _synth_sse(resp), media_type="text/event-stream"
                )
            return JSONResponse(resp)

        # Starlette calls exception handlers as `handler(request, exc)`, so the
        # first parameter must exist even though this handler ignores it.
        async def _on_backend_error(request: Request, exc: Exception) -> JSONResponse:
            status = _error_status(exc)
            detail = self._redact(str(getattr(exc, "message", None) or exc))
            # Record it against the turn so the runtime re-raises after the
            # stream ends. Codex treats a rejected request as the end of its
            # turn and returns whatever it had, so without this the caller sees
            # `status=completed`, a half-finished workspace and a plausible
            # summary -- a silently wrong answer. A 4xx here is terminal: it
            # arrives only after litellm's own retries are exhausted.
            turn_context = self._turn(_bearer_token(request))
            if turn_context is not None:
                turn_context.state.record_error(exc)
            logger.warning(
                "codex_backend_api_error status_code=%s error_type=%s detail=%s",
                status,
                type(exc).__name__,
                detail,
            )
            return JSONResponse(
                status_code=status,
                content={"error": {"type": _error_type(status), "message": detail}},
            )

        # Starlette resolves handlers by walking `type(exc).__mro__`, and none
        # of the errors litellm actually raises inherit `litellm.APIError`
        # (RateLimitError/AuthenticationError/BadRequestError derive from
        # openai.APIStatusError, Timeout from openai.APITimeoutError). Register
        # every root so 400/401/408/429/5xx are mapped instead of escaping to
        # ServerErrorMiddleware as a plain-text 500 that Codex then retries.
        for exc_type in _backend_error_types():
            app.add_exception_handler(exc_type, _on_backend_error)  # type: ignore[arg-type]

        return app

    def _redact(self, message: str) -> str:
        """Strip the backend credential and cap the size of an error message."""
        if self.api_key and self.api_key in message:
            message = message.replace(self.api_key, "***")
        return message if len(message) <= 2000 else message[:2000] + "... [truncated]"

    def usable_on(self, loop: asyncio.AbstractEventLoop) -> bool:
        """Whether this cached shim is still serving on ``loop``.

        A shim started on another (or a closed) event loop — e.g. a serverless
        worker that runs each invocation under its own ``asyncio.run`` — has an
        unreachable server, so the cache must drop it rather than hand back a
        dead URL.
        """
        if self._loop is None:
            return True  # never started
        if self._loop is not loop or loop.is_closed():
            return False
        # A shim whose server task is still running is usable even before
        # `url` is assigned: a concurrent caller that arrives mid-bind must
        # wait on `start()`, not discard (and force_close) the live server.
        return self._task is None or not self._task.done()

    async def start(self) -> str:
        """Start the server on an ephemeral local port and return its URL."""
        if self.url:
            return self.url

        loop = asyncio.get_running_loop()
        # Lazily bound so the lock always belongs to the running loop (no await
        # between the check and the assignment, so this is atomic).
        if self._start_lock is None or self._start_lock_loop is not loop:
            self._start_lock = asyncio.Lock()
            self._start_lock_loop = loop

        async with self._start_lock:
            if self.url:
                return self.url

            # The shim app has no startup/shutdown hooks, so disable the
            # lifespan protocol; otherwise its task lingers and logs a
            # CancelledError traceback when the event loop is torn down at
            # process exit.
            config = uvicorn.Config(
                self._app,
                host="127.0.0.1",
                port=0,
                log_level="warning",
                lifespan="off",
            )
            server = uvicorn.Server(config)
            server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
            task = asyncio.create_task(server.serve())
            self._server = server
            self._task = task
            self._loop = loop

            deadline = time.monotonic() + _shim_start_timeout()
            while not server.started:
                if task.done():
                    # Retrieve the exception so it is never "never retrieved",
                    # and fail the invocation instead of spinning forever.
                    exc = None if task.cancelled() else task.exception()
                    self._reset()
                    raise RuntimeError(
                        "Codex Responses shim server exited before binding"
                    ) from exc
                if time.monotonic() >= deadline:
                    server.should_exit = True
                    task.cancel()
                    with contextlib.suppress(BaseException):
                        await task
                    self._reset()
                    raise TimeoutError(
                        "Codex Responses shim server did not bind within "
                        f"{_shim_start_timeout():.1f}s"
                    )
                await asyncio.sleep(0.02)

            try:
                port = server.servers[0].sockets[0].getsockname()[1]
            except (IndexError, AttributeError) as e:
                server.should_exit = True
                task.cancel()
                with contextlib.suppress(BaseException):
                    await task
                self._reset()
                raise RuntimeError(
                    "Codex Responses shim server reported no bound socket"
                ) from e

            self.url = f"http://127.0.0.1:{port}"
            logger.info("codex_shim_started listen_url=%s", self.url)
            return self.url

    def _reset(self) -> None:
        self._server = None
        self._task = None
        self._loop = None
        self.url = None

    async def stop(self, *, timeout: float = _SHIM_STOP_TIMEOUT) -> None:
        """Ask the server to drain, await its task, and release the port."""
        running = None
        with contextlib.suppress(RuntimeError):
            running = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not running:
            # The server task belongs to another (possibly closed) loop, so it
            # cannot be awaited here; drop it synchronously instead.
            self.force_close()
            return
        server, task = self._server, self._task
        self._reset()
        with self._turns_lock:
            self._turns.clear()
        if server is not None:
            server.should_exit = True
        if task is None:
            return
        try:
            await asyncio.wait_for(task, timeout)
        except asyncio.TimeoutError:
            logger.warning("codex_shim_stop_timeout timeout_seconds=%s", timeout)
            # A drain that overran its grace period leaves uvicorn still holding
            # the listening socket, and `_reset()` has already dropped the
            # instance attributes, so nothing would ever close it again: the
            # port stays bound for the life of the process. The local `server`
            # and `task` were captured before the reset, so the sockets can
            # still be closed and the task cancelled here.
            for bound in getattr(server, "servers", None) or ():
                with contextlib.suppress(Exception):
                    bound.close()
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - shutdown must not raise
            logger.warning("codex_shim_stop_failed error_type=%s", type(e).__name__)
        else:
            logger.info("codex_shim_stopped")

    def force_close(self) -> None:
        """Best-effort synchronous teardown (no running loop required)."""
        server, task = self._server, self._task
        self._reset()
        with self._turns_lock:
            self._turns.clear()
        if server is not None:
            server.should_exit = True
            for bound in getattr(server, "servers", None) or ():
                with contextlib.suppress(Exception):
                    bound.close()
        if task is not None:
            with contextlib.suppress(Exception):
                if task.done():
                    if not task.cancelled():
                        task.exception()  # mark as retrieved
                else:
                    task.cancel()


def _looks_like_reasoning_rejection(exc: BaseException) -> bool:
    """Whether a backend error is "this model does not accept reasoning items"."""
    text = str(getattr(exc, "message", None) or exc).lower()
    return "reasoning" in text and (
        "not supported" in text or "unsupported" in text or "invalid" in text
    )


async def _call_backend_tolerating_reasoning(call_kwargs: dict[str, Any]) -> Any:
    """Call the backend, retrying once without Codex's replayed reasoning items.

    After its first tool round Codex replays its own ``reasoning`` items in the
    request ``input``. Some backends refuse them per-model -- Ark answers
    ``InvalidParameter: input[N].reasoning ... not supported for model`` for
    ``doubao-seed-1-6``, while accepting them for other models -- and the
    rejection lands mid-investigation, so the model family silently became
    unusable with this runtime rather than merely degraded.

    Reasoning items are dropped only in response to that specific refusal, never
    pre-emptively: for a backend that accepts them they carry the chain of
    thought across tool rounds, and stripping them unconditionally would trade a
    hard failure on a few models for quieter, worse answers on the rest.
    """
    try:
        return await litellm.aresponses(**call_kwargs)
    except Exception as e:  # noqa: BLE001 - re-raised unless it is this one case
        conversation = call_kwargs.get("input")
        if not _looks_like_reasoning_rejection(e) or not isinstance(conversation, list):
            raise
        kept = [
            item
            for item in conversation
            if not (isinstance(item, dict) and item.get("type") == "reasoning")
        ]
        if len(kept) == len(conversation):
            raise
        logger.info(
            "codex_backend_reasoning_items_dropped removed=%d",
            len(conversation) - len(kept),
        )
        return await litellm.aresponses(**{**call_kwargs, "input": kept})


#: ``extra_body`` keys that the Responses transport cannot carry, so they are
#: dropped rather than forwarded. Ark rejects prompt caching when the request
#: also has an ``instructions`` field ("caching is not supported for
#: instructions"), and Codex *always* sends ``instructions`` -- so forwarding
#: VeADK's default ``caching`` block 400s every single turn. ``expire_at`` only
#: qualifies the cache entry, so it goes with it. Everything else in
#: ``extra_body`` is forwarded untouched.
_BODY_KEYS_UNSUPPORTED_ON_RESPONSES = ("caching", "expire_at")


def _split_model_extra_config(
    model_extra_config: dict[str, Any] | None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Normalize an agent ``model_extra_config`` into header/body dicts.

    Headers are forwarded in full -- they carry VeADK's Ark attribution and
    encryption defaults. Body keys the Responses transport cannot support are
    filtered; see :data:`_BODY_KEYS_UNSUPPORTED_ON_RESPONSES`.
    """
    config = model_extra_config if isinstance(model_extra_config, dict) else {}
    raw_headers = config.get("extra_headers")
    raw_body = config.get("extra_body")
    # The `isinstance` check has to guard the *iteration*, not each item: a
    # comprehension evaluates `.items()` before it filters, so a truthy
    # non-dict `extra_headers` (a list of pairs, say) raised `AttributeError`
    # inside `register_turn` and failed the turn outright. `extra_body` below is
    # the shape to match.
    headers = (
        {str(k): str(v) for k, v in raw_headers.items() if v is not None}
        if isinstance(raw_headers, dict)
        else {}
    )
    body = dict(raw_body) if isinstance(raw_body, dict) else {}
    dropped = [key for key in _BODY_KEYS_UNSUPPORTED_ON_RESPONSES if key in body]
    for key in dropped:
        body.pop(key, None)
    if dropped:
        logger.debug(
            "codex_shim_extra_body_filtered keys=%s", ",".join(sorted(dropped))
        )
    return headers, body


def _strip_turn_marker(items: Any, marker: str) -> int:
    """Remove the shim's turn marker from a request's user messages, in place.

    The marker only has to survive the round trip *through Codex* — it is how
    the shim recognises this turn's own sampling passes. The model must never
    see it: it is routing metadata, it would differ from what the ADK runtime
    sends for the identical agent (the differential parity suite asserts the two
    arms send the same prompt), and a model that echoes it would corrupt the
    answer. Codex keeps the marker in its own history either way, so stripping
    here costs nothing.

    Args:
        items (Any): The request's ``input`` array; non-lists are ignored.
        marker (str): The turn marker to remove.

    Returns:
        int: How many message parts were rewritten.
    """
    if not marker or not isinstance(items, list):
        return 0
    tag = f"<veadk_turn>{marker}</veadk_turn>"
    stripped = 0
    for item in items:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            if tag in content:
                item["content"] = content.replace(tag, "").rstrip()
                stripped += 1
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and tag in text:
                part["text"] = text.replace(tag, "").rstrip()
                stripped += 1
    return stripped


def _user_message_texts(items: Any) -> list[str]:
    """Text of every ``user``-role message in a request's ``input``, in order.

    Used to identify the turn (see :meth:`TurnToolState.identify_request`).
    Codex sends message content as a list of parts, but a hand-built request may
    use a bare string, so both are accepted; non-message items (``reasoning``,
    ``function_call``, ``function_call_output``) and the ``developer``-role
    initial-context bundle are ignored.
    """
    texts: list[str] = []
    if not isinstance(items, list):
        return texts
    for item in items:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        if item.get("type") not in (None, "message"):
            continue
        content = item.get("content")
        if isinstance(content, str):
            texts.append(content)
            continue
        if not isinstance(content, list):
            continue
        texts.append(
            "\n".join(
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict)
            )
        )
    return texts


def _call_ids(items: list[Any]) -> set[str]:
    """Collect the call/item ids already present in a request's ``input``."""
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("call_id", "id"):
            value = item.get(key)
            if isinstance(value, str) and value:
                seen.add(value)
    return seen


@contextlib.contextmanager
def _otel_scope(context: Any):
    """Attach ``context`` for the duration of the block, if OTel is available."""
    # Bind the optional module to a local so `attach` and `detach` are paired
    # against the same non-None reference. `otel_context_api` is None on an
    # install without OpenTelemetry, and a guard on the module global cannot be
    # carried across the `yield` - neither by a reader nor by a type checker.
    api = otel_context_api
    token = None
    if api is not None and context is not None:
        try:
            token = api.attach(context)
        except Exception:  # noqa: BLE001 - tracing must never break a tool
            token = None
    try:
        yield
    finally:
        if api is not None and token is not None:
            with contextlib.suppress(Exception):
                api.detach(token)


def _backend_error_types() -> tuple[type[Exception], ...]:
    """Exception classes that must map to OpenAI-shaped error JSON.

    Verified against the installed litellm/openai: the MRO of the errors that
    actually occur is e.g.
    ``RateLimitError -> openai.RateLimitError -> openai.APIStatusError ->
    openai.APIError -> openai.OpenAIError``, so ``litellm.exceptions.APIError``
    (a sibling branch) is never found by Starlette's MRO walk.
    ``openai.OpenAIError`` is the single common ancestor; the explicit litellm
    names keep the mapping working if ``openai`` is not importable, and
    ``BudgetExceededError`` derives straight from ``Exception``.
    """
    candidates: list[type[Exception]] = []
    try:
        from openai import OpenAIError as _OpenAIError

        candidates.append(_OpenAIError)
    except Exception:  # noqa: BLE001 - openai is optional at import time
        pass
    for name in (
        "OpenAIError",
        "APIError",
        "APIConnectionError",
        "Timeout",
        "RateLimitError",
        "AuthenticationError",
        "PermissionDeniedError",
        "NotFoundError",
        "BadRequestError",
        "UnprocessableEntityError",
        "InternalServerError",
        "ServiceUnavailableError",
        "APIResponseValidationError",
        "BudgetExceededError",
    ):
        candidate = getattr(litellm_exceptions, name, None)
        if isinstance(candidate, type) and issubclass(candidate, Exception):
            candidates.append(candidate)
    unique: list[type[Exception]] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return tuple(unique)


def _error_status(exc: Exception) -> int:
    """Best-effort HTTP status for a backend exception.

    Codex retries 429/5xx and surfaces 4xx, so preserving the backend's status
    keeps its retry policy correct.
    """
    status = getattr(exc, "status_code", None)
    try:
        status = int(status)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 500
    return status if 400 <= status <= 599 else 500


def _error_type(status: int) -> str:
    """Map an HTTP status code to an error ``type`` string."""
    return {
        400: "invalid_request_error",
        401: "authentication_error",
        403: "permission_error",
        404: "not_found_error",
        408: "timeout_error",
        422: "invalid_request_error",
        429: "rate_limit_error",
        503: "overloaded_error",
    }.get(status, "api_error")


def _to_dict(obj: Any) -> dict[str, Any]:
    """Normalize a litellm Responses object into a plain dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return dict(obj)


def _is_transfer_output(value: str) -> bool:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("status") == _TRANSFERRED_STATUS


def _completed_transfer_response(resp: dict[str, Any]) -> dict[str, Any]:
    """Return a minimal completed response after VeADK handled a transfer."""

    completed = {
        "id": resp.get("id") or "resp_transfer_complete",
        "object": resp.get("object") or "response",
        "created_at": resp.get("created_at") or int(time.time()),
        "model": resp.get("model") or "model",
        "status": "completed",
        "output": [
            {
                "id": "msg_transfer_complete",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": ""}],
            }
        ],
    }
    if "usage" in resp:
        completed["usage"] = resp["usage"]
    return completed


# Usage counters summed across a turn's backend calls. The nested detail fields
# are addressed by their parent so a caller need not know the wire shape.
_USAGE_TOP_KEYS = ("input_tokens", "output_tokens", "total_tokens")
_USAGE_DETAIL_KEYS = (
    ("input_tokens_details", "cached_tokens"),
    ("output_tokens_details", "reasoning_tokens"),
)


def _accumulate_usage(acc: dict[str, int], usage: Any) -> None:
    """Add one backend response's token usage into ``acc``.

    The shim's tool loop calls the backend once per round but returns only the
    final response, so without this every intermediate call's cost is dropped:
    a turn billed for N calls would report the N-th call alone. Missing or
    malformed blocks are ignored rather than raised on — usage is accounting,
    and it must never fail a turn.
    """
    if not isinstance(usage, dict):
        return
    for key in _USAGE_TOP_KEYS:
        value = usage.get(key)
        if isinstance(value, (int, float)):
            acc[key] = acc.get(key, 0) + int(value)
    for parent, key in _USAGE_DETAIL_KEYS:
        detail = usage.get(parent)
        if not isinstance(detail, dict):
            continue
        value = detail.get(key)
        if isinstance(value, (int, float)):
            acc[f"{parent}.{key}"] = acc.get(f"{parent}.{key}", 0) + int(value)


def _with_total_usage(resp: dict[str, Any], acc: dict[str, int]) -> dict[str, Any]:
    """Return ``resp`` with its ``usage`` replaced by the turn's running total.

    Summing ``input_tokens`` counts the re-sent context once per call, which is
    what the backend actually bills for an agentic loop.
    """
    if not acc:
        return resp
    usage: dict[str, Any] = dict(resp.get("usage") or {})
    for key in _USAGE_TOP_KEYS:
        if key in acc:
            usage[key] = acc[key]
    if "total_tokens" not in acc:
        usage["total_tokens"] = acc.get("input_tokens", 0) + acc.get("output_tokens", 0)
    for parent, key in _USAGE_DETAIL_KEYS:
        total = acc.get(f"{parent}.{key}")
        if total is None:
            continue
        detail = dict(usage.get(parent) or {})
        detail[key] = total
        usage[parent] = detail
    return {**resp, "usage": usage}


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

    Note that the shim's own ADK ``function_call``/``function_call_output``
    pairs are deliberately *not* streamed here: a ``function_call`` item is
    Codex's "execute this" signal, and Codex has no such tool registered, so it
    would answer with an ``unsupported call`` output and poison the thread. The
    pairs are replayed to the backend instead (see :class:`TurnToolState`).
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


async def _synth_failed_sse(
    template: dict[str, Any], *, code: str, message: str
) -> AsyncIterator[bytes]:
    """Synthesize a terminal ``response.failed`` stream.

    ``response.failed`` (with ``response.error.{code,message}``) is a
    recognized Codex error path, so the failure is reported once with a real
    message instead of an HTTP 500 that Codex would retry — which would re-run
    every tool side effect the request already produced.
    """
    seq = 0

    def ev(payload: dict[str, Any]) -> bytes:
        nonlocal seq
        payload["sequence_number"] = seq
        seq += 1
        return _sse(payload)

    base = {
        key: value
        for key, value in (template or {}).items()
        if key not in ("output", "status", "error")
    }
    base.setdefault("id", "resp_veadk_shim_error")
    base.setdefault("object", "response")
    yield ev(
        {
            "type": "response.created",
            "response": {**base, "status": "in_progress", "output": []},
        }
    )
    yield ev(
        {
            "type": "response.failed",
            "response": {
                **base,
                "status": "failed",
                "output": [],
                "error": {"code": code, "message": message},
            },
        }
    )


# Reuse one shim per (api_base, credential fingerprint) for the lifetime of the
# process. LRU-ordered and capped so a multi-tenant server cannot allocate an
# unbounded number of servers/ports, and keyed by a hash so raw API keys are not
# retained in a module global.
_SHIMS: "OrderedDict[tuple[str, str], ResponsesShim]" = OrderedDict()

# Guards every read-modify-write of `_SHIMS` and `_RETIRED`.
#
# A `threading.Lock` rather than an asyncio primitive, and not merely "no awaits
# in this block": that argument only makes a block atomic against other
# coroutines *on one event loop*, and this cache is explicitly designed to be
# shared across them -- `ResponsesShim.usable_on` exists for "a serverless
# worker that runs each invocation under its own `asyncio.run`". Two such
# workers on two threads both missed the cache and both built a `ResponsesShim`;
# the second `_SHIMS[key] = shim` orphaned the first, which then bound a port in
# `start()` while being reachable from nothing -- not `_evict_idle_shims`, not
# `shutdown_shims`, not `_close_shims_at_exit` -- so the socket leaked for the
# life of the process. `TurnToolState` and the reservations were already
# thread-safe; the cache holding them was not.
#
# Held only across dict operations, never across an await: a coroutine that
# blocked here while holding it would deadlock its own loop.
_SHIMS_LOCK = threading.Lock()

# Shims removed from `_SHIMS` while still busy. A shim whose event loop no
# longer matches the caller's must leave the cache, but force-closing one that
# another loop's turn is still using would kill that turn, and simply dropping
# the reference would leak its port exactly the way an orphan does. They are
# parked here instead -- still serving, still reachable -- and closed by the
# next sweep once they go idle, or by shutdown/atexit.
_RETIRED: "list[ResponsesShim]" = []


def _credential_fingerprint(api_key: str) -> str:
    if not api_key:
        return ""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:32]


async def get_shim(api_base: str, api_key: str) -> ShimLease:
    """Return a started shim for the given backend, creating it if needed.

    Returns:
        ShimLease: The shim, wrapped in the reservation that keeps it out of the
        LRU's reach. Every attribute delegates to the shim, so it is used the
        same way — but **hold the lease** for as long as the shim is needed:
        letting go of it is what tells the cache the handoff is over. See
        :class:`ShimLease`.
    """
    key = (api_base, _credential_fingerprint(api_key))
    loop = asyncio.get_running_loop()
    stale: ResponsesShim | None = None
    retired: ResponsesShim | None = None
    with _SHIMS_LOCK:
        shim = _SHIMS.get(key)
        if shim is not None and not shim.usable_on(loop):
            del _SHIMS[key]
            # Busy means another loop's turn is being served on it right now,
            # so it is closed later (`_RETIRED`) rather than under that turn.
            if shim.busy:
                _RETIRED.append(shim)
                retired = shim
            else:
                stale = shim
            shim = None
        if shim is None:
            shim = ResponsesShim(api_base=api_base, api_key=api_key)
            _SHIMS[key] = shim
        _SHIMS.move_to_end(key)
        # Reserved inside the same critical section that publishes the shim, so
        # it is `busy` from the instant it becomes reachable: an `await` follows
        # immediately below, and until this point a concurrent `get_shim` could
        # evict a brand-new shim before its owner had ever been protected.
        lease = shim.reserve()
    if stale is not None or retired is not None:
        logger.warning(
            "codex_shim_discarded reason=event_loop_changed_or_closed retired=%s",
            retired is not None,
        )
    if stale is not None:
        stale.force_close()

    try:
        await shim.start()
    except BaseException:
        with _SHIMS_LOCK:
            if _SHIMS.get(key) is shim:
                del _SHIMS[key]
        shim.force_close()
        raise

    await _evict_idle_shims()
    return lease


async def _evict_idle_shims() -> None:
    """Drop least-recently-used shims that have no registered turn."""
    with _SHIMS_LOCK:
        idle_retired = [shim for shim in _RETIRED if not shim.busy]
        for shim in idle_retired:
            _RETIRED.remove(shim)
    for shim in idle_retired:
        await shim.stop()

    limit = _shim_cache_max()
    while True:
        with _SHIMS_LOCK:
            if len(_SHIMS) <= limit:
                return
            # The `busy` test and the pop have to be one critical section: a
            # shim that reads idle here must still be idle when it is removed,
            # or a turn registering in between is stopped out from under.
            victim_key = next((k for k, s in _SHIMS.items() if not s.busy), None)
            if victim_key is None:
                logger.warning(
                    "codex_shim_cache_over_limit size=%d limit=%d reason=all_busy",
                    len(_SHIMS),
                    limit,
                )
                return
            victim = _SHIMS.pop(victim_key)
            size = len(_SHIMS)
        logger.info("codex_shim_evicted cache_size=%d limit=%d", size, limit)
        await victim.stop()


async def shutdown_shims() -> None:
    """Stop every cached shim. Call on worker/app shutdown for a clean drain."""
    while True:
        with _SHIMS_LOCK:
            if _SHIMS:
                _, shim = _SHIMS.popitem()
            elif _RETIRED:
                shim = _RETIRED.pop()
            else:
                return
        await shim.stop()


# Registered with `atexit` by the decorator; nothing calls it by name, and the
# registration side effect is the entire point, so it must not be deleted.
@atexit.register
def _close_shims_at_exit() -> None:
    """Last-resort teardown: release listening sockets at interpreter exit."""
    # Best-effort on the lock: at exit a daemon thread may still hold it, and
    # blocking forever here would hang the interpreter on the way out. Releasing
    # the sockets matters more than the critical section, so a failed acquire
    # falls through and drains anyway.
    acquired = _SHIMS_LOCK.acquire(timeout=1.0)
    try:
        while _SHIMS or _RETIRED:
            with contextlib.suppress(Exception):
                shim = _SHIMS.popitem()[1] if _SHIMS else _RETIRED.pop()
                shim.force_close()
    finally:
        if acquired:
            _SHIMS_LOCK.release()


async def get_shim_url(api_base: str, api_key: str) -> str:
    """Return a started shim URL for the given backend, creating it if needed.

    The lease is dropped on return, so the shim is protected only by the
    ``CODEX_SHIM_RESERVE_SECONDS`` floor. Callers that need the shim for a whole
    turn should use :func:`get_shim` and keep the lease.
    """
    lease = await get_shim(api_base, api_key)
    return lease.url or ""
