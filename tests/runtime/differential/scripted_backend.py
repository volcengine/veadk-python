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

"""A declarative model backend shared by the ADK and Codex differential arms.

The two runtimes consume the model at different protocol levels:

- ``runtime="adk"`` calls ``BaseLlm.generate_content_async(llm_request)`` and
  consumes ``LlmResponse`` objects;
- ``runtime="codex"`` reaches the model through the Responses shim, which calls
  ``litellm.aresponses(**kwargs)`` and consumes a Responses ``dict``.

There is therefore no single object both arms can share. What *is* shareable is
a declarative :class:`Round` plan plus two adapters that replay it, and -- more
importantly -- a normalized record of **what each arm asked the model for**.

That record (:class:`RecordedCall`) is the single decision that makes the
differential suite able to catch silent no-ops. With a scripted model, dropping
``temperature`` (or the tool history, or OpenClaw instruction) does not change
the produced text at all, so a pure output comparison is blind to it. Recording
the inputs makes those rows testable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Iterable

from google.genai import types

_HISTORY_OPEN = "<conversation_history>"
_HISTORY_CLOSE = "</conversation_history>"
_CURRENT_OPEN = "<current_message>"
_CURRENT_CLOSE = "</current_message>"

#: Text the backend replies with once the scripted plan is exhausted. A
#: terminal text round (rather than an error) keeps a runaway agentic loop
#: bounded without masking the assertion that actually failed.
EXHAUSTED_TEXT = "[scripted-backend-exhausted]"


@dataclass(frozen=True)
class Round:
    """One scripted model reply.

    Attributes:
        text: Assistant text for this round, or ``None`` for a tool-only round.
        tool_calls: ``(tool_name, args)`` pairs the model asks for, in order.
        usage: ``(input_tokens, output_tokens)`` reported for this round.
        raises: When set, the backend raises this instead of replying.
    """

    text: str | None = None
    texts: tuple[str, ...] = ()
    tool_calls: tuple[tuple[str, dict[str, Any]], ...] = ()
    usage: tuple[int, int] = (0, 0)
    raises: BaseException | None = None

    @property
    def reply_texts(self) -> tuple[str, ...]:
        """All assistant text chunks this round emits, in order."""
        if self.texts:
            return self.texts
        return () if self.text is None else (self.text,)


@dataclass(frozen=True)
class RecordedCall:
    """Normalized view of one model request, comparable across both arms.

    ``system_instruction`` is deliberately *excluded* from :meth:`comparable`:
    the two runtimes legitimately wrap it in different boilerplate. Rows that
    care about it assert containment of a specific fragment instead.
    """

    arm: str
    tool_names: tuple[str, ...]
    history_texts: tuple[str, ...]
    current_text: str
    tool_records: tuple[tuple[str, str], ...]
    temperature: float | None
    max_output_tokens: int | None
    stop_sequences: tuple[str, ...]
    system_instruction: str

    def comparable(self) -> dict[str, Any]:
        """The subset of fields that must be identical in both arms."""
        return {
            "tool_names": self.tool_names,
            "history_texts": self.history_texts,
            "current_text": self.current_text,
            "tool_records": self.tool_records,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "stop_sequences": self.stop_sequences,
        }


class ScriptedBackend:
    """Replays a :class:`Round` plan into either runtime, recording its inputs.

    Instantiate one per arm (the round cursor and the call log are per-arm),
    from the same shared plan.
    """

    def __init__(self, rounds: Iterable[Round], *, arm: str = "unknown") -> None:
        self.rounds: list[Round] = list(rounds)
        self.arm = arm
        self.calls: list[RecordedCall] = []
        self._cursor = 0

    # ---------------------------------------------------------------- plan

    @property
    def declared_usage_total(self) -> tuple[int, int]:
        """``(prompt_tokens, output_tokens)`` the plan declares in total.

        Only rounds actually consumed count, so a plan whose tail is never
        reached (an early-terminating arm) is not silently credited.
        """
        used = self.rounds[: self._cursor]
        return (sum(r.usage[0] for r in used), sum(r.usage[1] for r in used))

    def _next(self) -> Round:
        if self._cursor >= len(self.rounds):
            self._cursor += 1
            return Round(text=EXHAUSTED_TEXT)
        rnd = self.rounds[self._cursor]
        self._cursor += 1
        return rnd

    # ------------------------------------------------------------- adk arm

    def as_base_llm(self, model: str = "scripted-model") -> Any:
        """A ``BaseLlm`` that replays the plan for ``runtime="adk"``."""
        from google.adk.models.base_llm import BaseLlm
        from google.adk.models.llm_response import LlmResponse

        backend = self

        class _ScriptedLlm(BaseLlm):
            async def generate_content_async(  # type: ignore[override]
                self, llm_request: Any, stream: bool = False
            ) -> AsyncGenerator[Any, None]:
                index = backend._cursor
                backend.calls.append(backend._record_adk(llm_request))
                rnd = backend._next()
                if rnd.raises is not None:
                    raise rnd.raises
                parts: list[types.Part] = []
                for offset, (name, args) in enumerate(rnd.tool_calls):
                    parts.append(
                        types.Part(
                            function_call=types.FunctionCall(
                                id=f"call-{index}-{offset}", name=name, args=dict(args)
                            )
                        )
                    )
                for chunk in rnd.reply_texts:
                    parts.append(types.Part(text=chunk))
                yield LlmResponse(
                    content=types.Content(role="model", parts=parts),
                    usage_metadata=types.GenerateContentResponseUsageMetadata(
                        prompt_token_count=rnd.usage[0],
                        candidates_token_count=rnd.usage[1],
                        total_token_count=rnd.usage[0] + rnd.usage[1],
                    ),
                )

        return _ScriptedLlm(model=model)

    # ----------------------------------------------------------- codex arm

    def as_aresponses(self) -> Callable[..., Any]:
        """A ``litellm.aresponses`` replacement replaying the plan."""

        async def aresponses(**kwargs: Any) -> dict[str, Any]:
            index = self._cursor
            self.calls.append(self._record_codex(kwargs))
            rnd = self._next()
            if rnd.raises is not None:
                raise rnd.raises
            output: list[dict[str, Any]] = []
            for offset, (name, args) in enumerate(rnd.tool_calls):
                output.append(
                    {
                        "id": f"fc-{index}-{offset}",
                        "call_id": f"call-{index}-{offset}",
                        "type": "function_call",
                        "name": name,
                        "arguments": json.dumps(dict(args)),
                        "status": "completed",
                    }
                )
            for chunk_index, chunk in enumerate(rnd.reply_texts):
                output.append(
                    {
                        "id": f"msg-{index}-{chunk_index}",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": chunk,
                                "annotations": [],
                            }
                        ],
                    }
                )
            return {
                "id": f"resp-{index}",
                "object": "response",
                "model": str(kwargs.get("model") or "scripted-model"),
                "status": "completed",
                "output": output,
                "usage": {
                    "input_tokens": rnd.usage[0],
                    "cached_input_tokens": 0,
                    "output_tokens": rnd.usage[1],
                    "reasoning_output_tokens": 0,
                    "total_tokens": rnd.usage[0] + rnd.usage[1],
                },
            }

        return aresponses

    # ------------------------------------------------------- normalization

    def _record_adk(self, llm_request: Any) -> RecordedCall:
        config = getattr(llm_request, "config", None)
        tool_names: list[str] = []
        for tool in getattr(config, "tools", None) or []:
            for declaration in getattr(tool, "function_declarations", None) or []:
                if declaration.name:
                    tool_names.append(str(declaration.name))

        contents = list(getattr(llm_request, "contents", None) or [])
        history, current, tool_records = _split_contents(contents)
        return RecordedCall(
            arm="adk",
            tool_names=tuple(tool_names),
            history_texts=tuple(history),
            current_text=current,
            tool_records=tuple(tool_records),
            temperature=getattr(config, "temperature", None),
            max_output_tokens=getattr(config, "max_output_tokens", None),
            stop_sequences=tuple(getattr(config, "stop_sequences", None) or ()),
            system_instruction=_system_instruction_text(
                getattr(config, "system_instruction", None)
            ),
        )

    def _record_codex(self, kwargs: dict[str, Any]) -> RecordedCall:
        tool_names = tuple(
            str(tool.get("name"))
            for tool in kwargs.get("tools") or []
            if isinstance(tool, dict) and tool.get("type") == "function"
        )

        history: list[str] = []
        current = ""
        tool_records: list[tuple[str, str]] = []
        call_names: dict[str, str] = {}

        for item in kwargs.get("input") or []:
            if isinstance(item, str):
                item_history, item_current, item_tools = _split_prompt(item)
                history.extend(item_history)
                current = item_current or current
                tool_records.extend(item_tools)
                continue
            if not isinstance(item, dict):
                continue
            itype = item.get("type")
            if itype == "function_call":
                name = str(item.get("name") or "")
                call_names[str(item.get("call_id") or item.get("id") or "")] = name
                tool_records.append(("function_call", name))
            elif itype == "function_call_output":
                key = str(item.get("call_id") or item.get("id") or "")
                tool_records.append(("function_response", call_names.get(key, "")))
            elif itype in (None, "message"):
                text = _codex_message_text(item)
                item_history, item_current, item_tools = _split_prompt(text)
                if item.get("role") == "assistant":
                    if text:
                        history.append(text)
                    continue
                history.extend(item_history)
                current = item_current or current
                tool_records.extend(item_tools)

        return RecordedCall(
            arm="codex",
            tool_names=tool_names,
            history_texts=tuple(history),
            current_text=current,
            tool_records=tuple(tool_records),
            temperature=kwargs.get("temperature"),
            max_output_tokens=kwargs.get("max_output_tokens"),
            stop_sequences=tuple(kwargs.get("stop_sequences") or ()),
            system_instruction=str(kwargs.get("instructions") or ""),
        )


# --------------------------------------------------------------- helpers


def _system_instruction_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    parts = getattr(value, "parts", None)
    if parts is not None:
        return "\n".join(p.text for p in parts if getattr(p, "text", None)).strip()
    if isinstance(value, (list, tuple)):
        return "\n".join(_system_instruction_text(v) for v in value).strip()
    return str(value)


def _content_texts(content: Any) -> list[str]:
    texts: list[str] = []
    for part in getattr(content, "parts", None) or []:
        text = getattr(part, "text", None)
        if text and not getattr(part, "thought", False):
            texts.append(str(text))
    return texts


def _split_contents(
    contents: list[Any],
) -> tuple[list[str], str, list[tuple[str, str]]]:
    """Split ADK ``contents`` into (history texts, current text, tool records).

    ``current_text`` is the *last* user text turn -- the message that triggered
    this invocation. Everything else is history. This mirrors how the Codex arm
    serializes the same conversation, so the two are comparable.
    """
    tool_records: list[tuple[str, str]] = []
    text_turns: list[tuple[int, str, str]] = []  # (index, role, text)
    for index, content in enumerate(contents):
        role = str(getattr(content, "role", "") or "")
        for part in getattr(content, "parts", None) or []:
            call = getattr(part, "function_call", None)
            if call is not None and getattr(call, "name", None):
                tool_records.append(("function_call", str(call.name)))
            response = getattr(part, "function_response", None)
            if response is not None and getattr(response, "name", None):
                tool_records.append(("function_response", str(response.name)))
        for text in _content_texts(content):
            text_turns.append((index, role, text))

    current = ""
    current_at = -1
    for position in range(len(text_turns) - 1, -1, -1):
        if text_turns[position][1] == "user":
            current = text_turns[position][2]
            current_at = position
            break
    history = [t for i, (_, _, t) in enumerate(text_turns) if i != current_at]
    return history, current, tool_records


def _codex_message_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    texts: list[str] = []
    for part in content or []:
        if isinstance(part, str):
            texts.append(part)
        elif isinstance(part, dict) and part.get("text"):
            texts.append(str(part["text"]))
    return "\n".join(texts)


def _split_prompt(text: str) -> tuple[list[str], str, list[tuple[str, str]]]:
    """Recover (history texts, current text, tool records) from a Codex prompt.

    ``veadk.runtime.codex.translate.build_prompt_from_llm_request`` serializes
    the whole ADK conversation into one prompt string wrapped in
    ``<conversation_history>`` / ``<current_message>`` JSON blocks. Parsing it
    back is what lets a Codex request be compared with an ADK one.
    """
    if not text:
        return [], "", []
    history_json = _between(text, _HISTORY_OPEN, _HISTORY_CLOSE)
    current_json = _between(text, _CURRENT_OPEN, _CURRENT_CLOSE)
    if history_json is None and current_json is None:
        return [], text.strip(), []

    history: list[str] = []
    tool_records: list[tuple[str, str]] = []
    for record in _loads(history_json) or []:
        texts, records = _parse_prompt_parts(record.get("parts") or [])
        history.extend(texts)
        tool_records.extend(records)
    current_texts, current_records = _parse_prompt_parts(_loads(current_json) or [])
    tool_records.extend(current_records)
    return history, "\n".join(current_texts).strip(), tool_records


def _parse_prompt_parts(
    parts: Any,
) -> tuple[list[str], list[tuple[str, str]]]:
    texts: list[str] = []
    records: list[tuple[str, str]] = []
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text" and part.get("text"):
            texts.append(str(part["text"]))
        elif part.get("type") == "function_call":
            records.append(("function_call", str(part.get("name") or "")))
        elif part.get("type") == "function_response":
            records.append(("function_response", str(part.get("name") or "")))
    return texts, records


def _between(text: str, open_tag: str, close_tag: str) -> str | None:
    start = text.find(open_tag)
    if start < 0:
        return None
    end = text.find(close_tag, start)
    if end < 0:
        return None
    return text[start + len(open_tag) : end]


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
