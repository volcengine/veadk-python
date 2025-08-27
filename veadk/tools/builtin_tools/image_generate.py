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
    params: list,
    tool_context: ToolContext,
) -> Dict:
    """
    Generate images in batch according to prompts and optional settings.

    Each item in `params` describes a single image-generation request.

    Args:
        params (list[dict]):
            A list of image generation requests. Each item supports:

            Required:
                - prompt (str):
                    The textual description of the desired image.
                    Supports English and Chinese.

            Optional:
                - image_name (str):
                    Name/identifier for the generated image.

                - response_format (str):
                    Format of the returned image.
                    * "url": JPEG link (default)
                    * "b64_json": Base64 string in JSON

                - size (str):
                    Resolution of the generated image.
                    Default: "1024x1024".
                    Must be within [512x512, 2048x2048].
                    Common options: 1024x1024, 864x1152, 1280x720, etc.

                - guidance_scale (float):
                    How strongly the prompt affects the result.
                    Range: [1.0, 10.0], default 2.5.

                - watermark (bool):
                    Whether to add watermark.
                    Default: True.

                - seed (int):
                    Random seed for reproducibility.
                    Range: [-1, 2^31-1], default -1 (random).

    Returns:
        Dict: API response containing generated image metadata.
        Example:
        {
            "status": "success",
            "success_list": [{"image_name": ""}],
            "error_list": [{}]
        }

    Notes:
        - Best suited for creating original images from text.
        - Use a fixed `seed` for reproducibility.
        - Choose appropriate `size` for desired aspect ratio.
    """
    success_list = []
    error_list = []
    for idx, item in enumerate(params):
        prompt = item.get("prompt", "")
        image_name = item.get("image_name", f"generated_image_{idx}")
        response_format = item.get("response_format", "url")
        size = item.get("size", "1024x1024")
        guidance_scale = item.get("guidance_scale", 2.5)
        watermark = item.get("watermark", True)
        seed = item.get("seed", -1)

        try:
            response = client.images.generate(
                model=getenv("MODEL_IMAGE_NAME"),
                prompt=prompt,
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
                        tool_context.state[f"{image_name}_url"] = image

                    elif response_format == "b64_json":
                        image = item.b64_json
                        image_bytes = base64.b64decode(image)

                        tool_context.state[f"{image_name}_url"] = (
                            f"data:image/jpeg;base64,{image}"
                        )

                        report_artifact = types.Part.from_bytes(
                            data=image_bytes, mime_type="image/png"
                        )
                        await tool_context.save_artifact(image_name, report_artifact)
                        logger.debug(f"Image saved as ADK artifact: {image_name}")

                    success_list.append({image_name: image})
            else:
                error_details = f"No images returned by Doubao model: {response}"
                logger.error(error_details)
                error_list.append(image_name)

        except Exception as e:
            error_details = f"No images returned by Doubao model: {e}"
            logger.error(error_details)
            error_list.append(image_name)

    if len(success_list) == 0:
        return {
            "status": "error",
            "success_list": success_list,
            "error_list": error_list,
        }
    else:
        return {
            "status": "success",
            "success_list": success_list,
            "error_list": error_list,
        }
