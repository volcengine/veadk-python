#!/usr/bin/env python3
# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

"""Minimal single-session preflight against the ma-infra unified gateway.

Proves one logical Session runs a plain streamed turn plus one real bash tool
turn end-to-end (user.message -> event_delta -> agent.tool_use/result -> final
-> session.status_idle). Prints the logical Session ID and, when the
AgentKit control-plane helper is available, the mapped physical sandbox
Session ID. No credentials are printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import anthropic

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anthropic_gateway_e2e import (  # noqa: E402
    AgentKitInspector,
    content_text,
    field_value,
)

_SAFE_EVENT_VALUE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def safe_event_value(value):
    text = str(value or "").strip()
    return text if _SAFE_EVENT_VALUE.fullmatch(text) else ""


def append_event_trace(path, *, turn, event=None, error_type=None):
    if path is None:
        return
    payload = {"turn": safe_event_value(turn)}
    if event is not None:
        payload.update(
            {
                "type": safe_event_value(field_value(event, "type", "")),
                "id": safe_event_value(field_value(event, "id", "")),
                "event_id": safe_event_value(field_value(event, "event_id", "")),
                "tool_use_id": safe_event_value(field_value(event, "tool_use_id", "")),
                "is_error": field_value(event, "is_error", None)
                if isinstance(field_value(event, "is_error", None), bool)
                else None,
                "sequence": int(field_value(event, "sequence", 0) or 0),
            }
        )
    if error_type is not None:
        payload.update(
            {
                "type": "probe.error",
                "error_type": safe_event_value(error_type),
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        output.write("\n")


async def run_turn(client, session_id, *, marker, prompt, timeout, event_output=None):
    started = time.monotonic()
    types_seen = []
    tool_uses = []
    tool_results = []
    final_parts = []
    first_delta = None
    saw_current_turn = False
    after_sequence = 0
    async for existing in client.beta.sessions.events.list(
        session_id, limit=1, order="desc"
    ):
        after_sequence = int(field_value(existing, "sequence", 0) or 0)
        break
    try:
        stream = await client.beta.sessions.events.stream(
            session_id,
            event_deltas=["agent.message"],
            extra_query={"page": str(after_sequence)},
        )
        await client.beta.sessions.events.send(
            session_id,
            events=[
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": prompt}],
                }
            ],
        )
        async with stream:
            async with asyncio.timeout(timeout):
                async for event in stream:
                    et = str(field_value(event, "type", ""))
                    sequence = int(field_value(event, "sequence", 0) or 0)
                    if sequence and sequence <= after_sequence:
                        continue
                    append_event_trace(event_output, turn=marker, event=event)
                    types_seen.append(et)
                    if et in {
                        "event_delta",
                        "agent.message",
                        "agent.tool_use",
                        "agent.tool_result",
                        "session.error",
                        "session.status_terminated",
                    }:
                        saw_current_turn = True
                    if et == "event_delta" and first_delta is None:
                        delta = field_value(event, "delta")
                        if content_text([field_value(delta, "content")]):
                            first_delta = time.monotonic() - started
                    elif et == "agent.message":
                        final_parts.append(content_text(field_value(event, "content")))
                    elif et == "agent.tool_use":
                        cid = str(field_value(event, "id", "") or "")
                        if cid:
                            tool_uses.append(cid)
                    elif et == "agent.tool_result":
                        tid = str(field_value(event, "tool_use_id", "") or "")
                        if tid:
                            tool_results.append(tid)
                    elif et in {"session.error", "session.status_terminated"}:
                        raise RuntimeError(f"terminal event {et}")
                    if et == "session.status_idle" and saw_current_turn:
                        break
    except Exception as exc:
        append_event_trace(event_output, turn=marker, error_type=type(exc).__name__)
        raise
    return {
        "marker": marker,
        "elapsed": round(time.monotonic() - started, 3),
        "first_delta": first_delta,
        "types": types_seen,
        "tool_uses": tool_uses,
        "tool_results": tool_results,
        "final": "\n".join(p for p in final_parts if p),
    }


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default=os.getenv("MANAGED_AGENTS_GATEWAY"))
    p.add_argument("--agent-id", default=os.getenv("MANAGED_AGENTS_TEST_AGENT_ID"))
    p.add_argument("--environment-id", default=os.getenv("ANTHROPIC_ENVIRONMENT_ID"))
    p.add_argument(
        "--auth-token",
        default=os.getenv("MANAGED_AGENTS_GATEWAY_TOKEN", "gateway-client"),
    )
    p.add_argument("--turn-timeout", type=float, default=300)
    p.add_argument("--tool-id", default=os.getenv("AGENTKIT_TOOL_ID"))
    p.add_argument("--with-inspector", action="store_true")
    p.add_argument(
        "--event-output",
        type=Path,
        default=Path(
            os.getenv(
                "MANAGED_AGENTS_PREFLIGHT_EVENTS",
                Path(__file__).with_name("deploy_records") / "tool_probe_events.jsonl",
            )
        ),
    )
    args = p.parse_args()

    inspector = None
    session_id = None
    success = False
    if args.with_inspector and args.tool_id:
        try:
            inspector = AgentKitInspector(
                os.getenv(
                    "AGENTKIT_TOOL_DEPLOY_SCRIPT",
                    "",
                ),
                args.tool_id,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[inspector-disabled] {type(exc).__name__}: {exc}")

    async with anthropic.AsyncAnthropic(
        base_url=args.base_url.rstrip("/"),
        auth_token=args.auth_token,
        timeout=args.turn_timeout,
    ) as client:
        session = await client.beta.sessions.create(
            agent=args.agent_id, environment_id=args.environment_id, title="preflight"
        )
        sid = str(session.id)
        session_id = sid
        print(f"logical_session={sid}")

        pm = f"plain-{uuid.uuid4().hex[:8]}"
        plain = await run_turn(
            client,
            sid,
            marker=pm,
            prompt=f"Do not use any tool. Reply with exactly: {pm}",
            timeout=args.turn_timeout,
            event_output=args.event_output,
        )
        print(
            f"[plain] elapsed={plain['elapsed']}s first_delta={plain['first_delta']} "
            f"final_ok={pm in plain['final']}"
        )
        plain_ok = plain["first_delta"] is not None and pm in plain["final"]

        tm = f"tool-{uuid.uuid4().hex[:8]}"
        tool = await run_turn(
            client,
            sid,
            marker=tm,
            prompt=f"Use the bash tool exactly once to run: printf {tm}. "
            f"Then include exactly {tm} in your final reply.",
            timeout=args.turn_timeout,
            event_output=args.event_output,
        )
        matched = set(tool["tool_uses"]) and set(tool["tool_uses"]) <= set(
            tool["tool_results"]
        )
        print(
            f"[tool] elapsed={tool['elapsed']}s tool_uses={len(tool['tool_uses'])} "
            f"tool_results={len(tool['tool_results'])} matched={bool(matched)} "
            f"final_ok={tm in tool['final']}"
        )
        tool_ok = (
            bool(matched)
            and tm in tool["final"]
            and "session.status_idle" in tool["types"]
        )

        if inspector is not None:
            try:
                phys = await inspector.for_managed_session(sid)
                print(f"physical_sandboxes={[x['session_id'] for x in phys]}")
                for x in phys:
                    print(
                        f"  physical: session_id={x['session_id']} status={x['status']} "
                        f"user_session_id={x['user_session_id']}"
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"[inspector-query-failed] {type(exc).__name__}: {exc}")
        success = plain_ok and tool_ok
        try:
            await client.beta.sessions.archive(sid)
            print(f"archived_session={sid}")
        except Exception as exc:  # noqa: BLE001
            print(f"[archive-failed] {type(exc).__name__}: {exc}")
            success = False
    if not success:
        print(f"preflight_failed session={session_id}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
