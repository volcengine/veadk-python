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

from __future__ import annotations

from typing import Dict
from typing import Optional
from datetime import timedelta
from contextlib import AsyncExitStack

from google.adk.tools.mcp_tool.mcp_session_manager import MCPSessionManager
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from mcp import ClientSession
from bytedance.jeddak_trusted_mcp import (
    trusted_mcp_client,
    trusted_mcp_client_context,
)
from veadk.utils.logger import get_logger

logger = get_logger("veadk." + __name__)


class TrustedMcpSessionManager(MCPSessionManager):
    """Manages TrustedMCP client sessions.

    This class provides methods for creating and initializing TrustedMCP client sessions,
    handling different connection parameters (Stdio and SSE) and supporting
    session pooling based on authentication headers.
    """

    def _create_client(self, merged_headers: Optional[Dict[str, str]] = None):
        """Creates an MCP client based on the connection parameters.

        Args:
            merged_headers: Optional headers to include in the connection.
                           Only applicable for SSE and StreamableHTTP connections.

        Returns:
            The appropriate MCP client instance.

        Raises:
            ValueError: If the connection parameters are not supported.
        """
        if (
            isinstance(self._connection_params, StreamableHTTPConnectionParams)
            and merged_headers
            and merged_headers.pop("x-trusted-mcp", None) == "true"
        ):
            logger.info("Creating TrustedMCP client")
            # FIXME: something wrong in client created via trusted_mcp_client_context as the
            # transports returned by exit_stack.enter_async_context(client) are inconsisted
            # with that via streamablehttp_client.
            client = trusted_mcp_client_context(
                url=self._connection_params.url,
                headers=merged_headers,
                timeout=timedelta(seconds=self._connection_params.timeout),
                sse_read_timeout=timedelta(
                    seconds=self._connection_params.sse_read_timeout
                ),
                terminate_on_close=self._connection_params.terminate_on_close,
            )
        else:
            logger.info("Creating MCP client")
            client = super()._create_client(merged_headers)
        return client

    async def create_session(
        self, headers: Optional[Dict[str, str]] = None
    ) -> ClientSession:
        """Creates and initializes an MCP client session.

        This method will check if an existing session for the given headers
        is still connected. If it's disconnected, it will be cleaned up and
        a new session will be created.

        Args:
            headers: Optional headers to include in the session. These will be
                    merged with any existing connection headers. Only applicable
                    for SSE and StreamableHTTP connections.

        Returns:
            ClientSession: The initialized MCP client session.
        """
        # Merge headers once at the beginning
        merged_headers = self._merge_headers(headers)

        # Generate session key using merged headers
        session_key = self._generate_session_key(merged_headers)

        # Use async lock to prevent race conditions
        async with self._session_lock:
            # Check if we have an existing session
            if session_key in self._sessions:
                session, exit_stack = self._sessions[session_key]

                # Check if the existing session is still connected
                if not self._is_session_disconnected(session):
                    # Session is still good, return it
                    return session
                else:
                    # Session is disconnected, clean it up
                    logger.info("Cleaning up disconnected session: %s", session_key)
                    try:
                        await exit_stack.aclose()
                    except Exception as e:
                        logger.warning(
                            "Error during disconnected session cleanup: %s", e
                        )
                    finally:
                        del self._sessions[session_key]

            # Create a new session (either first time or replacing disconnected one)
            exit_stack = AsyncExitStack()

            try:
                # FIXME: reuse the normal procedure to create a session after updated trusted_mcp_client_context
                if (
                    isinstance(self._connection_params, StreamableHTTPConnectionParams)
                    and merged_headers
                    and merged_headers.pop("x-trusted-mcp", None) == "true"
                ):
                    logger.info("Initialize TrustedMCP session via trusted_mcp_client")
                    session = await exit_stack.enter_async_context(
                        trusted_mcp_client(
                            url=self._connection_params.url,
                            headers=merged_headers,
                            timeout=timedelta(seconds=self._connection_params.timeout),
                            sse_read_timeout=timedelta(
                                seconds=self._connection_params.sse_read_timeout
                            ),
                            terminate_on_close=self._connection_params.terminate_on_close,
                        )
                    )

                    # Store session and exit stack in the pool
                    self._sessions[session_key] = (session, exit_stack)
                    logger.debug("Created new session: %s", session_key)
                    return session
                else:
                    # Create a new session
                    logger.info("Initialize MCP session")
                    return await super().create_session(headers)
            except Exception:
                # If session creation fails, clean up the exit stack
                if exit_stack:
                    await exit_stack.aclose()
                raise
