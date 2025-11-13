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

import base64
import json
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


def _strip_bearer_prefix(token: str) -> str:
    """Remove 'Bearer ' prefix from token if present.
    Args:
        token: Token string that may contain "Bearer " prefix
    Returns:
        Token without "Bearer " prefix
    """
    return token[7:] if token.lower().startswith("bearer ") else token


def _extract_role_id_from_jwt(token: str) -> Optional[str]:
    """Extract role_id (sub field) from JWT token.
    Args:
        token: JWT token string (with or without "Bearer " prefix)
    Returns:
        Role ID from sub field, or None if parsing fails
    """
    try:
        # Remove "Bearer " prefix if present
        token = _strip_bearer_prefix(token)

        # JWT token has 3 parts separated by dots: header.payload.signature
        parts = token.split(".")
        if len(parts) != 3:
            logger.error("Invalid JWT format: expected 3 parts")
            return None

        # Decode payload (second part)
        payload_part = parts[1]

        # Add padding for base64url decoding (JWT doesn't use padding)
        missing_padding = len(payload_part) % 4
        if missing_padding:
            payload_part += "=" * (4 - missing_padding)

        # Decode base64 and parse JSON
        decoded_bytes = base64.urlsafe_b64decode(payload_part)
        payload = json.loads(decoded_bytes.decode("utf-8"))

        # Extract sub field as role_id
        return payload.get("act").get("sub")

    except (ValueError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse JWT token: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing JWT: {e}")
        return None


async def check_agent_authorization(
    callback_context: CallbackContext,
) -> Optional[types.Content]:
    """Check if the agent is authorized to run using VeIdentity."""
    user_id = callback_context._invocation_context.user_id

    try:
        workload_token = await get_workload_token(
            tool_context=callback_context, identity_client=identity_client
        )

        # Parse role_id from workload_token
        role_id = _extract_role_id_from_jwt(workload_token)

        principal = {"Type": "User", "Id": user_id}
        operation = {"Type": "Action", "Id": "invoke"}
        resource = {"Type": "Agent", "Id": role_id}

        allowed = identity_client.check_permission(
            principal=principal, operation=operation, resource=resource
        )

        if allowed:
            logger.info("Agent is authorized to run.")
            return None
        else:
            logger.warning("Agent is not authorized to run.")
            return types.Content(
                parts=[types.Part(text="Agent is not authorized to run.")], role="model"
            )

    except Exception as e:
        logger.error(f"Authorization check failed with error: {e}")
        return types.Content(
            parts=[types.Part(text="Failed to verify agent authorization.")],
            role="model",
        )
