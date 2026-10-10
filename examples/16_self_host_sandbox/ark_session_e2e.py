# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

"""Run against the deployed worker; credentials stay inside its environment.

Usage: kubectl exec -i deploy/managed-agents-agent-loop-agentkit -- python - ACTION [SESSION_ID]
with this file on stdin. Actions: probe, start, poll, next, tool, archive.
"""

import asyncio
import json
import os
import sys
import urllib.request


def request(method, path, body=None):
    headers = {
        "x-api-key": os.environ["TASK_SERVER_API_KEY"],
        "x-account-id": os.environ["TASK_SERVER_ACCOUNT_ID"],
        "content-type": "application/json",
    }
    req = urllib.request.Request(
        os.environ["ANTHROPIC_BASE_URL"].rstrip("/") + path,
        method=method,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read()
        return json.loads(data) if data else {}


async def probe():
    from volcenginesdkarkruntime import AsyncArk

    async with AsyncArk(api_key=os.environ["MODEL_AGENT_API_KEY"]) as client:
        first = await client.responses.create(
            model=os.environ["MODEL_AGENT_NAME"],
            input="Remember the number 731946. Reply OK.",
            store=True,
        )
        second = await client.responses.create(
            model=os.environ["MODEL_AGENT_NAME"],
            input="Which number did I ask you to remember?",
            previous_response_id=first.id,
            tools=[
                {
                    "type": "function",
                    "name": "bash",
                    "description": "Execute a bash command",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                }
            ],
            store=True,
        )
        text = "".join(
            part.text
            for output in second.output
            if output.type == "message"
            for part in output.content
            if part.type == "output_text"
        )
        assert "731946" in text, text
        print(
            json.dumps(
                {
                    "responses_api": True,
                    "cloud_context_recall": True,
                    "status": second.status,
                }
            )
        )


required = {"ANTHROPIC_BASE_URL", "TASK_SERVER_API_KEY", "TASK_SERVER_ACCOUNT_ID"}
if len(sys.argv) < 2:
    raise SystemExit("Usage: ark_session_e2e.py ACTION [SESSION_ID]")
action = sys.argv[1]
if action == "start":
    required.update({"SANDBOX_AGENT_ID", "E2E_ENVIRONMENT_ID"})
elif action == "probe":
    required = {"MODEL_AGENT_API_KEY", "MODEL_AGENT_NAME"}
missing = sorted(name for name in required if not os.getenv(name))
if missing:
    raise SystemExit("Missing required configuration: " + ", ".join(missing))
if action == "probe":
    asyncio.run(probe())
elif action == "start":
    agent_id = os.environ["SANDBOX_AGENT_ID"]
    result = request(
        "POST",
        "/v1/sessions",
        {
            "agent": agent_id,
            "environment_id": os.environ["E2E_ENVIRONMENT_ID"],
            "title": "Ark Responses worker restart E2E",
            "initial_events": [
                {
                    "type": "user.message",
                    "content": [
                        {
                            "type": "text",
                            "text": "Remember the secret test number 731946. Reply only OK. Do not run any tools.",
                        }
                    ],
                }
            ],
        },
    )
    print(json.dumps({"session_id": result["id"]}))
else:
    session_id = sys.argv[2]
    if action == "poll":
        session = request("GET", "/v1/sessions/" + session_id)
        events = request(
            "GET", "/v1/sessions/" + session_id + "/events?limit=1000&order=asc"
        )["data"]
        uses = {e["id"] for e in events if e["type"] == "agent.tool_use"}
        results = [e for e in events if e["type"] == "agent.tool_result"]
        print(
            json.dumps(
                {
                    "status": session.get("status"),
                    "tool_uses": len(uses),
                    "matching_tool_results": sum(
                        e.get("tool_use_id") in uses for e in results
                    ),
                    "events": [
                        {
                            "type": e["type"],
                            "content": e.get("content"),
                            "error": e.get("error"),
                            "has_response_id": bool(
                                e.get("metadata", {}).get("ark_response_id")
                            ),
                        }
                        for e in events
                        if e["type"]
                        in {
                            "agent.message",
                            "session.error",
                            "session.status_idle",
                            "agent.tool_use",
                            "agent.tool_result",
                            "span.model_request_end",
                        }
                    ],
                }
            )
        )
    elif action in {"next", "tool"}:
        prompt = "Which secret test number did I ask you to remember? Reply only that number; do not run tools."
        if action == "tool":
            prompt = "Use bash to calculate 123 * 456 with python, then report the result. You must actually call the bash tool."
        request(
            "POST",
            "/v1/sessions/" + session_id + "/events",
            {
                "events": [
                    {
                        "type": "user.message",
                        "content": [{"type": "text", "text": prompt}],
                    }
                ]
            },
        )
        print(json.dumps({"sent": action}))
    elif action == "archive":
        request(
            "POST",
            "/v1/sessions/" + session_id + "/events",
            {
                "events": [{"type": "session.status_terminated"}],
            },
        )
        request("POST", "/v1/sessions/" + session_id + "/archive", {})
        print(json.dumps({"terminated_and_archived": True}))
