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

from typing import List, Optional

from langchain.tools import ToolRuntime, tool

from veadk.tools.builtin_tools._agentkit import (
    get_agentkit_account_id,
    resolve_agentkit_tool_id,
)
from veadk.tools.builtin_tools.run_sandbox_agent import (
    _format_execution_result,
    _build_agent_command,
    _build_agent_runner_code,
)
from veadk.utils.logger import get_logger
from veadk.tools.builtin_tools._agentkit import (
    get_agentkit_endpoint_config,
    invoke_agentkit_run_code,
)

logger = get_logger(__name__)


@tool
def execute_skills(
    workflow_prompt: str,
    runtime: ToolRuntime,
    skills: Optional[List[str]] = None,
    timeout: int = 900,
) -> str:
    """execute skills in a code sandbox and return the output.
    For C++ code, don't execute it directly, compile and execute via Python; write sources and object files to /tmp.

    Args:
        workflow_prompt (str): instruction of workflow
        skills (Optional[List[str]]): The skills will be invoked
        timeout (int, optional): The timeout in seconds for the code execution, less than or equal to 900. Defaults to 900.

    Returns:
        str: The output of the code execution.
    """

    tool_id = resolve_agentkit_tool_id("AGENTKIT_TOOL_ID_SKILLS")
    service, region, host, _ = get_agentkit_endpoint_config()
    logger.debug(f"tools endpoint: {host}")

    session_id = runtime.session_id  # type: ignore
    agent_name = runtime.context.agent_name  # type: ignore
    user_id = runtime.context.user_id  # type: ignore
    tool_user_session_id = agent_name + "_" + user_id + "_" + session_id
    logger.debug(f"tool_user_session_id: {tool_user_session_id}")

    logger.debug(
        f"Execute skills in session_id={session_id}, tool_id={tool_id}, host={host}, service={service}, region={region}, timeout={timeout}"
    )

    cmd = _build_agent_command(workflow_prompt=workflow_prompt, skills=skills)
    try:
        account_id = get_agentkit_account_id()
    except KeyError as e:
        logger.error(f"Error occurred while getting account id: {e}")
        return {"error": str(e)}

    env_vars = {"TOOL_USER_SESSION_ID": tool_user_session_id}
    if account_id:
        env_vars["TOS_SKILLS_DIR"] = f"tos://agentkit-platform-{account_id}/skills/"

    code = _build_agent_runner_code(
        cmd=cmd,
        timeout=timeout,
        env_vars=env_vars,
    )

    res = invoke_agentkit_run_code(
        tool_id=tool_id,
        tool_user_session_id=tool_user_session_id,
        code=code,
        timeout=timeout,
        kernel_name="python3",
    )
    logger.debug(f"Invoke run code response: {res}")

    try:
        return _format_execution_result(res["Result"]["Result"])
    except KeyError as e:
        logger.error(f"Error occurred while running code: {e}, response is {res}")
        return res
