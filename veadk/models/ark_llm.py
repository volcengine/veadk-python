import uuid
from datetime import datetime
from typing import Any, Dict, Union

import litellm
from google.adk.models.lite_llm import (
    LiteLlm,
    LiteLLMClient,
)
from litellm import Logging
from litellm import aresponses
from litellm.completion_extras.litellm_responses_transformation.transformation import (
    LiteLLMResponsesTransformationHandler,
)
from litellm.litellm_core_utils.get_litellm_params import get_litellm_params
from litellm.litellm_core_utils.get_llm_provider_logic import get_llm_provider
from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper
from litellm.types.llms.openai import ResponsesAPIResponse
from litellm.types.utils import ModelResponse, LlmProviders
from litellm.utils import get_optional_params, ProviderConfigManager
from pydantic import Field

from veadk.utils.logger import get_logger

# This will add functions to prompts if functions are provided.
litellm.add_function_to_prompt = True

logger = get_logger(__name__)


class ArkLlmClient(LiteLLMClient):
    def __init__(self):
        super().__init__()
        self.transformation_handler = LiteLLMResponsesTransformationHandler()

    async def acompletion(
        self, model, messages, tools, **kwargs
    ) -> Union[ModelResponse, CustomStreamWrapper]:
        # 1.1. Get optional_params using get_optional_params function
        optional_params = get_optional_params(model=model, **kwargs)

        # 1.2. Get litellm_params using get_litellm_params function
        litellm_params = get_litellm_params(**kwargs)

        # 1.3. Get headers by merging kwargs headers and extra_headers
        headers = kwargs.get("headers", None) or kwargs.get("extra_headers", None)
        if headers is None:
            headers = {}
        if kwargs.get("extra_headers") is not None:
            headers.update(kwargs.get("extra_headers"))

        # 1.4. Get logging_obj from kwargs or create new LiteLLMLoggingObj
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
        # 1.5. Convert Message to `llm_provider` format
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

        # 1.6 Transform request to responses api format
        request_data = self.transformation_handler.transform_request(
            model=model,
            messages=messages,
            optional_params=optional_params,
            litellm_params=litellm_params,
            headers=headers,
            litellm_logging_obj=logging_obj,
            client=kwargs.get("client"),
        )

        # 2. Call litellm.aresponses with the transformed request data
        result = await aresponses(
            **request_data,
        )

        # 3.1 Create model_response object
        model_response = ModelResponse()
        setattr(model_response, "usage", litellm.Usage())

        # 3.2 Transform ResponsesAPIResponse to ModelResponses
        if isinstance(result, ResponsesAPIResponse):
            return self.transformation_handler.transform_response(
                model=model,
                raw_response=result,
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
        else:
            completion_stream = self.transformation_handler.get_model_response_iterator(
                streaming_response=result,  # type: ignore
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


class ArkLlm(LiteLlm):
    llm_client: ArkLlmClient = Field(default_factory=ArkLlmClient)
    _additional_args: Dict[str, Any] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    # async def generate_content_async(
    #   self, llm_request: LlmRequest, stream: bool = False
    # ) -> AsyncGenerator[LlmResponse, None]:
    #     pass
