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

# adapted from Google ADK models adk-python/blob/main/src/google/adk/models/lite_llm.py at f1f44675e4a86b75e72cfd838efd8a0399f23e24 · google/adk-python

import uuid
from typing import Any, Dict, Optional, cast, List, Generator, Tuple, Union

import litellm
from google.adk.models import LlmResponse
from google.adk.models.lite_llm import (
    TextChunk,
    FunctionChunk,
    UsageMetadataChunk,
    _model_response_to_chunk,
    _model_response_to_generate_content_response,
)
from openai.types.responses import (
    Response as OpenAITypeResponse,
    ResponseStreamEvent,
    ResponseTextDeltaEvent,
)
from openai.types.responses import (
    ResponseCompletedEvent,
)
from litellm.completion_extras.litellm_responses_transformation.transformation import (
    LiteLLMResponsesTransformationHandler,
)
from litellm.litellm_core_utils.get_llm_provider_logic import get_llm_provider
from litellm.types.llms.openai import ResponsesAPIResponse
from litellm.types.utils import (
    ModelResponse,
    LlmProviders,
    Choices,
    Message,
)
from litellm.utils import ProviderConfigManager

from veadk.utils.logger import get_logger

# This will add functions to prompts if functions are provided.
litellm.add_function_to_prompt = True

logger = get_logger(__name__)


openai_supported_fields = [
    "stream",
    "background",
    "include",
    "input",
    "instructions",
    "max_output_tokens",
    "max_tool_calls",
    "metadata",
    "model",
    "parallel_tool_calls",
    "previous_response_id",
    "prompt",
    "prompt_cache_key",
    "reasoning",
    "safety_identifier",
    "service_tier",
    "store",
    "stream",
    "stream_options",
    "temperature",
    "text",
    "tool_choice",
    "tools",
    "top_logprobs",
    "top_p",
    "truncation",
    "user",
    "extra_headers",
    "extra_query",
    "extra_body",
    "timeout",
    # auth params
    "api_key",
    "api_base",
]


def ark_field_reorganization(request_data: dict) -> dict:
    # [Note: Ark Limitations] tools and previous_response_id
    # Remove tools in subsequent rounds (when previous_response_id is present)
    if (
        "tools" in request_data
        and "previous_response_id" in request_data
        and request_data["previous_response_id"] is not None
    ):
        # Remove tools in subsequent rounds regardless of caching status
        del request_data["tools"]

    # [Note: Ark Limitations] caching and store
    # Ensure store field is true or default when caching is enabled
    if (
        "extra_body" in request_data
        and isinstance(request_data["extra_body"], dict)
        and "caching" in request_data["extra_body"]
        and isinstance(request_data["extra_body"]["caching"], dict)
        and request_data["extra_body"]["caching"].get("type") == "enabled"
    ):
        # Set store to true when caching is enabled for writing
        if "store" not in request_data:
            request_data["store"] = True
        elif request_data["store"] is False:
            # Override false to true for cache writing
            request_data["store"] = True

    # [NOTE Ark Limitations] instructions -> input (because of caching)
    # Due to the Volcano Ark settings, there is a conflict between the cache and the instructions field.
    # If a system prompt is needed, it should be placed in the system role message within the input, instead of using the instructions parameter.
    # https://www.volcengine.com/docs/82379/1585128
    instructions = request_data.pop("instructions", None)
    if instructions:
        request_data["input"] = [
            {
                "content": [{"text": instructions, "type": "input_text"}],
                "role": "system",
                "type": "message",
            }
        ] + request_data["input"]

    return request_data


class CompletionToResponsesAPIHandler:
    def __init__(self):
        self.litellm_handler = LiteLLMResponsesTransformationHandler()

    def transform_request(
        self, model: str, messages: list, tools: Optional[list], **kwargs
    ):
        messages = messages[:1] + messages[-1:]
        # completion_request to responses api request
        # 1. model and llm_custom_provider
        model, custom_llm_provider, _, _ = get_llm_provider(model=model)

        # 2. input and instruction
        if custom_llm_provider is not None and custom_llm_provider in [
            provider.value for provider in LlmProviders
        ]:
            provider_config = ProviderConfigManager.get_provider_chat_config(
                model=model, provider=LlmProviders(custom_llm_provider)
            )
            if provider_config is not None:
                messages = provider_config.translate_developer_role_to_system_role(
                    messages=messages
                )

        input_items, instructions = (
            self.litellm_handler.convert_chat_completion_messages_to_responses_api(
                messages
            )
        )
        if tools is not None:
            tools = self.litellm_handler._convert_tools_to_responses_format(
                cast(List[Dict[str, Any]], tools)
            )

        response_args = {
            "input": input_items,
            "instructions": instructions,
            "tools": tools,
            "stream": kwargs.get("stream", False),
            "model": model,
            **kwargs,
        }
        result = {
            key: value
            for key, value in response_args.items()
            if key in openai_supported_fields
        }

        # Filter and reorganize scenarios that are not supported by some arks
        return ark_field_reorganization(result)

    def transform_response(
        self, openai_response: OpenAITypeResponse, stream: bool = False
    ) -> ModelResponse:
        # openai_type_response -> responses_api_response  ->  completion_response
        raw_response = ResponsesAPIResponse(**openai_response.model_dump())

        model_response = ModelResponse(stream=stream)
        setattr(model_response, "usage", litellm.Usage())
        response = self.litellm_handler.transform_response(
            model=raw_response.model,
            raw_response=raw_response,
            model_response=model_response,
            logging_obj=None,
            request_data={},
            messages=[],
            optional_params={},
            litellm_params={},
            encoding=None,
        )
        if raw_response and hasattr(raw_response, "id"):
            response.id = raw_response.id
        return response

    def openai_response_to_generate_content_response(
        self, raw_response: OpenAITypeResponse
    ) -> LlmResponse:
        """
        OpenAITypeResponse -> litellm.ModelResponse -> LlmResponse
        instead of `_model_response_to_generate_content_response`,
        """
        # no stream response
        model_response = self.transform_response(
            openai_response=raw_response, stream=False
        )
        llm_response = _model_response_to_generate_content_response(model_response)

        llm_response = self.adapt_responses_api(
            model_response,
            llm_response,
        )
        return llm_response

    def adapt_responses_api(
        self,
        model_response: ModelResponse,
        llm_response: LlmResponse,
        stream: bool = False,
    ):
        """
        Adapt responses api.
        """
        if not model_response.id.startswith("chatcmpl"):
            if llm_response.custom_metadata is None:
                llm_response.custom_metadata = {}
            llm_response.custom_metadata["response_id"] = model_response["id"]
        # add responses cache data
        if not stream:
            if model_response.get("usage", {}).get("prompt_tokens_details"):
                if llm_response.usage_metadata:
                    llm_response.usage_metadata.cached_content_token_count = (
                        model_response.get("usage", {})
                        .get("prompt_tokens_details")
                        .cached_tokens
                    )
        return llm_response

    def stream_event_to_chunk(
        self, event: ResponseStreamEvent, model: str
    ) -> Generator[
        Tuple[
            ModelResponse,
            Optional[Union[TextChunk, FunctionChunk, UsageMetadataChunk]],
            Optional[str],
        ],
        None,
        None,
    ]:
        """
        instead of using `_model_response_to_chunk`,
        we use our own implementation to support the responses api.
        """
        choices = []

        if isinstance(event, ResponseTextDeltaEvent):
            delta = Message(content=event.delta)
            choices.append(
                Choices(delta=delta, index=event.output_index, finish_reason=None)
            )
            model_response = ModelResponse(
                stream=True, choices=choices, model=model, id=str(uuid.uuid4())
            )
            for chunk, _ in _model_response_to_chunk(model_response):
                # delta text, not finish
                yield model_response, chunk, None
        elif isinstance(event, ResponseCompletedEvent):
            response = event.response
            model_response = self.transform_response(response, stream=True)
            model_response = fix_model_response(model_response)

            for chunk, finish_reason in _model_response_to_chunk(model_response):
                if isinstance(chunk, TextChunk):
                    yield model_response, None, finish_reason
                else:
                    yield model_response, chunk, finish_reason
        else:
            # Ignore other event types like ResponseOutputItemAddedEvent, etc.
            pass


def fix_model_response(model_response: ModelResponse) -> ModelResponse:
    """
    fix: tool_call has no attribute `index` in `_model_response_to_chunk`
    """
    for i, choice in enumerate(model_response.choices):
        if choice.message.tool_calls:
            for idx, tool_call in enumerate(choice.message.tool_calls):
                if not tool_call.get("index"):
                    model_response.choices[i].message.tool_calls[idx].index = 0

    return model_response
