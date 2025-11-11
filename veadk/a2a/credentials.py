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

"""In-memory credential store for VeADK A2A authentication.

This module provides an in-memory credential store that supports both
session-based and user-based credential management for A2A authentication.
"""

import asyncio
import logging
from typing import Optional

from a2a.client.auth import CredentialService
from a2a.client.base_client import ClientCallContext

logger = logging.getLogger(__name__)


class VeCredentialStore(CredentialService):
    """In-memory credential store supporting session-based and user-based lookups.

    This credential store implements the A2A CredentialService interface and provides
    flexible credential management for VeADK agents. It supports:

    - **Session-based credentials**: Credentials keyed by session ID
    - **User-based credentials**: Credentials keyed by user ID
    - **Fallback mechanism**: Tries session ID first, then falls back to user ID
    - **Sync/async set operations**: `set_credentials` can be called synchronously or asynchronously

    The store uses a two-level dictionary structure:
    - First level: context key (session ID or user ID)
    - Second level: security scheme name -> credential

    Examples:
        ```python
        # Create credential store
        store = VeCredentialStore()

        # Set credentials synchronously (for server-side)
        store.set_credentials(
            session_id="session_123",
            security_scheme_name="inbound_auth",
            credential="bearer_token_xyz"
        )

        # Set credentials asynchronously (for async contexts)
        await store.set_credentials_async(
            user_id="user_456",
            security_scheme_name="inbound_auth",
            credential="bearer_token_abc"
        )

        # Get credentials (always async, per CredentialService interface)
        from a2a.client.base_client import ClientCallContext

        # Retrieve by session ID
        token = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=ClientCallContext(state={"sessionId": "session_123"})
        )

        # Retrieve by user ID (fallback)
        token = await store.get_credentials(
            security_scheme_name="inbound_auth",
            context=ClientCallContext(state={"userId": "user_456"})
        )
        ```

    Note:
        This is an in-memory store and credentials will be lost when the process restarts.
        For production use cases requiring persistence, consider implementing a custom
        CredentialService backed by a database or cache.
    """

    def __init__(self) -> None:
        """Initialize the credential store with empty storage."""
        self._store: dict[str, dict[str, str]] = {}
        self._lock = asyncio.Lock()

    async def get_credentials(
        self,
        security_scheme_name: str,
        context: ClientCallContext | None,
    ) -> str | None:
        """Retrieve credentials from the store.

        This method attempts to retrieve credentials using the following priority:
        1. Session ID from context.state["sessionId"]
        2. User ID from context.state["userId"]

        Args:
            security_scheme_name: The name of the security scheme (e.g., "inbound_auth")
            context: The client call context containing session or user information

        Returns:
            The credential string if found, None otherwise

        Examples:
            ```python
            # Retrieve by session ID
            token = await store.get_credentials(
                security_scheme_name="inbound_auth",
                context=ClientCallContext(state={"sessionId": "session_123"})
            )

            # Retrieve by user ID
            token = await store.get_credentials(
                security_scheme_name="inbound_auth",
                context=ClientCallContext(state={"userId": "user_456"})
            )
            ```
        """
        if not context or not context.state:
            return None

        user_id = context.state.get("userId")
        if user_id:
            credential = self._store.get(user_id, {}).get(security_scheme_name)
            if credential:
                return credential

        session_id = context.state.get("sessionId")
        if session_id:
            credential = self._store.get(session_id, {}).get(security_scheme_name)
            if credential:
                return credential

        return None

    def set_credentials(
        self,
        security_scheme_name: str,
        credential: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Set credentials in the store (synchronous version).

        This method can be called synchronously from non-async contexts (e.g., server middleware).
        At least one of session_id or user_id must be provided.

        Args:
            security_scheme_name: The name of the security scheme (e.g., "inbound_auth")
            credential: The credential string to store
            session_id: Optional session ID to use as the key
            user_id: Optional user ID to use as the key

        Raises:
            ValueError: If neither session_id nor user_id is provided

        Examples:
            ```python
            # Set by session ID
            store.set_credentials(
                session_id="session_123",
                security_scheme_name="inbound_auth",
                credential="bearer_token_xyz"
            )

            # Set by user ID
            store.set_credentials(
                user_id="user_456",
                security_scheme_name="inbound_auth",
                credential="bearer_token_abc"
            )
            ```
        """
        if not session_id and not user_id:
            raise ValueError("Either session_id or user_id must be provided")

        # Use user_id if provided, otherwise use session_id
        context_key = user_id or session_id

        if context_key not in self._store:
            self._store[context_key] = {}

        self._store[context_key][security_scheme_name] = credential
        logger.debug(
            f"Set credential for {context_key} (scheme: {security_scheme_name})"
        )

    async def set_credentials_async(
        self,
        security_scheme_name: str,
        credential: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Set credentials in the store (async version).

        This is the async version of set_credentials, useful when called from async contexts.
        It uses a lock to ensure thread-safety in concurrent scenarios.

        Args:
            security_scheme_name: The name of the security scheme (e.g., "inbound_auth")
            credential: The credential string to store
            session_id: Optional session ID to use as the key
            user_id: Optional user ID to use as the key

        Raises:
            ValueError: If neither session_id nor user_id is provided

        Examples:
            ```python
            # Set by session ID (async)
            await store.set_credentials_async(
                session_id="session_123",
                security_scheme_name="inbound_auth",
                credential="bearer_token_xyz"
            )
            ```
        """
        async with self._lock:
            self.set_credentials(
                security_scheme_name=security_scheme_name,
                credential=credential,
                session_id=session_id,
                user_id=user_id,
            )

    def clear(self, context_key: Optional[str] = None) -> None:
        """Clear credentials from the store.

        Args:
            context_key: Optional session ID or user ID to clear. If None, clears all credentials.

        Examples:
            ```python
            # Clear specific session
            store.clear("session_123")

            # Clear all credentials
            store.clear()
            ```
        """
        if context_key:
            if context_key in self._store:
                del self._store[context_key]
        else:
            self._store.clear()
