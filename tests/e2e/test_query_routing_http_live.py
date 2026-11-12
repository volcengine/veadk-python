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
"""Live HTTP acceptance: separate ADK server process, real SystemOne and models.

Run with VEADK_QUERY_ROUTING_LIVE=1 and MODEL_AGENT_API_BASE/API_KEY set.
No Runner, ASGI test transport or fabricated provider answers are used by the client.
Default questions, thresholds and the two-second budget are preserved except
in the explicitly named deadline-failure case.
"""

import asyncio
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import uuid
import zlib
from pathlib import Path

import httpx
import pytest
from google.adk.events.event import Event

pytestmark = [
    pytest.mark.query_routing_live,
    pytest.mark.skipif(
        os.getenv("VEADK_QUERY_ROUTING_LIVE") != "1"
        or not os.getenv("MODEL_AGENT_API_KEY")
        or not os.getenv("MODEL_AGENT_API_BASE"),
        reason="requires explicit live enablement and model credentials",
    ),
]

APPS = (
    "responses",
    "chat",
    "mixed",
    "tools",
    "nested",
    "schema",
    "shadow",
    "disabled",
    "default_off",
    "timeout",
    "cancel",
)


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp("query-routing-http")
    agents = root / "agents"
    agents.mkdir()
    for name in APPS:
        package = agents / name
        package.mkdir()
        (package / "__init__.py").write_text("from . import agent\n")
        (package / "agent.py").write_text(
            "from query_routing_http_agent import build_agent\n"
            f"root_agent = build_agent({name!r})\n"
        )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(__file__).parent), str(Path(__file__).resolve().parents[2])]
    )
    env["VEADK_QUERY_ROUTING_AUDIT"] = str(root / "audit.jsonl")
    for key in ("NO_PROXY", "no_proxy"):
        env[key] = env.get(key, "") + ",127.0.0.1,localhost,::1"
    command = [
        str(Path(sys.executable).with_name("adk")),
        "api_server",
        str(agents),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-reload",
        "--session_service_uri",
        "memory://",
        "--artifact_service_uri",
        "memory://",
    ]
    log = (root / "server.log").open("w")
    process = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=log)
    (root / "server-command.json").write_text(
        json.dumps({"command": command, "pid": process.pid})
    )
    url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=url, trust_env=False, timeout=1) as client:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                assert process.poll() is None, (
                    f"server exited; see {root / 'server.log'}"
                )
                try:
                    response = client.get("/list-apps")
                    if response.status_code == 200:
                        assert set(APPS).issubset(response.json())
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("ADK API server did not start within 30 seconds")
        yield {"url": url, "root": root, "command": command}
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()


def decisions(server, app):
    path = server["root"] / "audit.jsonl"
    records = (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )
    return [r for r in records if r["kind"] == "decision_start" and r["app"] == app]


async def session(client, app):
    user = "http_acceptance"
    response = await client.post(f"/apps/{app}/users/{user}/sessions", json={})
    response.raise_for_status()
    return {"appName": app, "userId": user, "sessionId": response.json()["id"]}


async def turn(client, identity, text, *, stream=False, parts=None):
    payload = {
        **identity,
        "newMessage": {"role": "user", "parts": parts or [{"text": text}]},
    }
    if stream:
        events = []
        async with client.stream(
            "POST", "/run_sse", json={**payload, "streaming": True}
        ) as response:
            response.raise_for_status()
            assert response.headers["content-type"].startswith("text/event-stream")
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    event = json.loads(line[6:])
                    events.append(event)
    else:
        response = await client.post("/run", json=payload)
        response.raise_for_status()
        events = response.json()
    assert events, "Agent API returned no events"
    answer = ""
    for value in reversed(events):
        event = Event.model_validate(value)
        if event.is_final_response() and event.content:
            answer = "".join(
                p.text for p in event.content.parts or [] if p.text and not p.thought
            ).strip()
            if answer:
                break
    routes = [e.get("customMetadata", {}).get("veadk_query_routing") for e in events]
    routes = [r for r in routes if r]
    result = {
        "events": events,
        "answer": answer.strip(),
        "routes": routes,
        "errors": [
            {
                "code": e.get("errorCode"),
                "message": e.get("errorMessage") or e.get("error"),
            }
            for e in events
            if e.get("errorCode") or e.get("error")
        ],
    }
    assert not result["errors"], result["errors"]
    return result


def save(server, case, result):
    with (server["root"] / "results.jsonl").open("a") as output:
        output.write(json.dumps({"case": case, **result}, ensure_ascii=False) + "\n")


def fixed_route(result, expected=None):
    assert result["answer"], result
    routes = result["routes"]
    assert routes, result
    assert len({r["model"] for r in routes}) == 1, routes
    assert len({r["root_turn_id"] for r in routes}) == 1, routes
    if expected:
        assert routes[0]["route"] == expected, routes[0]
    return routes[0]


NATURAL_CASES = [
    (
        "extract",
        "从这段文字中提取工单编号，只输出编号：工单编号 TK-482，状态处理中。",
        "simple",
        "TK-482",
    ),
    (
        "medical",
        "我服用华法林后出现黑便和头晕，今晚应该如何调整剂量，是否需要立即就医？",
        "strong",
        None,
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("app", ["responses", "chat"])
@pytest.mark.parametrize(
    "case,prompt,expected,answer", NATURAL_CASES, ids=[c[0] for c in NATURAL_CASES]
)
async def test_http_default_natural_queries(
    server, app, case, prompt, expected, answer
):
    async with httpx.AsyncClient(
        base_url=server["url"], trust_env=False, timeout=60
    ) as client:
        identity = await session(client, app)
        before = len(decisions(server, app))
        result = await turn(client, identity, prompt, stream=app == "responses")
        save(server, f"natural/{app}/{case}", result)
        route = fixed_route(result, expected)
        assert route["reason"] not in ("decision_timeout", "decision_error")
        assert len(decisions(server, app)) == before + 1
        if answer:
            assert result["answer"].rstrip("。.") == answer


@pytest.mark.asyncio
@pytest.mark.parametrize("app", ["responses", "chat", "mixed"])
async def test_http_natural_multiturn_history(server, app):
    async with httpx.AsyncClient(
        base_url=server["url"], trust_env=False, timeout=60
    ) as client:
        identity = await session(client, app)
        before = len(decisions(server, app))
        for index, (prompt, expected, values) in enumerate(
            [
                ("记住项目代号 ORCHID47。只回复该代号。", "simple", ["ORCHID47"]),
                ("项目代号是什么？只回复代号。", "simple", ["ORCHID47"]),
                (
                    "记住里程碑代号 MAPLE83。另外，我服用华法林后出现黑便、头晕，是否应立即就医？",
                    "strong",
                    [],
                ),
                (
                    "现在只提取之前给出的项目代号和里程碑代号，不讨论其他事情。",
                    "simple",
                    ["ORCHID47", "MAPLE83"],
                ),
            ]
        ):
            result = await turn(client, identity, prompt, stream=index % 2 == 1)
            save(server, f"history/{app}/{index}", result)
            fixed_route(result, expected)
            assert all(value in result["answer"] for value in values)
        assert len(decisions(server, app)) == before + 4
        fetched = await client.get(
            f"/apps/{app}/users/{identity['userId']}/sessions/{identity['sessionId']}"
        )
        fetched.raise_for_status()
        assert (
            len(
                {
                    e["invocationId"]
                    for e in fetched.json()["events"]
                    if e.get("customMetadata", {}).get("veadk_query_routing")
                }
            )
            == 4
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("app", ["disabled", "default_off", "shadow", "timeout"])
async def test_http_opt_in_shadow_and_deadline(server, app):
    async with httpx.AsyncClient(
        base_url=server["url"], trust_env=False, timeout=60
    ) as client:
        identity = await session(client, app)
        before = len(decisions(server, app))
        result = await turn(client, identity, "计算 17+25，只输出数字。")
        save(server, f"config/{app}", result)
        assert result["answer"] == "42"
        if app in ("disabled", "default_off"):
            assert not result["routes"]
            assert len(decisions(server, app)) == before
        else:
            route = fixed_route(result, "strong")
            assert route["reason"] == (
                "shadow" if app == "shadow" else "decision_timeout"
            )
            assert len(decisions(server, app)) == before + 1


@pytest.mark.asyncio
async def test_http_tool_error_recovery_keeps_one_decision(server):
    app = "tools"
    async with httpx.AsyncClient(
        base_url=server["url"], trust_env=False, timeout=60
    ) as client:
        identity = await session(client, app)
        before = len(decisions(server, app))
        result = await turn(
            client,
            identity,
            "查询订单 ORD-041 并计算总价。查询暂时失败可以重试一次。",
            stream=True,
        )
        save(server, "tools/retry", result)
        fixed_route(result)
        assert result["answer"].rstrip(".。") == "133"
        calls = [
            p["functionCall"]
            for e in result["events"]
            for p in (e.get("content") or {}).get("parts", [])
            if p.get("functionCall") and not e.get("partial")
        ]
        assert [c["name"] for c in calls] == [
            "lookup_order",
            "lookup_order",
            "calculate_total",
        ]
        # Events preserve provider arguments; validate values at execution,
        # after the schema guard normalizes unambiguous integer strings.
        executed = [
            record
            for line in (server["root"] / "audit.jsonl").read_text().splitlines()
            if (record := json.loads(line))["kind"] == "calculate_total"
        ]
        assert executed == [
            {"kind": "calculate_total", "quantity": 7, "unit_price": 19}
        ]
        assert len(decisions(server, app)) == before + 1


@pytest.mark.asyncio
async def test_http_nested_agents_and_schema(server):
    async with httpx.AsyncClient(
        base_url=server["url"], trust_env=False, timeout=60
    ) as client:
        for app, prompt in [
            ("nested", "请通过 child 获取 leaf 的结果。"),
            ("schema", "项目编号 ORCHID47，数量 7。提取为要求的结构。"),
        ]:
            identity = await session(client, app)
            before = len(decisions(server, app))
            result = await turn(client, identity, prompt)
            save(server, app, result)
            fixed_route(result)
            assert len(decisions(server, app)) == before + 1
            if app == "nested":
                assert "NESTED_HTTP_OK" in result["answer"]
                records = [
                    json.loads(line)
                    for line in (server["root"] / "audit.jsonl")
                    .read_text()
                    .splitlines()
                ]
                models = [
                    r
                    for r in records
                    if r["kind"] == "model"
                    and r["agent"] in ("nested", "child", "leaf")
                ]
                assert {r["agent"] for r in models} == {"nested", "child", "leaf"}
                assert len({r["model"] for r in models}) == 1
            else:
                assert json.loads(result["answer"]) == {
                    "code": "ORCHID47",
                    "quantity": 7,
                }


@pytest.mark.asyncio
async def test_http_concurrent_sessions_do_not_leak(server):
    app = "mixed"
    async with httpx.AsyncClient(
        base_url=server["url"], trust_env=False, timeout=60
    ) as client:
        identities = [await session(client, app) for _ in range(4)]
        codes = ["SESSION_" + uuid.uuid4().hex[:12] for _ in identities]
        before = len(decisions(server, app))

        async def conversation(index):
            own = codes[index]
            prompt = f"记住我的项目代号 {own}。只回复代号。"
            if index % 2:
                prompt += "另外，我服用华法林后出现黑便和头晕，是否应立即就医？"
            first = await turn(client, identities[index], prompt, stream=True)
            save(server, f"concurrent/{index}/first", first)
            fixed_route(first, "strong" if index % 2 else "simple")
            last = await turn(
                client, identities[index], "只回复我之前给出的项目代号。", stream=True
            )
            save(server, f"concurrent/{index}/last", last)
            fixed_route(last, "simple")
            assert own in last["answer"]
            assert all(
                code not in json.dumps(last["events"]) for code in codes if code != own
            )

        await asyncio.gather(*(conversation(i) for i in range(4)))
        assert len(decisions(server, app)) == before + 8


@pytest.mark.asyncio
async def test_http_image_with_default_decision(server):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff\x00\x00" * 64) * 64))
        + chunk(b"IEND", b"")
    )
    async with httpx.AsyncClient(
        base_url=server["url"], trust_env=False, timeout=60
    ) as client:
        identity = await session(client, "responses")
        result = await turn(
            client,
            identity,
            "",
            stream=True,
            parts=[
                {
                    "text": "What is the dominant image color? Reply with one English color word."
                },
                {
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": base64.b64encode(png).decode(),
                    }
                },
            ],
        )
        save(server, "image", result)
        fixed_route(result, "simple")
        assert result["answer"].lower().rstrip(".") == "red"


@pytest.mark.asyncio
async def test_http_sse_disconnect_cancels_tool_and_next_turn_recovers(server):
    app = "cancel"

    def audit_records():
        return [
            json.loads(line)
            for line in (server["root"] / "audit.jsonl").read_text().splitlines()
        ]

    async with httpx.AsyncClient(
        base_url=server["url"], trust_env=False, timeout=60
    ) as client:
        identity = await session(client, app)
        before = len(decisions(server, app))
        payload = {
            **identity,
            "newMessage": {"role": "user", "parts": [{"text": "请调用工具查询库存。"}]},
            "streaming": True,
        }
        async with client.stream("POST", "/run_sse", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    event = json.loads(line[6:])
                    if any(
                        p.get("functionCall", {}).get("name") == "wait_for_inventory"
                        for p in (event.get("content") or {}).get("parts", [])
                    ):
                        break
            deadline = time.monotonic() + 3
            while not any(r["kind"] == "inventory_started" for r in audit_records()):
                assert time.monotonic() < deadline, "tool never started"
                await asyncio.sleep(0.05)
        deadline = time.monotonic() + 5
        while not any(r["kind"] == "inventory_finished" for r in audit_records()):
            assert time.monotonic() < deadline, (
                "client disconnect did not stop the in-flight tool"
            )
            await asyncio.sleep(0.05)
        assert any(
            r["kind"] == "inventory_finished" and r["cancelled"]
            for r in audit_records()
        )
        result = await turn(
            client,
            identity,
            "取消刚才的查询。现在不要调用工具，只计算 17+25，输出数字。",
            stream=True,
        )
        save(server, "disconnect/recovery", result)
        fixed_route(result)
        assert result["answer"] == "42"
        assert len(decisions(server, app)) == before + 2
