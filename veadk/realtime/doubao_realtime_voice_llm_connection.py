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

from typing import Union

from google.adk.models.gemini_llm_connection import GeminiLlmConnection
from google.genai import types
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

RealtimeInput = Union[types.Blob, types.ActivityStart, types.ActivityEnd]


class DoubaoRealtimeVoiceLlmConnection(GeminiLlmConnection):
    """The doubao realtime voice model connection."""

    async def send_realtime(self, input: RealtimeInput):
        """Sends a chunk of audio or a frame of video to the model in realtime.

        Args:
          input: The input to send to the model.
        """
        if isinstance(input, types.Blob):
            # The blob is binary and is very large. So let's not log it.
            # logger.debug('Sending LLM Blob.')
            # bugfix: 'error': 'decode ws request failed: unsupported protocol version 7'
            await self._gemini_session.send_realtime_input(media=input)

        elif isinstance(input, types.ActivityStart):
            logger.debug("Sending LLM activity start signal.")
            await self._gemini_session.send_realtime_input(activity_start=input)
        elif isinstance(input, types.ActivityEnd):
            logger.debug("Sending LLM activity end signal.")
            await self._gemini_session.send_realtime_input(activity_end=input)
        else:
            raise ValueError("Unsupported input type: %s" % type(input))
