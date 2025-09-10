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

import json
import time
import traceback
from typing import Dict, cast

from google.adk.tools import ToolContext
from opentelemetry import trace
from opentelemetry.trace import Span
from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime.types.content_generation.create_task_content_param import (
    CreateTaskContentParam,
)

from veadk.config import getenv
from veadk.utils.logger import get_logger
from veadk.version import VERSION

logger = get_logger(__name__)

client = Ark(
    api_key=getenv("MODEL_VIDEO_API_KEY"),
    base_url=getenv("MODEL_VIDEO_API_BASE"),
)


async def generate(prompt, first_frame_image=None, last_frame_image=None):
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
                content=cast(
                    list[CreateTaskContentParam],  # avoid IDE warning
                    [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": first_frame_image},
                        },
                    ],
                ),
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


async def video_generate(params: list, tool_context: ToolContext) -> Dict:
    """
    Generate videos in **batch** from text prompts, optionally guided by a first/last frame,
    and fine-tuned via *model text commands* (a.k.a. `parameters` appended to the prompt).

    This API creates video-generation tasks. Each item in `params` describes a single video.
    The function submits all items in one call and returns task metadata for tracking.

    Args:
        params (list[dict]):
            A list of video generation requests. Each item supports the fields below.

            Required per item:
                - video_name (str):
                    Name/identifier of the output video file.

                - prompt (str):
                    Text describing the video to generate. Supports zh/EN.
                    You may append **model text commands** after the prompt to control resolution,
                    aspect ratio, duration, fps, watermark, seed, camera lock, etc.
                    Format: `... --rs <resolution> --rt <ratio> --dur <seconds> --fps <fps> --wm <bool> --seed <int> --cf <bool>`
                    Example:
                        "小猫骑着滑板穿过公园。 --rs 720p --rt 16:9 --dur 5 --fps 24 --wm true --seed 11 --cf false"

            Optional per item:
                - first_frame (str | None):
                    URL or Base64 string (data URL) for the **first frame** (role = `first_frame`).
                    Use when you want the clip to start from a specific image.

                - last_frame (str | None):
                    URL or Base64 string (data URL) for the **last frame** (role = `last_frame`).
                    Use when you want the clip to end on a specific image.

            Notes on first/last frame:
                * When both frames are provided, **match width/height** to avoid cropping; if they differ,
                  the tail frame may be auto-cropped to fit.
                * If you only need one guided frame, provide either `first_frame` or `last_frame` (not both).

            Image input constraints (for first/last frame):
                - Formats: jpeg, png, webp, bmp, tiff, gif
                - Aspect ratio (宽:高): 0.4–2.5
                - Width/Height (px): 300–6000
                - Size: < 30 MB
                - Base64 data URL example: `data:image/png;base64,<BASE64>`

    Model text commands (append after the prompt; unsupported keys are ignored by some models):
        --rs / --resolution <value>       Video resolution. Common values: 480p, 720p, 1080p.
                                          Default depends on model (e.g., doubao-seedance-1-0-pro: 1080p,
                                          some others default 720p).

        --rt / --ratio <value>            Aspect ratio. Typical: 16:9 (default), 9:16, 4:3, 3:4, 1:1, 2:1, 21:9.
                                          Some models support `keep_ratio` (keep source image ratio) or `adaptive`
                                          (auto choose suitable ratio).

        --dur / --duration <seconds>      Clip length in seconds. Seedance supports **3–12 s**;
                                          Wan2.1 仅支持 5 s。Default varies by model.

        --fps / --framespersecond <int>   Frame rate. Common: 16 or 24 (model-dependent; e.g., seaweed=24, wan2.1=16).

        --wm / --watermark <true|false>   Whether to add watermark. Default: **false** (per doc).

        --seed <int>                      Random seed in [-1, 2^32-1]. Default **-1** = auto seed.
                                          Same seed may yield similar (not guaranteed identical) results across runs.

        --cf / --camerafixed <true|false> Lock camera movement. Some models support this flag.
                                          true: try to keep camera fixed; false: allow movement. Default: **false**.

    Returns:
        Dict:
            API response containing task creation results for each input item. A typical shape is:
            {
                "status": "success",
                "success_list": [{"video_name": "video_url"}],
                "error_list": []
            }

    Constraints & Tips:
        - Keep prompt concise and focused (建议 ≤ 500 字); too many details may distract the model.
        - If using first/last frames, ensure their **aspect ratio matches** your chosen `--rt` to minimize cropping.
        - If you must reproduce results, specify an explicit `--seed`.
        - Unsupported parameters are ignored silently or may cause validation errors (model-specific).

    Minimal examples:
        1) Text-only batch of two 5-second clips at 720p, 16:9, 24 fps:
            params = [
                {
                    "video_name": "cat_park.mp4",
                    "prompt": "小猫骑着滑板穿过公园。 --rs 720p --rt 16:9 --dur 5 --fps 24 --wm false"
                },
                {
                    "video_name": "city_night.mp4",
                    "prompt": "霓虹灯下的城市延时摄影风。 --rs 720p --rt 16:9 --dur 5 --fps 24 --seed 7"
                },
            ]

        2) With guided first/last frame (square, 6 s, camera fixed):
            params = [
                {
                    "video_name": "logo_reveal.mp4",
                    "first_frame": "https://cdn.example.com/brand/logo_start.png",
                    "last_frame": "https://cdn.example.com/brand/logo_end.png",
                    "prompt": "品牌 Logo 从线稿到上色的变化。 --rs 1080p --rt 1:1 --dur 6 --fps 24 --cf true"
                }
            ]
    """
    batch_size = 10
    success_list = []
    error_list = []
    tracer = trace.get_tracer("gcp.vertex.agent")
    with tracer.start_as_current_span("call_llm") as span:
        input_part = {"role": "user"}
        output_part = {"message.role": "model"}

        for idx, item in enumerate(params):
            input_part[f"parts.{idx}.type"] = "text"
            input_part[f"parts.{idx}.text"] = json.dumps(item, ensure_ascii=False)

        for start_idx in range(0, len(params), batch_size):
            batch = params[start_idx : start_idx + batch_size]
            task_dict = {}
            for idx, item in enumerate(batch):
                video_name = item["video_name"]
                prompt = item["prompt"]
                first_frame = item.get("first_frame", None)
                last_frame = item.get("last_frame", None)
                try:
                    if not first_frame:
                        response = await generate(prompt)
                    elif not last_frame:
                        response = await generate(prompt, first_frame)
                    else:
                        response = await generate(prompt, first_frame, last_frame)
                    task_dict[response.id] = video_name
                except Exception as e:
                    logger.error(f"Error: {e}")
                    error_list.append(video_name)

            total_tokens = 0
            while True:
                task_list = list(task_dict.keys())
                if len(task_list) == 0:
                    break
                for idx, task_id in enumerate(task_list):
                    result = client.content_generation.tasks.get(task_id=task_id)
                    status = result.status
                    if status == "succeeded":
                        logger.debug("----- task succeeded -----")
                        tool_context.state[f"{task_dict[task_id]}_video_url"] = (
                            result.content.video_url
                        )
                        total_tokens += result.usage.completion_tokens
                        output_part[f"message.parts.{idx}.type"] = "text"
                        output_part[f"message.parts.{idx}.text"] = (
                            f"{task_dict[task_id]}: {result.content.video_url}"
                        )
                        success_list.append(
                            {task_dict[task_id]: result.content.video_url}
                        )
                        task_dict.pop(task_id, None)
                    elif status == "failed":
                        logger.error("----- task failed -----")
                        logger.error(f"Error: {result.error}")
                        error_list.append(task_dict[task_id])
                        task_dict.pop(task_id, None)
                    else:
                        logger.debug(
                            f"Current status: {status}, Retrying after 10 seconds..."
                        )
                time.sleep(10)

        add_span_attributes(
            span,
            tool_context,
            input_part=input_part,
            output_part=output_part,
            output_tokens=total_tokens,
            total_tokens=total_tokens,
            request_model=getenv("MODEL_VIDEO_NAME"),
            response_model=getenv("MODEL_VIDEO_NAME"),
        )

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


def add_span_attributes(
    span: Span,
    tool_context: ToolContext,
    input_part: dict | None = None,
    output_part: dict | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    request_model: str | None = None,
    response_model: str | None = None,
):
    try:
        # common attributes
        app_name = tool_context._invocation_context.app_name
        user_id = tool_context._invocation_context.user_id
        agent_name = tool_context.agent_name
        session_id = tool_context._invocation_context.session.id
        span.set_attribute("gen_ai.agent.name", agent_name)
        span.set_attribute("openinference.instrumentation.veadk", VERSION)
        span.set_attribute("gen_ai.app.name", app_name)
        span.set_attribute("gen_ai.user.id", user_id)
        span.set_attribute("gen_ai.session.id", session_id)
        span.set_attribute("agent_name", agent_name)
        span.set_attribute("agent.name", agent_name)
        span.set_attribute("app_name", app_name)
        span.set_attribute("app.name", app_name)
        span.set_attribute("user.id", user_id)
        span.set_attribute("session.id", session_id)
        span.set_attribute("cozeloop.report.source", "veadk")

        # llm attributes
        span.set_attribute("gen_ai.system", "openai")
        span.set_attribute("gen_ai.operation.name", "chat")
        if request_model:
            span.set_attribute("gen_ai.request.model", request_model)
        if response_model:
            span.set_attribute("gen_ai.response.model", response_model)
        if total_tokens:
            span.set_attribute("gen_ai.usage.total_tokens", total_tokens)
        if output_tokens:
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        if input_tokens:
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        if input_part:
            span.add_event("gen_ai.user.message", input_part)
        if output_part:
            span.add_event("gen_ai.choice", output_part)

    except Exception:
        traceback.print_exc()
