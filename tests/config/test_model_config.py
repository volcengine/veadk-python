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
from unittest import TestCase, mock
from veadk.configs.model_configs import RealtimeModelConfig


class TestRealtimeModelConfig(TestCase):
    def test_default_values(self):
        """Test that default values are set correctly"""
        config = RealtimeModelConfig()
        self.assertEqual(config.name, "doubao_realtime_voice_model")
        self.assertEqual(
            config.api_base, "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
        )

    @mock.patch.dict(os.environ, {"MODEL_REALTIME_API_KEY": "test_api_key"})
    def test_api_key_from_env(self):
        """Test api_key is retrieved from environment variable"""
        config = RealtimeModelConfig()
        self.assertEqual(config.api_key, "test_api_key")

    @mock.patch.dict(os.environ, {}, clear=True)
    @mock.patch(
        "veadk.configs.model_configs.get_speech_token", return_value="mocked_token"
    )
    def test_api_key_from_get_speech_token(self, mock_get_token):
        """Test api_key falls back to get_speech_token when env var is not set"""
        config = RealtimeModelConfig()
        self.assertEqual(config.api_key, "mocked_token")
        mock_get_token.assert_called_once()

    @mock.patch.dict(os.environ, {"MODEL_REALTIME_API_KEY": ""})
    @mock.patch(
        "veadk.configs.model_configs.get_speech_token", return_value="mocked_token"
    )
    def test_api_key_empty_env_var(self, mock_get_token):
        """Test api_key falls back when env var is empty string"""
        config = RealtimeModelConfig()
        self.assertEqual(config.api_key, "mocked_token")
        mock_get_token.assert_called_once()

    def test_api_key_caching(self):
        """Test that api_key is properly cached"""
        with mock.patch.dict(os.environ, {"MODEL_REALTIME_API_KEY": "test_key"}):
            config = RealtimeModelConfig()
            first_call = config.api_key
            second_call = config.api_key
            self.assertEqual(first_call, second_call)
            self.assertEqual(first_call, "test_key")
