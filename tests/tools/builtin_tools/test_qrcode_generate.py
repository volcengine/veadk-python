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

"""Hermetic tests for the ``qrcode_generate`` built-in tool."""

import inspect
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from veadk.tools.builtin_tools import qrcode_generate as tool

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class FakeToolContext:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.saved: list[tuple[str, object]] = []

    async def save_artifact(self, filename: str, artifact: object) -> int:
        if self.fail:
            raise RuntimeError("artifact store unavailable")
        self.saved.append((filename, artifact))
        return 1


def test_signature_and_defaults():
    params = inspect.signature(tool.qrcode_generate).parameters
    assert list(params) == [
        "content",
        "filename",
        "box_size",
        "border",
        "fill_color",
        "back_color",
        "tool_context",
    ]
    assert params["filename"].default == "qrcode.png"
    assert params["box_size"].default == 10
    assert params["border"].default == 4
    assert params["fill_color"].default == "black"
    assert params["back_color"].default == "white"
    assert params["tool_context"].default is None


@pytest.mark.asyncio
async def test_generates_real_png_temp_file():
    result = await tool.qrcode_generate("hello world", box_size=2, border=1)
    path = Path(result["path"])
    assert result["artifact_saved"] is False
    assert result["format"] == "png"
    assert result["mime_type"] == "image/png"
    assert result["filename"] == "qrcode.png"
    assert path.is_file()
    data = path.read_bytes()
    assert data.startswith(PNG_MAGIC)
    assert result["size_bytes"] == len(data)
    with Image.open(BytesIO(data)) as image:
        assert image.format == "PNG"
        assert image.size == (result["width"], result["height"])
        assert result["width"] == result["height"]
        assert result["width"] > 2 * 1 * 2 + 2 * 2


@pytest.mark.asyncio
async def test_custom_colors_and_dimensions():
    result = await tool.qrcode_generate(
        "https://example.com",
        box_size=5,
        border=2,
        fill_color="#102030",
        back_color="#ffffff",
    )
    assert "error" not in result
    with Image.open(result["path"]) as image:
        assert image.size == (result["width"], result["height"])


@pytest.mark.asyncio
async def test_artifact_saving():
    context = FakeToolContext()
    result = await tool.qrcode_generate(
        "artifact payload", filename="My Code!!.jpg", tool_context=context
    )
    assert result["artifact_saved"] is True
    assert result["path"] is None
    assert result["filename"] == "My-Code.png"
    filename, artifact = context.saved[0]
    assert filename == "My-Code.png"
    assert artifact.inline_data.mime_type == "image/png"
    assert artifact.inline_data.display_name == "My-Code.png"
    assert artifact.inline_data.data.startswith(PNG_MAGIC)


@pytest.mark.asyncio
async def test_artifact_failure_returns_error():
    result = await tool.qrcode_generate(
        "payload", tool_context=FakeToolContext(fail=True)
    )
    assert "artifact store unavailable" in result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"content": ""}, "content"),
        ({"content": "   "}, "content"),
        ({"content": 123}, "content"),
        ({"content": "x" * 2001}, "2000"),
        ({"content": "x", "box_size": 0}, "box_size"),
        ({"content": "x", "box_size": 51}, "box_size"),
        ({"content": "x", "box_size": 1.5}, "box_size"),
        ({"content": "x", "box_size": True}, "box_size"),
        ({"content": "x", "border": -1}, "border"),
        ({"content": "x", "border": 21}, "border"),
        ({"content": "x", "border": True}, "border"),
        ({"content": "x", "fill_color": 5}, "fill_color"),
        ({"content": "x", "back_color": None}, "back_color"),
        ({"content": "x", "fill_color": "notacolor"}, "color"),
    ],
)
async def test_validation_errors(kwargs, fragment):
    result = await tool.qrcode_generate(**kwargs)
    assert "error" in result
    assert fragment.lower() in result["error"].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("../../code", "code.png"),
        ("code.jpg", "code.png"),
        ("", "qrcode.png"),
        ("code", "code.png"),
    ],
)
async def test_filename_sanitization(filename, expected):
    result = await tool.qrcode_generate("payload", filename=filename)
    assert result["filename"] == expected
