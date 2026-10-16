#!/usr/bin/env python3
# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

"""Verify deployed Managed Session MCP and custom-tool restoration."""

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
MODEL = os.environ["MANAGED_AGENTS_MODEL_CARD_ID"]
ENVIRONMENT_ID = os.environ["MANAGED_AGENTS_ENVIRONMENT_ID"]
MCP_URL = os.environ.get(
    "MANAGED_AGENTS_TEST_MCP_URL", "http://managed-agents-test-mcp:9000/mcp"
)


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


def events(session_id: str) -> list[dict]:
    return request("GET", f"/v1/sessions/{session_id}/events?limit=1000&order=asc").get(
        "data", []
    )


def send_message(session_id: str, text: str) -> None:
    request(
        "POST",
        f"/v1/sessions/{session_id}/events",
        {
            "events": [
                {"type": "user.message", "content": [{"type": "text", "text": text}]}
            ]
        },
    )


def wait(session_id: str, predicate, timeout: float = 180) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for event in events(session_id):
            if predicate(event):
                return event
        time.sleep(0.5)
    raise TimeoutError(f"timed out waiting for Session event in {session_id}")


def create_session(agent: dict, title: str) -> dict:
    return request(
        "POST",
        "/api/sessions",
        {"agent": agent["id"], "environment_id": ENVIRONMENT_ID, "title": title},
    )


def archive_agent(agent: dict | None) -> None:
    if agent is None:
        return
    try:
        request("POST", f"/api/agents/{agent['id']}/archive")
    except Exception as error:  # noqa: BLE001 -- test cleanup only
        print({"cleanup_warning": str(error)})


def test_mcp() -> dict:
    agent = None
    try:
        agent = request(
            "POST",
            "/api/agents",
            {
                "name": f"mcp-e2e-{uuid.uuid4().hex[:8]}",
                "model": {"id": MODEL},
                "system": "Always call the MCP add_numbers tool with a=19 and b=23, then state the result.",
                "mcp_servers": [{"type": "url", "name": "math", "url": MCP_URL}],
                "tools": [
                    {
                        "type": "mcp_toolset",
                        "mcp_server_name": "math",
                        "default_config": {
                            "enabled": True,
                            "permission_policy": {"type": "always_allow"},
                        },
                        "configs": [],
                    }
                ],
            },
        )
        session = create_session(agent, "MCP restore E2E")
        send_message(session["id"], "Use the required MCP tool now.")
        wait(
            session["id"],
            lambda item: item.get("type") == "session.status_idle"
            and (item.get("stop_reason") or {}).get("type") == "end_turn",
        )
        ledger = events(session["id"])
        uses = [item for item in ledger if item.get("type") == "agent.mcp_tool_use"]
        results = [
            item for item in ledger if item.get("type") == "agent.mcp_tool_result"
        ]
        answers = [item for item in ledger if item.get("type") == "agent.message"]
        assert uses and uses[-1]["mcp_server_name"] == "math"
        assert results and "42" in str(results[-1].get("content"))
        assert answers and "42" in str(answers[-1].get("content"))
        return {
            "session_id": session["id"],
            "use": uses[-1]["name"],
            "result": results[-1]["content"],
        }
    finally:
        archive_agent(agent)


def test_custom() -> dict:
    agent = None
    try:
        agent = request(
            "POST",
            "/api/agents",
            {
                "name": f"custom-e2e-{uuid.uuid4().hex[:8]}",
                "model": {"id": MODEL},
                "system": "Always call approve_release with name=demo, then report its returned ticket.",
                "tools": [
                    {
                        "type": "custom",
                        "name": "approve_release",
                        "description": "Request release approval",
                        "input_schema": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"],
                        },
                    }
                ],
            },
        )
        session = create_session(agent, "Custom tool restore E2E")
        send_message(session["id"], "Request the approval now.")
        call = wait(
            session["id"], lambda item: item.get("type") == "agent.custom_tool_use"
        )
        request(
            "POST",
            f"/v1/sessions/{session['id']}/events",
            {
                "events": [
                    {
                        "type": "user.custom_tool_result",
                        "custom_tool_use_id": call["id"],
                        "content": [{"type": "text", "text": "ticket-custom-e2e-42"}],
                    }
                ]
            },
        )
        wait(
            session["id"],
            lambda item: item.get("type") == "session.status_idle"
            and (item.get("stop_reason") or {}).get("type") == "end_turn",
        )
        ledger = events(session["id"])
        answers = [item for item in ledger if item.get("type") == "agent.message"]
        assert answers and "ticket-custom-e2e-42" in str(answers[-1].get("content"))
        return {
            "session_id": session["id"],
            "custom_tool_use_id": call["id"],
            "answer": answers[-1]["content"],
        }
    finally:
        archive_agent(agent)


if __name__ == "__main__":
    print(
        json.dumps(
            {"mcp": test_mcp(), "custom": test_custom()}, ensure_ascii=False, indent=2
        )
    )
