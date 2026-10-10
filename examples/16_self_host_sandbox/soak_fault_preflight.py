#!/usr/bin/env python3
# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

"""Dedicated sandbox-loss preflight; never include it in soak statistics.

This script is deliberately separate from ``soak_load_test.py``. It creates a
single logical Session, waits until a long tool call has a bound physical
Session, deletes exactly that physical ID while the Work lease is active, then
measures the next tool turn's lease-based recovery. Run only after deployment
authorization.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anthropic_gateway_e2e import (  # noqa: E402
    AgentKitInspector,
    content_text,
    field_value,
)
from soak_load_test import sanitize_error_detail, verify_turn_settled  # noqa: E402


def assert_tool_turn(result: dict, marker: str) -> None:
    if result.get("error"):
        raise AssertionError(f"turn collection failed: {result['error']}")
    uses = result["tool_uses"]
    results = result["tool_results"]
    if (
        not uses
        or len(uses) != len(set(uses))
        or len(results) != len(set(results))
        or set(uses) != set(results)
    ):
        raise AssertionError(f"tool IDs do not match: uses={uses} results={results}")
    if result.get("tool_error_ids"):
        raise AssertionError(
            f"tool execution failed: IDs={result['tool_error_ids']} "
            f"details={result.get('tool_error_details', [])}"
        )
    if marker not in result["final"]:
        raise AssertionError("final response is missing marker")
    if "session.status_idle" not in result["types"]:
        raise AssertionError("turn did not reach idle")


def event_sequence(event) -> int:
    value = field_value(event, "seq", field_value(event, "sequence"))
    if isinstance(value, bool) or not str(value).isdigit() or int(value) < 1:
        raise RuntimeError("canonical event is missing a positive sequence")
    return int(value)


async def send_turn(client, session_id: str, prompt: str) -> tuple[str, int]:
    """Use the persisted send acknowledgement as the authoritative turn boundary."""
    response = await client.beta.sessions.events.send(
        session_id,
        events=[
            {"type": "user.message", "content": [{"type": "text", "text": prompt}]}
        ],
    )
    accepted = field_value(response, "data", [])
    if len(accepted) != 1 or field_value(accepted[0], "type") != "user.message":
        raise RuntimeError("send did not acknowledge exactly one user.message")
    event_id = field_value(accepted[0], "id")
    if not event_id:
        raise RuntimeError("acknowledged user.message has no ID")
    return str(event_id), event_sequence(accepted[0])


async def run_verified_tool_turn(
    client,
    session_id: str,
    *,
    marker: str,
    prompt: str,
    timeout: float,
    environment_id: str | None = None,
) -> dict:
    started = time.monotonic()
    types_seen = []
    tool_uses = []
    tool_results = []
    tool_error_ids = []
    tool_error_details = []
    final_parts = []
    summaries = []
    input_id = None
    input_seq = None
    boundary_seen = False
    error = None
    seen: dict[int, str] = {}
    last_seq = 0
    final_seq = 0
    last_tool_seq = 0
    idle_seq = 0
    completion = {}
    try:
        async with asyncio.timeout(timeout):
            input_id, input_seq = await send_turn(client, session_id, prompt)
            # Include the acknowledged input itself, even if the worker finished
            # before the stream opens. Durable SSE replay cannot lose that turn.
            stream = await client.beta.sessions.events.stream(
                session_id, extra_headers={"Last-Event-ID": str(input_seq - 1)}
            )
            async with stream:
                async for event in stream:
                    seq = event_sequence(event)
                    if seq < input_seq:
                        continue
                    event_type = str(field_value(event, "type", ""))
                    event_id = str(field_value(event, "id", "") or "")
                    raw = (
                        event.model_dump(mode="json")
                        if hasattr(event, "model_dump")
                        else event
                    )
                    signature = hashlib.sha256(
                        json.dumps(raw, sort_keys=True, default=str).encode()
                    ).hexdigest()
                    if seq in seen:
                        if seen[seq] != signature:
                            raise RuntimeError("conflicting duplicate event sequence")
                        continue
                    if seq <= last_seq:
                        raise RuntimeError("event sequence moved backwards")
                    seen[seq] = signature
                    last_seq = seq
                    summaries.append(
                        {
                            "sequence": seq,
                            "id": event_id,
                            "type": event_type,
                            "tool_use_id": field_value(event, "tool_use_id"),
                            "is_error": field_value(event, "is_error"),
                            "observed_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    if not boundary_seen:
                        if (
                            seq != input_seq
                            or event_id != input_id
                            or event_type != "user.message"
                        ):
                            raise RuntimeError(
                                "stream did not replay acknowledged user.message"
                            )
                        boundary_seen = True
                    elif event_type in {"user.message", "user.interrupt"}:
                        raise RuntimeError(f"unexpected concurrent {event_type}")
                    types_seen.append(event_type)
                    if event_type == "agent.tool_use":
                        if not event_id:
                            raise RuntimeError("tool use has no ID")
                        tool_uses.append(event_id)
                        last_tool_seq = seq
                    elif event_type == "agent.tool_result":
                        tool_id = str(field_value(event, "tool_use_id", "") or "")
                        if not tool_id or tool_id not in tool_uses:
                            raise RuntimeError(
                                "tool result has no matching preceding use"
                            )
                        tool_results.append(tool_id)
                        last_tool_seq = seq
                        if field_value(event, "is_error", False) is True:
                            tool_error_ids.append(tool_id)
                            detail = content_text(field_value(event, "content"))
                            tool_error_details.append(
                                sanitize_error_detail(detail or "tool execution failed")
                            )
                    elif event_type == "agent.message":
                        # A model may speak before invoking its tool. Only a
                        # message after all results is evidence of the final.
                        if tool_results and set(tool_uses) == set(tool_results):
                            final_parts.append(
                                content_text(field_value(event, "content"))
                            )
                            final_seq = seq
                    elif event_type in {"session.error", "session.status_terminated"}:
                        raise RuntimeError(f"terminal event {event_type}")
                    if event_type == "session.status_idle":
                        reason = field_value(
                            field_value(event, "stop_reason", {}), "type"
                        )
                        if reason != "end_turn":
                            raise RuntimeError("idle is not end_turn")
                        if final_seq <= last_tool_seq or not final_parts:
                            raise RuntimeError(
                                "idle arrived before final after tool results"
                            )
                        idle_seq = seq
                        break
            if not boundary_seen:
                raise RuntimeError("stream ended before acknowledged user.message")
            if environment_id:
                if not idle_seq:
                    raise RuntimeError("stream ended before end_turn idle")
                await verify_turn_settled(
                    client,
                    session_id,
                    environment_id,
                    input_id=input_id,
                    input_sequence=input_seq,
                    idle_sequence=idle_seq,
                    evidence=completion,
                    timeout=max(0.001, timeout - (time.monotonic() - started)),
                )
    except Exception as exc:  # noqa: BLE001
        # Return partial evidence so assertions, timeouts and transport errors
        # cannot erase the failed recovery turn from the final JSON artifact.
        error = sanitize_error_detail(f"{type(exc).__name__}: {exc}", limit=300)
    return {
        "input_event_id": input_id,
        "input_sequence": input_seq,
        "events": summaries,
        "error": error,
        "completion": completion,
        "elapsed": round(time.monotonic() - started, 3),
        "types": types_seen,
        "tool_uses": tool_uses,
        "tool_results": tool_results,
        "tool_error_ids": tool_error_ids,
        "tool_error_details": tool_error_details,
        "final": sanitize_error_detail(
            "\n".join(part for part in final_parts if part), limit=2000
        ),
    }


async def run_loss_during_active_tool(
    client, inspector, session_id: str, *, marker: str, timeout: float
) -> dict:
    started = time.monotonic()
    stream = await client.beta.sessions.events.stream(session_id)
    await client.beta.sessions.events.send(
        session_id,
        events=[
            {
                "type": "user.message",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Use bash exactly once to run: sleep 120; printf {marker}. "
                            f"Then reply with {marker}."
                        ),
                    }
                ],
            }
        ],
    )
    event_types = []
    physical = None
    deleted_at = None
    error = None
    try:
        async with stream:
            async with asyncio.timeout(timeout):
                async for event in stream:
                    event_type = str(field_value(event, "type", ""))
                    event_types.append(event_type)
                    if event_type == "agent.tool_use" and physical is None:
                        physical = await inspector.wait_present(session_id, timeout=120)
                        await asyncio.to_thread(
                            inspector.client.call,
                            "DeleteSession",
                            {
                                "ToolId": inspector.tool_id,
                                "SessionId": physical["session_id"],
                            },
                        )
                        deleted_at = time.monotonic()
                    if event_type == "session.status_idle":
                        break
    except Exception as exc:  # noqa: BLE001
        error = sanitize_error_detail(f"{type(exc).__name__}: {exc}", limit=300)
    if physical is None and error is not None:
        raise RuntimeError(f"physical lookup failed: {error}")
    if physical is None or deleted_at is None:
        raise AssertionError("fault preflight never observed a bound physical sandbox")
    return {
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "deleted_at_offset_seconds": round(deleted_at - started, 3),
        "event_types": event_types,
        "physical": physical,
        "error": error,
    }


async def session_work_snapshot(
    base_url: str,
    auth_token: str,
    environment_id: str,
    session_id: str,
    *,
    expected_work_ids: set[str] | None = None,
) -> dict:
    rows: list[dict] = []
    query_started_at = datetime.now(timezone.utc).isoformat()
    page: str | None = None
    seen_pages: set[str] = set()
    headers = {"Authorization": f"Bearer {auth_token}"}
    async with httpx.AsyncClient(timeout=30) as http:
        for page_index in range(100):
            params = {"limit": 100}
            if page:
                params["page"] = page
            response = await http.get(
                f"{base_url.rstrip('/')}/v1/environments/{environment_id}/work",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(
                payload.get("data"), list
            ):
                raise RuntimeError("Work response must be an object with a data list")
            if "next_page" not in payload:
                raise RuntimeError("Work response is missing next_page")
            for item in payload["data"]:
                if not isinstance(item, dict):
                    raise RuntimeError("Work response contains a non-object item")
                work_id = item.get("work_id") or item.get("id")
                owner = item.get("data")
                if not isinstance(work_id, str) or not work_id:
                    raise RuntimeError("Work response item is missing work_id/id")
                if not isinstance(owner, dict) or not isinstance(owner.get("id"), str):
                    raise RuntimeError(f"Work {work_id} has invalid data.id ownership")
                if item.get("type") != "work" or item.get("work_type") != "session":
                    raise RuntimeError(f"Work {work_id} has an invalid type/work_type")
                if owner.get("type") != "session":
                    raise RuntimeError(
                        f"Work {work_id} has invalid data.type ownership"
                    )
                if item.get("environment_id") != environment_id:
                    raise RuntimeError(
                        f"Work {work_id} belongs to an unexpected environment"
                    )
                if item.get("state") not in {"queued", "starting", "active", "stopped"}:
                    raise RuntimeError(f"Work {work_id} has an unknown state")
                if owner["id"] == session_id:
                    rows.append(item)
            next_page = payload["next_page"]
            if next_page is None:
                found = {str(item.get("work_id") or item.get("id")) for item in rows}
                missing = set(expected_work_ids or ()) - found
                if missing:
                    raise RuntimeError(
                        f"Work snapshot lost known IDs: {','.join(sorted(missing))}"
                    )
                return {
                    "complete": True,
                    "query_started_at": query_started_at,
                    "query_completed_at": datetime.now(timezone.utc).isoformat(),
                    "page_count": page_index + 1,
                    "rows": rows,
                }
            if not isinstance(next_page, str) or not next_page:
                raise RuntimeError("Work next_page must be a non-empty string or null")
            if next_page in seen_pages:
                raise RuntimeError("Work pagination repeated next_page")
            seen_pages.add(next_page)
            page = next_page
    raise RuntimeError("Work pagination exceeded 100 pages")


def summarize_work(rows: list[dict]) -> list[dict]:
    return [
        {
            "work_id": item.get("work_id") or item.get("id"),
            "state": item.get("state"),
            "created_at": item.get("created_at"),
            "started_at": item.get("started_at"),
            "latest_heartbeat_at": item.get("latest_heartbeat_at"),
            "stop_requested_at": item.get("stop_requested_at"),
            "stopped_at": item.get("stopped_at"),
        }
        for item in rows
    ]


async def main(args: argparse.Namespace) -> dict:
    inspector = AgentKitInspector(args.inspector_script, args.tool_id)
    async with anthropic.AsyncAnthropic(
        base_url=args.base_url.rstrip("/"),
        auth_token=args.auth_token,
        timeout=args.turn_timeout,
        max_retries=0,
    ) as client:
        session = await client.beta.sessions.create(
            agent=args.agent_id,
            environment_id=args.environment_id,
            title=f"soak fault preflight {uuid.uuid4().hex[:8]}",
        )
        logical_id = str(session.id)
        cleanup = "pending"
        result = {
            "logical_session_id": logical_id,
            "note": "Never merge this fault result into soak statistics.",
            "recovery_ok": False,
        }
        known_work_ids: set[str] = set()
        try:
            fault_marker = f"fault-a-{uuid.uuid4().hex[:8]}"
            fault = await run_loss_during_active_tool(
                client,
                inspector,
                logical_id,
                marker=fault_marker,
                timeout=args.turn_timeout,
            )
            result["fault_turn"] = fault
            if fault.get("error"):
                raise RuntimeError(f"fault turn did not finish: {fault['error']}")
            work_after_delete_snapshot = await session_work_snapshot(
                args.base_url, args.auth_token, args.environment_id, logical_id
            )
            work_after_delete_rows = work_after_delete_snapshot["rows"]
            if not work_after_delete_rows:
                raise RuntimeError(
                    "Work snapshot contains no Work for the fault Session"
                )
            known_work_ids = {
                str(item.get("work_id") or item.get("id"))
                for item in work_after_delete_rows
            }
            work_after_delete = summarize_work(work_after_delete_rows)
            absence_query_started_at = datetime.now(timezone.utc).isoformat()
            await inspector.wait_absent(logical_id, timeout=120)
            absence_query_completed_at = datetime.now(timezone.utc).isoformat()

            recovery_started = time.monotonic()
            second_marker = f"fault-b-{uuid.uuid4().hex[:8]}"
            recovery_error = None
            second = None
            second_physical = None
            try:
                second = await run_verified_tool_turn(
                    client,
                    logical_id,
                    marker=second_marker,
                    prompt=f"Use bash exactly once to run: printf {second_marker}. Reply with {second_marker}.",
                    timeout=args.recovery_timeout,
                    environment_id=args.environment_id,
                )
                assert_tool_turn(second, second_marker)
                second_physical = await inspector.wait_present(
                    logical_id, timeout=args.recovery_timeout
                )
                if second_physical["session_id"] == fault["physical"]["session_id"]:
                    raise AssertionError("recovery reused the deleted physical Session")
            except Exception as exc:  # noqa: BLE001
                recovery_error = sanitize_error_detail(
                    f"{type(exc).__name__}: {exc}", limit=300
                )
            result.update(
                {
                    "second_turn": second,
                    "second_physical": second_physical,
                    "recovery_error": recovery_error,
                }
            )
            work_after_recovery_snapshot = await session_work_snapshot(
                args.base_url,
                args.auth_token,
                args.environment_id,
                logical_id,
                expected_work_ids=known_work_ids,
            )
            work_after_recovery = summarize_work(work_after_recovery_snapshot["rows"])
            known_work_ids.update(
                item["work_id"] for item in work_after_recovery if item["work_id"]
            )
            result.update(
                {
                    "fault_turn": fault,
                    "second_turn": second,
                    "second_physical": second_physical,
                    "recovery_ok": recovery_error is None,
                    "recovery_error": recovery_error,
                    "recovery_turn_seconds": round(
                        time.monotonic() - recovery_started, 3
                    ),
                    "work_after_delete": work_after_delete,
                    "work_after_delete_query": {
                        key: value
                        for key, value in work_after_delete_snapshot.items()
                        if key != "rows"
                    },
                    "work_after_recovery": work_after_recovery,
                    "work_after_recovery_query": {
                        key: value
                        for key, value in work_after_recovery_snapshot.items()
                        if key != "rows"
                    },
                    "physical_absence_query_started_at": absence_query_started_at,
                    "physical_absence_query_completed_at": absence_query_completed_at,
                }
            )
        except Exception as exc:  # noqa: BLE001
            result["recovery_ok"] = False
            result["error"] = sanitize_error_detail(
                f"{type(exc).__name__}: {exc}", limit=300
            )
        finally:
            result["cleanup_started_at"] = datetime.now(timezone.utc).isoformat()
            physical_cleanup_query_started_at = None
            physical_cleanup_query_completed_at = None
            physical_cleanup_reclaimed = False
            physical_cleanup_error = None
            try:
                await client.beta.sessions.events.send(
                    logical_id, events=[{"type": "user.interrupt"}]
                )
                await client.beta.sessions.archive(logical_id)
                cleanup = "archived"
            except Exception as exc:  # noqa: BLE001
                cleanup = "archive_failed"
                physical_cleanup_error = sanitize_error_detail(
                    f"{type(exc).__name__}: {exc}", limit=300
                )
            physical_cleanup_query_started_at = datetime.now(timezone.utc).isoformat()
            try:
                await inspector.wait_absent(logical_id, timeout=args.recovery_timeout)
                physical_cleanup_reclaimed = True
            except Exception as exc:  # noqa: BLE001
                detail = sanitize_error_detail(
                    f"{type(exc).__name__}: {exc}", limit=300
                )
                physical_cleanup_error = (
                    f"{physical_cleanup_error}; {detail}"
                    if physical_cleanup_error
                    else detail
                )
            finally:
                physical_cleanup_query_completed_at = datetime.now(
                    timezone.utc
                ).isoformat()
            print(f"cleanup={cleanup}", file=sys.stderr)
        try:
            work_after_cleanup_snapshot = await session_work_snapshot(
                args.base_url,
                args.auth_token,
                args.environment_id,
                logical_id,
                expected_work_ids=known_work_ids,
            )
        except Exception as exc:  # noqa: BLE001
            result["recovery_ok"] = False
            work_after_cleanup_snapshot = {
                "complete": False,
                "rows": [],
                "error": sanitize_error_detail(
                    f"{type(exc).__name__}: {exc}", limit=300
                ),
            }
        work_after_cleanup = summarize_work(work_after_cleanup_snapshot["rows"])
        active_states = {"queued", "starting", "active"}
        result["cleanup"] = cleanup
        result["physical_cleanup_query_started_at"] = physical_cleanup_query_started_at
        result["physical_cleanup_query_completed_at"] = (
            physical_cleanup_query_completed_at
        )
        result["physical_cleanup_reclaimed"] = physical_cleanup_reclaimed
        result["physical_cleanup_error"] = physical_cleanup_error
        result["work_after_cleanup"] = work_after_cleanup
        result["work_after_cleanup_query"] = {
            key: value
            for key, value in work_after_cleanup_snapshot.items()
            if key != "rows"
        }
        result["orphan_work_after_cleanup"] = [
            item for item in work_after_cleanup if item["state"] in active_states
        ]
        return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default=os.getenv("MANAGED_AGENTS_GATEWAY"))
    p.add_argument("--agent-id", default=os.getenv("MANAGED_AGENTS_TEST_AGENT_ID"))
    p.add_argument("--environment-id", default=os.getenv("ANTHROPIC_ENVIRONMENT_ID"))
    p.add_argument(
        "--auth-token",
        default=os.getenv("MANAGED_AGENTS_GATEWAY_TOKEN", "gateway-client"),
    )
    p.add_argument("--tool-id", default=os.getenv("AGENTKIT_TOOL_ID"), required=False)
    p.add_argument("--turn-timeout", type=float, default=300)
    p.add_argument("--recovery-timeout", type=float, default=600)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--inspector-script",
        default=os.getenv(
            "AGENTKIT_TOOL_DEPLOY_SCRIPT",
            "",
        ),
    )
    return p


if __name__ == "__main__":
    args = parser().parse_args()
    if not all((args.base_url, args.agent_id, args.environment_id, args.tool_id)):
        raise SystemExit("base-url, agent-id, environment-id and tool-id are required")
    result = asyncio.run(main(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if (
        not result.get("recovery_ok")
        or result.get("cleanup") != "archived"
        or not result.get("physical_cleanup_reclaimed")
        or result.get("orphan_work_after_cleanup")
    ):
        raise SystemExit(1)
