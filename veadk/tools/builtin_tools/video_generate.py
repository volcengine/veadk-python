from typing import Dict
from google.adk.tools import ToolContext
from volcenginesdkarkruntime import Ark
from veadk.config import getenv
import time
import traceback
import base64

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

client = Ark(
    api_key=getenv("MODEL_VIDEO_API_KEY"),
    base_url=getenv("MODEL_VIDEO_API_BASE"),
)

async def generate(tool_context, prompt, first_frame_image=None, last_frame_image=None):
    try:
        if first_frame_image is None:
            logger.debug("text generation")
            response = client.content_generation.tasks.create(
                model=getenv("MODEL_VIDEO_NAME"),
                content=[
                    {"type": "text", "text": prompt},
                ],
            )
        elif last_frame_image is None:
            logger.debug("first frame generation")
            response = client.content_generation.tasks.create(
                model=getenv("MODEL_VIDEO_NAME"),
                content=[
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": first_frame_image},
                    },
                ],
            )
        else:
            logger.debug("last frame generation")
            response = client.content_generation.tasks.create(
                model=getenv("MODEL_VIDEO_NAME"),
                content=[
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": first_frame_image},
                        "role": "first_frame",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": last_frame_image},
                        "role": "last_frame",
                    },
                ],
            )
    except:
        traceback.print_exc()
        raise
    return response

async def video_generate(
    params: list,
    tool_context: ToolContext) -> Dict:
    """Generate video in batch according to the prompt.

    Args:
        params:
            video_name: The name of the generated video.
            first_frame: The first frame of the video, url or base64 string, or None.
            last_frame：The last frame of the video, url or base64 string, or None.
            prompt：The prompt of the video.
    """
    batch_size = 10
    success_list = []
    error_list = []
    for start_idx in range(0, len(params), batch_size):
        batch = params[start_idx : start_idx + batch_size]
        task_dict = {}
        for item in batch:
            video_name = item["video_name"]
            first_frame = item["first_frame"]
            last_frame = item["last_frame"]
            prompt = item["prompt"]
            try:
                if not first_frame:
                    response = await generate(tool_context, prompt)
                elif not last_frame:
                    response = await generate(tool_context, prompt, first_frame)
                else:
                    response = await generate(
                        tool_context, prompt, first_frame, last_frame
                    )
                task_dict[response.id] = video_name
            except Exception:
                traceback.print_exc()
        while True:
            task_list = list(task_dict.keys())
            if len(task_list) == 0:
                break
            for task_id in task_list:
                result = client.content_generation.tasks.get(task_id=task_id)
                status = result.status
                if status == "succeeded":
                    logger.debug("----- task succeeded -----")
                    tool_context.state[f"{task_dict[task_id]}_video_url"] = result.content.video_url
                    success_list.append({task_dict[task_id]: result.content.video_url})
                    task_dict.pop(task_id, None)
                elif status == "failed":
                    logger.debug("----- task failed -----")
                    logger.debug(f"Error: {result.error}")
                    error_list.append(task_dict[task_id])
                    task_dict.pop(task_id, None)
                else:
                    logger.debug(f"Current status: {status}, Retrying after 10 seconds...")
            time.sleep(10)

    if len(success_list) == 0:
        return {"status": "error", "message": f"Following videos failed: {error_list}"}
    else:
        return {
            "status": "success",
            "message": f"Following videos generated: {success_list}\nFollowing videos failed: {error_list}",
        }