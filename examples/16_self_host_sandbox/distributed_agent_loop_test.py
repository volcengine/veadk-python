#!/usr/bin/env python3
# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

"""Three-worker canonical Session ledger and Ark continuation smoke test.

Requires an isolated empty environment and an existing test Agent configured
with an Ark model, Session credential references and native bash permissions."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import anthropic


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
STATE_DIR = SCRIPT_DIR / ".local-managed-agents"


def _headers() -> dict[str, str]:
    headers = {"anthropic-beta": "managed-agents-2026-04-01"}
    if account_id := os.getenv("X_TOP_ACCOUNT_ID"):
        headers["X-Top-Account-Id"] = account_id
    return headers


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        base_url=os.environ["ANTHROPIC_BASE_URL"],
        auth_token=os.environ["ANTHROPIC_ENVIRONMENT_KEY"],
        default_headers=_headers(),
        timeout=60,
    )


def _events(client: anthropic.Anthropic, session_id: str) -> list[Any]:
    return list(client.beta.sessions.events.list(session_id, limit=1000, order="asc"))


def _text(event: Any) -> str:
    return "\n".join(
        str(getattr(block, "text", "") or "")
        for block in (getattr(event, "content", None) or [])
        if getattr(block, "type", None) == "text"
    )


def _wait_for_turn(
    client: anthropic.Anthropic,
    session_id: str,
    user_event_id: str,
    timeout: float = 180,
) -> tuple[list[Any], str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = _events(client, session_id)
        start = next(
            (
                index
                for index, event in enumerate(events)
                if getattr(event, "id", None) == user_event_id
            ),
            None,
        )
        if start is not None:
            turn = events[start:]
            if any(getattr(event, "type", None) == "session.error" for event in turn):
                errors = [
                    str(getattr(event, "error", ""))
                    for event in turn
                    if event.type == "session.error"
                ]
                raise RuntimeError(f"Agent Loop failed: {errors}")
            if any(
                getattr(event, "type", None) == "session.status_idle" for event in turn
            ):
                answers = [
                    _text(event) for event in turn if event.type == "agent.message"
                ]
                return turn, "\n".join(answer for answer in answers if answer)
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for session {session_id}")


def _send(client: anthropic.Anthropic, session_id: str, message: str) -> str:
    response = client.beta.sessions.events.send(
        session_id,
        events=[
            {"type": "user.message", "content": [{"type": "text", "text": message}]}
        ],
    )
    if not response.data:
        raise RuntimeError("Task Server did not return the persisted user.message")
    return response.data[0].id


def _start_worker(worker_id: str) -> tuple[subprocess.Popen[str], Path]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = STATE_DIR / f"{worker_id}.log"
    log = log_path.open("w")
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    worker_workdir = STATE_DIR / "workspaces" / worker_id
    worker_workdir.mkdir(parents=True, exist_ok=True)
    env["MANAGED_AGENT_WORKDIR"] = str(worker_workdir)
    env["MANAGED_AGENT_READY_FILE"] = str(STATE_DIR / f"{worker_id}.ready")
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT), str(SCRIPT_DIR), env.get("PYTHONPATH", "")]
    )
    process = subprocess.Popen(
        [
            sys.executable,
            str(SCRIPT_DIR / "main.py"),
            "--managed-agent-worker",
            "--worker-id",
            worker_id,
            "--max-work-items",
            "1",
            "--managed-agent-readiness-probe",
        ],
        cwd=SCRIPT_DIR,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log.close()
    return process, log_path


def _wait_for_workers_ready(
    workers: dict[str, subprocess.Popen[str]],
    logs: dict[str, Path],
    timeout: float = 30,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        failed = {
            name: process.returncode
            for name, process in workers.items()
            if (process.poll() is not None and process.returncode != 0)
        }
        if failed:
            raise RuntimeError(f"Workers exited before becoming ready: {failed}")
        ready = {
            name
            for name, path in logs.items()
            if path.exists()
            and f"MANAGED_AGENT_WORKER_READY worker_id={name}" in path.read_text()
        }
        if ready == set(workers):
            return
        time.sleep(0.2)
    raise TimeoutError(f"Workers did not all become ready: {sorted(ready)}")


def _wait_for_new_claim(
    logs: dict[str, Path],
    session_id: str,
    seen_work_ids: set[str],
    timeout: float = 10,
) -> tuple[str, str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        claims = [
            (name, work_id)
            for name, path in logs.items()
            for work_id in _claim_ids(path, session_id)
            if work_id not in seen_work_ids
        ]
        if len(claims) == 1:
            return claims[0]
        if len(claims) > 1:
            raise RuntimeError(f"More than one worker claimed the new turn: {claims}")
        time.sleep(0.2)
    raise TimeoutError(f"No new worker claim found for {session_id}")


def _wait_for_work_stopped(
    client: anthropic.Anthropic, environment_id: str, work_id: str, timeout: float = 15
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        work = client.beta.environments.work.retrieve(
            work_id, environment_id=environment_id
        )
        if work.state == "stopped":
            if not work.acknowledged_at or not work.stopped_at:
                raise AssertionError(f"Stopped work lacks lifecycle timestamps: {work}")
            return
        time.sleep(0.2)
    raise TimeoutError(f"Work item {work_id} did not reach stopped")


def _claim_ids(path: Path, session_id: str) -> list[str]:
    if not path.exists():
        return []
    return re.findall(
        rf"MANAGED_AGENT_WORK_CLAIM .*?work_id=(\S+) session_id={re.escape(session_id)}(?:\s|$)",
        path.read_text(),
    )


def _wait_for_initial_user_message(
    client: anthropic.Anthropic,
    session_id: str,
    expected_text: str,
    timeout: float = 10,
) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for event in _events(client, session_id):
            if event.type == "user.message" and _text(event) == expected_text:
                return event.id
        time.sleep(0.2)
    raise TimeoutError(f"Initial user.message was not persisted for {session_id}")


def _wait_for_worker_exit(
    worker_id: str, process: subprocess.Popen[str], log_path: Path, timeout: float = 15
) -> None:
    try:
        return_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(f"{worker_id} did not exit after one work item") from error
    if return_code != 0:
        raise RuntimeError(f"{worker_id} exited with {return_code}; inspect {log_path}")


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    required = (
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_ENVIRONMENT_ID",
        "ANTHROPIC_ENVIRONMENT_KEY",
        "SANDBOX_AGENT_ID",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    first_codeword = f"cedar-{uuid.uuid4().hex[:8]}"
    second_codeword = f"maple-{uuid.uuid4().hex[:8]}"
    # The caller supplies an isolated environment with an empty Work queue.
    environment_id = os.environ["ANTHROPIC_ENVIRONMENT_ID"]
    os.environ["ANTHROPIC_ENVIRONMENT_ID"] = environment_id
    workers: dict[str, subprocess.Popen[str]] = {}
    logs: dict[str, Path] = {}
    with _client() as client:
        session = None
        try:
            for name in ("worker-a", "worker-b", "worker-c"):
                workers[name], logs[name] = _start_worker(name)
            _wait_for_workers_ready(workers, logs)

            agent = client.beta.agents.retrieve(os.environ["SANDBOX_AGENT_ID"])
            first_prompt = (
                f"Use the bash tool to run exactly: printf {first_codeword}. "
                "Remember the codeword and include the exact tool output in your reply."
            )
            session = client.beta.sessions.create(
                agent=agent.id,
                environment_id=environment_id,
                title="VeADK three-worker stateless Agent Loop test",
                initial_events=[
                    {
                        "type": "user.message",
                        "content": [{"type": "text", "text": first_prompt}],
                    }
                ],
            )
            first_id = _wait_for_initial_user_message(client, session.id, first_prompt)
            first_events, first_answer = _wait_for_turn(client, session.id, first_id)
            seen_work_ids: set[str] = set()
            first_owner, first_work_id = _wait_for_new_claim(
                logs, session.id, seen_work_ids
            )
            seen_work_ids.add(first_work_id)
            _wait_for_work_stopped(client, environment_id, first_work_id)
            _wait_for_worker_exit(first_owner, workers[first_owner], logs[first_owner])
            if first_codeword not in first_answer:
                raise AssertionError(
                    f"First answer did not contain {first_codeword!r}: {first_answer!r}"
                )

            second_id = _send(
                client,
                session.id,
                f"Without using tools, recall the first codeword and remember a second codeword "
                f"{second_codeword}. Reply with both exact codewords.",
            )
            second_events, second_answer = _wait_for_turn(client, session.id, second_id)
            second_owner, second_work_id = _wait_for_new_claim(
                logs, session.id, seen_work_ids
            )
            seen_work_ids.add(second_work_id)
            _wait_for_work_stopped(client, environment_id, second_work_id)
            _wait_for_worker_exit(
                second_owner, workers[second_owner], logs[second_owner]
            )
            if (
                first_codeword not in second_answer
                or second_codeword not in second_answer
            ):
                raise AssertionError(
                    f"Second-turn canonical ledger recovery failed: {second_answer!r}"
                )

            third_id = _send(
                client,
                session.id,
                "Without using tools, recall both codewords from the previous two turns. "
                "Reply with both exact codewords.",
            )
            third_events, third_answer = _wait_for_turn(client, session.id, third_id)
            third_owner, third_work_id = _wait_for_new_claim(
                logs, session.id, seen_work_ids
            )
            seen_work_ids.add(third_work_id)
            _wait_for_work_stopped(client, environment_id, third_work_id)
            _wait_for_worker_exit(third_owner, workers[third_owner], logs[third_owner])
            if (
                first_codeword not in third_answer
                or second_codeword not in third_answer
            ):
                raise AssertionError(
                    f"Third-turn canonical ledger recovery failed: {third_answer!r}"
                )

            for number, turn in enumerate(
                (first_events, second_events, third_events), start=1
            ):
                types = [event.type for event in turn]
                for required_type in (
                    "user.message",
                    "session.status_running",
                    "span.model_request_start",
                    "span.model_request_end",
                    "session.status_idle",
                ):
                    if types.count(required_type) != 1:
                        raise AssertionError(
                            f"turn {number} expected one {required_type}, got {types}"
                        )
                if types.count("agent.message") < 1:
                    raise AssertionError(
                        f"turn {number} emitted no agent.message: {types}"
                    )
            first_tool_uses = [
                event for event in first_events if event.type == "agent.tool_use"
            ]
            if len(first_tool_uses) != 1 or first_tool_uses[0].name != "bash":
                raise AssertionError(
                    f"Expected one bash tool use in turn 1: {first_tool_uses}"
                )
            matching_results = [
                event
                for event in first_events
                if event.type == "agent.tool_result"
                and event.tool_use_id == first_tool_uses[0].id
            ]
            if len(matching_results) != 1 or first_codeword not in str(
                matching_results[0].content
            ):
                raise AssertionError(
                    f"Missing matching bash result for {first_codeword}: {matching_results}"
                )
            later_tool_events = [
                event
                for turn in (second_events, third_events)
                for event in turn
                if event.type in {"agent.tool_use", "agent.tool_result"}
            ]
            if later_tool_events:
                raise AssertionError(
                    f"Later turns unexpectedly used tools: {later_tool_events}"
                )

            owners = (first_owner, second_owner, third_owner)
            if set(owners) != set(workers):
                raise AssertionError(f"Each worker must win exactly one turn: {owners}")
            claims = {name: _claim_ids(path, session.id) for name, path in logs.items()}
            if any(len(ids) != 1 for ids in claims.values()):
                raise AssertionError(
                    f"Expected exactly one claim per worker for this session: {claims}"
                )
            work_ids = (first_work_id, second_work_id, third_work_id)
            if len(set(work_ids)) != 3:
                raise AssertionError(
                    f"Each turn must have a distinct work item: {work_ids}"
                )

            history = _events(client, session.id)
            successful_spans = [
                event
                for event in history
                if event.type == "span.model_request_end" and not event.is_error
            ]
            response_ids = [
                getattr(event, "metadata", {}).get("ark_response_id")
                for event in successful_spans
            ]
            if len(successful_spans) != 3 or not all(response_ids):
                raise AssertionError("Expected three durable model response references")
            print(f"agent_id={agent.id}")
            print(f"session_id={session.id}")
            print(f"first_worker={first_owner}")
            print(f"second_worker={second_owner}")
            print(f"third_worker={third_owner}")
            print(f"first_work_id={first_work_id}")
            print(f"second_work_id={second_work_id}")
            print(f"third_work_id={third_work_id}")
            print(f"canonical_events={len(history)}")
            print(f"model_response_references={len(response_ids)}")
            print("Distributed stateless VeADK Agent Loop test passed.")
        finally:
            for process in workers.values():
                _stop(process)
            try:
                if session is not None:
                    client.beta.sessions.archive(session.id)
            except Exception as error:  # noqa: BLE001 -- cleanup is best effort
                print(
                    f"cleanup warning: Session archive failed ({type(error).__name__})"
                )


if __name__ == "__main__":
    main()
