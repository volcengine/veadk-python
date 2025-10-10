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

from typing import Optional

import click

from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.short_term_memory import ShortTermMemory


def _get_stm_from_module(module) -> ShortTermMemory:
    return module.agent_run_config.short_term_memory


def _get_stm_from_env() -> ShortTermMemory:
    import os

    from veadk.utils.logger import get_logger

    logger = get_logger(__name__)

    short_term_memory_backend = os.getenv("SHORT_TERM_MEMORY_BACKEND")
    if not short_term_memory_backend:  # prevent None or empty string
        short_term_memory_backend = "local"
    logger.info(f"Short term memory: backend={short_term_memory_backend}")

    return ShortTermMemory(backend=short_term_memory_backend)  # type: ignore


def _get_ltm_from_module(module) -> LongTermMemory | None:
    agent = module.agent_run_config.agent

    if not hasattr(agent, "long_term_memory"):
        return None
    else:
        return agent.long_term_memory


def _get_ltm_from_env() -> LongTermMemory | None:
    import os

    from veadk.utils.logger import get_logger

    logger = get_logger(__name__)

    long_term_memory_backend = os.getenv("LONG_TERM_MEMORY_BACKEND")

    if long_term_memory_backend:
        logger.info(f"Long term memory: backend={long_term_memory_backend}")
        return LongTermMemory(backend=long_term_memory_backend)  # type: ignore
    else:
        logger.warning("No long term memory backend settings detected.")
        return None


def _get_memory(
    module_path: str,
) -> tuple[ShortTermMemory, LongTermMemory | None]:
    from veadk.utils.logger import get_logger
    from veadk.utils.misc import load_module_from_file

    logger = get_logger(__name__)

    # 1. load user module
    try:
        module_file_path = module_path
        module = load_module_from_file(
            module_name="agent_and_mem", file_path=f"{module_file_path}/agent.py"
        )
    except Exception as e:
        logger.error(
            f"Failed to get memory config from `agent.py`: {e}. Fallback to get memory from environment variables."
        )
        return _get_stm_from_env(), _get_ltm_from_env()

    if not hasattr(module, "agent_run_config"):
        logger.error(
            "You must export `agent_run_config` as a global variable in `agent.py`. Fallback to get memory from environment variables."
        )
        return _get_stm_from_env(), _get_ltm_from_env()

    # 2. try to get short term memory
    # short term memory must exist in user code, as we use `default_factory` to init it
    short_term_memory = _get_stm_from_module(module)

    # 3. try to get long term memory
    long_term_memory = _get_ltm_from_module(module)
    if not long_term_memory:
        long_term_memory = _get_ltm_from_env()

    return short_term_memory, long_term_memory


def patch_adkwebserver_disable_openapi():
    """
    Monkey patch AdkWebServer.get_fast_api to remove openapi.json route.
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


@click.command()
@click.option("--host", default="127.0.0.1", help="Host to run the web server on")
def web(host: str) -> None:
    """Launch web with long term and short term memory."""
    import os
    from typing import Any

    from google.adk.cli.utils.shared_value import SharedValue

    from veadk.utils.logger import get_logger

    logger = get_logger(__name__)

    def init_for_veadk(
        self,
        *,
        agent_loader: Any,
        session_service: Any,
        memory_service: Any,
        artifact_service: Any,
        credential_service: Any,
        eval_sets_manager: Any,
        eval_set_results_manager: Any,
        agents_dir: str,
        extra_plugins: Optional[list[str]] = None,
    ):
        self.agent_loader = agent_loader
        self.artifact_service = artifact_service
        self.credential_service = credential_service
        self.eval_sets_manager = eval_sets_manager
        self.eval_set_results_manager = eval_set_results_manager
        self.agents_dir = agents_dir
        self.runners_to_clean = set()
        self.current_app_name_ref = SharedValue(value="")
        self.runner_dict = {}
        self.extra_plugins = extra_plugins or []

        # parse VeADK memories
        short_term_memory, long_term_memory = _get_memory(module_path=agents_dir)
        self.session_service = short_term_memory.session_service
        self.memory_service = long_term_memory

    import google.adk.cli.adk_web_server

    google.adk.cli.adk_web_server.AdkWebServer.__init__ = init_for_veadk
    patch_adkwebserver_disable_openapi()

    import google.adk.cli.cli_tools_click as cli_tools_click

    agents_dir = os.getcwd()
    logger.info(f"Load agents from {agents_dir}")

    cli_tools_click.cli_web.main(
        args=[agents_dir, "--host", host, "--log_level", "ERROR"]
    )
