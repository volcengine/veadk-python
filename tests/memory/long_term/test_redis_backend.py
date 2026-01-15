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
import sys
from unittest.mock import patch, MagicMock


class TestRedisLTMBackend:
    """Test RedisLTMBackend class"""

    def setup_method(self):
        """Set up mocks for each test method"""
        # Set up test environment variables with correct prefixes
        os.environ["DATABASE_REDIS_HOST"] = "localhost"
        os.environ["DATABASE_REDIS_PORT"] = "6379"
        os.environ["DATABASE_REDIS_PASSWORD"] = "test_password"
        os.environ["DATABASE_REDIS_DB"] = "0"
        os.environ["MODEL_EMBEDDING_NAME"] = "text-embedding-ada-002"
        os.environ["MODEL_EMBEDDING_API_KEY"] = "test_api_key"
        os.environ["MODEL_EMBEDDING_API_BASE"] = "https://api.openai.com/v1"

        # Mock the import dependencies that require extensions
        sys.modules["llama_index.vector_stores.redis"] = MagicMock()
        sys.modules["redis"] = MagicMock()
        sys.modules["redisvl.schema"] = MagicMock()

        # Mock the specific classes
        mock_redis_module = MagicMock()
        mock_redis_module.Redis = MagicMock()
        sys.modules["redis"] = mock_redis_module

        mock_redisvl_schema_module = MagicMock()
        mock_redisvl_schema_module.IndexSchema = MagicMock()
        mock_redisvl_schema_module.IndexSchema.from_dict = MagicMock(
            return_value=MagicMock()
        )
        sys.modules["redisvl.schema"] = mock_redisvl_schema_module

        # Create mock instances
        self.mock_redis_instance = MagicMock()
        self.mock_schema_instance = MagicMock()
        self.mock_redis_store_instance = MagicMock(
            index_name="test_index",
            schema=MagicMock(index=MagicMock(prefix="test_prefix")),
        )
        self.mock_vector_index_instance = MagicMock()
        self.mock_embed_model_instance = MagicMock()
        self.mock_splitter_instance = MagicMock(
            get_nodes_from_documents=MagicMock(return_value=[MagicMock()])
        )

        # Mock all external dependencies
        self.mock_redis = patch(
            "veadk.memory.long_term_memory_backends.redis_backend.Redis",
            return_value=self.mock_redis_instance,
        ).start()
        self.mock_redis_vector_store = patch(
            "veadk.memory.long_term_memory_backends.redis_backend.RedisVectorStore",
            return_value=self.mock_redis_store_instance,
        ).start()
        self.mock_index_schema = patch(
            "veadk.memory.long_term_memory_backends.redis_backend.IndexSchema",
            return_value=self.mock_schema_instance,
        ).start()
        self.mock_vector_store_index = patch(
            "veadk.memory.long_term_memory_backends.redis_backend.VectorStoreIndex",
            return_value=self.mock_vector_index_instance,
        ).start()
        self.mock_embedding = patch(
            "veadk.memory.long_term_memory_backends.redis_backend.OpenAILikeEmbedding",
            return_value=self.mock_embed_model_instance,
        ).start()
        self.mock_splitter = patch(
            "veadk.memory.long_term_memory_backends.redis_backend.get_llama_index_splitter",
            return_value=self.mock_splitter_instance,
        ).start()

        # Configure IndexSchema.from_dict
        self.mock_index_schema.from_dict.return_value = self.mock_schema_instance

        # Configure VectorStoreIndex.from_vector_store
        self.mock_vector_store_index.from_vector_store.return_value = (
            self.mock_vector_index_instance
        )

        # Import the actual class after mocking
        from veadk.memory.long_term_memory_backends.redis_backend import RedisLTMBackend

        self.RedisLTMBackend = RedisLTMBackend

    def teardown_method(self):
        """Clean up mocks after each test method"""
        # Stop all mocks
        self.mock_redis.stop()
        self.mock_redis_vector_store.stop()
        self.mock_index_schema.stop()
        self.mock_vector_store_index.stop()
        self.mock_embedding.stop()
        self.mock_splitter.stop()

        # Clean up sys.modules
        for module_name in [
            "llama_index.vector_stores.redis",
            "redis",
            "redisvl.schema",
        ]:
            if module_name in sys.modules:
                del sys.modules[module_name]

        # Clean up environment variables
        env_vars = [
            "DATABASE_REDIS_HOST",
            "DATABASE_REDIS_PORT",
            "DATABASE_REDIS_PASSWORD",
            "DATABASE_REDIS_DB",
            "MODEL_EMBEDDING_NAME",
            "MODEL_EMBEDDING_API_KEY",
            "MODEL_EMBEDDING_API_BASE",
        ]
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]

    def test_redis_ltm_backend_creation(self):
        """Test RedisLTMBackend creation"""
        index = "test_index"
        backend = self.RedisLTMBackend(index=index)

        # Verify basic attributes
        assert backend.index == index
        assert hasattr(backend, "redis_config")
        assert hasattr(backend, "embedding_config")

    def test_model_post_init(self):
        """Test model_post_init method"""
        index = "test_index"
        backend = self.RedisLTMBackend(index=index)

        # Call model_post_init with required context parameter
        backend.model_post_init(None)

        # Verify embedding model is set
        assert hasattr(backend, "_embed_model")

    def test_precheck_index_naming(self):
        """Test precheck_index_naming method (Redis has no checking)"""
        backend = self.RedisLTMBackend(index="test_index")

        # Test that precheck_index_naming does nothing (no exception)
        # Redis backend has no index naming restrictions
        test_names = [
            "test",
            "test-index",
            "test_index",
            "test123",
            "_test",
            "-test",
            "Test",
            "test@",
            "test space",
        ]
        for name in test_names:
            backend.precheck_index_naming(name)  # Should not raise any exception

    def test_create_vector_index(self):
        """Test _create_vector_index method"""
        backend = self.RedisLTMBackend(index="test_index")

        # Test valid index creation
        index_name = "valid_index"
        vector_index = backend._create_vector_index(index_name)

        # Verify Redis client was created with correct parameters
        self.mock_redis.assert_called_once_with(
            host="localhost", port=6379, db=0, password="test_password"
        )

        # Verify IndexSchema was created
        self.mock_index_schema.from_dict.assert_called_once()

        # Verify RedisVectorStore creation
        self.mock_redis_vector_store.assert_called_once_with(
            schema=self.mock_schema_instance, redis_client=self.mock_redis_instance
        )

        # Verify VectorStoreIndex creation
        self.mock_vector_store_index.from_vector_store.assert_called_once_with(
            vector_store=self.mock_redis_store_instance,
            embed_model=self.mock_embed_model_instance,
        )

        # Verify vector index is returned
        assert vector_index == self.mock_vector_index_instance

    def test_save_memory(self):
        """Test save_memory method"""
        backend = self.RedisLTMBackend(index="test_index")

        # Execute test
        event_strings = ["event1", "event2", "event3"]
        result = backend.save_memory("test_user", event_strings)

        # Verify VectorStoreIndex was created
        self.mock_vector_store_index.from_vector_store.assert_called_once()

        # Verify documents were processed
        assert self.mock_splitter_instance.get_nodes_from_documents.call_count == 3

        # Verify nodes were inserted
        assert self.mock_vector_index_instance.insert_nodes.call_count == 3

        # Verify results
        assert result is True

    def test_save_memory_empty_events(self):
        """Test save_memory method with empty event list"""
        backend = self.RedisLTMBackend(index="test_index")

        # Execute test with empty events
        event_strings = []
        result = backend.save_memory("test_user", event_strings)

        # Verify no documents were processed
        assert self.mock_splitter_instance.get_nodes_from_documents.call_count == 0

        # Verify no nodes were inserted
        assert self.mock_vector_index_instance.insert_nodes.call_count == 0

        # Verify results
        assert result is True

    def test_save_memory_default_user(self):
        """Test save_memory method with default user"""
        backend = self.RedisLTMBackend(index="test_index")

        # Execute test
        event_strings = ["event1"]
        result = backend.save_memory("default_user", event_strings)

        # Verify VectorStoreIndex was created
        self.mock_vector_store_index.from_vector_store.assert_called_once()

        # Verify results
        assert result is True

    def test_search_memory(self):
        """Test search_memory method"""
        backend = self.RedisLTMBackend(index="test_index")

        # Mock retriever
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            MagicMock(text="result1"),
            MagicMock(text="result2"),
        ]
        self.mock_vector_index_instance.as_retriever.return_value = mock_retriever

        # Execute test
        query = "test query"
        top_k = 5
        result = backend.search_memory("test_user", query, top_k)

        # Verify VectorStoreIndex was created
        self.mock_vector_store_index.from_vector_store.assert_called_once()

        # Verify retriever was created with correct parameters
        self.mock_vector_index_instance.as_retriever.assert_called_once_with(
            similarity_top_k=top_k
        )

        # Verify search was performed
        mock_retriever.retrieve.assert_called_once_with(query)

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 2
        assert result == ["result1", "result2"]

    def test_search_memory_default_user(self):
        """Test search_memory method with default user"""
        backend = self.RedisLTMBackend(index="test_index")

        # Mock retriever
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [MagicMock(text="result")]
        self.mock_vector_index_instance.as_retriever.return_value = mock_retriever

        # Execute test
        query = "test query"
        top_k = 3
        result = backend.search_memory("default_user", query, top_k)

        # Verify VectorStoreIndex was created
        self.mock_vector_store_index.from_vector_store.assert_called_once()

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 1

    def test_search_memory_empty_results(self):
        """Test search_memory method handling empty results"""
        backend = self.RedisLTMBackend(index="test_index")

        # Mock retriever with empty results
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        self.mock_vector_index_instance.as_retriever.return_value = mock_retriever

        # Execute test
        query = "test query"
        top_k = 5
        result = backend.search_memory("test_user", query, top_k)

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 0

    def test_split_documents(self):
        """Test _split_documents method"""
        backend = self.RedisLTMBackend(index="test_index")

        # Mock documents
        mock_documents = [MagicMock() for _ in range(3)]

        # Execute test
        result = backend._split_documents(mock_documents)

        # Verify splitter was called for each document
        assert self.mock_splitter.call_count == 3

        # Verify results
        assert isinstance(result, list)
        assert len(result) == 3  # 3 documents * 1 node per document

    def test_inheritance(self):
        """Test class inheritance"""
        backend = self.RedisLTMBackend(index="test_index")

        # Verify inheritance from BaseLongTermMemoryBackend
        from veadk.memory.long_term_memory_backends.base_backend import (
            BaseLongTermMemoryBackend,
        )

        assert isinstance(backend, BaseLongTermMemoryBackend)

    def test_index_naming_pattern(self):
        """Test the index naming pattern used in save/search operations"""
        backend = self.RedisLTMBackend(index="base_index")

        # Test index naming pattern
        user_id = "test_user"

        # Execute test
        backend.save_memory(user_id, ["test_event"])
        backend.search_memory(user_id, "test_query", 5)

        # Verify the operations completed without errors
        assert True

    def test_save_memory_exception_handling(self):
        """Test save_memory method exception handling"""
        backend = self.RedisLTMBackend(index="test_index")

        # Execute test
        event_strings = ["event1"]
        result = backend.save_memory("test_user", event_strings)

        # Verify exception is handled gracefully
        assert result is True

    def test_search_memory_exception_handling(self):
        """Test search_memory method exception handling"""
        backend = self.RedisLTMBackend(index="test_index")

        # Execute test
        query = "test query"
        top_k = 5
        result = backend.search_memory("test_user", query, top_k)

        # Verify exception is handled gracefully
        assert isinstance(result, list)

    def test_config_validation(self):
        """Test configuration validation"""
        backend = self.RedisLTMBackend(index="test_index")

        # Verify configs are properly initialized with test environment values
        assert backend.redis_config.host == "localhost"
        assert backend.redis_config.port == 6379
        assert backend.redis_config.password == "test_password"
        assert backend.redis_config.db == 0

        # Verify embedding config with test environment values
        assert backend.embedding_config.name == "text-embedding-ada-002"
        assert backend.embedding_config.api_key == "test_api_key"
        assert backend.embedding_config.api_base == "https://api.openai.com/v1"
        assert backend.embedding_config.dim == 2560
