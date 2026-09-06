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


"""Translate Code Sidecar protocol v1 directly into ADK events."""

from __future__ import annotations

import asyncio
import re
from contextlib import suppress

from google.adk.events import Event
from google.genai import types

from veadk.agents.agentkit_remote_sandbox_agent import SandboxAgentError, binding_key
from veadk.tools.sandbox.codex_worker_client import CodexWorkerClient, CodexWorkerError


def observation(value, secrets=()):
    """Bound display data and redact credential fields and signed URLs."""
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if re.search(r"(?i)authorization|token|api.?key|password|secret", k)
            else observation(v, secrets)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [observation(v, secrets) for v in value[:100]]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"https?://[^\s\"<>]+", "[URL]", value)
        value = re.sub(
            r"(?i)(bearer\s+|(?:api.?key|token|password|secret)\s*[=:]\s*)[^\s,;]+",
            r"\1[REDACTED]",
            value,
        )
        return value[:16000]
    return value


def check_lease(agent, lease):
    if lease:
        remaining = lease.remaining_seconds()
        if (
            remaining is None
            or remaining <= agent.request_timeout + agent.expiry_buffer
        ):
            raise SandboxAgentError(
                "Sandbox session no longer has enough execution lifetime"
            )


def event_for(agent, ctx, parts, *, partial=False, metadata=None):
    return Event(
        author=agent.name,
        invocation_id=ctx.invocation_id,
        branch=ctx.branch,
        partial=partial,
        content=types.Content(role="model", parts=parts),
        custom_metadata=metadata or {},
    )


async def code_events(
    *, agent, ctx, endpoint, headers, binding, turn_key, task, context, lease
):
    sid = tid = None
    completed = False
    tools = {}
    async with CodexWorkerClient(endpoint, headers=headers) as client:
        try:
            async with asyncio.timeout(agent.ready_timeout):
                while True:
                    try:
                        ready = await client.request("GET", "/readyz")
                        break
                    except CodexWorkerError as exc:
                        if exc.status_code == 404:
                            raise SandboxAgentError(
                                "CodeEnv image has no Sidecar; install code-env 1.1.2.3 or newer"
                            ) from None
                        if exc.status_code and exc.status_code < 500:
                            raise SandboxAgentError(str(exc)) from None
                        await asyncio.sleep(1)
                if ready.get("schemaVersion") != 1 or "tool_events" not in ready.get(
                    "capabilities", []
                ):
                    raise SandboxAgentError(
                        "CodeEnv Sidecar protocol is incompatible; version 1 with tool_events is required"
                    )
            check_lease(agent, lease)
            async with asyncio.timeout(agent.request_timeout):
                sid = await client.create_session(binding)
                started = await client.start_turn(sid, task, turn_key)
                tid = started["turnId"]
                async for raw in client.events(sid, tid):
                    kind, payload = raw["type"], raw["payload"]
                    metadata = {
                        "remote_sandbox": {
                            "type": "CodeEnv",
                            "session_id": sid,
                            "turn_id": tid,
                            "event_id": raw["eventId"],
                            "event_type": kind,
                        }
                    }
                    if kind == "message.delta" and payload.get("delta"):
                        yield event_for(
                            agent,
                            ctx,
                            [types.Part(text=payload["delta"])],
                            partial=True,
                            metadata=metadata,
                        )
                    elif kind in {"tool.started", "tool.completed"}:
                        item = payload["item"]
                        item_id = str(item["id"])
                        call_id = "remote_" + binding_key(tid, item_id)[:24]
                        name = re.sub(
                            r"[^a-zA-Z0-9_]", "_", str(item.get("tool") or item["type"])
                        )[:64]
                        safe = observation(item, headers.values())
                        if item_id not in tools:
                            tools[item_id] = name
                            args = {
                                k: v
                                for k, v in safe.items()
                                if k
                                not in {
                                    "id",
                                    "type",
                                    "status",
                                    "aggregatedOutput",
                                    "exitCode",
                                    "durationMs",
                                    "result",
                                    "error",
                                }
                            }
                            yield event_for(
                                agent,
                                ctx,
                                [
                                    types.Part(
                                        function_call=types.FunctionCall(
                                            id=call_id, name=name, args=args
                                        )
                                    )
                                ],
                                metadata=metadata,
                            )
                        if kind == "tool.completed":
                            yield event_for(
                                agent,
                                ctx,
                                [
                                    types.Part(
                                        function_response=types.FunctionResponse(
                                            id=call_id,
                                            name=tools[item_id],
                                            response=safe,
                                        )
                                    )
                                ],
                                metadata=metadata,
                            )
                    elif kind in {"tool.delta", "reasoning.delta"} and payload.get(
                        "delta"
                    ):
                        prefix = "Tool output: " if kind == "tool.delta" else ""
                        metadata["remote_sandbox"]["item_id"] = payload.get("itemId")
                        yield event_for(
                            agent,
                            ctx,
                            [
                                types.Part(
                                    text=prefix
                                    + observation(payload["delta"], headers.values()),
                                    thought=True,
                                )
                            ],
                            partial=True,
                            metadata=metadata,
                        )
                    elif (
                        kind == "message.completed"
                        and payload.get("phase") == "commentary"
                    ):
                        yield event_for(
                            agent,
                            ctx,
                            [types.Part(text=payload.get("text", ""), thought=True)],
                            metadata=metadata,
                        )
                    elif kind == "turn.completed":
                        completed = True
                        if payload["status"] != "completed":
                            error = (
                                payload.get("error", {}).get("message")
                                or payload.get("reason")
                                or payload["status"]
                            )
                            raise SandboxAgentError(
                                f"CodeEnv turn {payload['status']}: {observation(error, headers.values())}"
                            )
                        yield event_for(
                            agent,
                            ctx,
                            [
                                types.Part(
                                    text=payload.get("finalText")
                                    or "Sandbox task completed."
                                )
                            ],
                            metadata=metadata,
                        )
                        return
                raise SandboxAgentError(
                    "CodeEnv stream ended without a terminal event; do not resubmit"
                )
        except CodexWorkerError as exc:
            raise SandboxAgentError(str(exc)) from None
        finally:
            # Covers timeout, task cancellation and async-generator close. A
            # browser subscriber alone must not close the owning Runner task.
            if sid and not completed:

                async def cancel_accepted():
                    turn = tid
                    if turn is None:
                        turn = (
                            await client.request(
                                "GET", client.turn_path(sid) + "/by-key/" + turn_key
                            )
                        )["turnId"]
                    await client.cancel(sid, turn)

                with suppress(Exception):
                    await asyncio.wait_for(cancel_accepted(), timeout=25)
