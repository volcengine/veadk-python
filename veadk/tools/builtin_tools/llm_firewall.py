from typing import Optional, List
from volcenginesdkllmshield import ClientV2, ModerateV2Request, MessageV2, ContentTypeV2

from google.adk.plugins import BasePlugin
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types

from veadk.config import getenv
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class LLMFirewallPlugin(BasePlugin):
    """
    LLM Firewall Plugin for content moderation and security filtering.

    This plugin integrates with Volcengine's LLM Firewall service to provide real-time
    content moderation for LLM requests. It analyzes user inputs for various risks
    including prompt injection, sensitive information, and policy violations before
    allowing requests to reach the language model.

    Examples:
        Basic usage with default settings:
        ```python
        governance = LLMFirewallPlugin()
        agent = Agent(
            before_model_callback=governance.before_model_callback
        )
        ```
    """

    def __init__(
        self, max_history: int = 5, region: str = "cn-beijing", timeout: int = 50
    ) -> None:
        """
        Initialize the LLM Firewall Plugin.

        Sets up the plugin with Volcengine LLM Firewall service configuration
        and initializes the moderation client.

        Args:
            max_history (int, optional): Maximum number of conversation turns
                to include in moderation context. Defaults to 5.
            region (str, optional): Volcengine service region.
                Defaults to "cn-beijing".
            timeout (int, optional): Request timeout in seconds.
                Defaults to 50.

        Raises:
            ValueError: If required environment variables are missing
        """
        self.name = "LLMFirewallPlugin"
        super().__init__(name=self.name)

        self.ak = getenv("VOLCENGINE_ACCESS_KEY")
        self.sk = getenv("VOLCENGINE_SECRET_KEY")
        self.appid = getenv("TOOL_LLM_FIREWALL_APP_ID")
        self.region = region
        self.llm_fw_url = (
            f"https://{self.region}.sdk.access.llm-shield.omini-shield.com"
        )
        self.timeout = timeout
        self.max_history = max_history

        self.client = ClientV2(self.llm_fw_url, self.ak, self.sk, region, self.timeout)

        self.category_map = {
            101: "Model Misuse",
            103: "Sensitive Information",
            104: "Prompt Injection",
            106: "General Topic Control",
            107: "Computational Resource Consumption",
        }

    def _get_system_instruction(self, llm_request: LlmRequest) -> str:
        """
        Extract system instruction from LLM request.

        Retrieves the system instruction from the request configuration
        to include in moderation context for better risk assessment.

        Args:
            llm_request (LlmRequest): The incoming LLM request object

        Returns:
            str: System instruction text, empty string if not found
        """
        config = getattr(llm_request, "config", None)
        if config:
            return getattr(config, "system_instruction", "")
        return ""

    def _build_history_from_contents(self, llm_request: LlmRequest) -> List[MessageV2]:
        """
        Build conversation history from LLM request contents.

        Constructs a structured conversation history for moderation context,
        including system instructions and recent user-assistant exchanges.
        This helps the firewall understand conversation context for better
        risk assessment.

        Args:
            llm_request (LlmRequest): The incoming LLM request containing
                conversation contents

        Returns:
            List[MessageV2]: Structured conversation history with messages
                formatted for LLM Firewall service. Limited to max_history
                recent exchanges plus system instruction if present.
        """
        history = []

        # Add system instruction as the first message if available
        system_instruction = self._get_system_instruction(llm_request)
        if system_instruction:
            history.append(
                MessageV2(
                    role="system",
                    content=system_instruction,
                    content_type=ContentTypeV2.TEXT,
                )
            )

        contents = getattr(llm_request, "contents", [])
        if not contents:
            return history

        # Add recent conversation history (excluding current user message)
        recent_contents = contents[:-1]
        if len(recent_contents) > self.max_history:
            recent_contents = recent_contents[-self.max_history :]

        for content in recent_contents:
            parts = getattr(content, "parts", [])
            if parts and hasattr(parts[0], "text"):
                role = getattr(content, "role", "")
                role = "user" if role == "user" else "assistant"
                text = getattr(parts[0], "text", "")
                if text:
                    history.append(
                        MessageV2(
                            role=role, content=text, content_type=ContentTypeV2.TEXT
                        )
                    )

        return history

    def before_model_callback(
        self, callback_context: CallbackContext, llm_request: LlmRequest, **kwargs
    ) -> Optional[LlmResponse]:
        """
        Callback executed before sending request to the model.

        This is the main entry point for content moderation. It extracts the
        user's message, builds conversation context, sends it to LLM Firewall
        for analysis, and either blocks harmful content or allows safe content
        to proceed to the model.

        The moderation process:
        1. Extracts the latest user message from request
        2. Builds conversation history for context
        3. Sends moderation request to LLM Firewall service
        4. Analyzes response for risk categories
        5. Blocks request with informative message if risks detected
        6. Allows request to proceed if content is safe

        Args:
            callback_context (CallbackContext): Callback context
            llm_request (LlmRequest): The incoming LLM request to moderate
            **kwargs: Additional keyword arguments

        Returns:
            Optional[LlmResponse]:
                - LlmResponse with blocking message if content violates policies
                - None if content is safe and request should proceed to model
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

        # Build conversation history for context
        history = self._build_history_from_contents(llm_request)

        # Create moderation request
        moderation_request = ModerateV2Request(
            scene=self.appid,
            message=MessageV2(
                role="user", content=last_user_message, content_type=ContentTypeV2.TEXT
            ),
            history=history,
        )

        try:
            # Send request to LLM Firewall service
            response = self.client.Moderate(moderation_request)
        except Exception as e:
            logger.error(f"LLM Firewall request failed: {e}")
            return None

        # Check for API errors in response
        response_metadata = getattr(response, "response_metadata", None)
        if response_metadata:
            error_info = getattr(response_metadata, "error", None)
            if error_info:
                error_code = getattr(error_info, "code", "Unknown")
                if error_code:
                    error_message = getattr(error_info, "message", "Unknown error")
                    logger.error(
                        f"LLM Firewall API error: {error_code} - {error_message}"
                    )
                    return None

        # Process risk detection results
        result = getattr(response, "result", None)
        if result:
            decision = getattr(result, "decision", None)
            decision_type = getattr(decision, "decision_type", None)
            risk_info = getattr(result, "risk_info", None)
            if int(decision_type) == 2 and risk_info:
                risks = getattr(risk_info, "risks", [])
                if risks:
                    # Extract risk categories for user-friendly error message
                    risk_reasons = set()
                    for risk in risks:
                        category = getattr(risk, "category", None)
                        if category:
                            category_name = self.category_map.get(
                                int(category), f"Category {category}"
                            )
                            risk_reasons.add(category_name)

                    risk_reasons_list = list(risk_reasons)

                    # Generate blocking response
                    reason_text = (
                        ", ".join(risk_reasons_list)
                        if risk_reasons_list
                        else "security policy violation"
                    )
                    response_text = (
                        f"Your request has been blocked due to: {reason_text}. "
                        f"Please modify your input and try again."
                    )

                    return LlmResponse(
                        content=types.Content(
                            role="model",
                            parts=[types.Part(text=response_text)],
                        )
                    )

        return None
