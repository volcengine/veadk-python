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

"""Utility functions for handling authentication events in the veADK framework."""

from __future__ import annotations
import base64
import functools
from typing import Optional

from google.adk.events import Event
from google.adk.auth import AuthConfig
from google.adk.auth.auth_credential import AuthCredential

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def is_pending_auth_event(event: Event) -> bool:
    """Check if an ADK event represents a pending authentication request.

    The ADK framework emits a special function call ('adk_request_credential')
    when a tool requires user authentication that hasn't been satisfied yet.

    Args:
        event: The ADK Event object to inspect.

    Returns:
        True if the event is an 'adk_request_credential' function call, False otherwise.
    """
    return (
        event.content
        and event.content.parts
        and event.content.parts[0]
        and event.content.parts[0].function_call
        and event.content.parts[0].function_call.name == "adk_request_credential"
    )


def get_function_call_id(event: Event) -> str:
    """Extract the unique function call ID from an ADK event.

    This ID is used to correlate function responses back to the specific
    function call that initiated the authentication request.

    Args:
        event: The ADK Event object containing the function call.

    Returns:
        The unique identifier string of the function call.

    Raises:
        ValueError: If the function call ID cannot be found in the event structure.
    """
    if (
        event
        and event.content
        and event.content.parts
        and event.content.parts[0]
        and event.content.parts[0].function_call
        and event.content.parts[0].function_call.id
    ):
        return event.content.parts[0].function_call.id

    raise ValueError(f"Cannot extract function call ID from event: {event}")


def get_function_call_auth_config(event: Event) -> AuthConfig:
    """Extract authentication configuration from an 'adk_request_credential' event.

    The client should use this AuthConfig to provide necessary authentication details
    (like OAuth codes and state) and send it back to the ADK to continue the OAuth
    token exchange process.

    Args:
        event: The ADK Event object containing the 'adk_request_credential' call.

    Returns:
        An AuthConfig object populated with details from the function call arguments.

    Raises:
        ValueError: If the 'authConfig' argument cannot be found in the event.
    """
    if (
        event
        and event.content
        and event.content.parts
        and event.content.parts[0]
        and event.content.parts[0].function_call
        and event.content.parts[0].function_call.args
        and event.content.parts[0].function_call.args.get("authConfig")
    ):
        auth_config_dict = event.content.parts[0].function_call.args.get("authConfig")
        return AuthConfig(**auth_config_dict)

    raise ValueError(f"Cannot extract auth config from event: {event}")


def generate_headers(credential: AuthCredential) -> Optional[dict[str, str]]:
    """Extracts authentication headers from credentials.

    Args:
        credential: The authentication credential to process.

    Returns:
        Dictionary of headers to add to the request, or None if no auth.
    """
    headers: Optional[dict[str, str]] = None
    if credential:
        if credential.oauth2:
            headers = {"Authorization": f"Bearer {credential.oauth2.access_token}"}
        elif credential.http:
            # Handle HTTP authentication schemes
            if (
                credential.http.scheme.lower() == "bearer"
                and credential.http.credentials.token
            ):
                headers = {
                    "Authorization": f"Bearer {credential.http.credentials.token}"
                }
            elif credential.http.scheme.lower() == "basic":
                # Handle basic auth
                if (
                    credential.http.credentials.username
                    and credential.http.credentials.password
                ):
                    credentials = f"{credential.http.credentials.username}:{credential.http.credentials.password}"
                    encoded_credentials = base64.b64encode(
                        credentials.encode()
                    ).decode()
                    headers = {"Authorization": f"Basic {encoded_credentials}"}
            elif credential.http.credentials.token:
                # Handle other HTTP schemes with token
                headers = {
                    "Authorization": (
                        f"{credential.http.scheme} {credential.http.credentials.token}"
                    )
                }
        elif credential.api_key:
            headers = {"Authorization": credential.api_key}
        elif credential.service_account:
            pass

    return headers


def retry_on_errors(func):
    """Decorator to automatically retry action when MCP session errors occur.

    When MCP session errors occur, the decorator will automatically retry the
    action once. The create_session method will handle creating a new session
    if the old one was disconnected.

    Args:
        func: The function to decorate.

    Returns:
        The decorated function.
    """

    @functools.wraps(func)  # Preserves original function metadata
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            # If an error is thrown, we will retry the function to reconnect to the
            # server. create_session will handle detecting and replacing disconnected
            # sessions.
            logger.info("Retrying %s due to error: %s", func.__name__, e)
            return await func(self, *args, **kwargs)

    return wrapper
