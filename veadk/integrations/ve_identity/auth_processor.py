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

"""Authentication request processor for handling OAuth2 flows in agent conversations."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Awaitable, Callable, Optional, TYPE_CHECKING

from google.adk.auth import AuthConfig
from google.genai import types
from google.adk.auth.auth_credential import OAuth2Auth

from .identity_client import IdentityClient
from .models import AuthRequestConfig, OAuth2AuthPoller
from .utils import (
    get_function_call_auth_config,
    get_function_call_id,
    is_pending_auth_event,
)
from a2a.utils import new_agent_text_message

from veadk.utils.logger import get_logger
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState


if TYPE_CHECKING:
    from veadk.runner import Runner


logger = get_logger("veadk." + __name__)

# Default configuration for token polling
DEFAULT_POLLING_INTERVAL_SECONDS = 5
DEFAULT_POLLING_TIMEOUT_SECONDS = 600


class MockOauth2AuthPoller(OAuth2AuthPoller):
    """Mock OAuth2 auth poller for testing purposes."""

    async def poll_for_auth(self, *args, **kwargs) -> OAuth2Auth:
        """Return a mock oauth2 auth immediately.

        Returns:
            A mock token string.
        """
        return OAuth2Auth(access_token="mock_token")


class WaitInputOauth2AuthPoller(OAuth2AuthPoller):
    """Wait for user input to complete OAuth2 flow."""

    def __init__(self, auth_uri: str, *args, **kwargs):
        self.auth_uri = auth_uri

    async def poll_for_auth(self) -> OAuth2Auth:
        """Wait for user input to complete OAuth2 flow.

        Returns:
            The complete OAuth2Auth object containing auth_response_uri.
        """

        async def get_user_input(prompt: str) -> str:
            loop = asyncio.get_event_loop()
            # Run the blocking `input()` function in a separate thread managed by the executor.
            return await loop.run_in_executor(None, input, prompt)

        logger.info(
            f"Please open this URL in your browser to authorize: {self.auth_uri}"
        )
        auth_response_uri = await get_user_input(f"Please enter the callback URL:\n> ")
        auth_response_uri = auth_response_uri.strip()

        if not auth_response_uri:
            raise Exception("No auth response URI provided. Aborting.")

        return OAuth2Auth(auth_response_uri=auth_response_uri)


class _DefaultOauth2AuthPoller(OAuth2AuthPoller):
    """Default implementation of OAuth2 auth polling.

    This poller repeatedly calls a polling function until a OAuth2 auth becomes available
    or a timeout occurs.
    """

    def __init__(
        self,
        auth_url: str,
        polling_func: Callable[[], Optional[OAuth2Auth]] | Callable[[], Awaitable[Optional[OAuth2Auth]]],
    ):
        """Initialize the OAuth2 auth poller.

        Args:
            auth_url: The authorization URL for logging purposes.
            polling_func: Function that returns the OAuth2 auth when ready, or None if not yet available.
                         Can be either sync or async function.
        """
        self.auth_url = auth_url
        self.polling_func = polling_func

    async def poll_for_auth(self) -> OAuth2Auth:
        """Poll for a oauth2 auth until it becomes available or timeout occurs.

        Returns:
            The complete OAuth2Auth object containing tokens or auth_response_uri.

        Raises:
            asyncio.TimeoutError: If polling times out before oauth2 auth is available.
        """
        start_time = time.time()

        while time.time() - start_time < DEFAULT_POLLING_TIMEOUT_SECONDS:
            await asyncio.sleep(DEFAULT_POLLING_INTERVAL_SECONDS)

            logger.info(
                f"Polling for oauth2 auth at authorization URL: {self.auth_url}"
            )

            # Check if polling_func is async or sync
            import inspect
            if inspect.iscoroutinefunction(self.polling_func):
                oauth2auth = await self.polling_func()
            else:
                oauth2auth = self.polling_func()

            if oauth2auth is not None:
                logger.info("OAuth2 auth successfully retrieved")
                return oauth2auth

        raise asyncio.TimeoutError(
            f"OAuth2 auth polling timed out after {DEFAULT_POLLING_TIMEOUT_SECONDS} seconds. "
            "User may not have completed authorization."
        )


class _NoOpAuthProcessor:
    """No-op auth processor that doesn't modify the event generator."""

    def with_auth_loop(self, runner, message, max_cycles):
        """Return a decorator that does nothing."""

        def decorator(func):
            return func

        return decorator


class AuthRequestProcessor:
    """Processor for handling authentication requests in agent conversations.

    This class manages the OAuth2 authentication flow when tools require user authorization.
    It handles displaying authorization URLs to users and polling for tokens after authorization.

    Attributes:
        config: Configuration for authentication request handling.
    """

    def __init__(self, *, config: Optional[AuthRequestConfig] = None):
        """Initialize the authentication request processor.

        Args:
            config: Authentication configuration. If None, uses default configuration
                   that prints the authorization URL to console.
        """
        self.config = config or AuthRequestConfig(
            on_auth_url=lambda url: print(
                f"Please open this URL in your browser to authorize: {url}"
            )
        )
        self._identity_client = self.config.identity_client or IdentityClient(
            region=self.config.region
        )

    async def process_auth_request(
        self,
        auth_request_event_id: str,
        auth_config: AuthConfig,
        task_updater: Optional[TaskUpdater] = None,
    ) -> types.Content:
        """Process a single authentication request.

        This method handles the complete OAuth2 flow:
        1. Displays the authorization URL to the user (via on_auth_url callback)
        2. Polls for the access token after user authorization
        3. Constructs and returns the authentication response

        Args:
            auth_request_event_id: Unique ID of the authentication request event.
            auth_config: Authentication configuration containing the auth URI.

        Returns:
            Content object containing the authentication response to send back to the agent.
        """
        logger.info(f"Processing auth request: {auth_request_event_id}")

        auth_uri = auth_config.exchanged_auth_credential.oauth2.auth_uri
        request_dict = (
            json.loads(resource_ref_str)
            if (resource_ref_str := auth_config.exchanged_auth_credential.resource_ref)
            else {}
        )

        # Invoke the auth URL callback (sync or async)
        if on_auth_url := self.config.on_auth_url:
            if asyncio.iscoroutinefunction(on_auth_url):
                await on_auth_url(auth_uri)
            else:
                on_auth_url(auth_uri)

        # Use custom poller or default poller
        # Create async token fetcher for default poller
        async def async_token_fetcher():
            response = await self._identity_client.get_oauth2_token_or_auth_url(**request_dict)
            return (
                OAuth2Auth(access_token=response.access_token)
                if response.access_token and response.access_token.strip()
                else None
            )

        active_poller = (
            self.config.oauth2_auth_poller(auth_uri, request_dict)
            if self.config.oauth2_auth_poller
            else _DefaultOauth2AuthPoller(auth_uri, async_token_fetcher)
        )

        # Poll for the oauth2 auth
        updated_oauth2_auth = await active_poller.poll_for_auth()
        if task_updater:
            await task_updater.update_status(
                TaskState.working,
                message=new_agent_text_message("Authorization received, continuing..."),
            )
        for k, v in updated_oauth2_auth.__dict__.items():
            if (
                v is not None
                and k
                in auth_config.exchanged_auth_credential.oauth2.__pydantic_fields__
            ):
                auth_config.exchanged_auth_credential.oauth2.__dict__[k] = v

        # Construct the authentication response
        auth_content = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=auth_request_event_id,
                        name="adk_request_credential",
                        response=auth_config.model_dump(),
                    )
                )
            ],
        )

        logger.info(f"Auth request {auth_request_event_id} processed successfully")
        return auth_content

    def with_auth_loop(
        self,
        runner: Runner,
        message: types.Content,
        max_cycles: int,
        task_updater: Optional[TaskUpdater] = None,
    ):
        """Decorator to add authentication loop handling to event generators.

        This decorator intercepts runner.run_async calls and automatically handles
        authentication loops. The event_generator code can remain completely unchanged!

        Usage example:
            @auth_processor.with_auth_loop(
                runner=runner,
                message=message,
                max_cycles=len(tools) * 2 + 1
            )
            async def event_generator():
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=message,
                    run_config=RunConfig(streaming_mode=stream_mode),
                ):
                    if event.get_function_calls():
                        for function_call in event.get_function_calls():
                            logger.debug(f"Function call: {function_call}")
                    elif event.content is not None:
                        yield event.content.parts[0].text

            # Then call (no parameters needed):
            async for chunk in event_generator():
                print(chunk)

        The decorator automatically:
        1. Intercepts runner.run_async calls
        2. Detects authentication events
        3. Processes authentication requests
        4. Loops until no more authentication events

        Args:
            runner: Runner instance (will be wrapped).
            message: Initial message to send.
            max_cycles: Maximum number of authentication cycles to allow.

        Returns:
            Decorated generator function.
        """

        def decorator(event_generator_func):
            async def wrapper():
                current_message = message

                for _ in range(max_cycles):
                    auth_request_event_id = None
                    auth_config = None

                    # Buffer to collect chunks from this cycle
                    cycle_buffer = []

                    # Create a wrapped runner to intercept run_async calls
                    original_run_async = runner.run_async

                    async def wrapped_run_async(**kwargs):
                        nonlocal auth_request_event_id, auth_config

                        # Override the message with the current message
                        kwargs["new_message"] = current_message

                        async for event in original_run_async(**kwargs):
                            # Detect authentication events
                            if is_pending_auth_event(event):
                                auth_request_event_id = get_function_call_id(event)
                                auth_config = get_function_call_auth_config(event)
                                logger.info(
                                    f"Found auth request {auth_request_event_id}, breaking to process"
                                )

                                break

                            # Pass events to the caller
                            yield event

                    # Temporarily replace runner.run_async
                    runner.run_async = wrapped_run_async

                    try:
                        # Call the original event_generator and buffer the output
                        async for chunk in event_generator_func():
                            cycle_buffer.append(chunk)
                    finally:
                        # Restore the original run_async
                        runner.run_async = original_run_async

                    # Check if there was an authentication request
                    if auth_request_event_id and auth_config:
                        # Process the authentication request
                        current_message = await self.process_auth_request(
                            auth_request_event_id, auth_config, task_updater
                        )
                        # Continue to next cycle
                    else:
                        # No more auth events, yield the final chunk
                        logger.info("No more auth events found, processing complete")
                        yield cycle_buffer[-1]
                        break

            return wrapper

        return decorator
