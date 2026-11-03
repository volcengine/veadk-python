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

"""Preserve ADK conversation roles across stateless Pi invocations."""

from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict, deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from google.adk.models.llm_request import LlmRequest

from veadk.runtime.piagent.config import PiAgentModelConfig
from veadk.runtime.piagent.translate import _system_instruction_text


def build_pi_messages(
    request: LlmRequest,
    model: PiAgentModelConfig,
    *,
    tool_names: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Keep tool call IDs and results in Pi's native message protocol."""
    messages: list[dict[str, Any]] = []
    tool_names = tool_names or {}
    pending_ids: dict[str, list[str]] = {}
    call_number = 0
    used_ids = {
        part.function_call.id
        for content in request.contents
        for part in content.parts or []
        if part.function_call and part.function_call.id
    }
    for content in request.contents:
        blocks: list[dict[str, Any]] = []

        def flush() -> None:
            if not blocks:
                return
            has_calls = any(block["type"] == "toolCall" for block in blocks)
            message: dict[str, Any] = {
                "role": "user"
                if content.role == "user" and not has_calls
                else "assistant",
                "content": list(blocks),
                "timestamp": 0,
            }
            if message["role"] == "assistant":
                message.update(
                    api=model.api,
                    provider=model.provider_id,
                    model=model.model,
                    stopReason="toolUse" if has_calls else "stop",
                    usage={
                        "input": 0,
                        "output": 0,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "totalTokens": 0,
                        "cost": {
                            "input": 0,
                            "output": 0,
                            "cacheRead": 0,
                            "cacheWrite": 0,
                            "total": 0,
                        },
                    },
                )
            if (
                message["role"] == "assistant"
                and messages
                and messages[-1]["role"] == "assistant"
            ):
                previous = messages[-1]
                previous["content"].extend(message["content"])
                if has_calls:
                    previous["stopReason"] = "toolUse"
            else:
                messages.append(message)
            blocks.clear()

        for part in content.parts or []:
            if part.text and not part.thought:
                blocks.append({"type": "text", "text": part.text})
            elif call := part.function_call:
                while not call.id and f"veadk-call-{call_number}" in used_ids:
                    call_number += 1
                call_id = call.id or f"veadk-call-{call_number}"
                call_number += 1
                used_ids.add(call_id)
                pending_ids.setdefault(call.name or "", []).append(call_id)
                blocks.append(
                    {
                        "type": "toolCall",
                        "id": call_id,
                        "name": tool_names.get(call.name or "", call.name),
                        "arguments": call.model_dump(mode="json").get("args") or {},
                    }
                )
            elif response := part.function_response:
                flush()
                pending = pending_ids.get(response.name or "", [])
                call_id = response.id or (pending[0] if pending else None)
                if call_id in pending:
                    pending.remove(call_id)
                messages.append(
                    {
                        "role": "toolResult",
                        "toolCallId": call_id,
                        "toolName": tool_names.get(response.name or "", response.name),
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    response.model_dump(mode="json")["response"],
                                    ensure_ascii=False,
                                ),
                            }
                        ],
                        "isError": False,
                        "timestamp": 0,
                    }
                )
        flush()
    return _pair_tool_results(messages)


def _pair_tool_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Providers require a call's results before the next user/assistant message.

    ADK may emit each parallel call separately, mix user text with results, or
    deliver a result after intervening user input. Keep user order intact while
    moving each result to its owning call, rather than letting Pi fabricate a
    missing-result placeholder and later repeat the real result.
    """
    results: dict[str, deque[tuple[int, dict[str, Any]]]] = defaultdict(deque)
    next_call: dict[str, int] = {}
    boundaries: dict[tuple[int, str], int] = {}
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message["role"] == "assistant":
            for part in message["content"]:
                if part["type"] == "toolCall":
                    call_id = part["id"]
                    boundaries[index, call_id] = next_call.get(call_id, len(messages))
                    next_call[call_id] = index
    for index, message in enumerate(messages):
        if message["role"] == "toolResult":
            results[message["toolCallId"]].append((index, message))

    consumed: set[int] = set()
    ordered: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if index in consumed:
            continue
        ordered.append(message)
        if message["role"] != "assistant":
            continue
        following = []
        for part in message["content"]:
            if part["type"] != "toolCall":
                continue
            call_id = part["id"]
            candidates = results[call_id]
            while candidates and candidates[0][0] < index:
                candidates.popleft()
            updates = []
            while candidates and candidates[0][0] < boundaries[index, call_id]:
                position, result = candidates.popleft()
                consumed.add(position)
                updates.append((position, result))
            if updates:
                position, result = updates[0]
                # Long-running tools can send progress and a final result for
                # one call ID. Preserve every update within one protocol result.
                following.append(
                    (
                        position,
                        {
                            **result,
                            "content": [
                                block
                                for _, update in updates
                                for block in update["content"]
                            ],
                        },
                    )
                )
        ordered.extend(
            result for _, result in sorted(following, key=lambda item: item[0])
        )
    return ordered


@contextmanager
def pi_context_extension(
    request: LlmRequest,
    model: PiAgentModelConfig,
    *,
    prompt: str,
    tool_names: dict[str, str] | None = None,
) -> Iterator[str]:
    """Replace only the RPC's startup message, preserving later Pi messages."""
    payload = {
        "messages": build_pi_messages(request, model, tool_names=tool_names),
        "prompt": prompt,
        "instruction": _system_instruction_text(request.config.system_instruction),
    }
    # The extension contains conversation and tool-result data, so neither its
    # directory nor its file may be accessible to another local user.
    with tempfile.TemporaryDirectory(prefix="veadk-piagent-context-") as directory:
        path = Path(directory) / "veadk-context.ts"
        source = (
            "const context = JSON.parse("
            + json.dumps(json.dumps(payload, ensure_ascii=True))
            + ");\n"
        )
        source += """
export default function(pi) {
  if (context.instruction) {
    pi.on("before_agent_start", event => ({
      systemPrompt: event.systemPrompt + "\\n\\n" + context.instruction,
    }));
  }
  pi.on("context", event => {
    const index = event.messages.findIndex(message => {
      if (message.role !== "user") return false;
      const text = typeof message.content === "string" ? message.content :
        message.content.filter(part => part.type === "text").map(part => part.text).join("");
      return text === context.prompt;
    });
    if (index < 0) return;
    return {messages: [
      ...event.messages.slice(0, index),
      ...structuredClone(context.messages),
      ...event.messages.slice(index + 1),
    ]};
  });
}
"""
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(source)
        yield str(path)
