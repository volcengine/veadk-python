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
from typing import Any, Optional

from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.config import getenv
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


def resolve_agentkit_tool_id(*preferred_env_names: str) -> str:
    """Resolve the first configured AgentKit tool id with AGENTKIT_TOOL_ID fallback."""
    for env_name in [*preferred_env_names, "AGENTKIT_TOOL_ID"]:
        tool_id = os.getenv(env_name)
        if tool_id:
            return tool_id

    return getenv("AGENTKIT_TOOL_ID")


def get_agentkit_endpoint_config(
    host_env_name: str = "AGENTKIT_TOOL_HOST",
) -> tuple[str, str, str, str]:
    """Return service, region, host and scheme for AgentKit tool invocation."""
    service = getenv("AGENTKIT_TOOL_SERVICE_CODE", "agentkit")

    cloud_provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
    if cloud_provider == "byteplus":
        sld = "bytepluses"
        default_region = "ap-southeast-1"
    else:
        sld = "volces"
        default_region = "cn-beijing"

    region = getenv("AGENTKIT_TOOL_REGION", default_region)
    host = getenv(host_env_name, service + "." + region + f".{sld}.com")
    scheme = getenv("AGENTKIT_TOOL_SCHEME", "https", allow_false_values=True).lower()
    if scheme not in {"http", "https"}:
        scheme = "https"

    return service, region, host, scheme


def get_agentkit_credentials(
    tool_state: Optional[dict[str, Any]] = None,
) -> tuple[str, str, dict[str, str]]:
    """Resolve AgentKit invocation credentials from tool state, env, or IAM."""
    ak = tool_state.get("VOLCENGINE_ACCESS_KEY") if tool_state else None
    sk = tool_state.get("VOLCENGINE_SECRET_KEY") if tool_state else None
    header: dict[str, str] = {}

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

    return ak, sk, header


def get_agentkit_account_id(tool_state: Optional[dict[str, Any]] = None) -> str:
    """Get the current caller account id for remote skills sandbox setup."""
    cloud_provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
    if cloud_provider == "vestack":
        return ""

    _, region, _, _ = get_agentkit_endpoint_config()
    ak, sk, header = get_agentkit_credentials(tool_state)
    host = (
        "open.byteplusapi.com"
        if cloud_provider == "byteplus"
        else "sts.volcengineapi.com"
    )
    res = ve_request(
        request_body={},
        action="GetCallerIdentity",
        ak=ak,
        sk=sk,
        service="sts",
        version="2018-01-01",
        region=region,
        host=host,
        header=header,
    )
    return res["Result"]["AccountId"]


def invoke_agentkit_run_code(
    *,
    tool_id: str,
    tool_user_session_id: str,
    code: str,
    timeout: int,
    kernel_name: str,
    tool_state: Optional[dict[str, Any]] = None,
    ttl: Optional[int] = None,
) -> dict[str, Any]:
    """Invoke the AgentKit RunCode operation."""
    service, region, host, scheme = get_agentkit_endpoint_config()
    ak, sk, header = get_agentkit_credentials(tool_state)

    request_body: dict[str, Any] = {
        "ToolId": tool_id,
        "UserSessionId": tool_user_session_id,
        "OperationType": "RunCode",
        "OperationPayload": json.dumps(
            {
                "code": code,
                "timeout": timeout,
                "kernel_name": kernel_name,
            }
        ),
    }
    if ttl is not None:
        request_body["Ttl"] = ttl

    return ve_request(
        request_body=request_body,
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


def invoke_agentkit_exec_bash(
    *,
    tool_id: str,
    tool_user_session_id: str,
    command: str,
    exec_dir: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
    timeout: int = 30,
    hard_timeout: Optional[int] = None,
    max_output_length: Optional[int] = None,
    tool_state: Optional[dict[str, Any]] = None,
    ttl: Optional[int] = None,
) -> dict[str, Any]:
    """Invoke AgentKit's Bash execution operation through InvokeTool."""
    service, region, host, scheme = get_agentkit_endpoint_config()
    ak, sk, header = get_agentkit_credentials(tool_state)

    operation_payload: dict[str, Any] = {
        "command": command,
        "timeout": timeout,
    }
    if exec_dir is not None:
        operation_payload["exec_dir"] = exec_dir
    if env is not None:
        operation_payload["env"] = env
    if hard_timeout is not None:
        operation_payload["hard_timeout"] = hard_timeout
    if max_output_length is not None:
        operation_payload["max_output_length"] = max_output_length

    request_body: dict[str, Any] = {
        "ToolId": tool_id,
        "OperationType": "ExecBash",
        "UserSessionId": tool_user_session_id,
        "OperationPayload": json.dumps(operation_payload),
    }
    if ttl is not None:
        request_body["Ttl"] = ttl

    return ve_request(
        request_body=request_body,
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
