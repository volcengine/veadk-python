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
from google.adk.tools import ToolContext
from google.genai import types
from volcenginesdkarkruntime import Ark
from veadk.config import getenv
import base64

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

client = Ark(
    api_key=getenv("MODEL_EDIT_API_KEY"),
    base_url=getenv("MODEL_EDIT_API_BASE"),
)


async def image_edit(
    params: list,
    tool_context: ToolContext,
) -> Dict:
    """
    Edit images in batch according to prompts and optional settings.

    Each item in `params` describes a single image-edit request.

    Args:
        params (list[dict]):
            A list of image editing requests. Each item supports:

            Required:
                - origin_image (str):
                    The URL or Base64 string of the original image to edit.
                    Example:
                      * URL: "https://example.com/image.png"
                      * Base64: "data:image/png;base64,<BASE64>"

                - prompt (str):
                    The textual description/instruction for editing the image.
                    Supports English and Chinese.

            Optional:
                - image_name (str):
                    Name/identifier for the generated image.

                - response_format (str):
                    Format of the returned image.
                    * "url": JPEG link (default)
                    * "b64_json": Base64 string in JSON

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
        - Uses SeedEdit 3.0 model.
        - Provide the same `seed` for consistent outputs across runs.
        - A high `guidance_scale` enforces stricter adherence to text prompt.
    """
    success_list = []
    error_list = []
    for idx, item in enumerate(params):
        image_name = item.get("image_name", f"generated_image_{idx}")
        prompt = item.get("prompt")
        origin_image = item.get("origin_image")
        response_format = item.get("response_format", "url")
        guidance_scale = item.get("guidance_scale", 2.5)
        watermark = item.get("watermark", True)
        seed = item.get("seed", -1)

        try:
            response = client.images.generate(
                model=getenv("MODEL_EDIT_NAME"),
                image=origin_image,
                prompt=prompt,
                response_format=response_format,
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
