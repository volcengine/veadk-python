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

import queue
import json
import base64
import requests
from unittest import TestCase
from unittest.mock import patch, MagicMock
from google.adk.tools import ToolContext
from veadk.tools.builtin_tools.tts import (
    text_to_speech,
    handle_server_response,
    save_output_to_file,
    _audio_player_thread,
)


class TestTTS(TestCase):
    def setUp(self):
        self.mock_tool_context = MagicMock(spec=ToolContext)
        self.mock_tool_context._invocation_context = MagicMock()
        self.mock_tool_context._invocation_context.user_id = "test_user"

        # Mock environment variables
        self.patcher_env = patch.dict(
            "os.environ",
            {
                "TOOL_TTS_APP_ID": "test_app_id",
                "TOOL_TTS_API_KEY": "test_api_key",
                "TOOL_TTS_SPEAKER": "test_speaker",
            },
        )
        self.patcher_env.start()

    def tearDown(self):
        self.patcher_env.stop()

    @patch("requests.Session")
    def test_tts_success(self, mock_session):
        """Test successful TTS request"""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.headers = {"X-Tt-Logid": "test_log_id"}
        mock_response.iter_lines.return_value = [
            json.dumps({"code": 0, "data": base64.b64encode(b"audio_chunk").decode()}),
            json.dumps({"code": 20000000}),
        ]
        mock_session.return_value.post.return_value = mock_response

        # Call function
        result = text_to_speech("test text", self.mock_tool_context)

        # Assertions
        self.assertEqual("test text", result)  # Still returns True despite error
        mock_session.return_value.post.assert_called_once()
        mock_response.close.assert_called_once()

    @patch("requests.Session")
    def test_tts_failure(self, mock_session):
        """Test TTS request failure"""
        # Setup mock to raise exception
        mock_session.return_value.post.side_effect = (
            requests.exceptions.RequestException("Test error")
        )

        # Call function
        result = text_to_speech("test text", self.mock_tool_context)

        # Assertions
        self.assertEqual("test text", result)  # Still returns True despite error
        mock_session.return_value.post.assert_called_once()

    @patch("builtins.open")
    @patch("pyaudio.PyAudio")
    def test_handle_server_response_success(self, mock_pyaudio, mock_open):
        """Test successful response handling"""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            json.dumps({"code": 0, "data": base64.b64encode(b"audio_chunk").decode()}),
            json.dumps({"code": 20000000}),
        ]

        # Setup mock audio stream
        mock_stream = MagicMock()
        mock_pyaudio.return_value.open.return_value = mock_stream

        # Call function
        handle_server_response(mock_response, "test.pcm")

        # Assertions
        mock_stream.write.assert_called_with(b"audio_chunk")
        mock_open.assert_called_once_with("test.pcm", "wb")

    @patch("builtins.open")
    def test_save_output_to_file_success(self, mock_open):
        """Test successful audio file save"""
        # Setup mock file handler
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Call function
        save_output_to_file(b"audio_data", "test.pcm")

        # Assertions
        mock_open.assert_called_once_with("test.pcm", "wb")
        mock_file.write.assert_called_once_with(b"audio_data")

    @patch("time.sleep")
    def test_audio_player_thread(self, mock_sleep):
        """Test audio player thread"""
        # Setup test data
        mock_queue = MagicMock()
        mock_queue.get.side_effect = [b"audio_data", queue.Empty]
        mock_stream = MagicMock()
        stop_event = MagicMock()
        stop_event.is_set.side_effect = [False, True]

        # Call function
        _audio_player_thread(mock_queue, mock_stream, stop_event)

        # Assertions
        mock_stream.write.assert_called_once_with(b"audio_data")
        mock_queue.task_done.assert_called_once()
