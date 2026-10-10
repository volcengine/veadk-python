#!/usr/bin/env python3
# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

"""Official Anthropic SDK E2E for the Managed Agents public gateway.

Conversation operations use only ``anthropic.AsyncAnthropic``. Optional
AgentKit control-plane inspection is used solely to prove physical sandbox
creation, reclamation, and replacement; signed endpoints and credentials are
never printed or written to the result file.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import anthropic
from dotenv import load_dotenv

DEFAULT_TOOL_ID = os.getenv("AGENTKIT_TOOL_ID", "")
DEFAULT_AGENTKIT_HELPER = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def field_value(value: Any, name: str, default: Any = None) -> Any:
    return (
        value.get(name, default)
        if isinstance(value, dict)
        else getattr(value, name, default)
    )


def content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(
        str(field_value(block, "text", "") or "")
        for block in content or []
        if field_value(block, "type") == "text"
    )


@dataclass
class ObservedEvent:
    type: str
    elapsed_seconds: float
    event_id: str | None = None
    link_id: str | None = None
    text: str = ""


@dataclass
class TurnResult:
    session_id: str
    marker: str
    started_at: str
    elapsed_seconds: float
    first_delta_seconds: float | None
    final_message_seconds: float | None
    event_types: list[str]
    tool_use_ids: list[str]
    tool_result_ids: list[str]
    final_text: str
    observations: list[ObservedEvent] = field(default_factory=list)

    def assert_complete(self, *, require_stream: bool, require_tool: bool) -> None:
        if "session.status_running" not in self.event_types:
            raise AssertionError(f"{self.session_id}: missing session.status_running")
        if "session.status_idle" not in self.event_types:
            raise AssertionError(f"{self.session_id}: missing session.status_idle")
        if self.marker not in self.final_text:
            raise AssertionError(
                f"{self.session_id}: final response did not contain {self.marker!r}"
            )
        if require_stream:
            if self.first_delta_seconds is None:
                raise AssertionError(f"{self.session_id}: no event_delta was streamed")
            if self.final_message_seconds is None:
                raise AssertionError(f"{self.session_id}: no final agent.message")
            if self.first_delta_seconds >= self.final_message_seconds:
                raise AssertionError(
                    f"{self.session_id}: first delta did not precede the final message"
                )
        if require_tool:
            if not self.tool_use_ids:
                raise AssertionError(f"{self.session_id}: no agent.tool_use")
            if not self.tool_result_ids:
                raise AssertionError(f"{self.session_id}: no agent.tool_result")
            missing = set(self.tool_use_ids) - set(self.tool_result_ids)
            if missing:
                raise AssertionError(
                    f"{self.session_id}: tool calls without results: {sorted(missing)}"
                )


class AgentKitInspector:
    def __init__(self, helper_path: str, tool_id: str) -> None:
        path = Path(helper_path)
        if not path.is_file():
            raise FileNotFoundError(f"AgentKit helper not found: {path}")
        spec = importlib.util.spec_from_file_location("agentkit_tool_e2e_helper", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load AgentKit helper: {path}")
        helper_dir = str(path.parent)
        if helper_dir not in sys.path:
            sys.path.insert(0, helper_dir)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.module: ModuleType = module
        dotenv = os.getenv("AGENTKIT_DOTENV", str(Path(__file__).with_name(".env")))
        module.load_dotenv(dotenv)
        args = SimpleNamespace(
            bp=False,
            access_key=None,
            secret_key=None,
            region=None,
            service=None,
        )
        auth = module.require_credentials(args)
        self.client = module.AgentkitClient(
            os.getenv("AGENTKIT_ENDPOINT", module.DEFAULT_ENDPOINT),
            os.getenv("AGENTKIT_VERSION", module.DEFAULT_VERSION),
            auth,
            timeout=60,
            verbose=False,
        )
        self.tool_id = tool_id

    async def sessions(self) -> list[dict[str, str]]:
        infos = await asyncio.to_thread(
            self.module.list_all_sessions, self.client, self.tool_id, 100
        )
        return [
            {
                "session_id": str(item.get("SessionId") or ""),
                "user_session_id": str(item.get("UserSessionId") or ""),
                "status": str(item.get("Status") or ""),
                "created_at": str(item.get("CreatedAt") or ""),
            }
            for item in infos
        ]

    async def for_managed_session(self, session_id: str) -> list[dict[str, str]]:
        return [
            item
            for item in await self.sessions()
            if item["user_session_id"] == session_id
        ]

    async def wait_present(self, session_id: str, *, timeout: float) -> dict[str, str]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            matches = await self.for_managed_session(session_id)
            ready = next((item for item in matches if item["status"] == "Ready"), None)
            if ready:
                return ready
            await asyncio.sleep(2)
        raise TimeoutError(f"AgentKit sandbox did not become Ready for {session_id}")

    async def wait_absent(self, session_id: str, *, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not await self.for_managed_session(session_id):
                return
            await asyncio.sleep(3)
        raise TimeoutError(f"AgentKit sandbox was not reclaimed for {session_id}")


async def create_session(
    client: anthropic.AsyncAnthropic, *, agent_id: str, environment_id: str, title: str
) -> str:
    session = await client.beta.sessions.create(
        agent=agent_id, environment_id=environment_id, title=title
    )
    return str(session.id)


async def run_turn(
    client: anthropic.AsyncAnthropic,
    session_id: str,
    *,
    marker: str,
    prompt: str,
    timeout: float,
    ready_gate: asyncio.Event | None = None,
    ready_counter: list[int] | None = None,
    ready_total: int | None = None,
) -> TurnResult:
    started = time.monotonic()
    observations: list[ObservedEvent] = []
    event_types: list[str] = []
    tool_uses: list[str] = []
    tool_results: list[str] = []
    final_text_parts: list[str] = []
    first_delta: float | None = None
    final_message: float | None = None

    stream = await client.beta.sessions.events.stream(
        session_id, event_deltas=["agent.message"]
    )
    if ready_gate is not None and ready_counter is not None and ready_total is not None:
        ready_counter[0] += 1
        if ready_counter[0] == ready_total:
            ready_gate.set()
        await ready_gate.wait()

    await client.beta.sessions.events.send(
        session_id,
        events=[
            {"type": "user.message", "content": [{"type": "text", "text": prompt}]}
        ],
    )

    async with stream:
        async with asyncio.timeout(timeout):
            async for event in stream:
                elapsed = time.monotonic() - started
                event_type = str(field_value(event, "type", ""))
                event_types.append(event_type)
                event_id = str(field_value(event, "id", "") or "") or None
                link_id: str | None = None
                text = ""
                if event_type == "event_delta":
                    link_id = str(field_value(event, "event_id", "") or "") or None
                    delta = field_value(event, "delta")
                    text = content_text([field_value(delta, "content")])
                    if text and first_delta is None:
                        first_delta = elapsed
                elif event_type == "event_start":
                    preview = field_value(event, "event")
                    link_id = str(field_value(preview, "id", "") or "") or None
                elif event_type == "agent.message":
                    text = content_text(field_value(event, "content"))
                    final_text_parts.append(text)
                    final_message = elapsed
                elif event_type == "agent.tool_use":
                    call_id = str(field_value(event, "id", "") or "")
                    if call_id:
                        tool_uses.append(call_id)
                elif event_type == "agent.tool_result":
                    link_id = str(field_value(event, "tool_use_id", "") or "") or None
                    if link_id:
                        tool_results.append(link_id)
                    text = content_text(field_value(event, "content"))
                observations.append(
                    ObservedEvent(event_type, elapsed, event_id, link_id, text[:500])
                )
                if event_type in {"session.error", "session.status_terminated"}:
                    raise RuntimeError(
                        f"{session_id}: terminal failure event {event_type}"
                    )
                if event_type == "session.status_idle":
                    break

    result = TurnResult(
        session_id=session_id,
        marker=marker,
        started_at=now_iso(),
        elapsed_seconds=time.monotonic() - started,
        first_delta_seconds=first_delta,
        final_message_seconds=final_message,
        event_types=event_types,
        tool_use_ids=tool_uses,
        tool_result_ids=tool_results,
        final_text="\n".join(part for part in final_text_parts if part),
        observations=observations,
    )
    return result


async def smoke(
    client: anthropic.AsyncAnthropic,
    args: argparse.Namespace,
    inspector: AgentKitInspector | None,
) -> dict[str, Any]:
    session_id = await create_session(
        client,
        agent_id=args.agent_id,
        environment_id=args.environment_id,
        title="SDK streaming smoke",
    )
    plain_marker = f"plain-{uuid.uuid4().hex[:12]}"
    plain = await run_turn(
        client,
        session_id,
        marker=plain_marker,
        prompt=f"Do not use any tool. Reply with exactly: {plain_marker}",
        timeout=args.turn_timeout,
    )
    plain.assert_complete(require_stream=True, require_tool=False)
    if inspector is not None and await inspector.for_managed_session(session_id):
        raise AssertionError(
            "plain user message unexpectedly started an AgentKit sandbox"
        )

    tool_marker = f"tool-{uuid.uuid4().hex[:12]}"
    tool = await run_turn(
        client,
        session_id,
        marker=tool_marker,
        prompt=(
            f"Use the bash tool exactly once to run: printf {tool_marker}. "
            f"Then include exactly {tool_marker} in your final reply."
        ),
        timeout=args.turn_timeout,
    )
    tool.assert_complete(require_stream=True, require_tool=True)
    physical = (
        await inspector.wait_present(session_id, timeout=120) if inspector else None
    )
    return {
        "session_id": session_id,
        "plain": asdict(plain),
        "tool": asdict(tool),
        "physical": physical,
    }


async def lifecycle(
    client: anthropic.AsyncAnthropic,
    args: argparse.Namespace,
    inspector: AgentKitInspector,
) -> dict[str, Any]:
    session_id = await create_session(
        client,
        agent_id=args.agent_id,
        environment_id=args.environment_id,
        title="SDK sandbox lifecycle",
    )
    first_marker = f"life-a-{uuid.uuid4().hex[:10]}"
    first = await run_turn(
        client,
        session_id,
        marker=first_marker,
        prompt=f"Use bash exactly once to run: printf {first_marker}. Reply with {first_marker}.",
        timeout=args.turn_timeout,
    )
    first.assert_complete(require_stream=True, require_tool=True)
    first_sandbox = await inspector.wait_present(session_id, timeout=120)
    idle_at = time.monotonic()
    await inspector.wait_absent(session_id, timeout=args.reclaim_timeout)
    wait_remaining = args.restart_after - (time.monotonic() - idle_at)
    if wait_remaining > 0:
        await asyncio.sleep(wait_remaining)

    second_marker = f"life-b-{uuid.uuid4().hex[:10]}"
    second = await run_turn(
        client,
        session_id,
        marker=second_marker,
        prompt=f"Use bash exactly once to run: printf {second_marker}. Reply with {second_marker}.",
        timeout=args.turn_timeout,
    )
    second.assert_complete(require_stream=True, require_tool=True)
    second_sandbox = await inspector.wait_present(session_id, timeout=120)
    if first_sandbox["session_id"] == second_sandbox["session_id"]:
        raise AssertionError("AgentKit reused the reclaimed physical sandbox ID")
    return {
        "session_id": session_id,
        "first": asdict(first),
        "second": asdict(second),
        "first_sandbox": first_sandbox,
        "second_sandbox": second_sandbox,
        "restart_after_seconds": args.restart_after,
    }


async def interrupt(
    client: anthropic.AsyncAnthropic,
    args: argparse.Namespace,
    inspector: AgentKitInspector,
) -> dict[str, Any]:
    session_id = await create_session(
        client,
        agent_id=args.agent_id,
        environment_id=args.environment_id,
        title="SDK interrupt",
    )
    marker = f"interrupt-{uuid.uuid4().hex[:10]}"
    started = time.monotonic()
    stream = await client.beta.sessions.events.stream(
        session_id, event_deltas=["agent.message"]
    )
    await client.beta.sessions.events.send(
        session_id,
        events=[
            {
                "type": "user.message",
                "content": [
                    {
                        "type": "text",
                        "text": f"Use bash to run: sleep 120; printf {marker}. Then reply with the output.",
                    }
                ],
            }
        ],
    )
    seen: list[str] = []
    interrupted_at: float | None = None
    async with stream:
        async with asyncio.timeout(args.turn_timeout):
            async for event in stream:
                event_type = str(field_value(event, "type", ""))
                seen.append(event_type)
                if event_type == "agent.tool_use" and interrupted_at is None:
                    await inspector.wait_present(session_id, timeout=120)
                    await asyncio.sleep(2)
                    await client.beta.sessions.events.send(
                        session_id, events=[{"type": "user.interrupt"}]
                    )
                    interrupted_at = time.monotonic()
                if event_type == "agent.tool_result":
                    text = content_text(field_value(event, "content"))
                    if marker in text:
                        raise AssertionError(
                            "interrupted shell command completed with its marker"
                        )
                if event_type == "session.status_idle" and interrupted_at is not None:
                    break
    if interrupted_at is None:
        raise AssertionError("interrupt test never observed agent.tool_use")
    await inspector.wait_absent(session_id, timeout=60)
    return {
        "session_id": session_id,
        "event_types": seen,
        "elapsed_seconds": time.monotonic() - started,
        "interrupt_to_idle_seconds": time.monotonic() - interrupted_at,
    }


async def concurrency(
    client: anthropic.AsyncAnthropic,
    args: argparse.Namespace,
    inspector: AgentKitInspector,
) -> dict[str, Any]:
    count = args.concurrency
    sessions = []
    for index in range(count):
        sessions.append(
            await create_session(
                client,
                agent_id=args.agent_id,
                environment_id=args.environment_id,
                title=f"SDK concurrency {index:02d} {uuid.uuid4().hex[:8]}",
            )
        )
    if len(set(sessions)) != count:
        raise AssertionError("concurrent Session creation returned duplicate IDs")
    markers = [f"c{index:02d}-{uuid.uuid4().hex[:12]}" for index in range(count)]
    gate = asyncio.Event()
    ready = [0]

    async def one(index: int) -> TurnResult:
        marker = markers[index]
        result = await run_turn(
            client,
            sessions[index],
            marker=marker,
            prompt=(
                "Use the bash tool exactly once to run: "
                f"started=$(date +%s%3N); sleep {args.concurrency_hold_seconds}; "
                "ended=$(date +%s%3N); "
                f'printf \'{marker} %s %s\' "$started" "$ended". '
                f"Reply with exactly {marker}."
            ),
            timeout=args.turn_timeout,
            ready_gate=gate,
            ready_counter=ready,
            ready_total=count,
        )
        result.assert_complete(require_stream=True, require_tool=True)
        return result

    started = time.monotonic()
    turns = asyncio.gather(*(one(index) for index in range(count)))
    peak_physical: dict[str, dict[str, str]] = {}
    while not turns.done():
        current = {
            item["user_session_id"]: item
            for item in await inspector.sessions()
            if item["user_session_id"] in sessions
        }
        if len(current) > len(peak_physical):
            peak_physical = current
        await asyncio.sleep(1)
    results = await turns
    for index, result in enumerate(results):
        all_text = (
            "\n".join(item.text for item in result.observations)
            + "\n"
            + result.final_text
        )
        leaked = [
            marker
            for pos, marker in enumerate(markers)
            if pos != index and marker in all_text
        ]
        if leaked:
            raise AssertionError(f"{result.session_id}: cross-session markers {leaked}")
    physical = {
        item["user_session_id"]: item
        for item in await inspector.sessions()
        if item["user_session_id"] in sessions
    }
    if len(physical) > len(peak_physical):
        peak_physical = physical
    if len(peak_physical) != count:
        missing = sorted(set(sessions) - set(peak_physical))
        raise AssertionError(
            f"expected {count} simultaneously retained physical sandboxes, "
            f"observed {len(peak_physical)}; missing={missing}"
        )
    physical_ids = [item["session_id"] for item in peak_physical.values()]
    if len(set(physical_ids)) != count:
        raise AssertionError("concurrent logical Sessions shared a physical sandbox")

    intervals: list[tuple[int, int]] = []
    for index, result in enumerate(results):
        tool_text = "\n".join(
            item.text
            for item in result.observations
            if item.type == "agent.tool_result"
        )
        match = re.search(
            rf"{re.escape(markers[index])}\s+(\d{{10,}})\s+(\d{{10,}})",
            tool_text,
        )
        if match is None:
            raise AssertionError(
                f"{result.session_id}: missing tool execution timestamps"
            )
        interval = (int(match.group(1)), int(match.group(2)))
        if interval[1] <= interval[0]:
            raise AssertionError(
                f"{result.session_id}: invalid tool execution interval {interval}"
            )
        intervals.append(interval)
    edges = sorted(
        [(start, 1) for start, _ in intervals] + [(end, -1) for _, end in intervals],
        key=lambda item: (item[0], -item[1]),
    )
    active = 0
    max_tool_overlap = 0
    for _, delta in edges:
        active += delta
        max_tool_overlap = max(max_tool_overlap, active)
    if max_tool_overlap != count:
        raise AssertionError(
            f"expected {count} overlapping bash executions, observed {max_tool_overlap}"
        )
    return {
        "concurrency": count,
        "elapsed_seconds": time.monotonic() - started,
        "sessions": [result.session_id for result in results],
        "physical_sessions": peak_physical,
        "peak_physical_sessions": len(peak_physical),
        "tool_execution_intervals_ms": intervals,
        "max_overlapping_tool_executions": max_tool_overlap,
        "results": [asdict(result) for result in results],
        "first_delta_seconds": [result.first_delta_seconds for result in results],
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument(
        "--mode",
        choices=(
            "conversation",
            "smoke",
            "interrupt",
            "lifecycle",
            "concurrency",
            "all",
        ),
        default="all",
    )
    value.add_argument(
        "--base-url",
        default=os.getenv("MANAGED_AGENTS_GATEWAY") or os.getenv("ANTHROPIC_BASE_URL"),
        required=not (
            os.getenv("MANAGED_AGENTS_GATEWAY") or os.getenv("ANTHROPIC_BASE_URL")
        ),
    )
    value.add_argument(
        "--auth-token",
        default=os.getenv("MANAGED_AGENTS_GATEWAY_TOKEN")
        or os.getenv("ANTHROPIC_ENVIRONMENT_KEY"),
        required=not (
            os.getenv("MANAGED_AGENTS_GATEWAY_TOKEN")
            or os.getenv("ANTHROPIC_ENVIRONMENT_KEY")
        ),
    )
    value.add_argument(
        "--agent-id",
        default=os.getenv("MANAGED_AGENTS_TEST_AGENT_ID"),
        required=os.getenv("MANAGED_AGENTS_TEST_AGENT_ID") is None,
    )
    value.add_argument(
        "--environment-id",
        default=os.getenv("ANTHROPIC_ENVIRONMENT_ID"),
        required=os.getenv("ANTHROPIC_ENVIRONMENT_ID") is None,
    )
    value.add_argument("--concurrency", type=int, default=40)
    value.add_argument("--concurrency-hold-seconds", type=int, default=90)
    value.add_argument("--turn-timeout", type=float, default=600)
    value.add_argument("--reclaim-timeout", type=float, default=300)
    value.add_argument("--restart-after", type=float, default=300)
    value.add_argument("--tool-id", default=DEFAULT_TOOL_ID)
    value.add_argument(
        "--agentkit-helper",
        default=os.getenv("AGENTKIT_TOOL_DEPLOY_SCRIPT", DEFAULT_AGENTKIT_HELPER),
    )
    value.add_argument("--output", type=Path)
    return value


async def async_main(args: argparse.Namespace) -> dict[str, Any]:
    if args.concurrency < 1:
        raise ValueError("concurrency must be positive")
    if args.concurrency_hold_seconds < 1:
        raise ValueError("concurrency hold seconds must be positive")
    modes = (
        ["smoke", "interrupt", "lifecycle", "concurrency"]
        if args.mode == "all"
        else [args.mode]
    )
    inspector = (
        AgentKitInspector(args.agentkit_helper, args.tool_id)
        if any(
            mode in {"smoke", "interrupt", "lifecycle", "concurrency"} for mode in modes
        )
        else None
    )
    output: dict[str, Any] = {
        "started_at": now_iso(),
        "base_url": args.base_url,
        "agent_id": args.agent_id,
        "environment_id": args.environment_id,
        "modes": modes,
    }
    async with anthropic.AsyncAnthropic(
        base_url=args.base_url.rstrip("/"),
        auth_token=args.auth_token,
        timeout=args.turn_timeout,
    ) as client:
        if "conversation" in modes:
            session_id = await create_session(
                client,
                agent_id=args.agent_id,
                environment_id=args.environment_id,
                title="SDK conversation verification",
            )
            print(f"Created test session {session_id}", file=sys.stderr, flush=True)
            try:
                marker = f"conversation-{uuid.uuid4().hex[:12]}"
                result = await run_turn(
                    client,
                    session_id,
                    marker=marker,
                    prompt=f"Do not use any tool. Reply with exactly: {marker}",
                    timeout=args.turn_timeout,
                )
                result.assert_complete(require_stream=True, require_tool=False)
                output["conversation"] = asdict(result)
            finally:
                # Idle may precede the Work acknowledgement. Interrupt only
                # this test Session so queued/running Work cannot block cleanup.
                await client.beta.sessions.events.send(
                    session_id, events=[{"type": "user.interrupt"}]
                )
                await client.beta.sessions.events.send(
                    session_id, events=[{"type": "session.status_terminated"}]
                )
                await client.beta.sessions.archive(session_id)
            output["session_archived"] = True
        if "smoke" in modes:
            output["smoke"] = await smoke(client, args, inspector)
        if "interrupt" in modes:
            assert inspector is not None
            output["interrupt"] = await interrupt(client, args, inspector)
        if "lifecycle" in modes:
            assert inspector is not None
            output["lifecycle"] = await lifecycle(client, args, inspector)
        if "concurrency" in modes:
            assert inspector is not None
            output["concurrency"] = await concurrency(client, args, inspector)
    output["completed_at"] = now_iso()
    output["status"] = "passed"
    return output


def main() -> int:
    # Match this example's configuration without overriding exported values.
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    args = parser().parse_args()
    result = asyncio.run(async_main(args))
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
