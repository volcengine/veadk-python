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

"""Unit tests for veadk.runtime.codex.translate."""

from enum import Enum
from types import SimpleNamespace
from typing import Any

from google.adk.events.event import Event
from google.genai import types

from veadk.runtime.codex import translate
from veadk.runtime.codex.translate import (
    _join,
    _parse_args,
    _scalar,
    _tool_call,
    build_prompt,
    result_to_events,
)


def _part(text: Any = None, thought: bool = False) -> Any:
    return SimpleNamespace(text=text, thought=thought)


def _event(author: str, parts: Any) -> Any:
    return SimpleNamespace(author=author, content=SimpleNamespace(parts=parts))


def _ctx(events: Any) -> Any:
    return SimpleNamespace(session=SimpleNamespace(events=events))


def _content(event: Event) -> Any:
    """Return an Event's content, asserting it is present (it always is here)."""
    assert event.content is not None
    assert event.content.parts is not None
    return event.content


class TestBuildPrompt:
    def test_single_user_turn_returns_bare_message(self):
        ctx = _ctx([_event("user", [_part(text="hello there")])])
        assert build_prompt(ctx) == "hello there"

    def test_multi_turn_renders_prefixed_transcript(self):
        ctx = _ctx(
            [
                _event("user", [_part(text="hi")]),
                _event("agent", [_part(text="hello")]),
                _event("user", [_part(text="bye")]),
            ]
        )
        assert build_prompt(ctx) == "User: hi\nAssistant: hello\nUser: bye"

    def test_thought_parts_are_skipped(self):
        ctx = _ctx(
            [
                _event(
                    "agent",
                    [_part(text="thinking...", thought=True), _part(text="answer")],
                )
            ]
        )
        # The single non-thought line is from a non-user author, so it stays
        # prefixed (the bare-message shortcut only applies to a lone user turn).
        assert build_prompt(ctx) == "Assistant: answer"

    def test_events_without_content_or_parts_skipped(self):
        empty_content = SimpleNamespace(author="user", content=None)
        no_parts = _event("user", [])
        ctx = _ctx([empty_content, no_parts, _event("user", [_part(text="x")])])
        assert build_prompt(ctx) == "x"

    def test_whitespace_only_text_skipped(self):
        ctx = _ctx(
            [
                _event("user", [_part(text="   ")]),
                _event("user", [_part(text="real")]),
            ]
        )
        assert build_prompt(ctx) == "real"

    def test_empty_session_returns_empty_string(self):
        assert build_prompt(_ctx([])) == ""


class TestScalar:
    def test_enum_returns_value(self):
        class Status(Enum):
            DONE = "completed"

        assert _scalar(Status.DONE) == "completed"

    def test_object_with_value_attr(self):
        assert _scalar(SimpleNamespace(value="v")) == "v"

    def test_plain_scalar_passthrough(self):
        assert _scalar("plain") == "plain"
        assert _scalar(7) == 7


class TestJoin:
    def test_list_of_strings(self):
        assert _join(["a", "b"]) == "a\nb"

    def test_list_of_dicts_with_text(self):
        assert _join([{"text": "one"}, {"text": "two"}]) == "one\ntwo"

    def test_strips_and_drops_blanks(self):
        assert _join(["  a  ", "", "   ", "b"]) == "a\nb"

    def test_none_returns_empty(self):
        assert _join(None) == ""


class TestParseArgs:
    def test_dict_passthrough(self):
        assert _parse_args({"k": "v"}) == {"k": "v"}

    def test_valid_json_object(self):
        assert _parse_args('{"a": 1}') == {"a": 1}

    def test_json_non_object_wrapped(self):
        assert _parse_args("[1, 2]") == {"input": [1, 2]}

    def test_invalid_json_wrapped_as_input(self):
        assert _parse_args("not json") == {"input": "not json"}

    def test_empty_and_other_types_return_empty(self):
        assert _parse_args("") == {}
        assert _parse_args("   ") == {}
        assert _parse_args(None) == {}
        assert _parse_args(123) == {}


class TestToolCall:
    def test_command_execution(self):
        result = _tool_call(
            {
                "type": "commandExecution",
                "command": "ls",
                "cwd": "/tmp",
                "aggregated_output": "out",
                "exit_code": 0,
                "status": "completed",
            }
        )
        assert result is not None
        name, args, response = result
        assert name == "exec_command"
        assert args == {"command": "ls", "cwd": "/tmp"}
        assert response == {"output": "out", "exit_code": 0, "status": "completed"}

    def test_mcp_tool_call_joins_server_and_tool(self):
        result = _tool_call(
            {
                "type": "mcpToolCall",
                "server": "fs",
                "tool": "read",
                "arguments": '{"path": "/a"}',
                "result": "data",
                "error": None,
                "status": "completed",
            }
        )
        assert result is not None
        name, args, response = result
        assert name == "fs.read"
        assert args == {"path": "/a"}
        assert response["result"] == "data"

    def test_mcp_tool_call_falls_back_to_default_name(self):
        result = _tool_call({"type": "mcpToolCall"})
        assert result is not None
        assert result[0] == "mcp_tool"

    def test_dynamic_tool_call(self):
        result = _tool_call(
            {
                "type": "dynamicToolCall",
                "namespace": "ns",
                "tool": "do",
                "arguments": {"x": 1},
                "content_items": ["c"],
                "success": True,
                "status": "completed",
            }
        )
        assert result is not None
        name, args, response = result
        assert name == "ns.do"
        assert args == {"x": 1}
        assert response == {"content": ["c"], "success": True, "status": "completed"}

    def test_file_change(self):
        result = _tool_call(
            {"type": "fileChange", "changes": [{"path": "a"}], "status": "completed"}
        )
        assert result is not None
        name, args, response = result
        assert name == "apply_patch"
        assert args == {"changes": [{"path": "a"}]}
        assert response == {"status": "completed"}

    def test_web_search_status_always_completed(self):
        result = _tool_call({"type": "webSearch", "query": "q", "action": "search"})
        assert result is not None
        name, args, response = result
        assert name == "web_search"
        assert args == {"query": "q", "action": "search"}
        assert response == {"status": "completed"}

    def test_non_tool_returns_none(self):
        assert _tool_call({"type": "agentMessage", "text": "hi"}) is None
        assert _tool_call({"type": "reasoning"}) is None


class TestResultToEvents:
    def test_user_message_is_skipped(self):
        result = SimpleNamespace(items=[{"type": "userMessage", "text": "hi"}])
        assert result_to_events(result, "agent", "inv-1") == []

    def test_reasoning_becomes_thought_part(self):
        result = SimpleNamespace(
            items=[{"type": "reasoning", "summary": ["thinking hard"]}]
        )
        events = result_to_events(result, "agent", "inv-1")
        assert len(events) == 1
        part = _content(events[0]).parts[0]
        assert part.thought is True
        assert part.text == "thinking hard"
        assert events[0].author == "agent"
        assert events[0].invocation_id == "inv-1"
        assert _content(events[0]).role == "model"

    def test_reasoning_falls_back_to_content(self):
        result = SimpleNamespace(
            items=[{"type": "reasoning", "summary": [], "content": ["from content"]}]
        )
        events = result_to_events(result, "agent", "inv-1")
        assert _content(events[0]).parts[0].text == "from content"

    def test_empty_reasoning_emits_no_event(self):
        result = SimpleNamespace(items=[{"type": "reasoning", "summary": []}])
        assert result_to_events(result, "agent", "inv-1") == []

    def test_agent_message_becomes_text_part(self):
        result = SimpleNamespace(items=[{"type": "agentMessage", "text": "hello"}])
        events = result_to_events(result, "agent", "inv-1")
        assert len(events) == 1
        assert _content(events[0]).parts[0].text == "hello"
        assert _content(events[0]).parts[0].thought is not True

    def test_tool_call_emits_call_and_response_pair(self):
        result = SimpleNamespace(
            items=[
                {
                    "type": "commandExecution",
                    "id": "c-1",
                    "command": "ls",
                    "cwd": "/tmp",
                    "aggregated_output": "out",
                    "exit_code": 0,
                    "status": "completed",
                }
            ]
        )
        events = result_to_events(result, "agent", "inv-1")
        assert len(events) == 2

        call_part = _content(events[0]).parts[0]
        assert _content(events[0]).role == "model"
        assert isinstance(call_part.function_call, types.FunctionCall)
        assert call_part.function_call.name == "exec_command"
        assert call_part.function_call.id == "c-1"
        assert call_part.function_call.args == {"command": "ls", "cwd": "/tmp"}

        resp_part = _content(events[1]).parts[0]
        assert _content(events[1]).role == "user"
        assert isinstance(resp_part.function_response, types.FunctionResponse)
        assert resp_part.function_response.id == "c-1"
        assert resp_part.function_response.name == "exec_command"
        response = resp_part.function_response.response
        assert response is not None
        assert response["output"] == "out"

    def test_tool_call_synthesizes_id_when_missing(self):
        result = SimpleNamespace(
            items=[{"type": "webSearch", "query": "q", "action": "search"}]
        )
        events = result_to_events(result, "agent", "inv-1")
        # No "id" in the item -> synthesized as call_<len(events)>; at the point
        # of synthesis no events exist yet, so it is call_0.
        assert _content(events[0]).parts[0].function_call.id == "call_0"
        assert _content(events[1]).parts[0].function_response.id == "call_0"

    def test_multi_step_turn_order_preserved(self):
        result = SimpleNamespace(
            items=[
                {"type": "reasoning", "summary": ["let me look"]},
                {
                    "type": "webSearch",
                    "id": "w-1",
                    "query": "q",
                    "action": "search",
                },
                {"type": "agentMessage", "text": "done"},
            ]
        )
        events = result_to_events(result, "agent", "inv-1")
        # reasoning(1) + tool call/response(2) + agentMessage(1) = 4
        assert len(events) == 4
        assert _content(events[0]).parts[0].thought is True
        assert _content(events[1]).parts[0].function_call.name == "web_search"
        assert _content(events[2]).parts[0].function_response is not None
        assert _content(events[3]).parts[0].text == "done"

    def test_fallback_to_final_response_when_no_items_map(self):
        result = SimpleNamespace(items=[], final_response="the answer")
        events = result_to_events(result, "agent", "inv-1")
        assert len(events) == 1
        assert _content(events[0]).parts[0].text == "the answer"
        assert _content(events[0]).role == "model"

    def test_no_items_and_no_final_response_returns_empty(self):
        result = SimpleNamespace(items=[], final_response=None)
        assert result_to_events(result, "agent", "inv-1") == []

    def test_items_attribute_absent(self):
        result = SimpleNamespace(final_response="fallback")
        events = result_to_events(result, "agent", "inv-1")
        assert _content(events[0]).parts[0].text == "fallback"

    def test_pydantic_item_via_model_dump(self):
        class Item:
            def model_dump(self) -> dict[str, Any]:
                return {"type": "agentMessage", "text": "from pydantic"}

        result = SimpleNamespace(items=[Item()])
        events = result_to_events(result, "agent", "inv-1")
        assert _content(events[0]).parts[0].text == "from pydantic"


def test_item_dict_unknown_object_returns_empty():
    # An object without model_dump and not a dict yields {}.
    assert translate._item_dict(object()) == {}
