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

"""A simulated internal observability backend for the ops-triage example.

Stands in for the log store, metrics store and deploy tracker a real on-call
engineer would query. Everything is generated from a fixed seed, so the same
incident is reproducible on every machine and the intended root cause can be
verified by hand (see ``README.md``).

The data is deliberately awkward, the way production data is:

- The log stream mixes **JSON lines** (the application) with **plaintext
  lines** (an Envoy sidecar), so a parser that assumes one format crashes.
- Log timestamps are UTC ISO-8601, metric timestamps are **epoch seconds**,
  and deploy timestamps come from a CI system in **UTC+08:00**. Correlating
  the three requires normalizing all of them.
- The loudest error signature is chronic background noise, and the largest
  metric spike belongs to an unrelated service.

Nothing here is VeADK-specific; it is just the "internal system" the ADK tools
in ``ops_tools.py`` read from.
"""

from __future__ import annotations

import json
import math
import random
import zlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

UTC = timezone.utc
CI_TZ = timezone(timedelta(hours=8))
"""The CI system stamps deploys in UTC+08:00, not UTC. On purpose."""

SERVICE = "checkout-api"
LOG_STREAM = "checkout-api-prod"

RETENTION_START = datetime(2026, 8, 10, tzinfo=UTC)
RETENTION_END = datetime(2026, 8, 26, tzinfo=UTC)

INCIDENT_DAY = date(2026, 8, 24)
BASELINE_DAY = date(2026, 8, 17)
"""The same weekday, one week earlier: the "is this new?" comparison window."""

#: The deploy that actually breaks things, and the first minute it shows up in
#: the logs. Kept as module constants so the README's ground truth and the
#: generator cannot drift apart.
REGRESSION_DEPLOY_AT = datetime(2026, 8, 24, 14, 7, 55, tzinfo=UTC)
REGRESSION_ONSET_AT = datetime(2026, 8, 24, 14, 9, 0, tzinfo=UTC)
DB_POOL_SIZE = 20

_GATEWAYS = ("unionpay", "alipay", "visa-intl")
_COUPONS = ("coupon expired", "coupon not applicable", "quantity above limit")


# --------------------------------------------------------------------------
# line formatting
# --------------------------------------------------------------------------


def _iso(ts: datetime) -> str:
    return (
        ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.")
        + f"{ts.microsecond // 1000:03d}Z"
    )


def _trace(rng: random.Random) -> str:
    return f"{rng.getrandbits(64):016x}"


def _json_line(
    ts: datetime, level: str, service: str, component: str, msg: str, **fields
) -> str:
    record = {
        "ts": _iso(ts),
        "level": level,
        "service": service,
        "component": component,
        "msg": msg,
    }
    record.update(fields)
    return json.dumps(record, separators=(",", ":"))


def _sidecar_line(ts: datetime, body: str) -> str:
    """Plaintext sidecar line: a different format *and* a different clock."""
    stamp = ts.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S +0000")
    return f"{stamp} [envoy-sidecar] {body}"


# --------------------------------------------------------------------------
# log generation
# --------------------------------------------------------------------------


def _pool_error_rate(hour: int) -> int:
    """Errors/hour for the connection-pool leak, once it starts.

    Ramps up over the afternoon but stays *below* the chronic payment-gateway
    noise in total volume, so ranking signatures by count alone points at the
    wrong thing.
    """
    ramp = {
        14: 2,
        15: 12,
        16: 28,
        17: 47,
        18: 66,
        19: 82,
        20: 95,
        21: 104,
        22: 110,
        23: 94,
    }
    return ramp.get(hour, 0)


def _generate_log_lines(day: date, rng: random.Random) -> list[tuple[datetime, str]]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    incident = day == INCIDENT_DAY
    out: list[tuple[datetime, str]] = []

    def at(hour: int) -> datetime:
        return start + timedelta(hours=hour, seconds=rng.uniform(0, 3600))

    for hour in range(24):
        # Successful checkouts: the bulk of the stream, and the reason a
        # case-insensitive grep for "error" is useless here.
        for _ in range(rng.randint(95, 115)):
            ts = at(hour)
            out.append(
                (
                    ts,
                    _json_line(
                        ts,
                        "INFO",
                        SERVICE,
                        "http",
                        "checkout completed",
                        trace_id=_trace(rng),
                        status=200,
                        duration_ms=rng.randint(60, 320),
                    ),
                )
            )
        # Chronic validation warnings.
        for _ in range(rng.randint(80, 100)):
            ts = at(hour)
            out.append(
                (
                    ts,
                    _json_line(
                        ts,
                        "WARN",
                        SERVICE,
                        "cart.validation",
                        f"line item rejected: {rng.choice(_COUPONS)}",
                        trace_id=_trace(rng),
                        cart_id=f"cart_{rng.getrandbits(32):08x}",
                    ),
                )
            )
        # Decoy #1: the loudest ERROR in the file, at a flat rate all day and
        # all of last week too.
        for _ in range(rng.randint(35, 45)):
            ts = at(hour)
            out.append(
                (
                    ts,
                    _json_line(
                        ts,
                        "ERROR",
                        "payments-proxy",
                        "payments.gateway",
                        "gateway timeout after 3000ms",
                        trace_id=_trace(rng),
                        gateway=rng.choice(_GATEWAYS),
                        attempt=rng.randint(1, 3),
                    ),
                )
            )
        # Sidecar heartbeat: plaintext, so json.loads() on every line fails.
        for minute in range(0, 60, 2):
            ts = start + timedelta(hours=hour, minutes=minute)
            out.append(
                (
                    ts,
                    _sidecar_line(
                        ts,
                        "health_check ok cluster=checkout-api upstream=10.4.2.17:8080",
                    ),
                )
            )

        if not incident:
            continue

        # The real signature: absent before the deploy, growing after it.
        for _ in range(_pool_error_rate(hour)):
            ts = max(
                at(hour), REGRESSION_ONSET_AT + timedelta(seconds=rng.uniform(0, 60))
            )
            if ts.hour != hour:
                continue
            out.append(
                (
                    ts,
                    _json_line(
                        ts,
                        "ERROR",
                        SERVICE,
                        "db.pool",
                        "acquire timeout after 5000ms",
                        trace_id=_trace(rng),
                        pool_size=DB_POOL_SIZE,
                        pool_in_use=DB_POOL_SIZE,
                        wait_ms=rng.randint(5000, 5400),
                    ),
                )
            )
            # Downstream symptom, visible only in the plaintext lines.
            if rng.random() < 0.55:
                out.append(
                    (
                        ts,
                        _sidecar_line(
                            ts,
                            "upstream_reset_before_response_started{connection_termination} "
                            f"cluster=checkout-api-db req_id={_trace(rng)}",
                        ),
                    )
                )

    if incident:
        # Decoy #2: a short, loud burst right after the *other* deploy of the
        # afternoon, which then stops on its own.
        burst_start = datetime(2026, 8, 24, 13, 52, 40, tzinfo=UTC)
        for _ in range(124):
            ts = burst_start + timedelta(seconds=rng.uniform(0, 360))
            out.append(
                (
                    ts,
                    _json_line(
                        ts,
                        "ERROR",
                        "notify-worker",
                        "notify.webhook",
                        "retry exhausted after 5 attempts",
                        trace_id=_trace(rng),
                        endpoint="https://hooks.internal/checkout",
                    ),
                )
            )

    out.sort(key=lambda item: item[0])
    return out


# --------------------------------------------------------------------------
# metric generation
# --------------------------------------------------------------------------


def _ramp(elapsed_min: float, span_min: float, lo: float, hi: float) -> float:
    return lo + (hi - lo) * min(1.0, max(0.0, elapsed_min / span_min))


def _generate_metric_rows(
    day: date, rng: random.Random
) -> list[tuple[int, str, float]]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    incident = day == INCIDENT_DAY
    onset = datetime(2026, 8, 24, 14, 10, tzinfo=UTC)
    notify_from = datetime(2026, 8, 24, 13, 52, tzinfo=UTC)
    notify_peak = datetime(2026, 8, 24, 14, 5, tzinfo=UTC)
    notify_to = datetime(2026, 8, 24, 14, 25, tzinfo=UTC)

    rows: list[tuple[int, str, float]] = []
    for minute in range(24 * 60):
        ts = start + timedelta(minutes=minute)
        epoch = int(ts.timestamp())
        after = (ts - onset).total_seconds() / 60.0 if incident else -1.0

        # Traffic is flat week over week: this rules out "we just got busier".
        rps = (
            40 + 25 * math.sin(2 * math.pi * (minute - 360) / 1440) + rng.uniform(-2, 2)
        )
        p99 = 180 + rng.uniform(-25, 25)
        errors = max(0.0, 0.4 + rng.uniform(-0.3, 0.5))
        in_use = min(12.0, max(2.0, 6 + rng.uniform(-2, 2)))
        queue = 12 + rng.uniform(-4, 4)

        if after >= 0:
            p99 = _ramp(after, 300, 180, 5200) + rng.uniform(-60, 60)
            errors = _ramp(after, 300, 0.4, 9.0) + rng.uniform(-0.4, 0.4)
            in_use = min(
                float(DB_POOL_SIZE), _ramp(after, 60, 6, 20.6) + rng.uniform(-0.4, 0.2)
            )
        if incident and notify_from <= ts <= notify_to:
            # Decoy #3: by far the biggest number on any dashboard, belonging
            # to a different service, and it starts *before* the real onset.
            if ts <= notify_peak:
                queue = _ramp((ts - notify_from).total_seconds() / 60, 13, 12, 900)
            else:
                queue = _ramp((notify_to - ts).total_seconds() / 60, 20, 12, 900)

        rows.extend(
            [
                (epoch, "checkout.rps", round(rps, 1)),
                (epoch, "http.p99_latency_ms", round(p99, 1)),
                (epoch, "http.5xx_per_min", round(max(0.0, errors), 2)),
                (epoch, "db.pool.in_use", round(in_use, 1)),
                (epoch, "db.pool.size", float(DB_POOL_SIZE)),
                (epoch, "notify.queue_depth", round(queue, 1)),
            ]
        )
    return rows


# --------------------------------------------------------------------------
# deploy records
# --------------------------------------------------------------------------


def _deploy(
    when: datetime, service: str, version: str, author: str, changes: list[str]
) -> dict:
    return {
        "service": service,
        "version": version,
        "deployed_at": when.astimezone(CI_TZ).strftime("%Y-%m-%d %H:%M:%S %z"),
        "deployed_by": author,
        "pipeline": f"cicd-{when:%Y%m%d}-{zlib.crc32(version.encode()) % 9000 + 1000}",
        "changes": changes,
    }


def _generate_deploys(day: date) -> list[dict]:
    if day == INCIDENT_DAY:
        return [
            _deploy(
                datetime(2026, 8, 24, 9, 31, 12, tzinfo=UTC),
                SERVICE,
                "4.10.3",
                "wu.lei",
                ["bump libcurl to 8.9.1", "fix typo in receipt email template"],
            ),
            _deploy(
                datetime(2026, 8, 24, 13, 52, 40, tzinfo=UTC),
                "notify-worker",
                "2.3.1",
                "chen.yu",
                ["switch webhook retry to exponential backoff (max 5 attempts)"],
            ),
            _deploy(
                REGRESSION_DEPLOY_AT,
                SERVICE,
                "4.11.0",
                "zhao.min",
                [
                    "raise checkout worker concurrency 8 -> 32",
                    "cache tax tables in process",
                    "add /healthz readiness probe",
                ],
            ),
            _deploy(
                datetime(2026, 8, 24, 15, 40, 10, tzinfo=UTC),
                "search-api",
                "1.9.4",
                "li.fang",
                ["re-rank suggestions by conversion"],
            ),
        ]
    if day == BASELINE_DAY:
        return [
            _deploy(
                datetime(2026, 8, 17, 10, 12, 4, tzinfo=UTC),
                SERVICE,
                "4.10.1",
                "wu.lei",
                ["add currency formatting for MYR"],
            )
        ]
    return []


# --------------------------------------------------------------------------
# store: materialize once, then query by time range
# --------------------------------------------------------------------------


def _seed(day: date) -> int:
    return int(day.strftime("%Y%m%d"))


def ensure_day(store: Path, day: date) -> None:
    """Materialize one day of the simulated backend, if not already present."""
    logs = store / "logs" / f"{day.isoformat()}.log"
    metrics = store / "metrics" / f"{day.isoformat()}.csv"
    deploys = store / "deploys" / f"{day.isoformat()}.json"
    if logs.exists() and metrics.exists() and deploys.exists():
        return
    for path in (logs, metrics, deploys):
        path.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(_seed(day))
    logs.write_text(
        "".join(f"{line}\n" for _, line in _generate_log_lines(day, rng)),
        encoding="utf-8",
    )
    rows = _generate_metric_rows(day, rng)
    metrics.write_text(
        "timestamp,metric,value\n" + "".join(f"{t},{m},{v}\n" for t, m, v in rows),
        encoding="utf-8",
    )
    deploys.write_text(
        json.dumps(_generate_deploys(day), indent=2) + "\n", encoding="utf-8"
    )


def _days(start: datetime, end: datetime) -> Iterator[date]:
    day = start.astimezone(UTC).date()
    last = end.astimezone(UTC).date()
    while day <= last:
        yield day
        day += timedelta(days=1)


def _line_time(line: str) -> datetime | None:
    """Parse either log format's timestamp, or give up on a malformed line."""
    if line.startswith('{"ts":"'):
        try:
            return datetime.strptime(line[7:30], "%Y-%m-%dT%H:%M:%S.%f").replace(
                tzinfo=UTC
            )
        except ValueError:
            return None
    try:
        return datetime.strptime(line[:25], "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return None


def read_log_lines(store: Path, start: datetime, end: datetime) -> Iterator[str]:
    """Yield raw log lines whose timestamp falls in ``[start, end)``."""
    for day in _days(start, end):
        ensure_day(store, day)
        path = store / "logs" / f"{day.isoformat()}.log"
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.rstrip("\n")
                when = _line_time(stripped)
                if when is not None and start <= when < end:
                    yield stripped


def read_metric_rows(store: Path, start: datetime, end: datetime) -> Iterator[str]:
    """Yield raw ``timestamp,metric,value`` rows in ``[start, end)``."""
    lo, hi = int(start.timestamp()), int(end.timestamp())
    for day in _days(start, end):
        ensure_day(store, day)
        path = store / "metrics" / f"{day.isoformat()}.csv"
        with path.open(encoding="utf-8") as handle:
            next(handle, None)
            for line in handle:
                stripped = line.rstrip("\n")
                if not stripped:
                    continue
                epoch = int(stripped.split(",", 1)[0])
                if lo <= epoch < hi:
                    yield stripped


def read_deploys(store: Path, start: datetime, end: datetime) -> list[dict]:
    """Return deploy records in ``[start, end)``, oldest first."""
    found: list[dict] = []
    for day in _days(start, end):
        ensure_day(store, day)
        path = store / "deploys" / f"{day.isoformat()}.json"
        for record in json.loads(path.read_text(encoding="utf-8")):
            when = datetime.strptime(record["deployed_at"], "%Y-%m-%d %H:%M:%S %z")
            if start <= when < end:
                found.append(record)
    found.sort(key=lambda item: item["deployed_at"])
    return found
