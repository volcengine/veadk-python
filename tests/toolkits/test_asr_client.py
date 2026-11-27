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

import io
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from veadk.toolkits.audio.asr import asr_client
from veadk.toolkits.audio.asr.asr_client import AsrWsClient, RequestBuilder


def make_wav(pcm):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(pcm)
    return output.getvalue()


@pytest.mark.asyncio
async def test_read_audio_data_preserves_non_wav_source(tmp_path, monkeypatch):
    source = tmp_path / "recording.mp3"
    original = b"test compressed audio"
    source.write_bytes(original)
    converted = make_wav(b"\x01\x00" * 160)
    run = Mock(return_value=SimpleNamespace(stdout=converted))
    monkeypatch.setattr(asr_client.subprocess, "run", run)

    client = AsrWsClient("test-app", "test-token")
    assert await client.read_audio_data(str(source)) == converted
    run.assert_called_once()
    assert source.exists(), "ASR conversion must preserve the caller's source file"
    assert source.read_bytes() == original


@pytest.mark.asyncio
async def test_connections_use_each_clients_credentials():
    first = AsrWsClient("test-app-one", "test-token-one")
    second = AsrWsClient("test-app-two", "test-token-two")
    first.session = SimpleNamespace(ws_connect=AsyncMock())
    second.session = SimpleNamespace(ws_connect=AsyncMock())

    await first.create_connection()
    await second.create_connection()

    for client, app_id, token in (
        (first, "test-app-one", "test-token-one"),
        (second, "test-app-two", "test-token-two"),
    ):
        headers = client.session.ws_connect.call_args.kwargs["headers"]
        assert headers["X-Api-App-Key"] == app_id
        assert headers["X-Api-Access-Key"] == token
    assert (
        first.session.ws_connect.call_args.kwargs["headers"]["X-Api-Request-Id"]
        != second.session.ws_connect.call_args.kwargs["headers"]["X-Api-Request-Id"]
    )


def test_auth_header_builder_keeps_default_call_compatible():
    AsrWsClient("test-app", "test-token")
    headers = RequestBuilder.new_auth_headers()
    assert headers["X-Api-App-Key"] == "test-app"
    assert headers["X-Api-Access-Key"] == "test-token"
