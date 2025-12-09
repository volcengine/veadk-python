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

import json
import os
from typing import Optional, List

from google.adk.tools import ToolContext

from veadk.config import getenv
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request
from veadk.auth.veauth.utils import get_credential_from_vefaas_iam

logger = get_logger(__name__)


def execute_skills(
    workflow_prompt: str,
    skills: Optional[List[str]] = None,
    tool_context: ToolContext = None,
    timeout: int = 300,
) -> str:
    """execute skills in a code sandbox and return the output.
    For C++ code, don't execute it directly, compile and execute via Python; write sources and object files to /tmp.

    Args:
        workflow_prompt (str): instruction of workflow
        skills (Optional[List[str]]): The skills will be invoked
        timeout (int, optional): The timeout in seconds for the code execution, less than or equal to 300. Defaults to 300.

    Returns:
        str: The output of the code execution.
    """

    tool_id = getenv("AGENTKIT_TOOL_ID")

    service = getenv(
        "AGENTKIT_TOOL_SERVICE_CODE", "agentkit"
    )  # temporary service for code run tool
    region = getenv("AGENTKIT_TOOL_REGION", "cn-beijing")
    host = getenv(
        "AGENTKIT_TOOL_HOST", service + "." + region + ".volces.com"
    )  # temporary host for code run tool
    logger.debug(f"tools endpoint: {host}")

    session_id = tool_context._invocation_context.session.id
    agent_name = tool_context._invocation_context.agent.name
    user_id = tool_context._invocation_context.user_id
    tool_user_session_id = agent_name + "_" + user_id + "_" + session_id
    logger.debug(f"tool_user_session_id: {tool_user_session_id}")

    logger.debug(
        f"Execute skills in session_id={session_id}, tool_id={tool_id}, host={host}, service={service}, region={region}, timeout={timeout}"
    )

    ak = getenv("VOLCENGINE_ACCESS_KEY")
    sk = getenv("VOLCENGINE_SECRET_KEY")
    header = {}

    if not (ak and sk):
        logger.debug("Get AK/SK from tool context failed.")
        ak = os.getenv("VOLCENGINE_ACCESS_KEY")
        sk = os.getenv("VOLCENGINE_SECRET_KEY")
        if not (ak and sk):
            logger.debug(
                "Get AK/SK from environment variables failed. Try to use credential from Iam."
            )
            credential = get_credential_from_vefaas_iam()
            ak = credential.access_key_id
            sk = credential.secret_access_key
            header = {"X-Security-Token": credential.session_token}
        else:
            logger.debug("Successfully get AK/SK from environment variables.")
    else:
        logger.debug("Successfully get AK/SK from tool context.")

    cmd = ["python", "agent.py", workflow_prompt]
    if skills:
        cmd.extend(["--skills"] + skills)

    # TODO: remove after agentkit supports custom environment variables setting
    env_vars = {
        "MODEL_AGENT_API_KEY": os.getenv("MODEL_AGENT_API_KEY"),
        "TOS_SKILLS_DIR": os.getenv("TOS_SKILLS_DIR"),
    }

    code = f"""
import subprocess
import os

env = os.environ.copy()
env.update({env_vars!r})

result = subprocess.run(
    {cmd!r},
    cwd='/home/gem/veadk_skills',
    capture_output=True,
    text=True,
    env=env,
    timeout={timeout - 10},
)
print(result.stdout)
if result.stderr:
    print(result.stderr)
    """

    res = ve_request(
        request_body={
            "ToolId": tool_id,
            "UserSessionId": tool_user_session_id,
            "OperationType": "RunCode",
            "OperationPayload": json.dumps(
                {
                    "code": code,
                    "timeout": timeout,
                    "kernel_name": "python3",
                }
            ),
        },
        action="InvokeTool",
        ak=ak,
        sk=sk,
        service=service,
        version="2025-10-30",
        region=region,
        host=host,
        header=header,
    )
    logger.debug(f"Invoke run code response: {res}")

    try:
        return res["Result"]["Result"]
    except KeyError as e:
        logger.error(f"Error occurred while running code: {e}, response is {res}")
        return res
