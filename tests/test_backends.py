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
from unittest.mock import patch

import pytest

from veadk.knowledgebase.backends.in_memory_backend import InMemoryKnowledgeBackend
from veadk.memory.long_term_memory_backends.in_memory_backend import (
    InMemoryLTMBackend as InMemoryLongTermMemoryBackend,
)


class TestKnowledgeBaseBackends:
    """测试KnowledgeBase Backend类"""

    @pytest.mark.asyncio
    async def test_in_memory_knowledge_backend_creation(self):
        """测试InMemoryKnowledgeBackend创建"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        app_name = "test_app"
        backend = InMemoryKnowledgeBackend(app_name=app_name, index=app_name)

        assert backend.index == app_name
        assert hasattr(backend, "index")

    @pytest.mark.asyncio
    async def test_in_memory_knowledge_backend_methods(self):
        """测试InMemoryKnowledgeBackend方法"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        app_name = "test_app"
        backend = InMemoryKnowledgeBackend(app_name=app_name, index=app_name)

        # 测试基本方法存在
        assert hasattr(backend, "add_from_text")
        assert hasattr(backend, "search")

    @pytest.mark.asyncio
    async def test_in_memory_knowledge_backend_string_representation(self):
        """测试InMemoryKnowledgeBackend字符串表示"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        app_name = "test_app"
        backend = InMemoryKnowledgeBackend(app_name=app_name, index=app_name)

        str_repr = str(backend)
        assert "index='test_app'" in str_repr
        assert app_name in str_repr


class TestLongTermMemoryBackends:
    """测试LongTermMemory Backend类"""

    @pytest.mark.asyncio
    async def test_in_memory_long_term_memory_backend_creation(self):
        """测试InMemoryLongTermMemoryBackend创建"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        index = "test_index"
        backend = InMemoryLongTermMemoryBackend(index=index)

        assert backend.index == index

    @pytest.mark.asyncio
    async def test_in_memory_long_term_memory_backend_methods(self):
        """测试InMemoryLongTermMemoryBackend方法"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        index = "test_index"
        backend = InMemoryLongTermMemoryBackend(index=index)

        # 测试基本方法存在
        assert hasattr(backend, "save_memory")
        assert hasattr(backend, "search_memory")
        assert hasattr(backend, "precheck_index_naming")

    @pytest.mark.asyncio
    async def test_in_memory_long_term_memory_backend_string_representation(self):
        """测试InMemoryLongTermMemoryBackend字符串表示"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        index = "test_index"
        backend = InMemoryLongTermMemoryBackend(index=index)

        str_repr = str(backend)
        # 检查是否包含关键信息
        assert index in str_repr
        assert "embedding_config" in str_repr


class TestBackendIntegration:
    """测试Backend集成功能"""

    @pytest.mark.asyncio
    async def test_backend_compatibility(self):
        """测试backend兼容性"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        # 测试KnowledgeBase backend
        kb_backend = InMemoryKnowledgeBackend(app_name="test_app", index="test_app")
        assert kb_backend.index == "test_app"

        # 测试LongTermMemory backend
        ltm_backend = InMemoryLongTermMemoryBackend(
            app_name="test_app", index="test_app"
        )
        assert ltm_backend.index == "test_app"

    @pytest.mark.asyncio
    async def test_backend_without_app_name(self):
        """测试backend在没有app_name时的行为"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        # 测试KnowledgeBase backend
        kb_backend = InMemoryKnowledgeBackend(index="default_app")
        assert hasattr(kb_backend, "index")

        # 测试LongTermMemory backend
        ltm_backend = InMemoryLongTermMemoryBackend(index="default_app")
        assert hasattr(ltm_backend, "index")

    @pytest.mark.asyncio
    async def test_backend_environment_variables(self):
        """测试backend环境变量处理"""
        # 测试环境变量设置
        with patch.dict(os.environ, {"MODEL_EMBEDDING_API_KEY": "test_key"}):
            kb_backend = InMemoryKnowledgeBackend(app_name="test_app", index="test_app")
            ltm_backend = InMemoryLongTermMemoryBackend(
                app_name="test_app", index="test_app"
            )

            # 验证backend可以正常创建
            assert kb_backend is not None
            assert ltm_backend is not None

    @pytest.mark.asyncio
    async def test_backend_error_handling(self):
        """测试backend错误处理"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        # 测试无效参数
        kb_backend = InMemoryKnowledgeBackend(app_name="test_app", index="test_app")
        ltm_backend = InMemoryLongTermMemoryBackend(
            app_name="test_app", index="test_app"
        )

        # 验证backend可以处理基本操作
        # 这里主要测试backend不会因为基本操作而崩溃
        assert hasattr(kb_backend, "index")
        assert hasattr(ltm_backend, "index")
