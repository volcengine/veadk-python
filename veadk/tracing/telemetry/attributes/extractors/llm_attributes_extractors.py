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

from google.adk.agents.run_config import StreamingMode
from veadk.tracing.telemetry.attributes.extractors.types import (
    ExtractorResponse,
    LLMAttributesParams,
)
from veadk.utils.misc import safe_json_serialize


def llm_gen_ai_request_model(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the requested language model name.

    Provides the model identifier that was specified in the LLM request
    for tracking model usage patterns and performance analysis.

    Args:
        params: LLM execution parameters containing request details

    Returns:
        ExtractorResponse: Response containing the model name or placeholder
    """
    return ExtractorResponse(content=params.llm_request.model or "<unknown_model_name>")


def llm_gen_ai_request_type(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the LLM request type.

    Provides the type of LLM operation being performed, typically "chat"
    for conversational interactions with language models.

    Args:
        params: LLM execution parameters (unused in this extractor)

    Returns:
        ExtractorResponse: Response containing "chat" as the request type
    """
    return ExtractorResponse(content="chat" or "<unknown_type>")


def llm_gen_ai_response_model(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the responding language model name.

    Provides the actual model that generated the response, which should
    match the requested model for verification and tracking purposes.

    Args:
        params: LLM execution parameters containing request details

    Returns:
        ExtractorResponse: Response containing the response model name or placeholder
    """
    return ExtractorResponse(content=params.llm_request.model or "<unknown_model_name>")


def llm_gen_ai_request_max_tokens(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the maximum output tokens configuration.

    Provides the maximum number of tokens the model is allowed to generate
    in its response, used for cost prediction and output length control.

    Args:
        params: LLM execution parameters containing request configuration

    Returns:
        ExtractorResponse: Response containing max output tokens value
    """
    return ExtractorResponse(content=params.llm_request.config.max_output_tokens)


def llm_gen_ai_request_temperature(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the temperature parameter for response randomness.

    Provides the temperature setting that controls randomness in model
    responses, affecting creativity and consistency of outputs.

    Args:
        params: LLM execution parameters containing request configuration

    Returns:
        ExtractorResponse: Response containing temperature value
    """
    return ExtractorResponse(content=params.llm_request.config.temperature)


def llm_gen_ai_request_top_p(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the top-p parameter for nucleus sampling.

    Provides the top-p (nucleus sampling) setting that controls the
    diversity of token sampling in model responses.

    Args:
        params: LLM execution parameters containing request configuration

    Returns:
        ExtractorResponse: Response containing top-p value
    """
    return ExtractorResponse(content=params.llm_request.config.top_p)


def llm_gen_ai_response_stop_reason(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the stop reason for response completion.

    Provides information about why the model stopped generating tokens,
    which helps identify truncation or completion patterns.

    Args:
        params: LLM execution parameters (currently not implemented)

    Returns:
        ExtractorResponse: Response containing placeholder stop reason
    """
    return ExtractorResponse(content="<no_stop_reason_provided>")


def llm_gen_ai_response_finish_reason(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the finish reason for response completion.

    Provides information about how the model completed its response,
    such as natural completion, token limit, or stop sequence.

    Args:
        params: LLM execution parameters (currently not implemented)

    Returns:
        ExtractorResponse: Response containing placeholder finish reason

    Note:
        - Currently returns placeholder value
        - TODO: Update implementation for Google ADK v1.12.0
        - Critical for understanding response quality and completeness
    """
    # TODO: update to google-adk v1.12.0
    return ExtractorResponse(content="<no_finish_reason_provided>")


def llm_gen_ai_usage_input_tokens(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the number of input tokens consumed.

    Provides the count of tokens in the prompt and context that were
    processed by the model, essential for cost tracking and analysis.

    Args:
        params: LLM execution parameters containing response metadata

    Returns:
        ExtractorResponse: Response containing input token count or None
    """
    if params.llm_response.usage_metadata:
        return ExtractorResponse(
            content=params.llm_response.usage_metadata.prompt_token_count
        )
    return ExtractorResponse(content=None)


def llm_gen_ai_usage_output_tokens(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the number of output tokens generated.

    Provides the count of tokens generated by the model in its response,
    essential for cost tracking and response length analysis.

    Args:
        params: LLM execution parameters containing response metadata

    Returns:
        ExtractorResponse: Response containing output token count or None
    """
    if params.llm_response.usage_metadata:
        return ExtractorResponse(
            content=params.llm_response.usage_metadata.candidates_token_count,
        )
    return ExtractorResponse(content=None)


def llm_gen_ai_usage_total_tokens(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the total number of tokens consumed.

    Provides the total count of tokens (input + output) consumed by
    the model interaction, used for overall cost tracking.

    Args:
        params: LLM execution parameters containing response metadata

    Returns:
        ExtractorResponse: Response containing total token count or None
    """
    if params.llm_response.usage_metadata:
        return ExtractorResponse(
            content=params.llm_response.usage_metadata.total_token_count,
        )
    return ExtractorResponse(content=None)


# FIXME
def llm_gen_ai_usage_cache_creation_input_tokens(
    params: LLMAttributesParams,
) -> ExtractorResponse:
    """Extract the number of tokens used for cache creation.

    Provides the count of tokens used for creating cached content,
    which affects cost calculation in caching-enabled models.

    Args:
        params: LLM execution parameters containing response metadata

    Returns:
        ExtractorResponse: Response containing cache creation token count or None
    """
    if params.llm_response.usage_metadata:
        return ExtractorResponse(
            content=params.llm_response.usage_metadata.cached_content_token_count,
        )
    return ExtractorResponse(content=None)


# FIXME
def llm_gen_ai_usage_cache_read_input_tokens(
    params: LLMAttributesParams,
) -> ExtractorResponse:
    """Extract the number of tokens used for cache reading.

    Provides the count of tokens read from cached content,
    which affects cost calculation in caching-enabled models.

    Args:
        params: LLM execution parameters containing response metadata

    Returns:
        ExtractorResponse: Response containing cache read token count or None
    """
    if params.llm_response.usage_metadata:
        return ExtractorResponse(
            content=params.llm_response.usage_metadata.cached_content_token_count,
        )
    return ExtractorResponse(content=None)


def llm_gen_ai_prompt(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract structured prompt data for span attributes.

    Processes the complete conversation history from the LLM request
    and structures it into indexed prompt messages with role, content,
    and metadata information for analysis and debugging.

    Args:
        params: LLM execution parameters containing request content

    Returns:
        ExtractorResponse: Response containing list of structured prompt messages
    """
    # a part is a message
    messages: list[dict] = []
    idx = 0

    for content in params.llm_request.contents:
        if content.parts:
            for part in content.parts:
                message = {}
                # text part
                if part.text:
                    message[f"gen_ai.prompt.{idx}.role"] = content.role
                    message[f"gen_ai.prompt.{idx}.content"] = part.text
                # function response
                if part.function_response:
                    message[f"gen_ai.prompt.{idx}.role"] = content.role
                    message[f"gen_ai.prompt.{idx}.content"] = (
                        str(part.function_response.response)
                        if part.function_response
                        else "<unknown_function_response>"
                    )
                # function call
                if part.function_call:
                    message[f"gen_ai.prompt.{idx}.tool_calls.0.id"] = (
                        part.function_call.id
                        if part.function_call.id
                        else "<unkown_function_call_id>"
                    )
                    message[f"gen_ai.prompt.{idx}.tool_calls.0.type"] = "function"
                    message[f"gen_ai.prompt.{idx}.tool_calls.0.function.name"] = (
                        part.function_call.name
                        if part.function_call.name
                        else "<unknown_function_name>"
                    )
                    message[f"gen_ai.prompt.{idx}.tool_calls.0.function.arguments"] = (
                        safe_json_serialize(part.function_call.args)
                        if part.function_call.args
                        else json.dumps({})
                    )
                # image
                if part.inline_data:
                    message[f"gen_ai.prompt.{idx}.type"] = "image_url"
                    message[f"gen_ai.prompt.{idx}.image_url.name"] = (
                        part.inline_data.display_name.split("/")[-1]
                        if part.inline_data.display_name
                        else "<unknown_image_name>"
                    )
                    message[f"gen_ai.prompt.{idx}.image_url.url"] = (
                        part.inline_data.display_name
                    )

                if message:
                    messages.append(message)
                    idx += 1

    return ExtractorResponse(content=messages)


def llm_gen_ai_completion(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract structured completion data for span attributes.

    Processes the model's response content and structures it into
    indexed completion messages with role, content, and tool call
    information for analysis and evaluation.

    Args:
        params: LLM execution parameters containing response content

    Returns:
        ExtractorResponse: Response containing list of structured completion messages
    """
    messages = []

    content = params.llm_response.content
    if content and content.parts:
        for idx, part in enumerate(content.parts):
            message = {}
            if part.text:
                message[f"gen_ai.completion.{idx}.role"] = content.role
                message[f"gen_ai.completion.{idx}.content"] = part.text
            elif part.function_call:
                message[f"gen_ai.completion.{idx}.role"] = content.role
                message[f"gen_ai.completion.{idx}.tool_calls.0.id"] = (
                    part.function_call.id
                    if part.function_call.id
                    else "<unkown_function_call_id>"
                )
                message[f"gen_ai.completion.{idx}.tool_calls.0.type"] = "function"
                message[f"gen_ai.completion.{idx}.tool_calls.0.function.name"] = (
                    part.function_call.name
                    if part.function_call.name
                    else "<unknown_function_name>"
                )
                message[f"gen_ai.completion.{idx}.tool_calls.0.function.arguments"] = (
                    safe_json_serialize(part.function_call.args)
                    if part.function_call.args
                    else json.dumps({})
                )

            if message:
                messages.append(message)
    return ExtractorResponse(content=messages)


def llm_gen_ai_messages(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract complete conversation messages as structured events.

    Processes the entire conversation context including system instructions,
    user messages, tool messages, and assistant responses into structured
    events for comprehensive conversation flow analysis.

    Args:
        params: LLM execution parameters containing request content

    Returns:
        ExtractorResponse: Event list response containing structured conversation events
    """
    events = []

    # system message
    events.append(
        {
            "gen_ai.system.message": {
                "role": "system",
                "content": str(params.llm_request.config.system_instruction),
            }
        }
    )

    # user, tool, and assistant message
    if params.llm_request and params.llm_request.contents:
        for content in params.llm_request.contents:
            if content and content.parts:
                # content.role == "user"
                #   part.function_response -> gen_ai.tool.message
                #   not part.function_response -> gen_ai.user.message
                # content.role == "model" -> gen_ai.assistant.message
                if content.role == "user":
                    user_event = {}
                    user_event["gen_ai.user.message"] = {"role": content.role}
                    for idx, part in enumerate(content.parts):
                        if part.function_response:
                            events.append(
                                {
                                    "gen_ai.tool.message": {
                                        "role": "tool",
                                        "id": part.function_response.id,
                                        "content": safe_json_serialize(
                                            part.function_response.response
                                        ),
                                    }
                                }
                            )
                        else:
                            if part.text:
                                if len(content.parts) == 1:
                                    user_event["gen_ai.user.message"].update(
                                        {"content": part.text}
                                    )
                                else:
                                    user_event["gen_ai.user.message"].update(
                                        {
                                            f"parts.{idx}.type": "text",
                                            f"parts.{idx}.text": part.text,
                                        },
                                    )
                            if part.inline_data:
                                if len(content.parts) == 1:
                                    part = content.parts[0]
                                    user_event["gen_ai.user.message"].update(
                                        {
                                            "parts.0.type": "image_url",
                                            "parts.0.image_url.name": (
                                                part.inline_data.display_name.split(
                                                    "/"
                                                )[-1]
                                                if part.inline_data
                                                and part.inline_data.display_name
                                                else "<unknown_image_name>"
                                            ),
                                            "parts.0.image_url.url": (
                                                part.inline_data.display_name
                                                if part.inline_data
                                                and part.inline_data.display_name
                                                else "<unknown_image_url>"
                                            ),
                                        }
                                    )
                                else:
                                    user_event["gen_ai.user.message"].update(
                                        {
                                            f"parts.{idx}.type": "image_url",
                                            f"parts.{idx}.image_url.name": (
                                                part.inline_data.display_name.split(
                                                    "/"
                                                )[-1]
                                                if part.inline_data.display_name
                                                else "<unknown_image_name>"
                                            ),
                                            f"parts.{idx}.image_url.url": (
                                                part.inline_data.display_name
                                                if part.inline_data.display_name
                                                else "<unknown_image_url>"
                                            ),
                                        }
                                    )
                    # in case of only function response
                    if len(user_event["gen_ai.user.message"].items()) > 1:
                        events.append(user_event)
                elif content.role == "model":
                    event = {}
                    event["gen_ai.assistant.message"] = {"role": content.role}
                    for idx, part in enumerate(content.parts):
                        if part.text:
                            event["gen_ai.assistant.message"].update(
                                {
                                    f"parts.{idx}.type": "text",
                                    f"parts.{idx}.text": part.text,
                                }
                            )
                        if part.function_call:
                            event["gen_ai.assistant.message"].update(
                                {
                                    "tool_calls.0.id": str(part.function_call.id),
                                    "tool_calls.0.type": "function",
                                    "tool_calls.0.function.name": part.function_call.name
                                    if part.function_call.name
                                    else "<unknown_function_name>",
                                    "tool_calls.0.function.arguments": safe_json_serialize(
                                        part.function_call.args
                                    )
                                    if part.function_call.args
                                    else json.dumps({}),
                                }
                            )
                    events.append(event)

    return ExtractorResponse(type="event_list", content=events)


def llm_gen_ai_is_streaming(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract streaming mode indicator.

    Indicates whether the LLM request was processed in streaming mode
    for performance analysis and debugging purposes.

    Args:
        params: LLM execution parameters

    Returns:
        ExtractorResponse: Response containing None
    """
    is_streaming = bool(
        params.invocation_context.run_config and params.invocation_context.run_config.streaming_mode != StreamingMode.NONE)

    return ExtractorResponse(content=is_streaming)


def llm_gen_ai_operation_name(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the operation name for LLM spans.

    Provides a standardized operation name for LLM interactions,
    enabling consistent categorization across all model calls.

    Args:
        params: LLM execution parameters (unused in this extractor)

    Returns:
        ExtractorResponse: Response containing "chat" as the operation name
    """
    return ExtractorResponse(content="chat")


def llm_gen_ai_span_kind(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the span kind for LLM spans.

    Provides span kind classification following OpenTelemetry semantic
    conventions for generative AI LLM operations.

    Returns:
        ExtractorResponse: Response containing "llm" as the span kind
    """
    return ExtractorResponse(content="llm")


# def llm_gen_ai_system_message(params: LLMAttributesParams) -> ExtractorResponse:
#     event_attributes = {
#         "content": str(params.llm_request.config.system_instruction),
#         "role": "system",
#     }
#     return ExtractorResponse(type="event", content=event_attributes)


# def llm_gen_ai_user_message(params: LLMAttributesParams) -> ExtractorResponse:
#     # a content is a message
#     messages = []

#     for content in params.llm_request.contents:
#         if content.role == "user":
#             message_parts = []

#             if content.parts:
#                 if len(content.parts) == 1:
#                     if content.parts[0].text:
#                         message_parts.append(
#                             {
#                                 "role": content.role,
#                                 "content": content.parts[0].text,
#                             }
#                         )
#                     elif content.parts[0].function_response:
#                         message_parts.append(
#                             {
#                                 "role": content.role,
#                                 "content": str(
#                                     content.parts[0].function_response.response
#                                 ),
#                             }
#                         )
#                 else:
#                     message_part = {"role": content.role}
#                     for idx, part in enumerate(content.parts):
#                         # text part
#                         if part.text:
#                             message_part[f"parts.{idx}.type"] = "text"
#                             message_part[f"parts.{idx}.content"] = part.text
#                         # function response
#                         if part.function_response:
#                             message_part[f"parts.{idx}.type"] = "function"
#                             message_part[f"parts.{idx}.content"] = str(
#                                 part.function_response
#                             )
#                         if part.inline_data:
#                             message_part[f"parts.{idx}.type"] = "image_url"
#                             message_part[f"parts.{idx}.image_url.name"] = (
#                                 part.inline_data.display_name.split("/")[-1]
#                             )
#                             message_part[f"parts.{idx}.image_url.url"] = (
#                                 part.inline_data.display_name
#                             )

#                     message_parts.append(message_part)

#             if message_parts:
#                 messages.extend(message_parts)

#     return ExtractorResponse(type="event", content=messages)


# def llm_gen_ai_assistant_message(params: LLMAttributesParams) -> ExtractorResponse:
#     # a content is a message
#     messages = []

#     # each part in each content we make it a message
#     # e.g. 2 contents and 3 parts each means 6 messages
#     for content in params.llm_request.contents:
#         if content.role == "model":
#             message_parts = []

#             # each part we make it a message
#             if content.parts:
#                 # only one part
#                 if len(content.parts) == 1:
#                     if content.parts[0].text:
#                         message_parts.append(
#                             {
#                                 "role": content.role,
#                                 "content": content.parts[0].text,
#                             }
#                         )
#                     elif content.parts[0].function_call:
#                         pass
#                 # multiple parts
#                 else:
#                     message_part = {"role": content.role}

#                     for idx, part in enumerate(content.parts):
#                         # parse content
#                         if part.text:
#                             message_part[f"parts.{idx}.type"] = "text"
#                             message_part[f"parts.{idx}.content"] = part.text
#                         # parse tool_calls
#                         if part.function_call:
#                             message_part["tool_calls.0.id"] = (
#                                 part.function_call.id
#                                 if part.function_call.id
#                                 else "<unkown_function_call_id>"
#                             )
#                             message_part["tool_calls.0.type"] = "function"
#                             message_part["tool_calls.0.function.name"] = (
#                                 part.function_call.name
#                                 if part.function_call.name
#                                 else "<unknown_function_name>"
#                             )
#                             message_part["tool_calls.0.function.arguments"] = (
#                                 safe_json_serialize(part.function_call.args)
#                                 if part.function_call.args
#                                 else json.dumps({})
#                             )
#                     message_parts.append(message_part)

#             if message_parts:
#                 messages.extend(message_parts)

#     return ExtractorResponse(type="event", content=messages)


def llm_gen_ai_choice(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract model choice data as span events.

    Processes the model's response content and creates choice events
    containing response metadata, content, and tool calls for
    detailed response analysis.

    Args:
        params: LLM execution parameters containing response content

    Returns:
        ExtractorResponse: Event response containing structured choice data
    """
    message = {}

    # parse content to build a message
    content = params.llm_response.content
    if content and content.parts:
        message = {"message.role": content.role}

        if len(content.parts) == 1:
            part = content.parts[0]
            if part.text:
                message["message.content"] = part.text
            elif part.function_call:
                message["message.tool_calls.0.id"] = (
                    part.function_call.id
                    if part.function_call.id
                    else "<unkown_function_call_id>"
                )
                message["message.tool_calls.0.type"] = "function"
                message["message.tool_calls.0.function.name"] = (
                    part.function_call.name
                    if part.function_call.name
                    else "<unknown_function_name>"
                )
                message["message.tool_calls.0.function.arguments"] = (
                    safe_json_serialize(part.function_call.args)
                    if part.function_call.args
                    else json.dumps({})
                )
        else:
            for idx, part in enumerate(content.parts):
                # parse content
                if part.text:
                    message[f"message.parts.{idx}.type"] = "text"
                    message[f"message.parts.{idx}.text"] = part.text

                # parse tool_calls
                if part.function_call:
                    message["message.tool_calls.0.id"] = (
                        part.function_call.id
                        if part.function_call.id
                        else "<unkown_function_call_id>"
                    )
                    message["message.tool_calls.0.type"] = "function"
                    message["message.tool_calls.0.function.name"] = (
                        part.function_call.name
                        if part.function_call.name
                        else "<unknown_function_name>"
                    )
                    message["message.tool_calls.0.function.arguments"] = (
                        safe_json_serialize(part.function_call.args)
                        if part.function_call.args
                        else json.dumps({})
                    )

    return ExtractorResponse(type="event", content=message)


def llm_input_value(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract complete LLM request data for debugging.

    Provides the complete LLM request object in string format
    for detailed debugging and analysis purposes.

    Args:
        params: LLM execution parameters containing request details

    Returns:
        ExtractorResponse: Response containing serialized request data
    """
    return ExtractorResponse(
        content=str(params.llm_request.model_dump(exclude_none=True))
    )


def llm_output_value(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract complete LLM response data for debugging.

    Provides the complete LLM response object in string format
    for detailed debugging and analysis purposes.

    Args:
        params: LLM execution parameters containing response details

    Returns:
        ExtractorResponse: Response containing serialized response data
    """
    return ExtractorResponse(
        content=str(params.llm_response.model_dump(exclude_none=True))
    )


def llm_gen_ai_request_functions(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract available functions/tools from the LLM request.

    Processes the tools dictionary from the LLM request and extracts
    function metadata including names, descriptions, and parameters
    for tool usage analysis and debugging.

    Args:
        params: LLM execution parameters containing request tools

    Returns:
        ExtractorResponse: Response containing list of function metadata
    """
    functions = []

    for idx, (tool_name, tool_instance) in enumerate(
        params.llm_request.tools_dict.items()
    ):
        functions.append(
            {
                f"gen_ai.request.functions.{idx}.name": tool_instance.name,
                f"gen_ai.request.functions.{idx}.description": tool_instance.description,
                f"gen_ai.request.functions.{idx}.parameters": str(
                    tool_instance._get_declaration().parameters.model_dump_json(  # type: ignore
                        exclude_none=True
                    )
                    if tool_instance._get_declaration()
                    and tool_instance._get_declaration().parameters  # type: ignore
                    else {}
                ),
            }
        )

    return ExtractorResponse(content=functions)

def llm_server_address(params: LLMAttributesParams) -> ExtractorResponse:
    """Extract the LLM server address (model API base URL).

    Returns the model API base URL configured on the current Agent.
    If the Agent or base URL is unavailable, returns 'unknown' to
    keep the span attribute consistent.

    Args:
        params: LLM execution parameters containing invocation context

    Returns:
        ExtractorResponse: Response containing the server address or 'unknown'
    """
    return ExtractorResponse(content=getattr(params.invocation_context.agent, "model_api_base", None) or "unknown")


LLM_ATTRIBUTES = {
    # -> 1. attributes
    # -> 1.1. request
    "gen_ai.request.model": llm_gen_ai_request_model,
    "gen_ai.request.type": llm_gen_ai_request_type,
    "gen_ai.request.max_tokens": llm_gen_ai_request_max_tokens,
    "gen_ai.request.temperature": llm_gen_ai_request_temperature,
    "gen_ai.request.top_p": llm_gen_ai_request_top_p,
    "server.address": llm_server_address,
    # CozeLoop required
    "gen_ai.request.functions": llm_gen_ai_request_functions,
    # -> 1.2. response
    "gen_ai.response.model": llm_gen_ai_response_model,
    "gen_ai.response.stop_reason": llm_gen_ai_response_stop_reason,
    "gen_ai.response.finish_reason": llm_gen_ai_response_finish_reason,
    # -> 1.3. streaming
    "gen_ai.is_streaming": llm_gen_ai_is_streaming,
    # -> 1.4. span kind
    "gen_ai.operation.name": llm_gen_ai_operation_name,
    "gen_ai.span.kind": llm_gen_ai_span_kind,  # apmplus required
    # -> 1.5. inputs
    "gen_ai.prompt": llm_gen_ai_prompt,
    # -> 1.6. outputs
    "gen_ai.completion": llm_gen_ai_completion,
    # -> 1.7. usage
    "gen_ai.usage.input_tokens": llm_gen_ai_usage_input_tokens,
    "gen_ai.usage.output_tokens": llm_gen_ai_usage_output_tokens,
    "gen_ai.usage.total_tokens": llm_gen_ai_usage_total_tokens,
    "gen_ai.usage.cache_creation_input_tokens": llm_gen_ai_usage_cache_creation_input_tokens,
    "gen_ai.usage.cache_read_input_tokens": llm_gen_ai_usage_cache_read_input_tokens,
    # -> 2. events
    # -> 2.1. inputs
    # In order to adapt OpenTelemetry and CozeLoop rendering,
    # and avoid error sequence of tool-call and too-response,
    # we use `llm_gen_ai_messages` to upload system message, user message,
    # and assistant message together.
    # Correct sequence: system message, user message, tool message,
    # and assistant message.
    "gen_ai.messages": llm_gen_ai_messages,
    # [depracated]
    # "gen_ai.system.message": llm_gen_ai_system_message,
    # [depracated]
    # "gen_ai.user.message": llm_gen_ai_user_message,
    # [depracated]
    # "gen_ai.assistant.message": llm_gen_ai_assistant_message,
    # -> 2.2. outputs
    "gen_ai.choice": llm_gen_ai_choice,
    # [debugging]
    # "input.value": llm_input_value,
    # [debugging]
    # "output.value": llm_output_value,
}
