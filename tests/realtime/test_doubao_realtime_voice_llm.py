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

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from google.genai import types
from veadk.realtime.doubao_realtime_voice_llm import DoubaoRealtimeVoice
from google.adk.models.llm_request import LlmRequest
from google.adk.models.base_llm_connection import BaseLlmConnection
from google.genai.types import GenerateContentConfig
import os
from veadk.realtime.client import DoubaoClient
from veadk.realtime.doubao_realtime_voice_llm import (
    _AGENT_ENGINE_TELEMETRY_TAG,
    _AGENT_ENGINE_TELEMETRY_ENV_VARIABLE_NAME,
)


class TestDoubaoRealtimeVoice:
    @pytest.fixture
    def mock_llm_request(self):
        request = MagicMock(spec=LlmRequest)
        request.model = "doubao_realtime_voice"
        request.config = GenerateContentConfig()
        request.config.system_instruction = "Test instruction"
        request.config.tools = []
        request.live_connect_config = types.LiveConnectConfig(
            http_options=types.HttpOptions()
        )
        return request

    def test_supported_models(self):
        """Test supported_models returns correct model patterns"""
        models = DoubaoRealtimeVoice.supported_models()
        assert isinstance(models, list)
        assert len(models) == 2
        assert r"doubao_realtime_voice.*" in models
        assert r"Doubao_scene_SLM_Doubao_realtime_voice_model.*" in models

    def test_api_client_property(self):
        """Test api_client property returns DoubaoClient with correct options"""
        model = DoubaoRealtimeVoice()
        client = model.api_client
        assert isinstance(client, DoubaoClient)
        assert client._api_client._http_options.retry_options == model.retry_options

    def test_live_api_client_property(self):
        """Test _live_api_client property returns DoubaoClient with correct version"""
        model = DoubaoRealtimeVoice()
        client = model._live_api_client
        assert isinstance(client, DoubaoClient)
        assert client._api_client._http_options.api_version == model._live_api_version

    def test_tracking_headers_without_env(self):
        """Test _tracking_headers without environment variable"""
        model = DoubaoRealtimeVoice()
        headers = model._tracking_headers
        assert "x-volcengine-api-client" in headers
        assert "user-agent" in headers
        assert _AGENT_ENGINE_TELEMETRY_TAG not in headers["x-volcengine-api-client"]

    @patch.dict(os.environ, {_AGENT_ENGINE_TELEMETRY_ENV_VARIABLE_NAME: "test_id"})
    def test_tracking_headers_with_env(self):
        """Test _tracking_headers with environment variable set"""
        model = DoubaoRealtimeVoice()
        headers = model._tracking_headers
        assert _AGENT_ENGINE_TELEMETRY_TAG in headers["x-volcengine-api-client"]

    @pytest.mark.asyncio
    async def test_connect_with_speech_config(self, mock_llm_request):
        """Test connect method with speech config"""
        speech_config = types.SpeechConfig()
        model = DoubaoRealtimeVoice(speech_config=speech_config)

        # 修正异步上下文管理器的 mock 设置
        with patch.object(model._live_api_client.aio.live, "connect") as mock_connect:
            # 创建模拟的异步上下文管理器
            mock_session = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_session

            async with model.connect(mock_llm_request) as connection:
                assert isinstance(connection, BaseLlmConnection)
                assert (
                    mock_llm_request.live_connect_config.speech_config == speech_config
                )
                mock_connect.assert_called_once_with(
                    model=mock_llm_request.model,
                    config=mock_llm_request.live_connect_config,
                )

    @pytest.mark.asyncio
    async def test_connect_without_speech_config(self, mock_llm_request):
        """Test connect method without speech config"""
        model = DoubaoRealtimeVoice()

        with patch.object(model._live_api_client.aio.live, "connect") as mock_connect:
            # 使用AsyncMock模拟会话对象，更贴近真实场景
            mock_session = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_session

            async with model.connect(mock_llm_request) as connection:
                assert isinstance(connection, BaseLlmConnection)
                # 验证speech_config为None而非检查属性是否存在
                assert mock_llm_request.live_connect_config.speech_config is None
                mock_connect.assert_called_once_with(
                    model=mock_llm_request.model,
                    config=mock_llm_request.live_connect_config,
                )
