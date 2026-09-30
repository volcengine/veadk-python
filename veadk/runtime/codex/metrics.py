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

"""Business metrics for ``runtime="codex"``.

Like :mod:`veadk.tracing.telemetry.portal_metrics`, this module only creates
instruments on the *global* OpenTelemetry ``MeterProvider``; it never installs
a provider, reader, exporter or credentials. With no provider configured the
OTel API hands out proxy/no-op instruments, so every helper costs a dict
lookup and a no-op call. Instruments obtained before an application installs
its provider follow it once installed (OTel proxy semantics).

Instruments (meter name ``veadk.runtime.codex``):

| Name | Type | Unit | Attributes | Meaning |
|---|---|---|---|---|
| `veadk.codex.thread.resume` | Counter | `1` | `outcome`: resumed, new_thread, instructions_changed, retried_then_resumed, fallback_after_error, store_error, other | How each invocation obtained its Codex thread. |
| `veadk.codex.thread.save` | Counter | `1` | `outcome`: saved, conflict, failed, skipped, cancelled, too_large, other | Result of persisting the thread after a turn. |
| `veadk.codex.turn` | Counter | `1` | `status`: completed, failed, cancelled, transferred, timeout, other; `transport`: direct, shim, other | Finished Codex turns. |
| `veadk.codex.turn.duration` | Histogram | `s` | same as `veadk.codex.turn` | Wall-clock duration of a finished turn. |
| `veadk.codex.turn.startup` | Histogram | `s` | `transport` | Invocation start until the Codex turn has started. |
| `veadk.codex.turn.tokens` | Counter | `{token}` | `transport`; `kind`: input, output, cached_input, reasoning_output | Tokens from Codex's `total` usage for the turn. |

Cardinality: every attribute value is validated against the fixed sets above;
anything else is recorded as ``"other"``. No user, session, thread,
invocation or request identifiers are ever attached. (No model attribute is
emitted; if one is added later it must be the operator-configured model name,
never a value derived from user input.)

All ``record_*`` helpers are best effort: they swallow every exception so a
misbehaving metrics SDK can never fail a turn.
"""

from __future__ import annotations

import threading
from typing import Any, Mapping, Optional

from opentelemetry import metrics as metrics_api

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

METER_NAME = "veadk.runtime.codex"

THREAD_RESUME = "veadk.codex.thread.resume"
THREAD_SAVE = "veadk.codex.thread.save"
TURN = "veadk.codex.turn"
TURN_DURATION = "veadk.codex.turn.duration"
TURN_STARTUP = "veadk.codex.turn.startup"
TURN_TOKENS = "veadk.codex.turn.tokens"

OTHER = "other"

RESUME_OUTCOMES = frozenset(
    {
        "resumed",
        "new_thread",
        "instructions_changed",
        "retried_then_resumed",
        "fallback_after_error",
        "store_error",
    }
)
SAVE_OUTCOMES = frozenset(
    {"saved", "conflict", "failed", "skipped", "cancelled", "too_large"}
)
TURN_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "transferred", "timeout"}
)
TRANSPORTS = frozenset({"direct", "shim"})

# Codex ``total`` usage key -> ``kind`` attribute value.
_TOKEN_KINDS = {
    "input_tokens": "input",
    "output_tokens": "output",
    "cached_input_tokens": "cached_input",
    "reasoning_output_tokens": "reasoning_output",
}

# Turns run from seconds to tens of minutes.
_TURN_DURATION_BUCKETS = [
    0.5,
    1,
    2.5,
    5,
    10,
    20,
    40,
    80,
    160,
    320,
    640,
    1280,
    2560,
]
_STARTUP_BUCKETS = [0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64]


class _Instruments:
    def __init__(self, meter: Any) -> None:
        self.resume = meter.create_counter(
            name=THREAD_RESUME,
            unit="1",
            description="How a Codex invocation obtained its thread",
        )
        self.save = meter.create_counter(
            name=THREAD_SAVE,
            unit="1",
            description="Outcome of persisting a Codex thread after a turn",
        )
        self.turn = meter.create_counter(
            name=TURN, unit="1", description="Finished Codex turns"
        )
        self.turn_duration = meter.create_histogram(
            name=TURN_DURATION,
            unit="s",
            description="Wall-clock duration of a Codex turn",
            explicit_bucket_boundaries_advisory=_TURN_DURATION_BUCKETS,
        )
        self.startup = meter.create_histogram(
            name=TURN_STARTUP,
            unit="s",
            description="Time from invocation start until the Codex turn started",
            explicit_bucket_boundaries_advisory=_STARTUP_BUCKETS,
        )
        self.tokens = meter.create_counter(
            name=TURN_TOKENS,
            unit="{token}",
            description="Tokens reported by Codex turn usage",
        )


_lock = threading.Lock()
_instruments: Optional[_Instruments] = None
_meter_override: Optional[Any] = None


def _get() -> Optional[_Instruments]:
    """Return the process-wide instruments, creating them on first use."""
    global _instruments
    inst = _instruments
    if inst is not None:
        return inst
    with _lock:
        if _instruments is None:
            meter = _meter_override or metrics_api.get_meter(METER_NAME)
            _instruments = _Instruments(meter)
        return _instruments


def set_meter_for_testing(meter: Optional[Any]) -> None:
    """Route instruments to ``meter`` (``None`` restores the global provider).

    Drops cached instruments so the next record re-creates them. Test hook
    only; production code relies on the global ``MeterProvider``.
    """
    global _instruments, _meter_override
    with _lock:
        _meter_override = meter
        _instruments = None


def _bounded(value: Any, allowed: frozenset) -> str:
    return value if isinstance(value, str) and value in allowed else OTHER


def _safe(what: str, fn) -> None:
    try:
        inst = _get()
        if inst is not None:
            fn(inst)
    except Exception as exc:  # metrics are best effort
        logger.debug(f"Codex metric {what} not recorded: {exc!r}")


def _seconds(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if value != value or value < 0 or value == float("inf"):
        return None
    return value


def record_resume(outcome: str) -> None:
    """Count how an invocation obtained its Codex thread."""
    attrs = {"outcome": _bounded(outcome, RESUME_OUTCOMES)}
    _safe(THREAD_RESUME, lambda i: i.resume.add(1, attrs))


def record_save(outcome: str) -> None:
    """Count the outcome of persisting a Codex thread."""
    attrs = {"outcome": _bounded(outcome, SAVE_OUTCOMES)}
    _safe(THREAD_SAVE, lambda i: i.save.add(1, attrs))


def record_turn(status: str, transport: str, duration_s: Optional[float]) -> None:
    """Count a finished turn and record its duration (skipped if invalid)."""
    attrs = {
        "status": _bounded(status, TURN_STATUSES),
        "transport": _bounded(transport, TRANSPORTS),
    }
    duration = _seconds(duration_s)

    def _record(i: _Instruments) -> None:
        i.turn.add(1, attrs)
        if duration is not None:
            i.turn_duration.record(duration, attrs)

    _safe(TURN, _record)


def record_startup(transport: str, seconds: Optional[float]) -> None:
    """Record time from invocation start until the Codex turn started."""
    value = _seconds(seconds)
    if value is None:
        return
    attrs = {"transport": _bounded(transport, TRANSPORTS)}
    _safe(TURN_STARTUP, lambda i: i.startup.record(value, attrs))


def record_tokens(transport: str, usage: Optional[Mapping[str, Any]]) -> None:
    """Add token counts from a Codex ``total``-style usage dict.

    Recognised keys: ``input_tokens``, ``output_tokens``,
    ``cached_input_tokens``, ``reasoning_output_tokens``. Missing, non-int,
    bool or negative values are ignored; unknown keys never become attributes.
    """
    if not isinstance(usage, Mapping):
        return
    bounded_transport = _bounded(transport, TRANSPORTS)
    points = []
    for key, kind in _TOKEN_KINDS.items():
        value = usage.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            continue
        points.append((value, {"transport": bounded_transport, "kind": kind}))
    if not points:
        return

    def _record(i: _Instruments) -> None:
        for value, attrs in points:
            i.tokens.add(value, attrs)

    _safe(TURN_TOKENS, _record)


__all__ = [
    "METER_NAME",
    "OTHER",
    "RESUME_OUTCOMES",
    "SAVE_OUTCOMES",
    "THREAD_RESUME",
    "THREAD_SAVE",
    "TRANSPORTS",
    "TURN",
    "TURN_DURATION",
    "TURN_STARTUP",
    "TURN_STATUSES",
    "TURN_TOKENS",
    "record_resume",
    "record_save",
    "record_startup",
    "record_tokens",
    "record_turn",
    "set_meter_for_testing",
]
