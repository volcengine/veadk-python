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
import unittest
from unittest.mock import patch, MagicMock
from google.genai._api_client import BaseApiClient
from veadk.realtime.client import DoubaoClient, DoubaoAsyncClient
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class TestDoubaoAsyncClient(unittest.TestCase):
    def setUp(self):
        self.mock_api_client = MagicMock(spec=BaseApiClient)
        self.async_client = DoubaoAsyncClient(self.mock_api_client)

    def test_initialization(self):
        self.assertIsInstance(self.async_client, DoubaoAsyncClient)
        self.assertEqual(self.async_client._api_client, self.mock_api_client)

    def test_live_property(self):
        from veadk.realtime.live import DoubaoAsyncLive

        live_instance = self.async_client.live
        self.assertIsInstance(live_instance, DoubaoAsyncLive)
        self.assertEqual(live_instance._api_client, self.mock_api_client)


class TestDoubaoClient(unittest.TestCase):
    def setUp(self):
        self.patcher = patch.dict("os.environ", {}, clear=True)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_initialization_without_google_key(self):
        # Test when GOOGLE_API_KEY is not set
        os.environ["REALTIME_API_KEY"] = "hack_google_api_key"
        client = DoubaoClient()
        self.assertEqual(os.environ["GOOGLE_API_KEY"], "hack_google_api_key")
        self.assertIsNotNone(client._aio)

    def test_initialization_with_google_key(self):
        # Test when GOOGLE_API_KEY is already set
        os.environ["GOOGLE_API_KEY"] = "existing_key"
        os.environ["REALTIME_API_KEY"] = "existing_key"
        client = DoubaoClient()
        self.assertEqual(os.environ["GOOGLE_API_KEY"], "existing_key")
        self.assertIsNotNone(client._aio)

    @patch(
        "veadk.realtime.client.DoubaoAsyncClient", side_effect=Exception("Test error")
    )
    def test_initialization_failure(self, mock_async_client):
        # Test when DoubaoAsyncClient initialization fails
        os.environ["REALTIME_API_KEY"] = "hack_google_api_key"
        client = DoubaoClient()
        self.assertIsNone(client._aio)

    def test_aio_property(self):
        os.environ["REALTIME_API_KEY"] = "hack_google_api_key"
        client = DoubaoClient()
        aio_client = client.aio
        self.assertIsInstance(aio_client, DoubaoAsyncClient)


if __name__ == "__main__":
    unittest.main()
