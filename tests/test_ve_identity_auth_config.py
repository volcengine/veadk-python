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

"""Unit tests for ve_identity auth_config module."""

import pytest
from veadk.integrations.ve_identity import (
    api_key_auth,
    oauth2_auth,
    workload_auth,
    ApiKeyAuthConfig,
    OAuth2AuthConfig,
    WorkloadAuthConfig,
)


class TestApiKeyAuth:
    """Tests for api_key_auth factory function."""

    def test_api_key_auth_basic(self):
        """Test creating basic API key auth config."""
        config = api_key_auth("test-provider")
        
        assert isinstance(config, ApiKeyAuthConfig)
        assert config.provider_name == "test-provider"
        assert config.auth_type == "api_key"
        assert config.region == "cn-beijing"
        assert config.identity_client is None

    def test_api_key_auth_with_region(self):
        """Test creating API key auth config with custom region."""
        config = api_key_auth("test-provider", region="us-east-1")
        
        assert config.provider_name == "test-provider"
        assert config.region == "us-east-1"
        assert config.auth_type == "api_key"

    def test_api_key_auth_empty_provider_name(self):
        """Test that empty provider_name raises ValueError."""
        with pytest.raises(ValueError, match="provider_name cannot be empty"):
            api_key_auth("")

    def test_api_key_auth_whitespace_provider_name(self):
        """Test that whitespace-only provider_name raises ValueError."""
        with pytest.raises(ValueError, match="provider_name cannot be empty"):
            api_key_auth("   ")


class TestOAuth2Auth:
    """Tests for oauth2_auth factory function."""

    def test_oauth2_auth_basic(self):
        """Test creating basic OAuth2 auth config."""
        config = oauth2_auth(
            provider_name="github",
            scopes=["repo", "user"],
            auth_flow="M2M"
        )
        
        assert isinstance(config, OAuth2AuthConfig)
        assert config.provider_name == "github"
        assert config.scopes == ["repo", "user"]
        assert config.auth_flow == "M2M"
        assert config.auth_type == "oauth2"
        assert config.force_authentication is False
        assert config.callback_url is None

    def test_oauth2_auth_with_all_params(self):
        """Test creating OAuth2 auth config with all parameters."""
        def on_auth_url_callback(url: str):
            pass
        
        config = oauth2_auth(
            provider_name="github",
            scopes=["repo", "user"],
            auth_flow="USER_FEDERATION",
            callback_url="https://example.com/callback",
            force_authentication=True,
            response_for_auth_required="Please authorize",
            on_auth_url=on_auth_url_callback,
            region="us-west-2"
        )
        
        assert config.provider_name == "github"
        assert config.scopes == ["repo", "user"]
        assert config.auth_flow == "USER_FEDERATION"
        assert config.callback_url == "https://example.com/callback"
        assert config.force_authentication is True
        assert config.response_for_auth_required == "Please authorize"
        assert config.on_auth_url == on_auth_url_callback
        assert config.region == "us-west-2"

    def test_oauth2_auth_empty_scopes(self):
        """Test that empty scopes raises ValueError."""
        with pytest.raises(ValueError, match="scopes cannot be empty"):
            oauth2_auth(
                provider_name="github",
                scopes=[],
                auth_flow="M2M"
            )

    def test_oauth2_auth_empty_scope_value(self):
        """Test that empty scope value raises ValueError."""
        with pytest.raises(ValueError, match="scope values cannot be empty"):
            oauth2_auth(
                provider_name="github",
                scopes=["repo", ""],
                auth_flow="M2M"
            )

    def test_oauth2_auth_duplicate_scopes_removed(self):
        """Test that duplicate scopes are removed."""
        config = oauth2_auth(
            provider_name="github",
            scopes=["repo", "user", "repo", "user"],
            auth_flow="M2M"
        )
        
        assert config.scopes == ["repo", "user"]

    def test_oauth2_auth_invalid_callback_url(self):
        """Test that invalid callback URL raises ValueError."""
        with pytest.raises(ValueError, match="callback_url must be a valid HTTP/HTTPS URL"):
            oauth2_auth(
                provider_name="github",
                scopes=["repo"],
                auth_flow="M2M",
                callback_url="invalid-url"
            )

    def test_oauth2_auth_valid_https_callback_url(self):
        """Test that valid HTTPS callback URL is accepted."""
        config = oauth2_auth(
            provider_name="github",
            scopes=["repo"],
            auth_flow="M2M",
            callback_url="https://example.com/callback"
        )
        
        assert config.callback_url == "https://example.com/callback"

    def test_oauth2_auth_valid_http_callback_url(self):
        """Test that valid HTTP callback URL is accepted."""
        config = oauth2_auth(
            provider_name="github",
            scopes=["repo"],
            auth_flow="M2M",
            callback_url="http://localhost:8080/callback"
        )
        
        assert config.callback_url == "http://localhost:8080/callback"


class TestWorkloadAuth:
    """Tests for workload_auth factory function."""

    def test_workload_auth_basic(self):
        """Test creating basic workload auth config."""
        config = workload_auth("test-provider")
        
        assert isinstance(config, WorkloadAuthConfig)
        assert config.provider_name == "test-provider"
        assert config.auth_type == "workload"
        assert config.region == "cn-beijing"
        assert config.identity_client is None

    def test_workload_auth_with_region(self):
        """Test creating workload auth config with custom region."""
        config = workload_auth("test-provider", region="eu-west-1")
        
        assert config.provider_name == "test-provider"
        assert config.region == "eu-west-1"
        assert config.auth_type == "workload"

    def test_workload_auth_empty_provider_name(self):
        """Test that empty provider_name raises ValueError."""
        with pytest.raises(ValueError, match="provider_name cannot be empty"):
            workload_auth("")

