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

from google.genai import types
from google.adk.agents.callback_context import CallbackContext

from veadk.integrations.ve_identity.auth_config import _get_default_region
from veadk.integrations.ve_identity.identity_client import IdentityClient
from veadk.integrations.ve_identity.token_manager import get_workload_token
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


region = _get_default_region()
identity_client = IdentityClient(region=region)


async def check_agent_authorization(
    callback_context: CallbackContext,
) -> Optional[types.Content]:
    workload_token = await get_workload_token(
        tool_context=callback_context,
        identity_client=identity_client,
    )

    # Parse role_id from workload_token
    # Format: trn:id:${Region}:${Account}:workloadpool/default/workload/${RoleId}
    role_id = None
    if workload_token:
        try:
            role_id = workload_token.split("/")[-1]
            logger.debug(f"Parsed role_id: {role_id}")
        except Exception as e:
            logger.warning(f"Failed to parse role_id from workload_token: {e}")

    agent_name = callback_context.agent_name
    user_id = callback_context._invocation_context.user_id

    namespace = "default"
    user_id = user_id
    action = "invoke"
    workload_id = role_id if role_id else agent_name

    allowed = identity_client.check_permission(
        principal_id=user_id,
        operation=action,
        resource_id=workload_id,
        namespace=namespace,
    )

    if allowed:
        logger.debug("Agent is authorized to run.")
        return None
    else:
        logger.warning("Agent is not authorized to run.")
        return types.Content(
            parts=[types.Part(text=f"Agent {agent_name} is not authorized to run.")],
            role="model",
        )
