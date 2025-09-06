import json
from typing import AsyncGenerator, Dict, List, Optional, Union

from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from typing_extensions import override
from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime.types.chat import (
    ChatCompletion,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCallParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
)
from volcenginesdkarkruntime.types.chat.chat_completion_content_part_param import (
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
)

from veadk.utils.misc import safe_json_serialize


def _get_content(
    parts: list[types.Part],
) -> ChatCompletionContentPartParam:
    """Converts a list of parts to ARK message content.

    Args:
      parts: The parts to convert.

    Returns:
      The ARK message content.
    """

    content_objects = []
    for part in parts:
        if part.text:
            if len(parts) == 1:
                return part.text
            content_objects.append(
                ChatCompletionContentPartTextParam(type="text", text=part.text)
            )
        # elif part.inline_data and part.inline_data.data and part.inline_data.mime_type:
        #     base64_string = base64.b64encode(part.inline_data.data).decode("utf-8")
        #     data_uri = f"data:{part.inline_data.mime_type};base64,{base64_string}"

        #     if part.inline_data.mime_type.startswith("image"):
        #         # Use full MIME type (e.g., "image/png") for providers that validate it
        #         format_type = part.inline_data.mime_type
        #         content_objects.append(
        #             ChatCompletionContentPartImageParam(
        #                 type="image_url", image_url=data_uri
        #             )
        #         )
        #     else:
        #         raise ValueError("LiteLlm(BaseLlm) does not support this content part.")

    return content_objects


def _content_to_ark_message(
    content: types.Content,
) -> Union[ChatCompletionMessageParam, list[ChatCompletionMessageParam]]:
    tool_messages = []
    for part in content.parts or []:
        if part.function_response:
            tool_messages.append(
                ChatCompletionToolMessageParam(
                    role="tool",
                    tool_call_id=part.function_response.id or "",
                    content=safe_json_serialize(part.function_response.response),
                )
            )
    if tool_messages:
        return tool_messages if len(tool_messages) > 1 else tool_messages[0]

    message_content = _get_content(content.parts or [])
    role = content.role if content.role == "user" else "assistant"

    if content.role == "user":
        return ChatCompletionUserMessageParam(role="user", content=message_content)
    else:  # assistant/model
        tool_calls = []
        content_present = False
        for part in content.parts or []:
            if part.function_call:
                function_call: ChatCompletionMessageToolCallParam = {
                    "id": part.function_call.id or "",
                    "type": "function",
                    "function": {
                        "name": part.function_call.name,
                        "arguments": safe_json_serialize(part.function_call.args),
                    },
                }
                tool_calls.append(function_call)
            elif part.text or part.inline_data:
                content_present = True

        final_content = message_content if content_present else None

        # ChatCompletionAssistantMessageParam
        return {
            "role": role,
            "content": final_content,
            "tool_calls": tool_calls or None,
        }


def _message_to_generate_content_response(
    message: ChatCompletionMessage, is_partial: bool = False
) -> LlmResponse:
    """Converts a litellm message to LlmResponse.

    Args:
      message: The message to convert.
      is_partial: Whether the message is partial.

    Returns:
      The LlmResponse.
    """

    parts = []
    if message.content:
        parts.append(types.Part.from_text(text=message.content))

    if message.tool_calls:
        for tool_call in message.tool_calls:
            if tool_call.type == "function":
                part = types.Part.from_function_call(
                    name=tool_call.function.name,
                    args=json.loads(tool_call.function.arguments or "{}"),
                )
                part.function_call.id = tool_call.id
                parts.append(part)

    return LlmResponse(
        content=types.Content(role="model", parts=parts), partial=is_partial
    )


def _model_response_to_generate_content_response(
    response: ChatCompletion,
) -> LlmResponse:
    """Converts an ARK response to LlmResponse. Also adds usage metadata.

    Args:
      response: The model response.

    Returns:
      The LlmResponse.
    """

    message = None
    if response.choices:
        message = response.choices[0].message

    if not message:
        raise ValueError("No message in response")

    llm_response = _message_to_generate_content_response(message)
    if response.usage:
        llm_response.usage_metadata = types.GenerateContentResponseUsageMetadata(
            prompt_token_count=response.usage.prompt_tokens,
            candidates_token_count=response.usage.completion_tokens,
            total_token_count=response.usage.total_tokens,
        )
    return llm_response


def _schema_to_dict(schema: types.Schema) -> dict:
    """
    Recursively converts a types.Schema to a pure-python dict
    with all enum values written as lower-case strings.

    Args:
      schema: The schema to convert.

    Returns:
      The dictionary representation of the schema.
    """
    # Dump without json encoding so we still get Enum members
    schema_dict = schema.model_dump(exclude_none=True)

    # ---- normalise this level ------------------------------------------------
    if "type" in schema_dict:
        # schema_dict["type"] can be an Enum or a str
        t = schema_dict["type"]
        schema_dict["type"] = (t.value if isinstance(t, types.Type) else t).lower()

    # ---- recurse into `items` -----------------------------------------------
    if "items" in schema_dict:
        schema_dict["items"] = _schema_to_dict(
            schema.items
            if isinstance(schema.items, types.Schema)
            else types.Schema.model_validate(schema_dict["items"])
        )

    # ---- recurse into `properties` ------------------------------------------
    if "properties" in schema_dict:
        new_props = {}
        for key, value in schema_dict["properties"].items():
            # value is a dict → rebuild a Schema object and recurse
            if isinstance(value, dict):
                new_props[key] = _schema_to_dict(types.Schema.model_validate(value))
            # value is already a Schema instance
            elif isinstance(value, types.Schema):
                new_props[key] = _schema_to_dict(value)
            # plain dict without nested schemas
            else:
                new_props[key] = value
                if "type" in new_props[key]:
                    new_props[key]["type"] = new_props[key]["type"].lower()
        schema_dict["properties"] = new_props

    return schema_dict


def _function_declaration_to_tool_param(
    function_declaration: types.FunctionDeclaration,
) -> dict:
    """Converts a types.FunctionDeclaration to a openapi spec dictionary.

    Args:
      function_declaration: The function declaration to convert.

    Returns:
      The openapi spec dictionary representation of the function declaration.
    """

    assert function_declaration.name

    properties = {}
    if function_declaration.parameters and function_declaration.parameters.properties:
        for key, value in function_declaration.parameters.properties.items():
            properties[key] = _schema_to_dict(value)

    tool_params = {
        "type": "function",
        "function": {
            "name": function_declaration.name,
            "description": function_declaration.description or "",
            "parameters": {
                "type": "object",
                "properties": properties,
            },
        },
    }

    if function_declaration.parameters.required:
        tool_params["function"]["parameters"]["required"] = (
            function_declaration.parameters.required
        )

    return tool_params


def _build_tools(
    llm_request: LlmRequest,
) -> List[Dict]:
    """Converts an LlmRequest to ARK inputs and extracts generation params.

    Args:
      llm_request: The LlmRequest to convert.

    Returns:
      The ARK inputs (message list, tool dictionary, response format and generation params).
    """
    # 2. Convert tool declarations
    tools: Optional[List[Dict]] = None
    if (
        llm_request.config
        and llm_request.config.tools
        and llm_request.config.tools[0].function_declarations
    ):
        tools = [
            _function_declaration_to_tool_param(tool)
            for tool in llm_request.config.tools[0].function_declarations
        ]

    return tools


class ArkLLM(BaseLlm):
    def __init__(self, model_name: str, api_key: str, **kwargs):
        """Initializes the ArkLLM class.

        Args:
        model_name: The name of the ArkLLM model.
        **kwargs: Additional arguments to pass to the litellm completion api.
        """
        super().__init__(model=model_name, **kwargs)

        self._ark_client = Ark(api_key=api_key)
        self._enable_responses_api = False

    # async def _generate_with_responses_api(
    #     self, llm_request: LlmRequest
    # ) -> AsyncGenerator[LlmResponse, None]:
    #     pass

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """Generates content asynchronously.

        Args:
        llm_request: LlmRequest, the request to send to the LiteLlm model.
        stream: bool = False, whether to do streaming call.

        Yields:
        LlmResponse: The model response.
        """
        messages: list[ChatCompletionMessageParam] = []
        messages.append(
            ChatCompletionSystemMessageParam(
                content=[
                    {"type": "text", "text": str(llm_request.config.system_instruction)}
                ],
                role="system",
            )
        )
        for content in llm_request.contents:
            messages.append(_content_to_ark_message(content))

        tools = _build_tools(llm_request=llm_request)

        response: ChatCompletion = self._ark_client.chat.completions.create(
            messages=messages, model=self.model, tools=tools
        )

        yield _model_response_to_generate_content_response(response)

    @classmethod
    @override
    def supported_models(cls) -> list[str]:
        """Provides the list of supported models.

        Returns:
        A list of supported models.
        """

        return []
