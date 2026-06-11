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

"""Unit tests for ``veadk.memory.short_term_memory_processor``.

The processor calls ``litellm.completion`` to summarize a session's history.
That call is mocked so no model / network access happens.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from google.adk.events.event import Event
from google.adk.sessions import Session
from google.genai.types import Content, Part

from veadk.memory import short_term_memory_processor as stmp
from veadk.memory.short_term_memory_processor import ShortTermMemoryProcessor


def _event(role: str, text: str) -> Event:
    return Event(
        author=role,
        content=Content(role=role, parts=[Part(text=text)]),
    )


def _make_session(events: list[Event]) -> Session:
    return Session(
        id="session-1",
        app_name="app",
        user_id="user",
        events=events,
    )


def _completion_returning(payload: object) -> MagicMock:
    """Build a fake litellm completion response wrapping ``payload`` as JSON."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = json.dumps(payload)
    return response


def test_after_load_session_replaces_events_with_summary():
    session = _make_session([_event("user", "hello"), _event("model", "hi")])

    abstracted = [
        {"role": "user", "content": "summary-user"},
        {"role": "model", "content": "summary-model"},
    ]

    processor = ShortTermMemoryProcessor()
    with patch.object(
        stmp, "completion", return_value=_completion_returning(abstracted)
    ) as mock_completion:
        result = processor.after_load_session(session)

    mock_completion.assert_called_once()
    # Events fully replaced by the abstracted messages.
    assert len(result.events) == 2
    assert result.events[0].author == "memory_optimizer"
    assert result.events[0].content is not None
    assert result.events[0].content.parts is not None
    assert result.events[0].content.parts[0].text == "summary-user"
    assert result.events[1].content is not None
    assert result.events[1].content.role == "model"


def test_after_load_session_skips_events_without_content():
    empty = Event(author="user", content=None)
    valid = _event("user", "keep me")
    session = _make_session([empty, valid])

    captured_messages = {}

    def fake_render(messages):
        captured_messages["messages"] = messages
        return "rendered-prompt"

    processor = ShortTermMemoryProcessor()
    with (
        patch.object(stmp, "render_prompt", side_effect=fake_render),
        patch.object(stmp, "completion", return_value=_completion_returning([])),
    ):
        processor.after_load_session(session)

    # Only the event carrying content should reach the prompt renderer.
    assert captured_messages["messages"] == [{"role": "user", "content": "keep me"}]


@pytest.mark.asyncio
async def test_patch_wraps_get_session_and_post_processes():
    """``patch()`` returns a decorator that runs ``after_load_session`` on the
    awaited result of the wrapped coroutine."""
    processor = ShortTermMemoryProcessor()
    decorator = processor.patch()

    sentinel_session = _make_session([_event("user", "hi")])
    processed = object()

    async def original_get_session(*args, **kwargs):
        return sentinel_session

    with patch.object(
        processor, "after_load_session", return_value=processed
    ) as mock_after:
        wrapped = decorator(original_get_session)
        out = await wrapped("a", b="c")

    mock_after.assert_called_once_with(sentinel_session)
    assert out is processed


@pytest.mark.asyncio
async def test_patch_passes_through_none_session():
    """If the wrapped function returns ``None`` no post-processing is done."""
    processor = ShortTermMemoryProcessor()
    decorator = processor.patch()

    async def original_get_session(*args, **kwargs):
        return None

    with patch.object(processor, "after_load_session") as mock_after:
        wrapped = decorator(original_get_session)
        out = await wrapped()

    assert out is None
    mock_after.assert_not_called()
