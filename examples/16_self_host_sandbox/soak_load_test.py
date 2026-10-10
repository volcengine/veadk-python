#!/usr/bin/env python3
# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

"""Sustained soak / load test for the Managed Agents unified gateway.

Unlike ``anthropic_gateway_e2e.py --mode concurrency`` (a one-shot isolation
check with no time axis), this harness holds a target number of concurrent
logical Sessions busy for a fixed duration by continuously *replenishing*
requests: whenever a worker slot finishes a turn it immediately starts the
next one, so the system stays at target concurrency for the whole window.

It records every request incrementally (JSONL) and in aggregate:
  * total requests, successes, failures, success rate
  * throughput (requests/min)
  * end-to-end latency percentiles (p50/p90/p95/p99, min/max/mean)
  * time-to-first-delta (streaming) percentiles
  * error classification (by type/status/short reason)
  * actual in-flight logical requests and low-frequency, run-scoped physical
    sandbox samples (via AgentKit helper)

It never prints or writes credentials. Signed endpoints stay out of the
result file. Sessions created for the run are best-effort archived on exit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anthropic_gateway_e2e import (  # noqa: E402
    AgentKitInspector,
    content_text,
    field_value,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


@dataclass
class RequestRecord:
    request_id: str
    worker: int
    session_id: str
    started_at: str
    completed_at: str
    started_offset_seconds: float
    completed_offset_seconds: float
    completion_phase: str
    elapsed_seconds: float
    first_delta_seconds: float | None
    ok: bool
    require_tool: bool
    tool_uses: int
    tool_results: int
    tool_use_ids: list[str] = field(default_factory=list)
    tool_result_ids: list[str] = field(default_factory=list)
    tool_error_ids: list[str] = field(default_factory=list)
    tool_error_details: list[str] = field(default_factory=list)
    cleanup_status: str | None = None
    cleanup_error: str | None = None
    physical_query_started_at: str | None = None
    physical_query_completed_at: str | None = None
    physical_query_count: int = 0
    physical_reclaimed: bool | None = None
    error_type: str | None = None
    error_category: str | None = None
    error_reason: str | None = None
    completion: dict[str, Any] | None = None


@dataclass
class Summary:
    started_at: str
    completed_at: str
    duration_seconds_target: float
    duration_seconds_actual: float
    concurrency: int
    require_tool: bool
    total_requests: int
    successes: int
    failures: int
    success_rate: float
    request_throughput_per_min: float
    success_throughput_per_min: float
    formal_window_seconds: float
    drain_seconds: float
    formal_completions: int
    drain_completions: int
    peak_in_flight_requests: int
    success_latency: dict[str, float | None]
    latency_including_failures: dict[str, float | None]
    first_text_event: dict[str, float | None]
    error_breakdown: dict[str, int]
    observed_peak_physical_sessions: int
    physical_session_ids: list[str] = field(default_factory=list)
    physical_samples: int = 0
    physical_sample_errors: int = 0
    physical_reclaim_confirmed: int = 0
    physical_reclaim_unconfirmed: int = 0
    physical_reclaim_unverified: int = 0
    total_sessions_created: int = 0
    sample_sessions_created: list[str] = field(default_factory=list)


class DurableJsonlWriter:
    """Durably append evidence so an interrupted run remains auditable."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._file = None

    def __enter__(self):
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("w", encoding="utf-8")
        return self

    def append(self, value: Any) -> None:
        if self._file is None:
            return
        payload = asdict(value) if hasattr(value, "__dataclass_fields__") else value
        self._file.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def __exit__(self, *_args) -> None:
        if self._file is not None:
            self._file.close()


def sanitize_error_detail(value: str, limit: int = 500) -> str:
    """Keep useful failure detail while removing common credential forms."""
    value = re.sub(r"(?i)bearer\s+[a-z0-9._~+/-]+", "Bearer <redacted>", value)
    credential_key = (
        r"(?:authorization|x[-_]api[-_]key|api[-_]?key|access[-_]?key|"
        r"secret[-_]?access[-_]?key|secret[-_]?key|client[-_]?secret|"
        r"session[-_]?token|security[-_]?token|auth[-_]?token|token|password|"
        r"private[-_]?key|secret)"
    )
    value = re.sub(
        rf"(?i)(?P<quote>['\"]?)(?P<key>{credential_key})(?P=quote)"
        r"\s*(?P<sep>[:=])\s*"
        r"(?:(?P<value_quote>['\"])(?P<quoted>.*?)(?P=value_quote)|"
        r"(?P<bare>[^\s,;&}]+))",
        lambda match: (
            f"{match.group('quote')}{match.group('key')}{match.group('quote')}"
            f"{match.group('sep')}<redacted>"
        ),
        value,
    )
    return value[:limit]


def error_category(reason: str) -> str:
    for needle, category in (
        ("expire_at is invalid", "expire_at_invalid"),
        ("InvalidParameter", "invalid_parameter"),
        ("rate limit", "rate_limit"),
        ("QuotaExceeded", "quota_exceeded"),
        ("timed out", "timeout"),
        ("Timeout", "timeout"),
        ("PreviousResponseNotFound", "previous_response_not_found"),
    ):
        if needle.lower() in reason.lower():
            return category
    return "unclassified"


def _error_record(
    request_id: str,
    worker: int,
    session_id: str,
    started_iso: str,
    started: float,
    exc: Exception,
    *,
    require_tool: bool,
    run_start: float,
    deadline: float,
    first_delta: float | None = None,
    tool_uses: int = 0,
    tool_results: int = 0,
    tool_use_ids: list[str] | None = None,
    tool_result_ids: list[str] | None = None,
    tool_error_ids: list[str] | None = None,
    tool_error_details: list[str] | None = None,
) -> RequestRecord:
    reason = str(exc)
    etype = type(exc).__name__
    status = getattr(exc, "status_code", None)
    if status is not None:
        etype = f"{etype}[{status}]"
    return RequestRecord(
        request_id=request_id,
        worker=worker,
        session_id=session_id,
        started_at=started_iso,
        completed_at=now_iso(),
        started_offset_seconds=round(started - run_start, 3),
        completed_offset_seconds=round(time.monotonic() - run_start, 3),
        completion_phase=("formal" if time.monotonic() <= deadline else "drain"),
        elapsed_seconds=time.monotonic() - started,
        first_delta_seconds=first_delta,
        ok=False,
        require_tool=require_tool,
        tool_uses=tool_uses,
        tool_results=tool_results,
        tool_use_ids=list(tool_use_ids or []),
        tool_result_ids=list(tool_result_ids or []),
        tool_error_ids=list(tool_error_ids or []),
        tool_error_details=list(tool_error_details or []),
        error_type=etype,
        error_category=error_category(reason),
        error_reason=sanitize_error_detail(reason),
    )


async def _bounded_pages(api, *args, **options) -> list[Any]:
    """Read explicit public pages; never accept a partial/repeating snapshot."""
    rows = []
    seen = set()
    for _ in range(100):
        response = await api(*args, limit=100, **options)
        data = field_value(response, "data")
        missing = object()
        page = field_value(response, "next_page", missing)
        if not isinstance(data, list) or page is missing:
            raise RuntimeError("incomplete public snapshot response")
        rows.extend(data)
        if page is None:
            if field_value(response, "has_more", False):
                raise RuntimeError("snapshot has_more without next_page")
            return rows
        if not isinstance(page, str) or not page or page in seen:
            raise RuntimeError("invalid/repeated snapshot page")
        seen.add(page)
        options["page"] = page
    raise RuntimeError("snapshot exceeded 100 pages")


async def verify_turn_settled(
    client,
    session_id: str,
    environment_id: str,
    *,
    input_id: str,
    input_sequence: int,
    idle_sequence: int,
    evidence: dict,
    timeout: float,
) -> None:
    """Require a closed model-Work graph, then recheck it and canonical events.

    ma-infra stops a Work and creates its successor in one Session-locked
    transaction. Two complete matching Work/event snapshots avoid accepting a
    pagination race. An active/queued successor keeps the gate open until the
    deadline; elapsed quiet time alone is never success. Tool Work can retain
    its sandbox lease after the model finishes (runtime_type is model-only).
    """
    evidence.update(
        input_event_id=input_id,
        input_sequence=input_sequence,
        idle_sequence=idle_sequence,
        settled=False,
        work=[],
        events=[],
    )
    previous = None
    known = set()
    async with asyncio.timeout(timeout):
        while True:
            rows = await _bounded_pages(
                client.beta.environments.work.list, environment_id
            )
            owned = [
                row
                for row in rows
                if field_value(field_value(row, "data", {}), "id") == session_id
            ]
            work = [
                {
                    **{
                        key: field_value(row, key)
                        for key in (
                            "id",
                            "state",
                            "runtime_type",
                            "created_at",
                            "stopped_at",
                        )
                    },
                    "worker_id": field_value(
                        field_value(row, "metadata", {}), "managed_agent_worker_id"
                    ),
                }
                for row in owned
            ]
            evidence["work"] = work
            ids = {row["id"] for row in work}
            if None in ids or not known.issubset(ids):
                raise RuntimeError("completion snapshot lost known Work IDs")
            known.update(ids)
            events = await _bounded_pages(
                client.beta.sessions.events.list,
                session_id,
                order="asc",
                page=str(input_sequence - 1),
            )
            summaries = [
                {
                    "id": field_value(e, "id"),
                    "type": field_value(e, "type"),
                    "sequence": field_value(e, "seq", field_value(e, "sequence")),
                    "tool_use_id": field_value(e, "tool_use_id"),
                    "stop_reason": field_value(
                        field_value(e, "stop_reason", {}), "type"
                    ),
                }
                for e in events
            ]
            evidence["events"] = summaries
            seen_input = seen_idle = False
            signatures = {}
            last = input_sequence - 1
            for e in summaries:
                seq = e["sequence"]
                if isinstance(seq, bool) or not str(seq).isdigit():
                    raise RuntimeError("completion event has no canonical sequence")
                seq = int(seq)
                signature = json.dumps(e, sort_keys=True, default=str)
                if seq in signatures:
                    if signatures[seq] != signature:
                        raise RuntimeError("conflicting completion event sequence")
                    continue
                if seq <= last:
                    raise RuntimeError("completion event sequence moved backwards")
                signatures[seq] = signature
                last = seq
                if (
                    seq == input_sequence
                    and e["id"] == input_id
                    and e["type"] == "user.message"
                ):
                    seen_input = True
                elif e["type"] in {"user.message", "user.interrupt"}:
                    raise RuntimeError(
                        "unexpected concurrent input during completion gate"
                    )
                if seq == idle_sequence and e["type"] == "session.status_idle":
                    if e["stop_reason"] != "end_turn":
                        raise RuntimeError("completion idle is not end_turn")
                    seen_idle = True
                if seq > idle_sequence and (
                    e["type"].startswith(
                        (
                            "agent.",
                            "span.model_request",
                            "user.tool",
                            "user.custom_tool",
                        )
                    )
                    or e["type"]
                    in {
                        "session.status_running",
                        "session.status_idle",
                        "session.error",
                        "session.status_terminated",
                    }
                ):
                    raise RuntimeError(
                        "new execution after end_turn idle without a new input"
                    )
            if not seen_input or not seen_idle:
                raise RuntimeError("completion history lost input/idle boundary")
            model = [row for row in work if row["runtime_type"]]
            closed = bool(model) and all(row["state"] == "stopped" for row in model)
            signature = json.dumps([work, summaries], sort_keys=True, default=str)
            evidence["observed_at"] = now_iso()
            if closed and signature == previous:
                evidence["settled"] = True
                return
            previous = signature if closed else None
            # Polling waits for an actual Work transition, never a quiet timer.
            if not closed:
                await asyncio.sleep(0.1)


async def run_one_turn(
    client: anthropic.AsyncAnthropic,
    session_id: str,
    *,
    marker: str,
    prompt: str,
    timeout: float,
    require_tool: bool,
    worker: int,
    request_id: str,
    run_start: float,
    deadline: float,
    environment_id: str | None = None,
) -> RequestRecord:
    started = time.monotonic()
    started_iso = now_iso()
    first_delta: float | None = None
    tool_use_ids: list[str] = []
    tool_result_ids: list[str] = []
    tool_error_ids: list[str] = []
    tool_error_details: list[str] = []
    final_parts: list[str] = []
    saw_idle = False
    completion: dict[str, Any] = {}
    input_id = None
    input_sequence = idle_sequence = None
    try:
        stream = await client.beta.sessions.events.stream(
            session_id, event_deltas=["agent.message"]
        )
        accepted = await client.beta.sessions.events.send(
            session_id,
            events=[
                {"type": "user.message", "content": [{"type": "text", "text": prompt}]}
            ],
        )
        if environment_id:
            inputs = field_value(accepted, "data", [])
            if len(inputs) != 1:
                raise RuntimeError("missing canonical input acknowledgement")
            input_id = field_value(inputs[0], "id")
            input_sequence = field_value(
                inputs[0], "seq", field_value(inputs[0], "sequence")
            )
            if not input_id or not str(input_sequence).isdigit():
                raise RuntimeError("missing canonical input identity/sequence")
        async with stream:
            async with asyncio.timeout(timeout):
                async for event in stream:
                    et = str(field_value(event, "type", ""))
                    if et == "event_delta" and first_delta is None:
                        delta = field_value(event, "delta")
                        if content_text([field_value(delta, "content")]):
                            first_delta = time.monotonic() - started
                    elif et == "agent.message":
                        final_parts.append(content_text(field_value(event, "content")))
                    elif et == "agent.tool_use":
                        tool_id = str(field_value(event, "id", "") or "")
                        if tool_id:
                            tool_use_ids.append(tool_id)
                    elif et == "agent.tool_result":
                        tool_id = str(field_value(event, "tool_use_id", "") or "")
                        if tool_id:
                            tool_result_ids.append(tool_id)
                            if field_value(event, "is_error", False) is True:
                                tool_error_ids.append(tool_id)
                                detail = content_text(field_value(event, "content"))
                                tool_error_details.append(
                                    sanitize_error_detail(
                                        detail or "tool execution failed"
                                    )
                                )
                    elif et in {"session.error", "session.status_terminated"}:
                        detail = ""
                        for key in ("error", "message", "content", "reason"):
                            val = field_value(event, key)
                            if val:
                                detail = str(val)
                                break
                        raise RuntimeError(f"{et}: {detail[:300]}")
                    if et == "session.status_idle":
                        if environment_id:
                            if (
                                field_value(
                                    field_value(event, "stop_reason", {}), "type"
                                )
                                != "end_turn"
                            ):
                                raise RuntimeError("idle is not end_turn")
                            idle_sequence = field_value(
                                event, "seq", field_value(event, "sequence")
                            )
                        saw_idle = True
                        break
        if environment_id and saw_idle:
            await verify_turn_settled(
                client,
                session_id,
                environment_id,
                input_id=input_id,
                input_sequence=int(input_sequence),
                idle_sequence=int(idle_sequence),
                evidence=completion,
                timeout=max(0.001, timeout - (time.monotonic() - started)),
            )
        final_text = "\n".join(p for p in final_parts if p)
        ok = saw_idle and (marker in final_text)
        if require_tool:
            ok = (
                ok
                and bool(tool_use_ids)
                and len(tool_use_ids) == len(set(tool_use_ids))
                and set(tool_use_ids) == set(tool_result_ids)
                and len(tool_result_ids) == len(set(tool_result_ids))
                and not tool_error_ids
            )
        if ok:
            category = reason = None
        elif tool_error_ids:
            category = "tool_result_error"
            reason = f"tool_result reported is_error=true for IDs: {','.join(tool_error_ids)}"
        else:
            category = "turn_assertion_failed"
            reason = "assertion: incomplete turn or marker/tool missing"
        return RequestRecord(
            request_id=request_id,
            worker=worker,
            session_id=session_id,
            started_at=started_iso,
            completed_at=now_iso(),
            started_offset_seconds=round(started - run_start, 3),
            completed_offset_seconds=round(time.monotonic() - run_start, 3),
            completion_phase=("formal" if time.monotonic() <= deadline else "drain"),
            elapsed_seconds=time.monotonic() - started,
            first_delta_seconds=first_delta,
            ok=ok,
            require_tool=require_tool,
            tool_uses=len(tool_use_ids),
            tool_results=len(tool_result_ids),
            tool_use_ids=tool_use_ids,
            tool_result_ids=tool_result_ids,
            tool_error_ids=tool_error_ids,
            tool_error_details=tool_error_details,
            error_type=None if ok else "AssertionError",
            error_category=category,
            error_reason=reason,
            completion=completion or None,
        )
    except Exception as exc:  # noqa: BLE001
        record = _error_record(
            request_id,
            worker,
            session_id,
            started_iso,
            started,
            exc,
            require_tool=require_tool,
            run_start=run_start,
            deadline=deadline,
            first_delta=first_delta,
            tool_uses=len(tool_use_ids),
            tool_results=len(tool_result_ids),
            tool_use_ids=tool_use_ids,
            tool_result_ids=tool_result_ids,
            tool_error_ids=tool_error_ids,
            tool_error_details=tool_error_details,
        )
        record.completion = completion or None
        return record


async def worker_loop(
    client: anthropic.AsyncAnthropic,
    worker: int,
    *,
    deadline: float,
    args: argparse.Namespace,
    records: list[RequestRecord],
    lock: asyncio.Lock,
    active: set[str],
    in_flight: dict[str, str],
    created: list[str],
    writer: DurableJsonlWriter,
    cleanup_records: list[dict[str, str | None]],
    cleanup_writer: DurableJsonlWriter,
    cleanup_tasks: list[asyncio.Task[None]],
    peak_in_flight: list[int],
    run_start: float,
    run_id: str,
) -> None:
    """Continuously replenish requests until deadline.

    A fresh logical Session is created for every turn. Reusing a Session and
    re-opening its event stream replays prior history (including an earlier
    ``session.status_idle``), which would end a turn instantly; a new Session
    per turn avoids that and keeps physical-sandbox concurrency honest.
    """
    while time.monotonic() < deadline:
        request_id = uuid.uuid4().hex
        async with lock:
            in_flight[request_id] = ""
            peak_in_flight[0] = max(peak_in_flight[0], len(in_flight))
        marker = f"w{worker:02d}-{uuid.uuid4().hex[:10]}"
        if args.require_tool:
            prompt = (
                f"Use the bash tool exactly once to run: printf {marker}. "
                f"Then include exactly {marker} in your final reply."
            )
        else:
            prompt = f"Do not use any tool. Reply with exactly: {marker}"
        started_iso = now_iso()
        started = time.monotonic()
        session_id = ""
        try:
            session = await client.beta.sessions.create(
                agent=args.agent_id,
                environment_id=args.environment_id,
                title=f"soak {run_id} w{worker:02d} {uuid.uuid4().hex[:8]}",
            )
            session_id = str(session.id)
            async with lock:
                active.add(session_id)
                in_flight[request_id] = session_id
                created.append(session_id)
        except Exception as exc:  # noqa: BLE001
            record = _error_record(
                request_id,
                worker,
                session_id,
                started_iso,
                started,
                exc,
                require_tool=args.require_tool,
                run_start=run_start,
                deadline=deadline,
            )
            async with lock:
                record.cleanup_status = "not_created"
                records.append(record)
                writer.append(record)
                in_flight.pop(request_id, None)
            if args.request_gap > 0:
                await asyncio.sleep(args.request_gap)
            continue

        record = await run_one_turn(
            client,
            session_id,
            marker=marker,
            prompt=prompt,
            timeout=args.turn_timeout,
            require_tool=args.require_tool,
            worker=worker,
            request_id=request_id,
            run_start=run_start,
            deadline=deadline,
            environment_id=args.environment_id,
        )
        # Persist the complete turn before cleanup so a slow or failed archive
        # cannot erase successful request evidence. Cleanup has its own ledger.
        record.cleanup_status = "pending"
        async with lock:
            records.append(record)
            writer.append(record)
            in_flight.pop(request_id, None)
        cleanup_tasks.append(
            asyncio.create_task(
                cleanup_session(
                    client,
                    session_id,
                    record,
                    lock=lock,
                    active=active,
                    cleanup_records=cleanup_records,
                    cleanup_writer=cleanup_writer,
                    archive_timeout=args.archive_timeout,
                )
            )
        )
        if args.request_gap > 0:
            await asyncio.sleep(args.request_gap)


async def cleanup_session(
    client: anthropic.AsyncAnthropic,
    session_id: str,
    record: RequestRecord,
    *,
    lock: asyncio.Lock,
    active: set[str],
    cleanup_records: list[dict[str, Any]],
    cleanup_writer: DurableJsonlWriter,
    archive_timeout: float,
) -> None:
    try:
        async with asyncio.timeout(archive_timeout):
            await client.beta.sessions.archive(session_id, timeout=archive_timeout)
        record.cleanup_status = "archived"
    except Exception as exc:  # noqa: BLE001
        record.cleanup_status = "archive_failed"
        record.cleanup_error = sanitize_error_detail(
            f"{type(exc).__name__}: {exc}", limit=300
        )

    cleanup_record: dict[str, Any] = {
        "session_id": session_id,
        "status": record.cleanup_status,
        "error": record.cleanup_error,
        "archive_completed_at": now_iso(),
        "physical_query_started_at": record.physical_query_started_at,
        "physical_query_completed_at": record.physical_query_completed_at,
        "physical_reclaimed": None,
        "physical_query_count": 0,
    }
    async with lock:
        cleanup_records.append(cleanup_record)
        cleanup_writer.append(cleanup_record)


async def confirm_physical_reclaims(
    inspector: AgentKitInspector | None,
    active: set[str],
    records: list[RequestRecord],
    cleanup_records: list[dict[str, Any]],
    cleanup_writer: DurableJsonlWriter,
    *,
    timeout: float,
    interval: float = 10.0,
) -> None:
    by_session = {record.session_id: record for record in records if record.session_id}
    cleanup_by_session = {item["session_id"]: item for item in cleanup_records}
    if inspector is None:
        for session_id in sorted(active):
            record = by_session[session_id]
            record.cleanup_status += "_physical_unverified"
            cleanup_by_session[session_id]["status"] = record.cleanup_status
            cleanup_writer.append(cleanup_by_session[session_id])
            active.discard(session_id)
        return

    started = time.monotonic()
    pending = set(active)
    while pending and time.monotonic() - started < timeout:
        query_started_at = now_iso()
        rows = await run_scoped_physical_sessions(inspector, pending)
        query_completed_at = now_iso()
        present = {item["user_session_id"] for item in rows}
        for session_id in sorted(pending):
            record = by_session[session_id]
            record.physical_query_started_at = (
                record.physical_query_started_at or query_started_at
            )
            record.physical_query_completed_at = query_completed_at
            record.physical_query_count += 1
        reclaimed = pending - present
        for session_id in reclaimed:
            record = by_session[session_id]
            record.physical_reclaimed = True
            record.cleanup_status += "_physical_absent"
            item = cleanup_by_session[session_id]
            item.update(
                status=record.cleanup_status,
                physical_query_started_at=record.physical_query_started_at,
                physical_query_completed_at=record.physical_query_completed_at,
                physical_query_count=record.physical_query_count,
                physical_reclaimed=True,
            )
            cleanup_writer.append(item)
            active.discard(session_id)
        pending -= reclaimed
        if pending:
            await asyncio.sleep(interval)

    for session_id in sorted(pending):
        record = by_session[session_id]
        record.physical_reclaimed = False
        record.cleanup_status += "_physical_unconfirmed"
        detail = f"physical sandbox still present after {timeout:.1f}s"
        record.cleanup_error = (
            f"{record.cleanup_error}; {detail}" if record.cleanup_error else detail
        )
        item = cleanup_by_session[session_id]
        item.update(
            status=record.cleanup_status,
            error=record.cleanup_error,
            physical_query_started_at=record.physical_query_started_at,
            physical_query_completed_at=record.physical_query_completed_at,
            physical_query_count=record.physical_query_count,
            physical_reclaimed=False,
        )
        cleanup_writer.append(item)


async def sample_physical(
    inspector: AgentKitInspector | None,
    active: set[str],
    in_flight: dict[str, str],
    lock: asyncio.Lock,
    stop: asyncio.Event,
    samples: list[dict[str, Any]],
    writer: DurableJsonlWriter,
    interval: float,
) -> None:
    if inspector is None:
        return
    while not stop.is_set():
        watch: set[str] = set()
        inflight_snapshot: dict[str, str] = {}
        try:
            async with lock:
                inflight_snapshot = dict(in_flight)
                watch = set(active)
                snapshot_started_at = now_iso()
            rows = await run_scoped_physical_sessions(inspector, watch)
            current = {
                item["user_session_id"]: item
                for item in rows
                if item["user_session_id"] in watch
            }
            sample = {
                "snapshot_started_at": snapshot_started_at,
                "snapshot_completed_at": now_iso(),
                "in_flight_requests": len(inflight_snapshot),
                "in_flight": inflight_snapshot,
                "logical_session_ids": sorted(watch),
                "physical_sessions": sorted(
                    current.values(), key=lambda item: item["session_id"]
                ),
                "error": None,
            }
            samples.append(sample)
            writer.append(sample)
        except Exception as exc:  # noqa: BLE001
            sample = {
                "snapshot_started_at": snapshot_started_at,
                "snapshot_completed_at": now_iso(),
                "in_flight_requests": len(inflight_snapshot),
                "in_flight": inflight_snapshot,
                "logical_session_ids": sorted(watch),
                "physical_sessions": [],
                "error": sanitize_error_detail(
                    f"{type(exc).__name__}: {exc}", limit=300
                ),
            }
            samples.append(sample)
            writer.append(sample)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def run_scoped_physical_sessions(
    inspector: AgentKitInspector, managed_session_ids: set[str]
) -> list[dict[str, str]]:
    """List only physical sessions bound to this run's active logical IDs."""
    if not managed_session_ids:
        return []
    custom = getattr(inspector, "sessions_for_managed_sessions", None)
    if callable(custom):
        rows = await custom(managed_session_ids)
        return _validated_physical_rows(rows, managed_session_ids)

    sessions: list[dict[str, str]] = []
    for managed_session_chunk in _chunks(sorted(managed_session_ids), 50):
        sessions.extend(
            await _list_physical_session_chunk(inspector, managed_session_chunk)
        )
    return _validated_physical_rows(sessions, managed_session_ids)


def _validated_physical_rows(
    rows: Any, managed_session_ids: set[str]
) -> list[dict[str, str]]:
    if not isinstance(rows, list):
        raise RuntimeError("physical session query must return a list")
    for item in rows:
        if not isinstance(item, dict):
            raise RuntimeError("physical session item must be an object")
        if not item.get("session_id"):
            raise RuntimeError("physical session item is missing session_id")
        if item.get("user_session_id") not in managed_session_ids:
            raise RuntimeError(
                f"physical query returned unexpected UserSessionId: {item.get('user_session_id')}"
            )
    return rows


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


async def _list_physical_session_chunk(
    inspector: AgentKitInspector, managed_session_ids: list[str]
) -> list[dict[str, str]]:
    sessions: list[dict[str, str]] = []
    next_token = None
    seen_tokens: set[str] = set()
    while True:
        body: dict[str, Any] = {
            "ToolId": inspector.tool_id,
            "MaxResults": 100,
            "Filters": [
                {
                    "Name": "UserSessionId",
                    "Values": managed_session_ids,
                }
            ],
        }
        if next_token:
            body["NextToken"] = next_token
        payload = await asyncio.to_thread(inspector.client.call, "ListSessions", body)
        if not isinstance(payload, dict):
            raise RuntimeError("ListSessions response must be an object")
        raw_sessions = payload.get("SessionInfos")
        if not isinstance(raw_sessions, list):
            raise RuntimeError("ListSessions response must contain SessionInfos list")
        for item in raw_sessions:
            if not isinstance(item, dict):
                raise RuntimeError("ListSessions SessionInfos item must be an object")
            session_id = item.get("SessionId")
            user_session_id = item.get("UserSessionId")
            if not isinstance(session_id, str) or not session_id:
                raise RuntimeError("ListSessions item is missing SessionId")
            if user_session_id not in managed_session_ids:
                raise RuntimeError(
                    f"ListSessions returned unexpected UserSessionId: {user_session_id}"
                )
            sessions.append(
                {
                    "session_id": session_id,
                    "user_session_id": user_session_id,
                    "status": str(item.get("Status") or ""),
                    "created_at": str(item.get("CreatedAt") or ""),
                }
            )
        next_token = payload.get("NextToken")
        if next_token is None or next_token == "":
            return sessions
        if not isinstance(next_token, str):
            raise RuntimeError("ListSessions NextToken must be a string or null")
        if next_token in seen_tokens:
            raise RuntimeError("AgentKit ListSessions repeated NextToken")
        seen_tokens.add(next_token)


async def async_main(args: argparse.Namespace) -> dict[str, Any]:
    run_id = args.run_id or (
        f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    )
    inspector = None
    if args.with_inspector and args.tool_id:
        inspector = AgentKitInspector(
            os.getenv(
                "AGENTKIT_TOOL_DEPLOY_SCRIPT",
                "",
            ),
            args.tool_id,
        )

    records: list[RequestRecord] = []
    lock = asyncio.Lock()
    active: set[str] = set()
    in_flight: dict[str, str] = {}
    created: list[str] = []
    cleanup_records: list[dict[str, Any]] = []
    cleanup_tasks: list[asyncio.Task[None]] = []
    peak_in_flight = [0]
    physical_samples: list[dict[str, Any]] = []
    started_iso = now_iso()
    run_start = time.monotonic()
    deadline = run_start + args.duration

    records_output = args.records_output
    if records_output is None and args.output is not None:
        records_output = args.output.with_suffix(".records.jsonl")
    samples_output = args.samples_output
    if samples_output is None and args.output is not None:
        samples_output = args.output.with_suffix(".samples.jsonl")
    cleanup_output = args.cleanup_output
    if cleanup_output is None and args.output is not None:
        cleanup_output = args.output.with_suffix(".cleanup.jsonl")
    with (
        DurableJsonlWriter(records_output) as writer,
        DurableJsonlWriter(samples_output) as sample_writer,
        DurableJsonlWriter(cleanup_output) as cleanup_writer,
    ):
        async with anthropic.AsyncAnthropic(
            base_url=args.base_url.rstrip("/"),
            auth_token=args.auth_token,
            timeout=args.turn_timeout,
            max_retries=0,
        ) as client:
            stop = asyncio.Event()
            sampler = asyncio.create_task(
                sample_physical(
                    inspector,
                    active,
                    in_flight,
                    lock,
                    stop,
                    physical_samples,
                    sample_writer,
                    args.sample_interval,
                )
            )

            loops = [
                worker_loop(
                    client,
                    index,
                    deadline=deadline,
                    args=args,
                    records=records,
                    lock=lock,
                    active=active,
                    in_flight=in_flight,
                    created=created,
                    writer=writer,
                    cleanup_records=cleanup_records,
                    cleanup_writer=cleanup_writer,
                    cleanup_tasks=cleanup_tasks,
                    peak_in_flight=peak_in_flight,
                    run_start=run_start,
                    run_id=run_id,
                )
                for index in range(args.concurrency)
            ]
            await asyncio.gather(*loops)
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks)
            stop.set()
            await sampler
            await confirm_physical_reclaims(
                inspector,
                active,
                records,
                cleanup_records,
                cleanup_writer,
                timeout=args.physical_reclaim_timeout,
            )

    actual = time.monotonic() - run_start
    successes = sum(1 for r in records if r.ok)
    failures = len(records) - successes
    latencies = [r.elapsed_seconds for r in records if r.ok]
    all_latencies = [r.elapsed_seconds for r in records]
    first_deltas = [
        r.first_delta_seconds
        for r in records
        if r.ok and r.first_delta_seconds is not None
    ]
    errors = Counter(
        f"{r.error_category}: {r.error_type}"
        for r in records
        if not r.ok and r.error_type
    )

    def stats(values: list[float]) -> dict[str, float | None]:
        if not values:
            return {k: None for k in ("min", "mean", "p50", "p90", "p95", "p99", "max")}
        return {
            "min": round(min(values), 3),
            "mean": round(statistics.fmean(values), 3),
            "p50": round(percentile(values, 50), 3),
            "p90": round(percentile(values, 90), 3),
            "p95": round(percentile(values, 95), 3),
            "p99": round(percentile(values, 99), 3),
            "max": round(max(values), 3),
        }

    summary = Summary(
        started_at=started_iso,
        completed_at=now_iso(),
        duration_seconds_target=args.duration,
        duration_seconds_actual=round(actual, 1),
        concurrency=args.concurrency,
        require_tool=args.require_tool,
        total_requests=len(records),
        successes=successes,
        failures=failures,
        success_rate=round(successes / len(records), 4) if records else 0.0,
        request_throughput_per_min=round(len(records) / (actual / 60.0), 2)
        if actual > 0
        else 0.0,
        success_throughput_per_min=round(successes / (actual / 60.0), 2)
        if actual > 0
        else 0.0,
        formal_window_seconds=args.duration,
        drain_seconds=round(max(0.0, actual - args.duration), 1),
        formal_completions=sum(r.completion_phase == "formal" for r in records),
        drain_completions=sum(r.completion_phase == "drain" for r in records),
        peak_in_flight_requests=peak_in_flight[0],
        success_latency=stats(latencies),
        latency_including_failures=stats(all_latencies),
        first_text_event=stats(first_deltas),
        error_breakdown=dict(errors),
        observed_peak_physical_sessions=max(
            (len(sample["physical_sessions"]) for sample in physical_samples),
            default=0,
        ),
        physical_session_ids=sorted(
            {
                item["session_id"]
                for sample in physical_samples
                for item in sample["physical_sessions"]
            }
        ),
        physical_samples=len(physical_samples),
        physical_sample_errors=sum(
            bool(sample["error"]) for sample in physical_samples
        ),
        physical_reclaim_confirmed=sum(
            item.get("physical_reclaimed") is True for item in cleanup_records
        ),
        physical_reclaim_unconfirmed=sum(
            item.get("physical_reclaimed") is False for item in cleanup_records
        ),
        physical_reclaim_unverified=sum(
            item.get("physical_reclaimed") is None for item in cleanup_records
        ),
        total_sessions_created=len(created),
        sample_sessions_created=created[:10],
    )

    return {
        "summary": asdict(summary),
        "run_id": run_id,
        "base_url": args.base_url,
        "agent_id": args.agent_id,
        "environment_id": args.environment_id,
        "records_output": str(records_output) if records_output else None,
        "samples_output": str(samples_output) if samples_output else None,
        "cleanup_output": str(cleanup_output) if cleanup_output else None,
        "records": [asdict(r) for r in records],
        "physical_samples": physical_samples,
        "cleanup_records": cleanup_records,
        "unreclaimed_logical_session_ids": sorted(active),
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default=os.getenv("MANAGED_AGENTS_GATEWAY"))
    p.add_argument("--agent-id", default=os.getenv("MANAGED_AGENTS_TEST_AGENT_ID"))
    p.add_argument("--environment-id", default=os.getenv("ANTHROPIC_ENVIRONMENT_ID"))
    p.add_argument(
        "--auth-token",
        default=os.getenv("MANAGED_AGENTS_GATEWAY_TOKEN", "gateway-client"),
    )
    p.add_argument("--concurrency", type=int, default=50)
    p.add_argument(
        "--duration", type=float, default=1200, help="seconds (default 20min)"
    )
    p.add_argument("--turn-timeout", type=float, default=180)
    p.add_argument(
        "--request-gap",
        type=float,
        default=0.0,
        help="seconds to wait between a worker's turns (0 = replenish immediately)",
    )
    p.add_argument(
        "--require-tool",
        action="store_true",
        help="each turn must run one bash tool (exercises sandbox path)",
    )
    p.add_argument(
        "--with-inspector",
        action="store_true",
        help="sample AgentKit physical sandbox Sessions for peak concurrency",
    )
    p.add_argument("--tool-id", default=os.getenv("AGENTKIT_TOOL_ID"))
    p.add_argument("--sample-interval", type=float, default=30.0)
    p.add_argument("--physical-reclaim-timeout", type=float, default=120.0)
    p.add_argument(
        "--archive-timeout",
        type=float,
        default=30.0,
        help="total wall-clock limit per Session archive, including SDK retries",
    )
    p.add_argument(
        "--run-id", help="unique non-secret run label (generated by default)"
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--records-output",
        type=Path,
        help="durable per-turn JSONL (default: <output>.records.jsonl)",
    )
    p.add_argument(
        "--samples-output",
        type=Path,
        help="durable low-frequency sample JSONL (default: <output>.samples.jsonl)",
    )
    p.add_argument(
        "--cleanup-output",
        type=Path,
        help="durable cleanup JSONL (default: <output>.cleanup.jsonl)",
    )
    p.add_argument("--progress-interval", type=float, default=60.0)
    return p


async def _with_progress(args: argparse.Namespace) -> dict[str, Any]:
    return await async_main(args)


def main() -> int:
    args = parser().parse_args()
    if not args.base_url or not args.agent_id or not args.environment_id:
        print("base-url, agent-id and environment-id are required", file=sys.stderr)
        return 2
    if args.with_inspector and not args.tool_id:
        print("--with-inspector requires --tool-id", file=sys.stderr)
        return 2
    result = asyncio.run(_with_progress(args))
    s = result["summary"]
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n")
    # Human-readable summary to stdout; full JSON only to file when requested.
    print(json.dumps(s, ensure_ascii=False, indent=2))
    cleanup_failed = any(
        not str(item.get("status") or "").startswith("archived")
        for item in result["cleanup_records"]
    )
    physical_incomplete = bool(result["unreclaimed_logical_session_ids"])
    if args.with_inspector:
        physical_incomplete = (
            physical_incomplete
            or result["summary"]["physical_sample_errors"] > 0
            or any(
                item.get("physical_reclaimed") is not True
                for item in result["cleanup_records"]
            )
        )
    return 1 if cleanup_failed or physical_incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
