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

from google.adk.tools import ToolContext

from veadk.tools.builtin_tools._agentkit import (
    get_agentkit_account_id,
    resolve_agentkit_tool_id,
)
from veadk.tools.builtin_tools.run_sandbox_agent import run_sandbox_agent
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def execute_skills(
    workflow_prompt: str,
    tool_context: ToolContext = None,
    env_vars: Optional[dict[str, str]] = None,
) -> str:
    """Execute skills in a sandbox and return the output.

    Execute skills in a remote sandbox amining to provide isolation and security.

    Args:
        workflow_prompt (str): instruction of workflow
        env_vars (Optional[dict[str, str]]): Environment variables passed to the
            skill agent process for this execution only.

    Returns:
        str: The output of the code execution.
    """
    timeout = 900
    tool_id = resolve_agentkit_tool_id("AGENTKIT_TOOL_ID_SKILLS")
    account_id = get_agentkit_account_id(tool_context.state if tool_context else None)

    extra_env_vars = {}
    if account_id:
        extra_env_vars["TOS_SKILLS_DIR"] = (
            f"tos://agentkit-platform-{account_id}/skills/"
        )
    if env_vars:
        extra_env_vars.update(env_vars)

    return run_sandbox_agent(
        workflow_prompt=workflow_prompt,
        tool_id=tool_id,
        tool_context=tool_context,
        timeout=timeout,
        extra_env_vars=extra_env_vars,
    )
