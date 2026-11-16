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

"""Hermetic tests for the shared vision helper and its tools."""

import base64
import inspect
import socket
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from veadk.tools.builtin_tools import image_understand as understand_tool
from veadk.tools.builtin_tools import ocr as ocr_tool
from veadk.tools.builtin_tools import vision

_PUBLIC_IP = "93.184.216.34"


def _addrinfo(ip: str) -> list:
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 0))]


@pytest.fixture(autouse=True)
def _hermetic_dns(monkeypatch):
    # Remote image URLs now pass through the shared SSRF guard, which resolves
    # the host; keep tests off the network.
    monkeypatch.setattr(
        "veadk.tools.builtin_tools.web_fetch.socket.getaddrinfo",
        lambda *args, **kwargs: _addrinfo(_PUBLIC_IP),
    )


def _fake_settings(
    monkeypatch,
    *,
    api_key="settings-key",
    name="vision-model",
    base_url="https://api.example.com/v1",
):
    monkeypatch.delenv("MODEL_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_VISION_NAME", raising=False)
    fake = SimpleNamespace(
        model=SimpleNamespace(name=name, api_base=base_url, api_key=api_key)
    )
    monkeypatch.setattr(vision, "settings", fake)
    return fake


class FakeResponse:
    def __init__(self, status_code=200, payload=None, json_error=None):
        self.status_code = status_code
        self.payload = payload
        self.json_error = json_error

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.payload


def _install_client(monkeypatch, response=None, error=None):
    captured = {}

    class FakeClient:
        def __init__(self, timeout=None):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            if error is not None:
                raise error
            return response

    monkeypatch.setattr(vision.httpx, "AsyncClient", FakeClient)
    return captured


def _chat_payload(content):
    return {"choices": [{"message": {"content": content}}]}


def _png_bytes(path):
    Image.new("RGB", (3, 2), (10, 20, 30)).save(path, format="PNG")
    return path


def test_analyze_images_signature_and_defaults():
    params = inspect.signature(vision.analyze_images).parameters
    assert list(params) == ["images", "prompt", "model_name", "timeout"]
    assert params["model_name"].default is None
    assert params["timeout"].default == 60


@pytest.mark.asyncio
async def test_success_with_string_content(monkeypatch):
    _fake_settings(monkeypatch)
    captured = _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    result = await vision.analyze_images(
        ["https://example.com/a.png"], "What is this?", timeout=42
    )
    assert result == {"text": "ok", "model": "vision-model"}
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer settings-key"
    assert captured["timeout"] == 42
    body = captured["json"]
    assert body["model"] == "vision-model"
    assert body["messages"][0]["role"] == "user"
    content = body["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "What is this?"}
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "https://example.com/a.png"},
    }


@pytest.mark.asyncio
async def test_success_with_list_content_parts(monkeypatch):
    _fake_settings(monkeypatch, base_url="https://api.example.com/v1/")
    _install_client(
        monkeypatch,
        FakeResponse(
            payload=_chat_payload(
                [
                    {"type": "text", "text": "Hello "},
                    {"type": "text", "text": "world"},
                    {"type": "image_url", "image_url": {"url": "x"}},
                    "not-a-dict",
                    {"text": 5},
                ]
            )
        ),
    )
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert result == {"text": "Hello world", "model": "vision-model"}


@pytest.mark.asyncio
async def test_local_image_is_base64_encoded(monkeypatch, tmp_path):
    _fake_settings(monkeypatch)
    path = _png_bytes(tmp_path / "local.png")
    captured = _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    result = await vision.analyze_images([str(path)], "prompt")
    assert result == {"text": "ok", "model": "vision-model"}
    data_url = captured["json"]["messages"][0]["content"][1]["image_url"]["url"]
    assert data_url.startswith("data:image/png;base64,")
    decoded = base64.b64decode(data_url.split(",", 1)[1])
    assert decoded == path.read_bytes()


@pytest.mark.asyncio
async def test_local_jpeg_mime_from_pillow(monkeypatch, tmp_path):
    _fake_settings(monkeypatch)
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (2, 2), (0, 0, 0)).save(path, format="JPEG")
    captured = _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    await vision.analyze_images([str(path)], "prompt")
    data_url = captured["json"]["messages"][0]["content"][1]["image_url"]["url"]
    assert data_url.startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_filetype_fallback(monkeypatch, tmp_path):
    _fake_settings(monkeypatch)
    path = _png_bytes(tmp_path / "image.bin")
    monkeypatch.setattr(
        vision.Image, "open", lambda *args, **kwargs: (_ for _ in ()).throw(OSError())
    )
    captured = _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    await vision.analyze_images([str(path)], "prompt")
    data_url = captured["json"]["messages"][0]["content"][1]["image_url"]["url"]
    assert data_url.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_extension_fallback(monkeypatch, tmp_path):
    _fake_settings(monkeypatch)
    path = tmp_path / "image.webp"
    path.write_bytes(b"not-really-an-image")
    monkeypatch.setattr(
        vision.Image, "open", lambda *args, **kwargs: (_ for _ in ()).throw(OSError())
    )
    monkeypatch.setattr(vision.filetype, "guess", lambda data: None)
    captured = _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    await vision.analyze_images([str(path)], "prompt")
    data_url = captured["json"]["messages"][0]["content"][1]["image_url"]["url"]
    assert data_url.startswith("data:image/webp;base64,")


@pytest.mark.asyncio
async def test_octet_stream_fallback(monkeypatch, tmp_path):
    _fake_settings(monkeypatch)
    path = tmp_path / "image.bin"
    path.write_bytes(b"not-an-image")
    captured = _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    await vision.analyze_images([str(path)], "prompt")
    data_url = captured["json"]["messages"][0]["content"][1]["image_url"]["url"]
    assert data_url.startswith("data:application/octet-stream;base64,")


@pytest.mark.asyncio
async def test_model_name_override(monkeypatch):
    _fake_settings(monkeypatch)
    monkeypatch.setenv("MODEL_VISION_NAME", "env-model")
    captured = _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    result = await vision.analyze_images(
        ["https://example.com/a.png"], "prompt", model_name="explicit-model"
    )
    assert result["model"] == "explicit-model"
    assert captured["json"]["model"] == "explicit-model"


@pytest.mark.asyncio
async def test_model_name_from_environment(monkeypatch):
    _fake_settings(monkeypatch)
    monkeypatch.setenv("MODEL_VISION_NAME", "env-model")
    captured = _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert result["model"] == "env-model"
    assert captured["json"]["model"] == "env-model"


@pytest.mark.asyncio
async def test_missing_model_name(monkeypatch):
    _fake_settings(monkeypatch, name="")
    _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert "model name" in result["error"]


@pytest.mark.asyncio
async def test_api_key_from_environment(monkeypatch):
    _fake_settings(monkeypatch, api_key="settings-key")
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "env-key")
    captured = _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert captured["headers"]["Authorization"] == "Bearer env-key"


@pytest.mark.asyncio
async def test_missing_api_key(monkeypatch):
    _fake_settings(monkeypatch, api_key="")
    _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert "API key" in result["error"]


@pytest.mark.asyncio
async def test_missing_api_base(monkeypatch):
    _fake_settings(monkeypatch, base_url="")
    _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert "API base" in result["error"]


@pytest.mark.asyncio
async def test_http_error_includes_status_but_not_key(monkeypatch):
    _fake_settings(monkeypatch, api_key="super-secret-value")
    _install_client(monkeypatch, FakeResponse(status_code=429))
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert "429" in result["error"]
    assert "super-secret-value" not in result["error"]


@pytest.mark.asyncio
async def test_http_error_includes_provider_message(monkeypatch):
    _fake_settings(monkeypatch)
    _install_client(
        monkeypatch,
        FakeResponse(
            status_code=400,
            payload={
                "error": {
                    "code": "InvalidEndpoint.ClosedEndpoint",
                    "message": "The request targeted an endpoint that is closed.",
                }
            },
        ),
    )
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert "HTTP status 400" in result["error"]
    assert "endpoint that is closed" in result["error"]


@pytest.mark.asyncio
async def test_http_error_falls_back_to_provider_code(monkeypatch):
    _fake_settings(monkeypatch)
    _install_client(
        monkeypatch,
        FakeResponse(status_code=500, payload={"error": {"code": "InternalError"}}),
    )
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert "HTTP status 500: InternalError" in result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"error": "plain failure"}, "HTTP status 503: plain failure"),
        ({"message": "top-level failure"}, "HTTP status 503: top-level failure"),
        ({"error": {"message": 42}}, "HTTP status 503"),
        (["unexpected"], "HTTP status 503"),
    ],
)
async def test_http_error_detail_variants(monkeypatch, payload, expected):
    _fake_settings(monkeypatch)
    _install_client(monkeypatch, FakeResponse(status_code=503, payload=payload))
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert result["error"] == f"vision request failed with {expected}"


@pytest.mark.asyncio
async def test_http_error_with_non_json_body(monkeypatch):
    _fake_settings(monkeypatch)
    _install_client(
        monkeypatch,
        FakeResponse(status_code=502, json_error=ValueError("not json")),
    )
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert result["error"] == "vision request failed with HTTP status 502"


@pytest.mark.asyncio
async def test_http_error_detail_is_truncated(monkeypatch):
    _fake_settings(monkeypatch)
    _install_client(
        monkeypatch,
        FakeResponse(status_code=400, payload={"message": "x" * 500}),
    )
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert result["error"].endswith("x" * vision._ERROR_DETAIL_LIMIT)
    assert (
        len(result["error"])
        == len("vision request failed with HTTP status 400: ")
        + vision._ERROR_DETAIL_LIMIT
    )


@pytest.mark.asyncio
async def test_invalid_json_response(monkeypatch):
    _fake_settings(monkeypatch)
    _install_client(monkeypatch, FakeResponse(json_error=ValueError("not json")))
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert "not valid JSON" in result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"choices": []},
        {"choices": ["bad"]},
        {"choices": [{}]},
        {"choices": [{"message": "bad"}]},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": 123}}]},
    ],
)
async def test_unparseable_response(monkeypatch, payload):
    _fake_settings(monkeypatch)
    _install_client(monkeypatch, FakeResponse(payload=payload))
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert "did not contain text content" in result["error"]


@pytest.mark.asyncio
async def test_transport_error(monkeypatch):
    _fake_settings(monkeypatch, api_key="secret")
    _install_client(monkeypatch, error=httpx.ConnectError("connection reset"))
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert "vision request failed" in result["error"]
    assert "secret" not in result["error"]


@pytest.mark.asyncio
async def test_unexpected_response_error(monkeypatch):
    _fake_settings(monkeypatch)
    _install_client(monkeypatch, FakeResponse(json_error=RuntimeError("weird")))
    result = await vision.analyze_images(["https://example.com/a.png"], "prompt")
    assert "vision request failed" in result["error"]
    assert "RuntimeError" in result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"images": "not-a-list"},
        {"images": []},
        {"images": ["u"] * 9},
        {"images": [123]},
        {"images": [""]},
        {"prompt": ""},
        {"prompt": 5},
        {"timeout": 0},
        {"timeout": 301},
        {"timeout": True},
        {"timeout": "60"},
    ],
)
async def test_validation_errors(monkeypatch, overrides):
    _fake_settings(monkeypatch)
    _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    arguments = {
        "images": ["https://example.com/a.png"],
        "prompt": "prompt",
        "timeout": 60,
    }
    arguments.update(overrides)
    result = await vision.analyze_images(**arguments)
    assert "error" in result


@pytest.mark.asyncio
async def test_missing_local_image(monkeypatch, tmp_path):
    _fake_settings(monkeypatch)
    _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    result = await vision.analyze_images([str(tmp_path / "missing.png")], "prompt")
    assert "does not exist" in result["error"]


@pytest.mark.asyncio
async def test_remote_image_internal_address_is_rejected(monkeypatch):
    _fake_settings(monkeypatch)
    captured = _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    monkeypatch.setattr(
        "veadk.tools.builtin_tools.web_fetch.socket.getaddrinfo",
        lambda *args, **kwargs: _addrinfo("169.254.169.254"),
    )
    result = await vision.analyze_images(
        ["http://169.254.169.254/latest/meta-data/"], "prompt"
    )
    assert "error" in result
    assert "non-public" in result["error"] or "Blocked" in result["error"]
    # The provider must never be asked to fetch the internal URL.
    assert "json" not in captured


@pytest.mark.asyncio
async def test_remote_image_loopback_is_rejected(monkeypatch):
    _fake_settings(monkeypatch)
    captured = _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    monkeypatch.setattr(
        "veadk.tools.builtin_tools.web_fetch.socket.getaddrinfo",
        lambda *args, **kwargs: _addrinfo("127.0.0.1"),
    )
    result = await vision.analyze_images(["http://127.0.0.1/secret.png"], "prompt")
    assert "error" in result
    assert "json" not in captured


@pytest.mark.asyncio
async def test_local_image_size_limit(monkeypatch, tmp_path):
    _fake_settings(monkeypatch)
    monkeypatch.setattr(vision, "_MAX_IMAGE_BYTES", 4)
    path = tmp_path / "big.png"
    path.write_bytes(b"12345")
    _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))
    result = await vision.analyze_images([str(path)], "prompt")
    assert "byte limit" in result["error"]


@pytest.mark.asyncio
async def test_local_images_share_an_aggregate_size_limit(monkeypatch, tmp_path):
    _fake_settings(monkeypatch)
    monkeypatch.setattr(vision, "_MAX_TOTAL_IMAGE_BYTES", 4)
    first = tmp_path / "one.png"
    second = tmp_path / "two.png"
    first.write_bytes(b"abc")
    second.write_bytes(b"def")
    captured = _install_client(monkeypatch, FakeResponse(payload=_chat_payload("ok")))

    result = await vision.analyze_images([str(first), str(second)], "prompt")

    assert "total limit" in result["error"]
    assert "json" not in captured


def test_image_understand_signature_and_defaults():
    params = inspect.signature(understand_tool.image_understand).parameters
    assert list(params) == ["images", "prompt", "model_name"]
    assert params["prompt"].default == "Describe the image in detail."
    assert params["model_name"].default is None


@pytest.mark.asyncio
async def test_image_understand_delegates_with_default_prompt(monkeypatch):
    captured = {}

    async def fake_analyze(images, prompt, model_name=None):
        captured["args"] = (images, prompt, model_name)
        return {"text": "description", "model": "m"}

    monkeypatch.setattr(understand_tool, "analyze_images", fake_analyze)
    result = await understand_tool.image_understand(["https://example.com/a.png"])
    assert result == {"text": "description", "model": "m"}
    assert captured["args"] == (
        ["https://example.com/a.png"],
        "Describe the image in detail.",
        None,
    )


@pytest.mark.asyncio
async def test_image_understand_passes_overrides(monkeypatch):
    captured = {}

    async def fake_analyze(images, prompt, model_name=None):
        captured["args"] = (images, prompt, model_name)
        return {"error": "nope"}

    monkeypatch.setattr(understand_tool, "analyze_images", fake_analyze)
    result = await understand_tool.image_understand(
        ["local.png"], "custom prompt", "custom-model"
    )
    assert result == {"error": "nope"}
    assert captured["args"] == (["local.png"], "custom prompt", "custom-model")


def test_ocr_signature_and_defaults():
    params = inspect.signature(ocr_tool.ocr).parameters
    assert list(params) == ["image", "language", "model_name"]
    assert params["language"].default == "auto"
    assert params["model_name"].default is None


@pytest.mark.asyncio
async def test_ocr_auto_language(monkeypatch):
    captured = {}

    async def fake_analyze(images, prompt, model_name=None):
        captured["args"] = (images, prompt, model_name)
        return {"text": "line one\nline two", "model": "m"}

    monkeypatch.setattr(ocr_tool, "analyze_images", fake_analyze)
    result = await ocr_tool.ocr("page.png")
    assert result == {
        "text": "line one\nline two",
        "language": "auto",
        "model": "m",
    }
    assert captured["args"][0] == ["page.png"]
    assert "Transcribe all text" in captured["args"][1]
    assert "preserving line breaks" in captured["args"][1]
    assert "expected to be in" not in captured["args"][1]


@pytest.mark.asyncio
async def test_ocr_requested_language(monkeypatch):
    captured = {}

    async def fake_analyze(images, prompt, model_name=None):
        captured["prompt"] = prompt
        return {"text": "", "model": "m"}

    monkeypatch.setattr(ocr_tool, "analyze_images", fake_analyze)
    result = await ocr_tool.ocr("page.png", language="Chinese", model_name="vision")
    assert result == {"text": "", "language": "Chinese", "model": "m"}
    assert "expected to be in Chinese" in captured["prompt"]


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["auto", "AUTO", None])
async def test_ocr_auto_variants(monkeypatch, language):
    captured = {}

    async def fake_analyze(images, prompt, model_name=None):
        captured["prompt"] = prompt
        return {"text": "x", "model": "m"}

    monkeypatch.setattr(ocr_tool, "analyze_images", fake_analyze)
    result = await ocr_tool.ocr("page.png", language=language)
    assert result["language"] == language
    assert "expected to be in" not in captured["prompt"]


@pytest.mark.asyncio
async def test_ocr_error_passthrough(monkeypatch):
    async def fake_analyze(images, prompt, model_name=None):
        return {"error": "boom"}

    monkeypatch.setattr(ocr_tool, "analyze_images", fake_analyze)
    result = await ocr_tool.ocr("page.png")
    assert result == {"error": "boom"}
