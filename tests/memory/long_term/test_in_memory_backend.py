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
import traceback
from unittest.mock import patch, MagicMock

import pytest
from llama_index.core import Document
from llama_index.core.schema import TextNode, BaseNode

from veadk.memory.long_term_memory_backends.in_memory_backend import InMemoryLTMBackend


class TestInMemoryLTMBackend:
    """Test InMemoryLTMBackend class"""

    @pytest.fixture(autouse=True)
    def setup_environment(self):
        """Set up test environment variables"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"
        yield
        # Clean up environment variables
        if "MODEL_EMBEDDING_API_KEY" in os.environ:
            del os.environ["MODEL_EMBEDDING_API_KEY"]

    def test_in_memory_ltm_backend_creation(self):
        """Test InMemoryLTMBackend creation"""
        index = "test_index"
        try:
            backend = InMemoryLTMBackend(index=index)
        except Exception as e:
            print(f"Error creating backend: {e}")
            print(f"Error type: {type(e)}")
            traceback.print_exc()
            raise e

        # Verify basic attributes
        assert backend.index == index
        assert hasattr(backend, "embedding_config")
        assert hasattr(backend, "_embed_model")
        assert hasattr(backend, "_vector_index")

    def test_precheck_index_naming(self):
        """Test precheck_index_naming method"""
        backend = InMemoryLTMBackend(index="test_index")

        # Method should exist and be callable
        assert hasattr(backend, "precheck_index_naming")
        # Calling method should not throw exception
        try:
            backend.precheck_index_naming()
        except Exception as e:
            pytest.fail(f"precheck_index_naming method threw exception: {e}")

    def test_simple_initialization(self):
        """Simple initialization test"""
        # Set environment variables
        os.environ["MODEL_EMBEDDING_API_KEY"] = "test-key"

        # Create backend instance directly
        backend = InMemoryLTMBackend(index="test_index")
        assert backend.index == "test_index"

    @patch(
        "veadk.memory.long_term_memory_backends.in_memory_backend.get_llama_index_splitter"
    )
    def test_save_memory(self, mock_get_splitter):
        """Test save_memory method"""
        # Set environment variables
        os.environ["MODEL_EMBEDDING_API_KEY"] = "test-key"

        # Create backend instance
        backend = InMemoryLTMBackend(index="test_index")

        # Mock splitter
        mock_splitter = MagicMock()
        mock_get_splitter.return_value = mock_splitter
        mock_nodes = [MagicMock(spec=BaseNode)]
        mock_splitter.get_nodes_from_documents.return_value = mock_nodes

        # Mock vector index insert_nodes method
        backend._vector_index.insert_nodes = MagicMock()

        # Execute test
        result = backend.save_memory("user1", ["event1", "event2"])

        # Verify results
        assert result is True
        assert mock_get_splitter.call_count == 2
        assert mock_splitter.get_nodes_from_documents.call_count == 2
        assert backend._vector_index.insert_nodes.call_count == 2

    @patch(
        "veadk.memory.long_term_memory_backends.in_memory_backend.get_llama_index_splitter"
    )
    def test_save_memory_empty_events(self, mock_get_splitter):
        """Test save_memory method handling empty event list"""
        backend = InMemoryLTMBackend(index="test_index")

        # Mock splitter
        mock_splitter = MagicMock()
        mock_splitter.get_nodes_from_documents.return_value = []
        mock_get_splitter.return_value = mock_splitter

        # Test saving empty memory
        user_id = "test_user"
        event_strings = []
        result = backend.save_memory(user_id, event_strings)

        # Verify results
        assert result is True

    def test_search_memory(self):
        """Test search_memory method"""
        # Set environment variables
        os.environ["MODEL_EMBEDDING_API_KEY"] = "test-key"

        # Create backend instance
        backend = InMemoryLTMBackend(index="test_index")

        # Mock retriever and nodes
        mock_retrieved_node = MagicMock(spec=BaseNode)
        mock_retrieved_node.text = "retrieved memory content"
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [mock_retrieved_node]

        # Mock as_retriever method
        backend._vector_index.as_retriever = MagicMock(return_value=mock_retriever)

        # Execute test
        result = backend.search_memory("user1", "query text", top_k=5)

        # Verify results
        assert result == ["retrieved memory content"]
        backend._vector_index.as_retriever.assert_called_once_with(similarity_top_k=5)
        mock_retriever.retrieve.assert_called_once_with("query text")

    def test_search_memory_empty_query(self):
        """Test search_memory method handling empty query"""
        backend = InMemoryLTMBackend(index="test_index")

        # Mock retriever
        mock_retrieved_node = TextNode(text="retrieved memory content")
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [mock_retrieved_node]

        # Mock as_retriever method
        backend._vector_index.as_retriever = MagicMock(return_value=mock_retriever)

        # Test empty query search
        user_id = "test_user"
        query = ""
        top_k = 3
        results = backend.search_memory(user_id, query, top_k)

        # Verify results
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0] == "retrieved memory content"

    def test_split_documents(self):
        """Test _split_documents private method"""
        backend = InMemoryLTMBackend(index="test_index")

        # Mock splitter
        mock_splitter = MagicMock()
        mock_splitter.get_nodes_from_documents.return_value = [
            TextNode(text="doc1 chunk1"),
            TextNode(text="doc1 chunk2"),
        ]

        with patch(
            "veadk.memory.long_term_memory_backends.in_memory_backend.get_llama_index_splitter"
        ) as mock_get_splitter:
            mock_get_splitter.return_value = mock_splitter

            # Create test documents
            documents = [Document(text="test document")]

            # Call private method
            nodes = backend._split_documents(documents)

            # Verify results
            assert isinstance(nodes, list)
            assert len(nodes) == 2
            assert nodes[0].text == "doc1 chunk1"
            assert nodes[1].text == "doc1 chunk2"

            # Verify method was called
            mock_get_splitter.assert_called()
            mock_splitter.get_nodes_from_documents.assert_called()

    def test_split_documents_multiple_documents(self):
        """Test _split_documents method handling multiple documents"""
        backend = InMemoryLTMBackend(index="test_index")

        # Mock splitters for each document
        mock_splitter1 = MagicMock()
        mock_splitter1.get_nodes_from_documents.return_value = [
            TextNode(text="doc1 chunk1")
        ]

        mock_splitter2 = MagicMock()
        mock_splitter2.get_nodes_from_documents.return_value = [
            TextNode(text="doc2 chunk1")
        ]

        # Create multiple test documents
        documents = [Document(text="test document 1"), Document(text="test document 2")]

        with patch(
            "veadk.memory.long_term_memory_backends.in_memory_backend.get_llama_index_splitter"
        ) as mock_get_splitter:
            # Configure mock to return different splitters for different calls
            mock_get_splitter.side_effect = [mock_splitter1, mock_splitter2]

            # Call private method
            nodes = backend._split_documents(documents)

            # Verify results
            assert isinstance(nodes, list)
            assert len(nodes) == 2
            assert nodes[0].text == "doc1 chunk1"
            assert nodes[1].text == "doc2 chunk1"

    def test_string_representation(self):
        """Test InMemoryLTMBackend string representation"""
        index = "test_index"
        backend = InMemoryLTMBackend(index=index)

        str_repr = str(backend)
        # Check if key information is included
        assert index in str_repr
        assert "embedding_config" in str_repr

    def test_model_post_init(self):
        """Test model_post_init method"""
        # Set environment variables
        os.environ["MODEL_EMBEDDING_API_KEY"] = "test-key"

        index = "test_index"
        backend = InMemoryLTMBackend(index=index)

        # Verify embedding model is correctly initialized
        assert hasattr(backend, "_embed_model")
        assert hasattr(backend, "_vector_index")
        # Verify _embed_model is an instance of OpenAILikeEmbedding
        from llama_index.embeddings.openai_like import OpenAILikeEmbedding

        assert isinstance(backend._embed_model, OpenAILikeEmbedding)

    def test_inheritance(self):
        """Test class inheritance"""
        backend = InMemoryLTMBackend(index="test_index")

        # Verify inheritance from BaseLongTermMemoryBackend
        from veadk.memory.long_term_memory_backends.base_backend import (
            BaseLongTermMemoryBackend,
        )

        assert isinstance(backend, BaseLongTermMemoryBackend)

        # Verify all abstract methods are implemented
        assert hasattr(backend, "precheck_index_naming")
        assert hasattr(backend, "save_memory")
        assert hasattr(backend, "search_memory")
