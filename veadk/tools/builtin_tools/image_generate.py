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
from typing import Dict

from google.genai import types
from google.adk.tools import ToolContext
from veadk.config import getenv
import base64
from volcenginesdkarkruntime import Ark

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

client = Ark(
    api_key=getenv("MODEL_IMAGE_API_KEY"),
    base_url=getenv("MODEL_IMAGE_API_BASE"),
)


async def image_generate(
    image_name: str,
    image_prompt: str,
    response_format: str,
    size: str,
    guidance_scale: float,
    watermark: bool,
    seed: int,
    tool_context: ToolContext,
) -> Dict:
    """Generate an image accoding to the prompt.

    Args:
        image_name: The name of the generated image.
        image_prompt: The prompt that describes the image.
        response_format: str, b64_json or url, default url.
        size: default 1024x1024.
        guidance_scale: default 2.5.
        watermark: default True.
        seed: default -1.

    """
    try:
        response = client.images.generate(
            model=getenv("MODEL_IMAGE_NAME"),
            prompt=image_prompt,
            response_format=response_format,
            size=size,
            guidance_scale=guidance_scale,
            watermark=watermark,
            seed=seed,
        )

        if response.data and len(response.data) > 0:
            for item in response.data:
                if response_format == "url":
                    image = item.url
                    tool_context.state["generated_image_url"] = image

                elif response_format == "b64_json":
                    image = item.b64_json
                    image_bytes = base64.b64decode(image)

                    tool_context.state["generated_image_url"] = (
                        f"data:image/jpeg;base64,{image}"
                    )

                    report_artifact = types.Part.from_bytes(
                        data=image_bytes, mime_type="image/png"
                    )
                    await tool_context.save_artifact(image_name, report_artifact)
                    logger.debug(f"Image saved as ADK artifact: {image_name}")

                return {"status": "success", "image_name": image_name, "image": image}
        else:
            error_details = f"No images returned by Doubao model: {response}"
            logger.error(error_details)
            return {"status": "error", "message": error_details}

    except Exception as e:
        return {
            "status": "error",
            "message": f"Doubao image generation failed: {str(e)}",
        }
