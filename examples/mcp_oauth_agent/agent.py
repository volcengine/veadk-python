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

"""Agent whose MCP tool is protected by ADK-native OAuth (OIDC).

Some MCP servers enforce inbound auth: a `tools/call` returns 401 unless an
`Authorization: Bearer <token>` from an OAuth/OIDC provider is present. Instead
of any provider-specific SDK, this uses google-adk's built-in OAuth2 handling —
give the toolset an OpenID Connect scheme plus client credentials and, on the
first tool call, ADK emits an `adk_request_credential` event carrying an
authorize URL. The web UI (`veadk frontend`) renders an authorization card; the
user logs in at the provider; ADK exchanges the returned code for a token and
replays the call with the bearer header. No extra client code is required.

Configure via environment variables (e.g. in a `.env` file):

    MCP_OAUTH_URL       the MCP server URL (StreamableHTTP), including any path
    OIDC_ISSUER         the provider's issuer, e.g. https://<pool>.../  — the
                        authorize/token endpoints are derived from it, or set
                        them explicitly with the two vars below
    OIDC_AUTHORIZATION_ENDPOINT   (optional) overrides "<issuer>/authorize"
    OIDC_TOKEN_ENDPOINT           (optional) overrides "<issuer>/oauth/token"
    OIDC_SCOPES         (optional) space-separated, default "openid profile email"
    OIDC_CLIENT_ID      OAuth client id registered with the provider
    OIDC_CLIENT_SECRET  its client secret
    OIDC_REDIRECT_URI   a redirect URI registered on that client; default
                        http://localhost:8000/ — where `veadk frontend` serves
                        the UI — so the popup captures the ?code=... callback on
                        its own origin (use http://localhost:5173/ with `--dev`)
"""

import os

from google.adk.auth import AuthCredential, AuthCredentialTypes
from google.adk.auth.auth_credential import OAuth2Auth
from google.adk.auth.auth_schemes import OpenIdConnectWithConfig
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from veadk import Agent

_issuer = os.getenv("OIDC_ISSUER", "").rstrip("/")
_auth_endpoint = os.getenv("OIDC_AUTHORIZATION_ENDPOINT") or f"{_issuer}/authorize"
_token_endpoint = os.getenv("OIDC_TOKEN_ENDPOINT") or f"{_issuer}/oauth/token"
_scopes = os.getenv("OIDC_SCOPES", "openid profile email").split()

auth_scheme = OpenIdConnectWithConfig(
    authorization_endpoint=_auth_endpoint,
    token_endpoint=_token_endpoint,
    scopes=_scopes,
)

auth_credential = AuthCredential(
    auth_type=AuthCredentialTypes.OPEN_ID_CONNECT,
    oauth2=OAuth2Auth(
        client_id=os.getenv("OIDC_CLIENT_ID", ""),
        client_secret=os.getenv("OIDC_CLIENT_SECRET", ""),
        redirect_uri=os.getenv("OIDC_REDIRECT_URI", "http://localhost:8000/"),
    ),
)

mcp_tool = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=os.getenv("MCP_OAUTH_URL", "")
    ),
    auth_scheme=auth_scheme,
    auth_credential=auth_credential,
)

agent = Agent(
    name="mcp_oauth_agent",
    description="An agent whose MCP tool is protected by ADK-native OAuth (OIDC).",
    instruction=(
        "You can call the connected MCP tools to help the user. Call the "
        "relevant tool directly to obtain real results; do not ask the user "
        "whether they are authorized — the authorization flow is started "
        "automatically when a tool requires it."
    ),
    tools=[mcp_tool],
)

root_agent = agent
