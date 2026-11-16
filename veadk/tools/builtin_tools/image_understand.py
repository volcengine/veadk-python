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

"""Understand images with the configured vision model."""

from __future__ import annotations

from veadk.tools.builtin_tools.vision import analyze_images


async def image_understand(
    images: list[str],
    prompt: str = "Describe the image in detail.",
    model_name: str | None = None,
) -> dict:
    """Describe one or more images in detail with a vision model.

    Args:
        images: Local image paths or public http(s) URLs (1 to 8 items).
        prompt: What to ask about the images. The default requests a detailed
            description covering objects, text, layout and notable details.
        model_name: Optional vision model override.

    Returns:
        ``{"text": ..., "model": ...}`` on success, otherwise
        ``{"error": ...}``.
    """
    return await analyze_images(images, prompt, model_name)


__all__ = ["image_understand"]
