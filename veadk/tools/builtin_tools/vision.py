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

"""Shared vision helper for image understanding and OCR tools."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import filetype
import httpx
from PIL import Image

from veadk.config import getenv, settings

_MAX_IMAGES = 8
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_DEFAULT_TIMEOUT_SECONDS = 60
_ERROR_DETAIL_LIMIT = 200

_PILLOW_MIME_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}
_EXTENSION_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def _validate(images: object, prompt: object, timeout: object) -> None:
    if not isinstance(images, list) or not 1 <= len(images) <= _MAX_IMAGES:
        raise ValueError(f"images must be a list of 1 to {_MAX_IMAGES} items")
    for image in images:
        if not isinstance(image, str) or not image.strip():
            raise ValueError("each image must be a non-empty path or URL")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, int)
        or not 1 <= timeout <= 300
    ):
        raise ValueError("timeout must be an integer between 1 and 300")


def _is_http_url(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _guess_mime(data: bytes, path: Path | None) -> str:
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format in _PILLOW_MIME_TYPES:
                return _PILLOW_MIME_TYPES[image.format]
    except Exception:
        pass
    kind = filetype.guess(data)
    if kind is not None:
        return kind.mime
    if path is not None:
        extension = path.suffix.lower()
        if extension in _EXTENSION_MIME_TYPES:
            return _EXTENSION_MIME_TYPES[extension]
    return "application/octet-stream"


def _image_part(image: str) -> dict:
    if _is_http_url(image):
        return {"type": "image_url", "image_url": {"url": image}}
    path = Path(image)
    if not path.is_file():
        raise ValueError(f"image file does not exist: {image}")
    data = path.read_bytes()
    if len(data) > _MAX_IMAGE_BYTES:
        raise ValueError(f"image exceeds the {_MAX_IMAGE_BYTES} byte limit")
    mime_type = _guess_mime(data, path)
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
    }


def _error_detail(response: object) -> str:
    """Extract a short provider error message so callers can fix the config."""
    try:
        payload = response.json()  # type: ignore[attr-defined]
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("code")
    elif isinstance(error, str):
        message = error
    else:
        message = payload.get("message")
    if not isinstance(message, str):
        return ""
    return " ".join(message.split())[:_ERROR_DETAIL_LIMIT]


def _resolve_model(model_name: str | None) -> str:
    model = (
        model_name
        or getenv("MODEL_VISION_NAME", "", allow_false_values=True)
        or settings.model.name
    )
    if not isinstance(model, str) or not model.strip():
        raise ValueError("vision model name is not configured")
    return model.strip()


def _resolve_api_key() -> str:
    api_key = getenv("MODEL_AGENT_API_KEY", "", allow_false_values=True)
    if not api_key:
        api_key = settings.model.api_key
    if not api_key:
        raise ValueError("vision model API key is not configured")
    return str(api_key)


def _extract_text(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part.get("text")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        return "".join(parts)
    return None


async def analyze_images(
    images: list[str],
    prompt: str,
    model_name: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Send one or more images to the configured vision model.

    Args:
        images: Local image paths or public http(s) URLs (1 to 8 items).
        prompt: Instruction for the model.
        model_name: Optional vision model override. Defaults to
            ``MODEL_VISION_NAME`` or the agent model name.
        timeout: Request timeout in seconds (1 to 300).

    Returns:
        ``{"text": ..., "model": ...}`` on success, otherwise
        ``{"error": ...}``. The API key is never included in errors.
    """
    try:
        _validate(images, prompt, timeout)
        model = _resolve_model(model_name)
        api_key = _resolve_api_key()
        base_url = settings.model.api_base
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("vision model API base is not configured")

        image_parts = [_image_part(image) for image in images]
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}, *image_parts],
                }
            ],
        }
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code >= 400:
            detail = _error_detail(response)
            suffix = f": {detail}" if detail else ""
            return {
                "error": f"vision request failed with HTTP status "
                f"{response.status_code}{suffix}"
            }
        try:
            response_payload = response.json()
        except ValueError:
            return {"error": "vision response was not valid JSON"}
        text = _extract_text(response_payload)
        if text is None:
            return {"error": "vision response did not contain text content"}
        return {"text": text, "model": model}
    except ValueError as e:
        return {"error": str(e)}
    except httpx.HTTPError as e:
        return {"error": f"vision request failed: {e}"}
    except Exception as e:
        return {"error": f"vision request failed: {type(e).__name__}: {e}"}


__all__ = ["analyze_images"]
