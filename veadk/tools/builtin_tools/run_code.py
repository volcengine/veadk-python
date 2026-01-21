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

from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.config import getenv
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


def run_code(
    code: str, language: str, tool_context: ToolContext, timeout: int = 30
) -> str:
    """Run code in a code sandbox and return the output.
    For C++ code, don't execute it directly, compile and execute via Python; write sources and object files to /tmp.

    Args:
        code (str): The code to run.
        language (str): The programming language of the code. Language must be one of the supported languages: python3.
        timeout (int, optional): The timeout in seconds for the code execution. Defaults to 30.

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
    scheme = getenv("AGENTKIT_TOOL_SCHEME", "https", allow_false_values=True).lower()
    if scheme not in {"http", "https"}:
        scheme = "https"
    logger.debug(f"tools endpoint: {host}")

    session_id = tool_context._invocation_context.session.id
    agent_name = tool_context._invocation_context.agent.name
    user_id = tool_context._invocation_context.user_id
    tool_user_session_id = agent_name + "_" + user_id + "_" + session_id
    logger.debug(f"tool_user_session_id: {tool_user_session_id}")

    logger.debug(
        f"Running code in language: {language}, session_id={session_id}, code={code}, tool_id={tool_id}, host={host}, service={service}, region={region}, timeout={timeout}"
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

    res = ve_request(
        request_body={
            "ToolId": tool_id,
            "UserSessionId": tool_user_session_id,
            "OperationType": "RunCode",
            "OperationPayload": json.dumps(
                {
                    "code": code,
                    "timeout": timeout,
                    "kernel_name": language,
                }
            ),
            "Ttl": os.getenv("AGENTKIT_TOOL_TTL", 1800),
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
        return res["Result"]["Result"]
    except KeyError as e:
        logger.error(f"Error occurred while running code: {e}, response is {res}")
        return res
