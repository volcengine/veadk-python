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

from veadk.configs.database_configs import (
    Mem0Config,
    MysqlConfig,
    NormalTOSConfig,
    OpensearchConfig,
    PostgreSqlConfig,
    RedisConfig,
    TOSConfig,
    VikingKnowledgebaseConfig,
)


class TestDatabaseConfigs:
    """测试数据库配置类"""

    def test_opensearch_config_defaults(self):
        """测试OpenSearch配置默认值"""
        config = OpensearchConfig()
        assert config.host == ""
        assert config.port == 9200
        assert config.username == ""
        assert config.password == ""
        assert config.secret_token == ""

    def test_opensearch_config_env_vars(self):
        """测试OpenSearch配置环境变量"""
        with patch.dict(
            os.environ,
            {
                "DATABASE_OPENSEARCH_HOST": "localhost",
                "DATABASE_OPENSEARCH_PORT": "9201",
                "DATABASE_OPENSEARCH_USERNAME": "admin",
                "DATABASE_OPENSEARCH_PASSWORD": "password123",
                "DATABASE_OPENSEARCH_SECRET_TOKEN": "token123",
            },
        ):
            config = OpensearchConfig()
            assert config.host == "localhost"
            assert config.port == 9201
            assert config.username == "admin"
            assert config.password == "password123"
            assert config.secret_token == "token123"

    def test_mysql_config_defaults(self):
        """测试MySQL配置默认值"""
        config = MysqlConfig()
        assert config.host == ""
        assert config.user == ""
        assert config.password == ""
        assert config.database == ""
        assert config.charset == "utf8"
        assert config.secret_token == ""

    def test_postgresql_config_defaults(self):
        """测试PostgreSQL配置默认值"""
        config = PostgreSqlConfig()
        assert config.host == ""
        assert config.port == 5432
        assert config.user == ""
        assert config.password == ""
        assert config.database == ""
        assert config.secret_token == ""

    def test_redis_config_defaults(self):
        """测试Redis配置默认值"""
        config = RedisConfig()
        assert config.host == ""
        assert config.port == 6379
        assert config.password == ""
        assert config.db == 0
        assert config.secret_token == ""

    def test_mem0_config_defaults(self):
        """测试Mem0配置默认值"""
        config = Mem0Config()
        assert config.api_key == ""
        assert config.base_url == ""

    def test_viking_knowledgebase_config_defaults(self):
        """测试Viking知识库配置默认值"""
        config = VikingKnowledgebaseConfig()
        assert config.project == "default"
        assert config.region == "cn-beijing"

    def test_tos_config_defaults(self):
        """测试TOS配置默认值"""
        config = TOSConfig()
        assert config.endpoint == "tos-cn-beijing.volces.com"
        assert config.region == "cn-beijing"

    def test_tos_config_bucket_property(self):
        """测试TOS配置的bucket属性"""
        # 直接mock整个VeTOS类
        with patch("veadk.configs.database_configs.VeTOS") as mock_ve_tos_class:
            # 模拟VeTOS实例
            mock_ve_tos_instance = Mock()
            mock_ve_tos_instance.create_bucket.return_value = None
            mock_ve_tos_class.return_value = mock_ve_tos_instance

            # 设置环境变量
            with patch.dict(os.environ, {"DATABASE_TOS_BUCKET": "test-bucket"}):
                config = TOSConfig()
                bucket = config.bucket
                assert bucket == "test-bucket"
                mock_ve_tos_instance.create_bucket.assert_called_once()

    def test_normal_tos_config_requires_bucket(self):
        """测试NormalTOS配置需要bucket参数"""
        # 应该抛出验证错误，因为bucket是必需的
        with pytest.raises(Exception):
            NormalTOSConfig()

    def test_normal_tos_config_with_bucket(self):
        """测试NormalTOS配置包含bucket"""
        config = NormalTOSConfig(bucket="test-bucket")
        assert config.bucket == "test-bucket"
        assert config.endpoint == "tos-cn-beijing.volces.com"
        assert config.region == "cn-beijing"

    def test_all_configs_env_prefix(self):
        """测试所有配置类的环境变量前缀"""
        # 验证每个配置类的环境变量前缀设置
        assert OpensearchConfig.model_config["env_prefix"] == "DATABASE_OPENSEARCH_"
        assert MysqlConfig.model_config["env_prefix"] == "DATABASE_MYSQL_"
        assert PostgreSqlConfig.model_config["env_prefix"] == "DATABASE_POSTGRESQL_"
        assert RedisConfig.model_config["env_prefix"] == "DATABASE_REDIS_"
        assert Mem0Config.model_config["env_prefix"] == "DATABASE_MEM0_"
        assert (
            VikingKnowledgebaseConfig.model_config["env_prefix"] == "DATABASE_VIKING_"
        )
        assert TOSConfig.model_config["env_prefix"] == "DATABASE_TOS_"
        assert NormalTOSConfig.model_config["env_prefix"] == "DATABASE_TOS_"
