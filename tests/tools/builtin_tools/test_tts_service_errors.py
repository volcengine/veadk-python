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

import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

from veadk.tools.builtin_tools import tts


@pytest.fixture
def tts_request(monkeypatch, tmp_path):
    monkeypatch.setenv("TOOL_VESPEECH_APP_ID", "test-app")
    monkeypatch.setenv("TOOL_VESPEECH_SPEAKER", "test-speaker")
    monkeypatch.setenv("TOOL_VESPEECH_AUDIO_OUTPUT_PATH", str(tmp_path))
    monkeypatch.setattr(
        tts,
        "settings",
        SimpleNamespace(
            tool=SimpleNamespace(vespeech=SimpleNamespace(api_key="test-key"))
        ),
    )
    monkeypatch.setitem(sys.modules, "veadk.utils.audio_manager", None)
    session = MagicMock()
    monkeypatch.setattr(tts.requests, "Session", lambda: session)

    def run(frames):
        response = requests.Response()
        response.status_code = 200
        response.encoding = "utf-8"
        response._content = "\n".join(json.dumps(frame) for frame in frames).encode()
        response._content_consumed = True
        session.post.return_value = response
        context = SimpleNamespace(
            _invocation_context=SimpleNamespace(user_id="test-user")
        )
        result = tts.text_to_speech("hello", context)
        session.post.assert_called_once()
        session.close.assert_called_once()
        return result

    return run


@pytest.mark.parametrize("partial_audio", [False, True])
@pytest.mark.parametrize("message", [None, "synthesis failed"])
def test_service_error_is_not_reported_as_saved_audio(
    tts_request, partial_audio, message
):
    frames = []
    if partial_audio:
        frames.append({"code": 0, "data": base64.b64encode(b"partial").decode()})
    error = {"code": 45000001}
    if message is not None:
        error["message"] = message
    frames.append(error)

    result = tts_request(frames)

    assert set(result) == {"error"}
    assert "45000001" in result["error"]
    if message is not None:
        assert message in result["error"]


def test_completed_stream_saves_audio_without_playback(tts_request):
    audio = b"first-second"
    result = tts_request(
        [
            {"code": 0, "data": base64.b64encode(audio).decode()},
            {"code": 0, "sentence": "hello"},
            {"code": 20000000},
        ]
    )

    assert set(result) == {"saved_audio_path"}
    assert Path(result["saved_audio_path"]).read_bytes() == audio
