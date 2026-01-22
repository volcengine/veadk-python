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

from veadk.integrations.ve_identity import (
    get_default_identity_client,
    get_workload_token,
)
from veadk.utils.logger import get_logger
from veadk.utils.auth import extract_delegation_chain_from_jwt

logger = get_logger(__name__)

identity_client = get_default_identity_client()


async def check_agent_authorization(
    callback_context: CallbackContext,
) -> Optional[types.Content]:
    """Check if the agent is authorized to run using Agent Identity."""
    try:
        workload_token = await get_workload_token(
            tool_context=callback_context, identity_client=identity_client
        )

        # Parse user_id and actors from workload_token
        user_id, actors = extract_delegation_chain_from_jwt(workload_token)

        if not user_id:
            logger.warning("Failed to extract user_id from JWT token")
            return types.Content(
                parts=[types.Part(text="Failed to verify agent authorization.")],
                role="model",
            )

        if len(actors) == 0:
            logger.warning("Failed to extract actors from JWT token")
            return types.Content(
                parts=[types.Part(text="Failed to verify agent authorization.")],
                role="model",
            )

        # The first actor in the chain is the agent itself
        role_id = actors[0]

        principal = {"Type": "user", "Id": user_id}
        operation = {"Type": "action", "Id": "invoke"}
        resource = {"Type": "agent", "Id": role_id}
        original_callers = [{"Type": "agent", "Id": actor} for actor in actors[1:]]

        allowed = identity_client.check_permission(
            principal=principal,
            operation=operation,
            resource=resource,
            original_callers=original_callers,
            namespace_name="wqf--test",
        )

        if allowed:
            logger.info(f"Agent {role_id} is authorized to run by user {user_id}.")
            return None
        else:
            logger.warning(
                f"Agent {role_id} is not authorized to run by user {user_id}."
            )
            return types.Content(
                parts=[
                    types.Part(
                        text=f"Agent {role_id} is not authorized to run by user {user_id}."
                    )
                ],
                role="model",
            )

    except Exception as e:
        logger.error(f"Authorization check failed with error: {e}")
        return types.Content(
            parts=[types.Part(text="Failed to verify agent authorization.")],
            role="model",
        )
