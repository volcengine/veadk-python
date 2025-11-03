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
    """测试LongTermMemory类"""

    @pytest.mark.asyncio
    async def test_long_term_memory_creation(self):
        """测试LongTermMemory基本创建"""
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
        """测试LongTermMemory使用自定义backend实例"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        # 创建模拟backend实例
        mock_backend = Mock(spec=BaseLongTermMemoryBackend)
        mock_backend.index = "test_index"

        long_term_memory = LongTermMemory(backend=mock_backend)

        assert long_term_memory._backend == mock_backend

    @pytest.mark.asyncio
    async def test_long_term_memory_with_invalid_backend(self):
        """测试LongTermMemory使用无效backend类型"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        # 测试无效backend类型
        with pytest.raises(ValueError):
            LongTermMemory(backend="invalid_backend")

    @pytest.mark.asyncio
    async def test_long_term_memory_properties(self):
        """测试LongTermMemory属性"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        long_term_memory = LongTermMemory(backend="local")

        # 测试基本属性
        assert hasattr(long_term_memory, "backend")

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"MODEL_EMBEDDING_API_KEY": ""}, clear=True)
    @patch("veadk.auth.veauth.ark_veauth.get_ark_token")
    @patch("veadk.auth.veauth.utils.get_credential_from_vefaas_iam")
    async def test_long_term_memory_without_embedding_api_key(
        self, mock_get_credential, mock_get_ark_token
    ):
        """测试在没有embedding api key时初始化LongTermMemory"""
        # Mock get_ark_token函数来抛出ValueError异常，模拟无法获取ARK token的情况
        mock_get_ark_token.side_effect = ValueError("Failed to get ARK api key")
        # Mock get_credential_from_vefaas_iam函数来抛出FileNotFoundError异常，模拟无法从IAM文件获取凭证的情况
        mock_get_credential.side_effect = FileNotFoundError(
            "Mocked VeFaaS IAM file not found"
        )

        # In this case, no exception should be raised during initialization,
        # as the key is only required when the embedding model is actually used.
        try:
            LongTermMemory()
        except (ValueError, FileNotFoundError) as e:
            pytest.fail(f"Initialization failed unexpectedly: {e}")

    @pytest.mark.asyncio
    async def test_long_term_memory_backend_initialization(self):
        """测试LongTermMemory backend初始化过程"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        long_term_memory = LongTermMemory(backend="local")

        # 验证backend已正确初始化
        assert long_term_memory._backend is not None
        assert isinstance(long_term_memory._backend, InMemoryLongTermMemoryBackend)

    @pytest.mark.asyncio
    async def test_long_term_memory_string_representation(self):
        """测试LongTermMemory的字符串表示"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        long_term_memory = LongTermMemory(backend="local")

        # 测试字符串表示
        str_repr = str(long_term_memory)
        # 检查是否包含关键信息
        assert "backend" in str_repr
        assert "local" in str_repr

    @pytest.mark.asyncio
    async def test_long_term_memory_with_app_name(self):
        """测试LongTermMemory使用app_name参数"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        app_name = "test_app"
        long_term_memory = LongTermMemory(backend="local", app_name=app_name)

        assert long_term_memory._backend is not None
        assert hasattr(long_term_memory._backend, "index")
        assert long_term_memory._backend.index == app_name

    @pytest.mark.asyncio
    async def test_long_term_memory_tool_integration(self):
        """测试LongTermMemory与Agent工具的集成"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        long_term_memory = LongTermMemory(backend="local")

        # 创建多个Agent实例测试工具集成
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

        # 验证每个Agent都有正确的工具集成
        for agent in agents:
            assert load_memory in agent.tools
            assert agent.long_term_memory == long_term_memory

    @pytest.mark.asyncio
    async def test_long_term_memory_backend_types(self):
        """测试LongTermMemory支持的不同backend类型"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        # 测试支持的backend类型
        supported_backends = ["local"]  # 目前只支持local

        for backend_type in supported_backends:
            long_term_memory = LongTermMemory(backend=backend_type)
            assert long_term_memory._backend is not None
            assert long_term_memory.backend == backend_type
