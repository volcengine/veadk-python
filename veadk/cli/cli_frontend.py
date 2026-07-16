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

import os
import json

from pathlib import Path

import click

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


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

# Built UI shipped inside the package (output of `npm run build`).
PACKAGED_WEBUI = Path(__file__).resolve().parent.parent / "webui"


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
    incoming_headers: dict[str, str], api_key: str | None
) -> dict[str, str]:
    """Return headers safe to forward from the local proxy to AgentKit."""
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
    open_browser: bool,
) -> None:
    """Launch the A2UI web UI backed by the ADK agent API server."""
    if ctx.invoked_subcommand is not None:
        return
    _run_frontend_server(
        agents_dir=agents_dir,
        frontend_dir=frontend_dir,
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
        open_browser=open_browser,
        studio=True,
    )


def _run_frontend_server(
    *,
    agents_dir: str,
    frontend_dir: str | None,
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
    open_browser: bool,
    studio: bool = False,
) -> None:
    """Launch the A2UI web UI backed by the ADK agent API server."""

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
    allow_origins = [DEV_SERVER_ORIGIN] if vite else []

    app = get_fast_api_app(
        agents_dir=agents_dir,
        allow_origins=allow_origins,
        web=False,  # we serve our own UI, not the bundled ADK dev UI
    )

    # Agent introspection for the UI's agent picker (name, model, tools). Reuses
    # ADK's AgentLoader, which caches each loaded `root_agent`.
    from fastapi import HTTPException, Request
    from fastapi.responses import Response
    from google.adk.cli.utils.agent_loader import AgentLoader
    import httpx

    _agent_loader = AgentLoader(agents_dir)

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

    def _agent_node(agent: object, depth: int = 0) -> dict:
        # Recursive typed tree for the conversation topology panel. Depth is
        # bounded so a pathological sub_agents cycle can't spin forever.
        children = []
        if depth < 8:
            children = [
                _agent_node(s, depth + 1)
                for s in getattr(agent, "sub_agents", []) or []
            ]
        return {
            "name": getattr(agent, "name", "") or "",
            "description": getattr(agent, "description", "") or "",
            "type": _agent_type(agent),
            "model": _model_name(getattr(agent, "model", "")),
            "tools": [_tool_label(t) for t in getattr(agent, "tools", []) or []],
            "children": children,
        }

    @app.get("/web/ui-config")
    async def _web_ui_config():
        """Feature gates the SPA reads at startup. Studio now serves the SAME UI
        as `veadk frontend` — all modules (chat/search/skill-center/history +
        add/manage agent) enabled, landing on the chat view. The `studio` flag
        is informational."""
        return {
            "studio": studio,
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
            "subAgents": [
                getattr(s, "name", "") for s in getattr(agent, "sub_agents", []) or []
            ],
            # Recursive typed tree used by the conversation topology panel.
            "graph": _agent_node(agent),
        }

    # Tool names that count as "web search is mounted" on an agent.
    _WEB_SEARCH_TOOLS = {"web_search", "parallel_web_search", "vesearch"}

    def _web_search_aksk() -> tuple[str | None, str | None]:
        ak = os.getenv("TOOL_WEB_SEARCH_ACCESS_KEY") or os.getenv(
            "VOLCENGINE_ACCESS_KEY"
        )
        sk = os.getenv("TOOL_WEB_SEARCH_SECRET_KEY") or os.getenv(
            "VOLCENGINE_SECRET_KEY"
        )
        return ak, sk

    @app.get("/web/search")
    async def _web_search(source: str, app_name: str, q: str):
        """Smart-search 'web' source: run the Volcengine WebSearch API with the
        server's env credentials. Returns mounted=False when a *known* agent has
        no web-search tool; unknown/remote agents are searched anyway."""
        if source != "web":
            raise HTTPException(status_code=400, detail=f"unsupported source: {source}")
        if not q.strip():
            return {"mounted": True, "results": []}

        # Gate on the agent's tools only when we can introspect it locally.
        try:
            agent = _agent_loader.load_agent(app_name)
        except ValueError:
            agent = None
        if agent is not None:
            tools = [_tool_label(t) for t in getattr(agent, "tools", []) or []]
            if not any(t in _WEB_SEARCH_TOOLS for t in tools):
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

    import threading as _threading

    _deploy_lock = _threading.Lock()

    @app.post("/web/deploy-agentkit")
    async def _deploy_to_agentkit(request: Request):
        """Deploy to AgentKit, streaming per-stage progress as Server-Sent Events.

        Body: {name, files:[{path,content}], config:{region,projectName}, author?}.
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

        data = await request.json()
        agent_name = (data.get("name") or "").strip()
        files = data.get("files", [])
        config = data.get("config", {})
        author = (data.get("author") or "").strip()
        if not agent_name:
            raise HTTPException(status_code=400, detail="Agent name is required")
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        region = config.get("region", "cn-beijing")
        project_name = config.get("projectName", "default")

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

        agentkit_config = {
            "common": {
                "agent_name": agent_name,
                "entry_point": "app.py",
                "python_version": "3.11",
                "launch_type": "cloud",
            },
            "launch_types": {
                "cloud": {
                    "region": region,
                    "project_name": project_name,
                    "image_tag": "latest",
                    "runtime_envs": {
                        "MODEL_AGENT_API_KEY": os.getenv("MODEL_AGENT_API_KEY", ""),
                        "OTEL_SDK_DISABLED": "true",
                        "VEADK_DISABLE_EXPIRE_AT": "true",
                    },
                }
            },
        }
        (base / "agentkit.yaml").write_text(
            _yaml.dump(agentkit_config, allow_unicode=True), encoding="utf-8"
        )

        events: "_queue.Queue" = _queue.Queue()
        state = {"phase": "build"}

        _PHASE_ORDER = {"build": 0, "deploy": 1, "publish": 2}

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

                    def _tagged_create(self, req, _orig=orig_create, _extra=extra):
                        req.tags = [*(req.tags or []), *_extra]
                        return _orig(self, req)

                    rt_client.create_runtime = _tagged_create
                except Exception as e:
                    logger.warning(f"Could not attach author tag to runtime: {e}")

                try:
                    result_box["result"] = sdk.launch(
                        config_file=str(base / "agentkit.yaml"),
                        preflight_mode=PreflightMode.WARN,
                        reporter=_QReporter(),
                    )
                except Exception as e:
                    logger.error(f"AgentKit launch error: {e}", exc_info=True)
                    result_box["error"] = str(e)
                finally:
                    if rt_client is not None and orig_create is not None:
                        rt_client.create_runtime = orig_create
            events.put(None)  # sentinel: launch finished

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
                    final.update(
                        {
                            "success": False,
                            "error": result_box["error"],
                            "phase": state["phase"],
                        }
                    )
                else:
                    res = result_box.get("result")
                    dr = getattr(res, "deploy_result", None) if res else None
                    if res is not None and getattr(res, "success", False):
                        meta = (dr.metadata if (dr and dr.metadata) else {}) or {}
                        final.update(
                            {
                                "success": True,
                                "agentName": agent_name,
                                "url": getattr(dr, "endpoint_url", None)
                                if dr
                                else None,
                                "apikey": meta.get("runtime_apikey", ""),
                                "runtimeId": meta.get("runtime_id", ""),
                                "consoleUrl": (
                                    "https://console.volcengine.com/agentkit/"
                                    f"region:agentkit+{region}/runtime?projectName={project_name}"
                                ),
                            }
                        )
                    else:
                        err = getattr(res, "error", None) if res else None
                        final.update(
                            {
                                "success": False,
                                "error": err or "Deployment failed",
                                "phase": state["phase"],
                            }
                        )
                yield f"data: {_json.dumps(final, ensure_ascii=False)}\n\n"
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        from fastapi.responses import StreamingResponse

        return StreamingResponse(_stream(), media_type="text/event-stream")

    @app.get("/web/my-runtimes")
    async def _web_my_runtimes(author: str = "", region: str = "cn-beijing"):
        """List AgentKit runtimes created via this UI (tagged veadk:managed),
        optionally filtered to a single `author` (veadk:author tag)."""
        ak, sk, token = _resolve_ve_credentials()
        try:
            from agentkit.sdk.runtime.client import AgentkitRuntimeClient
            from agentkit.sdk.runtime import types as _rt

            client = AgentkitRuntimeClient(
                access_key=ak, secret_key=sk, session_token=token, region=region
            )
            out: list[dict] = []
            token = None
            for _ in range(20):  # page cap
                kw = {"page_size": 100}
                if token:
                    kw["next_token"] = token
                resp = client.list_runtimes(_rt.ListRuntimesRequest(**kw))
                for r in resp.agent_kit_runtimes or []:
                    tags = {tg.key: tg.value for tg in (r.tags or [])}
                    if tags.get("veadk:managed") != "true":
                        continue
                    if author and tags.get("veadk:author") != author:
                        continue
                    out.append(
                        {
                            "name": r.name,
                            "runtimeId": r.runtime_id,
                            "status": r.status,
                            "createdAt": r.created_at,
                            "author": tags.get("veadk:author", ""),
                            "region": region,
                        }
                    )
                token = getattr(resp, "next_token", None)
                if not token:
                    break
            out.sort(key=lambda x: x.get("createdAt") or "", reverse=True)
            return {"runtimes": out}
        except Exception as e:
            logger.error(f"list my-runtimes failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

    @app.post("/web/delete-runtime")
    async def _web_delete_runtime(request: Request):
        """Delete an AgentKit runtime by id (used by the '管理 Agent' view)."""
        data = await request.json()
        runtime_id = (data.get("runtimeId") or "").strip()
        region = (data.get("region") or "cn-beijing").strip()
        if not runtime_id:
            raise HTTPException(status_code=400, detail="runtimeId is required")
        ak, sk, token = _resolve_ve_credentials()
        try:
            from agentkit.sdk.runtime.client import AgentkitRuntimeClient
            from agentkit.sdk.runtime import types as _rt

            client = AgentkitRuntimeClient(
                access_key=ak, secret_key=sk, session_token=token, region=region
            )
            client.delete_runtime(_rt.DeleteRuntimeRequest(runtime_id=runtime_id))
            return {"success": True}
        except Exception as e:
            logger.error(f"delete runtime failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/web/runtime-detail")
    async def _web_runtime_detail(runtimeId: str = "", region: str = "cn-beijing"):
        """Control-plane detail for one runtime (used by the '管理 Agent' view).

        Returns config/status metadata from GetRuntime. This is NOT the in-container
        agent graph (that lives on the runtime's data plane); env-var values that
        look like secrets are masked before leaving the server.
        """
        if not runtimeId:
            raise HTTPException(status_code=400, detail="runtimeId is required")
        ak, sk, token = _resolve_ve_credentials()

        def _mask(key: str, value: str) -> str:
            if not value:
                return value
            if any(s in key.upper() for s in ("KEY", "SECRET", "TOKEN", "PASSWORD")):
                return (value[:3] + "***") if len(value) > 3 else "***"
            return value

        try:
            from agentkit.sdk.runtime.client import AgentkitRuntimeClient
            from agentkit.sdk.runtime import types as _rt

            client = AgentkitRuntimeClient(
                access_key=ak, secret_key=sk, session_token=token, region=region
            )
            r = client.get_runtime(_rt.GetRuntimeRequest(runtime_id=runtimeId))
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
        author: str = "",
        scope: str = "all",
        page_size: int = 30,
        next_token: str = "",
        region: str = "cn-beijing",
    ):
        """One page of AgentKit runtimes for the agent selector. Lists ALL
        runtimes (server-side paginated); each item is flagged `isMine` when its
        veadk:author tag matches `author`. scope=mine filters to the user's own."""
        ak, sk, token = _resolve_ve_credentials()
        try:
            from agentkit.sdk.runtime.client import AgentkitRuntimeClient
            from agentkit.sdk.runtime import types as _rt

            client = AgentkitRuntimeClient(
                access_key=ak, secret_key=sk, session_token=token, region=region
            )
            # Token-based pagination: MaxResults bounds the page, NextToken
            # continues it (PageSize is ignored by this API).
            kw = {"max_results": max(1, min(page_size, 100))}
            if next_token:
                kw["next_token"] = next_token
            resp = client.list_runtimes(_rt.ListRuntimesRequest(**kw))
            out: list[dict] = []
            for r in resp.agent_kit_runtimes or []:
                tags = {tg.key: tg.value for tg in (r.tags or [])}
                is_mine = bool(author) and tags.get("veadk:author") == author
                if scope == "mine" and not is_mine:
                    continue
                out.append(
                    {
                        "name": r.name,
                        "runtimeId": r.runtime_id,
                        "status": r.status,
                        "region": region,
                        "author": tags.get("veadk:author", ""),
                        "isMine": is_mine,
                    }
                )
            return {"runtimes": out, "nextToken": getattr(resp, "next_token", "") or ""}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"list runtimes failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

    # Cache resolved (endpoint, apikey) per runtime so the data-plane proxy does
    # not call GetRuntime on every request. Short TTL; cleared on a 401.
    _rt_conn_cache: dict[str, tuple] = {}

    def _resolve_runtime_conn(runtime_id: str, region: str) -> tuple[str, str]:
        import time as _time

        cached = _rt_conn_cache.get(runtime_id)
        if cached and cached[2] > _time.time():
            return cached[0], cached[1]
        ak, sk, token = _resolve_ve_credentials()
        from agentkit.sdk.runtime.client import AgentkitRuntimeClient
        from agentkit.sdk.runtime import types as _rt

        client = AgentkitRuntimeClient(
            access_key=ak, secret_key=sk, session_token=token, region=region
        )
        r = client.get_runtime(_rt.GetRuntimeRequest(runtime_id=runtime_id))
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
        if key_auth:
            apikey = getattr(key_auth, "api_key", "") or ""
        if not endpoint:
            raise HTTPException(
                status_code=502, detail="runtime has no public endpoint"
            )
        _rt_conn_cache[runtime_id] = (endpoint, apikey, _time.time() + 300)
        return endpoint, apikey

    @app.api_route(
        "/web/runtime-proxy/{runtime_id}/{path:path}",
        methods=["GET", "POST", "DELETE"],
    )
    async def _runtime_proxy(runtime_id: str, path: str, request: Request):
        """Proxy a data-plane call to a runtime, injecting its apikey server-side
        (the browser never sees it). Streams the response so /run_sse works."""
        region = request.query_params.get("region", "cn-beijing")
        try:
            endpoint, apikey = _resolve_runtime_conn(runtime_id, region)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"resolve runtime conn failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=str(e))

        # Drop the SSO gateway querystring; keep any real API query params.
        qs = {k: v for k, v in request.query_params.items() if k != "region"}
        target = f"{endpoint.rstrip('/')}/{path}"
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in {"host", "cookie", "authorization", "content-length"}
        }
        if apikey:
            headers["Authorization"] = f"Bearer {apikey}"
        body = await request.body()

        from fastapi.responses import StreamingResponse

        # Open the upstream stream so we can forward status + body incrementally.
        client = httpx.AsyncClient(timeout=None)
        req = client.build_request(
            request.method, target, params=qs, headers=headers, content=body
        )
        upstream = await client.send(req, stream=True)
        if upstream.status_code == 401:
            _rt_conn_cache.pop(runtime_id, None)

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
                exempt_paths={"/", "/index.html", "/favicon.ico", "/web/auth-config"},
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
    async def _web_list_skill_spaces(region: str = "cn-beijing"):
        """List SkillSpaces visible to the server's credentials. v1: single
        page of up to 50 spaces (covers virtually all accounts)."""
        from agentkit.sdk.skills.types import ListSkillSpacesRequest

        try:
            client = _skills_client(region)
            resp = client.list_skill_spaces(
                ListSkillSpacesRequest(page_number=1, page_size=50)
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"ListSkillSpaces error: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=f"SkillSpaces API error: {e}")

        items = list(resp.items or [])
        return {
            "items": [
                {
                    "id": s.id or "",
                    "name": s.name or "",
                    "description": s.description or "",
                    "status": s.status or "",
                }
                for s in items
            ],
            "totalCount": resp.total_count or len(items),
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
                f"ListSkillsBySkillSpace({space_id}) error: {e}", exc_info=True
            )
            raise HTTPException(status_code=502, detail=f"SkillSpaces API error: {e}")

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
@click.option("--region", default="cn-beijing", show_default=True)
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
def frontend_deploy(
    user_pool_id: str,
    allowed_client_id: str,
    client_secret: str,
    vefaas_app_name: str,
    region: str,
    iam_role: str | None,
    gateway_name: str,
    gateway_service_name: str,
    gateway_upstream_name: str,
    volcengine_access_key: str | None,
    volcengine_secret_key: str | None,
    veadk_version: str,
    from_source: bool,
) -> None:
    """Deploy the SSO web frontend to VeFaaS.

    Builds a minimal function that runs `veadk frontend --auth-mode gateway`,
    fronted by an APIG SSO gateway bound to the given VeIdentity user pool +
    client, and prints the public URL. Inside the function the frontend uses the
    bound IAM role's STS credentials to manage AgentKit runtimes.
    """
    import tempfile
    import shutil

    from veadk.config import getenv, veadk_environments

    ak = volcengine_access_key or getenv("VOLCENGINE_ACCESS_KEY")
    sk = volcengine_secret_key or getenv("VOLCENGINE_SECRET_KEY")
    if not ak or not sk:
        raise click.ClickException(
            "Volcengine credentials required: set VOLCENGINE_ACCESS_KEY/SECRET_KEY "
            "or pass --volcengine-access-key/--volcengine-secret-key."
        )

    # 1) Ensure the IAM role the function runs as (auto-create unless provided).
    if iam_role:
        role_trn = iam_role
        click.echo(f"Using provided IAM role: {role_trn}")
    else:
        from veadk.cli._frontend_deploy_iam import ensure_frontend_role

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
    if client_secret:
        veadk_environments["OAUTH2_CLIENT_SECRET"] = client_secret

    # 2) Build the function project (zip): run.sh launches the frontend server on
    #    the FaaS-assigned port; requirements.txt pulls veadk-python (ships the UI).
    requirements = (
        f"veadk-python=={veadk_version}\n" if veadk_version else "veadk-python\n"
    )
    run_sh = (
        "#!/bin/bash\n"
        "set -ex\n"
        'cd "$(dirname "$0")"\n'
        'if [ -d "output" ]; then cd ./output/; fi\n'
        "HOST=0.0.0.0\n"
        "PORT=${_FAAS_RUNTIME_PORT:-8000}\n"
        "export PYTHONPATH=$PYTHONPATH:./site-packages\n"
        "exec python3 -m veadk.cli.cli studio "
        '--auth-mode frontend --host "$HOST" --port "$PORT"\n'
    )
    # 2b) Resolve the serverless APIG gateway: use --gateway-name if given, else
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
        (Path(tmp) / "run.sh").write_text(run_sh, encoding="utf-8")

        # When --from-source, build a wheel from this checkout (picks up
        # uncommitted changes + the current veadk/webui) and install it instead
        # of the PyPI release, so the deployed frontend runs this branch's code.
        if from_source:
            import shutil as _shutil
            import subprocess
            import sys
            import veadk

            repo_root = Path(veadk.__file__).resolve().parent.parent
            if not (repo_root / "pyproject.toml").is_file():
                raise click.ClickException(
                    f"--from-source: no pyproject.toml at {repo_root}; run from a "
                    "veadk source checkout."
                )
            click.echo(f"Building wheel from source at {repo_root}…")
            uv = _shutil.which("uv")
            if uv:
                cmd = [uv, "build", "--wheel", str(repo_root), "-o", tmp]
            else:
                cmd = [
                    sys.executable,
                    "-m",
                    "build",
                    "--wheel",
                    "-o",
                    tmp,
                    str(repo_root),
                ]
            subprocess.run(cmd, check=True)
            wheels = list(Path(tmp).glob("veadk*.whl"))
            if not wheels:
                raise click.ClickException(
                    "--from-source: wheel build produced no .whl"
                )
            wheel_name = wheels[0].name
            click.echo(f"Shipping local wheel: {wheel_name}")
            # Install the bundled wheel; deps still resolve from PyPI.
            requirements = f"./{wheel_name}\n"

        (Path(tmp) / "requirements.txt").write_text(requirements, encoding="utf-8")

        # 3) Deploy the function + a plain public APIG trigger on the serverless
        #    gateway (auth_method="none" — no gateway SSO plugin / domain upstream).
        from veadk.cloud.cloud_agent_engine import CloudAgentEngine

        engine = CloudAgentEngine(
            volcengine_access_key=ak,
            volcengine_secret_key=sk,
            region=region,
        )
        click.echo(f"Deploying frontend to VeFaaS as '{vefaas_app_name}'…")
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
                    access_key=ak, secret_key=sk, region=region
                ).register_callback_for_user_pool_client(
                    user_pool_uid=user_pool_id,
                    client_uid=allowed_client_id,
                    callback_url=redirect_uri,
                    web_origin=url,
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
