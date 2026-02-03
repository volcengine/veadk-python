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
import requests
from typing import Optional, List, Dict, Any, Union
from volcenginesdkllmshield.models.llm_shield_sign import request_sign

from google.adk.plugins import BasePlugin
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.tool_context import ToolContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types
from google.adk.tools.base_tool import BaseTool

from veadk.config import getenv
from veadk.utils.logger import get_logger
from veadk.auth.veauth.utils import get_credential_from_vefaas_iam

logger = get_logger(__name__)


class LLMShieldPlugin(BasePlugin):
    """
    LLM Shield Plugin for content moderation and safety.

    This plugin integrates with Volcano Engine's LLM Shield service to provide
    real-time content moderation for user inputs, model outputs, and tool interactions.
    It helps detect and block potentially harmful content including sensitive information,
    prompt injection attacks, and policy violations.

    Examples:
        Basic usage with default settings:
        ```python
        from veadk.tools.builtin_tools.llm_shield import content_safety
        agent = Agent(
            before_model_callback=content_safety.before_model_callback,
            after_model_callback=content_safety.after_model_callback,
            before_tool_callback=content_safety.before_tool_callback,
            after_tool_callback=content_safety.after_tool_callback,
        )
        ```
    """

    def __init__(self, timeout: int = 50) -> None:
        """
        Initialize the LLM Shield Plugin.

        Args:
            timeout (int, optional): Request timeout in seconds. Defaults to 50.
        """
        self.name = "LLMShieldPlugin"
        super().__init__(name=self.name)

        self.appid = getenv("TOOL_LLM_SHIELD_APP_ID")
        self.region = (
            os.getenv("REGION") or os.getenv("TOOL_LLM_SHIELD_REGION") or "cn-beijing"
        )
        self.timeout = timeout
        self.url = getenv(
            "TOOL_LLM_SHIELD_URL",
            f"https://{self.region}.sdk.access.llm-shield.omini-shield.com",
        )
        self.api_key = getenv("TOOL_LLM_SHIELD_API_KEY", allow_false_values=True)

        self.category_map = {
            101: "Model Misuse",
            103: "Sensitive Information",
            104: "Prompt Injection",
            106: "General Topic Control",
            107: "Computational Resource Consumption",
        }

    def _request_llm_shield(self, message: str, role: str) -> Optional[str]:
        """
        Make a request to the LLM Shield service for content moderation.

        This method sends a message to the LLM Shield API for security analysis.
        If the content is deemed risky, it returns a blocking message explaining
        the violation. Otherwise, it returns None to allow the content through.

        Args:
            message (str): The content to be moderated
            role (str): The role of the message sender ("user" or "assistant")

        Returns:
            Optional[str]: A blocking message if content violates policies,
                         None if content is safe or on error
        """
        if not self.appid:
            logger.error("LLM Shield app ID not configured")
            return None

        body = {
            "Message": {
                "Role": role,
                "Content": message,
                "ContentType": 1,
            },
            "Scene": self.appid,
        }

        body_json = json.dumps(body).encode("utf-8")

        path = "/v2/moderate"
        action = "Moderate"
        version = "2025-08-31"

        # Check if using API key authentication
        logger.debug(f"API key value: {self.api_key}, type: {type(self.api_key)}")
        if self.api_key and self.api_key != "":
            logger.debug("Using API key authentication (no AK/SK signature)")
            # Use API key authentication only - match curl command headers exactly
            signed_header = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
            }
        else:
            logger.debug("Using AK/SK signature authentication")
            # Use AK/SK signature authentication
            ak = os.getenv("VOLCENGINE_ACCESS_KEY")
            sk = os.getenv("VOLCENGINE_SECRET_KEY")
            session_token = ""
            if not (ak and sk):
                logger.debug("Get AK/SK from environment variables failed.")
                credential = get_credential_from_vefaas_iam()
                ak = credential.access_key_id
                sk = credential.secret_access_key
                session_token = credential.session_token
            else:
                logger.debug("Successfully get AK/SK from environment variables.")

            header = {"X-Security-Token": session_token}
            signed_header = request_sign(
                header, ak, sk, self.region, self.url, path, action, body_json
            )

            signed_header.update(
                {
                    "Content-Type": "application/json",
                    "X-Top-Service": "llmshield",
                    "X-Top-Region": self.region,
                }
            )

        try:
            response = requests.post(
                self.url + path,
                headers=signed_header,
                data=body_json,
                params={"Action": action, "Version": version},
                timeout=self.timeout,
            )

            if response.status_code != 200:
                logger.error(
                    f"LLM Shield HTTP error: {response.status_code} - {response.text}"
                )
                return None
            response = response.json()
        except requests.exceptions.Timeout:
            logger.error("LLM Shield request timeout")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"LLM Shield network request failed: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"LLM Shield response JSON decode failed: {e}")
            return None
        except Exception as e:
            logger.error(f"LLM Shield request failed: {e}")
            return None

        # Process risk detection results
        result = response.get("Result", None)
        if result:
            decision = result.get("Decision", None)
            decision_type = decision.get("DecisionType", None)
            risk_info = result.get("RiskInfo", None)
            if decision_type is not None and int(decision_type) == 2 and risk_info:
                risks = risk_info.get("Risks", [])
                if risks:
                    # Extract risk categories for user-friendly error message
                    risk_reasons = set()
                    for risk in risks:
                        category = risk.get("Category", None)
                        if category:
                            category_name = self.category_map.get(
                                int(category), f"Category {category}"
                            )
                            risk_reasons.add(category_name)

                    # Generate blocking response
                    reason_text = (
                        ", ".join(risk_reasons)
                        if risk_reasons
                        else "security policy violation"
                    )
                    response_text = (
                        f"Your request has been blocked due to: {reason_text}. "
                        f"Please modify your input and try again."
                    )

                    return response_text

        return None

    def before_agent_callback(
        self, callback_context: CallbackContext, **kwargs
    ) -> None:
        # TODO: Implement agent-level input validation and context analysis
        return None

    def after_agent_callback(self, callback_context: CallbackContext, **kwargs) -> None:
        # TODO: Implement post-agent analysis and context analysis
        return None

    def before_model_callback(
        self, callback_context: CallbackContext, llm_request: LlmRequest, **kwargs
    ) -> Optional[LlmResponse]:
        """
        Moderate user input before sending to the language model.

        Extracts the last user message from the LLM request and checks it
        against the LLM Shield service. If the content violates safety policies,
        returns a blocking response instead of allowing the request to proceed.

        Args:
            callback_context (CallbackContext): The callback execution context
            llm_request (LlmRequest): The incoming LLM request to moderate
            **kwargs: Additional keyword arguments

        Returns:
            Optional[LlmResponse]: A blocking response if content is unsafe,
                                 None if content is safe to proceed
        """
        # Extract the last user message for moderation
        last_user_message = None
        contents = getattr(llm_request, "contents", [])

        if contents:
            last_content = contents[-1]
            last_role = getattr(last_content, "role", "")
            last_parts = getattr(last_content, "parts", [])

            if last_role == "user" and last_parts:
                last_user_message = getattr(last_parts[0], "text", "")

        # Skip moderation if message is empty
        if not last_user_message:
            return None

        response = self._request_llm_shield(message=last_user_message, role="user")
        if response:
            logger.debug("LLM Shield triggered in before_model_callback.")
            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=response)],
                ),
                partial=True,
            )
        return None

    def after_model_callback(
        self, callback_context: CallbackContext, llm_response: LlmResponse, **kwargs
    ) -> Optional[LlmResponse]:
        """
        Moderate model output before returning to the user.

        Extracts the model's response and checks it against the LLM Shield service.
        If the model's output violates safety policies, returns a blocking response
        instead of the original model output.

        Args:
            callback_context (CallbackContext): The callback execution context
            llm_response (LlmResponse): The model's response to moderate
            **kwargs: Additional keyword arguments

        Returns:
            Optional[LlmResponse]: A blocking response if content is unsafe,
                                 None if content is safe to return
        """
        # Extract the model's response for moderation
        last_model_message = None
        content = getattr(llm_response, "content", [])

        if content:
            last_role = getattr(content, "role", "")
            last_parts = getattr(content, "parts", [])

            if last_role == "model" and last_parts:
                last_model_message = getattr(last_parts[0], "text", "")

        # Skip moderation if message is empty
        if not last_model_message:
            return None

        response = self._request_llm_shield(
            message=last_model_message, role="assistant"
        )
        if response:
            logger.debug("LLM Shield triggered in after_model_callback.")
            return LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=response)],
                ),
                partial=True,
            )
        return None

    def before_tool_callback(
        self, tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext, **kwargs
    ) -> Optional[Dict]:
        """
        Moderate tool arguments before tool execution.

        Combines all tool arguments into a message and checks it against
        the LLM Shield service. If the arguments contain unsafe content,
        returns a blocking result instead of allowing tool execution.

        Args:
            tool (BaseTool): The tool to be executed
            args (Dict[str, Any]): The arguments passed to the tool
            tool_context (ToolContext): The tool execution context
            **kwargs: Additional keyword arguments

        Returns:
            Optional[Dict]: A blocking result if arguments are unsafe,
                          None if arguments are safe to proceed
        """
        args_list = []

        for key, value in args.items():
            args_list.append(f"{key}: {value}")

        message = "\n".join(args_list)
        response = self._request_llm_shield(message=message, role="user")
        if response:
            logger.debug("LLM Shield triggered in before_tool_callback.")
            return {"result": response}
        return None

    def after_tool_callback(
        self,
        tool: BaseTool,
        args: Dict[str, Any],
        tool_context: CallbackContext,
        tool_response: Union[str, Dict[str, Any], List[Any]],
        **kwargs,
    ) -> Optional[Dict]:
        """
        Moderate tool output after tool execution.

        Processes the tool's response (string, dict, or list) into a message
        and checks it against the LLM Shield service. If the tool's output
        violates safety policies, returns a blocking result.

        Args:
            tool (BaseTool): The tool that was executed
            args (Dict[str, Any]): The arguments that were passed to the tool
            tool_context (CallbackContext): The tool execution context
            tool_response (Union[str, Dict[str, Any], List[Any]]): The tool's response
            **kwargs: Additional keyword arguments

        Returns:
            Optional[Dict]: A blocking result if tool output is unsafe,
                          None if output is safe to return
        """
        message = ""
        if isinstance(tool_response, str):
            message = tool_response
        elif isinstance(tool_response, dict):
            for key, value in tool_response.items():
                message += f"{value}\n"
        elif isinstance(tool_response, list):
            for item in tool_response:
                message += f"{item}\n"

        response = self._request_llm_shield(message=message, role="assistant")
        if response:
            logger.debug("LLM Shield triggered in after_tool_callback.")
            return {"result": response}
        return None


content_safety = LLMShieldPlugin()
