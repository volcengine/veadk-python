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

import os
import json
from unittest.mock import MagicMock, patch

import pytest
from google.adk.events.event import Event
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions import Session
from google.genai import types

from veadk.memory.long_term_memory import LongTermMemory, _get_backend_cls
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)


@pytest.fixture
def mock_get_backend_cls():
    """Fixture to mock the _get_backend_cls function."""
    with patch("veadk.memory.long_term_memory._get_backend_cls") as mock_factory:
        # The factory itself returns a mock class/constructor
        mock_backend_class = MagicMock()
        # The instance of the class is also a mock
        mock_backend_instance = MagicMock(spec=BaseLongTermMemoryBackend)
        mock_backend_instance.index = "mock_index"
        mock_backend_class.return_value = mock_backend_instance

        mock_factory.return_value = mock_backend_class
        yield mock_factory


# This test is simplified as we are not testing the actual import logic here
def test_get_backend_cls():
    """Test that _get_backend_cls raises error for unsupported backend."""
    with pytest.raises(ValueError, match="Unsupported long term memory backend: foo"):
        _get_backend_cls("foo")


class TestLongTermMemory:
    """Unit tests for the LongTermMemory class."""

    def test_init_with_backend_instance(self):
        """Test initialization with a direct backend instance."""
        mock_backend_instance = MagicMock(spec=BaseLongTermMemoryBackend)
        mock_backend_instance.index = "my_test_index"

        ltm = LongTermMemory(backend=mock_backend_instance)

        assert ltm._backend is mock_backend_instance
        assert ltm.index == "my_test_index"

    def test_init_with_backend_config(self, mock_get_backend_cls):
        """Test initialization with a backend_config dictionary."""
        backend_config = {"host": "localhost", "port": 9200, "index": "my_index"}
        ltm = LongTermMemory(backend="opensearch", backend_config=backend_config)

        mock_get_backend_cls.assert_called_once_with("opensearch")
        mock_get_backend_cls.return_value.assert_called_once_with(**backend_config)
        assert ltm._backend is not None

    def test_init_with_backend_config_no_index(self, mock_get_backend_cls):
        """Test backend_config without an index falls back to app_name."""
        backend_config = {"host": "localhost", "port": 9200}
        LongTermMemory(
            backend="opensearch", backend_config=backend_config, app_name="my_app"
        )

        expected_config = backend_config.copy()
        expected_config["index"] = "my_app"
        mock_get_backend_cls.assert_called_once_with("opensearch")
        mock_get_backend_cls.return_value.assert_called_once_with(**expected_config)

    def test_init_default(self, mock_get_backend_cls):
        """Test default initialization."""
        ltm = LongTermMemory(backend="local", index="default_index")

        mock_get_backend_cls.assert_called_once_with("local")
        mock_get_backend_cls.return_value.assert_called_once_with(index="default_index")
        assert ltm.index == "default_index"

    def test_init_fallback_to_app_name(self, mock_get_backend_cls):
        """Test initialization falls back to app_name if index is not provided."""
        ltm = LongTermMemory(backend="local", app_name="my_app")
        mock_get_backend_cls.assert_called_once_with("local")
        mock_get_backend_cls.return_value.assert_called_once_with(index="my_app")
        assert ltm.index == "my_app"

    def test_init_fallback_to_default_app(self, mock_get_backend_cls):
        """Test initialization falls back to 'default_app' if no index or app_name."""
        ltm = LongTermMemory(backend="local")
        mock_get_backend_cls.assert_called_once_with("local")
        mock_get_backend_cls.return_value.assert_called_once_with(index="default_app")
        assert ltm.index == "default_app"

    def test_init_viking_mem_compatibility(self, mock_get_backend_cls):
        """Test backward compatibility for 'viking_mem' backend."""
        ltm = LongTermMemory(backend="viking_mem", index="compat_index")
        mock_get_backend_cls.assert_called_once_with("viking")
        mock_get_backend_cls.return_value.assert_called_once_with(index="compat_index")
        assert ltm.backend == "viking"  # Backend name should be updated

    @patch.dict(os.environ, {"MODEL_EMBEDDING_API_KEY": "mock_api_key"})
    def test_filter_and_convert_events(self):
        """Test the _filter_and_convert_events method."""
        ltm = LongTermMemory(backend="local")
        events = [
            # Valid user event
            Event(
                author="user",
                content=types.Content(parts=[types.Part(text="Hello world")]),
            ),
            # Non-user event (should be filtered)
            Event(
                author="model",
                content=types.Content(parts=[types.Part(text="Hi there")]),
            ),
            # Event with no content (should be filtered)
            Event(author="user", content=None),
            # Event with no parts (should be filtered)
            Event(author="user", content=types.Content()),
            # Function call event (should be filtered)
            Event(
                author="user",
                content=types.Content(
                    parts=[types.Part(function_call=types.FunctionCall(name="foo"))]
                ),
            ),
            # Valid multi-part event (only text part is relevant)
            Event(
                author="user",
                content=types.Content(parts=[types.Part(text="Another message")]),
            ),
        ]

        result = ltm._filter_and_convert_events(events)

        assert len(result) == 2
        assert "Hello world" in result[0]
        assert "Another message" in result[1]
        # Check if it's a valid JSON
        assert json.loads(result[0])["parts"][0]["text"] == "Hello world"

    @pytest.mark.asyncio
    async def test_add_session_to_memory(self):
        """Test the add_session_to_memory method."""
        mock_backend_instance = MagicMock(spec=BaseLongTermMemoryBackend)
        mock_backend_instance.index = "test_index"
        ltm = LongTermMemory(backend=mock_backend_instance)

        mock_session = Session(
            id="test_session_id", user_id="test_user", app_name="test_app"
        )
        mock_session.events.append(
            Event(
                author="user", content=types.Content(parts=[types.Part(text="Event 1")])
            )
        )
        mock_session.events.append(
            Event(
                author="model",
                content=types.Content(parts=[types.Part(text="Event 2")]),
            )
        )

        await ltm.add_session_to_memory(mock_session)

        # Verify save_memory was called with the correct, filtered events
        mock_backend_instance.save_memory.assert_called_once()
        call_args = mock_backend_instance.save_memory.call_args[1]
        assert call_args["user_id"] == "test_user"
        assert len(call_args["event_strings"]) == 1
        assert "Event 1" in call_args["event_strings"][0]

    @pytest.mark.asyncio
    async def test_search_memory_success(self):
        """Test search_memory on a successful backend call."""
        mock_backend_instance = MagicMock(spec=BaseLongTermMemoryBackend)
        mock_backend_instance.index = "test_index"
        # Simulate backend returning a JSON string from a converted Event
        event_content = types.Content(
            parts=[types.Part(text="Found memory")], role="user"
        )
        backend_return = [json.dumps(event_content.model_dump(mode="json"))]
        mock_backend_instance.search_memory.return_value = backend_return

        ltm = LongTermMemory(backend=mock_backend_instance, top_k=10)
        response = await ltm.search_memory(app_name="a", user_id="u", query="q")

        mock_backend_instance.search_memory.assert_called_once_with(
            query="q", top_k=10, user_id="u"
        )
        assert len(response.memories) == 1
        assert isinstance(response.memories[0], MemoryEntry)
        assert response.memories[0].content.parts[0].text == "Found memory"

    @pytest.mark.asyncio
    async def test_search_memory_mixed_results(self):
        """Test search_memory with mixed valid, invalid, and non-JSON results."""
        mock_backend_instance = MagicMock(spec=BaseLongTermMemoryBackend)
        mock_backend_instance.index = "test_index"
        valid_event = types.Content(parts=[types.Part(text="Valid")], role="user")
        invalid_event_json = '{"role": "user"}'  # Missing 'parts'
        backend_return = [
            json.dumps(valid_event.model_dump(mode="json")),
            "just a plain string",
            invalid_event_json,
            "another plain string",
        ]
        mock_backend_instance.search_memory.return_value = backend_return

        ltm = LongTermMemory(backend=mock_backend_instance)
        response = await ltm.search_memory(app_name="a", user_id="u", query="q")

        assert len(response.memories) == 3
        assert response.memories[0].content.parts[0].text == "Valid"
        assert response.memories[1].content.parts[0].text == "just a plain string"
        assert response.memories[2].content.parts[0].text == "another plain string"

    @pytest.mark.asyncio
    async def test_search_memory_backend_exception(self):
        """Test search_memory when the backend raises an exception."""
        mock_backend_instance = MagicMock(spec=BaseLongTermMemoryBackend)
        mock_backend_instance.index = "test_index"
        mock_backend_instance.search_memory.side_effect = Exception("DB is down")

        ltm = LongTermMemory(backend=mock_backend_instance)
        response = await ltm.search_memory(app_name="a", user_id="u", query="q")

        # Should return an empty response and not raise an exception
        assert len(response.memories) == 0
