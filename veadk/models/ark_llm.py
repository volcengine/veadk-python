import json
import uuid
from datetime import datetime
from typing import Any, Dict, Union, AsyncGenerator

import litellm
from openai import OpenAI
from google.adk.models import LlmRequest, LlmResponse
from google.adk.models.lite_llm import (
    LiteLlm,
    LiteLLMClient,
    _get_completion_inputs,
    _model_response_to_chunk,
    FunctionChunk,
    TextChunk,
    _message_to_generate_content_response,
    UsageMetadataChunk,
    _model_response_to_generate_content_response,
)
from google.genai import types
from litellm import Logging, ChatCompletionAssistantMessage
from litellm.completion_extras.litellm_responses_transformation.transformation import (
    LiteLLMResponsesTransformationHandler,
)
from litellm.litellm_core_utils.get_litellm_params import get_litellm_params
from litellm.litellm_core_utils.get_llm_provider_logic import get_llm_provider
from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper
from litellm.types.llms.openai import ResponsesAPIResponse
from litellm.types.utils import (
    ModelResponse,
    LlmProviders,
    ChatCompletionMessageToolCall,
    Function,
)
from litellm.utils import get_optional_params, ProviderConfigManager
from pydantic import Field

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
]


def _add_response_id_to_llm_response(
    llm_response: LlmResponse, response: ModelResponse
) -> LlmResponse:
    if not response.id.startswith("chatcmpl"):
        if llm_response.custom_metadata is None:
            llm_response.custom_metadata = {}
        llm_response.custom_metadata["response_id"] = response["id"]
    return llm_response


async def openai_response_async(request_data: dict):
    # Filter out fields that are not supported by OpenAI SDK
    filtered_request_data = {
        key: value
        for key, value in request_data.items()
        if key in openai_supported_fields and value is not None
    }
    model_name, custom_llm_provider, _, _ = get_llm_provider(
        model=request_data["model"]
    )
    filtered_request_data["model"] = model_name  # remove custom_llm_provider

    if (
        "tools" in filtered_request_data
        and "extra_body" in filtered_request_data
        and isinstance(filtered_request_data["extra_body"], dict)
        and "caching" in filtered_request_data["extra_body"]
        and isinstance(filtered_request_data["extra_body"]["caching"], dict)
        and filtered_request_data["extra_body"]["caching"].get("type") == "enabled"
        and "previous_response_id" in filtered_request_data
        and filtered_request_data["previous_response_id"] is not None
    ):
        # Remove tools when caching is enabled and previous_response_id is present
        del filtered_request_data["tools"]

    # Remove instructions when caching is enabled with specific configuration
    if (
        "instructions" in filtered_request_data
        and "extra_body" in filtered_request_data
        and isinstance(filtered_request_data["extra_body"], dict)
        and "caching" in filtered_request_data["extra_body"]
        and isinstance(filtered_request_data["extra_body"]["caching"], dict)
        and filtered_request_data["extra_body"]["caching"].get("type") == "enabled"
    ):
        # Remove instructions when caching is enabled
        del filtered_request_data["instructions"]

    client = OpenAI(
        base_url=request_data["api_base"],
        api_key=request_data["api_key"],
    )
    openai_response = client.responses.create(**filtered_request_data)
    raw_response = ResponsesAPIResponse(**openai_response.model_dump())
    return raw_response


class ArkLlmClient(LiteLLMClient):
    def __init__(self):
        super().__init__()
        self.transformation_handler = LiteLLMResponsesTransformationHandler()

    async def acompletion(
        self, model, messages, tools, **kwargs
    ) -> Union[ModelResponse, CustomStreamWrapper]:
        # 1 Modify messages
        # Keep the header system-prompt and the user's messages
        messages = messages[:1] + messages[-1:]

        # 2 Get request params
        (
            request_data,
            optional_params,
            litellm_params,
            logging_obj,
            custom_llm_provider,
        ) = self._get_request_data(model, messages, tools, **kwargs)

        # 3. Call litellm.aresponses with the transformed request data
        # Cannot be called directly; there is a litellm bug :
        #      https://github.com/BerriAI/litellm/issues/16267
        # raw_response = await aresponses(
        #     **request_data,
        # )
        raw_response = await openai_response_async(request_data)

        # 4. Transform ResponsesAPIResponse
        # 4.1 Create model_response object
        model_response = ModelResponse()
        setattr(model_response, "usage", litellm.Usage())

        # 4.2 Transform ResponsesAPIResponse to ModelResponses
        if isinstance(raw_response, ResponsesAPIResponse):
            response = self.transformation_handler.transform_response(
                model=model,
                raw_response=raw_response,
                model_response=model_response,
                logging_obj=logging_obj,
                request_data=request_data,
                messages=messages,
                optional_params=optional_params,
                litellm_params=litellm_params,
                encoding=kwargs.get("encoding"),
                api_key=kwargs.get("api_key"),
                json_mode=kwargs.get("json_mode"),
            )
            # 4.2.1 Modify ModelResponse id
            if raw_response and hasattr(raw_response, "id"):
                response.id = raw_response.id
            return response

        else:
            completion_stream = self.transformation_handler.get_model_response_iterator(
                streaming_response=raw_response,  # type: ignore
                sync_stream=True,
                json_mode=kwargs.get("json_mode"),
            )
            streamwrapper = CustomStreamWrapper(
                completion_stream=completion_stream,
                model=model,
                custom_llm_provider=custom_llm_provider,
                logging_obj=logging_obj,
            )
            return streamwrapper

    def _get_request_data(self, model, messages, tools, **kwargs) -> tuple:
        # 1. Get optional_params using get_optional_params function
        optional_params = get_optional_params(model=model, tools=tools, **kwargs)

        # 2. Get litellm_params using get_litellm_params function
        litellm_params = get_litellm_params(**kwargs)

        # 3. Get headers by merging kwargs headers and extra_headers
        headers = kwargs.get("headers", None) or kwargs.get("extra_headers", None)
        if headers is None:
            headers = {}
        if kwargs.get("extra_headers") is not None:
            headers.update(kwargs.get("extra_headers"))

        # 4. Get logging_obj from kwargs or create new LiteLLMLoggingObj
        logging_obj = kwargs.get("litellm_logging_obj", None)
        if logging_obj is None:
            logging_obj = Logging(
                model=model,
                messages=messages,
                stream=kwargs.get("stream", False),
                call_type="acompletion",
                litellm_call_id=str(uuid.uuid4()),
                function_id=str(uuid.uuid4()),
                start_time=datetime.now(),
                kwargs=kwargs,
            )
        # 4. Convert Message to `llm_provider` format
        _, custom_llm_provider, _, _ = get_llm_provider(model=model)
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

        # 5 Transform request to responses api format
        request_data = self.transformation_handler.transform_request(
            model=model,
            messages=messages,
            optional_params=optional_params,
            litellm_params=litellm_params,
            headers=headers,
            litellm_logging_obj=logging_obj,
            client=kwargs.get("client"),
        )

        # 6 handler Missing field supply
        if "extra_body" not in request_data and kwargs.get("extra_body"):
            request_data["extra_body"] = kwargs.get("extra_body")
        if "extra_query" not in request_data and kwargs.get("extra_query"):
            request_data["extra_query"] = kwargs.get("extra_query")
        if "extra_headers" not in request_data and kwargs.get("extra_headers"):
            request_data["extra_headers"] = kwargs.get("extra_headers")

        return (
            request_data,
            optional_params,
            litellm_params,
            logging_obj,
            custom_llm_provider,
        )


class ArkLlm(LiteLlm):
    llm_client: ArkLlmClient = Field(default_factory=ArkLlmClient)
    _additional_args: Dict[str, Any] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

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

        self._maybe_append_user_content(llm_request)
        # logger.debug(_build_request_log(llm_request))

        messages, tools, response_format, generation_params = _get_completion_inputs(
            llm_request
        )

        if "functions" in self._additional_args:
            # LiteLLM does not support both tools and functions together.
            tools = None
        # ------------------------------------------------------ #
        # get previous_response_id
        previous_response_id = None
        if llm_request.cache_metadata and llm_request.cache_metadata.cache_name:
            previous_response_id = llm_request.cache_metadata.cache_name
        # ------------------------------------------------------ #
        completion_args = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "response_format": response_format,
            "previous_response_id": previous_response_id,  # supply previous_response_id
        }
        completion_args.update(self._additional_args)

        if generation_params:
            completion_args.update(generation_params)

        if stream:
            text = ""
            # Track function calls by index
            function_calls = {}  # index -> {name, args, id}
            completion_args["stream"] = True
            aggregated_llm_response = None
            aggregated_llm_response_with_tool_call = None
            usage_metadata = None
            fallback_index = 0
            async for part in await self.llm_client.acompletion(**completion_args):
                for chunk, finish_reason in _model_response_to_chunk(part):
                    if isinstance(chunk, FunctionChunk):
                        index = chunk.index or fallback_index
                        if index not in function_calls:
                            function_calls[index] = {"name": "", "args": "", "id": None}

                        if chunk.name:
                            function_calls[index]["name"] += chunk.name
                        if chunk.args:
                            function_calls[index]["args"] += chunk.args

                            # check if args is completed (workaround for improper chunk
                            # indexing)
                            try:
                                json.loads(function_calls[index]["args"])
                                fallback_index += 1
                            except json.JSONDecodeError:
                                pass

                        function_calls[index]["id"] = (
                            chunk.id or function_calls[index]["id"] or str(index)
                        )
                    elif isinstance(chunk, TextChunk):
                        text += chunk.text
                        yield _message_to_generate_content_response(
                            ChatCompletionAssistantMessage(
                                role="assistant",
                                content=chunk.text,
                            ),
                            is_partial=True,
                        )
                    elif isinstance(chunk, UsageMetadataChunk):
                        usage_metadata = types.GenerateContentResponseUsageMetadata(
                            prompt_token_count=chunk.prompt_tokens,
                            candidates_token_count=chunk.completion_tokens,
                            total_token_count=chunk.total_tokens,
                        )

                    if (
                        finish_reason == "tool_calls" or finish_reason == "stop"
                    ) and function_calls:
                        tool_calls = []
                        for index, func_data in function_calls.items():
                            if func_data["id"]:
                                tool_calls.append(
                                    ChatCompletionMessageToolCall(
                                        type="function",
                                        id=func_data["id"],
                                        function=Function(
                                            name=func_data["name"],
                                            arguments=func_data["args"],
                                            index=index,
                                        ),
                                    )
                                )
                        aggregated_llm_response_with_tool_call = (
                            _message_to_generate_content_response(
                                ChatCompletionAssistantMessage(
                                    role="assistant",
                                    content=text,
                                    tool_calls=tool_calls,
                                )
                            )
                        )
                        text = ""
                        function_calls.clear()
                    elif finish_reason == "stop" and text:
                        aggregated_llm_response = _message_to_generate_content_response(
                            ChatCompletionAssistantMessage(
                                role="assistant", content=text
                            )
                        )
                        text = ""

            # waiting until streaming ends to yield the llm_response as litellm tends
            # to send chunk that contains usage_metadata after the chunk with
            # finish_reason set to tool_calls or stop.
            if aggregated_llm_response:
                if usage_metadata:
                    aggregated_llm_response.usage_metadata = usage_metadata
                    usage_metadata = None
                yield aggregated_llm_response

            if aggregated_llm_response_with_tool_call:
                if usage_metadata:
                    aggregated_llm_response_with_tool_call.usage_metadata = (
                        usage_metadata
                    )
                yield aggregated_llm_response_with_tool_call

        else:
            response = await self.llm_client.acompletion(**completion_args)
            # ------------------------------------------------------ #
            # Transport response id
            # yield _model_response_to_generate_content_response(response)
            llm_response = _model_response_to_generate_content_response(response)
            yield _add_response_id_to_llm_response(llm_response, response)
            # ------------------------------------------------------ #
