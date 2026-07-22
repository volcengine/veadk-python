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

"""`veadk frontend` -- serve the A2UI web UI together with the agent API server.

This is a self-contained launcher built on Google ADK's supported
`get_fast_api_app`. In the default mode it serves both the agent API
(`/list-apps`, `/run_sse`, sessions, ...) and the built React UI from a single
process, so there is no cross-origin setup. In `--vite` mode it serves only the
API (with CORS allowing the Vite dev server) for React hot reload. `--dev` is a
separate toggle: it sources the agent picker from local agents instead of cloud
runtimes (the UI is still served).
"""

import asyncio
import json
import os
import re
import sys

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import click

from veadk.cli.frontend_branding import normalize_site_title, resolve_site_logo
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_BUILD_ERROR_MARKERS = (
    "no solution found",
    "unsatisfiable",
    "failed to solve",
    "did not complete successfully",
    "no matching distribution",
    "modulenotfounderror",
    "command not found",
    "permission denied",
    "traceback (most recent call last)",
)
_SENSITIVE_LOG_PATTERNS = (
    re.compile(r"authorization\s*[:=]", re.IGNORECASE),
    re.compile(r"\bbearer\s+\S+", re.IGNORECASE),
    re.compile(
        r"(?:access[_ -]?key(?:[_ -]?id)?|secret[_ -]?key|api[_ -]?key|"
        r"client[_ -]?secret|private[_ -]?key|(?:access|session|security|refresh|"
        r"id|jwt|cr)[_ -]?token|password|credential|signature)"
        r"\s*(?:=|:|\s)\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\."
        r"[A-Za-z0-9_-]{10,}\b"
    ),
)


def _extract_build_error_excerpt(
    lines: Iterable[object] | str, max_lines: int = 30
) -> str:
    """Return a credential-safe excerpt around high-signal build errors."""
    if max_lines <= 0:
        return ""
    raw_lines = lines.splitlines() if isinstance(lines, str) else lines
    clean_lines = []
    for raw_line in raw_lines:
        line = _ANSI_ESCAPE_RE.sub("", str(raw_line)).strip()
        if not line or any(pattern.search(line) for pattern in _SENSITIVE_LOG_PATTERNS):
            continue
        clean_lines.append(line[:1000])

    error_indexes = [
        index
        for index, line in enumerate(clean_lines)
        if any(marker in line.lower() for marker in _BUILD_ERROR_MARKERS)
    ]
    if not error_indexes:
        return ""

    selected_indexes = set()
    for index in error_indexes:
        selected_indexes.update(
            range(max(0, index - 3), min(len(clean_lines), index + 4))
        )
    return "\n".join(
        clean_lines[index] for index in sorted(selected_indexes)[:max_lines]
    )


def _redact_debug_text(text: str) -> str:
    """Redact credentials before debug details leave the server process."""
    redacted = text
    for key, value in os.environ.items():
        upper = key.upper()
        if (
            value
            and len(value) >= 8
            and any(s in upper for s in ("KEY", "SECRET", "TOKEN", "PASSWORD"))
        ):
            redacted = redacted.replace(value, "***")
    redacted = re.sub(
        r"(?i)(\bbearer\s+)[a-z0-9._~+/=-]+",
        r"\1***",
        redacted,
    )
    return re.sub(
        r"(?i)((?:api[_-]?key|auth[_-]?token|access[_-]?token|secret|"
        r"password|token)\s*[:=]\s*)(?:[\"'][^\"']*[\"']|[^\s,;]+)",
        r"\1***",
        redacted,
    )


def _claims_from_forwarded_jwt(authorization: str | None) -> dict | None:
    """Decode the JWT an upstream API gateway forwarded in the Authorization
    header, WITHOUT re-verifying its signature.

    Used only in ``--auth-mode gateway``: the AgentKit runtime gateway has
    already authenticated the user and validated the token against the user
    pool before forwarding it, so this server trusts the payload for identity.
    Returns the claims dict, or None when there is no usable bearer JWT.
    """
    if not authorization:
        return None
    from veadk.utils.auth import strip_bearer_prefix

    token = strip_bearer_prefix(authorization)
    parts = token.split(".")
    if len(parts) != 3:
        return None
    import base64
    import json

    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except Exception:
        return None


DEV_SERVER_ORIGIN = "http://localhost:5173"
DEV_SERVER_LOOPBACK_ORIGIN = "http://127.0.0.1:5173"


def _frontend_allow_origins(vite: bool) -> list[str]:
    """Return browser origins accepted by the local Vite development server."""
    if not vite:
        return []
    return [DEV_SERVER_ORIGIN, DEV_SERVER_LOOPBACK_ORIGIN]


# Built UI shipped inside the package (output of `npm run build`).
PACKAGED_WEBUI = Path(__file__).resolve().parent.parent / "webui"


def _mount_session_trace_route(app: Any, memory_exporter: Any) -> None:
    """Expose the session trace endpoint used by the VeADK frontend."""

    @app.get("/dev/apps/{app_name}/debug/trace/session/{session_id}")
    async def _get_session_trace(app_name: str, session_id: str) -> list[dict]:
        del app_name
        return [
            {
                "name": span.name,
                "span_id": span.context.span_id,
                "trace_id": span.context.trace_id,
                "start_time": span.start_time,
                "end_time": span.end_time,
                "attributes": dict(span.attributes),
                "parent_span_id": span.parent.span_id if span.parent else None,
            }
            for span in memory_exporter.get_finished_spans(session_id)
        ]


def _resolve_frontend_dir(arg: str | None) -> Path:
    """Resolve the built-UI directory.

    Priority: explicit ``--frontend-dir`` > packaged ``veadk/webui`` (works for
    pip-installed users) > ``./frontend/dist`` relative to cwd (dev fallback).
    """
    if arg:
        return Path(arg).resolve()
    if (PACKAGED_WEBUI / "index.html").is_file():
        return PACKAGED_WEBUI
    return (Path.cwd() / "frontend" / "dist").resolve()


def _open_browser_when_ready(
    url: str, host: str, port: int, timeout: float = 15.0
) -> None:
    """Open ``url`` in the default browser once the server accepts connections.

    Polls the TCP port (up to ``timeout`` seconds) so the tab lands on a ready
    server rather than a connection error. Runs on a daemon thread; any failure
    is logged and ignored — a browser that will not open must never block the
    server from serving.
    """
    import socket
    import time
    import webbrowser

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.25)
    else:
        logger.warning("Server not ready in time; skipped opening the browser.")
        return
    try:
        webbrowser.open(url)
    except Exception as e:  # noqa: BLE001 - opening a browser is best-effort
        logger.warning(f"Could not open the browser automatically: {e}")


# Built-in provider presets so users only need to supply client id/secret.
# Google is OIDC (endpoints come from discovery via OAUTH2_ISSUER); GitHub is
# not OIDC, so its endpoints are explicit and it needs Accept: application/json
# on the token request plus a non-"sub" id field.
_PROVIDER_PRESETS: dict[str, dict] = {
    "github": {
        "label": "GitHub",
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scope": "read:user user:email",
        "user_id_field": "login",
        "extra_token_headers": {"Accept": "application/json"},
    },
    "google": {
        "label": "Google",
        "issuer": "https://accounts.google.com",
        "scope": "openid email profile",
        "user_id_field": "sub",
    },
}

_PROVIDER_LABELS = {
    "veidentity": "火山引擎 Identity",
    "github": "GitHub",
    "google": "Google",
}


def _agentkit_authorization_header(api_key: str) -> str:
    """Normalize AgentKit credential input to an Authorization header value."""
    value = api_key.strip()
    if value.lower().startswith("bearer "):
        return value
    return f"Bearer {value}"


def _build_agentkit_proxy_headers(
    incoming_headers: dict[str, str],
    api_key: str | None,
    validated_authorization: str | None = None,
) -> dict[str, str]:
    """Return headers safe to forward from the local proxy to AgentKit.

    ``validated_authorization`` must only contain a credential already validated
    by the frontend OAuth middleware or its trusted upstream gateway.
    """
    excluded_headers = {
        # Host/proxy control.
        "host",
        "connection",
        "content-length",
        "x-agentkit-base",
        "x-agentkit-key",
        # Local VeADK/SSO credentials must not leak to the remote runtime.
        "authorization",
        "cookie",
        # Browser-only CORS/fetch metadata for the local origin.
        "origin",
        "referer",
        "sec-fetch-site",
        "sec-fetch-mode",
        "sec-fetch-dest",
        "sec-fetch-user",
    }
    headers = {
        key: value
        for key, value in incoming_headers.items()
        if key.lower() not in excluded_headers
    }
    if api_key and api_key.strip():
        headers["Authorization"] = _agentkit_authorization_header(api_key)
    elif validated_authorization and validated_authorization.strip():
        headers["Authorization"] = _agentkit_authorization_header(
            validated_authorization
        )
    return headers


def _build_generic_oauth2(provider_id: str, redirect_uri: str):
    """Build an OAuth2Config from env vars for a non-VeIdentity provider.

    Returns None when no generic provider is configured (no OAUTH2_CLIENT_ID).
    Endpoints come from a built-in preset, OAUTH2_ISSUER (OIDC discovery), or
    explicit OAUTH2_AUTHORIZE_URL / OAUTH2_TOKEN_URL / OAUTH2_USERINFO_URL.
    """
    client_id = os.getenv("OAUTH2_CLIENT_ID")
    if not client_id:
        return None

    from veadk.auth.middleware.oauth2_auth import OAuth2Config

    preset = _PROVIDER_PRESETS.get(provider_id, {})
    issuer = os.getenv("OAUTH2_ISSUER") or preset.get("issuer")
    authorize_url = os.getenv("OAUTH2_AUTHORIZE_URL") or preset.get("authorize_url")
    token_url = os.getenv("OAUTH2_TOKEN_URL") or preset.get("token_url")
    userinfo_url = os.getenv("OAUTH2_USERINFO_URL") or preset.get("userinfo_url")
    scope = os.getenv("OAUTH2_SCOPE") or preset.get("scope") or "openid profile email"

    # For an OIDC issuer, discover the endpoints we don't already have.
    if issuer and not (authorize_url and token_url):
        from veadk.auth.middleware.oauth2_auth import _fetch_oidc_discovery

        disc = _fetch_oidc_discovery(issuer.rstrip("/"))
        authorize_url = authorize_url or disc.authorization_endpoint
        token_url = token_url or disc.token_endpoint
        userinfo_url = userinfo_url or disc.userinfo_endpoint

    if not (authorize_url and token_url):
        raise click.ClickException(
            f"OAuth2 provider '{provider_id}': set OAUTH2_ISSUER (OIDC discovery) or "
            "OAUTH2_AUTHORIZE_URL + OAUTH2_TOKEN_URL (+ OAUTH2_USERINFO_URL)."
        )

    return OAuth2Config(
        authorize_url=authorize_url,
        token_url=token_url,
        userinfo_url=userinfo_url,
        client_id=client_id,
        client_secret=os.getenv("OAUTH2_CLIENT_SECRET"),
        scope=scope,
        redirect_uri=redirect_uri,
        issuer=issuer,
        user_id_field=preset.get("user_id_field", "sub"),
        extra_token_headers=preset.get("extra_token_headers", {}),
    )


def _serve_options(f):
    """Shared CLI options for the `frontend` and `studio` serve commands."""
    options = [
        click.option(
            "--agents-dir",
            default=".",
            show_default=True,
            help="Directory containing agent apps (like `adk web`): run from the "
            "parent folder of your agent directories — each subdir with an "
            "`agent.py` exposing a `root_agent` becomes a selectable app in the "
            "UI. Defaults to the current directory.",
        ),
        click.option(
            "--frontend-dir",
            default=None,
            help="Override the built React UI directory. Defaults to the UI shipped "
            "with the package (veadk/webui), falling back to ./frontend/dist.",
        ),
        click.option(
            "--site-logo",
            default=None,
            envvar="VEADK_SITE_LOGO",
            help="Studio logo as a local image path or HTTP(S) URL "
            "(env: VEADK_SITE_LOGO).",
        ),
        click.option(
            "--site-title",
            default=None,
            envvar="VEADK_SITE_TITLE",
            help="Studio title, at most 6 characters (env: VEADK_SITE_TITLE).",
        ),
        click.option("--host", default="127.0.0.1", show_default=True),
        click.option("--port", default=8000, show_default=True, type=int),
        click.option(
            "--dev",
            is_flag=True,
            default=False,
            help=(
                "Load LOCAL agents (this server's /list-apps) in the agent picker "
                "instead of your cloud AgentKit runtimes. The UI is still served "
                "normally; this only changes where the picker sources agents."
            ),
        ),
        click.option(
            "--vite",
            is_flag=True,
            default=False,
            help=(
                "Frontend hot-reload mode: serve the API only (no bundled UI) and "
                f"allow CORS from the Vite dev server ({DEV_SERVER_ORIGIN}). Run "
                "`npm run dev` in ./frontend and open that URL. For hacking on the "
                "React app; combine with --dev to also use local agents."
            ),
        ),
        click.option(
            "--oauth2-user-pool",
            default=None,
            help="VeIdentity User Pool NAME. When set (or its UID), enables SSO: "
            "unauthenticated browsers see a login page and the UI uses the signed-in user.",
        ),
        click.option(
            "--oauth2-user-pool-client",
            default=None,
            help="VeIdentity User Pool client NAME.",
        ),
        click.option(
            "--oauth2-user-pool-uid",
            default=None,
            envvar="OAUTH2_USER_POOL_ID",
            help="VeIdentity User Pool UID (env: OAUTH2_USER_POOL_ID). Use instead of "
            "the pool name.",
        ),
        click.option(
            "--oauth2-user-pool-client-uid",
            default=None,
            envvar="OAUTH2_USER_POOL_CLIENT_ID",
            help="VeIdentity client UID (env: OAUTH2_USER_POOL_CLIENT_ID). Use instead "
            "of the client name.",
        ),
        click.option(
            "--oauth2-redirect-uri",
            default=None,
            envvar="OAUTH2_REDIRECT_URI",
            help="OAuth2 callback URL (env: OAUTH2_REDIRECT_URI). Set this when deploying "
            "behind a public host/runtime; defaults to http://{host}:{port}/oauth2/callback.",
        ),
        click.option(
            "--oauth2-provider",
            default=None,
            envvar="OAUTH2_PROVIDER",
            help="SSO provider id (env: OAUTH2_PROVIDER), e.g. veidentity, github, google, "
            "or a custom name. For github/google, only client id/secret env vars are needed; "
            "for any OIDC provider set OAUTH2_ISSUER; otherwise set OAUTH2_AUTHORIZE_URL/"
            "OAUTH2_TOKEN_URL/OAUTH2_USERINFO_URL. Client creds via OAUTH2_CLIENT_ID/"
            "OAUTH2_CLIENT_SECRET. Defaults to veidentity when a user pool is configured.",
        ),
        click.option(
            "--oauth2-provider-label",
            default=None,
            envvar="OAUTH2_PROVIDER_LABEL",
            help="Display label for the SSO login button (env: OAUTH2_PROVIDER_LABEL).",
        ),
        click.option(
            "--auth-mode",
            type=click.Choice(["frontend", "gateway"]),
            default="frontend",
            show_default=True,
            envvar="VEADK_FRONTEND_AUTH_MODE",
            help="How the UI obtains the signed-in user (env: VEADK_FRONTEND_AUTH_MODE). "
            "'frontend' (default): this server runs its own OAuth2 login. 'gateway': "
            "trust the identity an upstream API gateway already authenticated and "
            "forwards as an Authorization: Bearer <JWT> — parse the user from it and run "
            "no in-app login (use when deployed behind the AgentKit runtime gateway).",
        ),
        click.option(
            "--generated-agent-test-run-ttl",
            default=1800,
            show_default=True,
            type=int,
            help="Seconds before a generated-agent debug runner is cleaned up.",
        ),
        click.option(
            "--admin",
            "studio_admins",
            default=None,
            envvar="VEADK_STUDIO_ADMINS",
            help="Comma-separated Studio admin usernames or OAuth emails "
            "(env: VEADK_STUDIO_ADMINS). Omit both role options to grant "
            "every user admin access.",
        ),
        click.option(
            "--developer",
            "studio_developers",
            default=None,
            envvar="VEADK_STUDIO_DEVELOPERS",
            help="Comma-separated Studio developer usernames or OAuth emails "
            "(env: VEADK_STUDIO_DEVELOPERS).",
        ),
        click.option(
            "--open/--no-open",
            "open_browser",
            default=False,
            show_default=True,
            help="Open the web UI in your default browser once the server is ready. "
            "Off by default (typical server-hosted deployments have no local browser); "
            "pass --open for local use. Ignored with --vite.",
        ),
    ]
    for opt in reversed(options):
        f = opt(f)
    return f


@click.group(invoke_without_command=True)
@_serve_options
@click.pass_context
def frontend(
    ctx: click.Context,
    agents_dir: str,
    frontend_dir: str | None,
    site_logo: str | None,
    site_title: str | None,
    host: str,
    port: int,
    dev: bool,
    vite: bool,
    oauth2_user_pool: str | None,
    oauth2_user_pool_client: str | None,
    oauth2_user_pool_uid: str | None,
    oauth2_user_pool_client_uid: str | None,
    oauth2_redirect_uri: str | None,
    oauth2_provider: str | None,
    oauth2_provider_label: str | None,
    auth_mode: str,
    generated_agent_test_run_ttl: int,
    studio_admins: str | None,
    studio_developers: str | None,
    open_browser: bool,
) -> None:
    """Launch the A2UI web UI backed by the ADK agent API server."""
    if ctx.invoked_subcommand is not None:
        return
    _run_frontend_server(
        agents_dir=agents_dir,
        frontend_dir=frontend_dir,
        site_logo=site_logo,
        site_title=site_title,
        host=host,
        port=port,
        dev=dev,
        vite=vite,
        oauth2_user_pool=oauth2_user_pool,
        oauth2_user_pool_client=oauth2_user_pool_client,
        oauth2_user_pool_uid=oauth2_user_pool_uid,
        oauth2_user_pool_client_uid=oauth2_user_pool_client_uid,
        oauth2_redirect_uri=oauth2_redirect_uri,
        oauth2_provider=oauth2_provider,
        oauth2_provider_label=oauth2_provider_label,
        auth_mode=auth_mode,
        generated_agent_test_run_ttl=generated_agent_test_run_ttl,
        studio_admins=studio_admins,
        studio_developers=studio_developers,
        open_browser=open_browser,
        studio=False,
    )


@click.group(invoke_without_command=True)
@_serve_options
@click.pass_context
def studio(
    ctx: click.Context,
    agents_dir: str,
    frontend_dir: str | None,
    site_logo: str | None,
    site_title: str | None,
    host: str,
    port: int,
    dev: bool,
    vite: bool,
    oauth2_user_pool: str | None,
    oauth2_user_pool_client: str | None,
    oauth2_user_pool_uid: str | None,
    oauth2_user_pool_client_uid: str | None,
    oauth2_redirect_uri: str | None,
    oauth2_provider: str | None,
    oauth2_provider_label: str | None,
    auth_mode: str,
    generated_agent_test_run_ttl: int,
    studio_admins: str | None,
    studio_developers: str | None,
    open_browser: bool,
) -> None:
    """Launch VeADK Studio — the frontend trimmed to add & manage agents.

    Same server as `veadk frontend`, but studio mode: the UI feature-gates off
    chat/search/skill-center/history and lands on the add-agent page.
    `veadk studio deploy` deploys this to VeFaaS.
    """
    if ctx.invoked_subcommand is not None:
        return
    _run_frontend_server(
        agents_dir=agents_dir,
        frontend_dir=frontend_dir,
        site_logo=site_logo,
        site_title=site_title,
        host=host,
        port=port,
        dev=dev,
        vite=vite,
        oauth2_user_pool=oauth2_user_pool,
        oauth2_user_pool_client=oauth2_user_pool_client,
        oauth2_user_pool_uid=oauth2_user_pool_uid,
        oauth2_user_pool_client_uid=oauth2_user_pool_client_uid,
        oauth2_redirect_uri=oauth2_redirect_uri,
        oauth2_provider=oauth2_provider,
        oauth2_provider_label=oauth2_provider_label,
        auth_mode=auth_mode,
        generated_agent_test_run_ttl=generated_agent_test_run_ttl,
        studio_admins=studio_admins,
        studio_developers=studio_developers,
        open_browser=open_browser,
        studio=True,
    )


def _run_frontend_server(
    *,
    agents_dir: str,
    frontend_dir: str | None,
    site_logo: str | None,
    site_title: str | None,
    host: str,
    port: int,
    dev: bool,
    vite: bool = False,
    oauth2_user_pool: str | None,
    oauth2_user_pool_client: str | None,
    oauth2_user_pool_uid: str | None,
    oauth2_user_pool_client_uid: str | None,
    oauth2_redirect_uri: str | None,
    oauth2_provider: str | None,
    oauth2_provider_label: str | None,
    auth_mode: str,
    generated_agent_test_run_ttl: int,
    studio_admins: str | None = None,
    studio_developers: str | None = None,
    open_browser: bool,
    studio: bool = False,
) -> None:
    """Launch the A2UI web UI backed by the ADK agent API server."""

    try:
        branding_title = normalize_site_title(site_title)
        branding_logo = resolve_site_logo(site_logo)
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    # Explicitly load .env file before any agent code runs
    # find_dotenv() searches upward from current directory to find .env
    from dotenv import find_dotenv, load_dotenv

    env_file_path = find_dotenv()
    if env_file_path:
        load_dotenv(env_file_path)
        logger.info(f"Loaded .env file from {env_file_path}")
    else:
        logger.warning("No .env file found in current directory or parent directories")

    from google.adk.cli.fast_api import get_fast_api_app

    agents_dir = os.path.abspath(agents_dir)
    allow_origins = _frontend_allow_origins(vite)

    app = get_fast_api_app(
        agents_dir=agents_dir,
        allow_origins=allow_origins,
        extra_plugins=[
            "veadk.multimodal.plugin.MultimodalMediaPlugin",
            "veadk.cli.frontend_invocation.FrontendInvocationPlugin",
        ],
        web=False,  # we serve our own UI, not the bundled ADK dev UI
    )

    # ``web=False`` deliberately keeps ADK's full development API disabled,
    # but the VeADK trace drawer needs this one read-only endpoint. Register a
    # dedicated in-memory exporter instead of enabling eval/builder endpoints.
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from veadk.cli.frontend_trace import SessionTraceExporter

    tracer_provider = trace.get_tracer_provider()
    if not isinstance(tracer_provider, TracerProvider):
        raise RuntimeError("ADK did not initialize an SDK tracer provider")
    trace_exporter = SessionTraceExporter()
    tracer_provider.add_span_processor(SimpleSpanProcessor(trace_exporter))
    _mount_session_trace_route(app, trace_exporter)

    # Agent introspection for the UI's agent picker (name, model, tools). Reuses
    # ADK's AgentLoader, which caches each loaded `root_agent`.
    from fastapi import HTTPException, Request
    from fastapi.responses import Response
    from google.adk.cli.utils.agent_loader import AgentLoader
    import httpx

    from veadk.cli.studio_rbac import (
        StudioAccessPolicy,
        StudioPrincipal,
        StudioRole,
        runtime_belongs_to,
    )
    from veadk.agent_metadata import (
        agent_component_summaries,
        agent_search_sources,
        agent_skill_summaries,
    )
    from veadk.agent_search import search_agent_component
    from veadk.multimodal.api import mount_media_routes
    from veadk.multimodal.service import MediaService
    from veadk.multimodal.storage import create_media_storage
    from veadk.multimodal.transport import resolve_runtime_media

    _agent_loader = AgentLoader(agents_dir)
    media_service = MediaService(create_media_storage())
    mount_media_routes(app, media_service)

    # Generated-agent debug is intentionally feature-complete in both local and
    # remote Studio deployments: the backend receives AgentDraft JSON, generates
    # the same project content as "Generate project", writes it to a temp dir,
    # and starts a runner for the debug session.
    generated_agent_test_run_allows_local_resources = True

    generated_agent_test_run_ttl = max(60, generated_agent_test_run_ttl)
    access_policy = StudioAccessPolicy.from_csv(
        studio_admins,
        studio_developers,
    )

    def _current_principal(request: Request) -> StudioPrincipal | None:
        """Resolve identity only from a trusted auth source.

        ``X-VeADK-Local-User`` is a local-development convenience and is not a
        production authentication boundary. It is ignored whenever OAuth or a
        trusted gateway is active.
        """
        if auth_mode == "gateway":
            claims = _claims_from_forwarded_jwt(request.headers.get("authorization"))
            return StudioPrincipal.from_claims(claims) if claims else None

        oauth2_handler = getattr(app.state, "oauth2_handler", None)
        if oauth2_handler is not None:
            session = oauth2_handler.get_session_from_request(request)
            if session and session.user_info:
                return StudioPrincipal.from_claims(session.user_info)
            if getattr(request.state, "oauth2_access_token_validated", False):
                claims = _claims_from_forwarded_jwt(
                    request.headers.get("authorization")
                )
                if claims:
                    return StudioPrincipal.from_claims(claims)
            scope_user = request.scope.get("user")
            display_name = str(getattr(scope_user, "display_name", "") or "")
            return StudioPrincipal.local(display_name)

        return StudioPrincipal.local(request.headers.get("X-VeADK-Local-User", ""))

    def _request_role(request: Request) -> StudioRole:
        principal = _current_principal(request)
        if access_policy.enabled and principal is None:
            raise HTTPException(status_code=401, detail="Studio identity is required")
        return access_policy.role_for(principal)

    def _require_agent_management(request: Request) -> StudioPrincipal | None:
        principal = _current_principal(request)
        if access_policy.enabled and principal is None:
            raise HTTPException(status_code=401, detail="Studio identity is required")
        if access_policy.role_for(principal) == StudioRole.USER:
            raise HTTPException(
                status_code=403, detail="Agent management is not allowed"
            )
        return principal

    @app.get("/web/access")
    async def _web_access(request: Request):
        principal = _current_principal(request)
        if access_policy.enabled and principal is None:
            raise HTTPException(status_code=401, detail="Studio identity is required")
        return access_policy.access_payload(principal)

    def _resolve_ve_credentials() -> tuple[str, str, str | None]:
        """Resolve Volcengine creds as (access_key, secret_key, session_token).

        Priority: env AK/SK first; else the VeFaaS-injected STS credential file
        (which carries a session token); else 400. This lets the same `/web/*`
        endpoints work locally (env creds) and inside a VeFaaS function, where
        only the function's IAM-role STS credentials are available.
        """
        ak = os.getenv("VOLCENGINE_ACCESS_KEY")
        sk = os.getenv("VOLCENGINE_SECRET_KEY")
        if ak and sk:
            # STS / temporary credentials carry a session token; don't drop it.
            token = os.getenv("VOLCENGINE_SESSION_TOKEN") or os.getenv(
                "VOLC_SESSIONTOKEN"
            )
            return ak, sk, token or None
        try:
            with open("/var/run/secrets/iam/credential", encoding="utf-8") as f:
                data = json.load(f)
            ak = data.get("access_key_id") or data.get("AccessKeyId")
            sk = data.get("secret_access_key") or data.get("SecretAccessKey")
            token = data.get("session_token") or data.get("SessionToken")
            if ak and sk:
                return ak, sk, token
        except (OSError, ValueError):
            pass
        raise HTTPException(
            status_code=400,
            detail="Volcengine credentials not found (set VOLCENGINE_ACCESS_KEY/"
            "SECRET_KEY, or run inside a VeFaaS function with an IAM role)",
        )

    # Prefixes (and a few exact keys) we copy from the server's environment
    # into a created AgentKit runtime. Anything NOT in this list is left out
    # so we never ship unrelated host env (PATH, HOME, IAM_ROLE, _FAAS_*, etc.).
    _ENV_PREFIXES: tuple[str, ...] = (
        "MODEL_AGENT_",
        "MODEL_EMBEDDING_",
        "MODEL_IMAGE_",
        "MODEL_EDIT_",
        "MODEL_VIDEO_",
        "MODEL_REALTIME_",
        "TOOL_",
        "VOLCENGINE_",
        "BYTEPLUS_",
        "DATABASE_MEM0_",
        "DATABASE_VIKING",
        "DATABASE_TOS_",
        "DATABASE_CONTEXT_SEARCH_",
        "OBSERVABILITY_",
        "AGENTKIT_",
        "ARK_",
        "OPENAI_",
        "GOOGLE_",
    )
    _ENV_EXACT: frozenset[str] = frozenset({"CLOUD_PROVIDER"})

    def _collect_runtime_envs() -> dict[str, str]:
        """Return env vars that should be injected into a deployed runtime."""
        try:
            from veadk.config import veadk_environments as _src
        except Exception:  # pragma: no cover
            _src = os.environ
        out: dict[str, str] = {}
        for k, v in _src.items():
            if not v:
                continue
            if k in _ENV_EXACT or any(k.startswith(p) for p in _ENV_PREFIXES):
                out[str(k)] = str(v)
        if not out.get("MODEL_AGENT_API_KEY"):
            try:
                from veadk.auth.veauth.ark_veauth import get_ark_token

                logger.info(
                    "MODEL_AGENT_API_KEY not set; resolving an Ark API key "
                    "via ListApiKeys for the runtime..."
                )
                ark_key = get_ark_token()
                if ark_key:
                    out["MODEL_AGENT_API_KEY"] = str(ark_key)
                    logger.info("Injected MODEL_AGENT_API_KEY into runtime env.")
            except Exception as e:
                logger.warning(
                    "Could not auto-resolve MODEL_AGENT_API_KEY for the runtime: "
                    "%s. The deployed agent may fail to start without this key; "
                    "set MODEL_AGENT_API_KEY in .env/config.yaml before deploying.",
                    e,
                )
        out["OTEL_SDK_DISABLED"] = "true"
        out["VEADK_DISABLE_EXPIRE_AT"] = "true"
        # Force telemetry exporters off. The AgentKit runner sets
        # apmplus_enable=True on every created runtime, which makes the
        # platform inject ENABLE_APMPLUS=true into the container; pre-seeding
        # the APMPlus api-key env with a harmless sentinel short-circuits the
        # cached_property before it calls get_apmplus_token().
        out["ENABLE_APMPLUS"] = "false"
        out["ENABLE_COZELOOP"] = "false"
        out["ENABLE_TLS"] = "false"
        out["OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY"] = "tracing-disabled"
        return out

    def _model_name(model: object) -> str:
        if isinstance(model, str):
            return model
        # ADK BaseLlm subclasses (incl. LiteLlm) carry the id on `.model`.
        return str(getattr(model, "model", None) or type(model).__name__)

    def _tool_label(tool: object) -> str:
        # FunctionTool / BaseTool expose `.name`; a bare function has
        # `__name__`; a toolset (e.g. MCP) has neither -> use its class name.
        name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
        return str(name or type(tool).__name__)

    def _agent_type(agent: object) -> str:
        # Map an ADK agent instance to the same type vocabulary the create
        # wizard uses: llm | sequential | parallel | loop | a2a.
        try:
            from google.adk.agents import (
                LoopAgent,
                ParallelAgent,
                SequentialAgent,
            )

            if isinstance(agent, LoopAgent):
                return "loop"
            if isinstance(agent, SequentialAgent):
                return "sequential"
            if isinstance(agent, ParallelAgent):
                return "parallel"
        except Exception:
            pass
        try:
            from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

            if isinstance(agent, RemoteA2aAgent):
                return "a2a"
        except Exception:
            pass
        return "llm"

    def _agent_node(
        agent: object, depth: int = 0, parent_path: tuple[str, ...] = ()
    ) -> dict:
        # Recursive typed tree for the conversation topology panel. Depth is
        # bounded so a pathological sub_agents cycle can't spin forever.
        name = getattr(agent, "name", "") or ""
        path = (*parent_path, name) if name else parent_path
        children = []
        if depth < 8:
            children = [
                _agent_node(s, depth + 1, path)
                for s in getattr(agent, "sub_agents", []) or []
            ]
        mode = getattr(agent, "mode", None)
        return {
            "id": name,
            "name": name,
            "description": getattr(agent, "description", "") or "",
            "type": _agent_type(agent),
            "model": _model_name(getattr(agent, "model", "")),
            "tools": [_tool_label(t) for t in getattr(agent, "tools", []) or []],
            "skills": agent_skill_summaries(agent),
            "components": agent_component_summaries(agent),
            "path": list(path),
            "mentionable": mode not in ("task", "single_turn"),
            "children": children,
        }

    if branding_logo is not None:

        @app.get("/web/site-logo")
        async def _web_site_logo():
            return Response(
                content=branding_logo.content,
                media_type=branding_logo.media_type,
                headers={"Cache-Control": "no-cache"},
            )

    @app.get("/web/ui-config")
    async def _web_ui_config():
        """Feature gates the SPA reads at startup. Studio now serves the SAME UI
        as `veadk frontend` — all modules (chat/search/skill-center/history +
        add/manage agent) enabled, landing on the chat view. The `studio` flag
        is informational."""
        return {
            "studio": studio,
            "branding": {
                "title": branding_title,
                "logoUrl": "/web/site-logo" if branding_logo is not None else "",
            },
            # Agent source for the picker: --dev serves local agents (/list-apps),
            # otherwise the deployed UI lists the user's cloud AgentKit runtimes.
            "agentsSource": "local" if dev else "cloud",
            "features": {
                "newChat": True,
                "search": True,
                "skillCenter": True,
                "history": True,
                "addAgent": True,
                "manageAgents": True,
                "addAgentkit": True,
                "generatedAgentTestRun": True,
                "generatedAgentTestRunDisabledReason": "",
            },
            "defaultView": "chat",
        }

    @app.get("/web/agent-info/{app_name}")
    async def _web_agent_info(app_name: str):
        try:
            agent = _agent_loader.load_agent(app_name)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"unknown agent: {app_name}")
        return {
            "name": getattr(agent, "name", app_name),
            "description": getattr(agent, "description", "") or "",
            "type": _agent_type(agent),
            "model": _model_name(getattr(agent, "model", "")),
            "tools": [_tool_label(t) for t in getattr(agent, "tools", []) or []],
            "skills": agent_skill_summaries(agent),
            "components": agent_component_summaries(agent),
            "searchSources": agent_search_sources(agent),
            "subAgents": [
                getattr(s, "name", "") for s in getattr(agent, "sub_agents", []) or []
            ],
            # Recursive typed tree used by the conversation topology panel.
            "graph": _agent_node(agent),
        }

    def _web_search_aksk() -> tuple[str | None, str | None]:
        ak = os.getenv("TOOL_WEB_SEARCH_ACCESS_KEY") or os.getenv(
            "VOLCENGINE_ACCESS_KEY"
        )
        sk = os.getenv("TOOL_WEB_SEARCH_SECRET_KEY") or os.getenv(
            "VOLCENGINE_SECRET_KEY"
        )
        return ak, sk

    @app.get("/web/search")
    async def _web_search(
        source: str,
        app_name: str,
        q: str,
        user_id: str = "",
    ):
        """Search the web or retrieval components mounted on a local Agent."""
        if source not in {"web", "knowledge", "memory"}:
            raise HTTPException(status_code=400, detail=f"unsupported source: {source}")

        try:
            agent = _agent_loader.load_agent(app_name)
        except ValueError:
            agent = None
        if source in {"knowledge", "memory"}:
            if agent is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"unknown agent: {app_name}",
                )
            if source == "memory" and not user_id:
                raise HTTPException(
                    status_code=400,
                    detail="user_id is required for long-term memory search",
                )
            return await search_agent_component(
                agent,
                source,
                q,
                app_name=app_name,
                user_id=user_id,
            )

        if not q.strip():
            return {"mounted": True, "results": []}

        # Gate on the agent's tools only when we can introspect it locally.
        if agent is not None:
            if "web" not in agent_search_sources(agent):
                return {"mounted": False, "results": []}

        ak, sk = _web_search_aksk()
        if not (ak and sk):
            return {
                "mounted": True,
                "results": [],
                "error": "服务端未配置 Volcengine AK/SK",
            }

        from veadk.utils.volcengine_sign import ve_request

        resp = ve_request(
            request_body={
                "Query": q[:100],
                "SearchType": "web",
                "Count": 8,
                "NeedSummary": True,
                "Filter": {"NeedUrl": True},
            },
            action="WebSearch",
            ak=ak,
            sk=sk,
            service="volc_torchlight_api",
            version="2025-01-01",
            region="cn-beijing",
            host="mercury.volcengineapi.com",
            header={"X-Security-Token": ""},
        )
        err = (
            (resp.get("ResponseMetadata") or {}).get("Error")
            if isinstance(resp, dict)
            else None
        )
        if err:
            return {
                "mounted": True,
                "results": [],
                "error": str(err.get("Message") or err),
            }
        items = (
            ((resp.get("Result") or {}).get("WebResults") or [])
            if isinstance(resp, dict)
            else []
        )
        results = [
            {
                "title": it.get("Title", "") or "",
                "url": it.get("Url", "") or "",
                "siteName": it.get("SiteName", "") or "",
                "summary": (it.get("Summary") or it.get("Snippet") or "").strip(),
            }
            for it in items
        ]
        return {"mounted": True, "results": results}

    # ---- Skill Hub proxy: proxy /skillhub/* to skills.volces.com ----
    SKILLHUB_TARGET = "https://skills.volces.com"

    @app.api_route(
        "/skillhub/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
    )
    async def _skillhub_proxy(request: Request, path: str):
        """Proxy requests to Volcengine Skill Hub API to avoid CORS issues."""
        target_url = f"{SKILLHUB_TARGET}/{path}"
        if request.url.query:
            target_url += f"?{request.url.query}"

        headers = dict(request.headers)
        headers.pop("host", None)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=await request.body(),
                    timeout=30.0,
                )
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )
        except Exception as e:
            logger.error(f"Skillhub proxy error: {e}")
            raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")

    # ---- AgentKit proxy: proxy /agentkit-proxy/* to remote AgentKit ----
    @app.api_route(
        "/agentkit-proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
    )
    async def _agentkit_proxy(request: Request, path: str):
        """Proxy requests to remote AgentKit APIs to avoid CORS issues.

        This proxy makes server-side requests to a URL supplied by the client,
        so it is locked down to prevent SSRF: the target host must be an
        AgentKit domain (``*.volceapi.com``) over HTTPS, and a credential
        (``X-AgentKit-Key``) must be present. Without both, we refuse rather
        than let the server reach arbitrary internal/external URLs.
        """
        _require_agent_management(request)
        from urllib.parse import urlparse

        target_base = request.headers.get("X-AgentKit-Base")
        api_key = request.headers.get("X-AgentKit-Key")
        if not target_base:
            raise HTTPException(status_code=400, detail="Missing X-AgentKit-Base")
        # Require a credential — an unauthenticated proxy is an open relay.
        if not api_key or not api_key.strip():
            raise HTTPException(status_code=401, detail="Missing X-AgentKit-Key")

        # SSRF guard: only HTTPS AgentKit domains may be targeted.
        parsed = urlparse(target_base)
        host = (parsed.hostname or "").lower()
        allowed = host == "volceapi.com" or host.endswith(".volceapi.com")
        if parsed.scheme != "https" or not allowed:
            raise HTTPException(
                status_code=403,
                detail="X-AgentKit-Base must be an https://*.volceapi.com URL",
            )

        # The local frontend may append SSO gateway query params to authenticate
        # this same-origin proxy request. Do not forward those params to the
        # remote AgentKit runtime, where names such as "token" can be interpreted
        # as the runtime credential and cause a false 401.
        target_url = f"{target_base.rstrip('/')}/{path}"

        headers = _build_agentkit_proxy_headers(dict(request.headers), api_key)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=await request.body(),
                    timeout=30.0,
                )
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )
        except Exception as e:
            logger.error(f"AgentKit proxy error: {e}")
            raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")

    # ---- Generated-agent debug runs -----------------------------------------
    # This replaces the old in-process temp-agent loader. Generated Python code
    # is only loaded by a short-lived subprocess runner.
    import atexit
    import secrets
    import shutil
    import socket
    import subprocess
    import tempfile
    import threading as _test_threading
    import time
    from dataclasses import dataclass
    from pathlib import Path as PathlibPath
    from urllib.parse import quote
    from pydantic import ValidationError

    from veadk.cli.generated_agent_codegen import (
        AgentDraft,
        GeneratedAgentProjectRequest,
        GeneratedAgentTestRunRequest,
        GeneratedProject,
        generate_project_from_draft,
        normalize_and_validate_draft,
    )
    from veadk.cli.generated_agent_security import (
        DebugPolicyError,
        validate_debug_policy,
        validate_project_policy,
    )
    from veadk.cli.generated_agent_skills import materialize_selected_skills

    _TEST_RUN_MAX_FILES = 100
    _TEST_RUN_MAX_FILE_BYTES = 256 * 1024
    _TEST_RUN_MAX_TOTAL_BYTES = 2 * 1024 * 1024
    _TEST_RUN_MAX_ACTIVE = 3
    _TEST_RUN_READY_TIMEOUT = 30.0

    @dataclass
    class _GeneratedAgentTestRun:
        run_id: str
        app_name: str
        temp_dir: str
        base_url: str
        process: subprocess.Popen
        expires_at: float
        owner_id: str

    _test_runs: dict[str, _GeneratedAgentTestRun] = {}
    _test_runs_creating = {"count": 0}
    _test_runs_lock = _test_threading.Lock()

    def _terminate_test_run(run: _GeneratedAgentTestRun) -> None:
        if run.process.poll() is None:
            run.process.terminate()
            try:
                run.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                run.process.kill()
                run.process.wait(timeout=3)
        shutil.rmtree(run.temp_dir, ignore_errors=True)

    def _cleanup_expired_test_runs() -> None:
        now = time.time()
        expired: list[_GeneratedAgentTestRun] = []
        with _test_runs_lock:
            for run_id, run in list(_test_runs.items()):
                if run.expires_at <= now or run.process.poll() is not None:
                    expired.append(_test_runs.pop(run_id))
        for run in expired:
            _terminate_test_run(run)

    def _cleanup_all_test_runs() -> None:
        with _test_runs_lock:
            runs = list(_test_runs.values())
            _test_runs.clear()
        for run in runs:
            _terminate_test_run(run)

    atexit.register(_cleanup_all_test_runs)

    _cleanup_interval = min(30, max(5, generated_agent_test_run_ttl // 2))

    def _test_run_cleanup_loop() -> None:
        while True:
            time.sleep(_cleanup_interval)
            try:
                _cleanup_expired_test_runs()
            except Exception as e:
                logger.warning(f"Generated-agent test-run cleanup failed: {e}")

    _test_threading.Thread(
        target=_test_run_cleanup_loop,
        name="generated-agent-test-run-cleanup",
        daemon=True,
    ).start()

    def _get_test_run(
        run_id: str,
        request: Request,
    ) -> _GeneratedAgentTestRun:
        _cleanup_expired_test_runs()
        with _test_runs_lock:
            run = _test_runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="test run not found")
        principal = _require_agent_management(request)
        if _request_role(request) != StudioRole.ADMIN and (
            principal is None or run.owner_id != principal.owner_id
        ):
            raise HTTPException(status_code=404, detail="test run not found")
        return run

    def _safe_runner_env() -> dict[str, str]:
        """Whitelisted environment for the child runner.

        Do not inherit full os.environ. The debug runner gets model credentials
        plus Volcengine/tool credentials so generated agents can exercise real
        tool calls during local debugging.
        """
        env: dict[str, str] = {
            "OTEL_SDK_DISABLED": "true",
            "VEADK_DISABLE_EXPIRE_AT": "true",
            "ENABLE_APMPLUS": "false",
            "ENABLE_COZELOOP": "false",
            "ENABLE_TLS": "false",
        }
        for key in (
            "MODEL_AGENT_API_KEY",
            "MODEL_AGENT_API_BASE",
            "MODEL_AGENT_BASE_URL",
            "MODEL_AGENT_NAME",
            "MODEL_AGENT_PROVIDER",
            "MODEL_AGENT_API_KEY_NAME",
            "MODEL_EMBEDDING_API_KEY",
            "MODEL_IMAGE_API_KEY",
            "MODEL_EDIT_API_KEY",
            "MODEL_VIDEO_API_KEY",
            "MODEL_REALTIME_API_KEY",
            "ARK_API_KEY",
            "VOLCENGINE_ACCESS_KEY",
            "VOLCENGINE_SECRET_KEY",
            "VOLCENGINE_SESSION_TOKEN",
            "VOLCENGINE_REGION",
            "TOOL_WEB_SEARCH_ACCESS_KEY",
            "TOOL_WEB_SEARCH_SECRET_KEY",
            "TOOL_VESPEECH_APP_ID",
            "TOOL_VESPEECH_ACCESS_TOKEN",
            "TOOL_VESEARCH_ENDPOINT",
            "TOOL_WEB_SCRAPER_ENDPOINT",
            "DATABASE_MEM0_API_KEY",
            "CLOUD_PROVIDER",
            "BYTEPLUS_WEB_SEARCH_API_KEY",
            "OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY",
        ):
            if os.getenv(key):
                env[key] = os.environ[key]
        for key in (
            "PATH",
            "HOME",
            "USER",
            "LOGNAME",
            "SHELL",
            "TMPDIR",
            "TEMP",
            "TMP",
            "VIRTUAL_ENV",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "NO_PROXY",
        ):
            if os.getenv(key):
                env[key] = os.environ[key]
        repo_root = str(Path(__file__).resolve().parents[2])
        pythonpath = os.getenv("PYTHONPATH")
        env["PYTHONPATH"] = (
            f"{repo_root}{os.pathsep}{pythonpath}" if pythonpath else repo_root
        )
        return env

    def _read_runner_log_tail(path: PathlibPath, max_chars: int = 6000) -> str:
        try:
            with path.open("rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - max_chars * 4))
                text = f.read().decode("utf-8", "replace")
        except OSError:
            return ""
        return _redact_debug_text(text[-max_chars:].strip())

    def _runner_log_detail(
        prefix: str,
        stdout_path: PathlibPath,
        stderr_path: PathlibPath,
    ) -> str:
        parts = [prefix]
        stderr_tail = _read_runner_log_tail(stderr_path)
        stdout_tail = _read_runner_log_tail(stdout_path)
        if stderr_tail:
            parts.append(f"stderr:\n{stderr_tail}")
        if stdout_tail:
            parts.append(f"stdout:\n{stdout_tail}")
        if len(parts) == 1:
            parts.append("No runner logs were captured.")
        return "\n\n".join(parts)

    def _unexpected_debug_error_detail(prefix: str, exc: Exception) -> str:
        """Log an unexpected error and return a safe, traceable UI summary."""
        error_id = secrets.token_hex(4)
        message = _redact_debug_text(str(exc).strip()) or "No error message"
        logger.exception(
            "Generated-agent debug error %s (%s): %s",
            error_id,
            type(exc).__name__,
            message,
        )
        return (
            f"{prefix}（错误 ID：{error_id}）\n"
            f"异常类型：{type(exc).__name__}\n"
            "详细信息已记录在 Studio 服务端日志中。"
        )

    def _test_run_log_detail(run: _GeneratedAgentTestRun, prefix: str) -> str:
        temp_dir = PathlibPath(run.temp_dir)
        return _runner_log_detail(
            prefix,
            temp_dir / "runner.stdout.log",
            temp_dir / "runner.stderr.log",
        )

    def _runner_response_error_detail(
        run: _GeneratedAgentTestRun,
        operation: str,
        status_code: int,
        response_text: str,
    ) -> str:
        response_detail = _redact_debug_text(response_text.strip())
        prefix = f"{operation}失败（临时运行环境返回 HTTP {status_code}）"
        if response_detail and response_detail.lower() != "internal server error":
            prefix += f"\n响应：{response_detail[:2000]}"
        return _test_run_log_detail(run, prefix)

    def _http_policy_error(exc: Exception) -> HTTPException:
        return HTTPException(status_code=400, detail=str(exc))

    async def _resolve_skillspace_skill_md(
        space_id: str,
        skill_id: str,
        version: str | None,
        region: str | None = None,
    ) -> str:
        from agentkit.sdk.skills.types import GetSkillVersionRequest

        try:
            client = _skills_client(region or "cn-beijing")
            resp = client.get_skill_version(
                GetSkillVersionRequest(id=skill_id, skill_version=version)
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"GetSkillVersion({skill_id}@{version}) error for region {region or 'cn-beijing'}: {e}",
                exc_info=True,
            )
            raise HTTPException(status_code=502, detail=f"SkillSpaces API error: {e}")
        if not resp.skill_md:
            raise HTTPException(
                status_code=404, detail="Skill version has no SKILL.md content"
            )
        return str(resp.skill_md)

    def _draft_for_debug_run(draft: AgentDraft) -> AgentDraft:
        """Return a debug-safe draft by omitting stdio MCP tools recursively."""
        return draft.model_copy(
            deep=True,
            update={
                "mcpTools": [
                    tool for tool in draft.mcpTools if tool.transport != "stdio"
                ],
                "subAgents": [
                    _draft_for_debug_run(sub_agent) for sub_agent in draft.subAgents
                ],
            },
        )

    async def _generate_project_from_request(
        data: dict,
        *,
        debug: bool,
    ) -> GeneratedProject:
        try:
            if debug:
                req = GeneratedAgentTestRunRequest.model_validate(data)
            else:
                req = GeneratedAgentProjectRequest.model_validate(data)
            draft = normalize_and_validate_draft(req.draft)
            if debug:
                draft = _draft_for_debug_run(draft)
                validate_debug_policy(
                    draft,
                    allow_local_runtime_resources=(
                        generated_agent_test_run_allows_local_resources
                    ),
                )
            else:
                validate_project_policy(draft)
            project = generate_project_from_draft(draft)
            await materialize_selected_skills(
                draft,
                project,
                resolve_skillspace_detail=_resolve_skillspace_skill_md,
            )
            return project
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors()) from e
        except DebugPolicyError as e:
            raise _http_policy_error(e) from e

    def _write_generated_project(project: GeneratedProject, temp_dir: str) -> str:
        if not project.name:
            raise HTTPException(status_code=400, detail="Agent name is required")
        files = project.files
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        if len(files) > _TEST_RUN_MAX_FILES:
            raise HTTPException(status_code=400, detail="Too many files")

        base = PathlibPath(temp_dir).resolve()
        total = 0
        for item in files:
            file_path = item.path
            content = item.content
            if not isinstance(file_path, str) or not file_path.strip():
                raise HTTPException(status_code=400, detail="Invalid file path")
            if not isinstance(content, str):
                raise HTTPException(
                    status_code=400, detail=f"Invalid content: {file_path}"
                )
            encoded = content.encode("utf-8")
            if len(encoded) > _TEST_RUN_MAX_FILE_BYTES:
                raise HTTPException(
                    status_code=400, detail=f"File too large: {file_path}"
                )
            total += len(encoded)
            if total > _TEST_RUN_MAX_TOTAL_BYTES:
                raise HTTPException(status_code=400, detail="Project is too large")

            path_obj = PathlibPath(file_path)
            if path_obj.is_absolute() or "\x00" in file_path:
                raise HTTPException(
                    status_code=400, detail=f"Illegal file path: {file_path}"
                )
            if any(part in ("", ".", "..") for part in path_obj.parts):
                raise HTTPException(
                    status_code=400, detail=f"Illegal file path: {file_path}"
                )

            full = (base / file_path).resolve()
            if not full.is_relative_to(base):
                raise HTTPException(
                    status_code=400, detail=f"Illegal file path: {file_path}"
                )
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")

        agents_dir = base / "agents"
        apps = (
            sorted(
                p.name
                for p in agents_dir.iterdir()
                if p.is_dir() and (p / "agent.py").is_file()
            )
            if agents_dir.is_dir()
            else []
        )
        if project.name in apps:
            return project.name
        if len(apps) == 1:
            return apps[0]
        raise HTTPException(
            status_code=400,
            detail="Generated project must contain exactly one agents/<name>/agent.py",
        )

    def _free_local_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    async def _wait_for_runner_ready(
        base_url: str,
        app_name: str,
        proc: subprocess.Popen,
        stdout_path: PathlibPath,
        stderr_path: PathlibPath,
    ) -> None:
        import asyncio

        deadline = time.time() + _TEST_RUN_READY_TIMEOUT
        last_error = ""
        async with httpx.AsyncClient(timeout=2.0) as client:
            while time.time() < deadline:
                if proc.poll() is not None:
                    raise HTTPException(
                        status_code=400,
                        detail=_runner_log_detail(
                            "Debug runner exited before becoming ready "
                            f"(exit code {proc.returncode}).",
                            stdout_path,
                            stderr_path,
                        ),
                    )
                try:
                    res = await client.get(f"{base_url}/list-apps")
                    if res.status_code == 200 and app_name in (res.json() or []):
                        return
                    last_error = f"list-apps returned {res.status_code}"
                except Exception as e:
                    last_error = str(e)
                await asyncio.sleep(0.25)
        raise HTTPException(
            status_code=504,
            detail=_runner_log_detail(
                f"Debug runner did not become ready: {last_error}",
                stdout_path,
                stderr_path,
            ),
        )

    @app.post("/web/generated-agent-projects")
    async def _generate_agent_project(request: Request):
        _require_agent_management(request)
        data = await request.json()
        project = await _generate_project_from_request(data, debug=False)
        return project.model_dump()

    @app.post("/web/generated-agent-test-runs")
    async def _create_generated_agent_test_run(request: Request):
        principal = _require_agent_management(request)
        _cleanup_expired_test_runs()
        data = await request.json()

        reserved = False
        with _test_runs_lock:
            active_count = len(_test_runs) + _test_runs_creating["count"]
            if active_count >= _TEST_RUN_MAX_ACTIVE:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        "调试环境并发数已达上限 "
                        f"({active_count}/{_TEST_RUN_MAX_ACTIVE})，"
                        "请稍后重试或关闭不再使用的调试页面。"
                    ),
                )
            _test_runs_creating["count"] += 1
            reserved = True

        temp_dir = ""
        proc = None
        try:
            project = await _generate_project_from_request(data, debug=True)
            temp_dir = tempfile.mkdtemp(prefix="veadk_generated_agent_test_")
            app_name = _write_generated_project(project, temp_dir)
            port = _free_local_port()
            base_url = f"http://127.0.0.1:{port}"
            stdout_path = PathlibPath(temp_dir) / "runner.stdout.log"
            stderr_path = PathlibPath(temp_dir) / "runner.stderr.log"
            cmd = [
                sys.executable,
                "-m",
                "veadk.cli.generated_agent_test_runner",
                "--agents-dir",
                str(PathlibPath(temp_dir) / "agents"),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ]
            with stdout_path.open("w", encoding="utf-8") as stdout_file:
                with stderr_path.open("w", encoding="utf-8") as stderr_file:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=temp_dir,
                        env=_safe_runner_env(),
                        stdout=stdout_file,
                        stderr=stderr_file,
                    )
            await _wait_for_runner_ready(
                base_url,
                app_name,
                proc,
                stdout_path,
                stderr_path,
            )

            run_id = "tr_" + secrets.token_urlsafe(18)
            expires_at = time.time() + generated_agent_test_run_ttl
            run = _GeneratedAgentTestRun(
                run_id=run_id,
                app_name=app_name,
                temp_dir=temp_dir,
                base_url=base_url,
                process=proc,
                expires_at=expires_at,
                owner_id=principal.owner_id if principal else "",
            )
            with _test_runs_lock:
                _test_runs[run_id] = run
            return {
                "runId": run_id,
                "appName": app_name,
                "expiresAt": int(expires_at),
            }
        except Exception as exc:
            if proc is not None:
                _terminate_test_run(
                    _GeneratedAgentTestRun("", "", temp_dir, "", proc, 0, "")
                )
            else:
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(
                status_code=500,
                detail=_unexpected_debug_error_detail(
                    "创建调试环境失败",
                    exc,
                ),
            ) from exc
        finally:
            if reserved:
                with _test_runs_lock:
                    _test_runs_creating["count"] = max(
                        0,
                        _test_runs_creating["count"] - 1,
                    )

    @app.post("/web/generated-agent-test-runs/{run_id}/sessions")
    async def _create_generated_agent_test_session(run_id: str, request: Request):
        run = _get_test_run(run_id, request)
        data = await request.json()
        user_id = (data.get("userId") or "test_user").strip() or "test_user"
        url = (
            f"{run.base_url}/apps/{run.app_name}/users/"
            f"{quote(user_id, safe='')}/sessions"
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json={})
        except httpx.HTTPError as exc:
            detail = _unexpected_debug_error_detail(
                "连接临时运行环境以创建会话时失败",
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail=_test_run_log_detail(run, detail),
            ) from exc
        if res.status_code >= 400:
            raise HTTPException(
                status_code=res.status_code,
                detail=_runner_response_error_detail(
                    run,
                    "创建调试会话",
                    res.status_code,
                    res.text,
                ),
            )
        try:
            return res.json()
        except ValueError as exc:
            detail = _unexpected_debug_error_detail(
                "解析临时运行环境的会话响应时失败",
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail=_test_run_log_detail(run, detail),
            ) from exc

    @app.post("/web/generated-agent-test-runs/{run_id}/run_sse")
    async def _run_generated_agent_test_sse(run_id: str, request: Request):
        from fastapi.responses import StreamingResponse

        run = _get_test_run(run_id, request)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Invalid run_sse payload")
        payload["app_name"] = run.app_name

        async def _stream():
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        "POST",
                        f"{run.base_url}/run_sse",
                        json=payload,
                        timeout=None,
                    ) as res:
                        if res.status_code >= 400:
                            text = (await res.aread()).decode("utf-8", "replace")
                            detail = _runner_response_error_detail(
                                run,
                                "调试对话",
                                res.status_code,
                                text,
                            )
                            logger.warning(
                                "test-run run_sse %s (%s): %s",
                                res.status_code,
                                run.base_url,
                                detail[:500],
                            )
                            err = json.dumps(
                                {
                                    "error": detail,
                                    "status_code": res.status_code,
                                },
                                ensure_ascii=False,
                            )
                            yield f"data: {err}\n\n"
                            return
                        async for chunk in res.aiter_bytes():
                            yield chunk
            except httpx.HTTPError as exc:
                detail = _unexpected_debug_error_detail(
                    "连接临时运行环境进行调试对话时失败",
                    exc,
                )
                detail = _test_run_log_detail(run, detail)
                err = json.dumps({"error": detail}, ensure_ascii=False)
                yield f"data: {err}\n\n"

        return StreamingResponse(_stream(), media_type="text/event-stream")

    @app.delete("/web/generated-agent-test-runs/{run_id}")
    async def _delete_generated_agent_test_run(run_id: str, request: Request):
        _get_test_run(run_id, request)
        with _test_runs_lock:
            run = _test_runs.pop(run_id, None)
        if run is not None:
            _terminate_test_run(run)
        return {"success": True}

    import threading as _threading

    _deploy_lock = _threading.Lock()
    _deploy_tasks_lock = _threading.Lock()
    _deploy_tasks: dict[str, dict[str, Any]] = {}

    def _delete_agentkit_runtime(runtime_id: str, region: str) -> None:
        """Delete one AgentKit Runtime through the control plane."""
        from agentkit.sdk.runtime import types as _rt
        from agentkit.sdk.runtime.client import AgentkitRuntimeClient

        ak, sk, token = _resolve_ve_credentials()
        client = AgentkitRuntimeClient(
            access_key=ak,
            secret_key=sk,
            session_token=token or "",
            region=region,
        )
        client.delete_runtime(_rt.DeleteRuntimeRequest(RuntimeId=runtime_id))

    def _destroy_deploy_task_runtime(task: dict[str, Any]) -> bool:
        """Destroy a task's Runtime once, if creation has reached that stage."""
        with _deploy_tasks_lock:
            runtime_id = str(task.get("runtime_id") or "")
            if not runtime_id or task.get("destroyed") or task.get("destroying"):
                return False
            task["destroying"] = True
            region = str(task.get("region") or "cn-beijing")

        try:
            _delete_agentkit_runtime(runtime_id, region)
        except Exception:
            with _deploy_tasks_lock:
                task["destroying"] = False
            raise

        with _deploy_tasks_lock:
            task["destroying"] = False
            task["destroyed"] = True
        return True

    @app.post("/web/cancel-deploy-agentkit")
    async def _cancel_deploy_to_agentkit(request: Request):
        """Cancel a deployment and destroy any Runtime it already created."""
        principal = _require_agent_management(request)
        data = await request.json()
        task_id = str(data.get("taskId") or "").strip()
        if not task_id:
            raise HTTPException(status_code=400, detail="taskId is required")
        with _deploy_tasks_lock:
            task = _deploy_tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Deployment task not found")
        if _request_role(request) != StudioRole.ADMIN and (
            principal is None or task.get("owner_id") != principal.owner_id
        ):
            raise HTTPException(status_code=404, detail="Deployment task not found")

        task["cancel_event"].set()
        try:
            destroyed = _destroy_deploy_task_runtime(task)
        except Exception as e:
            logger.error("cancel deployment cleanup failed: %s", e, exc_info=True)
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {
            "success": True,
            "runtimeId": str(task.get("runtime_id") or ""),
            "destroyed": destroyed or bool(task.get("destroyed")),
        }

    @app.post("/web/deploy-agentkit")
    async def _deploy_to_agentkit(request: Request):
        """Deploy to AgentKit, streaming per-stage progress as Server-Sent Events.

        Body: {name, files:[{path,content}], config:{region,projectName}}.
        While building/deploying, streams `data: {level, phase, message, pct?}`
        frames (phase = build|deploy|publish); ends with a terminal
        `data: {done:true, success, agentName?, url?, apikey?, runtimeId?,
        consoleUrl?, error?, phase?}` frame. Uses the AgentKit SDK in-process
        (no CLI subprocess) and tags the runtime with the deploying user.
        """
        import tempfile
        import shutil
        import queue as _queue
        import json as _json
        import asyncio
        import yaml as _yaml
        from pathlib import Path as PathlibPath
        from contextlib import contextmanager

        principal = _require_agent_management(request)
        data = await request.json()
        agent_name = (data.get("name") or "").strip()
        files = data.get("files", [])
        config = data.get("config", {})
        task_id = str(data.get("taskId") or f"deploy-{id(request)}").strip()
        author = principal.display_name if principal else ""
        owner_id = principal.owner_id if principal else ""
        if not agent_name:
            raise HTTPException(status_code=400, detail="Agent name is required")
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        region = config.get("region", "cn-beijing")
        project_name = config.get("projectName", "default")
        # Network config (advanced): optional VPC/private networking.
        # Shape: { mode: "public"|"private"|"both", vpc_id?, subnet_ids?, enable_shared_internet_access? }
        # When absent or mode=public, use the default public endpoint.
        net_cfg = (
            config.get("network") if isinstance(config.get("network"), dict) else {}
        )
        runtime_network: dict | None = None
        if net_cfg:
            mode = str(net_cfg.get("mode") or "").strip().lower()
            if mode and mode != "public":
                runtime_network = dict(net_cfg)
        im_config = data.get("im") if isinstance(data.get("im"), dict) else {}
        feishu_config = (
            im_config.get("feishu") if isinstance(im_config.get("feishu"), dict) else {}
        )
        feishu_enabled = bool(feishu_config.get("enabled"))
        requested_envs = data.get("envs") if isinstance(data.get("envs"), list) else []
        requested_runtime_envs: dict[str, str] = {}
        for item in requested_envs:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            if not key.replace("_", "").isalnum() or key[0].isdigit():
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid environment variable name: {key}",
                )
            requested_runtime_envs[key] = str(item.get("value") or "")
        extra_runtime_envs = {
            key: value
            for key, value in requested_runtime_envs.items()
            if not key.startswith("TOOL_FEISHU_CHANNEL_")
        }
        feishu_app_id = (
            requested_runtime_envs.get("FEISHU_APP_ID", "").strip()
            or requested_runtime_envs.get("TOOL_FEISHU_CHANNEL_APP_ID", "").strip()
            or os.getenv("FEISHU_APP_ID", "").strip()
        )
        feishu_app_secret = (
            requested_runtime_envs.get("FEISHU_APP_SECRET", "").strip()
            or requested_runtime_envs.get("TOOL_FEISHU_CHANNEL_APP_SECRET", "").strip()
            or os.getenv("FEISHU_APP_SECRET", "").strip()
        )
        if feishu_enabled and (not feishu_app_id or not feishu_app_secret):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Feishu Channel is enabled but FEISHU_APP_ID "
                    "/ FEISHU_APP_SECRET are missing."
                ),
            )

        # Write the generated project (+ agentkit.yaml) into a temp dir. Passing
        # config_file makes the SDK resolve THIS dir as the project dir, so the
        # live server process is never chdir'd.
        temp_dir = tempfile.mkdtemp(prefix=f"agentkit_deploy_{agent_name}_")
        base = PathlibPath(temp_dir).resolve()
        for fi in files:
            fp = fi.get("path", "")
            if not fp or fp == "__init__.py":
                continue
            full = (base / fp).resolve()
            if not full.is_relative_to(base):
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise HTTPException(status_code=400, detail=f"Illegal file path: {fp}")
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(fi.get("content", ""), encoding="utf-8")
        if not (base / "app.py").exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="No app.py found in files")

        # Collect env vars from the deployer's environment to forward into the
        # created runtime. The AgentKit platform only injects what we pass here,
        # so we explicitly forward the VeADK/Volcengine/tool-related vars the
        # agent needs at boot. User-provided envs (from the UI) take priority
        # over our defaults.
        runtime_envs = _collect_runtime_envs()
        for k, v in extra_runtime_envs.items():
            runtime_envs[k] = v
        if feishu_enabled:
            runtime_envs.update(
                {
                    "FEISHU_APP_ID": feishu_app_id,
                    "FEISHU_APP_SECRET": feishu_app_secret,
                }
            )

        # TOS build-artifact buckets are region-scoped. The SDK default template
        # ("agentkit-platform-<account_id>") produces a single global name, which
        # collides once a bucket exists in cn-beijing and the user targets
        # cn-shanghai (TOS refuses cross-region reuse). For non-Beijing regions,
        # set a region-suffixed bucket name so each region gets its own
        # auto-created bucket.
        cloud_config: dict = {
            "region": region,
            "project_name": project_name,
            "image_tag": "latest",
            "runtime_envs": runtime_envs,
            "python_version": "3.12",
        }
        if runtime_network:
            cloud_config["runtime_network"] = runtime_network
        if region and region != "cn-beijing":
            region_suffix = region.split("-")[-1]  # "shanghai" from "cn-shanghai"
            try:
                from agentkit.utils.template_utils import render_template

                bucket_base = render_template("agentkit-platform-{{account_id}}")
            except Exception as e:
                logger.warning(
                    "Could not resolve account_id for TOS bucket naming: %s; "
                    "falling back to 'agentkit-platform-%s'",
                    e,
                    region_suffix,
                )
                bucket_base = "agentkit-platform"
            cloud_config["tos_bucket"] = f"{bucket_base}-{region_suffix}"

        agentkit_config = {
            "common": {
                "agent_name": agent_name,
                "entry_point": "app.py",
                "python_version": "3.12",
                "launch_type": "cloud",
            },
            "launch_types": {"cloud": cloud_config},
        }
        (base / "agentkit.yaml").write_text(
            _yaml.dump(agentkit_config, allow_unicode=True), encoding="utf-8"
        )

        task_state: dict[str, Any] = {
            "cancel_event": _threading.Event(),
            "runtime_id": "",
            "runtime_name": "",
            "region": region,
            "destroyed": False,
            "destroying": False,
            "owner_id": owner_id,
        }
        events: "_queue.Queue" = _queue.Queue()
        state = {"phase": "build", "build_error_excerpt": ""}

        _PHASE_ORDER = {"build": 0, "deploy": 1, "publish": 2}

        def _result_error_text(result) -> str:
            parts = []
            for obj in (
                result,
                getattr(result, "build_result", None),
                getattr(result, "deploy_result", None),
            ):
                if obj is None:
                    continue
                for attr in ("error", "error_code"):
                    value = getattr(obj, attr, None)
                    if value:
                        parts.append(str(value))
            return "\n".join(parts)

        def _is_tos_request_expired(error_text: str) -> bool:
            lower = (error_text or "").lower()
            return "request has expired" in lower and (
                "accessdenied" in lower or "access denied" in lower
            )

        def _friendly_error(error_text: str) -> str:
            if _is_tos_request_expired(error_text):
                return (
                    "云构建拉取源码包时 TOS 临时下载签名已过期。"
                    "已自动重试一次仍失败，请稍后重新点击部署。"
                )
            return error_text

        def _error_with_build_excerpt(error_text: str) -> str:
            error_text = _friendly_error(error_text)
            excerpt = state["build_error_excerpt"]
            if not excerpt or excerpt in error_text:
                return error_text
            return f"{error_text}\n\n构建日志关键错误：\n{excerpt}"

        def _classify(message: str) -> str:
            """Map a reporter message to a deploy phase, monotonically.

            The SDK prints two authoritative high-level markers — "Step 1/2:
            Building image" and "Step 2/2: Deploying service" — so the phase
            switches on those, and only advances to "publish" on a strong
            readiness/endpoint signal. The phase never regresses: many
            build/deploy sub-messages mention words like "endpoint", "ready",
            or "create" (e.g. "Ensuring CR public endpoint access", "Waiting for
            Runtime to be ready") that would otherwise flap the UI stepper
            backward.
            """
            m = message.lower()
            cur = state["phase"]
            if "step 2/2" in m:
                cand = "deploy"
            elif "step 1/2" in m:
                cand = "build"
            elif (
                "launch successful" in m
                or "service endpoint:" in m
                or "runtime status: ready" in m
                or "endpoint: http" in m
            ):
                cand = "publish"
            else:
                cand = cur
            # Phase only ever moves forward (build -> deploy -> publish).
            return cand if _PHASE_ORDER[cand] >= _PHASE_ORDER[cur] else cur

        from agentkit.toolkit.reporter import Reporter, TaskHandle

        def _emit(level: str, message: str, pct=None):
            state["phase"] = _classify(message)
            ev = {"level": level, "phase": state["phase"], "message": message}
            for marker in ("Generated Runtime name:", "Creating Runtime:"):
                if marker in message:
                    runtime_name = message.split(marker, 1)[1].strip()
                    if runtime_name:
                        task_state["runtime_name"] = runtime_name
                    break
            if task_state["runtime_name"]:
                ev["runtimeName"] = task_state["runtime_name"]
            if pct is not None:
                ev["pct"] = pct
            events.put(ev)

        class _QReporter(Reporter):
            def info(self, message, **k):
                _emit("info", str(message))

            def success(self, message, **k):
                _emit("success", str(message))

            def warning(self, message, **k):
                _emit("warning", str(message))

            def error(self, message, **k):
                _emit("error", str(message))

            def progress(self, message, current, total=100, **k):
                _emit(
                    "info", str(message), int(current / total * 100) if total else None
                )

            def confirm(self, message, default=False, **k):
                return default

            @contextmanager
            def long_task(self, description, total=100):
                _emit("info", str(description))

                class _H(TaskHandle):
                    def update(self, description=None, completed=None):
                        if description:
                            pct = (
                                int(completed / total * 100)
                                if (completed is not None and total)
                                else None
                            )
                            _emit("info", str(description), pct)

                yield _H()

            def show_logs(self, title, lines, max_lines=100):
                _emit("info", str(title))
                excerpt = _extract_build_error_excerpt(lines, min(max_lines, 30))
                if excerpt:
                    state["build_error_excerpt"] = excerpt
                    _emit("error", excerpt)

        result_box: dict = {}

        def _run():
            from agentkit.toolkit import sdk
            from agentkit.toolkit.models import PreflightMode

            with _deploy_lock:
                # Tag the created runtime with the deploying user so "管理 Agent"
                # can filter by author. Restored right after.
                rt_client = None
                orig_create = None
                try:
                    from agentkit.sdk.runtime.client import (
                        AgentkitRuntimeClient as rt_client,
                    )
                    from agentkit.sdk.runtime import types as _rt

                    orig_create = rt_client.create_runtime
                    extra = [
                        _rt.TagsItemForCreateRuntime.model_validate(
                            {"Key": "veadk:managed", "Value": "true"}
                        )
                    ]
                    if author:
                        extra.append(
                            _rt.TagsItemForCreateRuntime.model_validate(
                                {"Key": "veadk:author", "Value": author}
                            )
                        )
                    if owner_id:
                        extra.append(
                            _rt.TagsItemForCreateRuntime.model_validate(
                                {"Key": "veadk:owner", "Value": owner_id}
                            )
                        )

                    def _tagged_create(self, req, _orig=orig_create, _extra=extra):
                        if task_state["cancel_event"].is_set():
                            raise RuntimeError("Deployment cancelled")
                        req.tags = [*(req.tags or []), *_extra]
                        # The AgentKit runner hard-codes apmplus_enable=True on
                        # every runtime; force it off so the container doesn't
                        # try to fetch an APMPlus app-key with the deployer's
                        # AK/SK at boot (breaks for STS temp credentials).
                        req.apmplus_enable = False
                        created = _orig(self, req)
                        runtime_id = str(
                            getattr(created, "runtime_id", "")
                            or getattr(
                                getattr(created, "agent_kit_runtime", None),
                                "runtime_id",
                                "",
                            )
                        )
                        if runtime_id:
                            with _deploy_tasks_lock:
                                task_state["runtime_id"] = runtime_id
                        if task_state["cancel_event"].is_set():
                            _destroy_deploy_task_runtime(task_state)
                            raise RuntimeError("Deployment cancelled")
                        return created

                    rt_client.create_runtime = _tagged_create
                except Exception as e:
                    logger.error("Could not prepare Runtime ownership tags: %s", e)
                    result_box["error"] = str(e)
                    return

                try:
                    result = None
                    for attempt in range(1, 3):
                        state["build_error_excerpt"] = ""
                        if attempt > 1:
                            state["phase"] = "build"
                            _emit(
                                "warning",
                                (
                                    "TOS 临时下载签名已过期，正在重新打包上传并重试部署 "
                                    f"({attempt}/2)..."
                                ),
                            )
                        result = sdk.launch(
                            config_file=str(base / "agentkit.yaml"),
                            preflight_mode=PreflightMode.WARN,
                            reporter=_QReporter(),
                        )
                        if getattr(result, "success", False):
                            break
                        error_text = _result_error_text(result)
                        if attempt >= 2 or not _is_tos_request_expired(error_text):
                            break
                        _emit(
                            "warning",
                            "云构建使用的 TOS 源码包签名超过 900 秒有效期，自动重试一次。",
                        )
                    result_box["result"] = result
                except Exception as e:
                    logger.error(f"AgentKit launch error: {e}", exc_info=True)
                    result_box["error"] = str(e)
                finally:
                    if rt_client is not None and orig_create is not None:
                        rt_client.create_runtime = orig_create
                    if task_state["cancel_event"].is_set():
                        try:
                            _destroy_deploy_task_runtime(task_state)
                        except Exception as e:
                            logger.error(
                                "cancelled deployment cleanup failed: %s",
                                e,
                                exc_info=True,
                            )
                    with _deploy_tasks_lock:
                        _deploy_tasks.pop(task_id, None)
                    events.put(None)  # sentinel: launch finished

        with _deploy_tasks_lock:
            if task_id in _deploy_tasks:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=409, detail="Deployment task already exists"
                )
            _deploy_tasks[task_id] = task_state

        _threading.Thread(target=_run, daemon=True).start()

        async def _stream():
            loop = asyncio.get_event_loop()
            try:
                while True:
                    ev = await loop.run_in_executor(None, events.get)
                    if ev is None:
                        break
                    yield f"data: {_json.dumps(ev, ensure_ascii=False)}\n\n"

                final = {"done": True}
                if result_box.get("error"):
                    error_text = str(result_box["error"])
                    final.update(
                        {
                            "success": False,
                            "error": _error_with_build_excerpt(error_text),
                            "phase": state["phase"],
                        }
                    )
                else:
                    res = result_box.get("result")
                    dr = getattr(res, "deploy_result", None) if res else None
                    if res is not None and getattr(res, "success", False):
                        meta = (dr.metadata if (dr and dr.metadata) else {}) or {}
                        runtime_name = str(
                            meta.get("runtime_name")
                            or task_state.get("runtime_name")
                            or agent_name
                        )
                        final.update(
                            {
                                "success": True,
                                "agentName": runtime_name,
                                "url": getattr(dr, "endpoint_url", None)
                                if dr
                                else None,
                                "apikey": meta.get("runtime_apikey", ""),
                                "runtimeId": meta.get("runtime_id", ""),
                                "feishuChannel": {
                                    "enabled": True,
                                    "transport": "ws",
                                    "runtimeId": meta.get("runtime_id", ""),
                                }
                                if feishu_enabled
                                else None,
                                "consoleUrl": (
                                    "https://console.volcengine.com/agentkit/"
                                    f"region:agentkit+{region}/runtime?projectName={project_name}"
                                ),
                                "region": region,
                            }
                        )
                    else:
                        err = getattr(res, "error", None) if res else None
                        err_text = (
                            _result_error_text(res)
                            if res is not None
                            else str(err or "Deployment failed")
                        )
                        final.update(
                            {
                                "success": False,
                                "error": _error_with_build_excerpt(err_text)
                                or err
                                or "Deployment failed",
                                "phase": state["phase"],
                            }
                        )
                yield f"data: {_json.dumps(final, ensure_ascii=False)}\n\n"
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        from fastapi.responses import StreamingResponse

        return StreamingResponse(_stream(), media_type="text/event-stream")

    def _runtime_tags(runtime: Any) -> dict[str, str]:
        return {
            str(tag.key): str(tag.value)
            for tag in (getattr(runtime, "tags", None) or [])
        }

    def _get_runtime(runtime_id: str, region: str) -> Any:
        from agentkit.sdk.runtime import types as _rt
        from agentkit.sdk.runtime.client import AgentkitRuntimeClient

        ak, sk, token = _resolve_ve_credentials()
        client = AgentkitRuntimeClient(
            access_key=ak,
            secret_key=sk,
            session_token=token or "",
            region=region,
        )
        return client.get_runtime(_rt.GetRuntimeRequest(runtime_id=runtime_id))

    def _authorized_runtime(
        request: Request,
        runtime_id: str,
        region: str,
        *,
        managed_only: bool = False,
    ) -> Any:
        principal = _current_principal(request)
        role = _request_role(request)
        runtime = _get_runtime(runtime_id, region)
        tags = _runtime_tags(runtime)
        if role != StudioRole.ADMIN and not runtime_belongs_to(tags, principal):
            raise HTTPException(status_code=404, detail="Runtime not found")
        if managed_only and tags.get("veadk:managed") != "true":
            raise HTTPException(status_code=404, detail="Runtime not found")
        return runtime

    @app.get("/web/my-runtimes")
    async def _web_my_runtimes(request: Request, region: str = "all"):
        """List AgentKit runtimes created via this UI (tagged veadk:managed),
        filtered to the trusted current identity for non-admin users.
        `region=all` queries every supported region and merges results."""
        principal = _current_principal(request)
        role = _request_role(request)
        ak, sk, token = _resolve_ve_credentials()
        regions = (
            ["cn-beijing", "cn-shanghai"] if region in {"all", "", "*"} else [region]
        )

        async def _list_one(reg: str) -> list[dict]:
            from agentkit.sdk.runtime.client import AgentkitRuntimeClient
            from agentkit.sdk.runtime import types as _rt

            client = AgentkitRuntimeClient(
                access_key=ak,
                secret_key=sk,
                session_token=token or "",
                region=reg,
            )
            out: list[dict] = []
            next_token = None
            for _ in range(20):  # page cap
                kw: dict = {"page_size": 100}
                if next_token:
                    kw["next_token"] = next_token
                resp = client.list_runtimes(_rt.ListRuntimesRequest(**kw))
                for r in resp.agent_kit_runtimes or []:
                    tags = _runtime_tags(r)
                    if tags.get("veadk:managed") != "true":
                        continue
                    if role != StudioRole.ADMIN and not runtime_belongs_to(
                        tags, principal
                    ):
                        continue
                    out.append(
                        {
                            "name": r.name,
                            "runtimeId": r.runtime_id,
                            "status": r.status,
                            "createdAt": r.created_at,
                            "author": tags.get("veadk:author", ""),
                            "region": reg,
                        }
                    )
                next_token = getattr(resp, "next_token", None)
                if not next_token:
                    break
            return out

        try:
            results = await asyncio.gather(*[_list_one(r) for r in regions])
            out: list[dict] = [item for sub in results for item in sub]
            out.sort(key=lambda x: x.get("createdAt") or "", reverse=True)
            return {"runtimes": out}
        except Exception as e:
            logger.error(f"list my-runtimes failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

    @app.post("/web/delete-runtime")
    async def _web_delete_runtime(request: Request):
        """Delete an AgentKit runtime by id (used by the '管理 Agent' view)."""
        _require_agent_management(request)
        data = await request.json()
        runtime_id = (data.get("runtimeId") or "").strip()
        region = (data.get("region") or "cn-beijing").strip()
        if not runtime_id:
            raise HTTPException(status_code=400, detail="runtimeId is required")
        try:
            _authorized_runtime(
                request,
                runtime_id,
                region,
                managed_only=True,
            )
            _delete_agentkit_runtime(runtime_id, region)
            return {"success": True}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"delete runtime failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/web/runtime-detail")
    async def _web_runtime_detail(
        request: Request,
        runtimeId: str = "",
        region: str = "cn-beijing",
    ):
        """Control-plane detail for one runtime (used by the '管理 Agent' view).

        Returns config/status metadata from GetRuntime. This is NOT the in-container
        agent graph (that lives on the runtime's data plane); env-var values that
        look like secrets are masked before leaving the server.
        """
        if not runtimeId:
            raise HTTPException(status_code=400, detail="runtimeId is required")

        def _mask(key: str, value: str) -> str:
            if not value:
                return value
            if any(s in key.upper() for s in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
                return (value[:3] + "***") if len(value) > 3 else "***"
            return value

        try:
            r = _authorized_runtime(request, runtimeId, region)
            envs = [
                {"key": e.key, "value": _mask(e.key or "", e.value or "")}
                for e in (getattr(r, "envs", None) or [])
            ]
            return {
                "runtimeId": getattr(r, "runtime_id", runtimeId),
                "name": getattr(r, "name", "") or "",
                "description": getattr(r, "description", "") or "",
                "status": getattr(r, "status", "") or "",
                "statusMessage": getattr(r, "status_message", "") or "",
                "model": getattr(r, "model_agent_name", "") or "",
                "project": getattr(r, "project_name", "") or "",
                "region": region,
                "createdAt": getattr(r, "created_at", "") or "",
                "updatedAt": getattr(r, "updated_at", "") or "",
                "currentVersion": getattr(r, "current_version_number", None),
                "resources": {
                    "cpuMilli": getattr(r, "cpu_milli", None),
                    "memoryMb": getattr(r, "memory_mb", None),
                    "minInstance": getattr(r, "min_instance", None),
                    "maxInstance": getattr(r, "max_instance", None),
                    "maxConcurrency": getattr(r, "max_concurrency", None),
                },
                "envs": envs,
                "memoryId": getattr(r, "memory_id", "") or "",
                "toolId": getattr(r, "tool_id", "") or "",
                "knowledgeId": getattr(r, "knowledge_id", "") or "",
                "mcpToolsetId": getattr(r, "mcp_toolset_id", "") or "",
                "artifactUrl": getattr(r, "artifact_url", "") or "",
                "artifactType": getattr(r, "artifact_type", "") or "",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"get runtime detail failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/web/runtimes")
    async def _web_runtimes(
        request: Request,
        scope: str = "all",
        page_size: int = 30,
        next_token: str = "",
        region: str = "all",
    ):
        """One page of AgentKit runtimes for the agent selector. Lists ALL
        runtimes (server-side paginated); each item is flagged `isMine` when its
        ownership tags match the trusted current identity. Non-admin users are
        always restricted to their own runtimes.
        region=all merges runtimes across all supported regions."""
        principal = _current_principal(request)
        role = _request_role(request)
        ak, sk, svc_token = _resolve_ve_credentials()
        regions = (
            ["cn-beijing", "cn-shanghai"] if region in {"all", "", "*"} else [region]
        )
        page_size = max(1, min(page_size, 100))

        # next_token format for cross-region mode: "all:<offset>".
        async def _list_region(
            reg: str, tok: str, max_results: int = page_size
        ) -> tuple[list[dict], str]:
            from agentkit.sdk.runtime.client import AgentkitRuntimeClient
            from agentkit.sdk.runtime import types as _rt

            client = AgentkitRuntimeClient(
                access_key=ak,
                secret_key=sk,
                session_token=svc_token or "",
                region=reg,
            )
            out: list[dict] = []
            current_token = tok
            next_page_token = ""
            target_size = max(1, min(max_results, 100))
            for _ in range(20):
                kw: dict = {"max_results": max(1, target_size - len(out))}
                if current_token:
                    kw["next_token"] = current_token
                request = _rt.ListRuntimesRequest(**kw)
                resp = await asyncio.to_thread(client.list_runtimes, request)
                for runtime in resp.agent_kit_runtimes or []:
                    tags = _runtime_tags(runtime)
                    is_mine = runtime_belongs_to(tags, principal)
                    if (scope == "mine" or role != StudioRole.ADMIN) and not is_mine:
                        continue
                    out.append(
                        {
                            "name": runtime.name,
                            "runtimeId": runtime.runtime_id,
                            "status": runtime.status,
                            "createdAt": runtime.created_at,
                            "region": reg,
                            "author": tags.get("veadk:author", ""),
                            "isMine": is_mine,
                        }
                    )
                    if len(out) >= target_size:
                        break
                next_page_token = getattr(resp, "next_token", "") or ""
                if len(out) >= target_size or not next_page_token:
                    break
                current_token = next_page_token
            return out[:target_size], next_page_token

        try:
            if len(regions) == 1:
                out, nxt = await _list_region(regions[0], next_token)
                return {"runtimes": out, "nextToken": nxt}

            if next_token:
                match = re.fullmatch(r"all:(\d+)", next_token)
                if match is None:
                    raise HTTPException(
                        status_code=400,
                        detail="invalid cross-region runtime page token",
                    )
                offset = int(match.group(1))
            else:
                offset = 0

            # Pull only the regional prefixes needed to produce this merged
            # page. Fetching ``offset + page_size`` items per region is enough
            # to preserve the global created-at ordering without exhausting
            # every regional cursor on the first request.
            window_end = offset + page_size

            async def _list_region_window(reg: str) -> tuple[list[dict], bool]:
                items: list[dict] = []
                regional_token = ""
                seen_tokens: set[str] = set()
                following_token = ""
                while len(items) < window_end:
                    page, following_token = await _list_region(
                        reg,
                        regional_token,
                        window_end - len(items),
                    )
                    items.extend(page)
                    if not following_token:
                        break
                    if following_token in seen_tokens:
                        raise RuntimeError(f"repeated runtime page token for {reg}")
                    seen_tokens.add(following_token)
                    regional_token = following_token
                return items, bool(following_token)

            all_runtimes: list[dict] = []
            region_results = await asyncio.gather(
                *(_list_region_window(reg) for reg in regions),
                return_exceptions=True,
            )
            regional_has_more = False
            for reg, result in zip(regions, region_results, strict=True):
                if isinstance(result, BaseException):
                    logger.warning(f"list runtimes [{reg}] failed: {result}")
                    continue
                items, has_more = result
                all_runtimes.extend(items)
                regional_has_more = regional_has_more or has_more
            all_runtimes.sort(
                key=lambda x: x.get("createdAt") or "",
                reverse=True,
            )
            page_end = min(offset + page_size, len(all_runtimes))
            page = all_runtimes[offset:page_end]
            has_more = page_end < len(all_runtimes) or regional_has_more
            following_token = f"all:{page_end}" if has_more else ""
            return {"runtimes": page, "nextToken": following_token}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"list runtimes failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

    # Cache resolved (endpoint, apikey, auth type) per runtime so the data-plane
    # proxy does not call GetRuntime on every request. Short TTL; cleared on a 401.
    _rt_conn_cache: dict[tuple[str, str], tuple[str, str, str, float]] = {}

    def _resolve_runtime_conn(
        runtime_id: str,
        region: str,
        runtime: Any | None = None,
    ) -> tuple[str, str, str]:
        import time as _time

        cache_key = (region, runtime_id)
        cached = _rt_conn_cache.get(cache_key)
        if cached and cached[3] > _time.time():
            return cached[0], cached[1], cached[2]
        r = runtime if runtime is not None else _get_runtime(runtime_id, region)
        endpoint = ""
        for nc in getattr(r, "network_configurations", None) or []:
            ep = getattr(nc, "endpoint", "") or ""
            if ep:
                endpoint = ep
                if getattr(nc, "network_type", "") == "public":
                    break
        apikey = ""
        auth = getattr(r, "authorizer_configuration", None)
        key_auth = getattr(auth, "key_auth", None) if auth else None
        custom_jwt_auth = getattr(auth, "custom_jwt_authorizer", None) if auth else None
        auth_type = "none"
        if key_auth:
            apikey = getattr(key_auth, "api_key", "") or ""
            auth_type = "key_auth"
        elif custom_jwt_auth:
            auth_type = "custom_jwt"
        if not endpoint:
            raise HTTPException(
                status_code=502, detail="runtime has no public endpoint"
            )
        _rt_conn_cache[cache_key] = (
            endpoint,
            apikey,
            auth_type,
            _time.time() + 300,
        )
        return endpoint, apikey, auth_type

    @app.api_route(
        "/web/runtime-proxy/{runtime_id}/{path:path}",
        methods=["GET", "POST", "DELETE"],
    )
    async def _runtime_proxy(runtime_id: str, path: str, request: Request):
        """Proxy a data-plane call with its runtime credential injected server-side.

        The browser never sees an API key. Streams the response so /run_sse works.
        """
        region = request.query_params.get("region", "cn-beijing")
        try:
            runtime = _authorized_runtime(request, runtime_id, region)
            endpoint, apikey, auth_type = _resolve_runtime_conn(
                runtime_id,
                region,
                runtime,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"resolve runtime conn failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

        # Drop the SSO gateway querystring; keep any real API query params.
        qs = {k: v for k, v in request.query_params.items() if k != "region"}
        target = f"{endpoint.rstrip('/')}/{path}"
        # Use the shared proxy header builder so Origin/Referer and other
        # browser-only headers are stripped (the ADK server rejects them with
        # "origin not allowed" / 403 otherwise).
        validated_authorization = None
        if auth_type == "custom_jwt":
            access_token = getattr(request.state, "oauth2_access_token", None)
            if (
                getattr(request.state, "oauth2_access_token_validated", False)
                and access_token
            ):
                validated_authorization = access_token
            elif auth_mode == "gateway":
                incoming_authorization = request.headers.get("authorization")
                if _claims_from_forwarded_jwt(incoming_authorization):
                    validated_authorization = incoming_authorization
            if not validated_authorization:
                raise HTTPException(
                    status_code=401,
                    detail="OAuth runtime requires an authenticated frontend session",
                )
        headers = _build_agentkit_proxy_headers(
            dict(request.headers), apikey, validated_authorization
        )
        body = await request.body()
        if request.method == "POST" and path == "run_sse":
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as error:
                raise HTTPException(
                    status_code=400, detail="run_sse request body must be JSON"
                ) from error
            if not isinstance(payload, dict):
                raise HTTPException(
                    status_code=400, detail="run_sse request body must be an object"
                )
            try:
                body = json.dumps(
                    await resolve_runtime_media(payload, media_service)
                ).encode("utf-8")
            except FileNotFoundError as error:
                raise HTTPException(
                    status_code=404, detail="Media not found."
                ) from error
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error

        from fastapi.responses import StreamingResponse

        # Open the upstream stream so we can forward status + body incrementally.
        client = httpx.AsyncClient(timeout=None)
        req = client.build_request(
            request.method, target, params=qs, headers=headers, content=body
        )
        upstream = await client.send(req, stream=True)
        if upstream.status_code == 401:
            _rt_conn_cache.pop((region, runtime_id), None)
        if upstream.status_code >= 400:
            # Buffer error responses so we can log the body and still forward it.
            body_chunks = []
            async for chunk in upstream.aiter_raw():
                body_chunks.append(chunk)
            body_bytes = b"".join(body_chunks)
            logger.warning(
                "runtime-proxy %s %s -> %s (%s): %s",
                request.method,
                path,
                upstream.status_code,
                target,
                body_bytes.decode("utf-8", errors="replace")[:500],
            )
            from fastapi.responses import Response as _Resp

            media = upstream.headers.get("content-type", "application/octet-stream")
            await upstream.aclose()
            await client.aclose()
            return _Resp(
                content=body_bytes,
                status_code=upstream.status_code,
                media_type=media,
            )

        async def _body():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        media = upstream.headers.get("content-type", "application/octet-stream")
        return StreamingResponse(
            _body(), status_code=upstream.status_code, media_type=media
        )

    # ---- Auth ----------------------------------------------------------------
    # 'gateway' mode: an upstream API gateway (the AgentKit runtime gateway) has
    # already authenticated the user and forwards the identity as an
    # `Authorization: Bearer <JWT>`. Trust it — resolve the user from the token's
    # claims and run no in-app login. 'frontend' (default) keeps the existing
    # behavior where this server runs its own OAuth2 login.
    if auth_mode == "gateway":
        from fastapi.responses import JSONResponse

        @app.get("/oauth2/userinfo")
        async def _userinfo_gateway(request: Request):
            claims = _claims_from_forwarded_jwt(request.headers.get("authorization"))
            if not claims:
                # Gateway should always forward a token; if absent, report
                # unauthenticated so the SPA's auth check resolves cleanly.
                return JSONResponse({"status": "unauthenticated"}, status_code=401)
            uid = claims.get("sub") or claims.get("user_id") or claims.get("email")
            return {
                "sub": uid,
                "user_id": uid,
                "email": claims.get("email"),
                "name": claims.get("name") or claims.get("preferred_username"),
            }

        @app.get("/web/auth-config")
        async def _web_auth_config_gateway():
            # The gateway already authenticated the user — no in-app login buttons.
            return {"providers": []}

        logger.info("Auth mode: gateway (trusting upstream-forwarded JWT identity)")
    else:
        # ---- SSO (optional): VeIdentity user pool, or a generic provider via env ----
        redirect_uri = oauth2_redirect_uri or f"http://{host}:{port}/oauth2/callback"
        pool_ok = oauth2_user_pool or oauth2_user_pool_uid
        client_ok = oauth2_user_pool_client or oauth2_user_pool_client_uid
        provider_id = oauth2_provider or ""

        oauth2_config = None
        if pool_ok and client_ok:
            from veadk.auth.middleware.oauth2_auth import OAuth2Config

            oauth2_config = OAuth2Config.from_veidentity(
                user_pool_name=oauth2_user_pool,
                user_pool_uid=oauth2_user_pool_uid,
                client_name=oauth2_user_pool_client,
                client_uid=oauth2_user_pool_client_uid,
                redirect_uri=redirect_uri,
            )
            provider_id = provider_id or "veidentity"
        else:
            # Generic provider (github / google / any OIDC / custom) from env vars.
            oauth2_config = _build_generic_oauth2(provider_id or "custom", redirect_uri)
            provider_id = provider_id or "custom"

        # The SPA fetches /web/auth-config and /oauth2/userinfo on every startup, so
        # both must always return JSON. With SSO off we answer with an empty provider
        # list and a 401 (unauthenticated), and the app renders its normal no-login
        # UI; otherwise the SPA-fallback serves the HTML shell for these paths and the
        # app's `await res.json()` throws, leaving a white screen.
        providers: list[dict] = []

        if oauth2_config is not None:
            from urllib.parse import urlsplit

            from veadk.auth.middleware.oauth2_auth import setup_oauth2

            # Cookies require Secure over HTTPS (runtime deploys) but must also work
            # over plain HTTP for local serving.
            oauth2_config.cookie_secure = redirect_uri.lower().startswith("https://")
            # After logout, return to the app root derived from the callback origin
            # (so it is correct behind a public host), skipping the IdP end-session
            # redirect (its post-logout URL must be whitelisted by the IdP).
            origin = urlsplit(redirect_uri)
            oauth2_config.logout_redirect_url = f"{origin.scheme}://{origin.netloc}/"
            oauth2_config.end_session_url = None

            # Expose the configured provider to the login page (unauthenticated).
            label = (
                oauth2_provider_label
                or _PROVIDER_LABELS.get(provider_id)
                or provider_id.replace("_", " ").title()
            )
            providers = [
                {"id": provider_id, "label": label, "loginUrl": "/oauth2/login"}
            ]

            # Protect the API but exempt the SPA shell + this config endpoint so the
            # app can load and render its own login page when not signed in.
            setup_oauth2(
                app,
                oauth2_config,
                exempt_paths={
                    "/",
                    "/index.html",
                    "/favicon.ico",
                    "/web/auth-config",
                    "/web/site-logo",
                    "/web/ui-config",
                },
                exempt_prefixes={"/assets", "/skillhub"},
            )
            logger.info(
                f"OAuth2 SSO enabled (provider={provider_id}, redirect_uri={redirect_uri})"
            )
        else:
            from fastapi.responses import JSONResponse

            @app.get("/oauth2/userinfo")
            async def _userinfo_no_sso():
                # No SSO configured: report unauthenticated (401) so the SPA's auth
                # check resolves cleanly instead of parsing the HTML shell as JSON.
                return JSONResponse({"status": "unauthenticated"}, status_code=401)

        @app.get("/web/auth-config")
        async def _web_auth_config():
            # Empty provider list when SSO is off -> the SPA shows its normal UI.
            return {"providers": providers}

    @app.get("/web/runtime-config")
    async def _web_runtime_config():
        # Report whether Volcengine AK/SK are present in the server environment.
        # The agent-creation workbench needs them to call Volcengine services, so
        # the SPA shows a "set AK/SK" notice when they are absent.
        has_creds = bool(
            os.getenv("VOLCENGINE_ACCESS_KEY") and os.getenv("VOLCENGINE_SECRET_KEY")
        ) or os.path.exists("/var/run/secrets/iam/credential")
        return {"credentials": has_creds}

    # ---- SkillSpace proxy (AgentKit account-scoped skills) ----------------
    # These routes sign requests with the SERVER's Volcengine credentials (same
    # chain /web/deploy-agentkit uses) and sit under /web/* so the OAuth2
    # middleware gates them by SSO session when SSO is enabled. The browser
    # never sees AK/SK. v1 only returns SKILL.md (SkillMd) content, not the
    # full TOS zip; that keeps the surface small and mirrors how the public
    # Skill Hub picker only needs markdown for basic skills.

    def _skills_client(region: str):
        """Build an AgentkitSkillsClient using server-side creds, or raise
        HTTPException(409) if creds aren't configured."""
        from agentkit.sdk.skills.client import AgentkitSkillsClient

        try:
            ak, sk, token = _resolve_ve_credentials()
        except HTTPException:
            raise HTTPException(
                status_code=409,
                detail="Server Volcengine credentials not configured "
                "(set VOLCENGINE_ACCESS_KEY/SECRET_KEY).",
            )
        return AgentkitSkillsClient(
            access_key=ak,
            secret_key=sk,
            region=region,
            session_token=token or "",
        )

    @app.get("/web/skill-spaces")
    async def _web_list_skill_spaces(region: str = "all"):
        """List SkillSpaces visible to the server's credentials. Fetches from
        both cn-beijing and cn-shanghai when region=all."""
        from agentkit.sdk.skills.types import ListSkillSpacesRequest

        regions = ["cn-beijing", "cn-shanghai"] if region == "all" else [region]
        all_items = []

        for reg in regions:
            try:
                client = _skills_client(reg)
                resp = client.list_skill_spaces(
                    ListSkillSpacesRequest(page_number=1, page_size=50)
                )
                for s in resp.items or []:
                    all_items.append(
                        {
                            "id": s.id or "",
                            "name": s.name or "",
                            "description": s.description or "",
                            "status": s.status or "",
                            "region": reg,
                        }
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"ListSkillSpaces error for {reg}: {e}", exc_info=True)
                raise HTTPException(
                    status_code=502, detail=f"SkillSpaces API error for {reg}: {e}"
                )

        return {
            "items": all_items,
            "totalCount": len(all_items),
        }

    @app.get("/web/skill-spaces/{space_id}/skills")
    async def _web_list_skills_in_space(space_id: str, region: str = "cn-beijing"):
        """List skills in one SkillSpace (relation view: id/name/description/
        version/status per skill)."""
        from agentkit.sdk.skills.types import ListSkillsBySkillSpaceRequest

        try:
            client = _skills_client(region)
            resp = client.list_skills_by_skill_space(
                ListSkillsBySkillSpaceRequest(
                    skill_space_id=space_id, page_number=1, page_size=100
                )
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"ListSkillsBySkillSpace({space_id}) error for {region}: {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=502, detail=f"SkillSpaces API error for {region}: {e}"
            )

        items = list(resp.items or [])
        return {
            "items": [
                {
                    "skillId": r.skill_id or "",
                    "skillName": r.skill_name or "",
                    "skillDescription": r.skill_description or "",
                    "version": r.version or "",
                    "skillStatus": r.skill_status or "",
                }
                for r in items
            ],
            "totalCount": resp.total_count or len(items),
        }

    @app.get("/web/skill-spaces/{space_id}/skills/{skill_id}")
    async def _web_get_skill_detail(
        space_id: str,
        skill_id: str,
        version: str | None = None,
        region: str = "cn-beijing",
    ):
        """Fetch a specific skill version's SKILL.md content (SkillMd) plus
        metadata. v1 returns SkillMd only; the TOS zip (scripts/assets) is a
        follow-up."""
        from agentkit.sdk.skills.types import GetSkillVersionRequest

        try:
            client = _skills_client(region)
            resp = client.get_skill_version(
                GetSkillVersionRequest(id=skill_id, skill_version=version)
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"GetSkillVersion({skill_id}@{version}) error: {e}", exc_info=True
            )
            raise HTTPException(status_code=502, detail=f"SkillSpaces API error: {e}")

        if not resp.skill_md:
            raise HTTPException(
                status_code=404, detail="Skill version has no SKILL.md content"
            )

        return {
            "skillId": skill_id,
            "skillSpaceId": space_id,
            "name": resp.name or "",
            "description": resp.description or "",
            "version": resp.version or version or "",
            "skillMd": resp.skill_md,
            "bucketName": resp.bucket_name or "",
            "tosPath": resp.tos_path or "",
        }

    if vite:
        logger.info(
            f"A2UI Vite mode: API on http://{host}:{port} (no bundled UI), "
            f"run `cd frontend && npm run dev` and open {DEV_SERVER_ORIGIN}"
        )
    else:
        import re as _re

        from fastapi.responses import FileResponse, HTMLResponse
        from fastapi.staticfiles import StaticFiles

        webui = _resolve_frontend_dir(frontend_dir)
        if not (webui / "index.html").is_file():
            raise click.ClickException(
                f"Built UI not found at {webui}. Build it with: "
                "cd frontend && npm install && npm run build "
                "(or use --dev for the Vite dev server)."
            )

        _index_html = (webui / "index.html").read_text(encoding="utf-8")
        _ASSET_REF = _re.compile(r'((?:src|href)=")(/[^"?]+)(")')

        def _render_index(request: Request) -> HTMLResponse:
            # When behind a query-string API gateway (e.g. an AgentKit runtime
            # with the key in the query string), the browser's subresource
            # requests for /assets/* must also carry the key. The key arrives as
            # the page's querystring; forward it onto every same-origin asset URL
            # in the served HTML so those requests pass the gateway too. (The
            # app's own API/navigation requests already forward it via auth.ts.)
            qs = request.url.query
            if not qs:
                return HTMLResponse(_index_html)
            html = _ASSET_REF.sub(
                lambda m: f"{m.group(1)}{m.group(2)}?{qs}{m.group(3)}", _index_html
            )
            return HTMLResponse(html)

        # Built assets (the gateway has already authorized the request).
        app.mount(
            "/assets", StaticFiles(directory=str(webui / "assets")), name="assets"
        )

        @app.get("/")
        async def _spa_root(request: Request):
            return _render_index(request)

        # SPA fallback: serve real static files as-is, otherwise return the
        # (querystring-injected) HTML shell. Registered last so it never shadows
        # the API routes above.
        _webui_root = webui.resolve()

        @app.get("/{path:path}")
        async def _spa_fallback(path: str, request: Request):
            # Resolve and confine to the UI directory — a path like
            # "../../etc/passwd" must NOT escape `webui` (arbitrary file read).
            candidate = (webui / path).resolve()
            if path and candidate.is_relative_to(_webui_root) and candidate.is_file():
                return FileResponse(str(candidate))
            return _render_index(request)

        logger.info(
            f"A2UI UI + API serving on http://{host}:{port} (UI: {webui}, agents: {agents_dir})"
        )

    # Open the UI in the browser once the server is up. Only when this server
    # serves the UI; with --vite the Vite dev server owns it.
    if open_browser and not vite:
        import threading

        browse_host = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
        url = f"http://{browse_host}:{port}"
        threading.Thread(
            target=_open_browser_when_ready,
            args=(url, browse_host, port),
            daemon=True,
        ).start()
        logger.info(f"Opening {url} in your browser…")

    import uvicorn

    uvicorn.run(app, host=host, port=port)


def _studio_deploy_run_script(site_logo_filename: str | None = None) -> str:
    """Return the authenticated VeFaaS entrypoint used by ``studio deploy``."""
    from veadk.cli.studio_package import studio_run_script

    return studio_run_script(site_logo_filename)


def _resolve_studio_identity_region(
    *,
    access_key: str,
    secret_key: str,
    user_pool_id: str,
    client_id: str,
    deployment_region: str,
) -> str:
    """Locate a Studio user-pool client across supported Identity regions."""
    from veadk.integrations.ve_identity.identity_client import IdentityClient

    supported_regions = ("cn-beijing", "cn-shanghai")
    candidate_regions = (deployment_region,) + tuple(
        region for region in supported_regions if region != deployment_region
    )
    for candidate_region in candidate_regions:
        identity_client = IdentityClient(
            access_key=access_key,
            secret_key=secret_key,
            region=candidate_region,
        )
        if identity_client.user_pool_client_exists(
            user_pool_uid=user_pool_id,
            client_uid=client_id,
        ):
            return candidate_region
    raise click.ClickException(
        "VeIdentity user pool/client not found in cn-beijing or cn-shanghai."
    )


@studio.command("deploy")
@click.option(
    "--user-pool-id",
    required=True,
    help="VeIdentity User Pool UID that gates access (the gateway does SSO against it).",
)
@click.option(
    "--allowed-client-id",
    required=True,
    help="VeIdentity client UID used for the SSO login at the gateway.",
)
@click.option(
    "--client-secret",
    default="",
    help="Client secret, if it cannot be read back from the client UID.",
)
@click.option(
    "--vefaas-app-name",
    required=True,
    help="VeFaaS application/function name (4-64 chars, letters/digits/-, no underscore).",
)
@click.option(
    "--region",
    default="cn-beijing",
    show_default=True,
    type=click.Choice(["cn-beijing", "cn-shanghai"]),
    help="Volcengine region for Studio deployment.",
)
@click.option(
    "--project",
    default="default",
    show_default=True,
    help="Volcengine project for the VeFaaS function.",
)
@click.option(
    "--iam-role",
    default=None,
    help="Pre-existing IAM role TRN to bind to the function. If omitted, a role "
    "is auto-created with the frontend deploy policy.",
)
@click.option(
    "--gateway-name",
    default="",
    help="Serverless APIG gateway name to use. Default: auto-discover an "
    "existing serverless gateway and reuse it, creating one only if none exists.",
)
@click.option("--gateway-service-name", default="")
@click.option("--gateway-upstream-name", default="")
@click.option("--volcengine-access-key", default=None)
@click.option("--volcengine-secret-key", default=None)
@click.option(
    "--veadk-version",
    default="",
    help="Pin the veadk-python version in the function's requirements.txt "
    "(default: latest). The deployed UI is that version's veadk/webui.",
)
@click.option(
    "--from-source",
    is_flag=True,
    default=False,
    help="Build a wheel from THIS checkout (incl. uncommitted changes + the "
    "current veadk/webui) and ship it, instead of installing veadk-python from "
    "PyPI. Use to deploy unreleased frontend/backend changes.",
)
@click.option(
    "--site-logo",
    default=None,
    help="Studio logo as a local image path or HTTP(S) URL; the image is "
    "bundled into the deployed function.",
)
@click.option(
    "--site-title",
    default=None,
    help="Studio title, at most 6 characters.",
)
@click.option(
    "--admin",
    "studio_admins",
    default=None,
    envvar="VEADK_STUDIO_ADMINS",
    help="Comma-separated Studio admin usernames or OAuth emails. Omit both "
    "role options to grant every user admin access.",
)
@click.option(
    "--developer",
    "studio_developers",
    default=None,
    envvar="VEADK_STUDIO_DEVELOPERS",
    help="Comma-separated Studio developer usernames or OAuth emails.",
)
def frontend_deploy(
    user_pool_id: str,
    allowed_client_id: str,
    client_secret: str,
    vefaas_app_name: str,
    region: str,
    project: str,
    iam_role: str | None,
    gateway_name: str,
    gateway_service_name: str,
    gateway_upstream_name: str,
    volcengine_access_key: str | None,
    volcengine_secret_key: str | None,
    veadk_version: str,
    from_source: bool,
    site_logo: str | None,
    site_title: str | None,
    studio_admins: str | None,
    studio_developers: str | None,
) -> None:
    """Deploy the SSO web frontend to VeFaaS.

    Builds a minimal function that runs `veadk studio --auth-mode frontend`,
    with in-app SSO bound to the given VeIdentity user pool + client, and prints
    the public URL. Inside the function the frontend uses the bound IAM role's
    STS credentials to manage AgentKit runtimes.
    """
    import tempfile
    import shutil

    from veadk.config import getenv, veadk_environments

    try:
        branding_title = normalize_site_title(site_title)
        branding_logo = resolve_site_logo(site_logo)
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    ak = volcengine_access_key or getenv("VOLCENGINE_ACCESS_KEY")
    sk = volcengine_secret_key or getenv("VOLCENGINE_SECRET_KEY")
    if not ak or not sk:
        raise click.ClickException(
            "Volcengine credentials required: set VOLCENGINE_ACCESS_KEY/SECRET_KEY "
            "or pass --volcengine-access-key/--volcengine-secret-key."
        )

    identity_region = _resolve_studio_identity_region(
        access_key=ak,
        secret_key=sk,
        user_pool_id=user_pool_id,
        client_id=allowed_client_id,
        deployment_region=region,
    )
    if identity_region != region:
        click.secho(
            f"Warning: Studio deploys to {region}, but the VeIdentity user "
            f"pool/client was found in {identity_region}. Continuing with "
            f"Identity region {identity_region}.",
            fg="yellow",
        )

    # 1) Ensure VeFaaS has its service role before provisioning cloud resources.
    from veadk.cli.studio_deploy_serverless_iam import (
        ensure_serverless_application_role,
    )

    ensure_serverless_application_role(ak, sk)

    # 2) Ensure the IAM role the function runs as (auto-create unless provided).
    if iam_role:
        role_trn = iam_role
        click.echo(f"Using provided IAM role: {role_trn}")
    else:
        from veadk.cli.frontend_deploy_iam import ensure_frontend_role

        click.echo("Ensuring IAM role + policy…")
        role_trn = ensure_frontend_role(ak, sk)
        click.echo(f"IAM role ready: {role_trn}")
    # Consumed by VeFaaS._create_function as the function's Role (STS creds are
    # then injected into the instance); read via getenv from os.environ, NOT
    # shipped as a plain env var.
    os.environ["IAM_ROLE"] = role_trn

    # SECURITY: VeFaaS._create_function uploads *everything* in veadk_environments
    # (i.e. the deployer's whole .env) as function env vars. The frontend must
    # NOT receive the deployer's secrets (VOLCENGINE_ACCESS_KEY/SECRET_KEY, model
    # API keys, DB passwords). It authenticates to Volcengine via its IAM role's
    # STS credentials (see _resolve_ve_credentials — env AK/SK would otherwise
    # wrongly take precedence). So reset to a minimal, explicit, non-secret env.
    #
    # The frontend does SSO itself (--auth-mode frontend): a serverless APIG
    # gateway can only carry veFaaS upstreams, so the gateway-plugin OAuth path
    # (which needs a domain upstream to the user pool) can't run on VeFaaS.
    # `veadk frontend` resolves the client secret + registers the callback from
    # the pool/client UID via from_veidentity, so we only ship the UIDs here.
    veadk_environments.clear()
    veadk_environments["OAUTH2_USER_POOL_ID"] = user_pool_id
    veadk_environments["OAUTH2_USER_POOL_CLIENT_ID"] = allowed_client_id
    veadk_environments["OAUTH2_PROVIDER"] = "veidentity"
    veadk_environments["VEIDENTITY_REGION"] = identity_region
    if site_title is not None:
        veadk_environments["VEADK_SITE_TITLE"] = branding_title
    if studio_admins:
        veadk_environments["VEADK_STUDIO_ADMINS"] = studio_admins
    if studio_developers:
        veadk_environments["VEADK_STUDIO_DEVELOPERS"] = studio_developers
    if client_secret:
        veadk_environments["OAUTH2_CLIENT_SECRET"] = client_secret

    # 3) Build the function project (zip): run.sh launches the frontend server on
    #    the FaaS-assigned port; requirements.txt pulls veadk-python (ships the UI).
    requirements = (
        f"veadk-python=={veadk_version}\n" if veadk_version else "veadk-python\n"
    )
    # 3b) Resolve the serverless APIG gateway: use --gateway-name if given, else
    #     reuse an existing serverless gateway, creating one only if none exists.
    #     (VeFaaS applications can only attach to a serverless gateway; reusing
    #     avoids the per-account gateway quota.)
    from veadk.integrations.ve_apig.ve_apig import APIGateway

    if not gateway_name:
        apig = APIGateway(ak, sk, region)
        gw = apig.find_serverless_gateway()
        if gw is not None:
            gateway_name = getattr(gw, "name")
            click.echo(f"Reusing serverless gateway: {gateway_name}")
        else:
            gateway_name = "veadk-frontend-gw"
            click.echo(f"No serverless gateway found; creating '{gateway_name}'…")
            apig.create_serverless_gateway(gateway_name)
            click.echo(f"Created serverless gateway: {gateway_name}")

    tmp = tempfile.mkdtemp(prefix=f"veadk_frontend_deploy_{vefaas_app_name}_")
    try:
        # When --from-source, build a wheel from this checkout (picks up
        # uncommitted changes + the current veadk/webui) and install it instead
        # of the PyPI release, so the deployed frontend runs this branch's code.
        if from_source:
            import veadk

            from veadk.cli.studio_package import build_local_studio_requirements

            repo_root = Path(veadk.__file__).resolve().parent.parent
            click.echo(f"Building wheel from source at {repo_root}…")
            try:
                requirements = build_local_studio_requirements(repo_root, Path(tmp))
            except ValueError as error:
                raise click.ClickException(f"--from-source: {error}") from error

        from veadk.cli.studio_package import write_studio_package

        write_studio_package(
            Path(tmp),
            requirements=requirements,
            site_logo=branding_logo,
        )

        # 3) Deploy the function + a plain public APIG trigger on the serverless
        #    gateway (auth_method="none" — no gateway SSO plugin / domain upstream).
        from veadk.cloud.cloud_agent_engine import CloudAgentEngine

        engine = CloudAgentEngine(
            volcengine_access_key=ak,
            volcengine_secret_key=sk,
            region=region,
            project=project,
        )
        click.echo(
            f"Deploying frontend to VeFaaS as '{vefaas_app_name}' "
            f"in {region}/{project}…"
        )
        app = engine.deploy(
            application_name=vefaas_app_name,
            path=tmp,
            gateway_name=gateway_name,
            gateway_service_name=gateway_service_name,
            gateway_upstream_name=gateway_upstream_name,
            use_adk_web=False,
            auth_method="none",
        )
        url = (app.vefaas_endpoint or "").rstrip("/")
        redirect_uri = f"{url}/oauth2/callback"

        # 4) Register the SSO callback on the user-pool client HERE, with the
        #    deployer's full credentials — the function's IAM role is granted
        #    only read access to Identity (id:GetUserPoolClient), not
        #    id:UpdateUserPoolClient, so it can't register the callback itself.
        if url:
            try:
                from veadk.integrations.ve_identity.identity_client import (
                    IdentityClient,
                )

                IdentityClient(
                    access_key=ak, secret_key=sk, region=identity_region
                ).register_callback_for_user_pool_client(
                    user_pool_uid=user_pool_id,
                    client_uid=allowed_client_id,
                    callback_url=redirect_uri,
                    web_origin=url,
                    dismiss_login_page_enabled=False,
                    skip_consent_enabled=True,
                )
                click.echo(f"Registered SSO callback: {redirect_uri}")
            except Exception as e:
                click.echo(
                    f"⚠️  Could not register the SSO callback ({e}). Add "
                    f"{redirect_uri} to the user-pool client's allowed callback URLs manually."
                )

        # 5) Two-phase: now that the public URL is known, inject the correct
        #    OAuth redirect and re-release so in-app SSO points at this endpoint.
        function_id = getattr(app, "vefaas_function_id", "")
        if url and function_id:
            click.echo(f"Setting OAUTH2_REDIRECT_URI={redirect_uri} and re-releasing…")
            engine._vefaas_service.update_function_envs_and_release(
                function_id, {"OAUTH2_REDIRECT_URI": redirect_uri}
            )

        click.echo("")
        click.echo(f"✅ Frontend deployed: {url}")
        click.echo(f"   application id: {app.vefaas_application_id}")
        click.echo("   (open the URL — you'll be redirected through SSO login)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@studio.command("update")
@click.option(
    "--vefaas-app-name",
    required=True,
    help="Existing VeFaaS Application name to update.",
)
@click.option(
    "--region",
    default=None,
    type=click.Choice(["cn-beijing", "cn-shanghai"]),
    help="Limit Application lookup to one region (default: search both).",
)
@click.option(
    "--project",
    default=None,
    help="Limit Application lookup to one project (default: search all visible projects).",
)
@click.option(
    "--path",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="VeADK source checkout whose frontend will be built and uploaded.",
)
@click.option(
    "--site-logo",
    default=None,
    help="Replace the deployed Studio logo with a local image or HTTP(S) URL.",
)
@click.option(
    "--site-title",
    default=None,
    help="Replace the deployed Studio title, at most 6 characters.",
)
@click.option("--volcengine-access-key", default=None)
@click.option("--volcengine-secret-key", default=None)
def frontend_update(
    vefaas_app_name: str,
    region: str | None,
    project: str | None,
    path: Path,
    site_logo: str | None,
    site_title: str | None,
    volcengine_access_key: str | None,
    volcengine_secret_key: str | None,
) -> None:
    """Build local Studio sources and update an existing VeFaaS Application."""
    import shutil
    import tempfile

    from veadk.cli.studio_package import (
        build_frontend_assets,
        build_local_studio_requirements,
        write_studio_package,
    )
    from veadk.cli.studio_update import (
        find_studio_deployments,
        load_deployed_site_logo,
    )
    from veadk.config import getenv
    from veadk.integrations.ve_faas.ve_faas import VeFaaS

    ak = volcengine_access_key or getenv("VOLCENGINE_ACCESS_KEY")
    sk = volcengine_secret_key or getenv("VOLCENGINE_SECRET_KEY")
    if not ak or not sk:
        raise click.ClickException(
            "Volcengine credentials required: set VOLCENGINE_ACCESS_KEY/SECRET_KEY "
            "or pass --volcengine-access-key/--volcengine-secret-key."
        )

    targets = find_studio_deployments(
        access_key=ak,
        secret_key=sk,
        application_name=vefaas_app_name,
        region=region,
        project=project,
    )
    if not targets:
        scope = "/".join(value for value in (region, project) if value) or (
            "cn-beijing and cn-shanghai across all visible projects"
        )
        raise click.ClickException(
            f"VeFaaS Application '{vefaas_app_name}' was not found in {scope}."
        )
    if len(targets) > 1:
        candidates = "\n".join(
            f"  - {target.region}/{target.project} "
            f"(Application ID: {target.application_id})"
            for target in targets
        )
        raise click.ClickException(
            f"Multiple VeFaaS Applications named '{vefaas_app_name}' were found. "
            "Specify --region and/or --project:\n"
            f"{candidates}"
        )
    target = targets[0]

    try:
        branding_logo = (
            resolve_site_logo(site_logo)
            if site_logo is not None
            else load_deployed_site_logo(target)
        )
        branding_title = (
            normalize_site_title(site_title) if site_title is not None else None
        )
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    source_root = path.expanduser().resolve()
    tmp = Path(tempfile.mkdtemp(prefix=f"veadk_studio_update_{vefaas_app_name}_"))
    package_dir = tmp / "package"
    try:
        click.echo(f"Building Studio frontend from {source_root}…")
        frontend_assets = tmp / "frontend"
        try:
            build_frontend_assets(source_root, frontend_assets)
            requirements = build_local_studio_requirements(
                source_root,
                package_dir,
                frontend_assets=frontend_assets,
            )
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        write_studio_package(
            package_dir,
            requirements=requirements,
            site_logo=branding_logo,
        )

        click.echo(f"Updating '{vefaas_app_name}' in {target.region}/{target.project}…")
        service = VeFaaS(
            access_key=ak,
            secret_key=sk,
            region=target.region,
            project_name=target.project,
        )
        environment_overrides = (
            {"VEADK_SITE_TITLE": branding_title} if branding_title is not None else None
        )
        url = service.update_application_code_bundle(
            application_id=target.application_id,
            function_id=target.function_id,
            path=str(package_dir),
            environment_overrides=environment_overrides,
        )
        click.echo("")
        click.echo(f"✅ Studio updated: {url}")
        click.echo(f"   application id: {target.application_id}")
        click.echo(f"   function id: {target.function_id}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
