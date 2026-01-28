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

"""OAuth2 3LO middleware for Starlette/FastAPI with VeIdentity User Pool integration.

This middleware works with any Starlette-based framework, including FastAPI, Starlette,
and other ASGI frameworks built on Starlette.

Quick start with FastAPI (recommended - using VeIdentity User Pool):

    from fastapi import FastAPI
    from veadk.auth.middleware.oauth2_auth import OAuth2Config, setup_oauth2

    app = FastAPI()

    setup_oauth2(
        app,
        OAuth2Config.from_veidentity(
            user_pool_name="my-app",
            client_name="my-app-web",
            redirect_uri="https://myapp.com/oauth2/callback",
        ),
    )

Quick start with Starlette:

    from starlette.applications import Starlette
    from veadk.auth.middleware.oauth2_auth import OAuth2Config, setup_oauth2

    app = Starlette()

    setup_oauth2(
        app,
        OAuth2Config.from_veidentity(
            user_pool_name="my-app",
            client_name="my-app-web",
            redirect_uri="https://myapp.com/oauth2/callback",
        ),
    )

For custom OAuth2 providers:

    setup_oauth2(
        app,
        OAuth2Config(
            authorize_url="https://provider.com/oauth2/authorize",
            token_url="https://provider.com/oauth2/token",
            client_id="your-client-id",
            client_secret="your-client-secret",
            redirect_uri="https://myapp.com/oauth2/callback",
        ),
    )
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import random
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterable, Optional, Protocol, runtime_checkable

import httpx
from pydantic import BaseModel, Field
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from veadk.integrations.ve_identity import IdentityClient

# Maximum cookie size before warning (browsers typically limit to 4KB).
_MAX_COOKIE_SIZE_WARNING = 3800

logger = logging.getLogger(__name__)


def _get_origin_from_url(url: str) -> str:
    """Extract origin (scheme + host + port) from a URL."""
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _get_identity_client() -> "IdentityClient":
    """Get IdentityClient from global config or create new instance."""
    try:
        # Prefer global config for connection pool reuse
        from veadk.config import settings

        return settings.veidentity.get_identity_client()
    except Exception:
        pass

    # Fallback to creating new instance
    try:
        from veadk.integrations.ve_identity import IdentityClient

        return IdentityClient()
    except ImportError as e:
        raise RuntimeError(
            "VeIdentity integration requires veadk.integrations.ve_identity. "
            "Ensure the veadk package is properly installed."
        ) from e


__all__ = [
    # Configuration classes
    "OAuth2Config",
    "UserPoolClientType",
    "OIDCDiscoveryConfig",
    "OAuth2Session",
    "OAuth2RoutePaths",
    # Core handler
    "OAuth2Handler",
    # State store interface and implementations
    "StateStore",
    "InMemoryStateStore",
    # Setup function
    "setup_oauth2",
    # Lower-level functions for manual integration
    "register_oauth2_routes",
    "create_oauth2_middleware",
]


@dataclass(frozen=True)
class OAuth2RoutePaths:
    """Route paths used by the OAuth2 integration."""

    login: str = "/oauth2/login"
    callback: str = "/oauth2/callback"
    logout: str = "/oauth2/logout"
    userinfo: str = "/oauth2/userinfo"

    def all_paths(self) -> set[str]:
        """Return all configured paths as a set."""
        return {self.login, self.callback, self.logout, self.userinfo}


class UserPoolClientType(str, Enum):
    """VeIdentity User Pool client types."""

    WEB_APPLICATION = "WEB_APPLICATION"
    MOBILE_APPLICATION = "MOBILE_APPLICATION"
    SINGLE_PAGE_APPLICATION = "SINGLE_PAGE_APPLICATION"


class OIDCDiscoveryConfig(BaseModel):
    """OIDC Discovery configuration from .well-known/openid-configuration."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: Optional[str] = None
    end_session_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None
    introspection_endpoint: Optional[str] = None
    revocation_endpoint: Optional[str] = None
    scopes_supported: list[str] = Field(default_factory=list)
    response_types_supported: list[str] = Field(default_factory=list)
    grant_types_supported: list[str] = Field(default_factory=list)
    code_challenge_methods_supported: list[str] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


def _fetch_oidc_discovery(
    base_url: str,
    timeout: float = 10.0,
) -> OIDCDiscoveryConfig:
    """Fetch OIDC discovery configuration from .well-known endpoint.

    Args:
        base_url: Base URL of the OIDC provider (e.g., https://domain.com).
        timeout: HTTP request timeout in seconds.

    Returns:
        OIDCDiscoveryConfig with discovered endpoints.

    Raises:
        RuntimeError: If discovery fails.
    """
    import httpx

    discovery_url = f"{base_url}/.well-known/openid-configuration"
    logger.debug("Fetching OIDC discovery from: %s", discovery_url)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(discovery_url)
            response.raise_for_status()
            data = response.json()
            config = OIDCDiscoveryConfig.model_validate(data)
            logger.info(
                "OIDC discovery successful: issuer=%s",
                config.issuer,
            )
            return config
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"OIDC discovery failed: HTTP {e.response.status_code} from {discovery_url}"
        ) from e
    except httpx.RequestError as e:
        raise RuntimeError(f"OIDC discovery failed: {e} for {discovery_url}") from e
    except Exception as e:
        raise RuntimeError(f"OIDC discovery failed: {e}") from e


class OAuth2Config(BaseModel):
    """OAuth2 configuration for 3LO authentication.

    Can be created manually or via `OAuth2Config.from_veidentity()` for VeIdentity
    User Pool integration.

    Example - Manual configuration:
        config = OAuth2Config(
            authorize_url="https://provider.com/oauth2/authorize",
            token_url="https://provider.com/oauth2/token",
            client_id="your-client-id",
            client_secret="your-client-secret",
            redirect_uri="https://myapp.com/oauth2/callback",
        )

    Example - VeIdentity User Pool (recommended):
        config = OAuth2Config.from_veidentity(
            user_pool_name="my-app",
            client_name="my-app-web",
            redirect_uri="https://myapp.com/oauth2/callback",
        )
    """

    # OAuth2 provider endpoints
    authorize_url: str
    token_url: str

    # Client credentials
    client_id: str
    client_secret: Optional[str] = None

    # OAuth2 parameters
    scope: str = "openid profile"
    response_type: str = "code"
    redirect_uri: str
    extra_authorize_params: dict[str, str] = Field(default_factory=dict)
    extra_token_params: dict[str, str] = Field(default_factory=dict)
    use_pkce: bool = False

    # Session + cookie configuration
    session_cookie_name: str = "veadk_session"
    session_timeout_seconds: int = 3600  # 1 hour
    cookie_secure: bool = True
    cookie_samesite: str = "lax"
    cookie_domain: Optional[str] = None
    cookie_path: str = "/"
    cookie_signing_secret: Optional[str] = None

    # User info and logout behavior
    userinfo_url: Optional[str] = None
    end_session_url: Optional[str] = None
    user_id_cookie_name: str = "veadk_user_id"
    user_id_field: str = "sub"
    logout_redirect_url: str = "/"

    # State store behavior
    state_ttl_seconds: int = 300
    state_max_entries: int = 10000

    # HTTP client behavior
    http_timeout_seconds: float = 10.0
    http_max_connections: int = 100
    http_max_keepalive_connections: int = 20

    # Token refresh behavior
    token_refresh_threshold_seconds: int = 300  # Refresh when < 5 min remaining
    auto_refresh_token: bool = True

    # API vs browser behavior
    api_path_prefixes: list[str] = Field(default_factory=lambda: ["/api/"])

    @classmethod
    def from_veidentity(
        cls,
        *,
        user_pool_name: Optional[str] = None,
        user_pool_uid: Optional[str] = None,
        client_name: Optional[str] = None,
        client_uid: Optional[str] = None,
        redirect_uri: str,
        auto_create: bool = True,
        auto_register_callback: bool = True,
        client_type: UserPoolClientType = UserPoolClientType.WEB_APPLICATION,
        web_origin: Optional[str] = None,
        scope: str = "openid profile email",
        identity_client: Optional["IdentityClient"] = None,
        **extra_config: Any,
    ) -> "OAuth2Config":
        """Create OAuth2Config from VeIdentity User Pool (recommended).

        This method automatically:
        - Gets or creates the user pool
        - Gets or creates the user pool client
        - Registers the callback URL
        - Builds the OAuth2Config with correct endpoints

        Args:
            user_pool_name: Name of the VeIdentity user pool (used if user_pool_uid not set).
            user_pool_uid: UID of the VeIdentity user pool (takes precedence over name).
            client_name: Name of the user pool client (used if client_uid not set).
            client_uid: UID of the user pool client (takes precedence over name).
            redirect_uri: OAuth2 callback URL (e.g., https://myapp.com/oauth2/callback).
            auto_create: Create user pool and client if not found (default: True).
            auto_register_callback: Register callback URL with client (default: True).
            client_type: Client type for new clients (default: WEB_APPLICATION).
            web_origin: Web origin for CORS. Auto-detected from redirect_uri if not set.
            scope: OAuth2 scopes to request (default: "openid profile email").
            identity_client: Custom IdentityClient instance. Uses global config if not provided.
            **extra_config: Additional OAuth2Config options (e.g., cookie_secure=False).

        Returns:
            Configured OAuth2Config instance.

        Raises:
            ValueError: If user pool or client not found and auto_create=False.
            RuntimeError: If VeIdentity module is not available.

        Example:
            # Auto-create resources by name
            config = OAuth2Config.from_veidentity(
                user_pool_name="my-app",
                client_name="my-app-web",
                redirect_uri="https://myapp.com/oauth2/callback",
            )

            # Use existing resources by UID
            config = OAuth2Config.from_veidentity(
                user_pool_uid="pool-xxxx",
                client_uid="client-xxxx",
                redirect_uri="https://myapp.com/oauth2/callback",
                auto_create=False,
            )

            # With extra config options
            config = OAuth2Config.from_veidentity(
                user_pool_name="my-app",
                client_name="my-app-web",
                redirect_uri="http://localhost:8000/oauth2/callback",
                cookie_secure=False,  # For local development
                api_path_prefixes=["/api/", "/graphql"],
            )
        """
        # Validate inputs
        if not user_pool_name and not user_pool_uid:
            raise ValueError("Either user_pool_name or user_pool_uid must be provided")
        if not client_name and not client_uid:
            raise ValueError("Either client_name or client_uid must be provided")

        # Get or create IdentityClient
        if identity_client is None:
            identity_client = _get_identity_client()

        # Step 1: Get or create user pool
        user_pool = identity_client.get_user_pool(
            name=user_pool_name, uid=user_pool_uid
        )
        if user_pool:
            user_pool_id, user_pool_domain = user_pool
            logger.info(
                "Using existing user pool: %s",
                user_pool_uid or user_pool_name,
            )
        elif auto_create and user_pool_name:
            user_pool_id, user_pool_domain = identity_client.create_user_pool(
                name=user_pool_name
            )
            logger.info(
                "Created user pool: %s (domain: %s)", user_pool_name, user_pool_domain
            )
        else:
            identifier = user_pool_uid or user_pool_name
            raise ValueError(
                f"User pool '{identifier}' not found (auto_create=False or only UID provided)"
            )

        # Step 2: Get or create client
        client = identity_client.get_user_pool_client(
            user_pool_uid=user_pool_id,
            name=client_name,
            client_uid=client_uid,
        )
        if client:
            resolved_client_id, client_secret = client
            logger.info("Using existing client: %s", client_uid or client_name)
        elif auto_create and client_name:
            client_type_value = (
                client_type.value
                if isinstance(client_type, UserPoolClientType)
                else client_type
            )
            resolved_client_id, client_secret = identity_client.create_user_pool_client(
                user_pool_uid=user_pool_id,
                name=client_name,
                client_type=client_type_value,
            )
            logger.info("Created client: %s", client_name)
        else:
            identifier = client_uid or client_name
            raise ValueError(
                f"Client '{identifier}' not found (auto_create=False or only UID provided)"
            )

        # Step 3: Register callback URL
        if auto_register_callback:
            detected_origin = _get_origin_from_url(redirect_uri)
            callback_origin = web_origin or detected_origin
            try:
                identity_client.register_callback_for_user_pool_client(
                    user_pool_uid=user_pool_id,
                    client_uid=resolved_client_id,
                    callback_url=redirect_uri,
                    web_origin=callback_origin,
                )
                logger.info("Registered callback: %s", redirect_uri)
            except Exception as e:
                logger.warning("Callback registration skipped (may exist): %s", e)

        # Step 4: Fetch OIDC discovery configuration
        base_url = f"https://{user_pool_domain}"
        oidc_config = _fetch_oidc_discovery(base_url)

        # Step 5: Build OAuth2Config from discovered endpoints
        return cls(
            authorize_url=oidc_config.authorization_endpoint,
            token_url=oidc_config.token_endpoint,
            userinfo_url=oidc_config.userinfo_endpoint,
            end_session_url=oidc_config.end_session_endpoint,
            client_id=resolved_client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            cookie_signing_secret=extra_config.pop(
                "cookie_signing_secret", client_secret
            ),
            **extra_config,
        )


class OAuth2Session(BaseModel):
    """OAuth2 session data stored in cookies."""

    access_token: str
    token_type: str = "Bearer"
    expires_at: float
    refresh_token: Optional[str] = None
    user_info: Optional[dict[str, Any]] = None

    def is_expired(self) -> bool:
        """Check if the access token is expired."""
        return time.time() >= self.expires_at

    def is_refresh_needed(self, threshold_seconds: int = 300) -> bool:
        """Check if token refresh is needed (expires within threshold)."""
        return time.time() >= (self.expires_at - threshold_seconds)

    def can_refresh(self) -> bool:
        """Check if this session has a refresh token available."""
        return bool(self.refresh_token)

    def time_until_expiry(self) -> float:
        """Return seconds until token expires (negative if expired)."""
        return self.expires_at - time.time()

    def to_authorization_header(self) -> str:
        """Convert to Authorization header value."""
        return f"{self.token_type} {self.access_token}"


@runtime_checkable
class StateStore(Protocol):
    """Protocol for OAuth2 state storage backends.

    Implement this protocol to provide custom state storage (e.g., Redis, database).

    Example Redis implementation:
        class RedisStateStore:
            def __init__(self, redis_client, ttl_seconds: int = 300):
                self._redis = redis_client
                self._ttl = ttl_seconds

            def create_state(
                self, redirect_after_auth: str = "/", code_verifier: Optional[str] = None
            ) -> str:
                state = secrets.token_urlsafe(32)
                data = json.dumps({
                    "redirect_after_auth": redirect_after_auth,
                    "code_verifier": code_verifier,
                })
                self._redis.setex(f"oauth2_state:{state}", self._ttl, data)
                return state

            def validate_and_consume_state(self, state: str) -> Optional[dict[str, Any]]:
                key = f"oauth2_state:{state}"
                data = self._redis.get(key)
                if not data:
                    return None
                self._redis.delete(key)
                return json.loads(data)
    """

    def create_state(
        self, redirect_after_auth: str = "/", code_verifier: Optional[str] = None
    ) -> str:
        """Create and store a new OAuth2 state parameter."""
        ...

    def validate_and_consume_state(self, state: str) -> Optional[dict[str, Any]]:
        """Validate, consume and return state data. Returns None if invalid/expired."""
        ...


class InMemoryStateStore:
    """In-memory store for OAuth2 state parameters.

    Suitable for single-process deployments. For multi-process or distributed
    deployments, implement the StateStore protocol with Redis or a database.
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        max_entries: int = 10000,
        prune_probability: float = 0.01,
    ) -> None:
        self._states: dict[str, dict[str, Any]] = {}
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._prune_probability = prune_probability

    def create_state(
        self, redirect_after_auth: str = "/", code_verifier: Optional[str] = None
    ) -> str:
        """Create a new OAuth2 state parameter."""
        # Probabilistic pruning to avoid performance hit on every call.
        if random.random() < self._prune_probability:
            self._prune_expired()

        if len(self._states) >= self._max_entries:
            self._prune_oldest()

        state = secrets.token_urlsafe(32)
        self._states[state] = {
            "created_at": time.time(),
            "redirect_after_auth": redirect_after_auth,
            "code_verifier": code_verifier,
        }
        return state

    def validate_and_consume_state(self, state: str) -> Optional[dict[str, Any]]:
        """Validate and consume an OAuth2 state parameter."""
        state_data = self._states.pop(state, None)
        if not state_data:
            return None

        if time.time() - state_data["created_at"] > self._ttl_seconds:
            return None

        return state_data

    def _prune_expired(self) -> None:
        """Remove expired states to keep memory bounded."""
        now = time.time()
        expired_keys = [
            key
            for key, value in self._states.items()
            if now - value["created_at"] > self._ttl_seconds
        ]
        for key in expired_keys:
            self._states.pop(key, None)

    def _prune_oldest(self) -> None:
        """Remove the oldest states when size limit is reached."""
        if len(self._states) <= self._max_entries:
            return

        items = sorted(self._states.items(), key=lambda item: item[1]["created_at"])
        to_remove = len(self._states) - self._max_entries
        for key, _ in items[:to_remove]:
            self._states.pop(key, None)


class OAuth2Handler:
    """Handles OAuth2 authentication flow for Starlette/FastAPI apps."""

    def __init__(
        self,
        config: OAuth2Config,
        state_store: Optional[StateStore] = None,
    ):
        self.config = config
        self.state_store: StateStore = state_store or InMemoryStateStore(
            ttl_seconds=config.state_ttl_seconds,
            max_entries=config.state_max_entries,
        )
        # Configure HTTP client with connection pool limits.
        limits = httpx.Limits(
            max_keepalive_connections=config.http_max_keepalive_connections,
            max_connections=config.http_max_connections,
        )
        self._http_client = httpx.AsyncClient(
            timeout=config.http_timeout_seconds,
            limits=limits,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http_client.aclose()

    def build_authorization_request(self, redirect_after_auth: str) -> tuple[str, str]:
        """Create state and authorization URL for a redirect."""
        code_verifier = self._generate_code_verifier() if self.config.use_pkce else None
        state = self.state_store.create_state(
            redirect_after_auth=redirect_after_auth,
            code_verifier=code_verifier,
        )
        auth_url = self.get_authorization_url(state, code_verifier=code_verifier)
        return state, auth_url

    def get_authorization_url(
        self, state: str, code_verifier: Optional[str] = None
    ) -> str:
        """Generate the OAuth2 authorization URL."""
        params = {
            "response_type": self.config.response_type,
            "client_id": self.config.client_id,
            "scope": self.config.scope,
            "redirect_uri": self.config.redirect_uri,
            "state": state,
        }

        if self.config.use_pkce:
            if not code_verifier:
                raise HTTPException(
                    status_code=400, detail="Missing PKCE code verifier"
                )
            params["code_challenge"] = self._build_code_challenge(code_verifier)
            params["code_challenge_method"] = "S256"

        params.update(self.config.extra_authorize_params)
        return f"{self.config.authorize_url}?{urllib.parse.urlencode(params)}"

    async def exchange_code_for_token(
        self, code: str, code_verifier: Optional[str] = None
    ) -> OAuth2Session:
        """Exchange authorization code for access token."""
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
        }

        if self.config.use_pkce:
            if not code_verifier:
                raise HTTPException(
                    status_code=400, detail="Missing PKCE code verifier"
                )
            token_data["code_verifier"] = code_verifier

        token_data.update(self.config.extra_token_params)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        # Use Basic Auth for client credentials when possible.
        if self.config.client_secret:
            credentials = f"{self.config.client_id}:{self.config.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded_credentials}"
        else:
            # Fallback to client_id in form data for public clients.
            token_data["client_id"] = self.config.client_id

        try:
            response = await self._http_client.post(
                self.config.token_url,
                data=token_data,
                headers=headers,
            )
            response.raise_for_status()

            try:
                token_response = response.json()
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Token response is not valid JSON",
                ) from exc

            if "access_token" not in token_response:
                raise HTTPException(
                    status_code=400,
                    detail="Token response missing access_token",
                )

            expires_in = token_response.get("expires_in", 3600)
            try:
                expires_in = int(expires_in)
            except (TypeError, ValueError):
                expires_in = 3600

            expires_at = time.time() + max(0, expires_in)

            session = OAuth2Session(
                access_token=token_response["access_token"],
                token_type=token_response.get("token_type", "Bearer"),
                expires_at=expires_at,
                refresh_token=token_response.get("refresh_token"),
            )

            if self.config.userinfo_url:
                try:
                    user_info = await self._fetch_user_info(session.access_token)
                    session.user_info = user_info
                    logger.info(
                        "Successfully fetched user info for user: %s",
                        user_info.get("sub")
                        or user_info.get("email")
                        or user_info.get("id")
                        or "unknown",
                    )
                except Exception as e:
                    logger.warning("Failed to fetch user info: %s", e)
                    # Continue without user info.

            return session

        except httpx.HTTPStatusError as e:
            logger.error("Token exchange failed: %s", e.response.text)
            raise HTTPException(
                status_code=400,
                detail=f"Token exchange failed: {e.response.text}",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Token exchange error: %s", e)
            raise HTTPException(status_code=500, detail="Authentication failed")

    async def refresh_access_token(
        self, session: OAuth2Session
    ) -> Optional[OAuth2Session]:
        """Refresh the access token using the refresh token.

        Returns a new OAuth2Session with updated tokens, or None if refresh fails.
        The original session's user_info is preserved in the new session.
        """
        if not session.refresh_token:
            logger.debug("Cannot refresh: no refresh_token available")
            return None

        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": session.refresh_token,
        }
        token_data.update(self.config.extra_token_params)

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        # Use Basic Auth for client credentials when possible.
        if self.config.client_secret:
            credentials = f"{self.config.client_id}:{self.config.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded_credentials}"
        else:
            token_data["client_id"] = self.config.client_id

        try:
            response = await self._http_client.post(
                self.config.token_url,
                data=token_data,
                headers=headers,
            )
            response.raise_for_status()

            token_response = response.json()

            if "access_token" not in token_response:
                logger.warning("Token refresh response missing access_token")
                return None

            expires_in = token_response.get("expires_in", 3600)
            try:
                expires_in = int(expires_in)
            except (TypeError, ValueError):
                expires_in = 3600

            expires_at = time.time() + max(0, expires_in)

            # Create new session with refreshed tokens, preserving user_info.
            new_session = OAuth2Session(
                access_token=token_response["access_token"],
                token_type=token_response.get("token_type", "Bearer"),
                expires_at=expires_at,
                # Use new refresh_token if provided, otherwise keep the old one.
                refresh_token=token_response.get(
                    "refresh_token", session.refresh_token
                ),
                user_info=session.user_info,
            )

            logger.info(
                "Successfully refreshed access token, new expiry in %d seconds",
                expires_in,
            )
            return new_session

        except httpx.HTTPStatusError as e:
            logger.warning("Token refresh failed: %s", e.response.text)
            return None
        except Exception as e:
            logger.warning("Token refresh error: %s", e)
            return None

    async def _fetch_user_info(self, access_token: str) -> dict[str, Any]:
        """Fetch user information from the userinfo endpoint."""
        if not self.config.userinfo_url:
            raise ValueError("userinfo_url not configured")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            response = await self._http_client.get(
                self.config.userinfo_url,
                headers=headers,
            )
            response.raise_for_status()

            user_info = response.json()
            logger.debug("Fetched user info: %s", user_info)
            return user_info

        except httpx.HTTPStatusError as e:
            logger.error("User info fetch failed: %s", e.response.text)
            raise Exception(f"User info fetch failed: {e.response.text}")
        except Exception as e:
            logger.error("User info fetch error: %s", e)
            raise Exception(f"User info fetch error: {e}")

    def encode_session(self, session: OAuth2Session) -> str:
        """Encode OAuth2 session data for cookie storage.

        Warns if the encoded session exceeds the recommended cookie size limit.
        """
        session_json = session.model_dump_json()
        payload = self._base64url_encode(session_json.encode("utf-8"))
        signing_key = self._get_cookie_signing_key()

        if not signing_key:
            encoded = payload
        else:
            signature = hmac.new(
                signing_key, payload.encode("ascii"), hashlib.sha256
            ).digest()
            signature_text = self._base64url_encode(signature)
            encoded = f"{payload}.{signature_text}"

        # Warn if cookie size approaches browser limits.
        if len(encoded) > _MAX_COOKIE_SIZE_WARNING:
            logger.warning(
                "Session cookie size (%d bytes) approaching 4KB browser limit. "
                "Consider reducing user_info stored in session or using server-side sessions.",
                len(encoded),
            )

        return encoded

    def decode_session(self, encoded_session: str) -> Optional[OAuth2Session]:
        """Decode OAuth2 session data from cookie."""
        try:
            signing_key = self._get_cookie_signing_key()

            if "." in encoded_session:
                payload, signature = encoded_session.split(".", 1)
                if not signing_key:
                    logger.warning("Signed session cookie rejected without signing key")
                    return None
                expected = hmac.new(
                    signing_key, payload.encode("ascii"), hashlib.sha256
                ).digest()
                expected_signature = self._base64url_encode(expected)
                if not hmac.compare_digest(signature, expected_signature):
                    logger.warning("Session signature mismatch")
                    return None
            else:
                payload = encoded_session
                if signing_key:
                    logger.warning("Unsigned session cookie rejected")
                    return None

            session_bytes = self._base64url_decode(payload)
            session_json = session_bytes.decode("utf-8")
            session_data = json.loads(session_json)
            return OAuth2Session.model_validate(session_data)
        except Exception as e:
            logger.warning("Failed to decode session: %s", e)
            return None

    def get_session_from_request(self, request: Request) -> Optional[OAuth2Session]:
        """Extract OAuth2 session from request cookies."""
        session_cookie = request.cookies.get(self.config.session_cookie_name)
        if not session_cookie:
            return None

        session = self.decode_session(session_cookie)
        if not session or session.is_expired():
            return None

        return session

    def create_session_cookie(self, session: OAuth2Session) -> dict[str, Any]:
        """Create session cookie parameters."""
        encoded_session = self.encode_session(session)
        max_age = self._session_cookie_max_age(session)

        return {
            "key": self.config.session_cookie_name,
            "value": encoded_session,
            "max_age": max_age,
            "httponly": True,
            "secure": self.config.cookie_secure,
            "samesite": self.config.cookie_samesite,
            "domain": self.config.cookie_domain,
            "path": self.config.cookie_path,
        }

    def create_user_id_cookie(self, session: OAuth2Session) -> Optional[dict[str, Any]]:
        """Create user ID cookie for frontend access (non-HTTP-only)."""
        if not session.user_info:
            return None

        user_id = session.user_info.get(self.config.user_id_field)
        if not user_id:
            user_id = session.user_info.get("sub") or session.user_info.get("email")
        if not user_id:
            return None

        return {
            "key": self.config.user_id_cookie_name,
            "value": str(user_id),
            "max_age": self._session_cookie_max_age(session),
            "httponly": False,
            "secure": self.config.cookie_secure,
            "samesite": self.config.cookie_samesite,
            "domain": self.config.cookie_domain,
            "path": self.config.cookie_path,
        }

    def _session_cookie_max_age(self, session: OAuth2Session) -> int:
        token_ttl = max(0, int(session.expires_at - time.time()))
        if self.config.session_timeout_seconds <= 0:
            return token_ttl
        return min(self.config.session_timeout_seconds, token_ttl)

    def _get_cookie_signing_key(self) -> Optional[bytes]:
        # Fall back to client_secret when a dedicated signing secret is not provided.
        secret = self.config.cookie_signing_secret or self.config.client_secret
        if not secret:
            return None
        return secret.encode("utf-8")

    @staticmethod
    def _base64url_encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    @staticmethod
    def _base64url_decode(data: str) -> bytes:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding)

    @staticmethod
    def _generate_code_verifier() -> str:
        return OAuth2Handler._base64url_encode(secrets.token_bytes(32))

    @staticmethod
    def _build_code_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return OAuth2Handler._base64url_encode(digest)


def _resolve_redirect_after_auth(request: Request, redirect: Optional[str]) -> str:
    """Resolve a safe redirect URL after login."""
    if not redirect:
        return "/"

    redirect = redirect.strip()
    if redirect.startswith("/"):
        return redirect

    parsed = urllib.parse.urlparse(redirect)
    if not parsed.scheme and not parsed.netloc:
        return f"/{redirect.lstrip('/')}"

    current = urllib.parse.urlparse(str(request.url))
    if parsed.scheme == current.scheme and parsed.netloc == current.netloc:
        return redirect

    logger.warning("Unsafe redirect ignored: %s", redirect)
    return "/"


def register_oauth2_routes(
    app: Starlette,
    oauth2_handler: OAuth2Handler,
    *,
    routes: Optional[OAuth2RoutePaths] = None,
) -> OAuth2RoutePaths:
    """Register OAuth2 callback/login/logout/userinfo routes.

    Works with both Starlette and FastAPI applications.

    Args:
        app: The Starlette or FastAPI application instance.
        oauth2_handler: The OAuth2Handler instance.
        routes: Custom route paths (defaults to /oauth2/*).

    Returns:
        The OAuth2RoutePaths used for registration.
    """
    routes = routes or OAuth2RoutePaths()

    async def oauth2_login(request: Request) -> RedirectResponse:
        """Start the OAuth2 authorization flow."""
        redirect = request.query_params.get("redirect")
        redirect_after_auth = _resolve_redirect_after_auth(request, redirect)
        _, auth_url = oauth2_handler.build_authorization_request(redirect_after_auth)
        return RedirectResponse(url=auth_url, status_code=302)

    async def oauth2_callback(request: Request) -> RedirectResponse:
        """Handle OAuth2 authorization callback."""
        params = request.query_params
        error = params.get("error")
        error_description = params.get("error_description")
        code = params.get("code")
        state = params.get("state")

        if error:
            detail = error_description or error
            raise HTTPException(
                status_code=400, detail=f"OAuth2 authorization failed: {detail}"
            )

        if not code or not state:
            raise HTTPException(
                status_code=400, detail="Missing authorization code or state"
            )

        # Validate and consume the state to prevent replay attacks.
        state_data = oauth2_handler.state_store.validate_and_consume_state(state)
        if not state_data:
            raise HTTPException(
                status_code=400, detail="Invalid or expired state parameter"
            )

        try:
            session = await oauth2_handler.exchange_code_for_token(
                code,
                code_verifier=state_data.get("code_verifier"),
            )

            # Create session cookie for subsequent requests.
            session_cookie_params = oauth2_handler.create_session_cookie(session)

            redirect_url = state_data.get("redirect_after_auth") or "/"
            response = RedirectResponse(url=redirect_url, status_code=302)
            response.set_cookie(**session_cookie_params)

            # Set user ID cookie for frontend access (if user info available).
            user_id_cookie_params = oauth2_handler.create_user_id_cookie(session)
            if user_id_cookie_params:
                response.set_cookie(**user_id_cookie_params)
                logger.info(
                    "Set user ID cookie for user: %s",
                    user_id_cookie_params["value"],
                )

            return response

        except HTTPException:
            raise
        except Exception as e:
            logger.error("OAuth2 callback error: %s", e)
            raise HTTPException(status_code=500, detail="Authentication failed")

    async def oauth2_logout(request: Request) -> RedirectResponse:
        """Logout and clear session cookies."""
        # Determine logout redirect URL
        config = oauth2_handler.config
        if config.end_session_url:
            # Use OAuth2 provider's logout endpoint with post_logout redirect
            logout_url = (
                f"{config.end_session_url}?"
                f"post_logout_redirect_uri={urllib.parse.quote(config.logout_redirect_url)}&"
                f"client_id={config.client_id}"
            )
        else:
            logout_url = config.logout_redirect_url

        response = RedirectResponse(url=logout_url, status_code=302)
        response.delete_cookie(
            config.session_cookie_name,
            domain=config.cookie_domain,
            path=config.cookie_path,
        )
        response.delete_cookie(
            config.user_id_cookie_name,
            domain=config.cookie_domain,
            path=config.cookie_path,
        )
        logger.info("User logged out, cleared session and user ID cookies")
        return response

    async def get_current_user_info(request: Request) -> JSONResponse:
        """Get current user information from OAuth2 session."""
        session = oauth2_handler.get_session_from_request(request)

        if not session or session.is_expired():
            raise HTTPException(status_code=401, detail="Not authenticated")

        if not session.user_info:
            if oauth2_handler.config.userinfo_url:
                try:
                    user_info = await oauth2_handler._fetch_user_info(
                        session.access_token
                    )
                    session.user_info = user_info

                    session_cookie_params = oauth2_handler.create_session_cookie(
                        session
                    )
                    response = JSONResponse(content=user_info)
                    response.set_cookie(**session_cookie_params)

                    user_id_cookie_params = oauth2_handler.create_user_id_cookie(
                        session
                    )
                    if user_id_cookie_params:
                        response.set_cookie(**user_id_cookie_params)

                    return response
                except Exception as e:
                    logger.error("Failed to fetch user info: %s", e)
                    raise HTTPException(
                        status_code=500, detail="Failed to fetch user info"
                    )

            return JSONResponse(
                content={
                    "message": "User info not available",
                    "reason": "userinfo_url not configured",
                }
            )

        return JSONResponse(content=session.user_info)

    # Register routes using Starlette's Route objects (works with both Starlette and FastAPI)
    oauth2_routes = [
        Route(routes.login, oauth2_login, methods=["GET"]),
        Route(routes.callback, oauth2_callback, methods=["GET"]),
        Route(routes.logout, oauth2_logout, methods=["GET"]),
        Route(routes.userinfo, get_current_user_info, methods=["GET"]),
    ]
    app.routes.extend(oauth2_routes)

    return routes


def setup_oauth2(
    app: Starlette,
    config: OAuth2Config,
    *,
    routes: Optional[OAuth2RoutePaths] = None,
    exempt_paths: Optional[Iterable[str]] = None,
    exempt_prefixes: Optional[Iterable[str]] = None,
    state_store: Optional[StateStore] = None,
) -> OAuth2Handler:
    """Install OAuth2 routes, middleware, and shutdown hook.

    Works with both Starlette and FastAPI applications.

    Example with VeIdentity User Pool (recommended):
        setup_oauth2(
            app,
            OAuth2Config.from_veidentity(
                user_pool_name="my-app",
                client_name="my-app-web",
                redirect_uri="https://myapp.com/oauth2/callback",
            ),
        )

    Example with custom OAuth2 provider:
        setup_oauth2(
            app,
            OAuth2Config(
                authorize_url="https://provider.com/oauth2/authorize",
                token_url="https://provider.com/oauth2/token",
                client_id="...",
                client_secret="...",
                redirect_uri="https://myapp.com/oauth2/callback",
            ),
        )

    Args:
        app: The Starlette or FastAPI application instance.
        config: OAuth2 configuration. Use OAuth2Config.from_veidentity() for VeIdentity.
        routes: Custom route paths (defaults to /oauth2/*).
        exempt_paths: Paths that skip authentication (exact match).
        exempt_prefixes: Path prefixes that skip authentication.
        state_store: Custom state store for distributed deployments.

    Returns:
        The OAuth2Handler instance, also available at app.state.oauth2_handler.
    """
    oauth2_handler = OAuth2Handler(config, state_store=state_store)
    route_paths = register_oauth2_routes(app, oauth2_handler, routes=routes)

    merged_exempt_paths = set(route_paths.all_paths())
    if exempt_paths:
        merged_exempt_paths.update(exempt_paths)

    app.add_middleware(
        BaseHTTPMiddleware,
        dispatch=create_oauth2_middleware(
            oauth2_handler,
            exempt_paths=merged_exempt_paths,
            exempt_prefixes=exempt_prefixes,
        ),
    )

    if hasattr(app, "add_event_handler"):
        app.add_event_handler("shutdown", oauth2_handler.close)
    if hasattr(app, "state"):
        app.state.oauth2_handler = oauth2_handler

    return oauth2_handler


def _is_api_request(request: Request, api_prefixes: list[str]) -> bool:
    """Determine if a request is an API request (should get 401, not redirect)."""
    # Check Accept header for JSON preference.
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return True

    # Check configured API path prefixes.
    path = request.url.path
    for prefix in api_prefixes:
        if path.startswith(prefix):
            return True

    # Check X-Requested-With header (common for AJAX requests).
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        return True

    return False


def create_oauth2_middleware(
    oauth2_handler: OAuth2Handler,
    *,
    exempt_paths: Optional[Iterable[str]] = None,
    exempt_prefixes: Optional[Iterable[str]] = None,
    allow_existing_authorization: bool = True,
):
    """Create OAuth2 authentication middleware for Starlette/FastAPI.

    The middleware:
    - Skips authentication for exempt paths/prefixes and OPTIONS requests.
    - Passes through requests that already have an Authorization header.
    - Injects the OAuth2 access token as an Authorization header for valid sessions.
    - Auto-refreshes tokens when they are close to expiry (if configured).
    - Returns 401 JSON for API requests, redirects browsers to login for others.
    """
    exempt_paths_set = set(exempt_paths or [])
    exempt_prefixes_tuple = tuple(exempt_prefixes or [])
    config = oauth2_handler.config

    async def oauth2_middleware(request: Request, call_next):
        """OAuth2 authentication middleware."""
        path = request.url.path

        # Allow preflight requests and explicitly exempted paths.
        if request.method == "OPTIONS":
            return await call_next(request)
        if path in exempt_paths_set or any(
            path.startswith(prefix) for prefix in exempt_prefixes_tuple
        ):
            return await call_next(request)

        # Pass through if there's already an Authorization header.
        if allow_existing_authorization and "authorization" in request.headers:
            return await call_next(request)

        session = oauth2_handler.get_session_from_request(request)
        response_cookies: list[dict[str, Any]] = []

        # Attempt token refresh if session is close to expiry.
        if session and not session.is_expired():
            if (
                config.auto_refresh_token
                and session.can_refresh()
                and session.is_refresh_needed(config.token_refresh_threshold_seconds)
            ):
                logger.debug(
                    "Token expires in %.0f seconds, attempting refresh",
                    session.time_until_expiry(),
                )
                refreshed = await oauth2_handler.refresh_access_token(session)
                if refreshed:
                    session = refreshed
                    # Queue cookies to be set on the response.
                    response_cookies.append(
                        oauth2_handler.create_session_cookie(session)
                    )
                    user_id_cookie = oauth2_handler.create_user_id_cookie(session)
                    if user_id_cookie:
                        response_cookies.append(user_id_cookie)

        if session and not session.is_expired():
            auth_header_value = session.to_authorization_header().encode()

            # Update the scope headers so downstream dependencies can read it.
            headers = list(request.scope.get("headers", []))
            headers = [
                (name, value)
                for name, value in headers
                if name.lower() != b"authorization"
            ]
            headers.append((b"authorization", auth_header_value))
            request.scope["headers"] = headers

            logger.debug(
                "Added Authorization header to request: %s...",
                session.to_authorization_header()[:20],
            )

            response = await call_next(request)

            # Set any refreshed session cookies on the response.
            for cookie_params in response_cookies:
                response.set_cookie(**cookie_params)

            return response

        # No valid session - handle API vs browser requests differently.
        if _is_api_request(request, config.api_path_prefixes):
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Browser request: redirect to OAuth2 authorization.
        _, auth_url = oauth2_handler.build_authorization_request(str(request.url))
        return RedirectResponse(url=auth_url, status_code=302)

    return oauth2_middleware
