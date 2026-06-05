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
process, so there is no cross-origin setup. In `--dev` mode it serves only the
API (with CORS allowing the Vite dev server) for React hot reload.
"""

import os

from pathlib import Path

import click

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

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


@click.command()
@click.option(
    "--agents-dir",
    default=".",
    show_default=True,
    help="Directory containing agent apps (like `adk web`): run from the parent "
    "folder of your agent directories — each subdir with an `agent.py` exposing "
    "a `root_agent` becomes a selectable app in the UI. Defaults to the current "
    "directory.",
)
@click.option(
    "--frontend-dir",
    default=None,
    help="Override the built React UI directory. Defaults to the UI shipped "
    "with the package (veadk/webui), falling back to ./frontend/dist.",
)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
@click.option(
    "--dev",
    is_flag=True,
    default=False,
    help=(
        "Dev mode: serve API only and allow CORS from the Vite dev server "
        f"({DEV_SERVER_ORIGIN}). Run `npm run dev` in ./frontend alongside this."
    ),
)
@click.option(
    "--oauth2-user-pool",
    default=None,
    help="VeIdentity User Pool NAME. When set (or its UID), enables SSO: "
    "unauthenticated browsers see a login page and the UI uses the signed-in user.",
)
@click.option(
    "--oauth2-user-pool-client",
    default=None,
    help="VeIdentity User Pool client NAME.",
)
@click.option(
    "--oauth2-user-pool-uid",
    default=None,
    envvar="OAUTH2_USER_POOL_ID",
    help="VeIdentity User Pool UID (env: OAUTH2_USER_POOL_ID). Use instead of "
    "the pool name.",
)
@click.option(
    "--oauth2-user-pool-client-uid",
    default=None,
    envvar="OAUTH2_USER_POOL_CLIENT_ID",
    help="VeIdentity client UID (env: OAUTH2_USER_POOL_CLIENT_ID). Use instead "
    "of the client name.",
)
@click.option(
    "--oauth2-redirect-uri",
    default=None,
    envvar="OAUTH2_REDIRECT_URI",
    help="OAuth2 callback URL (env: OAUTH2_REDIRECT_URI). Set this when deploying "
    "behind a public host/runtime; defaults to http://{host}:{port}/oauth2/callback.",
)
@click.option(
    "--oauth2-provider",
    default=None,
    envvar="OAUTH2_PROVIDER",
    help="SSO provider id (env: OAUTH2_PROVIDER), e.g. veidentity, github, google, "
    "or a custom name. For github/google, only client id/secret env vars are needed; "
    "for any OIDC provider set OAUTH2_ISSUER; otherwise set OAUTH2_AUTHORIZE_URL/"
    "OAUTH2_TOKEN_URL/OAUTH2_USERINFO_URL. Client creds via OAUTH2_CLIENT_ID/"
    "OAUTH2_CLIENT_SECRET. Defaults to veidentity when a user pool is configured.",
)
@click.option(
    "--oauth2-provider-label",
    default=None,
    envvar="OAUTH2_PROVIDER_LABEL",
    help="Display label for the SSO login button (env: OAUTH2_PROVIDER_LABEL).",
)
def frontend(
    agents_dir: str,
    frontend_dir: str | None,
    host: str,
    port: int,
    dev: bool,
    oauth2_user_pool: str | None,
    oauth2_user_pool_client: str | None,
    oauth2_user_pool_uid: str | None,
    oauth2_user_pool_client_uid: str | None,
    oauth2_redirect_uri: str | None,
    oauth2_provider: str | None,
    oauth2_provider_label: str | None,
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
        logger.warning(f"No .env file found in current directory or parent directories")

    from google.adk.cli.fast_api import get_fast_api_app

    agents_dir = os.path.abspath(agents_dir)
    allow_origins = [DEV_SERVER_ORIGIN] if dev else []

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

    _temp_agents: dict[str, str] = {}  # app_name -> temp_dir_path

    # Monkey-patch AgentLoader class to handle temp agents
    # This way all instances will use the patched version
    _original_load_agent_method = AgentLoader.load_agent

    def _patched_load_agent_method(self, name: str):
        if name in _temp_agents:
            return _load_temp_agent(name)
        return _original_load_agent_method(self, name)

    AgentLoader.load_agent = _patched_load_agent_method
    logger.info("Patched AgentLoader.load_agent to support temp agents")

    _agent_loader = AgentLoader(agents_dir)

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

    @app.get("/web/agent-info/{app_name}")
    async def _web_agent_info(app_name: str):
        try:
            agent = _agent_loader.load_agent(app_name)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"unknown agent: {app_name}")
        return {
            "name": getattr(agent, "name", app_name),
            "description": getattr(agent, "description", "") or "",
            "model": _model_name(getattr(agent, "model", "")),
            "tools": [_tool_label(t) for t in getattr(agent, "tools", []) or []],
            "subAgents": [
                getattr(s, "name", "") for s in getattr(agent, "sub_agents", []) or []
            ],
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
        """Proxy requests to remote AgentKit APIs to avoid CORS issues."""
        target_base = request.headers.get("X-AgentKit-Base")
        api_key = request.headers.get("X-AgentKit-Key")
        if not target_base:
            raise HTTPException(status_code=400, detail="Missing X-AgentKit-Base")

        target_url = f"{target_base.rstrip('/')}/{path}"
        if request.url.query:
            target_url += f"?{request.url.query}"

        headers = dict(request.headers)
        # Remove proxy-specific and CORS-related headers
        headers.pop("host", None)
        headers.pop("x-agentkit-base", None)
        headers.pop("x-agentkit-key", None)
        headers.pop("origin", None)
        headers.pop("referer", None)
        headers.pop("sec-fetch-site", None)
        headers.pop("sec-fetch-mode", None)
        headers.pop("sec-fetch-dest", None)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

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

    # ---- Temporary agent deployment for testing generated code ----
    import tempfile
    import shutil
    import importlib.util
    from pathlib import Path as PathlibPath

    @app.post("/web/deploy-temp-agent")
    async def _deploy_temp_agent(request: Request):
        """Deploy a generated agent temporarily for testing.

        Request body: {
            "name": "agent_name",
            "files": [{"path": "agent.py", "content": "..."}, ...]
        }
        Returns: {"appName": "temp_agent_name"}
        """
        try:
            data = await request.json()
            agent_name = data.get("name", "").strip()
            files = data.get("files", [])

            if not agent_name:
                raise HTTPException(status_code=400, detail="Agent name is required")
            if not files:
                raise HTTPException(status_code=400, detail="No files provided")

            # Create a temporary directory
            temp_dir = tempfile.mkdtemp(prefix=f"veadk_temp_{agent_name}_")
            logger.info(f"Creating temporary agent at {temp_dir}")

            # Write all files
            for file_info in files:
                file_path = file_info.get("path", "")
                content = file_info.get("content", "")
                if not file_path:
                    continue

                full_path = PathlibPath(temp_dir) / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content, encoding="utf-8")

            # Verify agent.py exists and has root_agent
            agent_py = PathlibPath(temp_dir) / "agent.py"
            if not agent_py.exists():
                shutil.rmtree(temp_dir)
                raise HTTPException(
                    status_code=400,
                    detail="agent.py not found in files"
                )

            # Try to load the agent to validate it
            try:
                spec = importlib.util.spec_from_file_location("temp_agent", str(agent_py))
                if spec is None or spec.loader is None:
                    raise ValueError("Failed to create module spec")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if not hasattr(module, "root_agent"):
                    raise ValueError("root_agent not found in agent.py")
            except Exception as e:
                shutil.rmtree(temp_dir)
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to load agent: {str(e)}"
                )

            # Clean up old temp agent if exists
            app_name = f"_temp_{agent_name}"
            if app_name in _temp_agents:
                old_dir = _temp_agents[app_name]
                if os.path.exists(old_dir):
                    shutil.rmtree(old_dir)

            # Register the temp agent
            _temp_agents[app_name] = temp_dir

            logger.info(f"Temporary agent '{app_name}' deployed successfully")
            return {"appName": app_name}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error deploying temp agent: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Deployment failed: {str(e)}")

    def _load_temp_agent(app_name: str):
        """Load a temporary agent from the temp directory.

        Uses environment variables already loaded in the parent process.
        """
        if app_name not in _temp_agents:
            raise ValueError(f"Unknown temp agent: {app_name}")

        temp_dir = _temp_agents[app_name]
        agent_py = PathlibPath(temp_dir) / "agent.py"

        if not agent_py.exists():
            raise ValueError(f"agent.py not found in temp dir: {temp_dir}")

        spec = importlib.util.spec_from_file_location(app_name, str(agent_py))
        if spec is None or spec.loader is None:
            raise ValueError("Failed to create module spec")
        module = importlib.util.module_from_spec(spec)

        # Add temp dir to sys.path so imports work
        import sys
        if temp_dir not in sys.path:
            sys.path.insert(0, temp_dir)

        try:
            spec.loader.exec_module(module)
        finally:
            if temp_dir in sys.path:
                sys.path.remove(temp_dir)

        if not hasattr(module, "root_agent"):
            raise ValueError("root_agent not found in agent.py")

        return module.root_agent

    @app.delete("/web/deploy-temp-agent/{app_name}")
    async def _delete_temp_agent(app_name: str):
        """Clean up a temporary agent."""
        if app_name not in _temp_agents:
            raise HTTPException(status_code=404, detail=f"Agent '{app_name}' not found")

        temp_dir = _temp_agents.pop(app_name)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        logger.info(f"Temporary agent '{app_name}' deleted")
        return {"status": "deleted"}

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
        providers = [{"id": provider_id, "label": label, "loginUrl": "/oauth2/login"}]

        @app.get("/web/auth-config")
        async def _web_auth_config():
            return {"providers": providers}

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

    if dev:
        logger.info(
            f"A2UI dev mode: API on http://{host}:{port}, "
            f"run `cd frontend && npm run dev` and open {DEV_SERVER_ORIGIN}"
        )
    else:
        from fastapi.staticfiles import StaticFiles

        webui = _resolve_frontend_dir(frontend_dir)
        if not (webui / "index.html").is_file():
            raise click.ClickException(
                f"Built UI not found at {webui}. Build it with: "
                "cd frontend && npm install && npm run build "
                "(or use --dev for the Vite dev server)."
            )
        # Mount last so it doesn't shadow the API routes registered above.
        app.mount("/", StaticFiles(directory=str(webui), html=True), name="frontend")
        logger.info(
            f"A2UI UI + API serving on http://{host}:{port} (UI: {webui}, agents: {agents_dir})"
        )

    import uvicorn

    uvicorn.run(app, host=host, port=port)
