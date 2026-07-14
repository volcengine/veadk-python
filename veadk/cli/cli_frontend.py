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
import subprocess
import re
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
@click.option(
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
    auth_mode: str,
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

    @app.post("/web/deploy-agentkit")
    async def _deploy_to_agentkit(request: Request):
        """Deploy Agent to AgentKit cloud service.

        Request body: {
            "name": "agent_name",
            "files": [{"path": "app.py", "content": "..."}, ...],
            "config": {
                "region": "cn-beijing",
                "projectName": "default"
            }
        }
        Returns: {
            "success": true,
            "agentName": "my-agent",
            "apikey": "ak-xxx",
            "url": "https://...",
            "consoleUrl": "https://console.volcengine.com/..."
        }
        """
        import tempfile
        import shutil
        import yaml
        from pathlib import Path as PathlibPath

        temp_dir = None
        try:
            data = await request.json()
            agent_name = data.get("name", "").strip()
            files = data.get("files", [])
            config = data.get("config", {})

            if not agent_name:
                raise HTTPException(status_code=400, detail="Agent name is required")
            if not files:
                raise HTTPException(status_code=400, detail="No files provided")

            # 1. Create temporary working directory
            temp_dir = tempfile.mkdtemp(prefix=f"agentkit_deploy_{agent_name}_")
            logger.info(f"Deploying agent '{agent_name}' from {temp_dir}")

            # 2. Write all project files
            for file_info in files:
                file_path = file_info.get("path", "")
                content = file_info.get("content", "")
                if not file_path:
                    continue

                # Skip __init__.py to avoid package conflicts with python -m agent
                if file_path == "__init__.py":
                    logger.info(
                        f"Skipping {file_path} to ensure proper module execution"
                    )
                    continue

                # Confine writes to temp_dir — reject absolute paths and
                # "../" traversal so a crafted `path` can't write outside it.
                base = PathlibPath(temp_dir).resolve()
                full_path = (base / file_path).resolve()
                if not full_path.is_relative_to(base):
                    raise HTTPException(
                        status_code=400, detail=f"Illegal file path: {file_path}"
                    )
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content, encoding="utf-8")

            # 3. Verify entry point exists
            entry_point = "app.py"
            if not (PathlibPath(temp_dir) / "app.py").exists():
                raise HTTPException(
                    status_code=400,
                    detail="No app.py found in files (frontend should generate it)",
                )

            # Verify files in temp_dir
            files_created = list(PathlibPath(temp_dir).iterdir())
            logger.info(f"Files in deployment dir: {[f.name for f in files_created]}")

            # 5. Generate agentkit.yaml
            region = config.get("region", "cn-beijing")
            project_name = config.get("projectName", "default")

            agentkit_config = {
                "common": {
                    "agent_name": agent_name,
                    "entry_point": entry_point,  # Use agent.py or app.py
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
                            # Disable OpenTelemetry to avoid connection errors in AgentKit Runtime
                            "OTEL_SDK_DISABLED": "true",
                            # Disable expire_at to avoid signature expiration during deployment
                            "VEADK_DISABLE_EXPIRE_AT": "true",
                        },
                    }
                },
            }

            config_path = PathlibPath(temp_dir) / "agentkit.yaml"
            config_path.write_text(yaml.dump(agentkit_config, allow_unicode=True))

            # 5. Copy .env (use server credentials)
            if Path(".env").exists():
                shutil.copy(".env", PathlibPath(temp_dir) / ".env")

            # 6. Call veadk agentkit launch
            logger.info("Launching agent via CLI: veadk agentkit launch")
            result = subprocess.run(
                ["veadk", "agentkit", "launch"],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes timeout
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                logger.error(f"AgentKit launch failed: {error_msg}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Deployment failed: {error_msg[:500]}",
                )

            # 7. Parse output (extract runtime_id, apikey name, and url from CLI)
            output = result.stdout
            logger.info(f"AgentKit launch output: {output}")

            runtime_id, apikey_name, url, actual_agent_name = _parse_agentkit_output(
                output
            )
            logger.info(f"Parsed from CLI - RuntimeId: {runtime_id}, Endpoint: {url}")

            # 8. Try to get actual API key from AgentKit API
            try:
                actual_apikey = _get_runtime_apikey(runtime_id, region)
                if actual_apikey:
                    apikey = actual_apikey
                    logger.info("Successfully retrieved API key via AgentKit API")
                else:
                    apikey = apikey_name or f"API-KEY-{runtime_id}"
                    logger.warning(
                        f"Could not retrieve API key from AgentKit API, using placeholder: {apikey}"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to retrieve API key via AgentKit API: {e}, using placeholder"
                )
                apikey = apikey_name or f"API-KEY-{runtime_id}"

            # 9. Construct console URL
            console_url = (
                f"https://console.volcengine.com/agentkit/"
                f"region:agentkit+{region}/runtime"
                f"?projectName={project_name}"
            )

            return {
                "success": True,
                "agentName": actual_agent_name or agent_name,
                "apikey": apikey,
                "url": url,
                "consoleUrl": console_url,
            }

        except subprocess.TimeoutExpired:
            logger.error("AgentKit deployment timeout (>10min)")
            raise HTTPException(status_code=504, detail="Deployment timeout (>10min)")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"AgentKit deployment error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            # 9. Cleanup temporary directory
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _parse_agentkit_output(output: str) -> tuple[str, str, str, str]:
        """Parse CLI output to extract runtime_id, apikey name, endpoint, and actual agent name.

        Actual AgentKit CLI output format:
        - Runtime ID: "✅ Runtime created successfully: r-xxxxx"
        - Endpoint: "Endpoint: https://..."
        - Agent name: "Creating Runtime: a_111-8pi9eche" or "Creating new pipeline: a_111-8pi9eche"

        Returns:
            Tuple of (runtime_id, apikey_name, endpoint, actual_agent_name)
        """
        output = output.strip()

        # Extract RuntimeId
        runtime_match = re.search(
            r"Runtime created successfully:\s*(r-\w+)", output, re.IGNORECASE
        )
        runtime_id = runtime_match.group(1) if runtime_match else ""

        # Extract Endpoint (appears multiple times, use the first occurrence)
        endpoint_match = re.search(r"Endpoint:\s*(https?://\S+)", output, re.IGNORECASE)
        endpoint = endpoint_match.group(1) if endpoint_match else ""

        # Try to extract API key name (may not always be present)
        apikey_match = re.search(
            r"Generated API key name:\s*(API-KEY-\S+)", output, re.IGNORECASE
        )
        apikey_name = apikey_match.group(1) if apikey_match else ""

        # Extract actual agent name (pipeline/runtime name with suffix)
        # Try multiple patterns: "Creating Runtime: xxx" or "Creating new pipeline: xxx"
        agent_name = ""
        for pattern in [
            r"Creating Runtime:\s*([a-zA-Z0-9_-]+)",
            r"Creating new pipeline:\s*([a-zA-Z0-9_-]+)",
            r"Pipeline created successfully:\s*([a-zA-Z0-9_-]+)",
        ]:
            name_match = re.search(pattern, output, re.IGNORECASE)
            if name_match:
                agent_name = name_match.group(1)
                break

        if not runtime_id or not endpoint:
            logger.error(f"Cannot parse CLI output: {output}")
            raise ValueError(
                f"Failed to parse deployment output. "
                f"Expected RuntimeId and Endpoint, got: {output[:500]}"
            )

        return runtime_id, apikey_name, endpoint, agent_name

    def _get_runtime_apikey(runtime_id: str, region: str) -> str:
        """Get actual API key from AgentKit Runtime API.

        Args:
            runtime_id: Runtime ID (e.g., "r-yeo3ym4hkwo2eybtjs36")
            region: AgentKit region (e.g., "cn-beijing")

        Returns:
            Actual API key string, or empty string if retrieval fails

        This function calls the Volcengine AgentKit GetRuntime API to retrieve
        the actual API key after deployment. The API key is in the
        AuthorizerConfiguration.KeyAuth.ApiKey field.
        """
        try:
            from volcengine.Credentials import Credentials
            from volcengine.base.Service import Service
            from volcengine.ServiceInfo import ServiceInfo
            from volcengine.ApiInfo import ApiInfo

            access_key = os.getenv("VOLCENGINE_ACCESS_KEY")
            secret_key = os.getenv("VOLCENGINE_SECRET_KEY")

            if not access_key or not secret_key:
                logger.warning("VOLCENGINE_ACCESS_KEY or VOLCENGINE_SECRET_KEY not set")
                return ""

            # Configure AgentKit service
            service_info = ServiceInfo(
                host=f"agentkit.{region}.volcengineapi.com",
                header={},
                credentials=Credentials(access_key, secret_key, "agentkit", region),
                connection_timeout=30,
                socket_timeout=30,
                scheme="https",  # IMPORTANT: Use HTTPS instead of default HTTP
            )

            api_info = {
                "GetRuntime": ApiInfo(
                    "POST",
                    "/",
                    {"Action": "GetRuntime", "Version": "2025-10-30"},
                    {},
                    {},
                ),
            }

            service = Service(service_info, api_info)

            # Call GetRuntime to get API key
            request_body = {
                "RuntimeId": runtime_id,
            }

            logger.debug(f"Calling GetRuntime API for RuntimeId: {runtime_id}")
            response = service.json("GetRuntime", {}, json.dumps(request_body))

            if not response:
                logger.error("GetRuntime API returned empty response")
                return ""

            runtime_data = (
                json.loads(response) if isinstance(response, str) else response
            )
            logger.debug(f"GetRuntime response keys: {list(runtime_data.keys())}")

            if (
                "ResponseMetadata" in runtime_data
                and "Error" in runtime_data["ResponseMetadata"]
            ):
                error = runtime_data["ResponseMetadata"]["Error"]
                logger.error(
                    f"GetRuntime API error: {error.get('Code')} - {error.get('Message')}"
                )
                return ""

            result = runtime_data.get("Result", {})

            # Extract API key from AuthorizerConfiguration.KeyAuth.ApiKey
            authorizer_config = result.get("AuthorizerConfiguration", {})
            key_auth = authorizer_config.get("KeyAuth", {})
            api_key = key_auth.get("ApiKey", "")

            if api_key:
                logger.info(
                    f"Successfully retrieved API key from GetRuntime: {api_key[:10]}..."
                )
                return api_key
            else:
                logger.warning(
                    f"No API key found in GetRuntime response. "
                    f"AuthorizerConfiguration: {authorizer_config}"
                )
                return ""

        except Exception as e:
            logger.error(f"Failed to get API key from AgentKit API: {e}", exc_info=True)
            return ""

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
        )
        return {"credentials": has_creds}

    if dev:
        logger.info(
            f"A2UI dev mode: API on http://{host}:{port}, "
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

    import uvicorn

    uvicorn.run(app, host=host, port=port)
