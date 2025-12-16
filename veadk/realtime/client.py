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

import os
from google.genai.client import Client, AsyncClient
from google.genai._api_client import BaseApiClient
from .live import DoubaoAsyncLive
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class DoubaoAsyncClient(AsyncClient):
    """Client for making asynchronous (non-blocking) requests."""

    def __init__(self, api_client: BaseApiClient):
        super().__init__(api_client)
        self._live = DoubaoAsyncLive(self._api_client)

    @property
    def live(self) -> DoubaoAsyncLive:
        return self._live


class DoubaoClient(Client):
    """The synchronous client for doubao realtime voice model, with async support via the aio property."""

    def __init__(self, *args, **kwargs):
        # Temporary workaround to set Google API key for Gemini client
        if not os.environ.get("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = "hack_google_api_key"
        try:
            super().__init__(*args, **kwargs)
            self._aio = DoubaoAsyncClient(self._api_client)
        except Exception as e:
            logger.info(f"Failed to initialize DoubaoAsyncClient: {e}")
            self._aio = None

    @property
    def aio(self) -> DoubaoAsyncClient:
        return self._aio
