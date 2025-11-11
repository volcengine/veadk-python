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
from typing import Optional

from google.genai import types
from google.adk.agents.callback_context import CallbackContext

from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


def check_agent_authorization(
    callback_context: CallbackContext,
) -> Optional[types.Content]:
    """Callback to check agent authorization before execution.

    Args:
        callback_context (CallbackContext): The callback context containing agent info.

    Returns:
        Optional[types.Content]: If authorization fails, return a Content object with
        an error message; otherwise, return None to proceed.
    """
    ak = callback_context.state.get("VOLCENGINE_ACCESS_KEY")
    sk = callback_context.state.get("VOLCENGINE_SECRET_KEY")
    session_token = ""

    if not (ak and sk):
        logger.debug("Get AK/SK from tool context failed.")
        ak = os.getenv("VOLCENGINE_ACCESS_KEY")
        sk = os.getenv("VOLCENGINE_SECRET_KEY")
        if not (ak and sk):
            logger.debug("Get AK/SK from environment variables failed.")
            credential = get_credential_from_vefaas_iam()
            ak = credential.access_key_id
            sk = credential.secret_access_key
            session_token = credential.session_token
        else:
            logger.debug("Successfully get AK/SK from environment variables.")
    else:
        logger.debug("Successfully get AK/SK from tool context.")

    agent_name = callback_context.agent_name
    user_id = callback_context._invocation_context.user_id

    namespace = "default"
    user_id = user_id
    action = "invoke"
    workload_id = agent_name

    response = ve_request(
        request_body={
            "NamespaceName": namespace,
            "Principal": {"Type": "User", "Id": user_id},
            "Operation": {"Type": "Action", "Id": action},
            "Resource": {"Type": "Agent", "Id": workload_id},
        },
        action="CheckPermission",
        ak=ak,
        sk=sk,
        service="id",
        version="2025-10-30",
        region="cn-beijing",
        host="open.volcengineapi.com",
        header={"X-Security-Token": session_token},
    )

    try:
        allowed = response["Result"]["Allowed"]
        if allowed:
            logger.debug("Agent is authorized to run.")
            return None
        else:
            logger.warning("Agent is not authorized to run.")
            return types.Content(
                parts=[
                    types.Part(text=f"Agent {agent_name} is not authorized to run.")
                ],
                role="model",
            )
    except Exception as e:
        logger.error(f"Authorization check failed: {e}")
        return None
