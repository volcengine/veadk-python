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

from __future__ import annotations

import contextlib
from functools import cached_property
import os
import sys

from typing import Optional
from typing import TYPE_CHECKING


from .client import DoubaoClient
from google.genai import types
from typing_extensions import override
from google.adk import version
from google.adk.models.google_llm import Gemini
from google.adk.models.base_llm_connection import BaseLlmConnection
from .doubao_realtime_voice_llm_connection import DoubaoRealtimeVoiceLlmConnection


if TYPE_CHECKING:
    from google.adk.models.llm_request import LlmRequest

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

_NEW_LINE = "\n"
_EXCLUDED_PART_FIELD = {"inline_data": {"data"}}
_AGENT_ENGINE_TELEMETRY_TAG = "remote_reasoning_engine"
_AGENT_ENGINE_TELEMETRY_ENV_VARIABLE_NAME = "VOLCENGINE_CLOUD_AGENT_ENGINE_ID"


class DoubaoRealtimeVoice(Gemini):
    """Integration for doubao realtime voice model.

    Attributes:
      model: The name of the doubao realtime voice model (default: 'doubao_realtime_voice').
      speech_config: Optional speech configuration for voice input/output (type: google.genai.types.SpeechConfig).
      retry_options: Optional HTTP retry configuration for failed requests (type: google.genai.types.HttpRetryOptions).
    """

    model: str = "doubao_realtime_voice"

    speech_config: Optional[types.SpeechConfig] = None

    retry_options: Optional[types.HttpRetryOptions] = None
    """Allow doubao realtime voice model to retry failed responses.
  
    Sample:
    ```python
    from google.genai import types
  
    # ...
  
    agent = Agent(
      model=DoubaoRealtimeVoice(
        retry_options=types.HttpRetryOptions(initial_delay=1, attempts=2),
      )
    )
    ```
    """

    @classmethod
    @override
    def supported_models(cls) -> list[str]:
        """Provides the list of supported models.

        Returns:
          A list of supported models.
        """

        return [
            r"doubao_realtime_voice.*",
            r"Doubao_scene_SLM_Doubao_realtime_voice_model.*",
        ]

    @cached_property
    def api_client(self) -> DoubaoClient:
        """Provides the api client.

        Returns:
          The api client.
        """
        return DoubaoClient(
            http_options=types.HttpOptions(
                headers=self._tracking_headers,
                retry_options=self.retry_options,
            )
        )

    @cached_property
    def _live_api_client(self) -> DoubaoClient:
        return DoubaoClient(
            http_options=types.HttpOptions(
                headers=self._tracking_headers, api_version=self._live_api_version
            )
        )

    @cached_property
    def _tracking_headers(self) -> dict[str, str]:
        framework_label = f"veadk/{version.__version__}"
        if os.environ.get(_AGENT_ENGINE_TELEMETRY_ENV_VARIABLE_NAME):
            framework_label = f"{framework_label}+{_AGENT_ENGINE_TELEMETRY_TAG}"
        language_label = "ve-python/" + sys.version.split()[0]
        version_header_value = f"{framework_label} {language_label}"
        tracking_headers = {
            "x-volcengine-api-client": version_header_value,
            "user-agent": version_header_value,
        }
        return tracking_headers

    @contextlib.asynccontextmanager
    async def connect(self, llm_request: LlmRequest) -> BaseLlmConnection:
        """Connects to the doubao realtime voice LLM model and returns an llm connection.

        Args:
          llm_request: LlmRequest, the request to send to the Seed LLM model.

        Yields:
          BaseLlmConnection, the connection to the Seed LLM model.
        """
        # add tracking headers to custom headers and set api_version given
        # the customized http options will override the one set in the api client
        # constructor
        if (
            llm_request.live_connect_config
            and llm_request.live_connect_config.http_options
        ):
            if not llm_request.live_connect_config.http_options.headers:
                llm_request.live_connect_config.http_options.headers = {}
            llm_request.live_connect_config.http_options.headers.update(
                self._tracking_headers
            )
            llm_request.live_connect_config.http_options.api_version = (
                self._live_api_version
            )

        if self.speech_config is not None:
            llm_request.live_connect_config.speech_config = self.speech_config

        llm_request.live_connect_config.system_instruction = types.Content(
            role="system",
            parts=[types.Part.from_text(text=llm_request.config.system_instruction)],
        )
        llm_request.live_connect_config.tools = llm_request.config.tools
        logger.info("Connecting to live with llm_request:%s", llm_request)
        async with self._live_api_client.aio.live.connect(
            model=llm_request.model, config=llm_request.live_connect_config
        ) as live_session:
            # use DoubaoRealtimeVoiceLlmConnection in place of GeminiLlmConnection
            yield DoubaoRealtimeVoiceLlmConnection(live_session)
