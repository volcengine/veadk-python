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
from unittest.mock import Mock, patch

import pytest
from google.adk.tools import load_memory

from veadk.agent import Agent
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.long_term_memory_backends.in_memory_backend import (
    InMemoryLTMBackend as InMemoryLongTermMemoryBackend,
)
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)


class TestLongTermMemory:
    """Test LongTermMemory class"""

    @pytest.mark.asyncio
    async def test_long_term_memory_creation(self):
        """Test basic LongTermMemory creation"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"
        long_term_memory = LongTermMemory(backend="local")

        agent = Agent(
            name="all_name",
            model_name="test_model_name",
            model_provider="test_model_provider",
            model_api_key="test_model_api_key",
            model_api_base="test_model_api_base",
            description="a veadk test agent",
            instruction="a veadk test agent",
            long_term_memory=long_term_memory,
        )

        assert load_memory in agent.tools, "load_memory tool not found in agent tools"

        assert agent.long_term_memory
        assert agent.long_term_memory._backend

    @pytest.mark.asyncio
    async def test_long_term_memory_with_custom_backend(self):
        """Test LongTermMemory with custom backend instance"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        # Create mock backend instance
        mock_backend = Mock(spec=BaseLongTermMemoryBackend)
        mock_backend.index = "test_index"

        long_term_memory = LongTermMemory(backend=mock_backend)

        assert long_term_memory._backend == mock_backend

    @pytest.mark.asyncio
    async def test_long_term_memory_with_invalid_backend(self):
        """Test LongTermMemory with invalid backend type"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        # Test invalid backend type
        with pytest.raises(ValueError):
            LongTermMemory(backend="invalid_backend")

    @pytest.mark.asyncio
    async def test_long_term_memory_properties(self):
        """Test LongTermMemory properties"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        long_term_memory = LongTermMemory(backend="local")

        # Test basic properties
        assert hasattr(long_term_memory, "backend")

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"MODEL_EMBEDDING_API_KEY": ""}, clear=True)
    @patch("veadk.auth.veauth.ark_veauth.get_ark_token")
    @patch("veadk.auth.veauth.utils.get_credential_from_vefaas_iam")
    async def test_long_term_memory_without_embedding_api_key(
        self, mock_get_credential, mock_get_ark_token
    ):
        """Test LongTermMemory initialization without embedding API key"""
        # Mock get_ark_token function to throw ValueError exception, simulating inability to get ARK token
        mock_get_ark_token.side_effect = ValueError("Failed to get ARK api key")
        # Mock get_credential_from_vefaas_iam function to throw FileNotFoundError exception, simulating inability to get credentials from IAM file
        mock_get_credential.side_effect = FileNotFoundError(
            "Mocked VeFaaS IAM file not found"
        )

        # Clear any cached embedding config to ensure fresh initialization
        import importlib
        import veadk.configs.model_configs

        importlib.reload(veadk.configs.model_configs)

        # In this case, we expect an exception to be raised during initialization
        # because the embedding model requires an API key
        with pytest.raises((ValueError, FileNotFoundError)):
            LongTermMemory(backend="local")

    @pytest.mark.asyncio
    async def test_long_term_memory_backend_initialization(self):
        """Test LongTermMemory backend initialization process"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        long_term_memory = LongTermMemory(backend="local")

        # Verify backend is correctly initialized
        assert long_term_memory._backend is not None
        assert isinstance(long_term_memory._backend, InMemoryLongTermMemoryBackend)

    @pytest.mark.asyncio
    async def test_long_term_memory_string_representation(self):
        """Test LongTermMemory string representation"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        long_term_memory = LongTermMemory(backend="local")

        # Test string representation
        str_repr = str(long_term_memory)
        # Check if contains key information
        assert "backend" in str_repr
        assert "local" in str_repr

    @pytest.mark.asyncio
    async def test_long_term_memory_with_app_name(self):
        """Test LongTermMemory with app_name parameter"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        app_name = "test_app"
        long_term_memory = LongTermMemory(backend="local", app_name=app_name)

        assert long_term_memory._backend is not None
        assert hasattr(long_term_memory._backend, "index")
        assert long_term_memory._backend.index == app_name

    @pytest.mark.asyncio
    async def test_long_term_memory_tool_integration(self):
        """Test LongTermMemory integration with Agent tools"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        long_term_memory = LongTermMemory(backend="local")

        # Create multiple Agent instances to test tool integration
        agents = []
        for i in range(3):
            agent = Agent(
                name=f"agent_{i}",
                model_name="test_model_name",
                model_provider="test_model_provider",
                model_api_key="test_model_api_key",
                model_api_base="test_model_api_base",
                description=f"test agent {i}",
                instruction=f"test agent {i}",
                long_term_memory=long_term_memory,
            )
            agents.append(agent)

        # Verify each Agent has correct tool integration
        for agent in agents:
            assert load_memory in agent.tools
            assert agent.long_term_memory == long_term_memory

    @pytest.mark.asyncio
    async def test_long_term_memory_backend_types(self):
        """Test different backend types supported by LongTermMemory"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        # Test supported backend types
        supported_backends = ["local"]  # Currently only supports local

        for backend_type in supported_backends:
            long_term_memory = LongTermMemory(backend=backend_type)
            assert long_term_memory._backend is not None
            assert long_term_memory.backend == backend_type
