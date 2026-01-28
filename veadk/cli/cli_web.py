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

import logging
from functools import wraps

import click

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def _patch_adkwebserver_oauth2(
    user_pool_name: str,
    user_pool_client: str,
    redirect_uri: str,
) -> None:
    """
    Monkey patch AdkWebServer to enable OAuth2 authentication.

    This function patches the AdkWebServer.get_fast_api_app method to add
    OAuth2 authentication middleware using VeIdentity User Pool.

    Args:
        user_pool_name: VeIdentity User Pool name.
        user_pool_client: VeIdentity User Pool client name.
        redirect_uri: OAuth2 redirect URI (e.g., http://127.0.0.1:8000/oauth2/callback).
    """
    import google.adk.cli.adk_web_server

    from veadk.auth.middleware.oauth2_auth import OAuth2Config, setup_oauth2

    original_get_fast_api = google.adk.cli.adk_web_server.AdkWebServer.get_fast_api_app

    def wrapped_get_fast_api(self, *args, **kwargs):
        app = original_get_fast_api(self, *args, **kwargs)

        # Setup OAuth2 with VeIdentity User Pool
        oauth2_config = OAuth2Config.from_veidentity(
            user_pool_name=user_pool_name,
            client_name=user_pool_client,
            redirect_uri=redirect_uri,
        )
        oauth2_config.cookie_secure = False

        setup_oauth2(
            app,
            oauth2_config,
        )
        logger.info("OAuth2 middleware installed")

        return app

    google.adk.cli.adk_web_server.AdkWebServer.get_fast_api_app = wrapped_get_fast_api


def patch_adkwebserver_disable_openapi():
    """
    Monkey patch AdkWebServer to disable OpenAPI documentation endpoints.

    This function patches the AdkWebServer.get_fast_api_app method to remove
    OpenAPI-related routes (/openapi.json, /docs, /redoc) from the FastAPI
    application for security and simplicity purposes.

    The patch is applied by replacing the original method with a wrapped version
    that filters out the unwanted routes after the FastAPI app is created.
    """
    import google.adk.cli.adk_web_server
    from fastapi.routing import APIRoute
    from starlette.routing import Route

    original_get_fast_api = google.adk.cli.adk_web_server.AdkWebServer.get_fast_api_app

    def wrapped_get_fast_api(self, *args, **kwargs):
        app = original_get_fast_api(self, *args, **kwargs)

        paths = ["/openapi.json", "/docs", "/redoc"]
        new_routes = []
        for route in app.router.routes:
            if isinstance(route, (APIRoute, Route)) and route.path in paths:
                continue
            new_routes.append(route)
        app.router.routes = new_routes

        return app

    google.adk.cli.adk_web_server.AdkWebServer.get_fast_api_app = wrapped_get_fast_api


@click.command(
    context_settings=dict(ignore_unknown_options=True, allow_extra_args=True)
)
@click.option(
    "--oauth2-user-pool",
    type=str,
    default=None,
    help="VeIdentity User Pool name for OAuth2 authentication.",
)
@click.option(
    "--oauth2-user-pool-client",
    type=str,
    default=None,
    help="VeIdentity User Pool client name for OAuth2 authentication.",
)
@click.option(
    "--oauth2-redirect-uri",
    type=str,
    default=None,
    help="OAuth2 redirect URI. Defaults to http://{host}:{port}/oauth2/callback.",
)
@click.pass_context
def web(
    ctx,
    oauth2_user_pool: str | None,
    oauth2_user_pool_client: str | None,
    oauth2_redirect_uri: str | None,
    *args,
    **kwargs,
) -> None:
    """
    Launch a web server with VeADK agent support and memory integration.

    This command starts a web server that can serve VeADK agents with both
    short-term and long-term memory capabilities. It automatically detects
    the type of agent being loaded and configures the appropriate memory
    services accordingly.

    The function patches the ADK web server to integrate VeADK-specific
    functionality, including memory service configuration and workflow
    agent detection.

    Args:
        ctx: Click context object containing command line arguments

    Note:
        For workflow agents (Sequential, Loop, Parallel), individual sub-agent
        memory configurations are not utilized as warned in the logs.
    """
    from google.adk.cli import adk_web_server
    from google.adk.runners import Runner as ADKRunner

    from veadk import Agent
    from veadk.agents.loop_agent import LoopAgent
    from veadk.agents.parallel_agent import ParallelAgent
    from veadk.agents.sequential_agent import SequentialAgent

    def before_get_runner_async(func):
        logger.info("Hook before `get_runner_async`")

        @wraps(func)
        async def wrapper(*args, **kwargs) -> ADKRunner:
            self: adk_web_server.AdkWebServer = args[0]
            app_name: str = args[1]
            """Returns the cached runner for the given app."""
            agent_or_app = self.agent_loader.load_agent(app_name)

            if isinstance(agent_or_app, (SequentialAgent, LoopAgent, ParallelAgent)):
                logger.warning(
                    "Detect VeADK workflow agent, the short-term memory and long-term memory of each sub agent are useless."
                )

            if isinstance(agent_or_app, Agent):
                logger.info("Detect VeADK Agent.")

                if agent_or_app.short_term_memory:
                    self.session_service = (
                        agent_or_app.short_term_memory.session_service
                    )

                if agent_or_app.long_term_memory:
                    self.memory_service = agent_or_app.long_term_memory
                    logger.info(
                        f"Long term memory backend is {self.memory_service.backend}"
                    )

                logger.info(
                    f"Current session_service={self.session_service.__class__.__name__}, memory_service={self.memory_service.__class__.__name__}"
                )

            runner = await func(*args, **kwargs)
            return runner

        return wrapper

    adk_web_server.AdkWebServer.get_runner_async = before_get_runner_async(
        adk_web_server.AdkWebServer.get_runner_async
    )

    patch_adkwebserver_disable_openapi()

    from google.adk.cli.cli_tools_click import cli_web

    extra_args: list = ctx.args

    # Setup OAuth2 if configured
    if oauth2_user_pool and oauth2_user_pool_client:
        # Build redirect_uri from host/port if not provided
        redirect_uri = oauth2_redirect_uri
        if not redirect_uri:
            # Parse host and port from extra_args
            host = "127.0.0.1"
            port = "8000"
            if "--host" in extra_args:
                host = extra_args[extra_args.index("--host") + 1]
            if "--port" in extra_args:
                port = extra_args[extra_args.index("--port") + 1]
            redirect_uri = f"http://{host}:{port}/oauth2/callback"

        _patch_adkwebserver_oauth2(
            user_pool_name=oauth2_user_pool,
            user_pool_client=oauth2_user_pool_client,
            redirect_uri=redirect_uri,
        )
        logger.info(
            f"OAuth2 enabled: user_pool={oauth2_user_pool}, "
            f"client={oauth2_user_pool_client}, redirect_uri={redirect_uri}"
        )
    logger.debug(f"User args: {extra_args}")

    # set a default log level to avoid unnecessary outputs
    # from Google ADK and Litellm
    if "--log_level" not in extra_args:
        extra_args.extend(["--log_level", "ERROR"])
        logging.basicConfig(level=logging.ERROR, force=True)

    if "--log_level" in extra_args:
        logging.basicConfig(
            level=getattr(
                logging, extra_args[extra_args.index("--log_level") + 1].upper()
            ),
            force=True,
        )

    cli_web.main(args=extra_args, standalone_mode=False)
