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
from unittest.mock import AsyncMock, MagicMock
from veadk.realtime.live import DoubaoAsyncSession, ProtocolEvents
from veadk.realtime import protocol
from google.genai import types


@pytest.fixture
def mock_ws():
    ws = AsyncMock()
    ws.recv = AsyncMock()
    ws.send = AsyncMock()
    ws.response = MagicMock()
    ws.response.headers = {"X-Tt-Logid": "test-logid"}
    return ws


@pytest.fixture
def mock_api_client():
    client = MagicMock()
    client._websocket_ssl_ctx = {}
    return client


@pytest.fixture
def mock_session(mock_ws, mock_api_client):
    return DoubaoAsyncSession(
        api_client=mock_api_client, websocket=mock_ws, session_id="test-session-id"
    )


@pytest.mark.asyncio
async def test_send_realtime_input(mock_session):
    # Test with media input
    media = types.Blob(data=b"test-data", mime_type="audio/pcm")
    await mock_session.send_realtime_input(media=media)

    # Verify the message was constructed and sent correctly
    assert mock_session._ws.send.called

    # Test with multiple arguments (should raise error)
    with pytest.raises(ValueError):
        await mock_session.send_realtime_input(media=media, text="test")


@pytest.mark.asyncio
async def test_receive(mock_session):
    # Mock different response types
    test_cases = [
        (
            {"event": ProtocolEvents.ASR_INFO},
            {
                "message_type": "SERVER_FULL_RESPONSE",
                "event": ProtocolEvents.ASR_INFO,
                "payload_msg": {"asr_task_id": "test_id"},
            },
            True,
        ),  # ASR_INFO
        (
            {"event": ProtocolEvents.ASR_RESPONSE},
            {
                "message_type": "SERVER_FULL_RESPONSE",
                "event": ProtocolEvents.ASR_RESPONSE,
                "payload_msg": {"results": [{"text": "test"}]},
            },
            "test",
        ),
        # ASR_RESPONSE
        (
            {"event": ProtocolEvents.TTS_RESPONSE},
            {
                "message_type": "SERVER_FULL_RESPONSE",
                "event": ProtocolEvents.TTS_RESPONSE,
                "payload_msg": b"audio-data",
            },
            b"audio-data",
        ),  # TTS_RESPONSE
        (
            {"event": ProtocolEvents.CHAT_RESPONSE},
            {
                "message_type": "SERVER_FULL_RESPONSE",
                "event": ProtocolEvents.CHAT_RESPONSE,
                "payload_msg": {"content": "chat"},
            },
            "chat",
        ),  # CHAT_RESPONSE
        (
            {"event": ProtocolEvents.USAGE_RESPONSE},
            {
                "message_type": "SERVER_FULL_RESPONSE",
                "event": ProtocolEvents.USAGE_RESPONSE,
                "payload_msg": {"usage": {"cached_1": 10, "cached_2": 20, "other": 5}},
            },
            35,
        ),  # USAGE_RESPONSE
    ]

    for response_data, parse_data, expected in test_cases:
        mock_session._ws.recv = AsyncMock(return_value=response_data)
        protocol.parse_response = MagicMock(return_value=parse_data)
        async for msg in mock_session.receive():
            if response_data["event"] == ProtocolEvents.ASR_INFO:
                assert msg.server_content.interrupted == expected
            elif response_data["event"] == ProtocolEvents.ASR_RESPONSE:
                assert msg.server_content.input_transcription.text == expected
            elif response_data["event"] == ProtocolEvents.TTS_RESPONSE:
                assert (
                    msg.server_content.model_turn.parts[0].inline_data.data == expected
                )
            elif response_data["event"] == ProtocolEvents.CHAT_RESPONSE:
                assert msg.server_content.output_transcription.text == expected
            elif response_data["event"] == ProtocolEvents.USAGE_RESPONSE:
                assert msg.usage_metadata.tool_use_prompt_token_count == expected
            break


@pytest.mark.asyncio
async def test_convert_to_live_server_message(mock_session):
    # Test ASR_INFO event
    response = {
        "event": ProtocolEvents.ASR_INFO,
        "payload_msg": {"asr_task_id": "test_id"},
    }
    result = mock_session.convert_to_live_server_message(response)
    assert result.server_content.interrupted

    # Test ASR_RESPONSE event
    response = {
        "event": ProtocolEvents.ASR_RESPONSE,
        "payload_msg": {"results": [{"text": "test"}]},
    }
    result = mock_session.convert_to_live_server_message(response)
    assert result.server_content.input_transcription.text == "test"

    # Test TTS_RESPONSE event
    response = {"event": ProtocolEvents.TTS_RESPONSE, "payload_msg": b"audio-data"}
    result = mock_session.convert_to_live_server_message(response)
    assert result.server_content.model_turn.parts[0].inline_data.data == b"audio-data"

    # Test CHAT_ENDED event
    response = {
        "event": ProtocolEvents.CHAT_ENDED,
        "payload_msg": {"results": [{"text": "test"}]},
    }
    result = mock_session.convert_to_live_server_message(response)
    assert result.server_content.output_transcription.finished

    # Test TTS_ENDED event
    response = {
        "event": ProtocolEvents.TTS_ENDED,
        "payload_msg": {"results": [{"text": "test"}]},
    }
    result = mock_session.convert_to_live_server_message(response)
    assert result.server_content.turn_complete
