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

"""Generate a QR code image and save it as an ADK artifact."""

from __future__ import annotations

import os
import re
import tempfile
from io import BytesIO
from pathlib import Path

import qrcode
from google.adk.tools import ToolContext
from google.genai import types
from PIL import Image
from qrcode.constants import ERROR_CORRECT_M
from qrcode.image.pil import PilImage

_MAX_CONTENT_LENGTH = 2000
_MAX_BOX_SIZE = 50
_MAX_BORDER = 20
_MIME_TYPE = "image/png"


def _safe_filename(filename: str) -> str:
    value = Path(filename.strip()).name if isinstance(filename, str) else ""
    stem = Path(value).stem if value else "qrcode"
    stem = re.sub(r"[^\w一-鿿.-]+", "-", stem).strip("-._")[:100]
    return f"{stem or 'qrcode'}.png"


def _positive_int_in_range(value: object, name: str, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def _render(content: str, box_size: int, border: int, fill: str, back: str) -> bytes:
    qr = qrcode.QRCode(
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
        image_factory=PilImage,
    )
    qr.add_data(content)
    qr.make(fit=True)
    image = qr.make_image(fill_color=fill, back_color=back).get_image()
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _write_temp_file(data: bytes) -> str:
    file_descriptor, path = tempfile.mkstemp(prefix="veadk-qrcode-", suffix=".png")
    with os.fdopen(file_descriptor, "wb") as handle:
        handle.write(data)
    return path


async def qrcode_generate(
    content: str,
    filename: str = "qrcode.png",
    box_size: int = 10,
    border: int = 4,
    fill_color: str = "black",
    back_color: str = "white",
    tool_context: ToolContext | None = None,
) -> dict:
    """Generate a PNG QR code for text or a URL and save it.

    Args:
        content: Text or URL to encode (non-empty, at most 2000 characters).
        filename: Output filename; a .png extension is enforced.
        box_size: Pixels per QR module, from 1 to 50.
        border: Quiet-zone size in modules, from 0 to 20.
        fill_color: Pillow color name or hex value for the dark modules.
        back_color: Pillow color name or hex value for the background.
        tool_context: Current ADK tool context used to save the result artifact.

    Returns:
        A dict with filename, format, width, height, size_bytes, mime_type,
        artifact_saved and path. On failure, a dict with an ``error`` key.
    """
    try:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("content must be a non-empty string")
        if len(content) > _MAX_CONTENT_LENGTH:
            raise ValueError(
                f"content must be at most {_MAX_CONTENT_LENGTH} characters"
            )
        box_size = _positive_int_in_range(box_size, "box_size", 1, _MAX_BOX_SIZE)
        border = _positive_int_in_range(border, "border", 0, _MAX_BORDER)
        if not isinstance(fill_color, str) or not isinstance(back_color, str):
            raise ValueError("fill_color and back_color must be strings")

        encoded = _render(content, box_size, border, fill_color, back_color)
        artifact_name = _safe_filename(filename)

        with Image.open(BytesIO(encoded)) as image:
            width, height = image.size

        result: dict[str, object] = {
            "filename": artifact_name,
            "format": "png",
            "width": width,
            "height": height,
            "size_bytes": len(encoded),
            "mime_type": _MIME_TYPE,
            "artifact_saved": False,
            "path": None,
        }
        if tool_context is None:
            result["path"] = _write_temp_file(encoded)
        else:
            artifact = types.Part.from_bytes(data=encoded, mime_type=_MIME_TYPE)
            if artifact.inline_data is not None:
                artifact.inline_data.display_name = artifact_name
            await tool_context.save_artifact(artifact_name, artifact)
            result["artifact_saved"] = True
        return result
    except Exception as e:
        return {"error": str(e)}


__all__ = ["qrcode_generate"]
