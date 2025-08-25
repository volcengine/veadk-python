from typing import Dict
from google.adk.tools import ToolContext
from google.genai import types
from volcenginesdkarkruntime import Ark
from veadk.config import getenv
import base64

client = Ark(
    api_key=getenv("MODEL_IMAGE_API_KEY"),
    base_url=getenv("MODEL_IMAGE_API_BASE"),
)

async def image_edit(
    origin_image: str,
    image_name: str, 
    image_prompt: str, 
    response_format: str, 
    guidance_scale: float,
    watermark: bool,
    seed: int,
    tool_context: ToolContext) -> Dict:
    """Edit an image accoding to the prompt.

    Args:
        origin_image: The url or the base64 string of the edited image.
        image_name: The name of the generated image.
        image_prompt: The prompt that describes the image.
        response_format: str, b64_json or url, default url.
        guidance_scale: default 2.5.
        watermark: default True.
        seed: default -1.

    """
    try:
        response = client.images.generate(
            model=getenv("MODEL_EDIT_NAME"),
            image=origin_image,
            prompt=image_prompt,
            response_format=response_format,
            guidance_scale=guidance_scale,
            watermark=watermark,
            seed=seed
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

                return {
                    "status": "success",
                    "image_name": image_name,
                    "image": image
                }
        else:
            error_details = f"No images returned by Doubao model: {response}"
            logger.error(error_details)
            return {"status": "error", "message": error_details}

    except Exception as e:
        return {
            "status": "error",
            "message": f"Doubao image generation failed: {str(e)}",
        }

