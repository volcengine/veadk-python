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


"""Skill A2A transport using public client APIs and structured ADK parts."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.client.errors import A2AClientHTTPError, A2AClientTimeoutError
from a2a.types import (
    AgentCard,
    Message,
    Part,
    TaskArtifactUpdateEvent,
    TaskIdParams,
    TaskQueryParams,
    TaskState,
    TextPart,
)
from google.adk.a2a.converters.part_converter import convert_a2a_part_to_genai_part
from google.genai import types

from veadk.agents._remote_sandbox.timeout import timeout
from veadk.agents._remote_sandbox.code import check_lease, event_for, observation
from veadk.agents.agentkit_remote_sandbox_agent import SandboxAgentError

_ACTIVE = {TaskState.submitted, TaskState.working}


def endpoint_path(endpoint, path):
    url = httpx.URL(endpoint)
    if url.scheme not in {"http", "https"} or url.userinfo or url.fragment:
        raise SandboxAgentError("Invalid Skill endpoint")
    return url.copy_with(path=url.path.rstrip("/") + "/" + path.lstrip("/"))


async def skill_events(
    *, agent, ctx, endpoint, headers, binding, turn_key, task, context, lease
):
    async with httpx.AsyncClient(
        headers=headers, timeout=httpx.Timeout(30, connect=10), trust_env=False
    ) as http:
        async with timeout(agent.ready_timeout):
            while True:
                try:
                    response = await http.get(
                        endpoint_path(endpoint, "/.well-known/agent-card.json")
                    )
                    if response.status_code == 200:
                        card = AgentCard.model_validate(response.json())
                        break
                    if response.status_code not in {502, 503, 504}:
                        raise SandboxAgentError(
                            f"Skill Agent Card returned HTTP {response.status_code}"
                        )
                except (httpx.TransportError, ValueError):
                    pass
                await asyncio.sleep(1)
        check_lease(agent, lease)
        # Keep the platform authority/query, using only the Card's RPC path.
        card = card.model_copy(deep=True)
        card.url = str(endpoint_path(endpoint, httpx.URL(card.url).path))
        card.additional_interfaces = None
        client = ClientFactory(
            ClientConfig(
                httpx_client=http,
                streaming=bool(card.capabilities.streaming),
                polling=True,
                supported_transports=["JSONRPC"],
                use_client_preference=True,
            )
        ).create(card)
        invocations = context.setdefault("invocations", {})
        if turn_key in invocations:
            raise SandboxAgentError(
                "This A2A invocation was already submitted; do not execute it again"
            )
        if len(invocations) >= 64:
            raise SandboxAgentError(
                "Skill invocation capacity reached for this physical session"
            )
        invocations[turn_key] = {"status": "submitting"}
        message = Message(
            message_id=turn_key,
            role="user",
            parts=[Part(root=TextPart(text=task))],
            context_id=context.get("context_id"),
        )
        remote_task = None
        completed = False
        emitted = set()
        final_text = ""
        snapshots = {}

        def convert(parts, *, source):
            nonlocal final_text
            result = []
            for wire in parts or []:
                part = convert_a2a_part_to_genai_part(wire)
                for part in part if isinstance(part, list) else [part]:
                    if part is None:
                        continue
                    if part.function_call or part.function_response:
                        safe = observation(
                            part.model_dump(exclude_none=True), headers.values()
                        )
                        part = types.Part.model_validate(safe)
                        # Replayed Task snapshots repeat call/result parts.
                        identity = json.dumps(safe, sort_keys=True)
                        if identity in emitted:
                            continue
                        emitted.add(identity)
                        result.append(
                            event_for(
                                agent,
                                ctx,
                                [part],
                                metadata={
                                    "remote_sandbox": {
                                        "type": "Skill",
                                        "source": source,
                                    }
                                },
                            )
                        )
                    elif part.text:
                        result.append(
                            event_for(
                                agent,
                                ctx,
                                [part],
                                partial=True,
                                metadata={
                                    "remote_sandbox": {
                                        "type": "Skill",
                                        "source": source,
                                    }
                                },
                            )
                        )
            return result

        def consume(response):
            nonlocal remote_task, final_text, completed
            if isinstance(response, Message):
                completed = True
                if response.context_id:
                    context["context_id"] = response.context_id
                final_text = "\n".join(
                    p.root.text for p in response.parts if isinstance(p.root, TextPart)
                )
                return convert(response.parts, source=response.message_id)
            remote_task, update = response
            invocations[turn_key] = {
                "status": remote_task.status.state.value,
                "task_id": remote_task.id,
            }
            if remote_task.context_id:
                context["context_id"] = remote_task.context_id
            if isinstance(update, TaskArtifactUpdateEvent):
                artifact = update.artifact
                text = "".join(
                    p.root.text for p in artifact.parts if isinstance(p.root, TextPart)
                )
                snapshots[artifact.artifact_id] = (
                    (snapshots.get(artifact.artifact_id, "") + text)
                    if update.append
                    else text
                )
                return convert(artifact.parts, source=artifact.artifact_id)
            events = []
            messages = list(remote_task.history or []) if update is None else []
            if remote_task.status.message:
                messages.append(remote_task.status.message)
            for msg in messages:
                if msg.role == "user" or msg.message_id in emitted:
                    continue
                emitted.add(msg.message_id)
                events.extend(convert(msg.parts, source=msg.message_id))
                if remote_task.status.state not in _ACTIVE:
                    text = "\n".join(
                        p.root.text for p in msg.parts if isinstance(p.root, TextPart)
                    )
                    if text:
                        final_text = text
            # Final/polled snapshots provide authoritative artifacts. Streaming
            # artifact deltas were already shown; only extract tools on final.
            if update is None or remote_task.status.state not in _ACTIVE:
                for artifact in remote_task.artifacts or []:
                    snapshots[artifact.artifact_id] = "".join(
                        p.root.text
                        for p in artifact.parts
                        if isinstance(p.root, TextPart)
                    )
                    tool_parts = [
                        p for p in artifact.parts if not isinstance(p.root, TextPart)
                    ]
                    events.extend(convert(tool_parts, source=artifact.artifact_id))
            return events

        try:
            async with timeout(agent.request_timeout):
                try:
                    async for response in client.send_message(
                        message,
                        request_metadata={
                            "user_id": ctx.user_id,
                            "session_id": ctx.session.id,
                        },
                    ):
                        for event in consume(response):
                            yield event
                except (
                    httpx.TransportError,
                    A2AClientHTTPError,
                    A2AClientTimeoutError,
                ):
                    # An accepted Task can be queried; never send the message twice.
                    if remote_task is None:
                        raise SandboxAgentError(
                            "A2A submission result is unconfirmed; do not resubmit"
                        ) from None
                while remote_task and remote_task.status.state in _ACTIVE:
                    await asyncio.sleep(1)
                    queried = await client.get_task(
                        TaskQueryParams(id=remote_task.id, history_length=20)
                    )
                    for event in consume((queried, None)):
                        yield event
                if remote_task:
                    completed = remote_task.status.state not in _ACTIVE
                    if remote_task.status.state != TaskState.completed:
                        raise SandboxAgentError(
                            f"Skill task ended with state {remote_task.status.state.value}"
                        )
                if not completed:
                    raise SandboxAgentError(
                        "Skill stream ended without a terminal task"
                    )
                text = (
                    "\n".join(text for text in snapshots.values() if text)
                    or final_text
                    or "Sandbox task completed."
                )
                yield event_for(
                    agent,
                    ctx,
                    [types.Part(text=text)],
                    metadata={
                        "remote_sandbox": {
                            "type": "Skill",
                            "task_id": remote_task.id if remote_task else None,
                        }
                    },
                )
        finally:
            if remote_task and not completed:
                with suppress(Exception):
                    await asyncio.wait_for(
                        client.cancel_task(TaskIdParams(id=remote_task.id)), timeout=10
                    )
            await client.close()
