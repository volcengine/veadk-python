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

"""A2A Credential Service for VeADK.

This module provides a credential service that supports direct credential
management by app_name and user_id, extending the ADK BaseCredentialService.
"""

import logging
from typing import Optional

from typing_extensions import override

from google.adk.agents.callback_context import CallbackContext
from google.adk.auth.auth_credential import AuthCredential
from google.adk.auth.auth_tool import AuthConfig
from google.adk.auth.credential_service.base_credential_service import (
    BaseCredentialService,
)

logger = logging.getLogger(__name__)


class VeCredentialService(BaseCredentialService):
    """In-memory credential service with direct app_name/user_id access.

    This service extends BaseCredentialService to support both:
    1. Standard ADK credential operations (load_credential, save_credential)
    2. Direct credential access by app_name and user_id

    The credential store is organized as:
    {
        app_name: {
            user_id: {
                credential_key: AuthCredential
            }
        }
    }

    Examples:
        ```python
        # Create service
        service = VeCredentialService()

        # Direct set/get
        await service.set_credential(
            app_name="my_app",
            user_id="user123",
            credential_key="bearer_token",
            credential=AuthCredential(...)
        )

        credential = await service.get_credential(
            app_name="my_app",
            user_id="user123",
            credential_key="bearer_token"
        )

        # Standard ADK operations
        await service.save_credential(auth_config, callback_context)
        credential = await service.load_credential(auth_config, callback_context)
        ```
    """

    def __init__(self):
        """Initialize the credential service with empty storage."""
        super().__init__()
        self._credentials: dict[str, dict[str, dict[str, AuthCredential]]] = {}

    @override
    async def load_credential(
        self,
        auth_config: AuthConfig,
        callback_context: CallbackContext,
    ) -> Optional[AuthCredential]:
        """Load credential from the store using auth config and callback context.

        Args:
            auth_config: Auth configuration containing credential_key
            callback_context: Callback context containing app_name and user_id

        Returns:
            The stored AuthCredential, or None if not found
        """
        app_name = callback_context._invocation_context.app_name
        user_id = callback_context._invocation_context.user_id

        return await self.get_credential(
            app_name=app_name,
            user_id=user_id,
            credential_key=auth_config.credential_key,
        )

    @override
    async def save_credential(
        self,
        auth_config: AuthConfig,
        callback_context: CallbackContext,
    ) -> None:
        """Save credential to the store using auth config and callback context.

        Args:
            auth_config: Auth configuration containing credential_key and exchanged_auth_credential
            callback_context: Callback context containing app_name and user_id
        """
        app_name = callback_context._invocation_context.app_name
        user_id = callback_context._invocation_context.user_id

        await self.set_credential(
            app_name=app_name,
            user_id=user_id,
            credential_key=auth_config.credential_key,
            credential=auth_config.exchanged_auth_credential,
        )

    async def set_credential(
        self,
        app_name: str,
        user_id: str,
        credential_key: str,
        credential: AuthCredential,
    ) -> None:
        """Directly set a credential by app_name, user_id, and credential_key (async).

        This method allows setting credentials without requiring a CallbackContext,
        useful for middleware and request interceptors.

        Args:
            app_name: Application name
            user_id: User identifier
            credential_key: Key to identify the credential
            credential: The AuthCredential to store

        Examples:
            ```python
            from google.adk.auth.auth_credential import AuthCredential, AuthCredentialTypes

            service = VeCredentialService()
            await service.set_credential(
                app_name="my_app",
                user_id="user123",
                credential_key="bearer_token",
                credential=AuthCredential(
                    auth_type=AuthCredentialTypes.BEARER_TOKEN,
                    bearer_token="eyJhbGc..."
                )
            )
            ```
        """
        if app_name not in self._credentials:
            self._credentials[app_name] = {}
        if user_id not in self._credentials[app_name]:
            self._credentials[app_name][user_id] = {}

        self._credentials[app_name][user_id][credential_key] = credential
        logger.debug(
            f"Set credential for app={app_name}, user={user_id}, key={credential_key}"
        )

    async def get_credential(
        self,
        app_name: str,
        user_id: str,
        credential_key: str,
    ) -> Optional[AuthCredential]:
        """Directly get a credential by app_name, user_id, and credential_key (async).

        This method allows retrieving credentials without requiring a CallbackContext,
        useful for middleware and request interceptors.

        Args:
            app_name: Application name
            user_id: User identifier
            credential_key: Key to identify the credential

        Returns:
            The stored AuthCredential, or None if not found

        Examples:
            ```python
            service = VeCredentialService()
            credential = await service.get_credential(
                app_name="my_app",
                user_id="user123",
                credential_key="bearer_token"
            )
            if credential:
                print(f"Found token: {credential.bearer_token}")
            ```
        """
        return self._credentials.get(app_name, {}).get(user_id, {}).get(credential_key)
