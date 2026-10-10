#!/usr/bin/env python3
# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

"""Drive three sequential turns through the deployed Managed Agents gateway."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid

BASE_URL = os.environ.get(
    "MANAGED_AGENTS_GATEWAY_URL", "http://127.0.0.1:18080"
).rstrip("/")
CONTROL_URL = os.environ.get(
    "MANAGED_AGENTS_CONTROL_URL", "http://127.0.0.1:8000"
).rstrip("/")
CONTROL_TOKEN = os.environ.get("ANTHROPIC_ENVIRONMENT_KEY", "")
MODEL = os.environ["MANAGED_AGENTS_MODEL_CARD_ID"]
ENVIRONMENT_ID = os.environ["MANAGED_AGENTS_ENVIRONMENT_ID"]


def request(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        BASE_URL + path, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"{method} {path}: HTTP {error.code}: {error.read()[:500]!r}"
        ) from error
    return json.loads(raw) if raw else {}


def control_request(path: str) -> dict:
    headers = {"Accept": "application/json"}
    if CONTROL_TOKEN:
        headers["Authorization"] = f"Bearer {CONTROL_TOKEN}"
    req = urllib.request.Request(CONTROL_URL + path, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read())


def upload_skill_files(api_path: str, name: str, files: dict[str, bytes]) -> dict:
    boundary = f"----managed-agents-{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="display_name"\r\n\r\n{name}\r\n'
    ).encode()
    for path, content in files.items():
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files[]"; filename="{name}/{path}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        BASE_URL + api_path,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as response:
        return json.loads(response.read())


def upload_skill(name: str, files: dict[str, bytes]) -> dict:
    return upload_skill_files("/v1/skills", name, files)


def upload_skill_version(skill_id: str, name: str, files: dict[str, bytes]) -> dict:
    return upload_skill_files(f"/v1/skills/{skill_id}/versions", name, files)


def wait_turn(
    session_id: str, event_id: str, timeout: float = 240
) -> tuple[list[dict], str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = request(
            "GET", f"/v1/sessions/{session_id}/events?limit=1000&order=asc"
        ).get("data", [])
        start = next(
            (
                index
                for index, event in enumerate(events)
                if event.get("id") == event_id
            ),
            None,
        )
        if start is not None:
            turn = events[start:]
            errors = [
                event.get("error")
                for event in turn
                if event.get("type") == "session.error"
            ]
            if errors:
                raise RuntimeError(f"Agent Loop failed: {errors}")
            if any(event.get("type") == "session.status_idle" for event in turn):
                text = "\n".join(
                    str(block.get("text", ""))
                    for event in turn
                    if event.get("type") == "agent.message"
                    for block in (event.get("content") or [])
                    if block.get("type") == "text"
                )
                return turn, text
        time.sleep(1)
    raise TimeoutError(f"timed out waiting for {event_id}")


def send(session_id: str, text: str) -> str:
    response = request(
        "POST",
        f"/v1/sessions/{session_id}/events",
        {
            "events": [
                {"type": "user.message", "content": [{"type": "text", "text": text}]}
            ]
        },
    )
    data = response.get("data") or []
    if data and data[0].get("id"):
        return str(data[0]["id"])
    # Some Task Server versions return the accepted input shape without the
    # generated event ID. Resolve the ID from the durable event ledger instead
    # of retrying a write whose outcome is already known.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        events = request(
            "GET", f"/v1/sessions/{session_id}/events?limit=1000&order=asc"
        ).get("data", [])
        matches = [
            event
            for event in events
            if event.get("type") == "user.message"
            and any(
                block.get("type") == "text" and block.get("text") == text
                for block in (event.get("content") or [])
            )
        ]
        if matches and matches[-1].get("id"):
            return str(matches[-1]["id"])
        time.sleep(0.5)
    raise TimeoutError("accepted user.message was not found in the event ledger")


def main() -> None:
    first = f"cedar-{uuid.uuid4().hex[:8]}"
    second = f"maple-{uuid.uuid4().hex[:8]}"
    skill_name = f"managed-recovery-{uuid.uuid4().hex[:8]}"
    marker = f"skill-{uuid.uuid4().hex[:8]}"
    newer_marker = f"newer-skill-{uuid.uuid4().hex[:8]}"
    skill = upload_skill(
        skill_name,
        {
            "SKILL.md": (
                f"---\nname: {skill_name}\ndescription: Verify Session Skill recovery\n---\n"
                f"When asked for the skill marker, use bash to run: "
                f"cat skills/{skill_name}/references/marker.txt\n"
            ).encode(),
            "references/marker.txt": (marker + "\n").encode(),
        },
    )
    agent = None
    session = None
    try:
        agent = request(
            "POST",
            "/api/agents",
            {
                "name": f"k8s-e2e-{uuid.uuid4().hex[:8]}",
                "model": {"id": MODEL},
                "system": "Remember codewords across turns and follow attached Skills.",
                "skills": [
                    {"type": "custom", "skill_id": skill["id"], "version": "latest"}
                ],
                "tools": [
                    {
                        "type": "agent_toolset_20260401",
                        "default_config": {
                            "enabled": False,
                            "permission_policy": {"type": "always_allow"},
                        },
                        "configs": [
                            {
                                "type": "bash",
                                "name": "bash",
                                "enabled": True,
                                "permission_policy": {"type": "always_allow"},
                            }
                        ],
                    }
                ],
            },
        )
        session = request(
            "POST",
            "/api/sessions",
            {
                "agent": agent["id"],
                "environment_id": ENVIRONMENT_ID,
                "title": "K8s three-worker Skills recovery E2E",
            },
        )
        pinned = session["agent"]["skills"][0]["version"]
        if pinned in {"", "latest", None}:
            raise AssertionError(f"Session Skill version was not pinned: {pinned!r}")
        newer = upload_skill_version(
            skill["id"],
            skill_name,
            {
                "SKILL.md": (
                    f"---\nname: {skill_name}\ndescription: Newer version sentinel\n---\n"
                    f"When asked for the skill marker, use bash to run: "
                    f"cat skills/{skill_name}/references/marker.txt\n"
                ).encode(),
                "references/marker.txt": (newer_marker + "\n").encode(),
            },
        )
        if newer["id"] == pinned:
            raise AssertionError(
                "creating a Skill version did not advance its version ID"
            )
        prompts = [
            f"Use the attached skill to read its marker. Also remember {first}. Reply with both exact values.",
            f"Use the attached skill again. Recall {first}, remember {second}, and reply with all three values.",
            "Use the attached skill once more, then reply with its marker and both prior codewords.",
        ]
        answers = []
        event_counts = []
        for prompt in prompts:
            event_id = send(session["id"], prompt)
            events, answer = wait_turn(session["id"], event_id)
            answers.append(answer)
            event_counts.append(len(events))
        if first not in answers[0] or marker not in answers[0]:
            raise AssertionError(f"first Worker did not load the Skill: {answers[0]!r}")
        if (
            first not in answers[1]
            or second not in answers[1]
            or marker not in answers[1]
        ):
            raise AssertionError(f"conversation/Skill recovery failed: {answers[1]!r}")
        if any(value not in answers[2] for value in (first, second, marker)):
            raise AssertionError(
                f"third Worker did not restore all state: {answers[2]!r}"
            )
        if any(newer_marker in answer for answer in answers):
            raise AssertionError(
                "Worker loaded a newer Skill instead of the Session-pinned version"
            )
        all_events = request(
            "GET", f"/v1/sessions/{session['id']}/events?limit=1000&order=asc"
        )["data"]
        work = [
            item
            for item in control_request(
                f"/v1/environments/{ENVIRONMENT_ID}/work?limit=1000"
            )["data"]
            if item["data"] == {"type": "session", "id": session["id"]}
        ]
        worker_ids = {
            item.get("metadata", {}).get("managed_agent_worker_id")
            for item in work
            if item.get("metadata", {}).get("managed_agent_worker_id")
        }
        if len(work) != 3 or len(worker_ids) != 3:
            raise AssertionError(
                f"expected three one-work Worker processes, got "
                f"work={len(work)} workers={worker_ids}"
            )
        if any(item.get("state") != "stopped" for item in work):
            raise AssertionError(f"one or more Worker runs failed: {work}")
        print(
            json.dumps(
                {
                    "agent_id": agent["id"],
                    "session_id": session["id"],
                    "skill_id": skill["id"],
                    "pinned_skill_version": pinned,
                    "newer_skill_version": newer["id"],
                    "codewords": [first, second],
                    "skill_marker": marker,
                    "turn_event_counts": event_counts,
                    "event_count": len(all_events),
                    "tool_uses": sum(
                        event.get("type") == "agent.tool_use" for event in all_events
                    ),
                    "tool_results": sum(
                        event.get("type") == "agent.tool_result" for event in all_events
                    ),
                    "worker_ids": sorted(worker_ids),
                },
                indent=2,
            )
        )
    finally:
        cleanup_errors = []
        if session is not None:
            try:
                request("POST", f"/api/sessions/{session['id']}/archive")
            except Exception as error:  # noqa: BLE001 -- cleanup is best effort
                cleanup_errors.append(f"session: {error}")
        if agent is not None:
            try:
                request("POST", f"/api/agents/{agent['id']}/archive")
            except Exception as error:  # noqa: BLE001 -- continue deleting Skill
                cleanup_errors.append(f"agent: {error}")
        try:
            request("DELETE", f"/v1/skills/{skill['id']}")
        except Exception as error:  # noqa: BLE001 -- report after all cleanup attempts
            cleanup_errors.append(f"skill: {error}")
        if cleanup_errors:
            print(json.dumps({"cleanup_warnings": cleanup_errors}, indent=2))


if __name__ == "__main__":
    main()
