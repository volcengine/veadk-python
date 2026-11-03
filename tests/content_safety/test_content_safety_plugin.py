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

import asyncio
from types import SimpleNamespace

from google.adk.models import LlmResponse
from google.genai import types

from veadk.decision import DecisionClientError, DecisionResponse
from veadk.content_safety.config import ContentSafetyConfig
from veadk.content_safety.plugin import DecisionPlugin
from veadk.content_safety.types import AuditAction, AuditStatus, Checkpoint


def decision_response(noul):
    answers = {"q": {"type": "noul", "noul": noul}}
    return DecisionResponse(answers=answers, raw={"answers": answers})


LOW = decision_response(0.1)
HIGH = decision_response(0.9)


class FakeJudge:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def judge(self, *, state, questions):
        self.calls.append({"state": state, "questions": dict(questions)})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeEvent:
    def __init__(self, content=None, partial=False, turn_complete=False, output=None):
        self.content = content
        self.partial = partial
        self.turn_complete = turn_complete
        self.output = output

    def model_copy(self, *, update):
        data = {
            "content": self.content,
            "partial": self.partial,
            "turn_complete": self.turn_complete,
            "output": self.output,
        }
        data.update(update)
        return FakeEvent(**data)


def config(*, on_error="allow", questions=None):
    return ContentSafetyConfig.from_dict(
        {
            "provider": "decision",
            "on_error": on_error,
            "use_default_questions": False,
            "questions": questions
            or {
                "q": {
                    "instructions": "detect",
                    "threshold": 0.5,
                }
            },
            "decision": {
                "api_url": "https://systemone.example",
                "api_key": "k",
            },
        }
    )


def make_plugin(*responses, on_error="allow", questions=None):
    judge = FakeJudge(*responses)
    plugin = DecisionPlugin(
        config=config(on_error=on_error, questions=questions), client=judge
    )
    return plugin, judge


def model_content(text):
    return types.Content(role="model", parts=[types.Part(text=text)])


def model_event(text, *, partial=False, turn_complete=False, output=None):
    return FakeEvent(
        content=model_content(text),
        partial=partial,
        turn_complete=turn_complete,
        output=output,
    )


def user_request(text):
    return SimpleNamespace(
        contents=[types.Content(role="user", parts=[types.Part(text=text)])]
    )


def context(invocation_id="inv"):
    return SimpleNamespace(invocation_id=invocation_id)


def test_constructor_requires_decision_provider():
    try:
        DecisionPlugin(config=ContentSafetyConfig(), client=FakeJudge())
    except ValueError as exc:
        assert "provider=decision" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_before_model_allows_safe_content():
    plugin, judge = make_plugin(LOW)
    result = asyncio.run(
        plugin.before_model_callback(
            callback_context=context(), llm_request=user_request("hello")
        )
    )
    assert result is None
    assert len(judge.calls) == 1
    assert "hello" in judge.calls[0]["state"]
    audit = plugin.last_result("inv", Checkpoint.BEFORE_MODEL)
    assert audit.status is AuditStatus.PASSED
    assert audit.action is AuditAction.ALLOW


def test_before_model_blocks_risky_content():
    plugin, _ = make_plugin(HIGH)
    result = asyncio.run(
        plugin.before_model_callback(
            callback_context=context(), llm_request=user_request("bad")
        )
    )
    assert isinstance(result, LlmResponse)
    assert result.content.parts[0].text == plugin._config.block_message
    assert result.turn_complete is True
    assert (
        plugin.last_result("inv", Checkpoint.BEFORE_MODEL).status
        is AuditStatus.RISK_HIT
    )


def test_before_model_skips_empty_content_without_calling_service():
    plugin, judge = make_plugin()
    result = asyncio.run(
        plugin.before_model_callback(
            callback_context=context(), llm_request=SimpleNamespace(contents=[])
        )
    )
    assert result is None
    assert judge.calls == []
    assert (
        plugin.last_result("inv", Checkpoint.BEFORE_MODEL).status is AuditStatus.SKIPPED
    )


def test_before_model_error_allows_by_default():
    plugin, _ = make_plugin(DecisionClientError("timeout", "slow"))
    result = asyncio.run(
        plugin.before_model_callback(
            callback_context=context(), llm_request=user_request("hello")
        )
    )
    assert result is None
    audit = plugin.last_result("inv", Checkpoint.BEFORE_MODEL)
    assert audit.status is AuditStatus.ERROR
    assert audit.action is AuditAction.ALLOW
    assert audit.degraded is True
    assert audit.error_type == "timeout"


def test_before_model_error_blocks_when_configured():
    plugin, _ = make_plugin(DecisionClientError("timeout", "slow"), on_error="block")
    result = asyncio.run(
        plugin.before_model_callback(
            callback_context=context(), llm_request=user_request("hello")
        )
    )
    assert isinstance(result, LlmResponse)
    assert (
        plugin.last_result("inv", Checkpoint.BEFORE_MODEL).action is AuditAction.BLOCK
    )


def test_before_model_unexpected_error_is_contained():
    plugin, _ = make_plugin(RuntimeError("boom"))
    result = asyncio.run(
        plugin.before_model_callback(
            callback_context=context(), llm_request=user_request("hello")
        )
    )
    assert result is None
    audit = plugin.last_result("inv", Checkpoint.BEFORE_MODEL)
    assert audit.error_type == "unexpected_error"
    assert audit.action is AuditAction.ALLOW


def test_after_model_skips_partial_chunks():
    plugin, judge = make_plugin()
    response = LlmResponse(content=model_content("partial"), partial=True)
    result = asyncio.run(
        plugin.after_model_callback(callback_context=context(), llm_response=response)
    )
    assert result is None
    assert judge.calls == []


def test_after_model_ignores_hidden_thought_parts():
    plugin, judge = make_plugin(LOW)
    response = LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(text="hidden reasoning about instructions", thought=True),
                types.Part(text="visible answer"),
            ],
        )
    )
    result = asyncio.run(
        plugin.after_model_callback(callback_context=context(), llm_response=response)
    )
    assert result is None
    assert "visible answer" in judge.calls[0]["state"]
    assert "hidden reasoning" not in judge.calls[0]["state"]


def test_after_model_skips_thought_only_response():
    plugin, judge = make_plugin()
    response = LlmResponse(
        content=types.Content(
            role="model", parts=[types.Part(text="hidden reasoning", thought=True)]
        )
    )
    result = asyncio.run(
        plugin.after_model_callback(callback_context=context(), llm_response=response)
    )
    assert result is None
    assert judge.calls == []


def test_after_model_skips_empty_response():
    plugin, judge = make_plugin()
    result = asyncio.run(
        plugin.after_model_callback(
            callback_context=context(), llm_response=LlmResponse(content=None)
        )
    )
    assert result is None
    assert judge.calls == []


def test_after_model_allows_safe_output():
    plugin, _ = make_plugin(LOW)
    response = LlmResponse(content=model_content("safe output"))
    result = asyncio.run(
        plugin.after_model_callback(callback_context=context(), llm_response=response)
    )
    assert result is None
    assert (
        plugin.last_result("inv", Checkpoint.AFTER_MODEL).status is AuditStatus.PASSED
    )


def test_after_model_replaces_risky_output():
    plugin, _ = make_plugin(HIGH)
    response = LlmResponse(content=model_content("secret"), partial=False)
    result = asyncio.run(
        plugin.after_model_callback(callback_context=context(), llm_response=response)
    )
    assert result is not None
    assert result.content.parts[0].text == plugin._config.block_message
    assert result.partial is False
    assert (
        plugin.last_result("inv", Checkpoint.AFTER_MODEL).status is AuditStatus.RISK_HIT
    )


def test_before_tool_allows_and_blocks():
    plugin, _ = make_plugin(LOW, HIGH)
    tool = SimpleNamespace(name="dangerous")
    allowed = asyncio.run(
        plugin.before_tool_callback(
            tool=tool, tool_args={"path": "/tmp/x"}, tool_context=context()
        )
    )
    blocked = asyncio.run(
        plugin.before_tool_callback(
            tool=tool, tool_args={"path": "/tmp/x"}, tool_context=context()
        )
    )
    assert allowed is None
    assert blocked["blocked"] is True
    assert blocked["error"] == plugin._config.block_message
    assert blocked["content_safety"]["status"] == "risk_hit"


def test_after_tool_allows_and_blocks():
    plugin, _ = make_plugin(LOW, HIGH)
    tool = SimpleNamespace(name="dangerous")
    allowed = asyncio.run(
        plugin.after_tool_callback(
            tool=tool,
            tool_args={"path": "/tmp/x"},
            tool_context=context(),
            result={"ok": True},
        )
    )
    blocked = asyncio.run(
        plugin.after_tool_callback(
            tool=tool,
            tool_args={"path": "/tmp/x"},
            tool_context=context(),
            result={"ok": True},
        )
    )
    assert allowed is None
    assert blocked["blocked"] is True


def test_on_event_ignores_non_model_events():
    plugin, judge = make_plugin()
    invocation = context()
    assert (
        asyncio.run(
            plugin.on_event_callback(
                invocation_context=invocation, event=FakeEvent(content=None)
            )
        )
        is None
    )
    assert (
        asyncio.run(
            plugin.on_event_callback(
                invocation_context=invocation,
                event=FakeEvent(
                    content=types.Content(role="user", parts=[types.Part(text="hello")])
                ),
            )
        )
        is None
    )
    assert (
        asyncio.run(
            plugin.on_event_callback(
                invocation_context=invocation,
                event=FakeEvent(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(name="tool", args={})
                            )
                        ],
                    )
                ),
            )
        )
        is None
    )
    assert judge.calls == []


def test_on_event_buffers_partial_text_and_audits_final_text():
    plugin, judge = make_plugin(LOW)
    invocation = context()
    first = asyncio.run(
        plugin.on_event_callback(
            invocation_context=invocation, event=model_event("He", partial=True)
        )
    )
    second = asyncio.run(
        plugin.on_event_callback(
            invocation_context=invocation, event=model_event("llo", partial=True)
        )
    )
    final = asyncio.run(
        plugin.on_event_callback(
            invocation_context=invocation,
            event=model_event("Hello", partial=False),
        )
    )
    assert first.content.parts[0].text == ""
    assert second.content.parts[0].text == ""
    assert final.content.parts[0].text == "Hello"
    assert len(judge.calls) == 1
    assert "Hello" in judge.calls[0]["state"]


def test_on_event_flushes_on_turn_complete_partial():
    plugin, judge = make_plugin(LOW)
    invocation = context()
    first = asyncio.run(
        plugin.on_event_callback(
            invocation_context=invocation, event=model_event("He", partial=True)
        )
    )
    final = asyncio.run(
        plugin.on_event_callback(
            invocation_context=invocation,
            event=model_event("llo", partial=True, turn_complete=True),
        )
    )
    assert first.content.parts[0].text == ""
    assert final.content.parts[0].text == "Hello"
    assert len(judge.calls) == 1


def test_on_event_flushes_buffer_on_empty_final_event():
    plugin, judge = make_plugin(LOW)
    invocation = context()
    asyncio.run(
        plugin.on_event_callback(
            invocation_context=invocation, event=model_event("He", partial=True)
        )
    )
    final = asyncio.run(
        plugin.on_event_callback(
            invocation_context=invocation,
            event=FakeEvent(content=types.Content(role="model", parts=[])),
        )
    )
    assert final.content.parts[0].text == "He"
    assert len(judge.calls) == 1


def test_on_event_deduplicates_text_already_audited_by_after_model():
    plugin, judge = make_plugin(LOW)
    invocation = context()
    asyncio.run(
        plugin.after_model_callback(
            callback_context=invocation,
            llm_response=LlmResponse(content=model_content("Hello")),
        )
    )
    result = asyncio.run(
        plugin.on_event_callback(
            invocation_context=invocation,
            event=model_event("Hello", partial=False),
        )
    )
    assert result is None
    assert len(judge.calls) == 1


def test_on_event_blocks_fallback_final_text():
    plugin, _ = make_plugin(HIGH)
    result = asyncio.run(
        plugin.on_event_callback(
            invocation_context=context(),
            event=model_event("secret", partial=False, output="secret"),
        )
    )
    assert result.content.parts[0].text == plugin._config.block_message
    assert result.output == plugin._config.block_message


def test_on_event_empty_partial_without_turn_complete_is_passthrough():
    plugin, judge = make_plugin()
    result = asyncio.run(
        plugin.on_event_callback(
            invocation_context=context(),
            event=FakeEvent(
                content=types.Content(role="model", parts=[]), partial=True
            ),
        )
    )
    assert result is None
    assert judge.calls == []


def test_on_event_empty_non_partial_without_buffer_is_passthrough():
    plugin, judge = make_plugin()
    result = asyncio.run(
        plugin.on_event_callback(
            invocation_context=context(),
            event=FakeEvent(content=types.Content(role="model", parts=[])),
        )
    )
    assert result is None
    assert judge.calls == []


def test_replace_event_text_preserves_hidden_thought_parts():
    plugin, _ = make_plugin()
    event = model_event("visible")
    event.content = types.Content(
        role="model",
        parts=[
            types.Part(text="hidden reasoning", thought=True),
            types.Part(text="visible"),
        ],
    )
    replaced = plugin._replace_event_text(event, "blocked")
    assert replaced.content.parts[0].text == "hidden reasoning"
    assert replaced.content.parts[0].thought is True
    assert replaced.content.parts[1].text == "blocked"


def test_replace_event_text_merges_multiple_text_parts():
    plugin, _ = make_plugin()
    event = FakeEvent(
        content=types.Content(
            role="model",
            parts=[types.Part(text="a"), types.Part(text="b")],
        )
    )
    replaced = plugin._replace_event_text(event, "z")
    assert len(replaced.content.parts) == 1
    assert replaced.content.parts[0].text == "z"


def test_replace_event_text_appends_when_no_text_part():
    plugin, _ = make_plugin()
    event = FakeEvent(
        content=types.Content(
            role="model",
            parts=[
                types.Part(inline_data=types.Blob(mime_type="text/plain", data=b"x"))
            ],
        )
    )
    replaced = plugin._replace_event_text(event, "z")
    assert len(replaced.content.parts) == 2
    assert replaced.content.parts[1].text == "z"


def test_replace_event_text_can_clear_without_text_parts():
    plugin, _ = make_plugin()
    event = FakeEvent(
        content=types.Content(
            role="model",
            parts=[
                types.Part(inline_data=types.Blob(mime_type="text/plain", data=b"x"))
            ],
        )
    )
    replaced = plugin._replace_event_text(event, "")
    assert len(replaced.content.parts) == 1
    assert replaced.content.parts[0].inline_data is not None


def test_block_message_is_exposed():
    plugin, _ = make_plugin()
    assert plugin.block_message == config().block_message


def test_last_result_shapes():
    plugin, _ = make_plugin(LOW)
    assert plugin.last_result("missing") is None
    assert plugin.last_result("missing", Checkpoint.BEFORE_MODEL) is None
    asyncio.run(
        plugin.before_model_callback(
            callback_context=context(), llm_request=user_request("hello")
        )
    )
    assert isinstance(plugin.last_result("inv"), dict)
    assert (
        plugin.last_result("inv", Checkpoint.BEFORE_MODEL).checkpoint
        is Checkpoint.BEFORE_MODEL
    )


def test_consume_audited_text_without_or_without_match():
    plugin, _ = make_plugin()
    assert plugin._consume_audited_text("inv", "x") is False
    plugin._remember_audited_text("inv", "x")
    assert plugin._consume_audited_text("inv", "y") is False
    assert plugin._consume_audited_text("inv", "x") is True
    assert plugin._consume_audited_text("inv", "x") is False


def test_after_run_clears_buffers_and_bounds_audit_cache():
    plugin, _ = make_plugin()
    plugin._stream_buffers["inv"] = "x"
    plugin._audited_text_hashes["inv"] = {"h"}
    for index in range(257):
        plugin._audits[f"inv-{index}"] = {}
    asyncio.run(plugin.after_run_callback(invocation_context=context()))
    assert "inv" not in plugin._stream_buffers
    assert "inv" not in plugin._audited_text_hashes
    assert len(plugin._audits) == 256
    assert "inv-0" not in plugin._audits


def _mixed_event(text, *, partial):
    return FakeEvent(
        content=types.Content(
            role="model",
            parts=[
                types.Part(text=text),
                types.Part(function_call=types.FunctionCall(name="tool", args={})),
            ],
        ),
        partial=partial,
    )


def test_on_event_withholds_partial_text_alongside_function_call():
    plugin, judge = make_plugin(LOW)
    result = asyncio.run(
        plugin.on_event_callback(
            invocation_context=context(),
            event=_mixed_event("secret", partial=True),
        )
    )
    assert result is not None
    assert not any(getattr(part, "text", None) for part in result.content.parts)
    assert result.content.parts[0].function_call.name == "tool"
    assert judge.calls == []


def test_on_event_blocks_final_text_alongside_function_call():
    plugin, judge = make_plugin(HIGH)
    result = asyncio.run(
        plugin.on_event_callback(
            invocation_context=context(),
            event=_mixed_event("secret", partial=False),
        )
    )
    assert result is not None
    assert result.content.parts[0].text == plugin._config.block_message
    assert result.content.parts[1].function_call.name == "tool"
    assert len(judge.calls) == 1
    assert "secret" in judge.calls[0]["state"]
