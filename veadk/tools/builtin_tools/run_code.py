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

from google.adk.tools import ToolContext

from veadk.config import getenv
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


def run_code(code: str, language: str, tool_context: ToolContext) -> str:
    """Run code in a code sandbox and return the output.

    Args:
        code (str): The code to run.
        language (str): The programming language of the code. Language must be one of the supported languages: python3.

    Returns:
        str: The output of the code execution.
    """

    tool_id = getenv("AGENTKIT_TOOL_ID")
    host = getenv("AGENTKIT_TOOL_HOST")  # temporary host for code run tool
    service = getenv(
        "AGENTKIT_TOOL_SERVICE_CODE"
    )  # temporary service for code run tool
    region = getenv("AGENTKIT_TOOL_REGION", "cn-beijing")

    session_id = tool_context._invocation_context.session.id

    logger.debug(
        f"Running code in language: {language}, session_id={session_id}, code={code}, tool_id={tool_id}, host={host}, service={service}, region={region}"
    )

    access_key = getenv("VOLCENGINE_ACCESS_KEY")
    secret_key = getenv("VOLCENGINE_SECRET_KEY")

    res = ve_request(
        request_body={
            "ToolId": tool_id,
            "UserSessionId": session_id,
            "OperationType": "RunCode",
            "OperationPayload": json.dumps(
                {
                    "code": code,
                    "timeout": 30,
                    "kernel_name": language,
                }
            ),
        },
        action="InvokeTool",
        ak=access_key,
        sk=secret_key,
        service=service,
        version="2025-10-30",
        region=region,
        host=host,
    )

    logger.debug(f"Invoke run code response: {res}")

    try:
        return res["Result"]["Result"]
    except KeyError as e:
        logger.error(f"Error occurred while running code: {e}, response is {res}")
        return res
