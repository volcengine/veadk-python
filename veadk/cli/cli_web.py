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

import click


@click.command()
@click.option("--host", default="127.0.0.1", help="Host to run the web server on")
def web(host: str) -> None:
    """Launch web with long term and short term memory."""
    import os
    from typing import Any

    from google.adk.cli.utils.shared_value import SharedValue

    from veadk.memory.short_term_memory import ShortTermMemory
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

        short_term_memory_backend = os.getenv("SHORT_TERM_MEMORY_BACKEND")
        if not short_term_memory_backend:  # prevent None or empty string
            short_term_memory_backend = "local"
        logger.info(f"Short term memory: backend={short_term_memory_backend}")

        long_term_memory_backend = os.getenv("LONG_TERM_MEMORY_BACKEND")
        long_term_memory = None

        if long_term_memory_backend:
            from veadk.memory.long_term_memory import LongTermMemory

            logger.info(f"Long term memory: backend={long_term_memory_backend}")
            long_term_memory = LongTermMemory(backend=long_term_memory_backend)  # type: ignore
        else:
            logger.info("No long term memory backend settings detected.")

        self.session_service = ShortTermMemory(
            backend=short_term_memory_backend  # type: ignore
        ).session_service

        self.memory_service = long_term_memory

    import google.adk.cli.adk_web_server

    google.adk.cli.adk_web_server.AdkWebServer.__init__ = init_for_veadk

    import google.adk.cli.cli_tools_click as cli_tools_click

    agents_dir = os.getcwd()
    logger.info(f"Load agents from {agents_dir}")

    cli_tools_click.cli_web.main(args=[agents_dir, "--host", host])
