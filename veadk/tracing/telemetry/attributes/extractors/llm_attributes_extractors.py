import json


from veadk.tracing.telemetry.attributes.extractors.types import (
    ExtractorResponse,
    LLMAttributesParams,
)


def flatten(d, parent_key="", sep="."):
    items = []
    if isinstance(d, dict):
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            items.extend(flatten(v, new_key, sep=sep).items())
    elif isinstance(d, list):
        if not d:  # empty list
            items.append((parent_key, ""))
        else:
            for i, v in enumerate(d):
                new_key = f"{parent_key}{sep}{i}" if parent_key else str(i)
                items.extend(flatten(v, new_key, sep=sep).items())
    else:
        items.append((parent_key, d))
    return dict(items)


def llm_gen_ai_request_model(params: LLMAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content=params.llm_request.model or "<unknown_model_name>")


def llm_gen_ai_request_type(params: LLMAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content=type or "<unknown_type>")


def llm_gen_ai_response_model(params: LLMAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content=params.llm_request.model or "<unknown_model_name>")


def llm_gen_ai_request_max_tokens(params: LLMAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content=params.llm_request.config.max_output_tokens)


def llm_gen_ai_request_temperature(params: LLMAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content=params.llm_request.config.temperature)


def llm_gen_ai_request_top_p(params: LLMAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content=params.llm_request.config.top_p)


def llm_gen_ai_response_stop_reason(params: LLMAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content="<no_stop_reason_provided>")


def llm_gen_ai_response_finish_reason(params: LLMAttributesParams) -> ExtractorResponse:
    # TODO: update to google-adk v1.12.0
    return ExtractorResponse(content="<no_finish_reason_provided>")


def llm_gen_ai_usage_input_tokens(params: LLMAttributesParams) -> ExtractorResponse:
    if params.llm_response.usage_metadata:
        return ExtractorResponse(
            content=params.llm_response.usage_metadata.prompt_token_count
        )
    return ExtractorResponse(content=None)


def llm_gen_ai_usage_output_tokens(params: LLMAttributesParams) -> ExtractorResponse:
    if params.llm_response.usage_metadata:
        return ExtractorResponse(
            content=params.llm_response.usage_metadata.candidates_token_count,
        )
    return ExtractorResponse(content=None)


def llm_gen_ai_usage_total_tokens(params: LLMAttributesParams) -> ExtractorResponse:
    if params.llm_response.usage_metadata:
        return ExtractorResponse(
            content=params.llm_response.usage_metadata.total_token_count,
        )
    return ExtractorResponse(content=None)


# FIXME
def llm_gen_ai_usage_cache_creation_input_tokens(
    params: LLMAttributesParams,
) -> ExtractorResponse:
    if params.llm_response.usage_metadata:
        return ExtractorResponse(
            content=params.llm_response.usage_metadata.cached_content_token_count,
        )
    return ExtractorResponse(content=None)


# FIXME
def llm_gen_ai_usage_cache_read_input_tokens(
    params: LLMAttributesParams,
) -> ExtractorResponse:
    if params.llm_response.usage_metadata:
        return ExtractorResponse(
            content=params.llm_response.usage_metadata.cached_content_token_count,
        )
    return ExtractorResponse(content=None)


def llm_gen_ai_prompt(params: LLMAttributesParams) -> ExtractorResponse:
    # a content is a message
    messages: list[dict] = []

    for content in params.llm_request.contents:
        if content.parts:
            for idx, part in enumerate(content.parts):
                message = {}
                # text part
                if part.text:
                    message[f"gen_ai.prompt.{idx}.role"] = content.role
                    message[f"gen_ai.prompt.{idx}.content"] = part.text
                # function response
                if part.function_response:
                    message[f"gen_ai.prompt.{idx}.role"] = content.role
                    message[f"gen_ai.prompt.{idx}.content"] = str(
                        content.parts[0].function_response
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
                        json.dumps(part.function_call.args)
                        if part.function_call.args
                        else json.dumps({})
                    )

                if message:
                    messages.append(message)

    return ExtractorResponse(content=messages)


def llm_gen_ai_completion(params: LLMAttributesParams) -> ExtractorResponse:
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
                    json.dumps(part.function_call.args)
                    if part.function_call.args
                    else json.dumps({})
                )

            if message:
                messages.append(message)
    return ExtractorResponse(content=messages)


def llm_gen_ai_is_streaming(params: LLMAttributesParams) -> ExtractorResponse:
    # return params.llm_request.stream
    return ExtractorResponse(content=None)


def llm_gen_ai_operation_name(params: LLMAttributesParams) -> ExtractorResponse:
    return ExtractorResponse(content="chat")


def llm_gen_ai_system_message(params: LLMAttributesParams) -> ExtractorResponse:
    event_attributes = {
        "content": str(params.llm_request.config.system_instruction),
        "role": "system",
    }
    return ExtractorResponse(type="event", content=event_attributes)


def llm_gen_ai_user_message(params: LLMAttributesParams) -> ExtractorResponse:
    # a content is a message
    messages = []

    for content in params.llm_request.contents:
        if content.role == "user":
            message_parts = []

            if content.parts:
                if len(content.parts) == 1:
                    if content.parts[0].text:
                        message_parts.append(
                            {
                                "role": content.role,
                                "content": content.parts[0].text,
                            }
                        )
                    elif content.parts[0].function_response:
                        message_parts.append(
                            {
                                "role": content.role,
                                "content": str(
                                    content.parts[0].function_response.response
                                ),
                            }
                        )
                else:
                    message_part = {"role": content.role}
                    for idx, part in enumerate(content.parts):
                        # text part
                        if part.text:
                            message_part[f"parts.{idx}.type"] = "text"
                            message_part[f"parts.{idx}.content"] = part.text
                        # function response
                        if part.function_response:
                            message_part[f"parts.{idx}.type"] = "function"
                            message_part[f"parts.{idx}.content"] = str(
                                content.parts[0].function_response
                            )

                    message_parts.append(message_part)

            if message_parts:
                messages.extend(message_parts)

    return ExtractorResponse(type="event", content=messages)


def llm_gen_ai_assistant_message(params: LLMAttributesParams) -> ExtractorResponse:
    # a content is a message
    messages = []

    # each part in each content we make it a message
    # e.g. 2 contents and 3 parts each means 6 messages
    for content in params.llm_request.contents:
        if content.role == "model":
            message_parts = []

            # each part we make it a message
            if content.parts:
                # only one part
                if len(content.parts) == 1:
                    if content.parts[0].text:
                        message_parts.append(
                            {
                                "role": content.role,
                                "content": content.parts[0].text,
                            }
                        )
                    elif content.parts[0].function_call:
                        pass
                # multiple parts
                else:
                    message_part = {"role": content.role}

                    for idx, part in enumerate(content.parts):
                        # parse content
                        if part.text:
                            message_part[f"parts.{idx}.type"] = "text"
                            message_part[f"parts.{idx}.content"] = part.text
                        # parse tool_calls
                        if part.function_call:
                            message_part["tool_calls.0.id"] = (
                                part.function_call.id
                                if part.function_call.id
                                else "<unkown_function_call_id>"
                            )
                            message_part["tool_calls.0.type"] = "function"
                            message_part["tool_calls.0.function.name"] = (
                                part.function_call.name
                                if part.function_call.name
                                else "<unknown_function_name>"
                            )
                            message_part["tool_calls.0.function.arguments"] = (
                                json.dumps(part.function_call.args)
                                if part.function_call.args
                                else json.dumps({})
                            )
                    message_parts.append(message_part)

            if message_parts:
                messages.extend(message_parts)

    return ExtractorResponse(type="event", content=messages)


def llm_gen_ai_choice(params: LLMAttributesParams) -> ExtractorResponse:
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
                    json.dumps(part.function_call.args)
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
                        json.dumps(part.function_call.args)
                        if part.function_call.args
                        else json.dumps({})
                    )

    return ExtractorResponse(type="event", content=message)


LLM_ATTRIBUTES = {
    "gen_ai.request.model": llm_gen_ai_request_model,
    "gen_ai.request.type": llm_gen_ai_request_type,
    "gen_ai.response.model": llm_gen_ai_response_model,
    "gen_ai.request.max_tokens": llm_gen_ai_request_max_tokens,
    "gen_ai.request.temperature": llm_gen_ai_request_temperature,
    "gen_ai.request.top_p": llm_gen_ai_request_top_p,
    "gen_ai.prompt": llm_gen_ai_prompt,
    "gen_ai.completion": llm_gen_ai_completion,
    "gen_ai.response.stop_reason": llm_gen_ai_response_stop_reason,
    "gen_ai.response.finish_reason": llm_gen_ai_response_finish_reason,
    "gen_ai.usage.input_tokens": llm_gen_ai_usage_input_tokens,
    "gen_ai.usage.output_tokens": llm_gen_ai_usage_output_tokens,
    "gen_ai.usage.total_tokens": llm_gen_ai_usage_total_tokens,
    "gen_ai.usage.cache_creation_input_tokens": llm_gen_ai_usage_cache_creation_input_tokens,
    "gen_ai.usage.cache_read_input_tokens": llm_gen_ai_usage_cache_read_input_tokens,
    "gen_ai.is_streaming": llm_gen_ai_is_streaming,
    "gen_ai.operation.name": llm_gen_ai_operation_name,
    "gen_ai.system.message": llm_gen_ai_system_message,
    "gen_ai.user.message": llm_gen_ai_user_message,
    "gen_ai.assistant.message": llm_gen_ai_assistant_message,
    "gen_ai.choice": llm_gen_ai_choice,
}
