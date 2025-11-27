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

"""A2A Authentication Middleware for FastAPI/Starlette.

This module provides middleware for extracting authentication credentials
from HTTP requests and storing them in the credential service.
"""

from typing import Callable, Literal, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from volcenginesdkcore.rest import ApiException
import json
from starlette.datastructures import MutableHeaders
from veadk.auth.ve_credential_service import VeCredentialService
from veadk.utils.auth import (
    extract_delegation_chain_from_jwt,
    build_auth_config,
    VE_TIP_TOKEN_HEADER,
    VE_TIP_TOKEN_CREDENTIAL_KEY,
)
from veadk.integrations.ve_identity import (
    WorkloadToken,
    IdentityClient,
    get_default_identity_client,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class A2AAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to extract and store authentication credentials from requests.

    This middleware:
    1. Extracts auth tokens from Authorization header or query string
    2. Parses JWT tokens to extract user_id and delegation chain
    3. Builds AuthConfig based on the authentication method
    4. Stores credentials in the credential service
    5. Extracts TIP token from X-Ve-TIP-Token header for trust propagation
    6. Exchanges TIP token for workload access token using IdentityClient
    7. Sets workload token in request.scope["auth"] for downstream use

    Examples:
        ```python
        from fastapi import FastAPI
        from veadk.a2a.ve_middlewares import build_a2a_auth_middleware
        from veadk.auth.ve_credential_service  import VeCredentialService

        app = FastAPI()
        credential_service = VeCredentialService()

        # Add middleware with Authorization header support
        app.add_middleware(
            build_a2a_auth_middleware(
                app_name="my_app",
                credential_service=credential_service,
                auth_method="header"
            )
        )

        # Or with query string support
        app.add_middleware(
            build_a2a_auth_middleware(
                app_name="my_app",
                credential_service=credential_service,
                auth_method="querystring",
                token_param="token"
            )
        )
        ```
    """

    def __init__(
        self,
        app,
        app_name: str,
        credential_service: VeCredentialService,
        auth_method: Literal["header", "querystring"] = "header",
        token_param: str = "token",
        credential_key: str = "inbound_auth",
        identity_client: Optional[IdentityClient] = None,
    ):
        """Initialize the middleware.

        Args:
            app: The ASGI application
            app_name: Application name for credential storage
            credential_service: Credential service to store credentials
            auth_method: Authentication method - "header" or "querystring"
            token_param: Query parameter name for token (when auth_method="querystring")
            credential_key: Key to identify the credential in the store
            identity_client: Optional IdentityClient for TIP token exchange.
                If not provided, uses the global IdentityClient from VeIdentityConfig.
        """
        super().__init__(app)
        self.app_name = app_name
        self.credential_service = credential_service
        self.auth_method = auth_method
        self.token_param = token_param
        self.credential_key = credential_key
        self.identity_client = identity_client or get_default_identity_client()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process the request and extract authentication credentials.

        This method:
        1. Extracts token from Authorization header or query string
        2. Parses JWT to get user_id and stores credentials
        3. Sets request.scope["user"] with SimpleUser instance
        4. Extracts TIP token from X-Ve-TIP-Token header
        5. Exchanges TIP token for workload token via IdentityClient
        6. Sets request.scope["auth"] with WorkloadToken object

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or route handler

        Returns:
            The HTTP response
        """
        from starlette.authentication import SimpleUser

        token, has_prefix = self._extract_token(request)
        user_id = None

        if token:
            user_id, _ = extract_delegation_chain_from_jwt(token)
            if user_id:
                # Build auth config based on authentication method
                auth_config = build_auth_config(
                    token=token,
                    auth_method=self.auth_method,
                    credential_key=self.credential_key,
                    header_scheme="bearer" if has_prefix else None,
                    query_param_name=self.token_param,
                )

                await self.credential_service.set_credential(
                    app_name=self.app_name,
                    user_id=user_id,
                    credential_key=self.credential_key,
                    credential=auth_config.exchanged_auth_credential,
                )

                logger.debug(
                    f"Stored credential for app={self.app_name}, user={user_id}, "
                    f"method={self.auth_method}"
                )

                request.scope["user"] = SimpleUser(user_id)
            else:
                logger.warning("Failed to extract user_id from JWT token")

        # Extract TIP token from X-Ve-TIP-Token header for trust propagation
        tip_token = request.headers.get(VE_TIP_TOKEN_HEADER)

        try:
            workload_token: WorkloadToken = (
                self.identity_client.get_workload_access_token(
                    user_token=tip_token, user_id=user_id
                )
            )
            workload_auth_config = build_auth_config(
                token=workload_token.workload_access_token,
                auth_method="apikey",
                credential_key=VE_TIP_TOKEN_CREDENTIAL_KEY,
                header_name=VE_TIP_TOKEN_HEADER,
            )

            await self.credential_service.set_credential(
                app_name=self.app_name,
                user_id=user_id,
                credential_key=VE_TIP_TOKEN_CREDENTIAL_KEY,
                credential=workload_auth_config.exchanged_auth_credential,
            )
        except ApiException as e:
            logger.warning(f"Failed to get workload token: {e.reason}")
            workload_token = None
        request.scope["auth"] = workload_token
        # Continue processing the request
        response = await call_next(request)
        return response

    def _extract_token(self, request: Request) -> tuple[Optional[str], bool]:
        """Extract authentication token from the request.

        Args:
            request: The HTTP request

        Returns:
            The extracted token, or None if not found
        """
        has_prefix = False
        token = None

        if self.auth_method == "header":
            # Extract from Authorization header
            auth_header = request.headers.get("Authorization") or request.headers.get(
                "authorization"
            )
            if auth_header:
                # Strip "Bearer " prefix if present
                if auth_header.lower().startswith("bearer "):
                    has_prefix = True
                    token = auth_header[7:]
                else:
                    token = auth_header
            else:
                token = None
        elif self.auth_method == "querystring":
            # Extract from query string
            token = request.query_params.get(self.token_param)

        return token, has_prefix


def build_a2a_auth_middleware(
    app_name: str,
    credential_service: VeCredentialService,
    auth_method: Literal["header", "querystring"] = "header",
    token_param: str = "token",
    credential_key: str = "inbound_auth",
    identity_client: Optional[IdentityClient] = None,
) -> type[A2AAuthMiddleware]:
    """Build an A2A authentication middleware class.

    This is a factory function that creates a middleware class with the
    specified configuration. Use this with FastAPI's add_middleware().

    The middleware extracts authentication tokens from incoming requests,
    parses JWT delegation chains, stores credentials, and sets user information
    in the request state for downstream handlers.

    TIP Token Support:
        The middleware will:
        1. Extract TIP token from X-Ve-TIP-Token header
        2. Exchange TIP token for workload token using IdentityClient
        3. Set WorkloadToken object in request.scope["auth"] for downstream use

        If identity_client is not provided, uses the global IdentityClient
        from VeIdentityConfig.

    Args:
        app_name: Application name for credential storage
        credential_service: Credential service to store credentials
        auth_method: Authentication method - "header" or "querystring"
        token_param: Query parameter name for token (when auth_method="querystring")
        credential_key: Key to identify the credential in the store
        identity_client: Optional IdentityClient for TIP token exchange.
            If not provided, uses the global IdentityClient from VeIdentityConfig.

    Returns:
        A configured middleware class

    Request Attributes:
        After successful authentication, the following attributes are set:
        - request.scope["user"]: SimpleUser instance with the user_id from JWT
        - request.scope["auth"]: WorkloadToken object containing workload_access_token

    Examples:
        ```python
        from fastapi import FastAPI, Request
        from veadk.a2a.ve_middlewares import build_a2a_auth_middleware
        from veadk.auth.ve_credential_service  import VeCredentialService
        from veadk.integrations.ve_identity import IdentityClient

        app = FastAPI()
        credential_service = VeCredentialService()

        # Optional: Create identity client for TIP token support
        # If not provided, uses global client from VeIdentityConfig
        identity_client = IdentityClient(region="cn-beijing")

        # Add middleware with TIP token support
        app.add_middleware(
            build_a2a_auth_middleware(
                app_name="my_app",
                credential_service=credential_service,
                auth_method="header",
                identity_client=identity_client,  # Optional, uses global if not provided
            )
        )
        ```
    """

    class ConfiguredA2AAuthMiddleware(A2AAuthMiddleware):
        def __init__(self, app):
            super().__init__(
                app=app,
                app_name=app_name,
                credential_service=credential_service,
                auth_method=auth_method,
                token_param=token_param,
                credential_key=credential_key,
                identity_client=identity_client,
            )

    return ConfiguredA2AAuthMiddleware


class A2ASessionAffinityMiddleware(BaseHTTPMiddleware):
    _PATCHED = False

    def __init__(self, app, upstream_header: str = "x-session-id"):
        super().__init__(app)
        self.upstream_header = upstream_header
        if not A2ASessionAffinityMiddleware._PATCHED:
            self._patch()
            A2ASessionAffinityMiddleware._PATCHED = True

    def _patch(self):
        from a2a.server.apps.jsonrpc.jsonrpc_app import JSONRPCApplication
        from a2a.types import SendStreamingMessageRequest, TaskResubscriptionRequest

        header_name = self.upstream_header
        orig_create_response = JSONRPCApplication._create_response

        async def patched_process_streaming(self_app, request_id, a2a_request, context):
            """pre-extract the first event to get context_id"""
            request_obj = a2a_request.root

            if isinstance(request_obj, SendStreamingMessageRequest):
                gen = self_app.handler.on_message_send_stream(request_obj, context)
            elif isinstance(request_obj, TaskResubscriptionRequest):
                gen = self_app.handler.on_resubscribe_to_task(request_obj, context)
            else:
                return self_app._create_response(context, None)

            # pre-extract the first event
            try:
                first = await gen.__anext__()
            except StopAsyncIteration:
                # empty generator, return empty stream
                async def empty():
                    return
                    yield  # make it a generator

                return self_app._create_response(context, empty())

            # extract context_id
            try:
                ctx_id = getattr(first.root.result, "context_id", None)
                if ctx_id:
                    context.state["_ctx"] = ctx_id
                    logger.info(f"[Affinity] extract context_id: {ctx_id}")
            except Exception as e:
                logger.error(f"[Affinity] extract context_id failed: {e}")

            # re-compose generator
            async def combined():
                yield first
                async for item in gen:
                    yield item

            return self_app._create_response(context, combined())

        def patched_create_response(self_app, context, handler_result):
            """add header"""
            response = orig_create_response(self_app, context, handler_result)

            ctx_id = context.state.get("_ctx")

            # non-streaming: extract from body
            if not ctx_id and hasattr(response, "body"):
                try:
                    ctx_id = (
                        json.loads(response.body).get("result", {}).get("contextId")
                    )
                except Exception:
                    pass

            if ctx_id:
                response.headers[header_name] = ctx_id
                logger.info(f"[Affinity] Header: {ctx_id}")

            return response

        JSONRPCApplication._process_streaming_request = patched_process_streaming
        JSONRPCApplication._create_response = patched_create_response
        logger.info("[Affinity] Patch 完成")

    async def dispatch(self, request, call_next):
        return await call_next(request)


class MCPSessionAffinityMiddleware:
    """MCP session affinity middleware (ASGI level)"""

    def __init__(self, app, upstream_header: str = "x-session-id"):
        self.app = app
        self.upstream_header = upstream_header.lower()
        self.upstream_header_bytes = upstream_header.lower().encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # check if it is a MCP path
        path = scope.get("path", "")
        if not path.startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        # collect request body to extract session_id
        body_parts = []
        session_id = None

        async def receive_wrapper():
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                body_parts.append(body)
            return message

        # read the full request body first
        first_message = await receive()
        if first_message["type"] == "http.request":
            body_parts.append(first_message.get("body", b""))
            # if there is more data
            more_body = first_message.get("more_body", False)
            while more_body:
                msg = await receive()
                if msg["type"] == "http.request":
                    body_parts.append(msg.get("body", b""))
                    more_body = msg.get("more_body", False)
                else:
                    break

        # try to extract session_id from the request body
        full_body = b"".join(body_parts)
        try:
            data = json.loads(full_body)
            # MCP tools/call format: {"method": "tools/call", "params": {"arguments": {"session_id": "..."}}}
            if isinstance(data, dict):
                params = data.get("params", {})
                args = params.get("arguments", {})
                session_id = args.get("session_id")
                if session_id:
                    logger.info(f"[MCP Affinity] extract session_id: {session_id}")
        except Exception as e:
            logger.error(f"[MCP Affinity] parse request body failed: {e}")

        # replay the request body
        body_sent = False

        async def replay_receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": full_body, "more_body": False}
            return await receive()

        # wrap send to inject header
        header_value = session_id.encode() if session_id else None

        async def send_wrapper(message):
            if message["type"] == "http.response.start" and header_value:
                headers = MutableHeaders(raw=list(message.get("headers", [])))
                headers[self.upstream_header] = session_id
                message = {
                    **message,
                    "headers": headers.raw,
                }
                logger.info(f"[MCP Affinity] Header set: {session_id}")
            await send(message)

        await self.app(scope, replay_receive, send_wrapper)
