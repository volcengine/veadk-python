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
import inspect

import httpx
import pytest

from veadk.tools.builtin_tools import speech_to_text as stt_module
from veadk.tools.builtin_tools.speech_to_text import speech_to_text


class _FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self.error:
            raise self.error
        return self.response


def _patch_client(monkeypatch, response=None, error=None):
    fake = _FakeClient(response=response, error=error)
    monkeypatch.setattr(stt_module.httpx, "AsyncClient", lambda *a, **kw: fake)
    return fake


def _success_response(text="hello", utterances=None, duration=1200):
    return httpx.Response(
        200,
        headers={"X-Api-Status-Code": "20000000", "X-Tt-Logid": "log-1"},
        json={
            "audio_info": {"duration": duration},
            "result": {
                "text": text,
                "utterances": utterances
                if utterances is not None
                else [
                    {
                        "start_time": 0,
                        "end_time": 500,
                        "text": "hello",
                        "words": [{"text": "hello"}],
                    }
                ],
            },
        },
    )


def test_signature():
    sig = inspect.signature(speech_to_text)
    assert list(sig.parameters) == ["audio", "timeout"]
    assert sig.parameters["timeout"].default == 300


@pytest.mark.asyncio
async def test_missing_api_key(monkeypatch):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "")
    result = await speech_to_text("a.wav")
    assert "TOOL_SPEECH_TO_TEXT_API_KEY" in result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("audio", ["", None, 123])
async def test_invalid_audio(monkeypatch, audio):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    result = await speech_to_text(audio)
    assert result == {"error": "audio must be a non-empty path or URL"}


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0, 601, 1.5, True, "30"])
async def test_invalid_timeout(monkeypatch, timeout):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    result = await speech_to_text("a.wav", timeout=timeout)
    assert result == {"error": "timeout must be an integer between 1 and 600 seconds"}


@pytest.mark.asyncio
async def test_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    result = await speech_to_text(str(tmp_path / "missing.wav"))
    assert "does not exist" in result["error"]


@pytest.mark.asyncio
async def test_unsupported_suffix(monkeypatch, tmp_path):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    path = tmp_path / "audio.flac"
    path.write_bytes(b"data")
    result = await speech_to_text(str(path))
    assert "unsupported audio format" in result["error"]


@pytest.mark.asyncio
async def test_empty_file(monkeypatch, tmp_path):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    path = tmp_path / "audio.mp3"
    path.touch()
    result = await speech_to_text(str(path))
    assert "empty" in result["error"]


@pytest.mark.asyncio
async def test_file_too_large(monkeypatch, tmp_path):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    monkeypatch.setattr(stt_module, "_MAX_AUDIO_BYTES", 2)
    path = tmp_path / "audio.wav"
    path.write_bytes(b"12345")
    result = await speech_to_text(str(path))
    assert "100 MB" in result["error"]


@pytest.mark.asyncio
async def test_local_file_success(monkeypatch, tmp_path):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    path = tmp_path / "audio.wav"
    path.write_bytes(b"audio-bytes")
    fake = _patch_client(monkeypatch, response=_success_response("hi there"))

    result = await speech_to_text(str(path))

    assert result["text"] == "hi there"
    assert result["duration_ms"] == 1200
    assert result["log_id"] == "log-1"
    assert result["utterances"] == [{"start_time": 0, "end_time": 500, "text": "hello"}]
    sent = fake.calls[0]
    assert sent["url"] == stt_module._ENDPOINT
    assert sent["headers"]["X-Api-Key"] == "key"
    assert sent["headers"]["X-Api-Resource-Id"] == "volc.bigasr.auc_turbo"
    assert sent["headers"]["X-Api-Sequence"] == "-1"
    assert base64.b64decode(sent["json"]["audio"]["data"]) == b"audio-bytes"
    assert sent["json"]["request"]["model_name"] == "bigmodel"


@pytest.mark.asyncio
async def test_non_object_utterance_is_skipped(monkeypatch, tmp_path):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    path = tmp_path / "audio.wav"
    path.write_bytes(b"audio-bytes")
    _patch_client(
        monkeypatch,
        response=_success_response("hi", utterances=["not-a-dict", {"text": "ok"}]),
    )

    result = await speech_to_text(str(path))

    assert result["utterances"] == [
        {"start_time": None, "end_time": None, "text": "ok"}
    ]


@pytest.mark.asyncio
async def test_url_success(monkeypatch):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    monkeypatch.setattr(stt_module, "assert_public_url", lambda url: "example.com")
    fake = _patch_client(monkeypatch, response=_success_response("remote"))

    result = await speech_to_text("https://example.com/a.mp3")

    assert result["text"] == "remote"
    assert fake.calls[0]["json"]["audio"] == {"url": "https://example.com/a.mp3"}


@pytest.mark.asyncio
async def test_url_rejected(monkeypatch):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")

    def reject(_url):
        raise ValueError("Blocked non-public address")

    monkeypatch.setattr(stt_module, "assert_public_url", reject)
    result = await speech_to_text("http://127.0.0.1/a.mp3")
    assert "Blocked non-public address" in result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        ("20000003", None, "no speech"),
        ("45000001", None, "invalid request parameters"),
        ("45000002", None, "empty"),
        ("45000151", None, "unsupported audio format"),
        ("55000031", None, "busy"),
        ("99999999", "custom failure", "custom failure"),
        ("", None, "HTTP 400"),
    ],
)
async def test_error_status(monkeypatch, tmp_path, status, message, expected):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    path = tmp_path / "audio.wav"
    path.write_bytes(b"x")
    headers = {"X-Tt-Logid": "log-err"}
    if status:
        headers["X-Api-Status-Code"] = status
    if message:
        headers["X-Api-Message"] = message
    _patch_client(monkeypatch, response=httpx.Response(400, headers=headers))

    result = await speech_to_text(str(path))

    assert expected in result["error"]
    assert result["log_id"] == "log-err"


@pytest.mark.asyncio
async def test_invalid_json(monkeypatch, tmp_path):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    path = tmp_path / "audio.wav"
    path.write_bytes(b"x")
    _patch_client(
        monkeypatch,
        response=httpx.Response(
            200,
            headers={"X-Api-Status-Code": "20000000", "X-Tt-Logid": "log"},
            content=b"not-json",
        ),
    )
    result = await speech_to_text(str(path))
    assert "invalid ASR response" in result["error"]


@pytest.mark.asyncio
async def test_http_error_without_status_header(monkeypatch, tmp_path):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    path = tmp_path / "audio.wav"
    path.write_bytes(b"x")
    _patch_client(monkeypatch, response=httpx.Response(500))
    result = await speech_to_text(str(path))
    assert "HTTP 500" in result["error"]


@pytest.mark.asyncio
async def test_transport_error(monkeypatch, tmp_path):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    path = tmp_path / "audio.wav"
    path.write_bytes(b"x")
    _patch_client(monkeypatch, error=httpx.ConnectError("boom"))
    result = await speech_to_text(str(path))
    assert "ASR request failed" in result["error"]


@pytest.mark.asyncio
async def test_response_with_unexpected_shapes(monkeypatch, tmp_path):
    monkeypatch.setattr(stt_module, "_resolve_api_key", lambda: "key")
    path = tmp_path / "audio.wav"
    path.write_bytes(b"x")
    _patch_client(
        monkeypatch,
        response=httpx.Response(
            200,
            headers={"X-Api-Status-Code": "20000000"},
            json=["unexpected"],
        ),
    )
    result = await speech_to_text(str(path))
    assert result["text"] == ""
    assert result["utterances"] == []
    assert result["duration_ms"] is None


def test_resolve_api_key_env(monkeypatch):
    monkeypatch.setenv("TOOL_SPEECH_TO_TEXT_API_KEY", "primary")
    monkeypatch.setenv("TOOL_VESPEECH_API_KEY", "fallback")
    assert stt_module._resolve_api_key() == "primary"


def test_resolve_api_key_falls_back(monkeypatch):
    monkeypatch.delenv("TOOL_SPEECH_TO_TEXT_API_KEY", raising=False)
    monkeypatch.setenv("TOOL_VESPEECH_API_KEY", "fallback")
    assert stt_module._resolve_api_key() == "fallback"


def test_resolve_api_key_settings_failure(monkeypatch):
    monkeypatch.delenv("TOOL_SPEECH_TO_TEXT_API_KEY", raising=False)
    monkeypatch.delenv("TOOL_VESPEECH_API_KEY", raising=False)

    class Broken:
        @property
        def api_key(self):
            raise RuntimeError("no credentials")

    monkeypatch.setattr(
        stt_module.settings, "tool", type("Tool", (), {"vespeech": Broken()})()
    )
    assert stt_module._resolve_api_key() == ""
