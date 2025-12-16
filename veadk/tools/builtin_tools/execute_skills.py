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


def _clean_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences (color codes, etc.)"""
    import re

    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


def _format_execution_result(result_str: str) -> str:
    """Format the execution results, handle escape characters and JSON structures"""
    try:
        result_json = json.loads(result_str)

        if not result_json.get("success"):
            message = result_json.get("message", "Unknown error")
            outputs = result_json.get("data", {}).get("outputs", [])
            if outputs and isinstance(outputs[0], dict):
                error_msg = outputs[0].get("ename", "Unknown error")
                return f"Execution failed: {message}, {error_msg}"

        outputs = result_json.get("data", {}).get("outputs", [])
        if not outputs:
            return "No output generated"

        formatted_lines = []
        for output in outputs:
            if output and isinstance(output, dict) and "text" in output:
                text = output["text"]
                text = _clean_ansi_codes(text)
                text = text.replace("\\n", "\n")
                formatted_lines.append(text)

        return "".join(formatted_lines).strip()

    except json.JSONDecodeError:
        return _clean_ansi_codes(result_str)
    except Exception as e:
        logger.warning(f"Error formatting result: {e}, returning raw result")
        return result_str


def execute_skills(
    workflow_prompt: str,
    skills: Optional[List[str]] = None,
    tool_context: ToolContext = None,
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

    ak = tool_context.state.get("VOLCENGINE_ACCESS_KEY")
    sk = tool_context.state.get("VOLCENGINE_SECRET_KEY")
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
    res = ve_request(
        request_body={},
        action="GetCallerIdentity",
        ak=ak,
        sk=sk,
        service="sts",
        version="2018-01-01",
        region=region,
        host="sts.volcengineapi.com",
    )
    try:
        account_id = res["Result"]["AccountId"]
    except KeyError as e:
        logger.error(f"Error occurred while getting account id: {e}, response is {res}")
        return res

    env_vars = {
        "TOS_SKILLS_DIR": f"tos://agentkit-platform-{account_id}/skills/",
        "TOOL_USER_SESSION_ID": tool_user_session_id,
    }

    code = f"""
import subprocess
import os

env = os.environ.copy()
for key, value in {env_vars!r}.items():
    if key not in env:
        env[key] = value

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
        return _format_execution_result(res["Result"]["Result"])
    except KeyError as e:
        logger.error(f"Error occurred while running code: {e}, response is {res}")
        return res
