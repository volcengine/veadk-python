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

"""Hermetic tests for the ``image_transform`` built-in tool."""

import inspect
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from veadk.tools.builtin_tools import image_transform as tool

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_bytes(size=(4, 4), mode="RGB", color=(255, 0, 0)) -> bytes:
    buffer = BytesIO()
    Image.new(mode, size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _save(tmp_path: Path, name: str, size=(40, 20), mode="RGB", color=(255, 0, 0)):
    path = tmp_path / name
    Image.new(mode, size, color).save(path)
    return str(path)


class FakeToolContext:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.saved: list[tuple[str, object]] = []

    async def save_artifact(self, filename: str, artifact: object) -> int:
        if self.fail:
            raise RuntimeError("artifact store unavailable")
        self.saved.append((filename, artifact))
        return 1


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
        headers: dict | None = None,
        is_redirect: bool = False,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.is_redirect = is_redirect

    async def aiter_bytes(self):
        # Yield an empty chunk first: HTTP clients may do this, and the
        # bounded reader must skip it rather than treat it as data.
        yield b""
        for index in range(0, len(self.content), 4):
            yield self.content[index : index + 4]


class FakeStream:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    async def __aenter__(self) -> FakeResponse:
        return self.response

    async def __aexit__(self, *exc_info) -> bool:
        return False


def _install_http(monkeypatch, responses):
    captured: dict[str, object] = {"client_kwargs": [], "requests": []}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured["client_kwargs"].append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        def stream(self, method, url, headers=None):
            captured["requests"].append(
                {"method": method, "url": url, "headers": headers}
            )
            return FakeStream(responses.pop(0))

    monkeypatch.setattr(tool.httpx, "AsyncClient", FakeClient)
    return captured


def _allow_public(monkeypatch):
    validated: list[str] = []

    def fake_assert(url: str) -> str:
        validated.append(url)
        return "example.com"

    monkeypatch.setattr(tool, "assert_public_url", fake_assert)
    return validated


def test_signature_and_defaults():
    params = inspect.signature(tool.image_transform).parameters
    assert list(params) == [
        "source",
        "operations",
        "output_format",
        "quality",
        "filename",
        "tool_context",
    ]
    assert params["output_format"].default is None
    assert params["quality"].default == 90
    assert params["filename"].default is None
    assert params["tool_context"].default is None


@pytest.mark.asyncio
async def test_resize_both_dimensions_keeps_aspect(tmp_path):
    source = _save(tmp_path, "source.png", size=(40, 20))
    result = await tool.image_transform(
        source, [{"type": "resize", "width": 20, "height": 20}]
    )
    assert result["width"] == 20
    assert result["height"] == 10
    assert Path(result["path"]).is_file()


@pytest.mark.asyncio
async def test_resize_single_dimension_preserves_aspect(tmp_path):
    source = _save(tmp_path, "source.png", size=(40, 20))
    by_width = await tool.image_transform(source, [{"type": "resize", "width": 10}])
    assert (by_width["width"], by_width["height"]) == (10, 5)
    by_height = await tool.image_transform(source, [{"type": "resize", "height": 10}])
    assert (by_height["width"], by_height["height"]) == (20, 10)


@pytest.mark.asyncio
async def test_resize_keep_aspect_false_distorts(tmp_path):
    source = _save(tmp_path, "source.png", size=(40, 20))
    result = await tool.image_transform(
        source,
        [{"type": "resize", "width": 10, "height": 3, "keep_aspect": False}],
    )
    assert (result["width"], result["height"]) == (10, 3)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [
        {"type": "resize"},
        {"type": "resize", "width": 0},
        {"type": "resize", "width": -3},
        {"type": "resize", "width": True},
        {"type": "resize", "width": 10, "keep_aspect": "yes"},
    ],
)
async def test_resize_validation(tmp_path, operation):
    source = _save(tmp_path, "source.png")
    result = await tool.image_transform(source, [operation])
    assert "error" in result


@pytest.mark.asyncio
async def test_crop(tmp_path):
    source = _save(tmp_path, "source.png", size=(10, 10))
    result = await tool.image_transform(
        source,
        [{"type": "crop", "left": 1, "top": 2, "right": 9, "bottom": 8}],
    )
    assert (result["width"], result["height"]) == (8, 6)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [
        {"type": "crop", "left": 0, "top": 0, "right": 20, "bottom": 10},
        {"type": "crop", "left": 5, "top": 0, "right": 5, "bottom": 10},
        {"type": "crop", "left": -1, "top": 0, "right": 5, "bottom": 10},
        {"type": "crop", "left": 0, "top": 0, "right": 5},
        {"type": "crop", "left": "0", "top": 0, "right": 5, "bottom": 5},
    ],
)
async def test_crop_validation(tmp_path, operation):
    source = _save(tmp_path, "source.png", size=(10, 10))
    result = await tool.image_transform(source, [operation])
    assert "error" in result


@pytest.mark.asyncio
async def test_rotate_rgb_fills_white(tmp_path):
    source = _save(tmp_path, "source.png", size=(10, 5))
    result = await tool.image_transform(source, [{"type": "rotate", "degrees": 45}])
    assert result["width"] > 10
    assert result["height"] > 5
    with Image.open(result["path"]) as image:
        assert image.getpixel((0, 0)) == (255, 255, 255)


@pytest.mark.asyncio
async def test_rotate_rgba_fills_transparent(tmp_path):
    source = _save(
        tmp_path, "source.png", size=(10, 5), mode="RGBA", color=(0, 0, 255, 255)
    )
    result = await tool.image_transform(source, [{"type": "rotate", "degrees": 45}])
    with Image.open(result["path"]) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0))[3] == 0


@pytest.mark.asyncio
async def test_rotate_validation(tmp_path):
    source = _save(tmp_path, "source.png")
    for degrees in (None, "90", True):
        result = await tool.image_transform(
            source, [{"type": "rotate", "degrees": degrees}]
        )
        assert "error" in result


@pytest.mark.asyncio
async def test_flip_horizontal(tmp_path):
    path = tmp_path / "split.png"
    image = Image.new("RGB", (4, 2), (255, 0, 0))
    image.paste((0, 0, 255), (2, 0, 4, 2))
    image.save(path)
    result = await tool.image_transform(
        str(path), [{"type": "flip", "direction": "horizontal"}]
    )
    with Image.open(result["path"]) as flipped:
        assert flipped.getpixel((0, 0)) == (0, 0, 255)


@pytest.mark.asyncio
async def test_flip_vertical(tmp_path):
    path = tmp_path / "split.png"
    image = Image.new("RGB", (2, 4), (255, 0, 0))
    image.paste((0, 0, 255), (0, 2, 2, 4))
    image.save(path)
    result = await tool.image_transform(
        str(path), [{"type": "flip", "direction": "vertical"}]
    )
    with Image.open(result["path"]) as flipped:
        assert flipped.getpixel((0, 0)) == (0, 0, 255)


@pytest.mark.asyncio
@pytest.mark.parametrize("direction", ["diagonal", None, 3])
async def test_flip_validation(tmp_path, direction):
    source = _save(tmp_path, "source.png")
    result = await tool.image_transform(
        source, [{"type": "flip", "direction": direction}]
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_thumbnail_preserves_aspect(tmp_path):
    source = _save(tmp_path, "source.png", size=(100, 50))
    result = await tool.image_transform(source, [{"type": "thumbnail", "max_size": 20}])
    assert (result["width"], result["height"]) == (20, 10)


@pytest.mark.asyncio
@pytest.mark.parametrize("max_size", [0, -1, True, "20"])
async def test_thumbnail_validation(tmp_path, max_size):
    source = _save(tmp_path, "source.png")
    result = await tool.image_transform(
        source, [{"type": "thumbnail", "max_size": max_size}]
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_grayscale_to_jpeg(tmp_path):
    source = _save(tmp_path, "source.png", mode="RGB")
    result = await tool.image_transform(
        source,
        [{"type": "grayscale"}, {"type": "convert", "format": "jpeg"}],
    )
    assert result["format"] == "jpeg"
    assert result["filename"] == "image.jpg"
    with Image.open(result["path"]) as image:
        assert image.mode == "RGB"


@pytest.mark.asyncio
async def test_convert_operation_applies_at_end(tmp_path):
    source = _save(tmp_path, "source.png")
    result = await tool.image_transform(
        source,
        [{"type": "resize", "width": 20}, {"type": "convert", "format": "webp"}],
    )
    assert result["format"] == "webp"
    assert result["mime_type"] == "image/webp"
    assert result["filename"] == "image.webp"
    assert Path(result["path"]).read_bytes().startswith(b"RIFF")


@pytest.mark.asyncio
async def test_output_format_parameter_wins_over_convert(tmp_path):
    source = _save(tmp_path, "source.png")
    result = await tool.image_transform(
        source,
        [{"type": "convert", "format": "webp"}],
        output_format="png",
    )
    assert result["format"] == "png"


@pytest.mark.asyncio
async def test_output_format_defaults_to_jpeg_source(tmp_path):
    source = _save(tmp_path, "source.jpg")
    result = await tool.image_transform(source, [{"type": "grayscale"}])
    assert result["format"] == "jpeg"
    assert result["mime_type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_output_format_defaults_to_png_for_other_sources(tmp_path):
    path = tmp_path / "source.bmp"
    Image.new("RGB", (4, 4), (1, 2, 3)).save(path, format="BMP")
    result = await tool.image_transform(str(path), [{"type": "grayscale"}])
    assert result["format"] == "png"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_format", ["gif", "JPG2", "", 3])
async def test_output_format_validation(tmp_path, bad_format):
    source = _save(tmp_path, "source.png")
    result = await tool.image_transform(
        source, [{"type": "grayscale"}], output_format=bad_format
    )
    assert "error" in result


@pytest.mark.asyncio
@pytest.mark.parametrize("quality", [0, 101, True, "90"])
async def test_quality_validation(tmp_path, quality):
    source = _save(tmp_path, "source.png")
    result = await tool.image_transform(
        source, [{"type": "grayscale"}], quality=quality
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_quality_only_affects_jpeg_and_webp(tmp_path):
    source = _save(tmp_path, "source.png", size=(32, 32))
    low = await tool.image_transform(
        source, [{"type": "grayscale"}], output_format="jpeg", quality=1
    )
    high = await tool.image_transform(
        source, [{"type": "grayscale"}], output_format="jpeg", quality=100
    )
    assert low["size_bytes"] < high["size_bytes"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operations",
    [
        "not-a-list",
        [],
        [{"type": "grayscale"}] * 21,
        [{"type": "unknown"}],
        ["not-a-dict"],
        [{"width": 10}],
        [{"type": 3}],
        [{"type": "convert", "format": "gif"}],
        [{"type": "convert", "format": None}],
    ],
)
async def test_operation_validation(tmp_path, operations):
    source = _save(tmp_path, "source.png")
    result = await tool.image_transform(source, operations)
    assert "error" in result


@pytest.mark.asyncio
async def test_invalid_source_inputs(tmp_path):
    assert "error" in await tool.image_transform("", [{"type": "grayscale"}])
    assert "error" in await tool.image_transform(123, [{"type": "grayscale"}])  # type: ignore[arg-type]
    missing = tmp_path / "missing.png"
    assert "error" in await tool.image_transform(str(missing), [{"type": "grayscale"}])
    assert "error" in await tool.image_transform(str(tmp_path), [{"type": "grayscale"}])
    assert "error" in await tool.image_transform(
        "ftp://example.com/a.png", [{"type": "grayscale"}]
    )


@pytest.mark.asyncio
async def test_invalid_image_bytes(tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(b"not an image")
    result = await tool.image_transform(str(path), [{"type": "grayscale"}])
    assert "error" in result
    assert "decode" in result["error"]


@pytest.mark.asyncio
async def test_palette_transparency_becomes_rgba(tmp_path):
    path = tmp_path / "palette.png"
    image = Image.new("P", (4, 4), 0)
    image.putpalette([0, 0, 0, 255, 255, 255] + [0, 0, 0] * 254)
    image.info["transparency"] = 0
    image.save(path, format="PNG")
    result = await tool.image_transform(str(path), [{"type": "grayscale"}])
    with Image.open(result["path"]) as output:
        assert output.mode == "L"


@pytest.mark.asyncio
async def test_url_download_success(tmp_path, monkeypatch):
    validated = _allow_public(monkeypatch)
    captured = _install_http(
        monkeypatch, [FakeResponse(content=_png_bytes(size=(8, 4)))]
    )
    result = await tool.image_transform(
        "https://example.com/image.png", [{"type": "grayscale"}]
    )
    assert validated == ["https://example.com/image.png"]
    assert result["width"] == 8
    assert result["height"] == 4
    assert captured["client_kwargs"][0]["follow_redirects"] is False
    assert captured["requests"][0]["headers"]["User-Agent"].startswith("VeADK")


@pytest.mark.asyncio
async def test_url_redirect_revalidates_each_hop(monkeypatch):
    validated = _allow_public(monkeypatch)
    _install_http(
        monkeypatch,
        [
            FakeResponse(
                status_code=302,
                headers={"location": "https://cdn.example.com/image.png"},
                is_redirect=True,
            ),
            FakeResponse(content=_png_bytes()),
        ],
    )
    result = await tool.image_transform(
        "https://example.com/image.png", [{"type": "grayscale"}]
    )
    assert "error" not in result
    assert validated == [
        "https://example.com/image.png",
        "https://cdn.example.com/image.png",
    ]


@pytest.mark.asyncio
async def test_url_too_many_redirects(monkeypatch):
    _allow_public(monkeypatch)
    redirect = FakeResponse(
        status_code=302,
        headers={"location": "https://example.com/next"},
        is_redirect=True,
    )
    _install_http(monkeypatch, [redirect, redirect, redirect, redirect])
    result = await tool.image_transform(
        "https://example.com/image.png", [{"type": "grayscale"}]
    )
    assert "too many redirects" in result["error"]


@pytest.mark.asyncio
async def test_url_redirect_without_location(monkeypatch):
    _allow_public(monkeypatch)
    _install_http(monkeypatch, [FakeResponse(status_code=302, is_redirect=True)])
    result = await tool.image_transform(
        "https://example.com/image.png", [{"type": "grayscale"}]
    )
    assert "location" in result["error"]


@pytest.mark.asyncio
async def test_url_http_error(monkeypatch):
    _allow_public(monkeypatch)
    _install_http(monkeypatch, [FakeResponse(status_code=404)])
    result = await tool.image_transform(
        "https://example.com/image.png", [{"type": "grayscale"}]
    )
    assert "HTTP 404" in result["error"]


@pytest.mark.asyncio
async def test_url_declared_size_limit(monkeypatch):
    _allow_public(monkeypatch)
    monkeypatch.setattr(tool, "_MAX_DOWNLOAD_BYTES", 10)
    _install_http(monkeypatch, [FakeResponse(headers={"content-length": "11"})])
    result = await tool.image_transform(
        "https://example.com/image.png", [{"type": "grayscale"}]
    )
    assert "byte limit" in result["error"]


@pytest.mark.asyncio
async def test_url_actual_size_limit(monkeypatch):
    _allow_public(monkeypatch)
    monkeypatch.setattr(tool, "_MAX_DOWNLOAD_BYTES", 10)
    _install_http(monkeypatch, [FakeResponse(content=b"x" * 11)])
    result = await tool.image_transform(
        "https://example.com/image.png", [{"type": "grayscale"}]
    )
    assert "byte limit" in result["error"]


@pytest.mark.asyncio
async def test_url_invalid_content_length_falls_back(monkeypatch):
    _allow_public(monkeypatch)
    _install_http(
        monkeypatch,
        [FakeResponse(content=_png_bytes(), headers={"content-length": "abc"})],
    )
    result = await tool.image_transform(
        "https://example.com/image.png", [{"type": "grayscale"}]
    )
    assert "error" not in result


@pytest.mark.asyncio
async def test_artifact_saving(tmp_path):
    source = _save(tmp_path, "source.png", size=(6, 3))
    context = FakeToolContext()
    result = await tool.image_transform(
        source,
        [{"type": "grayscale"}],
        filename="out!!.png",
        tool_context=context,
    )
    assert result["artifact_saved"] is True
    assert result["path"] is None
    assert result["filename"] == "out.png"
    assert result["mime_type"] == "image/png"
    filename, artifact = context.saved[0]
    assert filename == "out.png"
    assert artifact.inline_data.mime_type == "image/png"
    assert artifact.inline_data.display_name == "out.png"
    assert artifact.inline_data.data.startswith(PNG_MAGIC)


@pytest.mark.asyncio
async def test_artifact_failure_returns_error(tmp_path):
    source = _save(tmp_path, "source.png")
    result = await tool.image_transform(
        source,
        [{"type": "grayscale"}],
        tool_context=FakeToolContext(fail=True),
    )
    assert "artifact store unavailable" in result["error"]


@pytest.mark.asyncio
async def test_temp_file_path_when_no_context(tmp_path):
    source = _save(tmp_path, "source.png")
    result = await tool.image_transform(source, [{"type": "grayscale"}])
    path = Path(result["path"])
    assert result["artifact_saved"] is False
    assert path.is_file()
    assert path.name.endswith(".png")
    assert path.read_bytes().startswith(PNG_MAGIC)
    assert result["size_bytes"] == path.stat().st_size


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "output_format", "expected"),
    [
        ("../../evil", None, "evil.png"),
        ("photo.jpeg", "png", "photo.png"),
        ("my photo!!.webp", "webp", "my-photo.webp"),
        ("", None, "image.png"),
        (None, None, "image.png"),
    ],
)
async def test_filename_sanitization(tmp_path, filename, output_format, expected):
    source = _save(tmp_path, "source.png")
    result = await tool.image_transform(
        source,
        [{"type": "grayscale"}],
        output_format=output_format,
        filename=filename,
    )
    assert result["filename"] == expected


@pytest.mark.asyncio
async def test_jpg_format_alias(tmp_path):
    source = _save(tmp_path, "source.png")
    result = await tool.image_transform(
        source, [{"type": "grayscale"}], output_format="jpg"
    )
    assert result["format"] == "jpeg"
    assert result["filename"] == "image.jpg"


def test_source_format_jpg_alias():
    from types import SimpleNamespace

    assert tool._detect_source_format(SimpleNamespace(format="JPG")) == "jpeg"


@pytest.mark.asyncio
async def test_rgb_image_saved_as_jpeg(tmp_path):
    source = _save(tmp_path, "source.png", mode="RGB")
    result = await tool.image_transform(
        source, [{"type": "thumbnail", "max_size": 20}], output_format="jpeg"
    )
    assert result["format"] == "jpeg"
    with Image.open(result["path"]) as image:
        assert image.mode == "RGB"


@pytest.mark.asyncio
async def test_rgba_image_flattened_for_jpeg(tmp_path):
    source = _save(
        tmp_path, "source.png", size=(8, 8), mode="RGBA", color=(255, 0, 0, 0)
    )
    result = await tool.image_transform(
        source, [{"type": "thumbnail", "max_size": 4}], output_format="jpeg"
    )
    assert result["format"] == "jpeg"
    with Image.open(result["path"]) as image:
        assert image.mode == "RGB"
        # Transparent pixels are composited onto a white background.
        assert image.getpixel((0, 0)) == (255, 255, 255)
