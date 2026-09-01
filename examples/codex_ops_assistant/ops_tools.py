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

"""ADK tools for the Codex ops-triage example: the agent's only I/O.

Two rules shape every tool here, and they are the point of the example:

**The workspace is the data plane; tool results are the control plane.**
An ADK tool under ``runtime="codex"`` is executed by VeADK's shim, not inside
the sandbox, and whatever it returns is pasted into the model's context as the
function-call result. Returning 8,000 log lines would blow the turn's context
on data the model then still has to grep. So the ``fetch_*`` tools write a file
into Codex's workspace and return a **receipt** — path, size, shape — and the
model reads the file with its own sandboxed shell and Python.

**The tools are the only egress.** Codex runs with ``network_access=False`` and
``sandbox="workspace_write"``, so it can read and rewrite everything in the
workspace and reach nothing else: no sockets, and no writes outside the
workspace. ``file_incident_ticket`` writes to ``outbox/``, which lives *beside*
the workspace and is therefore unreachable from inside the sandbox. Every byte
that leaves is a structured argument to this one function, on one audited code
path you own.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ops_backend import (
    LOG_STREAM,
    RETENTION_END,
    RETENTION_START,
    SERVICE,
    read_deploys,
    read_log_lines,
    read_metric_rows,
)

_HERE = Path(__file__).resolve().parent

WORKSPACE = _HERE / "workspace"
"""Codex's working directory. Writable by the sandbox *and* by these tools."""

OUTBOX = _HERE / "outbox"
"""Where filed tickets land. Outside the workspace, so the sandbox cannot."""

STORE = _HERE / "_store"
"""The simulated internal system's own storage. Also outside the workspace."""

MAX_RANGE = timedelta(days=3)
_MAX_TICKET_FIELD_CHARS = 4000
_MAX_EVIDENCE_ITEMS = 20


def _parse_time(value: str, label: str) -> datetime:
    """Accept ISO-8601 with ``Z``, an offset, or none (treated as UTC)."""
    text = (value or "").strip().replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"{label}={value!r} is not ISO-8601; use e.g. '2026-08-24T00:00:00Z'"
        ) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _resolve_range(start_time: str, end_time: str) -> tuple[datetime, datetime]:
    start = _parse_time(start_time, "start_time")
    end = _parse_time(end_time, "end_time")
    if end <= start:
        raise ValueError("end_time must be after start_time")
    if end - start > MAX_RANGE:
        raise ValueError(
            f"range is {end - start}; this backend serves at most {MAX_RANGE} "
            "per call, so fetch one window at a time"
        )
    if start < RETENTION_START or end > RETENTION_END:
        raise ValueError(
            "outside retention; logs and metrics exist from "
            f"{RETENTION_START:%Y-%m-%dT%H:%M:%SZ} to "
            f"{RETENTION_END:%Y-%m-%dT%H:%M:%SZ}"
        )
    return start, end


def _slug(start: datetime, end: datetime) -> str:
    return f"{start:%Y%m%dT%H%M}_{end:%Y%m%dT%H%M}"


def _write(relative: str, text: str) -> tuple[str, int]:
    """Write into the workspace and return ``(relative path, bytes)``."""
    target = WORKSPACE / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return relative, target.stat().st_size


def fetch_application_logs(stream: str, start_time: str, end_time: str) -> dict:
    """Download raw application logs into your workspace as a file.

    The log content is NOT returned to you: it is far too large for the
    conversation. Only a receipt comes back; read and analyze the file with
    your own shell and Python.

    Args:
        stream: Log stream to pull. The only stream you have access to is
            'checkout-api-prod' (the production checkout pod's combined
            stdout).
        start_time: Inclusive start of the window, ISO-8601 UTC, e.g.
            '2026-08-24T00:00:00Z'.
        end_time: Exclusive end of the window, ISO-8601 UTC. At most 3 days
            after start_time.

    Returns:
        dict: A receipt with the workspace-relative 'path', 'lines' and
        'bytes' on success, or 'status'='error' with a 'message' explaining
        how to fix the call.
    """
    if stream != LOG_STREAM:
        return {
            "status": "error",
            "message": f"unknown stream {stream!r}; available streams: [{LOG_STREAM!r}]",
        }
    try:
        start, end = _resolve_range(start_time, end_time)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    lines = list(read_log_lines(STORE, start, end))
    path, size = _write(
        f"logs/{stream}_{_slug(start, end)}.log", "".join(f"{line}\n" for line in lines)
    )
    return {
        "status": "ok",
        "path": path,
        "lines": len(lines),
        "bytes": size,
        "window_utc": [f"{start:%Y-%m-%dT%H:%M:%SZ}", f"{end:%Y-%m-%dT%H:%M:%SZ}"],
        "note": "one event per line, chronological; content not returned",
    }


def fetch_service_metrics(service: str, start_time: str, end_time: str) -> dict:
    """Download a per-minute metric series into your workspace as a CSV file.

    As with the logs, the rows are NOT returned to you — only a receipt.

    Args:
        service: Service to pull metrics for. Use 'checkout-api'.
        start_time: Inclusive start of the window, ISO-8601 UTC.
        end_time: Exclusive end of the window, ISO-8601 UTC. At most 3 days
            after start_time.

    Returns:
        dict: A receipt with the workspace-relative 'path', 'rows', 'columns'
        and the metric names present, or 'status'='error' with a 'message'.
    """
    if service != SERVICE:
        return {
            "status": "error",
            "message": f"unknown service {service!r}; available services: [{SERVICE!r}]",
        }
    try:
        start, end = _resolve_range(start_time, end_time)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    rows = list(read_metric_rows(STORE, start, end))
    path, size = _write(
        f"metrics/{service}_{_slug(start, end)}.csv",
        "timestamp,metric,value\n" + "".join(f"{row}\n" for row in rows),
    )
    return {
        "status": "ok",
        "path": path,
        "rows": len(rows),
        "bytes": size,
        "columns": ["timestamp", "metric", "value"],
        "note": (
            "long format (one row per metric per minute); 'timestamp' is "
            "epoch seconds in UTC"
        ),
    }


def fetch_deploy_history(start_time: str, end_time: str) -> dict:
    """Download the deploy log for every service into your workspace as JSON.

    Args:
        start_time: Inclusive start of the window, ISO-8601 UTC.
        end_time: Exclusive end of the window, ISO-8601 UTC. At most 3 days
            after start_time.

    Returns:
        dict: A receipt with the workspace-relative 'path' and 'records', or
        'status'='error' with a 'message'.
    """
    try:
        start, end = _resolve_range(start_time, end_time)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    records = read_deploys(STORE, start, end)
    path, size = _write(
        f"deploys/deploys_{_slug(start, end)}.json",
        json.dumps(records, indent=2) + "\n",
    )
    return {
        "status": "ok",
        "path": path,
        "records": len(records),
        "bytes": size,
        "note": "JSON array; 'deployed_at' is stamped by the CI system, not in UTC",
    }


def file_incident_ticket(
    title: str,
    severity: str,
    root_cause: str,
    evidence: list[str],
    recommended_action: str,
) -> dict:
    """File an incident ticket. This is the ONLY way to report anything.

    Nothing you write in the workspace reaches a human. Call this exactly once,
    when you can name a root cause and cite the evidence for it.

    Args:
        title: One-line summary, e.g. 'checkout-api 5xx after <deploy>'.
        severity: One of 'sev1', 'sev2', 'sev3'.
        root_cause: What actually broke and why, in a few sentences. Name the
            specific change if you found one.
        evidence: Concrete observations backing the root cause — counts,
            timestamps, metric values. One string per observation, at most 20.
        recommended_action: What on-call should do next.

    Returns:
        dict: 'ticket_id' and the absolute 'path' the ticket was written to,
        or 'status'='error' with a 'message'.
    """
    severity = (severity or "").strip().lower()
    if severity not in {"sev1", "sev2", "sev3"}:
        return {
            "status": "error",
            "message": f"severity must be one of sev1/sev2/sev3, got {severity!r}",
        }
    if isinstance(evidence, str):
        evidence = [evidence]
    items = [str(item)[:_MAX_TICKET_FIELD_CHARS] for item in (evidence or [])]
    if not items:
        return {"status": "error", "message": "evidence must not be empty"}

    ticket_id = (
        f"INC-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    )
    ticket = {
        "ticket_id": ticket_id,
        "filed_at": f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}",
        "title": str(title)[:_MAX_TICKET_FIELD_CHARS],
        "severity": severity,
        "root_cause": str(root_cause)[:_MAX_TICKET_FIELD_CHARS],
        "evidence": items[:_MAX_EVIDENCE_ITEMS],
        "recommended_action": str(recommended_action)[:_MAX_TICKET_FIELD_CHARS],
    }
    OUTBOX.mkdir(parents=True, exist_ok=True)
    target = OUTBOX / f"{ticket_id}.json"
    target.write_text(json.dumps(ticket, indent=2, ensure_ascii=False) + "\n", "utf-8")

    # The audit point: one line per byte that leaves the sandbox.
    print(f"  [egress] ticket {ticket_id} ({severity}) -> {target}")
    return {
        "status": "ok",
        "ticket_id": ticket_id,
        "path": str(target),
        "evidence_items_accepted": len(ticket["evidence"]),
    }


OPS_TOOLS = [
    fetch_application_logs,
    fetch_service_metrics,
    fetch_deploy_history,
    file_incident_ticket,
]
