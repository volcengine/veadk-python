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

"""Transform a local or remote image with Pillow and save the result."""

from __future__ import annotations

import asyncio
import math
import os
import re
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from google.adk.tools import ToolContext
from google.genai import types
from PIL import Image, ImageOps

from veadk.tools.builtin_tools.web_fetch import assert_public_url

_MAX_OPERATIONS = 20
_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
# Pillow's decompression-bomb guard only protects input decoding; upscaling via
# resize/rotate allocates the output bitmap directly, so bound it explicitly.
_MAX_OUTPUT_PIXELS = 40_000_000
_MAX_REDIRECTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 30
_USER_AGENT = "VeADK-ImageTransform/1.0"

# format -> (Pillow format, file extension, MIME type)
_FORMATS: dict[str, tuple[str, str, str]] = {
    "png": ("PNG", "png", "image/png"),
    "jpeg": ("JPEG", "jpg", "image/jpeg"),
    "webp": ("WEBP", "webp", "image/webp"),
}


def _normalize_format(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("format must be one of: png, jpeg, webp")
    normalized = value.strip().lower()
    if normalized == "jpg":
        normalized = "jpeg"
    if normalized not in _FORMATS:
        raise ValueError("format must be one of: png, jpeg, webp")
    return normalized


def _detect_source_format(image: Image.Image) -> str:
    source_format = (image.format or "").lower()
    if source_format == "jpg":
        source_format = "jpeg"
    return source_format if source_format in _FORMATS else "png"


def _safe_filename(filename: str | None, extension: str) -> str:
    value = Path(filename.strip()).name if isinstance(filename, str) else ""
    stem = Path(value).stem if value else "image"
    stem = re.sub(r"[^\w一-鿿.-]+", "-", stem).strip("-._")[:100]
    return f"{stem or 'image'}.{extension}"


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    return float(value)


async def _download_url(url: str) -> bytes:
    current = url
    redirects = 0
    headers = {"User-Agent": _USER_AGENT}
    async with httpx.AsyncClient(
        timeout=_DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=False
    ) as client:
        while True:
            # DNS resolution blocks; keep it off the event loop.
            await asyncio.to_thread(assert_public_url, current)
            async with client.stream("GET", current, headers=headers) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("redirect response did not include a location")
                    if redirects >= _MAX_REDIRECTS:
                        raise ValueError(f"too many redirects (>{_MAX_REDIRECTS})")
                    current = urljoin(current, location)
                    redirects += 1
                    continue
                if response.status_code >= 400:
                    raise ValueError(
                        f"failed to download image: HTTP {response.status_code}"
                    )
                declared_length = response.headers.get("content-length")
                if declared_length is not None:
                    try:
                        declared_bytes = int(declared_length)
                    except (TypeError, ValueError):
                        declared_bytes = 0
                    if declared_bytes > _MAX_DOWNLOAD_BYTES:
                        raise ValueError(
                            f"image exceeds the {_MAX_DOWNLOAD_BYTES} byte limit"
                        )
                # Stream with a hard cap: Content-Length is advisory and may be
                # absent or wrong, so never buffer an unbounded response.
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > _MAX_DOWNLOAD_BYTES:
                        raise ValueError(
                            f"image exceeds the {_MAX_DOWNLOAD_BYTES} byte limit"
                        )
                    chunks.append(chunk)
                return b"".join(chunks)


async def _read_source(source: str) -> bytes:
    if "://" in source:
        parsed = urlparse(source)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("only http(s) URLs are supported")
        return await _download_url(source)
    path = Path(source)
    if not path.is_file():
        raise ValueError(f"image file does not exist: {source}")
    # Match the download cap so a huge local file cannot exhaust memory.
    with path.open("rb") as handle:
        data = handle.read(_MAX_DOWNLOAD_BYTES + 1)
    if len(data) > _MAX_DOWNLOAD_BYTES:
        raise ValueError(f"image exceeds the {_MAX_DOWNLOAD_BYTES} byte limit")
    return data


def _load_image(data: bytes) -> Image.Image:
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except Exception as e:
        raise ValueError(f"unable to decode image: {e}") from e
    return image


def _normalize_mode(image: Image.Image) -> Image.Image:
    has_alpha = (
        "A" in image.getbands()
        or image.mode in ("RGBA", "LA")
        or (image.mode == "P" and "transparency" in image.info)
    )
    return image.convert("RGBA" if has_alpha else "RGB")


def _check_output_size(width: int, height: int) -> None:
    """Reject outputs whose bitmap would be unreasonably large."""
    if width * height <= _MAX_OUTPUT_PIXELS:
        return
    raise ValueError(
        f"output image would be {width}x{height} ({width * height} pixels), "
        f"exceeding the {_MAX_OUTPUT_PIXELS} pixel limit"
    )


def _rotated_size(width: int, height: int, degrees: float) -> tuple[int, int]:
    """Predicted canvas size of ``rotate(expand=True)`` without allocating it."""
    angle = math.radians(degrees % 360.0)
    cos = abs(math.cos(angle))
    sin = abs(math.sin(angle))
    # Truncate float noise (cos(90°) is 6e-17, not 0) before rounding up.
    return (
        max(1, math.ceil(width * cos + height * sin - 1e-9)),
        max(1, math.ceil(width * sin + height * cos - 1e-9)),
    )


def _op_resize(image: Image.Image, operation: dict) -> Image.Image:
    width_value = operation.get("width")
    height_value = operation.get("height")
    if width_value is None and height_value is None:
        raise ValueError("resize requires width and/or height")
    width = None if width_value is None else _positive_int(width_value, "width")
    height = None if height_value is None else _positive_int(height_value, "height")
    keep_aspect = operation.get("keep_aspect", True)
    if not isinstance(keep_aspect, bool):
        raise ValueError("keep_aspect must be a boolean")
    if width is None:
        width = max(1, round(image.width * height / image.height))
        _check_output_size(width, height)
        return image.resize((width, height))
    if height is None:
        height = max(1, round(image.height * width / image.width))
        _check_output_size(width, height)
        return image.resize((width, height))
    _check_output_size(width, height)
    if keep_aspect:
        return ImageOps.contain(image, (width, height))
    return image.resize((width, height))


def _op_crop(image: Image.Image, operation: dict) -> Image.Image:
    left = _integer(operation.get("left"), "left")
    top = _integer(operation.get("top"), "top")
    right = _integer(operation.get("right"), "right")
    bottom = _integer(operation.get("bottom"), "bottom")
    if (
        left < 0
        or top < 0
        or right > image.width
        or bottom > image.height
        or left >= right
        or top >= bottom
    ):
        raise ValueError("crop box must be inside the image bounds")
    return image.crop((left, top, right, bottom))


def _op_rotate(image: Image.Image, operation: dict) -> Image.Image:
    degrees = _number(operation.get("degrees"), "degrees")
    # Check the expanded canvas before Pillow allocates it.
    _check_output_size(*_rotated_size(image.width, image.height, degrees))
    fill = (0, 0, 0, 0) if image.mode == "RGBA" else "white"
    return image.rotate(degrees, expand=True, fillcolor=fill)


def _op_flip(image: Image.Image, operation: dict) -> Image.Image:
    direction = operation.get("direction")
    if not isinstance(direction, str):
        raise ValueError("flip direction must be 'horizontal' or 'vertical'")
    if direction.strip().lower() == "horizontal":
        return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if direction.strip().lower() == "vertical":
        return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    raise ValueError("flip direction must be 'horizontal' or 'vertical'")


def _op_thumbnail(image: Image.Image, operation: dict) -> Image.Image:
    max_size = _positive_int(operation.get("max_size"), "max_size")
    image.thumbnail((max_size, max_size))
    return image


def _apply_operations(
    image: Image.Image, operations: list[dict]
) -> tuple[Image.Image, str | None]:
    format_override: str | None = None
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError("each operation must be a dict")
        operation_type = operation.get("type")
        if not isinstance(operation_type, str):
            raise ValueError("each operation requires a string 'type'")
        operation_type = operation_type.strip().lower()
        if operation_type == "resize":
            image = _op_resize(image, operation)
        elif operation_type == "crop":
            image = _op_crop(image, operation)
        elif operation_type == "rotate":
            image = _op_rotate(image, operation)
        elif operation_type == "flip":
            image = _op_flip(image, operation)
        elif operation_type == "thumbnail":
            image = _op_thumbnail(image, operation)
        elif operation_type == "grayscale":
            image = image.convert("L")
        elif operation_type == "convert":
            format_override = _normalize_format(operation.get("format"))
        else:
            raise ValueError(f"unsupported operation type: {operation_type!r}")
    return image, format_override


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if "A" in image.getbands() or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def _encode_image(image: Image.Image, image_format: str, quality: int) -> bytes:
    pillow_format = _FORMATS[image_format][0]
    if image_format == "jpeg":
        image = _flatten_to_rgb(image)
    params: dict[str, object] = {}
    if image_format in ("jpeg", "webp"):
        params["quality"] = quality
    buffer = BytesIO()
    image.save(buffer, format=pillow_format, **params)
    return buffer.getvalue()


def _write_temp_file(data: bytes, extension: str) -> str:
    file_descriptor, path = tempfile.mkstemp(
        prefix="veadk-image-", suffix=f".{extension}"
    )
    with os.fdopen(file_descriptor, "wb") as handle:
        handle.write(data)
    return path


async def image_transform(
    source: str,
    operations: list[dict],
    output_format: str | None = None,
    quality: int = 90,
    filename: str | None = None,
    tool_context: ToolContext | None = None,
) -> dict:
    """Apply ordered Pillow operations to an image and save the result.

    ``source`` may be a local path or an http(s) URL. Operations are applied in
    order; each item is a dict with a ``type``:

    - ``resize``: ``width`` and/or ``height`` (positive ints). When only one
      side is given the aspect ratio is preserved. With both sides and
      ``keep_aspect`` true (default) the image fits inside the box. The output
      canvas may not exceed 40,000,000 pixels.
    - ``crop``: ``left``, ``top``, ``right``, ``bottom`` pixel coordinates.
    - ``rotate``: ``degrees`` (float), expanding the canvas and filling with
      white (RGB) or transparency (RGBA); the expanded canvas is subject to the
      same pixel limit.
    - ``flip``: ``direction`` equal to ``horizontal`` or ``vertical``.
    - ``thumbnail``: ``max_size`` (positive int), preserving aspect ratio.
    - ``grayscale``: converts the image to grayscale.
    - ``convert``: ``format`` of ``png``, ``jpeg`` or ``webp``; the output
      format is applied after every operation.

    Args:
        source: Local image path or public http(s) URL.
        operations: Ordered list of operation dicts (at most 20).
        output_format: png, jpeg or webp. Defaults to the source format when it
            is png/jpeg/webp, otherwise png.
        quality: Encoder quality from 1 to 100 for jpeg/webp only.
        filename: Optional output filename; sanitized with the right extension.
        tool_context: Current ADK tool context used to save the result artifact.

    Returns:
        A dict with filename, format, width, height, size_bytes, mime_type,
        artifact_saved and path. On failure, a dict with an ``error`` key.
    """
    try:
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source is required")
        if not isinstance(operations, list):
            raise ValueError("operations must be a list")
        if not operations:
            raise ValueError("operations must not be empty")
        if len(operations) > _MAX_OPERATIONS:
            raise ValueError(f"at most {_MAX_OPERATIONS} operations are allowed")
        if isinstance(quality, bool) or not isinstance(quality, int):
            raise ValueError("quality must be an integer between 1 and 100")
        if not 1 <= quality <= 100:
            raise ValueError("quality must be an integer between 1 and 100")

        data = await _read_source(source.strip())
        image = _load_image(data)
        source_format = _detect_source_format(image)
        image = _normalize_mode(image)
        image, format_override = _apply_operations(image, operations)

        if output_format is not None:
            image_format = _normalize_format(output_format)
        elif format_override is not None:
            image_format = format_override
        else:
            image_format = source_format

        _, extension, mime_type = _FORMATS[image_format]
        artifact_name = _safe_filename(filename, extension)
        encoded = _encode_image(image, image_format, quality)

        result: dict[str, object] = {
            "filename": artifact_name,
            "format": image_format,
            "width": image.width,
            "height": image.height,
            "size_bytes": len(encoded),
            "mime_type": mime_type,
            "artifact_saved": False,
            "path": None,
        }
        if tool_context is None:
            result["path"] = _write_temp_file(encoded, extension)
        else:
            artifact = types.Part.from_bytes(data=encoded, mime_type=mime_type)
            if artifact.inline_data is not None:
                artifact.inline_data.display_name = artifact_name
            await tool_context.save_artifact(artifact_name, artifact)
            result["artifact_saved"] = True
        return result
    except Exception as e:
        return {"error": str(e)}


__all__ = ["image_transform"]
