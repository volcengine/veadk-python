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

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.adk.events.event import Event
from google.adk.sessions import Session
from google.genai.types import Content, Part

from veadk.memory.short_term_memory_processor import ShortTermMemoryProcessor


@pytest.fixture
def processor():
    """Fixture to provide a ShortTermMemoryProcessor instance."""
    return ShortTermMemoryProcessor()


class TestShortTermMemoryProcessor:
    """Unit tests for the ShortTermMemoryProcessor class."""

    def test_init(self, processor):
        """Test that the processor initializes without errors."""
        assert isinstance(processor, ShortTermMemoryProcessor)

    @pytest.mark.asyncio
    async def test_patch_with_session(self, processor):
        """Test that the patch intercepts and processes a valid session."""
        # 1. Create a fake original get_session function
        original_session = Session(id="1", user_id="u1", app_name="a1")
        original_get_session = AsyncMock(return_value=original_session)

        # 2. Mock the actual processing method to isolate the patch logic
        processor.after_load_session = MagicMock(return_value="processed_session")

        # 3. Apply the patch (decorator)
        decorator = processor.patch()
        decorated_get_session = decorator(original_get_session)

        # 4. Call the decorated function
        result = await decorated_get_session("arg1", kwarg1="kw1")

        # 5. Assertions
        original_get_session.assert_awaited_once_with("arg1", kwarg1="kw1")
        processor.after_load_session.assert_called_once_with(original_session)
        assert result == "processed_session"

    @pytest.mark.asyncio
    async def test_patch_with_none_session(self, processor):
        """Test that the patch does nothing if get_session returns None."""
        original_get_session = AsyncMock(return_value=None)
        processor.after_load_session = MagicMock()

        decorator = processor.patch()
        decorated_get_session = decorator(original_get_session)

        result = await decorated_get_session()

        original_get_session.assert_awaited_once()
        processor.after_load_session.assert_not_called()
        assert result is None

    @patch("veadk.memory.short_term_memory_processor.completion")
    @patch("veadk.memory.short_term_memory_processor.render_prompt")
    def test_after_load_session(self, mock_render_prompt, mock_completion, processor):
        """Test the core AI summarization logic in after_load_session."""
        # 1. Setup Mocks
        mock_render_prompt.return_value = "This is the generated prompt."

        # Mock the response from the LLM
        mock_llm_response = MagicMock()
        summarized_messages = [
            {"role": "user", "content": "Summarized question."},
            {"role": "assistant", "content": "Summarized answer."},
        ]
        mock_llm_response.choices[0].message.content = json.dumps(summarized_messages)
        mock_completion.return_value = mock_llm_response

        # 2. Create a sample session with various events
        session = Session(id="s1", user_id="u1", app_name="a1")
        session.events = [
            Event(
                author="user", content=Content(role="user", parts=[Part(text="Hello")])
            ),
            Event(
                author="model",
                content=Content(role="model", parts=[Part(text="Hi there")]),
            ),
            Event(author="user", content=None),  # Should be skipped
            Event(author="user", content=Content(parts=[])),  # Should be skipped
        ]

        # 3. Call the method under test
        result_session = processor.after_load_session(session)

        # 4. Assertions
        # Check that the original session object is modified and returned
        assert result_session is session

        # Check that messages were correctly filtered and passed to the prompt renderer
        mock_render_prompt.assert_called_once()
        call_args = mock_render_prompt.call_args[1]
        expected_messages_for_prompt = [
            {"role": "user", "content": "Hello"},
            {"role": "model", "content": "Hi there"},
        ]
        assert call_args["messages"] == expected_messages_for_prompt

        # Check that the LLM was called correctly
        mock_completion.assert_called_once()
        llm_call_args = mock_completion.call_args[1]
        assert (
            llm_call_args["messages"][0]["content"] == "This is the generated prompt."
        )

        # Check that the session events were replaced with the summarized content
        assert len(result_session.events) == 2
        assert result_session.events[0].author == "memory_optimizer"
        assert result_session.events[0].content.role == "user"
        assert result_session.events[0].content.parts[0].text == "Summarized question."
        assert result_session.events[1].author == "memory_optimizer"
        assert result_session.events[1].content.role == "assistant"
        assert result_session.events[1].content.parts[0].text == "Summarized answer."
