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

from langchain.tools import ToolRuntime, tool

from veadk.tools.builtin_tools._agentkit import (
    get_agentkit_endpoint_config,
    invoke_agentkit_run_code,
    resolve_agentkit_tool_id,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


@tool
def run_code(code: str, language: str, runtime: ToolRuntime, timeout: int = 30) -> str:
    """Run code in a code sandbox and return the output.
    For C++ code, don't execute it directly, compile and execute via Python; write sources and object files to /tmp.

    Args:
        code (str): The code to run.
        language (str): The programming language of the code. Language must be one of the supported languages: python3.
        timeout (int, optional): The timeout in seconds for the code execution. Defaults to 30.

    Returns:
        str: The output of the code execution.
    """

    tool_id = resolve_agentkit_tool_id("AGENTKIT_TOOL_ID_SCRIPT")
    service, region, host, _ = get_agentkit_endpoint_config()
    logger.debug(f"tools endpoint: {host}")

    session_id = runtime.context.session_id  # type: ignore
    user_id = runtime.context.user_id  # type: ignore
    agent_name = runtime.context.agent_name  # type: ignore

    tool_user_session_id = agent_name + "_" + user_id + "_" + session_id
    logger.debug(f"tool_user_session_id: {tool_user_session_id}")

    logger.debug(
        f"Running code in language: {language}, session_id={session_id}, code={code}, tool_id={tool_id}, host={host}, service={service}, region={region}, timeout={timeout}"
    )

    res = invoke_agentkit_run_code(
        tool_id=tool_id,
        tool_user_session_id=tool_user_session_id,
        code=code,
        timeout=timeout,
        kernel_name=language,
    )
    logger.debug(f"Invoke run code response: {res}")

    try:
        return res["Result"]["Result"]
    except KeyError as e:
        logger.error(f"Error occurred while running code: {e}, response is {res}")
        return res
