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
    tool_context: ToolContext = None,
) -> str:
    """Execute skills in a sandbox and return the output.

    Execute skills in a remote sandbox amining to provide isolation and security.

    Args:
        workflow_prompt (str): instruction of workflow

    Returns:
        str: The output of the code execution.
    """
    timeout = 900  # The timeout in seconds for the code execution, less than or equal to 900. Defaults to 900. Hard-coded to prevent the Agent from adjusting this parameter.

    tool_id = getenv("AGENTKIT_TOOL_ID")

    service = getenv(
        "AGENTKIT_TOOL_SERVICE_CODE", "agentkit"
    )  # temporary service for code run tool
    region = getenv("AGENTKIT_TOOL_REGION", "cn-beijing")
    # volces example: agentkit.cn-beijing.volces.com
    host = getenv(
        "AGENTKIT_TOOL_HOST", service + "." + region + ".volces.com"
    )  # temporary host for code run tool

    provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
    if provider == "byteplus":
        region = (
            os.getenv("REGION") or os.getenv("AGENTKIT_TOOL_REGION") or "ap-southeast-1"
        )
        # byteplus example: agentkit.ap-southeast-1.bytepluses.com
        host = getenv("AGENTKIT_TOOL_HOST", service + "." + region + ".bytepluses.com")
    logger.debug(f"tools endpoint: {host}")

    session_id = tool_context._invocation_context.session.id
    agent_name = tool_context._invocation_context.agent.name
    user_id = tool_context._invocation_context.user_id
    tool_user_session_id = agent_name + "_" + user_id + "_" + session_id
    logger.debug(f"tool_user_session_id: {tool_user_session_id}")

    cloud_provider = getenv("CLOUD_PROVIDER", "", allow_false_values=True)
    scheme = getenv("AGENTKIT_TOOL_SCHEME", "https", allow_false_values=True).lower()
    if scheme not in {"http", "https"}:
        scheme = "https"

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

    account_id = ""
    if cloud_provider != "vestack":
        res = ve_request(
            request_body={},
            action="GetCallerIdentity",
            ak=ak,
            sk=sk,
            service="sts",
            version="2018-01-01",
            region=region,
            host="sts.volcengineapi.com",
            header=header,
        )
        try:
            account_id = res["Result"]["AccountId"]
        except KeyError as e:
            logger.error(
                f"Error occurred while getting account id: {e}, response is {res}"
            )
            return res

    skill_space_id = os.getenv("SKILL_SPACE_ID", "")
    if not skill_space_id:
        logger.warning("SKILL_SPACE_ID environment variable is not set")

    env_vars = {
        "TOS_SKILLS_DIR": f"tos://agentkit-platform-{account_id}/skills/",
        "SKILL_SPACE_ID": skill_space_id,
        "TOOL_USER_SESSION_ID": tool_user_session_id,
    }

    code = f"""
import subprocess
import os
import time
import select
import sys

env = os.environ.copy()
for key, value in {env_vars!r}.items():
    if key not in env:
        env[key] = value

process = subprocess.Popen(
    {cmd!r},
    cwd='/home/gem/veadk_skills',
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env=env,
    bufsize=1, 
    universal_newlines=True
)

start_time = time.time()
timeout = {timeout - 10}

with open('/tmp/agent.log', 'w') as log_file:
    while True:
        if time.time() - start_time > timeout:
            process.kill()
            log_file.write('log_type=stderr request_id=x function_id=y revision_number=1 Process timeout\\n')
            print("Process timeout", end='', file=sys.stderr)
            break
            
        reads = [process.stdout.fileno(), process.stderr.fileno()]
        ret = select.select(reads, [], [], 1)
        
        for fd in ret[0]:
            if fd == process.stdout.fileno():
                line = process.stdout.readline()
                if line:
                    log_file.write(f'log_type=stdout request_id=x function_id=y revision_number=1 {{line}}')
                    log_file.flush()
                    print(line, end='')
            if fd == process.stderr.fileno():
                line = process.stderr.readline()
                if line:
                    log_file.write(f'log_type=stderr request_id=x function_id=y revision_number=1 {{line}}')
                    log_file.flush()
                    print(line, end='', file=sys.stderr)
        
        if process.poll() is not None:
            break
    
    for line in process.stdout:
        log_file.write(f'log_type=stdout request_id=x function_id=y revision_number=1 {{line}}')
        print(line, end='')
    for line in process.stderr:
        log_file.write(f'log_type=stderr request_id=x function_id=y revision_number=1 {{line}}')
        print(line, end='', file=sys.stderr)
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
        scheme=scheme,
    )
    logger.debug(f"Invoke run code response: {res}")

    try:
        return _format_execution_result(res["Result"]["Result"])
    except KeyError as e:
        logger.error(f"Error occurred while running code: {e}, response is {res}")
        return res
