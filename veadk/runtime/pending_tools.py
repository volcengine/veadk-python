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

"""Keep partial external-tool results from restarting an agent's model."""

from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event


def has_pending_tool_calls(ctx: InvocationContext) -> bool:
    """Wait for this agent's unresolved calls, preserving nested branch resume."""
    branch_events = [
        event for event in ctx._get_events(current_branch=True) if not event.partial
    ]
    invocation_id = ctx.invocation_id
    if not ctx.is_resumable and ctx.user_content:
        response_ids = {
            part.function_response.id
            for part in ctx.user_content.parts or []
            if part.function_response and part.function_response.id
        }
        # The default Runner gives each submitted result a new invocation ID.
        # An explicit result still resumes its original call's external batch.
        matching_calls = [
            event
            for event in reversed(branch_events)
            if event.author == ctx.agent.name
            and any(call.id in response_ids for call in event.get_function_calls())
        ]
        if matching_calls:
            owner = next(
                (
                    event
                    for event in matching_calls
                    if event.invocation_id == invocation_id
                ),
                matching_calls[0],
            )
            invocation_id = owner.invocation_id

    external_resume = invocation_id != ctx.invocation_id
    pending: dict[str, Event] = {}
    owned_ids: set[str] = set()
    events = []
    for event in branch_events:
        owns_invocation = event.invocation_id == invocation_id
        responses = event.get_function_responses()
        if not owns_invocation and not (
            external_resume
            and event.author in {"user", ctx.agent.name}
            and any(response.id in owned_ids for response in responses)
        ):
            continue
        events.append(event)
        if owns_invocation and event.author == ctx.agent.name:
            for call in event.get_function_calls():
                if call.id and call.id in (event.long_running_tool_ids or ()):
                    pending[call.id] = event
                    owned_ids.add(call.id)
        if event.author in {"user", ctx.agent.name}:
            for response in responses:
                owner = pending.get(response.id)
                if (
                    owner is not None
                    and response.will_continue is not True
                    and (event.branch is None or event.branch == owner.branch)
                ):
                    pending.pop(response.id, None)

    if not pending:
        return False

    # ADK exempts a parent tool when input is resuming its nested branch. Scope
    # that check to this invocation, and to only the still-unresolved call IDs.
    scoped_ctx = ctx.model_copy(
        update={"session": ctx.session.model_copy(update={"events": events})}
    )
    return any(
        scoped_ctx.should_pause_invocation(
            event.model_copy(update={"long_running_tool_ids": {call_id}})
        )
        for call_id, event in pending.items()
    )
