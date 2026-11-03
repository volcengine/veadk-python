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

"""Pending tool barriers belong to one agent in one resumable invocation."""

import pytest
from google.adk.agents.invocation_context import InvocationContext
from google.adk.apps.app import ResumabilityConfig
from google.adk.events.event import Event
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions.session import Session
from google.genai import types

from veadk import Agent
from veadk.runtime.pending_tools import has_pending_tool_calls


def _call(call_id="call", **kwargs):
    return Event(
        author=kwargs.pop("author", "assistant"),
        invocation_id=kwargs.pop("invocation_id", "inv"),
        long_running_tool_ids={call_id},
        content=types.Content(
            role="model",
            parts=[
                types.Part(function_call=types.FunctionCall(id=call_id, name="job"))
            ],
        ),
        **kwargs,
    )


def _response(call_id="call", *, will_continue=None, **kwargs):
    return Event(
        author=kwargs.pop("author", "user"),
        invocation_id=kwargs.pop("invocation_id", "inv"),
        content=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=call_id,
                        name="job",
                        response={"value": "result", "isFinal": True},
                        will_continue=will_continue,
                    )
                )
            ],
        ),
        **kwargs,
    )


@pytest.fixture
def context():
    agent = Agent(name="assistant", model_api_key="unit-test-key")

    def build(*events, branch=None, resumable=True):
        return InvocationContext(
            session_service=InMemorySessionService(),
            invocation_id="inv",
            agent=agent,
            branch=branch,
            resumability_config=ResumabilityConfig(is_resumable=resumable),
            session=Session(
                id="session",
                app_name="test",
                user_id="test",
                state={},
                events=list(events),
            ),
        )

    return build


@pytest.mark.parametrize("first_result", ["first", "second"])
def test_partial_batch_stays_pending_in_either_response_order(context, first_result):
    assert has_pending_tool_calls(
        context(_call("first"), _call("second"), _response(first_result))
    )


@pytest.mark.parametrize("will_continue", [None, False])
def test_only_final_result_resolves_its_call(context, will_continue):
    assert not has_pending_tool_calls(
        context(_call(), _response(will_continue=will_continue))
    )
    assert has_pending_tool_calls(context(_call(), _response(will_continue=True)))


def test_progress_after_final_does_not_reopen_completed_call(context):
    assert not has_pending_tool_calls(
        context(_call(), _response(), _response(will_continue=True))
    )


def test_multiple_questions_wait_until_every_answer_is_final(context):
    events = [_call("a"), _call("b"), _call("c"), _response("b"), _response("a")]
    assert has_pending_tool_calls(context(*events))
    assert has_pending_tool_calls(context(*events, _response("c", will_continue=True)))
    assert not has_pending_tool_calls(context(*events, _response("c")))


def test_partial_events_do_not_complete_or_create_pending_calls(context):
    assert has_pending_tool_calls(context(_call(), _response(partial=True)))
    assert not has_pending_tool_calls(context(_call(partial=True)))


def test_old_response_cannot_resolve_reused_call_id(context):
    assert has_pending_tool_calls(context(_call(), _response(), _call()))
    assert not has_pending_tool_calls(
        context(_call(), _response(), _call(), _response())
    )


def test_only_current_agent_can_own_a_pending_call(context):
    assert not has_pending_tool_calls(context(_call(author="other")))
    assert has_pending_tool_calls(context(_call(), _response(author="other")))


def test_parallel_branch_does_not_block_or_resolve_current_branch(context):
    assert not has_pending_tool_calls(context(_call(branch="other"), branch="current"))
    assert has_pending_tool_calls(
        context(_call(branch="current"), _response(branch="other"), branch="current")
    )
    assert not has_pending_tool_calls(
        context(_call(branch="current"), _response(), branch="current")
    )


def test_old_invocation_after_cancel_cannot_block_new_turn(context):
    assert not has_pending_tool_calls(context(_call(invocation_id="cancelled-inv")))
    assert has_pending_tool_calls(context(_call(), _response(invocation_id="old-inv")))


def test_unmarked_regular_tools_do_not_block_but_default_runner_tools_do(context):
    call = _call()
    call.long_running_tool_ids = None
    assert not has_pending_tool_calls(context(call))
    assert has_pending_tool_calls(context(_call(), resumable=False))


def test_final_text_or_business_flags_do_not_resolve_another_call(context):
    text = Event(
        author="assistant",
        invocation_id="inv",
        content=types.Content(role="model", parts=[types.Part(text="Still waiting.")]),
    )
    assert text.is_final_response()
    assert has_pending_tool_calls(context(_call(), text, _response("unrelated")))


def test_nested_tool_input_can_resume_parent_without_unblocking_siblings(context):
    call = _call("parent", branch="current")
    sibling = _call("sibling", branch="current")
    call.content.parts.extend(sibling.content.parts)
    call.long_running_tool_ids.add("sibling")
    nested_input = Event(
        author="user",
        invocation_id="inv",
        branch="current.job@parent.child",
        content=types.Content(role="user", parts=[types.Part(text="Nested answer.")]),
    )
    assert has_pending_tool_calls(context(call, nested_input, branch="current"))
    assert not has_pending_tool_calls(
        context(call, nested_input, _response("sibling"), branch="current")
    )
    nested_input.invocation_id = "other-invocation"
    assert has_pending_tool_calls(
        context(call, nested_input, _response("sibling"), branch="current")
    )


def test_explicit_invocation_wins_over_reused_ids_in_a_later_invocation(context):
    response = _response("a")
    ctx = context(
        _call("a"),
        _call("b"),
        _call("a", invocation_id="later-inv"),
        _response("a", invocation_id="later-inv"),
        response,
        resumable=False,
    )
    ctx.user_content = response.content
    assert has_pending_tool_calls(ctx)


@pytest.mark.parametrize("branch", [None, "root"])
def test_explicit_child_response_cannot_resolve_root_call_with_reused_id(
    context, branch
):
    child_branch = f"{branch or 'other'}.child"
    assert has_pending_tool_calls(
        context(
            _call(branch=branch),
            _call(author="child", branch=child_branch),
            _response(branch=child_branch),
            branch=branch,
        )
    )
