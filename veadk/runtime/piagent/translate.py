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

"""Translation between ADK session/events and Pi RPC events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from google.adk.events.event import Event
from google.genai import types

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.models.llm_request import LlmRequest

_USER_PREFIX = "User"
_ASSISTANT_PREFIX = "Assistant"
_THINKING_MESSAGE_TYPES = {
    "thinking",
    "thought",
    "reasoning",
    "reasoning_message",
    "assistant_thought",
}


def build_prompt(ctx: "InvocationContext") -> str:
    """Render ADK session history into a text prompt for Pi RPC Phase 1."""

    lines: list[str] = []
    for event in ctx.session.events:
        if event.content is None or not event.content.parts:
            continue
        text = "".join(
            part.text for part in event.content.parts if part.text and not part.thought
        ).strip()
        if not text:
            continue
        prefix = _USER_PREFIX if event.author == "user" else _ASSISTANT_PREFIX
        lines.append(f"{prefix}: {text}")

    user_text = _content_text(getattr(ctx, "user_content", None))
    if user_text and (not lines or lines[-1] != f"{_USER_PREFIX}: {user_text}"):
        lines.append(f"{_USER_PREFIX}: {user_text}")

    if len(lines) == 1 and lines[0].startswith(f"{_USER_PREFIX}: "):
        return lines[0][len(_USER_PREFIX) + 2 :]

    return "\n".join(lines)


def build_prompt_from_llm_request(llm_request: "LlmRequest") -> str:
    """Render callback-mutated LlmRequest contents into a Pi prompt."""

    lines: list[str] = []
    for content in llm_request.contents:
        text = _content_text(content)
        if not text:
            continue
        prefix = (
            _USER_PREFIX
            if getattr(content, "role", None) == "user"
            else _ASSISTANT_PREFIX
        )
        lines.append(f"{prefix}: {text}")

    conversation = ""
    if len(lines) == 1 and lines[0].startswith(f"{_USER_PREFIX}: "):
        conversation = lines[0][len(_USER_PREFIX) + 2 :]
    else:
        conversation = "\n".join(lines)

    system_instruction = _system_instruction_text(
        getattr(llm_request.config, "system_instruction", None)
    )
    if system_instruction:
        if conversation:
            return (
                f"# System instructions\n\n{system_instruction}\n\n"
                f"# Conversation\n\n{conversation}"
            )
        return f"# System instructions\n\n{system_instruction}"
    return conversation


def _content_text(content: Any) -> str:
    if content is None or not getattr(content, "parts", None):
        return ""
    return "".join(
        part.text for part in content.parts if part.text and not part.thought
    ).strip()


def _system_instruction_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    parts = getattr(value, "parts", None)
    if parts is not None:
        return "\n".join(
            part.text for part in parts if getattr(part, "text", None)
        ).strip()
    return str(value).strip()


# Pi's `Usage` counters, as published on assistant messages and tool results.
# `reasoning` is deliberately tracked but never mapped onto genai's
# `thoughts_token_count`: it is a *subset* of `output`, whereas genai treats
# thoughts as disjoint from candidates, so mapping it would double-count.
_USAGE_FIELDS = (
    "input",
    "output",
    "cacheRead",
    "cacheWrite",
    "reasoning",
    "totalTokens",
)


def counts_as_model_call(event: dict[str, Any]) -> bool:
    """Whether a raw Pi RPC event marks one completed backend model call.

    Pi's agent loop performs exactly one backend model call per iteration and
    closes it with exactly one ``message_end`` carrying the assistant message.
    ``message_end`` is also emitted for user and tool-result messages, so the
    role check is what makes this a model-call boundary rather than a message
    boundary.

    Args:
        event (dict[str, Any]): One raw Pi RPC event.

    Returns:
        bool: Whether the event closes one backend model call.
    """
    if event.get("type") != "message_end":
        return False
    message = event.get("message")
    return isinstance(message, dict) and message.get("role") == "assistant"


def make_text_event(
    text: str,
    author: str,
    invocation_id: str,
    *,
    thought: bool = False,
    partial: bool = False,
) -> Event:
    return make_model_event(
        [types.Part(text=text, thought=thought)],
        author=author,
        invocation_id=invocation_id,
        partial=partial,
    )


def make_model_event(
    parts: list[types.Part],
    *,
    author: str,
    invocation_id: str,
    partial: bool = False,
) -> Event:
    return Event(
        invocation_id=invocation_id,
        author=author,
        partial=partial,
        content=types.Content(role="model", parts=parts),
    )


class PiEventTranslator:
    """Stateful converter for one Pi turn."""

    def __init__(self, *, author: str, invocation_id: str):
        self.author = author
        self.invocation_id = invocation_id
        self.emitted_text = False
        self._emitted_texts: list[str] = []
        self._thinking_parts: list[str] = []
        self._text_parts: list[str] = []
        self._usage_totals: dict[str, int] = {}

    def event_to_adk_events(self, event: dict[str, Any]) -> list[Event]:
        self._accumulate_usage(event)
        event_type = event.get("type")
        if event_type == "message_update":
            return self._message_update_to_events(event)
        if event_type == "tool_execution_start":
            return [self._tool_call_event(event)]
        if event_type == "tool_execution_update":
            return self._tool_update_events(event)
        if event_type == "tool_execution_end":
            return [self._tool_response_event(event)]
        if event_type == "message_end":
            message = event.get("message")
            if _message_is_thinking(message):
                return []
            return self._flush_events(preferred_text=_message_text(message))
        if event_type == "turn_end":
            return self._flush_events()
        if event_type == "agent_end":
            return self._flush_events(
                preferred_text=_last_assistant_text(event.get("messages")),
            )
        if event_type == "agent_settled":
            return self._flush_events()
        return []

    def _accumulate_usage(self, event: dict[str, Any]) -> None:
        """Add one raw Pi event's token usage to this turn's running totals.

        Only sources that contribute *new* tokens are summed, mirroring Pi's own
        accounting:

        - ``message_end`` for an assistant message -- one backend model call.
        - ``turn_end.toolResults[]`` -- LLM work performed inside a tool (a
          subagent), which no other event reports.
        - ``compaction_end.result`` -- the call that produced a compaction
          summary, which bypasses the agent loop.

        Deliberately excluded: ``message_update.usage`` is cumulative for the
        in-flight message rather than incremental, ``turn_end.message`` repeats
        the assistant message already counted at its ``message_end``, and
        ``agent_end.messages[]`` replays the whole conversation.

        Args:
            event (dict[str, Any]): One raw Pi RPC event.
        """
        event_type = event.get("type")
        if event_type == "message_end":
            message = event.get("message")
            if isinstance(message, dict) and message.get("role") == "assistant":
                self._add_usage(message.get("usage"))
        elif event_type == "turn_end":
            results = event.get("toolResults")
            if isinstance(results, list):
                for result in results:
                    if isinstance(result, dict):
                        self._add_usage(result.get("usage"))
        elif event_type == "compaction_end":
            result = event.get("result")
            if isinstance(result, dict):
                self._add_usage(result.get("usage"))

    def _add_usage(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        for key in _USAGE_FIELDS:
            value = usage.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            self._usage_totals[key] = self._usage_totals.get(key, 0) + int(value)

    def build_turn_usage_metadata(
        self,
    ) -> types.GenerateContentResponseUsageMetadata | None:
        """Map this turn's accumulated Pi usage onto genai usage metadata.

        Pi normalizes every provider to disjoint prompt-side counters:
        ``input`` excludes cached tokens, which are reported separately as
        ``cacheRead`` (a cache hit) and ``cacheWrite`` (a cache entry being
        created); adapters for providers that fold cache into prompt tokens
        subtract them explicitly. genai's ``prompt_token_count`` is instead the
        whole prompt, with ``cached_content_token_count`` a *subset* of it, so
        the three are summed into the prompt count and the cache-read figure is
        also surfaced on its own. ``cacheWrite`` counts as prompt because those
        tokens are part of the prompt the model processes: Pi's own cost model
        likewise sizes the input side as ``input + cacheRead + cacheWrite``,
        billing the three at different rates rather than treating any of them as
        non-prompt.

        The total is the larger of Pi's reported ``totalTokens`` and the
        component sum, because neither alone is right for every provider. Most
        adapters compute ``totalTokens`` as exactly that sum, but some pass the
        provider's figure through verbatim -- which can legitimately *exceed*
        the sum, since genai's total also covers tool-use prompt tokens that Pi
        never breaks out -- while at least one falls back to ``input + output``
        alone, which against a prompt count that includes cache tokens would
        report a total smaller than its own parts. Taking the maximum keeps
        whichever figure carries more information without ever violating
        ``total >= prompt + candidates``.

        Returns:
            google.genai.types.GenerateContentResponseUsageMetadata | None: The
            turn's usage, or ``None`` when Pi reported no usable counter, so a
            missing or malformed payload degrades to "no accounting" rather than
            to zeroed accounting that would pollute token histograms.
        """
        if not self._usage_totals:
            return None
        totals = self._usage_totals
        prompt = (
            totals.get("input", 0)
            + totals.get("cacheRead", 0)
            + totals.get("cacheWrite", 0)
        )
        candidates = totals.get("output", 0)
        total = max(prompt + candidates, totals.get("totalTokens", 0))
        if not total:
            return None
        return types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt or None,
            candidates_token_count=candidates or None,
            total_token_count=total,
            cached_content_token_count=totals.get("cacheRead") or None,
        )

    def _message_update_to_events(self, event: dict[str, Any]) -> list[Event]:
        update = event.get("assistantMessageEvent")
        if not isinstance(update, dict):
            return []

        update_type = update.get("type")
        if update_type == "text_delta" and update.get("delta"):
            delta = str(update["delta"])
            self._text_parts.append(delta)
            return [
                make_text_event(
                    delta,
                    author=self.author,
                    invocation_id=self.invocation_id,
                    partial=True,
                )
            ]
        if update_type == "thinking_delta" and update.get("delta"):
            delta = str(update["delta"])
            self._thinking_parts.append(delta)
            return [
                make_text_event(
                    delta,
                    author=self.author,
                    invocation_id=self.invocation_id,
                    thought=True,
                    partial=True,
                )
            ]
        if update_type == "error":
            reason = update.get("reason") or "error"
            raise RuntimeError(f"Pi assistant error: {reason}")
        return []

    def _flush_events(self, *, preferred_text: str = "") -> list[Event]:
        """Emit this round's durable assistant text, if it is new.

        Pi closes every round of a turn with its own ``message_end``, and
        ``turn_end`` / ``agent_end`` / ``agent_settled`` then re-announce text
        that has already been emitted. Suppression is therefore keyed on the
        text itself rather than on a "have I emitted anything yet" latch: a
        latch made the *first* round win, so on a turn whose tool call carried a
        text preamble ("let me check the weather...") the preamble became the
        turn's answer and the round that actually answered was dropped.

        Matching on text also covers the preamble a tool-call event has already
        persisted, so it is not repeated as a standalone text event.
        """
        if preferred_text:
            text = preferred_text
            self._text_parts.clear()
        else:
            text = self._drain_text()
        if not text:
            return []
        if text in self._emitted_texts:
            self._thinking_parts.clear()
            self._text_parts.clear()
            return []

        parts = self._drain_pending_parts(include_text=False)
        parts.append(types.Part(text=text, thought=False))
        self._note_emitted(text)
        return [
            make_model_event(
                parts,
                author=self.author,
                invocation_id=self.invocation_id,
            )
        ]

    def _drain_pending_parts(self, *, include_text: bool = True) -> list[types.Part]:
        parts: list[types.Part] = []
        thinking = self._drain_thinking()
        if thinking:
            parts.append(types.Part(text=thinking, thought=True))

        if include_text:
            text = self._drain_text()
            if text:
                parts.append(types.Part(text=text, thought=False))
                # This text is now persisted on the carrying event (a tool
                # call), so a later `message_end` repeating it must not emit it
                # again as a standalone answer.
                self._note_emitted(text)

        return parts

    def _note_emitted(self, text: str) -> None:
        self.emitted_text = True
        if text not in self._emitted_texts:
            self._emitted_texts.append(text)

    def _drain_thinking(self) -> str:
        text = "".join(self._thinking_parts).strip()
        self._thinking_parts.clear()
        return text

    def _drain_text(self) -> str:
        text = "".join(self._text_parts).strip()
        self._text_parts.clear()
        return text

    def _tool_call_event(self, event: dict[str, Any]) -> Event:
        parts = self._drain_pending_parts()
        parts.append(
            types.Part(
                function_call=types.FunctionCall(
                    id=str(event.get("toolCallId") or ""),
                    name=str(event.get("toolName") or "tool"),
                    args=_dict_or_empty(event.get("args")),
                )
            )
        )
        return Event(
            invocation_id=self.invocation_id,
            author=self.author,
            content=types.Content(role="model", parts=parts),
        )

    def _tool_response_event(self, event: dict[str, Any]) -> Event:
        name = str(event.get("toolName") or "tool")
        response = {
            "result": _tool_result_to_response(event.get("result")),
            "is_error": bool(event.get("isError")),
        }
        return Event(
            invocation_id=self.invocation_id,
            author=self.author,
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=str(event.get("toolCallId") or ""),
                            name=name,
                            response=response,
                        )
                    )
                ],
            ),
        )

    def _tool_update_events(self, event: dict[str, Any]) -> list[Event]:
        text = _tool_update_text(event)
        if not text:
            return []
        tool_name = str(event.get("toolName") or "tool")
        return [
            make_text_event(
                f"[{tool_name}] {text}",
                author=self.author,
                invocation_id=self.invocation_id,
                thought=True,
                partial=True,
            )
        ]


def _message_text(message: Any) -> str:
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return ""
    if _message_is_thinking(message):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict) or _content_item_is_thinking(item):
            continue
        if item.get("type") in (None, "text", "output_text") and item.get("text"):
            parts.append(str(item["text"]))
    return "".join(parts).strip()


def _last_assistant_text(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        text = _message_text(message)
        if text:
            return text
    return ""


def _message_is_thinking(message: Any) -> bool:
    if not isinstance(message, dict):
        return False

    if _truthy_flag(
        message,
        "thought",
        "isThought",
        "is_thought",
        "thinking",
        "isThinking",
        "is_thinking",
    ):
        return True

    message_type = _normalized_type(
        message.get("type") or message.get("messageType") or message.get("message_type")
    )
    if _is_thinking_type(message_type):
        return True

    content = message.get("content")
    if not isinstance(content, list):
        return False

    text_items = [
        item for item in content if isinstance(item, dict) and item.get("text")
    ]
    return bool(text_items) and all(
        _content_item_is_thinking(item) for item in text_items
    )


def _content_item_is_thinking(item: dict[str, Any]) -> bool:
    if _truthy_flag(
        item,
        "thought",
        "isThought",
        "is_thought",
        "thinking",
        "isThinking",
        "is_thinking",
    ):
        return True
    item_type = _normalized_type(
        item.get("type") or item.get("contentType") or item.get("content_type")
    )
    return _is_thinking_type(item_type)


def _truthy_flag(data: dict[str, Any], *keys: str) -> bool:
    return any(bool(data.get(key)) for key in keys)


def _normalized_type(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_thinking_type(value: str) -> bool:
    return (
        value in _THINKING_MESSAGE_TYPES or "thinking" in value or "reasoning" in value
    )


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tool_result_to_response(result: Any) -> Any:
    if isinstance(result, str):
        return {"content": result}
    if not isinstance(result, dict):
        return result
    content = result.get("content")
    response: dict[str, Any] = {}
    details: dict[str, Any] = {}
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(str(item.get("text") or ""))
        if texts:
            response["content"] = "".join(texts)
    elif isinstance(content, str):
        response["content"] = content
    for key in ("text", "output", "message"):
        if not response.get("content") and result.get(key) is not None:
            response["content"] = str(result[key])
    if not response.get("content"):
        shell_parts: list[str] = []
        if result.get("stdout"):
            shell_parts.append(str(result["stdout"]))
        if result.get("stderr"):
            shell_parts.append(str(result["stderr"]))
        if shell_parts:
            response["content"] = "\n".join(shell_parts)
    if "structuredContent" in result:
        response["structured_content"] = result["structuredContent"]
    if isinstance(result.get("details"), dict):
        details.update(result["details"])
    for key in (
        "stdout",
        "stderr",
        "exitCode",
        "exit_code",
        "code",
        "path",
        "diff",
        "oldText",
        "newText",
        "bytes",
    ):
        if key in result:
            details[key] = result[key]
    if details:
        response["details"] = details
    if "isError" in result:
        response["is_error"] = bool(result.get("isError"))
    return response or result


def _tool_update_text(event: dict[str, Any]) -> str:
    for key in ("delta", "message", "stdout", "stderr", "text", "output"):
        value = event.get(key)
        if value:
            return str(value).strip()

    for key in ("partialResult", "result", "update"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            text = _tool_update_text(value)
            if text:
                return text
    return ""
