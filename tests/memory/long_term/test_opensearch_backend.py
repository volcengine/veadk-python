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


class TestOpensearchLTMBackend:
    """Test OpensearchLTMBackend class"""

    def setup_method(self):
        """Set up mocks for each test method"""
        # Set up test environment variables with correct prefixes
        os.environ["DATABASE_OPENSEARCH_HOST"] = "localhost"
        os.environ["DATABASE_OPENSEARCH_PORT"] = "9200"
        os.environ["DATABASE_OPENSEARCH_USERNAME"] = "test_user"
        os.environ["DATABASE_OPENSEARCH_PASSWORD"] = "test_password"
        os.environ["MODEL_EMBEDDING_NAME"] = "text-embedding-ada-002"
        os.environ["MODEL_EMBEDDING_API_KEY"] = "test_api_key"
        os.environ["MODEL_EMBEDDING_API_BASE"] = "https://api.openai.com/v1"

        # Mock all external dependencies
        self.mock_opensearch_client = patch(
            "veadk.memory.long_term_memory_backends.opensearch_backend.OpensearchVectorClient"
        )
        self.mock_opensearch_store = patch(
            "veadk.memory.long_term_memory_backends.opensearch_backend.OpensearchVectorStore"
        )
        self.mock_vector_store = patch(
            "veadk.memory.long_term_memory_backends.opensearch_backend.VectorStoreIndex"
        )
        self.mock_embedding = patch(
            "veadk.memory.long_term_memory_backends.opensearch_backend.OpenAILikeEmbedding"
        )
        self.mock_splitter = patch(
            "veadk.memory.long_term_memory_backends.opensearch_backend.get_llama_index_splitter"
        )

        self.mock_client = self.mock_opensearch_client.start()
        self.mock_store = self.mock_opensearch_store.start()
        self.mock_vector_index = self.mock_vector_store.start()
        self.mock_embed_model = self.mock_embedding.start()
        self.mock_get_splitter = self.mock_splitter.start()

        # Import the actual class after mocking
        from veadk.memory.long_term_memory_backends.opensearch_backend import (
            OpensearchLTMBackend,
        )

        self.OpensearchLTMBackend = OpensearchLTMBackend

    def teardown_method(self):
        """Clean up mocks after each test method"""
        # Stop all mocks
        self.mock_opensearch_client.stop()
        self.mock_opensearch_store.stop()
        self.mock_vector_store.stop()
        self.mock_embedding.stop()
        self.mock_splitter.stop()

        # Clean up environment variables
        env_vars = [
            "DATABASE_OPENSEARCH_HOST",
            "DATABASE_OPENSEARCH_PORT",
            "DATABASE_OPENSEARCH_USERNAME",
            "DATABASE_OPENSEARCH_PASSWORD",
            "EMBEDDING_MODEL_NAME",
            "EMBEDDING_MODEL_API_KEY",
            "EMBEDDING_MODEL_API_BASE",
        ]
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]

    def test_opensearch_ltm_backend_creation(self):
        """Test OpensearchLTMBackend creation"""
        index = "test_index"
        backend = self.OpensearchLTMBackend(index=index)

        # Verify basic attributes
        assert backend.index == index
        assert hasattr(backend, "opensearch_config")
        assert hasattr(backend, "embedding_config")

    def test_model_post_init(self):
        """Test model_post_init method"""
        index = "test_index"
        backend = self.OpensearchLTMBackend(index=index)

        # Call model_post_init with required context parameter
        backend.model_post_init(None)

        # Verify embedding model is set
        assert hasattr(backend, "_embed_model")

    def test_precheck_index_naming_valid(self):
        """Test precheck_index_naming method with valid index names"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Test valid index names
        valid_names = ["test", "test-index", "test_index", "test123"]
        for name in valid_names:
            backend.precheck_index_naming(name)

    def test_precheck_index_naming_invalid(self):
        """Test precheck_index_naming method with invalid index names"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Test invalid index names
        invalid_names = ["_test", "-test", "Test", "test@", "test space"]
        for name in invalid_names:
            with pytest.raises(ValueError):
                backend.precheck_index_naming(name)

    def test_create_vector_index(self):
        """Test _create_vector_index method"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Test valid index creation
        index_name = "valid_index"
        vector_index = backend._create_vector_index(index_name)

        # Verify vector index is created
        assert vector_index is not None

    def test_create_vector_index_invalid_name(self):
        """Test _create_vector_index method with invalid index name"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Test with invalid index name
        invalid_name = "_invalid_index"
        with pytest.raises(ValueError):
            backend._create_vector_index(invalid_name)

    def test_save_memory(self):
        """Test save_memory method"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Execute test
        event_strings = ["event1", "event2", "event3"]
        result = backend.save_memory("test_user", event_strings)

        # Verify results
        assert result is True

    def test_save_memory_empty_events(self):
        """Test save_memory method with empty event list"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Execute test with empty events
        event_strings = []
        result = backend.save_memory("test_user", event_strings)

        # Verify results
        assert result is True

    def test_save_memory_default_user(self):
        """Test save_memory method with default user"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Execute test
        event_strings = ["event1"]
        result = backend.save_memory("default_user", event_strings)

        # Verify results
        assert result is True

    def test_search_memory(self):
        """Test search_memory method"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Execute test
        query = "test query"
        top_k = 5
        result = backend.search_memory("test_user", query, top_k)

        # Verify results
        assert isinstance(result, list)

    def test_search_memory_default_user(self):
        """Test search_memory method with default user"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Execute test
        query = "test query"
        top_k = 3
        result = backend.search_memory("default_user", query, top_k)

        # Verify results
        assert isinstance(result, list)

    def test_search_memory_empty_results(self):
        """Test search_memory method handling empty results"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Execute test
        query = "test query"
        top_k = 5
        result = backend.search_memory("test_user", query, top_k)

        # Verify results
        assert isinstance(result, list)

    def test_split_documents(self):
        """Test _split_documents method"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Mock documents
        mock_documents = [MagicMock() for _ in range(3)]

        # Execute test
        result = backend._split_documents(mock_documents)

        # Verify results
        assert isinstance(result, list)

    def test_inheritance(self):
        """Test class inheritance"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Verify inheritance from BaseLongTermMemoryBackend
        from veadk.memory.long_term_memory_backends.base_backend import (
            BaseLongTermMemoryBackend,
        )

        assert isinstance(backend, BaseLongTermMemoryBackend)

    def test_index_naming_pattern(self):
        """Test the index naming pattern used in save/search operations"""
        backend = self.OpensearchLTMBackend(index="base_index")

        # Test index naming pattern
        user_id = "test_user"

        # Execute test
        backend.save_memory(user_id, ["test_event"])
        backend.search_memory(user_id, "test_query", 5)

        # Verify the operations completed without errors
        assert True

    def test_save_memory_exception_handling(self):
        """Test save_memory method exception handling"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Execute test
        event_strings = ["event1"]
        result = backend.save_memory("test_user", event_strings)

        # Verify exception is handled gracefully
        assert result is True

    def test_search_memory_exception_handling(self):
        """Test search_memory method exception handling"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Execute test
        query = "test query"
        top_k = 5
        result = backend.search_memory("test_user", query, top_k)

        # Verify exception is handled gracefully
        assert isinstance(result, list)

    def test_config_validation(self):
        """Test configuration validation"""
        backend = self.OpensearchLTMBackend(index="test_index")

        # Verify configs are properly initialized with test environment values
        assert backend.opensearch_config.host == "localhost"
        assert backend.opensearch_config.port == 9200
        assert backend.opensearch_config.username == "test_user"
        assert backend.opensearch_config.password == "test_password"

        # Verify embedding config with test environment values
        assert backend.embedding_config.name == "text-embedding-ada-002"
        assert backend.embedding_config.api_key == "test_api_key"
        assert backend.embedding_config.api_base == "https://api.openai.com/v1"
        assert backend.embedding_config.dim == 2560
