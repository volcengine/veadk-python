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

"""Real Codex tool-loop benchmark with a scripted loopback model.

No provider credentials or tokens are used. Run from the checkout with
``uv run --extra dev python scripts/benchmark_codex_tools.py --scenario parallel``.
Compare ``--pool-size 0`` and ``20``. Model latency here is simulated; report
these mechanism measurements separately from any real-model benchmark.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


async def bounded_batch_lookup(
    keys: list[str],
    lookup: Callable[[str], Awaitable[dict]],
    *,
    max_size: int = 8,
    item_timeout: float = 10.0,
) -> dict:
    """Application example: bounded independent reads with explicit item errors.

    The lookup must authorize each key. One batch is one SDK tool invocation;
    the application owns the separate business-read bound. Dependent reads
    and writes must not be automatically combined into this operation.
    """
    if not keys or len(keys) > max_size or max_size < 1 or item_timeout <= 0:
        raise ValueError("the batch must contain between one and max_size keys")

    async def one(key: str) -> dict:
        try:
            result = await asyncio.wait_for(lookup(key), item_timeout)
            return {"key": key, "status": "completed", "result": result}
        except Exception as error:
            return {"key": key, "status": "error", "error_type": type(error).__name__}

    results = await asyncio.gather(*(one(key) for key in keys))
    return {
        "status": "completed"
        if all(r["status"] == "completed" for r in results)
        else "partial_failure",
        "results": results,
    }


class _Model:
    """Script only the tool ordering; Codex executes the real tool protocol."""

    def __init__(self, scenario: str, delay: float):
        self.scenario, self.delay = scenario, delay
        self.turn, self.request = 0, 0
        self.rows: list[dict[str, Any]] = []
        backend = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any):
                pass

            def do_GET(self):
                self._send("application/json", b'{"data":[],"models":[]}')

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("content-length", 0)))
                body = json.loads(raw)
                backend.request += 1
                messages = [
                    i for i in body.get("input", []) if i.get("type") == "message"
                ]
                backend.rows.append(
                    {
                        "request_bytes": len(raw),
                        "developer_messages": sum(
                            i.get("role") == "developer" for i in messages
                        ),
                        "reset_warnings": sum(
                            "your working directory was reset" in p.get("text", "")
                            for i in messages
                            for p in i.get("content", [])
                        ),
                    }
                )
                time.sleep(backend.delay)
                keys: list[str] = []
                name = "batch_lookup" if backend.scenario == "batch" else "mock_lookup"
                if backend.request == 1:
                    keys = (
                        ["alpha", "beta"]
                        if backend.scenario == "parallel"
                        else ["alpha"]
                    )
                elif backend.scenario == "serial" and backend.request == 2:
                    keys = ["beta"]
                items = []
                if keys:
                    namespace = next(
                        t["name"]
                        for t in body.get("tools", [])
                        if t.get("type") == "namespace"
                        and any(x.get("name") == name for x in t.get("tools", []))
                    )
                    for key in keys:
                        call_id = f"call_{backend.turn}_{key}"
                        args = (
                            {"keys": ["alpha", "beta"]}
                            if backend.scenario == "batch"
                            else {"key": key}
                        )
                        items.append(
                            {
                                "type": "function_call",
                                "id": "fc_" + call_id,
                                "call_id": call_id,
                                "namespace": namespace,
                                "name": name,
                                "arguments": json.dumps(args),
                                "status": "completed",
                            }
                        )
                else:
                    current_results = "\n".join(
                        str(i.get("output", ""))
                        for i in body.get("input", [])
                        if i.get("type") == "function_call_output"
                        and str(i.get("call_id", "")).startswith(
                            f"call_{backend.turn}_"
                        )
                    )
                    expected = (
                        ["alpha"] if backend.scenario == "single" else ["alpha", "beta"]
                    )
                    backend.rows[-1]["results_visible"] = all(
                        f"MOCK-{key}" in current_results for key in expected
                    )
                    items.append(
                        {
                            "type": "message",
                            "id": "msg_" + uuid.uuid4().hex,
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": f"ok-{backend.turn}",
                                    "annotations": [],
                                }
                            ],
                        }
                    )
                response_id = "resp_" + uuid.uuid4().hex
                events = [{"type": "response.created", "response": {"id": response_id}}]
                events.extend(
                    {
                        "type": "response.output_item.done",
                        "output_index": i,
                        "item": item,
                    }
                    for i, item in enumerate(items)
                )
                events.append(
                    {
                        "type": "response.completed",
                        "response": {
                            "id": response_id,
                            "usage": {
                                "input_tokens": 1,
                                "output_tokens": 1,
                                "total_tokens": 2,
                                "input_tokens_details": {"cached_tokens": 0},
                                "output_tokens_details": {"reasoning_tokens": 0},
                            },
                        },
                    }
                )
                self._send(
                    "text/event-stream",
                    b"".join(
                        f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode()
                        for e in events
                    ),
                )

            def _send(self, content_type, raw):
                self.send_response(200)
                self.send_header("content-type", content_type)
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)


async def run_case(
    scenario: str, turns: int, pool_size: int, tool_delay: float, model_delay: float
) -> dict:
    """Run isolated synthetic sessions, preserving normal SDK tool behavior."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    from veadk import Agent
    from veadk.runtime.codex import runtime, metrics
    from veadk.runtime.codex.config import CodexRuntimeConfig
    from veadk.runtime.codex.mcp_bridge import get_bridge

    await runtime.shutdown_codex_runtime()
    backend = _Model(scenario, model_delay)
    previous_pool = os.environ.get("VEADK_CODEX_PROCESS_POOL_SIZE")
    os.environ["VEADK_CODEX_PROCESS_POOL_SIZE"] = str(pool_size)
    outcomes = []
    original_resume = metrics.record_resume

    def resume(outcome):
        outcomes.append(outcome)
        original_resume(outcome)

    metrics.record_resume = resume
    reads: list[str] = []
    active, peak = 0, 0

    async def mock_lookup(key: str) -> dict:
        """Look up a synthetic receipt; independent read with no business service."""
        nonlocal active, peak
        if key not in {"alpha", "beta"}:
            raise PermissionError("key is outside this synthetic session")
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(tool_delay)
            reads.append(key)
            return {"receipt": f"MOCK-{key}"}
        finally:
            active -= 1

    async def batch_lookup(keys: list[str]) -> dict:
        """Look up at most eight independent synthetic keys, authorizing each."""
        return await bounded_batch_lookup(keys, mock_lookup)

    rows = []
    bridge = None
    try:
        service = InMemorySessionService()
        sid = "tool-bench-" + uuid.uuid4().hex
        await service.create_session(
            app_name="tool_benchmark", user_id="synthetic", session_id=sid
        )
        agent = Agent(
            name="tool_bench",
            runtime="codex",
            instruction="Synthetic tool workload. Answer briefly.",
            model_name="scripted-tool-model",
            model_api_base=backend.url,
            model_api_key="synthetic-model-key",
            model_api_key_name="",
            tools=[batch_lookup] if scenario == "batch" else [mock_lookup],
            codex_runtime_config=CodexRuntimeConfig(
                model_transport="direct",
                thread_mode="resume",
                reasoning_effort="minimal",
                turn_timeout_seconds=30,
                tool_timeout_seconds=10,
            ),
        )
        runner = Runner(app_name="tool_benchmark", agent=agent, session_service=service)
        for index in range(1, turns + 1):
            backend.turn, backend.request = index, 0
            start_requests, start_reads, start_outcomes = (
                len(backend.rows),
                len(reads),
                len(outcomes),
            )
            calls, text = set(), []
            start = time.perf_counter()

            async def consume():
                stream = runner.run_async(
                    user_id="synthetic",
                    session_id=sid,
                    new_message=types.Content(
                        role="user", parts=[types.Part(text=f"synthetic turn {index}")]
                    ),
                )
                async with contextlib.aclosing(stream):
                    async for event in stream:
                        calls.update(
                            (c.id, c.name) for c in event.get_function_calls() or []
                        )
                        if event.content and not event.partial:
                            text.extend(
                                p.text
                                for p in event.content.parts or []
                                if p.text and not p.thought
                            )

            await asyncio.wait_for(consume(), 35)
            requests = backend.rows[start_requests:]
            expected_reads = ["alpha"] if scenario == "single" else ["alpha", "beta"]
            rows.append(
                {
                    "turn": index,
                    "total_ms": (time.perf_counter() - start) * 1000,
                    "model_requests": len(requests),
                    "tool_calls": len(calls),
                    "reuse_outcome": outcomes[start_outcomes:][-1],
                    "request_bytes": requests[0]["request_bytes"],
                    "developer_messages": requests[0]["developer_messages"],
                    "reset_warnings": requests[0]["reset_warnings"],
                    "correct": sorted(reads[start_reads:]) == expected_reads
                    and text[-1:] == [f"ok-{index}"]
                    and requests[-1].get("results_visible", False),
                }
            )
        bridge = await get_bridge()
    finally:
        await runtime.shutdown_codex_runtime()
        backend.close()
        metrics.record_resume = original_resume
        if previous_pool is None:
            os.environ.pop("VEADK_CODEX_PROCESS_POOL_SIZE", None)
        else:
            os.environ["VEADK_CODEX_PROCESS_POOL_SIZE"] = previous_pool
    return {
        "scenario": scenario,
        "pool_size": pool_size,
        "model": "scripted loopback, no provider tokens",
        "tool_delay_ms": tool_delay * 1000,
        "model_delay_ms": model_delay * 1000,
        "rows": rows,
        "peak_concurrency": peak,
        "cleanup": {
            "pool_idle": len(runtime._PROCESS_POOL._idle),
            "bridge_processes": len(bridge._processes) if bridge else 0,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=["single", "parallel", "serial", "batch"],
        default="single",
    )
    parser.add_argument("--turns", type=int, choices=range(1, 21), default=5)
    parser.add_argument("--pool-size", type=int, choices=[0, 20], default=20)
    parser.add_argument("--tool-delay-ms", type=float, default=50)
    parser.add_argument("--model-delay-ms", type=float, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.tool_delay_ms < 0 or args.model_delay_ms < 0:
        parser.error("delays must be non-negative")
    os.environ["LOGGING_LEVEL"] = "CRITICAL"
    report = asyncio.run(
        run_case(
            args.scenario,
            args.turns,
            args.pool_size,
            args.tool_delay_ms / 1000,
            args.model_delay_ms / 1000,
        )
    )
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered)
    print(rendered)
    if not all(row["correct"] for row in report["rows"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
