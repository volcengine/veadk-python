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

"""Unit tests for VeCredentialStore."""

import pytest

from a2a.client.base_client import ClientCallContext

from veadk.a2a.credentials import VeCredentialStore


class TestVeCredentialStore:
    """Test suite for VeCredentialStore."""

    @pytest.mark.asyncio
    async def test_set_and_get_by_session_id(self):
        """Test setting and getting credentials by session ID."""
        store = VeCredentialStore()

        # Set credentials synchronously
        store.set_credentials(
            session_id="session_123",
            security_scheme_name="inbound_auth",
            credential="bearer_token_xyz",
        )

        # Get credentials
        context = ClientCallContext(state={"sessionId": "session_123"})
        token = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=context,
        )

        assert token == "bearer_token_xyz"

    @pytest.mark.asyncio
    async def test_set_and_get_by_user_id(self):
        """Test setting and getting credentials by user ID."""
        store = VeCredentialStore()

        # Set credentials synchronously
        store.set_credentials(
            user_id="user_456",
            security_scheme_name="inbound_auth",
            credential="bearer_token_abc",
        )

        # Get credentials
        context = ClientCallContext(state={"userId": "user_456"})
        token = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=context,
        )

        assert token == "bearer_token_abc"

    @pytest.mark.asyncio
    async def test_fallback_to_user_id(self):
        """Test fallback from session ID to user ID."""
        store = VeCredentialStore()

        # Set credentials by user ID
        store.set_credentials(
            user_id="user_789",
            security_scheme_name="inbound_auth",
            credential="bearer_token_fallback",
        )

        # Try to get with session ID (should fail) then fallback to user ID
        context = ClientCallContext(
            state={"sessionId": "nonexistent_session", "userId": "user_789"}
        )
        token = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=context,
        )

        assert token == "bearer_token_fallback"

    @pytest.mark.asyncio
    async def test_user_id_priority(self):
        """Test that user ID takes priority over user ID."""
        store = VeCredentialStore()

        # Set credentials for both session and user
        store.set_credentials(
            session_id="session_priority",
            security_scheme_name="inbound_auth",
            credential="session_token",
        )
        store.set_credentials(
            user_id="user_priority",
            security_scheme_name="inbound_auth",
            credential="user_token",
        )

        # Get with both session ID and user ID - should return session token
        context = ClientCallContext(
            state={"sessionId": "session_priority", "userId": "user_priority"}
        )
        token = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=context,
        )

        assert token == "user_token"

    @pytest.mark.asyncio
    async def test_async_set_credentials(self):
        """Test async version of set_credentials."""
        store = VeCredentialStore()

        # Set credentials asynchronously
        await store.set_credentials_async(
            session_id="async_session",
            security_scheme_name="inbound_auth",
            credential="async_token",
        )

        # Get credentials
        context = ClientCallContext(state={"sessionId": "async_session"})
        token = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=context,
        )

        assert token == "async_token"

    @pytest.mark.asyncio
    async def test_multiple_security_schemes(self):
        """Test storing multiple security schemes for the same session."""
        store = VeCredentialStore()

        # Set multiple credentials for the same session
        store.set_credentials(
            session_id="multi_session",
            security_scheme_name="inbound_auth",
            credential="inbound_token",
        )
        store.set_credentials(
            session_id="multi_session",
            security_scheme_name="outbound_auth",
            credential="outbound_token",
        )

        # Get both credentials
        context = ClientCallContext(state={"sessionId": "multi_session"})

        inbound_token = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=context,
        )
        outbound_token = await store.get_credentials(
            security_scheme_name="outbound_auth",
            context=context,
        )

        assert inbound_token == "inbound_token"
        assert outbound_token == "outbound_token"

    @pytest.mark.asyncio
    async def test_clear_specific_context(self):
        """Test clearing credentials for a specific context."""
        store = VeCredentialStore()

        # Set credentials for two sessions
        store.set_credentials(
            session_id="session_1",
            security_scheme_name="inbound_auth",
            credential="token_1",
        )
        store.set_credentials(
            session_id="session_2",
            security_scheme_name="inbound_auth",
            credential="token_2",
        )

        # Clear session_1
        store.clear("session_1")

        # Verify session_1 is cleared
        context1 = ClientCallContext(state={"sessionId": "session_1"})
        token1 = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=context1,
        )
        assert token1 is None

        # Verify session_2 still exists
        context2 = ClientCallContext(state={"sessionId": "session_2"})
        token2 = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=context2,
        )
        assert token2 == "token_2"

    @pytest.mark.asyncio
    async def test_clear_all(self):
        """Test clearing all credentials."""
        store = VeCredentialStore()

        # Set multiple credentials
        store.set_credentials(
            session_id="session_a",
            security_scheme_name="inbound_auth",
            credential="token_a",
        )
        store.set_credentials(
            user_id="user_b",
            security_scheme_name="inbound_auth",
            credential="token_b",
        )

        # Clear all
        store.clear()

        # Verify all are cleared
        context_a = ClientCallContext(state={"sessionId": "session_a"})
        token_a = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=context_a,
        )
        assert token_a is None

        context_b = ClientCallContext(state={"userId": "user_b"})
        token_b = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=context_b,
        )
        assert token_b is None

    @pytest.mark.asyncio
    async def test_no_context(self):
        """Test behavior when no context is provided."""
        store = VeCredentialStore()

        token = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=None,
        )

        assert token is None

    @pytest.mark.asyncio
    async def test_missing_session_and_user(self):
        """Test behavior when neither session ID nor user ID is in context."""
        store = VeCredentialStore()

        context = ClientCallContext(state={"someOtherKey": "value"})
        token = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=context,
        )

        assert token is None

    def test_set_credentials_without_ids_raises_error(self):
        """Test that set_credentials raises error when neither session_id nor user_id is provided."""
        store = VeCredentialStore()

        with pytest.raises(
            ValueError, match="Either session_id or user_id must be provided"
        ):
            store.set_credentials(
                security_scheme_name="inbound_auth",
                credential="token",
            )
