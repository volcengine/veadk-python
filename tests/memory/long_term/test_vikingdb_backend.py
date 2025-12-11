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
import os
from unittest.mock import patch, MagicMock

import pytest


class TestVikingDBLTMBackend:
    """Test VikingDBLTMBackend class"""

    def setup_method(self):
        """Set up mocks for each test method"""
        # Set up test environment variables
        os.environ["VOLCENGINE_ACCESS_KEY"] = "test_access_key"
        os.environ["VOLCENGINE_SECRET_KEY"] = "test_secret_key"
        os.environ["DATABASE_VIKINGMEM_MEMORY_TYPE"] = "event_v1,sys_event_v1"

        # Create mock instances
        self.mock_vikingdb_client = MagicMock()
        self.mock_credential = MagicMock(
            access_key_id="test_ak",
            secret_access_key="test_sk",
            session_token="test_token",
        )

        # Mock the external dependencies before importing the class
        # We need to patch the imports within the vikingdb_backend module
        self.mock_vikingdb_patch = patch(
            "veadk.memory.long_term_memory_backends.vikingdb_memory_backend.VikingDBMemoryClient",
            return_value=self.mock_vikingdb_client,
        )
        self.mock_credential_patch = patch(
            "veadk.memory.long_term_memory_backends.vikingdb_memory_backend.get_credential_from_vefaas_iam",
            return_value=self.mock_credential,
        )

        # Start the patches and store the mock objects
        self.mock_vikingdb_class = self.mock_vikingdb_patch.start()
        self.mock_get_credential = self.mock_credential_patch.start()

        # Configure mock returns
        self.mock_vikingdb_client.get_collection.return_value = {
            "code": 0,
            "data": {"collection_name": "test_index"},
        }
        self.mock_vikingdb_client.create_collection.return_value = {
            "code": 0,
            "data": {"collection_name": "test_index"},
        }
        self.mock_vikingdb_client.add_messages.return_value = {
            "code": 0,
            "data": {"message_ids": ["msg1", "msg2"]},
        }
        self.mock_vikingdb_client.search_memory.return_value = {
            "code": 0,
            "data": {
                "result_list": [
                    {"memory_info": {"summary": "test result 1"}},
                    {"memory_info": {"summary": "test result 2"}},
                ]
            },
        }

        # Import the actual class after mocking
        from veadk.memory.long_term_memory_backends.vikingdb_memory_backend import (
            VikingDBLTMBackend,
        )

        self.VikingDBLTMBackend = VikingDBLTMBackend

    def teardown_method(self):
        """Clean up mocks after each test method"""
        # Stop all patches
        self.mock_vikingdb_patch.stop()
        self.mock_credential_patch.stop()

        # Clean up environment variables
        env_vars = [
            "VOLCENGINE_ACCESS_KEY",
            "VOLCENGINE_SECRET_KEY",
            "DATABASE_VIKINGMEM_MEMORY_TYPE",
        ]
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]

    def test_vikingdb_ltm_backend_creation(self):
        """Test VikingDBLTMBackend creation"""
        index = "test_index"
        backend = self.VikingDBLTMBackend(index=index)

        # Verify basic attributes
        assert backend.index == index
        assert backend.volcengine_access_key == "test_access_key"
        assert backend.volcengine_secret_key == "test_secret_key"
        assert backend.region == "cn-beijing"

    def test_model_post_init_with_env_memory_type(self):
        """Test model_post_init method with environment memory type"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Call model_post_init
        backend.model_post_init(None)

        # Verify memory type is set from environment
        assert backend.memory_type == ["event_v1", "sys_event_v1"]

        # Verify collection existence check was performed
        # Note: get_collection is called twice - once during model_post_init and once during this test
        assert self.mock_vikingdb_client.get_collection.call_count >= 1
        self.mock_vikingdb_client.get_collection.assert_called_with(
            collection_name="test_index"
        )

    def test_model_post_init_with_default_memory_type(self):
        """Test model_post_init method with default memory type"""
        # Remove environment variable to test default behavior
        del os.environ["DATABASE_VIKINGMEM_MEMORY_TYPE"]

        backend = self.VikingDBLTMBackend(index="test_index")

        # Call model_post_init
        backend.model_post_init(None)

        # Verify default memory type is set
        assert backend.memory_type == ["sys_event_v1", "event_v1"]

    def test_model_post_init_collection_creation(self):
        """Test model_post_init method when collection needs to be created"""
        # Mock collection not existing
        self.mock_vikingdb_client.get_collection.side_effect = Exception(
            "Collection not found"
        )

        backend = self.VikingDBLTMBackend(index="test_index")

        # Call model_post_init
        backend.model_post_init(None)

        # Verify collection creation was attempted
        # Note: create_collection is called twice - once during model_post_init and once during this test
        assert self.mock_vikingdb_client.create_collection.call_count >= 1
        self.mock_vikingdb_client.create_collection.assert_called_with(
            collection_name="test_index",
            description="Created by Volcengine Agent Development Kit VeADK",
            builtin_event_types=["event_v1", "sys_event_v1"],
        )

    def test_precheck_index_naming_valid(self):
        """Test precheck_index_naming method with valid index names"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Test valid index names
        valid_names = ["test", "test_index", "test123", "t", "a" * 128]
        for name in valid_names:
            backend.index = name
            backend.precheck_index_naming()  # Should not raise exception

    def test_precheck_index_naming_invalid(self):
        """Test precheck_index_naming method with invalid index names"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Test invalid index names
        invalid_names = [
            "_test",  # starts with underscore
            "1test",  # starts with number
            "test@",  # contains special character
            "",  # empty string
            "a" * 129,  # too long
            "test space",  # contains space
            "Test-Case",  # contains hyphen
        ]

        for name in invalid_names:
            backend.index = name
            with pytest.raises(ValueError, match="does not conform to the rules"):
                backend.precheck_index_naming()

    def test_collection_exist(self):
        """Test _collection_exist method"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Test when collection exists
        result = backend._collection_exist()

        # Verify client was called correctly
        # Note: get_collection is called twice - once during model_post_init and once during this test
        assert self.mock_vikingdb_client.get_collection.call_count >= 1
        self.mock_vikingdb_client.get_collection.assert_called_with(
            collection_name="test_index"
        )
        assert result is True

    def test_collection_not_exist(self):
        """Test _collection_exist method when collection does not exist"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Mock collection not existing
        self.mock_vikingdb_client.get_collection.side_effect = Exception(
            "Collection not found"
        )

        result = backend._collection_exist()

        # Verify result is False when collection doesn't exist
        assert result is False

    def test_create_collection(self):
        """Test _create_collection method"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Set memory type for the test
        backend.memory_type = ["event_v1", "sys_event_v1"]

        result = backend._create_collection()

        # Verify collection creation parameters
        self.mock_vikingdb_client.create_collection.assert_called_once_with(
            collection_name="test_index",
            description="Created by Volcengine Agent Development Kit VeADK",
            builtin_event_types=["event_v1", "sys_event_v1"],
        )

        # Verify result
        assert result == {"code": 0, "data": {"collection_name": "test_index"}}

    def test_get_client_with_credentials(self):
        """Test _get_client method with provided credentials"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Test with provided credentials
        client = backend._get_client()

        # Verify client was created with correct parameters
        # The mock client is returned by our patch, so we verify it was used
        assert client == self.mock_vikingdb_client

        # Verify get_credential_from_vefaas_iam was NOT called
        # Since we provided credentials via environment variables
        # We can verify this by checking that the mock was not called
        # The mock function is accessed directly from the patch
        assert not self.mock_get_credential.called

    def test_save_memory(self):
        """Test save_memory method"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Execute test
        event_strings = [
            json.dumps({"role": "user", "parts": [{"text": "Hello"}]}),
            json.dumps({"role": "assistant", "parts": [{"text": "Hi there!"}]}),
        ]
        result = backend.save_memory("test_user", event_strings)

        # Verify add_messages was called with correct parameters
        # The mock client should have been called
        assert self.mock_vikingdb_client.add_messages.called
        call_args = self.mock_vikingdb_client.add_messages.call_args

        # Check basic call parameters
        assert call_args.kwargs["collection_name"] == "test_index"
        assert "session_id" in call_args.kwargs

        # Check messages structure
        messages = call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hi there!"

        # Check metadata
        metadata = call_args.kwargs["metadata"]
        assert metadata["default_user_id"] == "test_user"
        assert metadata["default_assistant_id"] == "assistant"
        assert isinstance(metadata["time"], int)

        # Verify results
        assert result is True

    def test_save_memory_empty_events(self):
        """Test save_memory method with empty event list"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Execute test with empty events
        event_strings = []
        result = backend.save_memory("test_user", event_strings)

        # Verify add_messages was called with empty messages
        # The mock client should have been called
        assert self.mock_vikingdb_client.add_messages.called
        call_args = self.mock_vikingdb_client.add_messages.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 0

        # Verify results
        assert result is True

    def test_save_memory_error_handling(self):
        """Test save_memory method error handling"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Mock API error
        self.mock_vikingdb_client.add_messages.return_value = {
            "code": 1,
            "message": "API error",
        }

        # Execute test
        event_strings = [json.dumps({"role": "user", "parts": [{"text": "Hello"}]})]

        with pytest.raises(ValueError, match="Save VikingDB memory error"):
            backend.save_memory("test_user", event_strings)

    def test_search_memory(self):
        """Test search_memory method"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Set memory type for the test
        backend.memory_type = ["event_v1", "sys_event_v1"]

        # Execute test
        query = "test query"
        top_k = 5
        result = backend.search_memory("test_user", query, top_k)

        # Verify search_memory was called with correct parameters
        # The mock client should have been called
        assert self.mock_vikingdb_client.search_memory.called
        self.mock_vikingdb_client.search_memory.assert_called_once_with(
            collection_name="test_index",
            query="test query",
            filter={
                "user_id": "test_user",
                "memory_type": ["event_v1", "sys_event_v1"],
            },
            limit=5,
        )

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 2

        # Verify result format
        for res in result:
            parsed = json.loads(res)
            assert parsed["role"] == "user"
            assert "parts" in parsed
            assert "text" in parsed["parts"][0]

    def test_search_memory_empty_results(self):
        """Test search_memory method with empty results"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Mock empty results
        self.mock_vikingdb_client.search_memory.return_value = {
            "code": 0,
            "data": {"result_list": []},
        }

        # Execute test
        result = backend.search_memory("test_user", "test query", 5)

        # Verify empty list is returned
        assert result == []

    def test_search_memory_error_handling(self):
        """Test search_memory method error handling"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Mock API error
        self.mock_vikingdb_client.search_memory.return_value = {
            "code": 1,
            "message": "Search error",
        }

        # Execute test
        with pytest.raises(ValueError, match="Search VikingDB memory error"):
            backend.search_memory("test_user", "test query", 5)

    def test_inheritance(self):
        """Test class inheritance"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Verify inheritance from BaseLongTermMemoryBackend
        from veadk.memory.long_term_memory_backends.base_backend import (
            BaseLongTermMemoryBackend,
        )

        assert isinstance(backend, BaseLongTermMemoryBackend)

    def test_session_id_generation(self):
        """Test that each save operation generates unique session IDs"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Execute multiple save operations
        event_strings = [json.dumps({"role": "user", "parts": [{"text": "Hello"}]})]

        backend.save_memory("user1", event_strings)
        backend.save_memory("user2", event_strings)

        # Verify two different session IDs were generated
        call1_session = self.mock_vikingdb_client.add_messages.call_args_list[0].kwargs[
            "session_id"
        ]
        call2_session = self.mock_vikingdb_client.add_messages.call_args_list[1].kwargs[
            "session_id"
        ]

        assert call1_session != call2_session
        assert isinstance(call1_session, str)
        assert isinstance(call2_session, str)

    def test_timestamp_generation(self):
        """Test that timestamps are correctly generated"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Execute test
        event_strings = [json.dumps({"role": "user", "parts": [{"text": "Hello"}]})]
        backend.save_memory("test_user", event_strings)

        # Verify timestamp is in milliseconds
        call_args = self.mock_vikingdb_client.add_messages.call_args
        metadata = call_args.kwargs["metadata"]
        timestamp = metadata["time"]

        # Should be a large number (milliseconds since epoch)
        assert timestamp > 1000000000000  # After year 2001
        assert timestamp < 5000000000000  # Before year 2128

    def test_role_conversion(self):
        """Test role conversion logic"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Test various role conversions
        event_strings = [
            json.dumps({"role": "user", "parts": [{"text": "User message"}]}),
            json.dumps({"role": "assistant", "parts": [{"text": "Assistant message"}]}),
            json.dumps({"role": "system", "parts": [{"text": "System message"}]}),
            json.dumps({"role": "unknown", "parts": [{"text": "Unknown message"}]}),
        ]

        backend.save_memory("test_user", event_strings)

        # Verify role conversion
        call_args = self.mock_vikingdb_client.add_messages.call_args
        messages = call_args.kwargs["messages"]

        assert messages[0]["role"] == "user"  # user -> user
        assert messages[1]["role"] == "assistant"  # assistant -> assistant
        assert messages[2]["role"] == "assistant"  # system -> assistant (converted)
        assert messages[3]["role"] == "assistant"  # unknown -> assistant (converted)

    def test_config_validation(self):
        """Test configuration validation"""
        backend = self.VikingDBLTMBackend(index="test_index")

        # Verify configs are properly initialized
        assert backend.volcengine_access_key == "test_access_key"
        assert backend.volcengine_secret_key == "test_secret_key"
        assert backend.region == "cn-beijing"
        assert backend.memory_type == ["event_v1", "sys_event_v1"]
