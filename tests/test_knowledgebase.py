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

from veadk.knowledgebase import KnowledgeBase
from veadk.knowledgebase.backends.in_memory_backend import InMemoryKnowledgeBackend


class TestKnowledgeBase:
    """测试KnowledgeBase类"""

    @pytest.mark.asyncio
    async def test_knowledgebase_creation(self):
        """测试KnowledgeBase基本创建"""
        # Mock get_ark_token函数来避免实际的认证调用
        with patch("veadk.auth.veauth.ark_veauth.get_ark_token") as mock_get_ark_token:
            mock_get_ark_token.return_value = "mocked_token"

            os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

            app_name = "kb_test_app"
            kb = KnowledgeBase(backend="local", app_name=app_name)

            assert isinstance(kb._backend, InMemoryKnowledgeBackend)
            assert kb.app_name == app_name

    @pytest.mark.asyncio
    async def test_knowledgebase_with_custom_backend(self):
        """测试KnowledgeBase使用自定义backend实例"""
        # Mock get_ark_token函数来避免实际的认证调用
        with patch("veadk.auth.veauth.ark_veauth.get_ark_token") as mock_get_ark_token:
            mock_get_ark_token.return_value = "mocked_token"

            os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

            # 创建实际的backend实例而不是Mock对象
            from veadk.knowledgebase.backends.in_memory_backend import (
                InMemoryKnowledgeBackend,
            )

            custom_backend = InMemoryKnowledgeBackend(index="test_index")

            app_name = "kb_test_app"
            kb = KnowledgeBase(backend=custom_backend, app_name=app_name)

            assert kb._backend == custom_backend
            assert kb.app_name == app_name
            assert kb.index == "test_index"  # index应该来自backend

    @pytest.mark.asyncio
    async def test_knowledgebase_with_invalid_backend(self):
        """测试KnowledgeBase使用无效backend类型"""
        # Mock get_ark_token函数来避免实际的认证调用
        with patch("veadk.auth.veauth.ark_veauth.get_ark_token") as mock_get_ark_token:
            mock_get_ark_token.return_value = "mocked_token"

            os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

            # 测试无效backend类型
            with pytest.raises(ValueError):
                KnowledgeBase(backend="invalid_backend", app_name="test_app")

    @pytest.mark.asyncio
    async def test_knowledgebase_properties(self):
        """测试KnowledgeBase属性"""
        # Mock get_ark_token函数来避免实际的认证调用
        with patch("veadk.auth.veauth.ark_veauth.get_ark_token") as mock_get_ark_token:
            mock_get_ark_token.return_value = "mocked_token"

            os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

            app_name = "kb_test_app"
            kb = KnowledgeBase(backend="local", app_name=app_name)

            # 测试基本属性
            assert hasattr(kb, "name")
            assert hasattr(kb, "description")
            assert hasattr(kb, "backend")
            assert hasattr(kb, "app_name")

    @pytest.mark.asyncio
    async def test_knowledgebase_without_embedding_api_key(self):
        """测试KnowledgeBase在没有embedding API key时的行为"""
        # 清除环境变量
        original_api_key = os.environ.get("MODEL_EMBEDDING_API_KEY")
        if "MODEL_EMBEDDING_API_KEY" in os.environ:
            del os.environ["MODEL_EMBEDDING_API_KEY"]

        # 清除VOLCENGINE环境变量，确保get_ark_token不会尝试实际认证
        original_volcengine_ak = os.environ.get("VOLCENGINE_ACCESS_KEY")
        original_volcengine_sk = os.environ.get("VOLCENGINE_SECRET_KEY")
        if "VOLCENGINE_ACCESS_KEY" in os.environ:
            del os.environ["VOLCENGINE_ACCESS_KEY"]
        if "VOLCENGINE_SECRET_KEY" in os.environ:
            del os.environ["VOLCENGINE_SECRET_KEY"]

        # Mock get_ark_token函数来避免实际的认证调用
        with patch("veadk.auth.veauth.ark_veauth.get_ark_token") as mock_get_ark_token:
            mock_get_ark_token.return_value = "mocked_token"

            # 清除EmbeddingModelConfig的api_key缓存
            # 由于cached_property缓存存储在实例的__dict__中，我们需要清除可能存在的实例缓存
            # 但这里的问题是EmbeddingModelConfig是一个类，我们需要清除的是其实例的缓存
            # 由于我们无法知道所有存在的实例，这里采用更直接的方法：重新导入模块
            import importlib
            import veadk.configs.model_configs

            importlib.reload(veadk.configs.model_configs)

            # 应该能够创建，但某些操作可能会失败
            app_name = "kb_test_app"
            kb = KnowledgeBase(backend="local", app_name=app_name)

            assert isinstance(kb._backend, InMemoryKnowledgeBackend)
            assert kb.app_name == app_name

        # 恢复环境变量
        if original_api_key is not None:
            os.environ["MODEL_EMBEDDING_API_KEY"] = original_api_key
        if original_volcengine_ak is not None:
            os.environ["VOLCENGINE_ACCESS_KEY"] = original_volcengine_ak
        if original_volcengine_sk is not None:
            os.environ["VOLCENGINE_SECRET_KEY"] = original_volcengine_sk

    @pytest.mark.asyncio
    async def test_knowledgebase_backend_initialization(self):
        """测试KnowledgeBase backend初始化过程"""
        # Mock get_ark_token函数来避免实际的认证调用
        with patch("veadk.auth.veauth.ark_veauth.get_ark_token") as mock_get_ark_token:
            mock_get_ark_token.return_value = "mocked_token"

            os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

            app_name = "kb_test_app"
            kb = KnowledgeBase(backend="local", app_name=app_name)

            # 验证backend已正确初始化
            assert kb._backend is not None
            assert hasattr(kb._backend, "index")
            assert kb._backend.index == app_name  # index应该等于app_name

    @pytest.mark.asyncio
    async def test_knowledgebase_string_representation(self):
        """测试KnowledgeBase的字符串表示"""
        # Mock get_ark_token函数来避免实际的认证调用
        with patch("veadk.auth.veauth.ark_veauth.get_ark_token") as mock_get_ark_token:
            mock_get_ark_token.return_value = "mocked_token"

            os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

            app_name = "kb_test_app"
            kb = KnowledgeBase(backend="local", app_name=app_name)

            # 测试字符串表示 - Pydantic模型的默认表示
            str_repr = str(kb)
            # 检查是否包含关键字段
            assert "name='user_knowledgebase'" in str_repr
            assert "backend='local'" in str_repr
            assert f"app_name='{app_name}'" in str_repr

    @pytest.mark.asyncio
    async def test_knowledgebase_with_different_app_names(self):
        """测试KnowledgeBase使用不同的app_name"""
        os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

        test_cases = [
            "app1",
            "app_with_underscore",
            "app-with-dash",
            "app123",
            "APP_UPPERCASE",
        ]

        for app_name in test_cases:
            kb = KnowledgeBase(backend="local", app_name=app_name)
            assert kb.app_name == app_name
            assert isinstance(kb._backend, InMemoryKnowledgeBackend)
