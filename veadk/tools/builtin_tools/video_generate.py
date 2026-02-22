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

import asyncio
import json
import traceback
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import httpx
from google.adk.tools import ToolContext
from opentelemetry import trace
from opentelemetry.trace import Span

from veadk.config import getenv, settings
from veadk.consts import DEFAULT_VIDEO_MODEL_API_BASE, DEFAULT_VIDEO_MODEL_NAME
from veadk.utils.logger import get_logger
from veadk.version import VERSION

logger = get_logger(__name__)

tracer = trace.get_tracer("veadk.video_generate")

API_KEY = getenv(
    "MODEL_VIDEO_API_KEY",
    getenv("MODEL_AGENT_API_KEY", settings.model.api_key),
)
API_BASE = getenv("MODEL_VIDEO_API_BASE", DEFAULT_VIDEO_MODEL_API_BASE).rstrip("/")


@dataclass
class VideoTaskResult:
    video_name: str
    task_id: Optional[str] = None
    video_url: Optional[str] = None
    error: Optional[str] = None
    error_detail: Optional[dict] = None
    status: str = "pending"
    execution_expires_after: Optional[int] = None


@dataclass
class VideoGenerationConfig:
    first_frame: Optional[str] = None
    last_frame: Optional[str] = None
    reference_images: List[str] = field(default_factory=list)
    reference_videos: List[str] = field(default_factory=list)
    reference_audios: List[str] = field(default_factory=list)
    generate_audio: Optional[bool] = None
    ratio: Optional[str] = None
    duration: Optional[int] = None
    resolution: Optional[str] = None
    frames: Optional[int] = None
    camera_fixed: Optional[bool] = None
    seed: Optional[int] = None
    watermark: Optional[bool] = None


def _get_model_name() -> str:
    return getenv("MODEL_VIDEO_NAME", DEFAULT_VIDEO_MODEL_NAME)


def _build_content(prompt: str, config: VideoGenerationConfig) -> list:
    content = [{"type": "text", "text": prompt}]

    if config.first_frame:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": config.first_frame},
                "role": "first_frame",
            }
        )

    if config.last_frame:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": config.last_frame},
                "role": "last_frame",
            }
        )

    for ref_image in config.reference_images:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": ref_image},
                "role": "reference_image",
            }
        )

    for ref_video in config.reference_videos:
        content.append(
            {
                "type": "video_url",
                "video_url": {"url": ref_video},
                "role": "reference_video",
            }
        )

    for ref_audio in config.reference_audios:
        content.append(
            {
                "type": "audio_url",
                "audio_url": {"url": ref_audio},
                "role": "reference_audio",
            }
        )

    return content


def _get_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "veadk-source": "veadk",
        "veadk-version": VERSION,
        "User-Agent": f"VeADK/{VERSION}",
        "X-Client-Request-Id": getenv("MODEL_AGENT_CLIENT_REQ_ID", f"veadk/{VERSION}"),
    }


def _should_disable_audio(
    model_name: str, generate_audio: Optional[bool]
) -> Optional[bool]:
    if generate_audio is False:
        return None
    if model_name.startswith("doubao-seedance-1-0") and generate_audio:
        logger.warning(
            "The `doubao-seedance-1-0` series models do not support enabling the audio field. "
            "Please upgrade to the doubao-seedance-1-5 series if you want to generate video with audio."
        )
        return None
    return generate_audio


def _build_request_body(prompt: str, config: VideoGenerationConfig) -> dict:
    model_name = _get_model_name()
    body = {
        "model": model_name,
        "content": _build_content(prompt, config),
    }

    generate_audio = _should_disable_audio(model_name, config.generate_audio)
    if generate_audio is not None:
        body["generate_audio"] = generate_audio

    if config.ratio is not None:
        body["ratio"] = config.ratio
    if config.duration is not None:
        body["duration"] = config.duration
    if config.resolution is not None:
        body["resolution"] = config.resolution
    if config.frames is not None:
        body["frames"] = config.frames
    if config.camera_fixed is not None:
        body["camera_fixed"] = config.camera_fixed
    if config.seed is not None:
        body["seed"] = config.seed
    if config.watermark is not None:
        body["watermark"] = config.watermark

    return body


async def _create_video_task(prompt: str, config: VideoGenerationConfig) -> dict:
    url = f"{API_BASE}/contents/generations/tasks"
    body = _build_request_body(prompt, config)

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=_get_headers(), json=body)
        if response.status_code >= 400:
            error_body = response.text
            logger.error(f"API Error {response.status_code}: {error_body}")
            logger.error(
                f"Request body: {json.dumps(body, ensure_ascii=False, indent=2)}"
            )
        response.raise_for_status()
        data = response.json()
        logger.debug(f"Video task created: {data}")
        return data


async def _get_task_status(task_id: str) -> dict:
    url = f"{API_BASE}/contents/generations/tasks/{task_id}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=_get_headers())
        response.raise_for_status()
        return response.json()


async def video_task_query(
    task_id: str,
    tool_context: ToolContext,
) -> Dict:
    """
    Query the status of a video generation task.

    Use this tool to check the status of a previously submitted video generation task.
    If the task is completed, the video URL will be returned.

    Args:
        task_id (str):
            The task ID returned from video_generate when the task was submitted.
            Format: "cgt-xxxxxxxxxxxx-xxxxx"

        tool_context (ToolContext):
            The tool context provided by the ADK framework.

    Returns:
        Dict:
            {
                "task_id": "cgt-xxxxxxxxxxxx-xxxxx",
                "status": "succeeded" | "running" | "failed" | "queued",
                "video_url": "https://..." | None,
                "error": {...} | None,
                "model": "doubao-seedance-x-x",
                "created_at": timestamp,
                "updated_at": timestamp,
                "execution_expires_after": seconds
            }

    Status Values:
        - queued: Task is waiting in queue
        - running: Task is being processed
        - succeeded: Task completed, video_url available
        - failed: Task failed, check error field

    Example:
        # Query a task status
        result = await video_task_query("cgt-20260222165751-wsnw8", tool_context)
        if result["status"] == "succeeded":
            print(f"Video ready: {result['video_url']}")
        elif result["status"] == "running":
            print("Still processing, please wait...")
        elif result["status"] == "failed":
            print(f"Task failed: {result['error']}")
    """
    try:
        result = await _get_task_status(task_id)

        status = result.get("status")
        response = {
            "task_id": task_id,
            "status": status,
            "video_url": None,
            "error": None,
            "model": result.get("model"),
            "created_at": result.get("created_at"),
            "updated_at": result.get("updated_at"),
            "execution_expires_after": result.get("execution_expires_after"),
        }

        if status == "succeeded":
            video_url = result.get("content", {}).get("video_url")
            response["video_url"] = video_url
            if video_url:
                tool_context.state[f"{task_id}_video_url"] = video_url
            logger.info(f"Task {task_id} succeeded: {video_url}")

        elif status == "failed":
            error = result.get("error")
            response["error"] = error
            logger.error(f"Task {task_id} failed: {error}")

        else:
            logger.debug(f"Task {task_id} status: {status}")

        return response

    except Exception as e:
        logger.error(f"Error querying task {task_id}: {e}")
        traceback.print_exc()
        return {
            "task_id": task_id,
            "status": "error",
            "video_url": None,
            "error": str(e),
        }


async def _poll_task_status(
    task_id: str,
    video_name: str,
    max_wait_seconds: int = 1200,
    poll_interval: int = 10,
) -> VideoTaskResult:
    max_polls = max_wait_seconds // poll_interval
    polls = 0

    while polls < max_polls:
        result = await _get_task_status(task_id)
        status = result.get("status")

        if status == "succeeded":
            video_url = result.get("content", {}).get("video_url")
            logger.debug(f"Video {video_name} succeeded: {video_url}")
            return VideoTaskResult(
                video_name=video_name,
                task_id=task_id,
                video_url=video_url,
                status="succeeded",
                execution_expires_after=result.get("execution_expires_after"),
            )

        if status == "failed":
            error = result.get("error", {})
            logger.error(f"Video {video_name} failed: {error}")
            return VideoTaskResult(
                video_name=video_name,
                task_id=task_id,
                error=str(error),
                status="failed",
                execution_expires_after=result.get("execution_expires_after"),
            )

        logger.debug(f"Video {video_name} status: {status}, retrying...")
        await asyncio.sleep(poll_interval)
        polls += 1

    result = await _get_task_status(task_id)
    logger.warning(
        f"Video {video_name} polling timed out after {max_wait_seconds}s, task still pending"
    )
    return VideoTaskResult(
        video_name=video_name,
        task_id=task_id,
        error="polling_timeout",
        status="pending",
        execution_expires_after=result.get("execution_expires_after"),
    )


async def poll_single_task(
    task_id: str,
    video_name: str,
    max_wait_seconds: int = 1200,
) -> VideoTaskResult:
    return await _poll_task_status(task_id, video_name, max_wait_seconds)


def _add_span_attributes(
    span: Span,
    tool_context: ToolContext,
    input_part: dict,
    output_part: dict,
    output_tokens: int,
    request_model: str,
    response_model: str,
):
    try:
        ctx = tool_context._invocation_context
        span.set_attribute("gen_ai.agent.name", tool_context.agent_name)
        span.set_attribute("openinference.instrumentation.veadk", VERSION)
        span.set_attribute("gen_ai.app.name", ctx.app_name)
        span.set_attribute("gen_ai.user.id", ctx.user_id)
        span.set_attribute("gen_ai.session.id", ctx.session.id)
        span.set_attribute("agent_name", tool_context.agent_name)
        span.set_attribute("agent.name", tool_context.agent_name)
        span.set_attribute("app_name", ctx.app_name)
        span.set_attribute("app.name", ctx.app_name)
        span.set_attribute("user.id", ctx.user_id)
        span.set_attribute("session.id", ctx.session.id)
        span.set_attribute("cozeloop.report.source", "veadk")
        span.set_attribute("gen_ai.system", "Ark")
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.request.model", request_model)
        span.set_attribute("gen_ai.response.model", response_model)
        span.set_attribute("gen_ai.usage.total_tokens", output_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        span.add_event("gen_ai.user.message", input_part)
        span.add_event("gen_ai.choice", output_part)
    except Exception:
        traceback.print_exc()


def _parse_item_to_config(item: dict) -> VideoGenerationConfig:
    return VideoGenerationConfig(
        first_frame=item.get("first_frame"),
        last_frame=item.get("last_frame"),
        reference_images=item.get("reference_images", []),
        reference_videos=item.get("reference_videos", []),
        reference_audios=item.get("reference_audios", []),
        generate_audio=item.get("generate_audio"),
        ratio=item.get("ratio"),
        duration=item.get("duration"),
        resolution=item.get("resolution"),
        frames=item.get("frames"),
        camera_fixed=item.get("camera_fixed"),
        seed=item.get("seed"),
        watermark=item.get("watermark"),
    )


async def _process_single_item(
    item: dict,
) -> VideoTaskResult:
    video_name = item["video_name"]
    prompt = item["prompt"]
    config = _parse_item_to_config(item)

    try:
        task_data = await _create_video_task(prompt, config)
        task_id = task_data.get("id")
        return VideoTaskResult(
            video_name=video_name,
            task_id=task_id,
            status="created",
            execution_expires_after=task_data.get("execution_expires_after"),
        )
    except httpx.HTTPStatusError as e:
        error_text = e.response.text if e.response else str(e)
        error_detail = None
        try:
            error_detail = json.loads(error_text)
        except Exception as e:
            error_detail = {"raw_error": error_text}
        logger.error(
            f"HTTP error for {video_name}: {e.response.status_code} - {error_text}"
        )
        return VideoTaskResult(
            video_name=video_name,
            error=error_text,
            error_detail=error_detail,
            status="failed",
        )
    except Exception as e:
        logger.error(f"Failed to create video task for {video_name}: {e}")
        return VideoTaskResult(
            video_name=video_name,
            error=str(e),
            error_detail={"raw_error": str(e)},
            status="failed",
        )


async def video_generate(
    params: list,
    tool_context: ToolContext,
    batch_size: int = 10,
    max_wait_seconds: int = 1200,
) -> Dict:
    """
    Generate videos in batch from text prompts, with support for multiple input modes:
    text-to-video, image-to-video (first/last frame), and multimodal reference generation.

    This API creates video-generation tasks asynchronously. Each item in `params` describes
    a single video generation request. The function submits all items and polls for results.

    If polling times out, the task_id will be returned so you can query the status later
    using the video_task_query tool.

    Args:
        params (list[dict]):
            A list of video generation requests. Each item is a dict with the following fields.

            Required per item:
                - video_name (str):
                    Name/identifier of the output video file.

                - prompt (str):
                    Text describing the video to generate. Supports Chinese and English.
                    For multimodal reference generation, use [图1], [图2], [视频1], [音频1]
                    to reference specific input materials in your prompt.

            Optional per item - Input Materials:
                - first_frame (str):
                    URL for the first frame image (role = first_frame).
                    Use when you want the video to start from a specific image.

                - last_frame (str):
                    URL for the last frame image (role = last_frame).
                    Use when you want the video to end on a specific image.

                - reference_images (list[str]):
                    1-4 reference image URLs for style/content guidance (role = reference_image).
                    The model extracts features from these images and applies them to the output.
                    Use [图1], [图2], etc. in prompt to reference specific images.

                - reference_videos (list[str]):
                    0-3 reference video URLs for multimodal generation (role = reference_video).
                    Video constraints: mp4/mov format, 2-15s duration per video,
                    total duration <= 15s, size <= 50MB, 24-60 FPS.
                    Use [视频1], [视频2], etc. in prompt to reference specific videos.

                - reference_audios (list[str]):
                    0-3 reference audio URLs for multimodal generation (role = reference_audio).
                    Audio constraints: mp3/wav format, 2-15s duration per audio,
                    total duration <= 15s, size <= 15MB.
                    Use [音频1], [音频2], etc. in prompt to reference specific audios.
                    Note: Audio cannot be used alone; must have at least one image or video.

            Optional per item - Video Output Parameters:
                - ratio (str):
                    Aspect ratio. Options: "16:9" (default), "9:16", "4:3", "3:4", "1:1",
                    "2:1", "21:9", "adaptive" (auto-select based on input).
                    Note: Reference image scenarios do not support all ratios.

                - duration (int):
                    Video length in seconds. Range: 2-12s depending on model.
                    - Seedance 1.5 pro: 4-12s
                    - Seedance 1.0 pro: 2-12s
                    - Seedance 1.0 pro-fast: 2-12s

                - resolution (str):
                    Video resolution. Options: "480p", "720p", "1080p".
                    Default varies by model (e.g., Seedance 1.0 pro defaults to 1080p).
                    Note: Reference image scenarios do not support resolution parameter.

                - frames (int):
                    Total frame count. Must be in [29, 289] and follow format 25 + 4n.
                    Alternative to duration for controlling video length.

                - camera_fixed (bool):
                    Lock camera movement. true = fixed camera, false = allow movement.
                    Default: false. Note: Not supported in reference image scenarios.

                - seed (int):
                    Random seed for reproducibility. Range: [-1, 2^32-1].
                    Default: -1 (auto seed). Same seed may yield similar results.

                - watermark (bool):
                    Whether to add watermark. Default: false.

                - generate_audio (bool):
                    Whether to generate audio. Only Seedance 1.5 pro supports this.
                    If True, audio (ambient sounds, music, voice) can be generated.
                    Describe desired audio content in the prompt field.

        batch_size (int):
            Number of videos to generate per batch. Defaults to 10.

        max_wait_seconds (int):
            Maximum wait time per batch in seconds. Defaults to 1200 (20 minutes).
            If tasks are still pending after this time, task_id will be returned
            for later querying using video_task_query.

    Returns:
        Dict:
            {
                "status": "success" | "partial_success" | "error",
                "success_list": [{"video_name": "video_url"}, ...],
                "error_list": ["video_name", ...],
                "pending_list": [
                    {
                        "video_name": "...",
                        "task_id": "cgt-xxx",
                        "execution_expires_after": 172800
                    }, ...
                ]
            }

    Input Modes:
        1. Text-to-Video: Only provide prompt, no images/videos.
        2. First Frame Guidance: Provide first_frame for starting image.
        3. First + Last Frame Guidance: Provide both for transition video.
        4. Reference Images: Provide reference_images for style/content guidance.
        5. Multimodal Reference: Combine reference_images, reference_videos, reference_audios.

    Constraints & Tips:
        - Keep prompt concise (recommended ≤ 500 characters).
        - For first/last frame, ensure aspect ratios match your chosen ratio.
        - Reference images: 1-4 images, formats: jpeg/png/webp/bmp/tiff/gif.
        - Reference videos: 0-3 videos, formats: mp4/mov, total duration ≤ 15s.
        - Reference audios: 0-3 audios, formats: mp3/wav, total duration ≤ 15s.
        - Multimodal requires at least one image or video (audio-only not supported).
        - Use explicit seed for reproducibility.
        - If polling times out, use video_task_query with the returned task_id.

    Examples:
        # 1. Text-to-Video
        params = [{
            "video_name": "cat_park.mp4",
            "prompt": "小猫骑着滑板穿过公园",
            "ratio": "16:9",
            "duration": 5,
            "resolution": "720p"
        }]

        # 2. First Frame Guidance
        params = [{
            "video_name": "cat_jump.mp4",
            "prompt": "小猫跳起来",
            "first_frame": "https://example.com/cat.png",
            "ratio": "adaptive",
            "duration": 5
        }]

        # 3. First + Last Frame Guidance
        params = [{
            "video_name": "transition.mp4",
            "prompt": "平滑过渡动画",
            "first_frame": "https://example.com/start.png",
            "last_frame": "https://example.com/end.png",
            "duration": 6
        }]

        # 4. Reference Images (style/content guidance)
        params = [{
            "video_name": "styled.mp4",
            "prompt": "[图1]戴着眼镜的男生和[图2]柯基小狗坐在[图3]草坪上，卡通风格",
            "reference_images": [
                "https://example.com/boy.png",
                "https://example.com/dog.png",
                "https://example.com/grass.png"
            ],
            "ratio": "16:9",
            "duration": 5
        }]

        # 5. Multimodal Reference (video + audio)
        params = [{
            "video_name": "multimodal.mp4",
            "prompt": "将视频中的两个人物换成[图1]和[图2]中的男孩和女孩，音色使用[音频1]中的音色",
            "reference_images": [
                "https://example.com/boy.png",
                "https://example.com/girl.png"
            ],
            "reference_videos": ["https://example.com/source.mp4"],
            "reference_audios": ["https://example.com/voice.wav"],
            "duration": 5
        }]

        # 6. With Audio Generation (Seedance 1.5 pro only)
        params = [{
            "video_name": "with_audio.mp4",
            "prompt": "女孩抱着狐狸，可以听到风声和树叶沙沙声",
            "first_frame": "https://example.com/girl_fox.png",
            "generate_audio": True,
            "duration": 6,
            "resolution": "1080p"
        }]
    """
    success_list = []
    error_list = []
    error_details = []
    pending_list = []
    model_name = _get_model_name()

    logger.debug(f"Using model: {model_name}")
    logger.debug(f"video_generate params: {params}")

    for start_idx in range(0, len(params), batch_size):
        batch = params[start_idx : start_idx + batch_size]
        logger.debug(f"Processing batch {start_idx // batch_size}: {len(batch)} items")

        task_results = await asyncio.gather(
            *[_process_single_item(item) for item in batch]
        )

        pending_tasks = {}
        for r in task_results:
            if r.status == "created" and r.task_id:
                pending_tasks[r.task_id] = {
                    "video_name": r.video_name,
                    "execution_expires_after": r.execution_expires_after,
                }
            elif r.status == "failed":
                error_list.append(r.video_name)
                if r.error_detail:
                    error_details.append(
                        {
                            "video_name": r.video_name,
                            "error": r.error_detail,
                        }
                    )

        input_part = {"role": "user"}
        output_part = {"message.role": "model"}
        total_tokens = 0

        for idx, item in enumerate(batch):
            input_part[f"parts.{idx}.type"] = "text"
            input_part[f"parts.{idx}.text"] = json.dumps(item, ensure_ascii=False)

        with tracer.start_as_current_span("video_generate_batch") as span:
            poll_count = 0
            max_polls = max_wait_seconds // 10

            while pending_tasks and poll_count < max_polls:
                completed_in_round = []

                for task_id in list(pending_tasks.keys()):
                    task_info = pending_tasks[task_id]
                    video_name = task_info["video_name"]

                    try:
                        result = await _get_task_status(task_id)
                        status = result.get("status")

                        if status == "succeeded":
                            video_url = result.get("content", {}).get("video_url")
                            tool_context.state[f"{video_name}_video_url"] = video_url
                            usage = result.get("usage", {})
                            total_tokens += usage.get("completion_tokens", 0)

                            idx = list(pending_tasks.keys()).index(task_id)
                            output_part[f"message.parts.{idx}.type"] = "text"
                            output_part[f"message.parts.{idx}.text"] = (
                                f"{video_name}: {video_url}"
                            )

                            success_list.append({video_name: video_url})
                            completed_in_round.append(task_id)
                            logger.debug(f"Video {video_name} completed: {video_url}")

                        elif status == "failed":
                            error_info = result.get("error")
                            error_list.append(video_name)
                            error_details.append(
                                {
                                    "video_name": video_name,
                                    "error": error_info,
                                }
                            )
                            completed_in_round.append(task_id)
                            logger.error(f"Video {video_name} failed: {error_info}")
                    except Exception as e:
                        logger.error(f"Error polling task {task_id}: {e}")

                for task_id in completed_in_round:
                    pending_tasks.pop(task_id, None)

                if not pending_tasks:
                    break

                await asyncio.sleep(10)
                poll_count += 1

            for task_id, task_info in pending_tasks.items():
                pending_list.append(
                    {
                        "video_name": task_info["video_name"],
                        "task_id": task_id,
                        "execution_expires_after": task_info["execution_expires_after"],
                        "message": f"Task still running. Use video_task_query('{task_id}') to check status later.",
                    }
                )

            _add_span_attributes(
                span,
                tool_context,
                input_part=input_part,
                output_part=output_part,
                output_tokens=total_tokens,
                request_model=model_name,
                response_model=model_name,
            )

    if success_list and not error_list and not pending_list:
        status = "success"
    elif success_list:
        status = "partial_success"
    else:
        status = "error"

    logger.debug(
        f"video_generate completed: {len(success_list)} success, {len(error_list)} errors, {len(pending_list)} pending"
    )

    return {
        "status": status,
        "success_list": success_list,
        "error_list": error_list,
        "error_details": error_details,
        "pending_list": pending_list,
    }
