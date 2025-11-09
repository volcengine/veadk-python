import json
from typing import Any, Dict, Union, AsyncGenerator, Optional

import litellm
import openai
from openai.types.responses import Response as OpenAITypeResponse, ResponseStreamEvent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.cache_metadata import CacheMetadata
from google.adk.models import LlmRequest, LlmResponse
from google.adk.models.lite_llm import (
    LiteLlm,
    _get_completion_inputs,
    FunctionChunk,
    TextChunk,
    _message_to_generate_content_response,
    UsageMetadataChunk,
    _model_response_to_generate_content_response,
)
from google.genai import types
from litellm import ChatCompletionAssistantMessage
from litellm.types.utils import (
    ChatCompletionMessageToolCall,
    Function,
)
from pydantic import Field

from veadk.models.ark_transform import (
    CompletionToResponsesAPIHandler,
)
from veadk.utils.logger import get_logger

# This will add functions to prompts if functions are provided.
litellm.add_function_to_prompt = True

logger = get_logger(__name__)


class ArkLlmClient:
    async def aresponse(
        self, **kwargs
    ) -> Union[OpenAITypeResponse, openai.AsyncStream[ResponseStreamEvent]]:
        # 1. Get request params
        api_base = kwargs.pop("api_base", None)
        api_key = kwargs.pop("api_key", None)

        # 2. Call openai responses
        client = openai.AsyncOpenAI(
            base_url=api_base,
            api_key=api_key,
        )

        raw_response = await client.responses.create(**kwargs)
        return raw_response


class ArkLlm(LiteLlm):
    llm_client: ArkLlmClient = Field(default_factory=ArkLlmClient)
    _additional_args: Dict[str, Any] = None
    transform_handler: CompletionToResponsesAPIHandler = Field(
        default_factory=CompletionToResponsesAPIHandler
    )

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
        response_args = self.transform_handler.transform_request(**completion_args)

        if stream:
            text = ""
            # Track function calls by index
            function_calls = {}  # index -> {name, args, id}
            response_args["stream"] = True
            aggregated_llm_response = None
            aggregated_llm_response_with_tool_call = None
            usage_metadata = None
            fallback_index = 0
            raw_response = await self.llm_client.aresponse(**response_args)
            async for part in raw_response:
                for (
                    chunk,
                    finish_reason,
                ) in self.transform_handler.stream_event_to_chunk(
                    part, model=self.model
                ):
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
            raw_response = await self.llm_client.aresponse(**response_args)
            yield self._openai_response_to_generate_content_response(raw_response)

    def _openai_response_to_generate_content_response(
        self, raw_response: OpenAITypeResponse
    ) -> LlmResponse:
        """
        OpenAITypeResponse -> litellm.ModelResponse -> LlmResponse
        """
        model_response = self.transform_handler.transform_response(
            openai_response=raw_response, stream=False
        )
        llm_response = _model_response_to_generate_content_response(model_response)

        if not model_response.id.startswith("chatcmpl"):
            if llm_response.custom_metadata is None:
                llm_response.custom_metadata = {}
            llm_response.custom_metadata["response_id"] = model_response["id"]
        # add responses cache data
        if model_response.get("usage", {}).get("prompt_tokens_details"):
            if llm_response.usage_metadata:
                llm_response.usage_metadata.cached_content_token_count = (
                    model_response.get("usage", {})
                    .get("prompt_tokens_details")
                    .cached_tokens
                )
        return llm_response


# before_model_callback
def add_previous_response_id(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    invocation_context = callback_context._invocation_context
    events = invocation_context.session.events
    if (
        events
        and len(events) >= 2
        and events[-2].custom_metadata
        and "response_id" in events[-2].custom_metadata
    ):
        previous_response_id = events[-2].custom_metadata["response_id"]
        llm_request.cache_metadata = CacheMetadata(
            cache_name=previous_response_id,
            expire_time=0,
            fingerprint="",
            invocations_used=0,
            cached_contents_count=0,
        )
    return
