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

"""Unit tests for VeCredentialService."""

import pytest
from unittest.mock import Mock

from google.adk.auth.auth_credential import (
    AuthCredential,
    AuthCredentialTypes,
    HttpAuth,
    HttpCredentials,
)
from google.adk.auth.auth_tool import AuthConfig
from google.adk.agents.callback_context import CallbackContext

from veadk.auth.ve_credential_service import VeCredentialService


@pytest.fixture
def credential_service():
    """Create a VeCredentialService instance for testing."""
    return VeCredentialService()


@pytest.fixture
def sample_auth_credential():
    """Create a sample AuthCredential for testing (HTTP Bearer type)."""
    return AuthCredential(
        auth_type=AuthCredentialTypes.HTTP,
        http=HttpAuth(
            scheme="bearer",
            credentials=HttpCredentials(token="test_token_123"),
        ),
    )


@pytest.fixture
def sample_api_key_credential():
    """Create a sample API Key AuthCredential for testing."""
    return AuthCredential(
        auth_type=AuthCredentialTypes.API_KEY,
        api_key="test_api_key_123",
    )


@pytest.fixture
def mock_callback_context():
    """Create a mock CallbackContext."""
    mock_ctx = Mock(spec=CallbackContext)
    mock_ctx._invocation_context = Mock()
    mock_ctx._invocation_context.app_name = "test_app"
    mock_ctx._invocation_context.user_id = "user123"
    return mock_ctx


@pytest.fixture
def mock_auth_config():
    """Create a mock AuthConfig."""
    mock_config = Mock(spec=AuthConfig)
    mock_config.credential_key = "test_key"
    mock_config.exchanged_auth_credential = AuthCredential(
        auth_type=AuthCredentialTypes.HTTP,
        http=HttpAuth(
            scheme="bearer",
            credentials=HttpCredentials(token="test_token"),
        ),
    )
    return mock_config


class TestVeCredentialService:
    """Tests for VeCredentialService class."""

    def test_initialization(self, credential_service):
        """Test service initialization."""
        assert credential_service._credentials == {}

    @pytest.mark.asyncio
    async def test_set_and_get_credential(
        self, credential_service, sample_auth_credential
    ):
        """Test setting and getting credentials."""
        # Set credential
        await credential_service.set_credential(
            app_name="test_app",
            user_id="user123",
            credential_key="bearer_token",
            credential=sample_auth_credential,
        )

        # Get credential
        retrieved = await credential_service.get_credential(
            app_name="test_app",
            user_id="user123",
            credential_key="bearer_token",
        )

        assert retrieved is not None
        assert retrieved.http.credentials.token == "test_token_123"

    @pytest.mark.asyncio
    async def test_get_nonexistent_credential(self, credential_service):
        """Test getting a credential that doesn't exist."""
        credential = await credential_service.get_credential(
            app_name="nonexistent_app",
            user_id="nonexistent_user",
            credential_key="nonexistent_key",
        )

        assert credential is None

    @pytest.mark.asyncio
    async def test_multiple_users_same_app(self, credential_service):
        """Test storing credentials for multiple users in the same app."""
        cred1 = AuthCredential(
            auth_type=AuthCredentialTypes.HTTP,
            http=HttpAuth(
                scheme="bearer",
                credentials=HttpCredentials(token="token_user1"),
            ),
        )
        cred2 = AuthCredential(
            auth_type=AuthCredentialTypes.HTTP,
            http=HttpAuth(
                scheme="bearer",
                credentials=HttpCredentials(token="token_user2"),
            ),
        )

        # Set credentials for two different users
        await credential_service.set_credential(
            app_name="test_app",
            user_id="user1",
            credential_key="bearer_token",
            credential=cred1,
        )
        await credential_service.set_credential(
            app_name="test_app",
            user_id="user2",
            credential_key="bearer_token",
            credential=cred2,
        )

        # Verify both credentials are stored separately
        retrieved1 = await credential_service.get_credential(
            app_name="test_app",
            user_id="user1",
            credential_key="bearer_token",
        )
        retrieved2 = await credential_service.get_credential(
            app_name="test_app",
            user_id="user2",
            credential_key="bearer_token",
        )

        assert retrieved1.http.credentials.token == "token_user1"
        assert retrieved2.http.credentials.token == "token_user2"

    @pytest.mark.asyncio
    async def test_multiple_credential_keys_same_user(self, credential_service):
        """Test storing multiple credential keys for the same user."""
        cred1 = AuthCredential(
            auth_type=AuthCredentialTypes.HTTP,
            http=HttpAuth(
                scheme="bearer",
                credentials=HttpCredentials(token="bearer_token_123"),
            ),
        )
        cred2 = AuthCredential(
            auth_type=AuthCredentialTypes.API_KEY,
            api_key="api_key_456",
        )

        # Set different credential types for the same user
        await credential_service.set_credential(
            app_name="test_app",
            user_id="user123",
            credential_key="bearer_token",
            credential=cred1,
        )
        await credential_service.set_credential(
            app_name="test_app",
            user_id="user123",
            credential_key="api_key",
            credential=cred2,
        )

        # Verify both credentials are stored
        retrieved1 = await credential_service.get_credential(
            app_name="test_app",
            user_id="user123",
            credential_key="bearer_token",
        )
        retrieved2 = await credential_service.get_credential(
            app_name="test_app",
            user_id="user123",
            credential_key="api_key",
        )

        assert retrieved1.http.credentials.token == "bearer_token_123"
        assert retrieved2.api_key == "api_key_456"

    @pytest.mark.asyncio
    async def test_save_credential_via_adk_interface(
        self, credential_service, mock_callback_context, mock_auth_config
    ):
        """Test saving credential via ADK BaseCredentialService interface."""
        # Save credential using ADK interface
        await credential_service.save_credential(
            auth_config=mock_auth_config,
            callback_context=mock_callback_context,
        )

        # Verify credential was stored
        credential = await credential_service.get_credential(
            app_name="test_app",
            user_id="user123",
            credential_key="test_key",
        )

        assert credential is not None
        assert credential.http.credentials.token == "test_token"

    @pytest.mark.asyncio
    async def test_load_credential_via_adk_interface(
        self,
        credential_service,
        mock_callback_context,
        mock_auth_config,
        sample_auth_credential,
    ):
        """Test loading credential via ADK BaseCredentialService interface."""
        # First set a credential
        await credential_service.set_credential(
            app_name="test_app",
            user_id="user123",
            credential_key="test_key",
            credential=sample_auth_credential,
        )

        # Load credential using ADK interface
        loaded = await credential_service.load_credential(
            auth_config=mock_auth_config,
            callback_context=mock_callback_context,
        )

        assert loaded is not None
        assert loaded.http.credentials.token == "test_token_123"

    @pytest.mark.asyncio
    async def test_load_nonexistent_credential_via_adk_interface(
        self, credential_service, mock_callback_context, mock_auth_config
    ):
        """Test loading a nonexistent credential via ADK interface."""
        # Try to load a credential that doesn't exist
        loaded = await credential_service.load_credential(
            auth_config=mock_auth_config,
            callback_context=mock_callback_context,
        )

        assert loaded is None

    @pytest.mark.asyncio
    async def test_overwrite_existing_credential(self, credential_service):
        """Test overwriting an existing credential."""
        cred1 = AuthCredential(
            auth_type=AuthCredentialTypes.HTTP,
            http=HttpAuth(
                scheme="bearer",
                credentials=HttpCredentials(token="old_token"),
            ),
        )
        cred2 = AuthCredential(
            auth_type=AuthCredentialTypes.HTTP,
            http=HttpAuth(
                scheme="bearer",
                credentials=HttpCredentials(token="new_token"),
            ),
        )

        # Set initial credential
        await credential_service.set_credential(
            app_name="test_app",
            user_id="user123",
            credential_key="bearer_token",
            credential=cred1,
        )

        # Overwrite with new credential
        await credential_service.set_credential(
            app_name="test_app",
            user_id="user123",
            credential_key="bearer_token",
            credential=cred2,
        )

        # Verify new credential replaced the old one
        retrieved = await credential_service.get_credential(
            app_name="test_app",
            user_id="user123",
            credential_key="bearer_token",
        )

        assert retrieved.http.credentials.token == "new_token"

    @pytest.mark.asyncio
    async def test_credential_isolation_between_apps(self, credential_service):
        """Test that credentials are isolated between different apps."""
        cred1 = AuthCredential(
            auth_type=AuthCredentialTypes.HTTP,
            http=HttpAuth(
                scheme="bearer",
                credentials=HttpCredentials(token="app1_token"),
            ),
        )
        cred2 = AuthCredential(
            auth_type=AuthCredentialTypes.HTTP,
            http=HttpAuth(
                scheme="bearer",
                credentials=HttpCredentials(token="app2_token"),
            ),
        )

        # Set credentials for two different apps
        await credential_service.set_credential(
            app_name="app1",
            user_id="user123",
            credential_key="bearer_token",
            credential=cred1,
        )
        await credential_service.set_credential(
            app_name="app2",
            user_id="user123",
            credential_key="bearer_token",
            credential=cred2,
        )

        # Verify credentials are isolated
        retrieved1 = await credential_service.get_credential(
            app_name="app1",
            user_id="user123",
            credential_key="bearer_token",
        )
        retrieved2 = await credential_service.get_credential(
            app_name="app2",
            user_id="user123",
            credential_key="bearer_token",
        )

        assert retrieved1.http.credentials.token == "app1_token"
        assert retrieved2.http.credentials.token == "app2_token"
