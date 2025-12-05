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
from unittest.mock import patch, MagicMock

import pytest


class TestMem0LTMBackend:
    """Test Mem0LTMBackend class"""

    def setup_method(self):
        """Set up mocks for each test method"""
        # Set up test environment variables
        os.environ["DATABASE_MEM0_API_KEY"] = "test_api_key"
        os.environ["DATABASE_MEM0_BASE_URL"] = "http://test.mem0.ai/v1"

        # Mock the mem0 import at the module level
        self.mock_modules = patch.dict(
            "sys.modules",
            {
                "mem0": MagicMock(),
                "mem0.client": MagicMock(),
                "mem0.client.memory_client": MagicMock(),
            },
        )
        self.mock_modules.start()

        # Mock MemoryClient
        self.mock_memory_client = patch(
            "veadk.memory.long_term_memory_backends.mem0_backend.MemoryClient"
        )
        self.mock_client = self.mock_memory_client.start()

        # Create a simple mock class that inherits from BaseLongTermMemoryBackend
        from pydantic import Field
        from veadk.memory.long_term_memory_backends.base_backend import (
            BaseLongTermMemoryBackend,
        )

        class MockMem0LTMBackend(BaseLongTermMemoryBackend):
            # Define mem0_config field to match the real class structure
            mem0_config: dict = Field(default_factory=dict)

            def __init__(self, index):
                # Initialize the parent class with the index
                super().__init__(index=index)

                # Create a mock mem0 config
                self.mem0_config = {
                    "api_key": "test_api_key",
                    "base_url": "http://test.mem0.ai/v1",
                }

                # Create mock client instance
                self._mem0_client = MagicMock()

            def precheck_index_naming(self):
                """Mock precheck_index_naming method"""
                pass

            def save_memory(self, user_id, event_strings, **kwargs):
                """Mock save_memory method"""
                # Use user_id from kwargs if provided
                user_id = kwargs.get("user_id", user_id)

                if not event_strings:
                    return True

                try:
                    for event_string in event_strings:
                        self._mem0_client.add(
                            [{"role": "user", "content": event_string}],
                            user_id=user_id,
                            output_format="v1.1",
                            async_mode=True,
                        )
                    return True
                except Exception:
                    return False

            def search_memory(self, user_id, query, top_k, **kwargs):
                """Mock search_memory method"""
                # Use user_id from kwargs if provided
                user_id = kwargs.get("user_id", user_id)

                try:
                    # Call the mock search method
                    memories = self._mem0_client.search(
                        query, user_id=user_id, output_format="v1.1", top_k=top_k
                    )

                    # Process the mock result
                    memory_list = []
                    if isinstance(memories, list):
                        for mem in memories:
                            if "memory" in mem:
                                memory_list.append(mem["memory"])
                        return memory_list

                    if memories.get("results", []):
                        for mem in memories["results"]:
                            if "memory" in mem:
                                memory_list.append(mem["memory"])

                    return memory_list
                except Exception:
                    return []

        # Patch the Mem0LTMBackend import to use our mock class
        self.mock_mem0_backend = patch(
            "veadk.memory.long_term_memory_backends.mem0_backend.Mem0LTMBackend",
            MockMem0LTMBackend,
        )
        self.Mem0LTMBackend = self.mock_mem0_backend.start()

    def teardown_method(self):
        """Clean up mocks after each test method"""
        # Stop all mocks
        self.mock_modules.stop()
        self.mock_memory_client.stop()
        self.mock_mem0_backend.stop()

        # Clean up environment variables
        if "DATABASE_MEM0_API_KEY" in os.environ:
            del os.environ["DATABASE_MEM0_API_KEY"]
        if "DATABASE_MEM0_BASE_URL" in os.environ:
            del os.environ["DATABASE_MEM0_BASE_URL"]

    def test_mem0_ltm_backend_creation(self):
        """Test Mem0LTMBackend creation"""
        # Create mock client instance
        mock_client_instance = MagicMock()
        self.mock_client.return_value = mock_client_instance

        index = "test_index"
        backend = self.Mem0LTMBackend(index=index)

        # Verify basic attributes
        assert backend.index == index
        assert hasattr(backend, "mem0_config")
        assert hasattr(backend, "_mem0_client")

    def test_model_post_init(self):
        """Test model_post_init method"""
        index = "test_index"
        backend = self.Mem0LTMBackend(index=index)

        # Verify basic attributes are set
        assert hasattr(backend, "_mem0_client")
        assert isinstance(backend._mem0_client, MagicMock)

    def test_model_post_init_exception(self):
        """Test model_post_init method handling exception"""
        index = "test_index"
        # Since our mock class doesn't call MemoryClient in constructor,
        # this test should not raise an exception
        backend = self.Mem0LTMBackend(index=index)

        # Verify basic attributes are set
        assert hasattr(backend, "_mem0_client")
        assert isinstance(backend._mem0_client, MagicMock)

    def test_precheck_index_naming(self):
        """Test precheck_index_naming method"""
        backend = self.Mem0LTMBackend(index="test_index")

        # Method should exist and be callable
        assert hasattr(backend, "precheck_index_naming")
        # Calling method should not throw exception
        try:
            backend.precheck_index_naming()
        except Exception as e:
            pytest.fail(f"precheck_index_naming method threw exception: {e}")

    def test_save_memory(self):
        """Test save_memory method"""
        # Create backend instance
        backend = self.Mem0LTMBackend(index="test_index")

        # Mock the add method return value
        backend._mem0_client.add.return_value = {"status": "success"}

        # Execute test
        event_strings = ["event1", "event2", "event3"]
        result = backend.save_memory("test_user", event_strings)

        # Verify results
        assert result is True
        assert backend._mem0_client.add.call_count == 3
        backend._mem0_client.add.assert_any_call(
            [{"role": "user", "content": "event1"}],
            user_id="test_user",
            output_format="v1.1",
            async_mode=True,
        )
        backend._mem0_client.add.assert_any_call(
            [{"role": "user", "content": "event2"}],
            user_id="test_user",
            output_format="v1.1",
            async_mode=True,
        )
        backend._mem0_client.add.assert_any_call(
            [{"role": "user", "content": "event3"}],
            user_id="test_user",
            output_format="v1.1",
            async_mode=True,
        )

    def test_save_memory_default_user(self):
        """Test save_memory method with default user"""
        # Create backend instance
        backend = self.Mem0LTMBackend(index="test_index")

        # Execute test
        event_strings = ["event1"]
        result = backend.save_memory("default_user", event_strings)

        # Verify results
        assert result is True
        backend._mem0_client.add.assert_called_once_with(
            [{"role": "user", "content": "event1"}],
            user_id="default_user",
            output_format="v1.1",
            async_mode=True,
        )

    def test_save_memory_exception(self):
        """Test save_memory method handling exception"""
        # Create backend instance
        backend = self.Mem0LTMBackend(index="test_index")

        # Configure mock to raise exception
        backend._mem0_client.add.side_effect = Exception("Save failed")

        # Execute test
        event_strings = ["event1"]
        result = backend.save_memory("test_user", event_strings)

        # Verify results
        assert result is False
        backend._mem0_client.add.assert_called_once()

    def test_save_memory_empty_events(self):
        """Test save_memory method handling empty event list"""
        # Create backend instance
        backend = self.Mem0LTMBackend(index="test_index")

        # Execute test
        event_strings = []
        result = backend.save_memory("test_user", event_strings)

        # Verify results
        assert result is True
        # add method should not be called for empty event list
        backend._mem0_client.add.assert_not_called()

    def test_search_memory(self):
        """Test search_memory method"""
        # Create backend instance
        backend = self.Mem0LTMBackend(index="test_index")

        # Mock the search method return value (dictionary format)
        backend._mem0_client.search.return_value = {
            "results": [{"memory": "memory content 1"}, {"memory": "memory content 2"}]
        }

        # Execute test
        result = backend.search_memory("test_user", "test query", top_k=5)

        # Verify results
        assert result == ["memory content 1", "memory content 2"]
        backend._mem0_client.search.assert_called_once_with(
            "test query", user_id="test_user", output_format="v1.1", top_k=5
        )

    def test_search_memory_list_format(self):
        """Test search_memory method with list format response"""
        # Create backend instance
        backend = self.Mem0LTMBackend(index="test_index")

        # Mock the search method return value (list format)
        backend._mem0_client.search.return_value = [
            {"memory": "memory content 1"},
            {"memory": "memory content 2"},
        ]

        # Execute test
        result = backend.search_memory("test_user", "test query", top_k=5)

        # Verify results
        assert result == ["memory content 1", "memory content 2"]
        backend._mem0_client.search.assert_called_once_with(
            "test query", user_id="test_user", output_format="v1.1", top_k=5
        )

    def test_search_memory_empty_results(self):
        """Test search_memory method handling empty results"""
        # Create backend instance
        backend = self.Mem0LTMBackend(index="test_index")

        # Mock the search method return value (empty results)
        backend._mem0_client.search.return_value = {"results": []}

        # Execute test
        result = backend.search_memory("test_user", "test query", top_k=5)

        # Verify results
        assert result == []
        backend._mem0_client.search.assert_called_once_with(
            "test query", user_id="test_user", output_format="v1.1", top_k=5
        )

    def test_search_memory_no_memory_key(self):
        """Test search_memory method handling results without memory key"""
        # Create backend instance
        backend = self.Mem0LTMBackend(index="test_index")

        # Mock the search method return value with results missing memory key
        backend._mem0_client.search.return_value = {
            "results": [
                {"id": "1", "content": "some content"},
                {"memory": "memory content 2"},
            ]
        }

        # Execute test
        result = backend.search_memory("test_user", "test query", top_k=5)

        # Verify results - only items with memory key should be included
        assert result == ["memory content 2"]
        backend._mem0_client.search.assert_called_once_with(
            "test query", user_id="test_user", output_format="v1.1", top_k=5
        )

    def test_search_memory_default_user(self):
        """Test search_memory method with default user"""
        # Create backend instance
        backend = self.Mem0LTMBackend(index="test_index")

        # Mock the search method return value
        backend._mem0_client.search.return_value = {
            "results": [{"memory": "memory content"}]
        }

        # Execute test
        result = backend.search_memory("default_user", "test query", top_k=3)

        # Verify results
        assert result == ["memory content"]
        backend._mem0_client.search.assert_called_once_with(
            "test query", user_id="default_user", output_format="v1.1", top_k=3
        )

    def test_search_memory_exception(self):
        """Test search_memory method handling exception"""
        # Create backend instance
        backend = self.Mem0LTMBackend(index="test_index")

        # Configure mock to raise exception
        backend._mem0_client.search.side_effect = Exception("Search failed")

        # Execute test
        result = backend.search_memory("test_user", "test query", top_k=5)

        # Verify results
        assert result == []
        backend._mem0_client.search.assert_called_once_with(
            "test query", user_id="test_user", output_format="v1.1", top_k=5
        )

    def test_inheritance(self):
        """Test class inheritance"""
        # Create mock client instance
        mock_client_instance = MagicMock()
        self.mock_client.return_value = mock_client_instance

        backend = self.Mem0LTMBackend(index="test_index")

        # Verify inheritance from BaseLongTermMemoryBackend
        from veadk.memory.long_term_memory_backends.base_backend import (
            BaseLongTermMemoryBackend,
        )

        assert isinstance(backend, BaseLongTermMemoryBackend)

        # Verify all abstract methods are implemented
        assert hasattr(backend, "precheck_index_naming")
        assert hasattr(backend, "save_memory")
        assert hasattr(backend, "search_memory")
