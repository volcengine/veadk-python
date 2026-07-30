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
import time
from typing import Any, Optional

from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.config import getenv
from veadk.utils.logger import get_logger
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)


_SESSION_READY_TIMEOUT = 120.0
_SESSION_POLL_INTERVAL = 1.0
_SESSION_TERMINAL_STATUSES = frozenset({"failed", "terminating", "terminated"})


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


def ensure_agentkit_session_endpoint(
    *,
    tool_id: str,
    tool_user_session_id: str,
    tool_state: Optional[dict[str, Any]] = None,
    ttl: int = 1800,
    prefer_internal_endpoint: bool = False,
    wait_until_ready: bool = False,
    ready_timeout: float = _SESSION_READY_TIMEOUT,
    poll_interval: float = _SESSION_POLL_INTERVAL,
) -> str:
    """Create or reuse an AgentKit tool session and return its endpoint."""
    from agentkit.sdk.tools import types as tools_types
    from agentkit.sdk.tools.client import AgentkitToolsClient

    if wait_until_ready:
        if ready_timeout < 0:
            raise ValueError("ready_timeout must be greater than or equal to 0")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be greater than 0")

    _, region, _, _ = get_agentkit_endpoint_config()
    ak, sk, header = get_agentkit_credentials(tool_state)
    session_token = header.get("X-Security-Token", "")
    client = AgentkitToolsClient(
        access_key=ak,
        secret_key=sk,
        region=region,
        session_token=session_token,
    )
    session = client.create_session(
        tools_types.CreateSessionRequest(
            ToolId=tool_id,
            UserSessionId=tool_user_session_id,
            Ttl=ttl,
        )
    )
    if not wait_until_ready:
        public_endpoint = getattr(session, "endpoint", None)
        internal_endpoint = getattr(session, "internal_endpoint", None)
        endpoint = (
            internal_endpoint or public_endpoint
            if prefer_internal_endpoint
            else public_endpoint or internal_endpoint
        )
        if endpoint:
            return endpoint

        session_id = session.session_id
        if not session_id:
            return ""
        current_session = client.get_session(
            tools_types.GetSessionRequest(
                ToolId=tool_id,
                SessionId=session_id,
            )
        )
        if prefer_internal_endpoint:
            return current_session.internal_endpoint or current_session.endpoint or ""
        return current_session.endpoint or current_session.internal_endpoint or ""

    session_id = session.session_id
    if not session_id:
        raise RuntimeError("AgentKit CreateSession response is missing SessionId")

    deadline = time.monotonic() + ready_timeout
    last_status = "Unknown"
    while True:
        current_session = client.get_session(
            tools_types.GetSessionRequest(
                ToolId=tool_id,
                SessionId=session_id,
            )
        )
        status = (getattr(current_session, "status", None) or "").strip()
        last_status = status or "Unknown"
        logger.debug(f"AgentKit session {session_id} status: {last_status}")
        normalized_status = status.lower()
        if normalized_status == "ready":
            public_endpoint = getattr(current_session, "endpoint", None) or getattr(
                session, "endpoint", None
            )
            internal_endpoint = getattr(
                current_session, "internal_endpoint", None
            ) or getattr(session, "internal_endpoint", None)
            endpoint = (
                internal_endpoint or public_endpoint
                if prefer_internal_endpoint
                else public_endpoint or internal_endpoint
            )
            if endpoint:
                return endpoint
            raise RuntimeError(
                f"AgentKit session {session_id} is Ready but has no endpoint"
            )
        if normalized_status in _SESSION_TERMINAL_STATUSES:
            raise RuntimeError(
                f"AgentKit session {session_id} entered terminal status {last_status}"
            )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Timed out waiting for AgentKit session {session_id} to become "
                f"Ready; last status: {last_status}"
            )
        time.sleep(min(poll_interval, remaining))
