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

"""Extract text from images with the configured vision model."""

from __future__ import annotations

from veadk.tools.builtin_tools.vision import analyze_images

_BASE_PROMPT = (
    "Transcribe all text visible in the image exactly as it appears. Return "
    "only the transcribed text, preserving line breaks and reading order. Do "
    "not translate, summarize, or add commentary. If the image contains no "
    "text, return an empty string."
)


async def ocr(
    image: str,
    language: str = "auto",
    model_name: str | None = None,
) -> dict:
    """Transcribe text from an image with a vision model.

    Args:
        image: Local image path or public http(s) URL.
        language: Expected text language, or ``auto`` to let the model decide.
        model_name: Optional vision model override.

    Returns:
        ``{"text": ..., "language": ..., "model": ...}`` on success, otherwise
        ``{"error": ...}``.
    """
    prompt = _BASE_PROMPT
    if isinstance(language, str) and language.strip().lower() != "auto":
        prompt = f"{prompt} The text is expected to be in {language.strip()}."
    result = await analyze_images([image], prompt, model_name)
    if "error" in result:
        return result
    return {
        "text": result["text"],
        "language": language,
        "model": result["model"],
    }


__all__ = ["ocr"]
