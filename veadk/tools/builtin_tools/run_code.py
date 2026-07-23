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

import os

from google.adk.tools import ToolContext

from veadk.tools.builtin_tools._agentkit import (
    get_agentkit_endpoint_config,
    invoke_agentkit_exec_bash,
    invoke_agentkit_run_code,
    resolve_agentkit_tool_id,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def run_code(
    code: str,
    language: str,
    tool_context: ToolContext,
    timeout: int = 30,
    exec_dir: str = "/tmp",
    env: dict[str, str] | None = None,
    hard_timeout: int = 300,
    max_output_length: int = 30000,
) -> str:
    """Run code in a code sandbox and return the output.
    For C++ code, don't execute it directly, compile and execute via Python; write sources and object files to /tmp.

    Args:
        code (str): The code to run.
        language (str): The execution language. Use ``python3`` for code or ``bash`` for shell scripts.
        timeout (int, optional): The timeout in seconds for the code execution. Defaults to 30.
        exec_dir (str, optional): Working directory for Bash execution. Defaults to ``/tmp``.
        env (dict[str, str], optional): Environment variables for Bash execution.
        hard_timeout (int, optional): Hard timeout for Bash execution. Defaults to 300 seconds.
        max_output_length (int, optional): Maximum Bash output length. Defaults to 30000.

    Returns:
        str: The output of the code execution.
    """

    tool_id = resolve_agentkit_tool_id("AGENTKIT_TOOL_ID_SCRIPT")
    service, region, host, _ = get_agentkit_endpoint_config()
    logger.debug(f"tools endpoint: {host}")

    session_id = tool_context._invocation_context.session.id
    agent_name = tool_context._invocation_context.agent.name
    user_id = tool_context._invocation_context.user_id
    tool_user_session_id = agent_name + "_" + user_id + "_" + session_id
    logger.debug(f"tool_user_session_id: {tool_user_session_id}")

    logger.debug(
        f"Running code in language: {language}, session_id={session_id}, code={code}, tool_id={tool_id}, host={host}, service={service}, region={region}, timeout={timeout}"
    )

    tool_state = tool_context.state if tool_context else None
    ttl = int(os.getenv("AGENTKIT_TOOL_TTL", "1800"))
    if language.lower() in {"bash", "shell"}:
        res = invoke_agentkit_exec_bash(
            tool_id=tool_id,
            tool_user_session_id=tool_user_session_id,
            command=code,
            exec_dir=exec_dir,
            env=env,
            timeout=timeout,
            hard_timeout=hard_timeout,
            max_output_length=max_output_length,
            tool_state=tool_state,
            ttl=ttl,
        )
    else:
        res = invoke_agentkit_run_code(
            tool_id=tool_id,
            tool_user_session_id=tool_user_session_id,
            code=code,
            timeout=timeout,
            kernel_name=language,
            tool_state=tool_state,
            ttl=ttl,
        )
    logger.debug(f"Invoke run code response: {res}")

    try:
        return res["Result"]["Result"]
    except (KeyError, TypeError) as e:
        logger.error(f"Error occurred while running code: {e}, response is {res}")
        return res
