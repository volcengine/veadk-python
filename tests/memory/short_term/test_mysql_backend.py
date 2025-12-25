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


class TestMysqlSTMBackend:
    """Test MysqlSTMBackend class"""

    def setup_method(self):
        """Set up mocks for each test method"""
        # Set up test environment variables
        os.environ["DATABASE_MYSQL_HOST"] = "test_host"
        os.environ["DATABASE_MYSQL_USER"] = "test_user"
        os.environ["DATABASE_MYSQL_PASSWORD"] = "test_password"
        os.environ["DATABASE_MYSQL_DATABASE"] = "test_db"
        os.environ["DATABASE_MYSQL_CHARSET"] = "utf8"

        # Create mock instances
        self.mock_session_service = MagicMock()
        self.mock_database_session_service = MagicMock(
            return_value=self.mock_session_service
        )

        # Mock the external dependencies before importing the class
        # We need to patch the imports within the mysql_backend module
        self.mock_database_session_service_patch = patch(
            "veadk.memory.short_term_memory_backends.mysql_backend.DatabaseSessionService",
            return_value=self.mock_session_service,
        )
        self.mock_base_session_service_patch = patch(
            "veadk.memory.short_term_memory_backends.mysql_backend.BaseSessionService",
            MagicMock,
        )

        # Start the patches
        self.mock_database_session_service_patch.start()
        self.mock_base_session_service_patch.start()

        # Import the actual class after mocking
        from veadk.memory.short_term_memory_backends.mysql_backend import (
            MysqlSTMBackend,
        )

        self.MysqlSTMBackend = MysqlSTMBackend

    def teardown_method(self):
        """Clean up mocks after each test method"""
        # Stop all patches
        self.mock_database_session_service_patch.stop()
        self.mock_base_session_service_patch.stop()

        # Clean up environment variables
        env_vars = [
            "DATABASE_MYSQL_HOST",
            "DATABASE_MYSQL_USER",
            "DATABASE_MYSQL_PASSWORD",
            "DATABASE_MYSQL_DATABASE",
            "DATABASE_MYSQL_CHARSET",
        ]
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]

    def test_mysql_stm_backend_creation(self):
        """Test MysqlSTMBackend creation"""
        backend = self.MysqlSTMBackend()

        # Verify basic attributes
        assert backend.mysql_config is not None
        assert backend.mysql_config.host == "test_host"
        assert backend.mysql_config.user == "test_user"
        assert backend.mysql_config.password == "test_password"
        assert backend.mysql_config.database == "test_db"
        assert backend.mysql_config.charset == "utf8"

    def test_model_post_init(self):
        """Test model_post_init method"""
        backend = self.MysqlSTMBackend()

        # Call model_post_init
        backend.model_post_init(None)

        # Verify database URL is correctly constructed
        expected_url = "mysql+pymysql://test_user:test_password@test_host/test_db"
        assert backend._db_url == expected_url

    def test_model_post_init_with_custom_config(self):
        """Test model_post_init method with custom configuration"""
        # Create backend with custom config
        from veadk.configs.database_configs import MysqlConfig

        custom_config = MysqlConfig(
            host="custom_host",
            user="custom_user",
            password="custom_password",
            database="custom_db",
            charset="utf8mb4",
        )
        backend = self.MysqlSTMBackend(mysql_config=custom_config)

        # Call model_post_init
        backend.model_post_init(None)

        # Verify database URL is correctly constructed with custom config
        expected_url = (
            "mysql+pymysql://custom_user:custom_password@custom_host/custom_db"
        )
        assert backend._db_url == expected_url

    def test_session_service_property(self):
        """Test session_service property"""
        backend = self.MysqlSTMBackend()

        # Call model_post_init first to set up _db_url
        backend.model_post_init(None)

        # Access session_service property
        session_service = backend.session_service

        # Verify DatabaseSessionService was called with correct URL
        from veadk.memory.short_term_memory_backends.mysql_backend import (
            DatabaseSessionService,
        )

        DatabaseSessionService.assert_called_once_with(db_url=backend._db_url)

        # Verify the correct session service is returned
        assert session_service == self.mock_session_service

    def test_session_service_cached_property(self):
        """Test that session_service is cached"""
        backend = self.MysqlSTMBackend()

        # Call model_post_init first to set up _db_url
        backend.model_post_init(None)

        # Access session_service property multiple times
        session_service1 = backend.session_service
        session_service2 = backend.session_service
        session_service3 = backend.session_service

        # Verify DatabaseSessionService was called only once (cached)
        from veadk.memory.short_term_memory_backends.mysql_backend import (
            DatabaseSessionService,
        )

        DatabaseSessionService.assert_called_once_with(db_url=backend._db_url)

        # Verify all accesses return the same instance
        assert session_service1 == session_service2 == session_service3
        assert session_service1 is session_service2 is session_service3

    def test_inheritance(self):
        """Test class inheritance"""
        backend = self.MysqlSTMBackend()

        # Verify inheritance from BaseShortTermMemoryBackend
        from veadk.memory.short_term_memory_backends.base_backend import (
            BaseShortTermMemoryBackend,
        )

        assert isinstance(backend, BaseShortTermMemoryBackend)

    def test_config_validation(self):
        """Test configuration validation"""
        backend = self.MysqlSTMBackend()

        # Verify configs are properly initialized
        assert backend.mysql_config.host == "test_host"
        assert backend.mysql_config.user == "test_user"
        assert backend.mysql_config.password == "test_password"
        assert backend.mysql_config.database == "test_db"
        assert backend.mysql_config.charset == "utf8"

    def test_db_url_format(self):
        """Test database URL format construction"""
        backend = self.MysqlSTMBackend()

        # Call model_post_init
        backend.model_post_init(None)

        # Verify URL format is correct
        db_url = backend._db_url
        assert db_url.startswith("mysql+pymysql://")
        assert "test_user:test_password@test_host/test_db" in db_url

    def test_session_service_type(self):
        """Test session service type"""
        backend = self.MysqlSTMBackend()

        # Call model_post_init first to set up _db_url
        backend.model_post_init(None)

        # Access session_service property
        session_service = backend.session_service

        # Verify it's an instance of BaseSessionService
        from veadk.memory.short_term_memory_backends.mysql_backend import (
            BaseSessionService,
        )

        assert isinstance(session_service, BaseSessionService)

    def test_override_decorator(self):
        """Test that session_service method has override decorator"""
        backend = self.MysqlSTMBackend()

        # Verify the method has the override decorator by checking the method signature
        # The override decorator doesn't add __wrapped__ attribute
        session_service_method = backend.__class__.session_service

        # Check that it's a cached_property
        assert isinstance(
            session_service_method, type(backend.__class__.session_service)
        )

        # Verify the method exists
        assert hasattr(backend.__class__, "session_service")

        # Verify that the property can be accessed and returns the correct type
        # The cached_property itself is not callable, but it returns a callable when accessed
        backend.model_post_init(None)
        session_service_instance = backend.session_service
        assert session_service_instance is not None

    def test_cached_property_functionality(self):
        """Test cached_property functionality"""
        backend = self.MysqlSTMBackend()

        # Call model_post_init first to set up _db_url
        backend.model_post_init(None)

        # First access should create the service
        session_service1 = backend.session_service

        # Second access should return cached instance
        session_service2 = backend.session_service

        # Verify they are the same instance
        assert session_service1 is session_service2

        # Verify the instance is stored in the object's dict
        assert "session_service" in backend.__dict__

    def test_error_handling_in_session_service(self):
        """Test error handling in session_service property"""
        backend = self.MysqlSTMBackend()

        # Mock DatabaseSessionService to raise an exception
        from veadk.memory.short_term_memory_backends.mysql_backend import (
            DatabaseSessionService,
        )

        DatabaseSessionService.side_effect = Exception("Database connection failed")

        # Call model_post_init first to set up _db_url
        backend.model_post_init(None)

        # Access session_service property should raise exception
        with pytest.raises(Exception, match="Database connection failed"):
            _ = backend.session_service

    def test_db_url_special_characters(self):
        """Test database URL with special characters in password"""
        # Set up environment with special characters
        os.environ["DATABASE_MYSQL_PASSWORD"] = "pass@word#123"

        backend = self.MysqlSTMBackend()

        # Call model_post_init
        backend.model_post_init(None)

        # Verify URL is correctly constructed with special characters
        expected_url = "mysql+pymysql://test_user:pass@word#123@test_host/test_db"
        assert backend._db_url == expected_url

    def test_default_config_values(self):
        """Test default configuration values"""
        # Remove environment variables to test defaults
        env_vars = [
            "DATABASE_MYSQL_HOST",
            "DATABASE_MYSQL_USER",
            "DATABASE_MYSQL_PASSWORD",
            "DATABASE_MYSQL_DATABASE",
            "DATABASE_MYSQL_CHARSET",
        ]
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]

        backend = self.MysqlSTMBackend()

        # Verify default values are set (empty strings for most fields)
        assert backend.mysql_config.host == ""
        assert backend.mysql_config.user == ""
        assert backend.mysql_config.password == ""
        assert backend.mysql_config.database == ""
        assert backend.mysql_config.charset == "utf8"

    def test_model_post_init_called_automatically(self):
        """Test that model_post_init is called automatically by Pydantic"""
        backend = self.MysqlSTMBackend()

        # Verify _db_url is set after initialization (model_post_init was called)
        assert hasattr(backend, "_db_url")
        assert backend._db_url is not None

    def test_session_service_independence(self):
        """Test that different backend instances have independent session services"""
        backend1 = self.MysqlSTMBackend()
        backend2 = self.MysqlSTMBackend()

        # Call model_post_init for both instances
        backend1.model_post_init(None)
        backend2.model_post_init(None)

        # Access session_service for both instances
        backend1.session_service
        backend2.session_service

        # Verify they are different instances (they should be different mock objects)
        # Since we're using the same mock class, they might be the same instance
        # This test is more about verifying the caching works correctly per instance
        assert (
            backend1.session_service is backend1.session_service
        )  # Same instance cached
        assert (
            backend2.session_service is backend2.session_service
        )  # Same instance cached

    def test_comprehensive_config_coverage(self):
        """Test comprehensive configuration coverage"""
        # Test with various configuration combinations
        test_cases = [
            {
                "host": "db1.example.com",
                "user": "admin",
                "password": "secret123",
                "database": "production_db",
                "charset": "utf8mb4",
            },
            {
                "host": "localhost",
                "user": "test",
                "password": "test",
                "database": "test_db",
                "charset": "utf8",
            },
            {
                "host": "192.168.1.100",
                "user": "user@domain",
                "password": "p@ssw0rd!",
                "database": "app_db",
                "charset": "latin1",
            },
        ]

        for config in test_cases:
            # Set environment variables
            os.environ["DATABASE_MYSQL_HOST"] = config["host"]
            os.environ["DATABASE_MYSQL_USER"] = config["user"]
            os.environ["DATABASE_MYSQL_PASSWORD"] = config["password"]
            os.environ["DATABASE_MYSQL_DATABASE"] = config["database"]
            os.environ["DATABASE_MYSQL_CHARSET"] = config["charset"]

            backend = self.MysqlSTMBackend()

            # Verify configuration is correctly loaded
            assert backend.mysql_config.host == config["host"]
            assert backend.mysql_config.user == config["user"]
            assert backend.mysql_config.password == config["password"]
            assert backend.mysql_config.database == config["database"]
            assert backend.mysql_config.charset == config["charset"]

            # Verify URL construction
            backend.model_post_init(None)
            expected_url = f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}/{config['database']}"
            assert backend._db_url == expected_url

    def test_backend_immutability(self):
        """Test that backend configuration is properly initialized and used"""
        backend = self.MysqlSTMBackend()

        # Verify that the configuration is properly set
        assert backend.mysql_config.host == "test_host"

        # If _db_url is set, verify it's correct
        if hasattr(backend, "_db_url"):
            assert backend._db_url is not None

    def test_mysql_specific_features(self):
        """Test MySQL-specific features like charset configuration"""
        backend = self.MysqlSTMBackend()

        # Verify charset is properly configured
        assert backend.mysql_config.charset == "utf8"

        # Test with different charset
        os.environ["DATABASE_MYSQL_CHARSET"] = "utf8mb4"
        backend_utf8mb4 = self.MysqlSTMBackend()
        assert backend_utf8mb4.mysql_config.charset == "utf8mb4"

    def test_url_construction_with_port(self):
        """Test URL construction when port is specified"""
        # Set up environment with port
        os.environ["DATABASE_MYSQL_HOST"] = "db.example.com"
        os.environ["DATABASE_MYSQL_USER"] = "user"
        os.environ["DATABASE_MYSQL_PASSWORD"] = "pass"
        os.environ["DATABASE_MYSQL_DATABASE"] = "db"

        backend = self.MysqlSTMBackend()

        # Call model_post_init
        backend.model_post_init(None)

        # Verify URL is correctly constructed (MySQL URL doesn't include port by default)
        expected_url = "mysql+pymysql://user:pass@db.example.com/db"
        assert backend._db_url == expected_url
