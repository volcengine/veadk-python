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
import base64
import json
import traceback
from typing import Dict, Optional

import httpx
from google.adk.tools import ToolContext
from google.genai.types import Blob, Part
from opentelemetry import trace
from opentelemetry.trace import Span

from veadk.config import getenv, settings
from veadk.consts import (
    DEFAULT_IMAGE_GENERATE_MODEL_API_BASE,
    DEFAULT_IMAGE_GENERATE_MODEL_NAME,
)
from veadk.utils.logger import get_logger
from veadk.utils.misc import formatted_timestamp, read_file_to_bytes
from veadk.version import VERSION

logger = get_logger(__name__)

tracer = trace.get_tracer("veadk")

API_KEY = getenv(
    "MODEL_IMAGE_API_KEY",
    getenv("MODEL_AGENT_API_KEY", settings.model.api_key),
)
API_BASE = getenv("MODEL_IMAGE_API_BASE", DEFAULT_IMAGE_GENERATE_MODEL_API_BASE).rstrip(
    "/"
)


def _get_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "veadk-source": "veadk",
        "veadk-version": VERSION,
        "User-Agent": f"VeADK/{VERSION}",
        "X-Client-Request-Id": getenv("MODEL_AGENT_CLIENT_REQ_ID", f"veadk/{VERSION}"),
    }


def _build_request_body(item: dict, model_name: str) -> dict:
    body = {
        "model": model_name,
        "prompt": item.get("prompt", ""),
    }

    size = item.get("size")
    if size:
        body["size"] = size

    response_format = item.get("response_format")
    if response_format:
        body["response_format"] = response_format

    watermark = item.get("watermark")
    if watermark is not None:
        body["watermark"] = watermark

    image_field = item.get("image")
    if image_field is not None:
        body["image"] = image_field

    sequential_image_generation = item.get("sequential_image_generation")
    if sequential_image_generation:
        body["sequential_image_generation"] = sequential_image_generation

    max_images = item.get("max_images")
    if max_images is not None and sequential_image_generation == "auto":
        body["sequential_image_generation_options"] = {"max_images": max_images}

    tools = item.get("tools")
    if tools is not None:
        body["tools"] = tools

    output_format = item.get("output_format")
    if output_format:
        body["output_format"] = output_format

    return body


async def _call_image_api(
    item: dict,
    model_name: str,
    timeout: int,
) -> dict:
    url = f"{API_BASE}/images/generations"
    body = _build_request_body(item, model_name)

    async with httpx.AsyncClient(timeout=float(timeout)) as client:
        response = await client.post(url, headers=_get_headers(), json=body)
        if response.status_code >= 400:
            error_body = response.text
            logger.error(f"API Error {response.status_code}: {error_body}")
            logger.error(
                f"Request body: {json.dumps(body, ensure_ascii=False, indent=2)}"
            )
        response.raise_for_status()
        return response.json()


def add_span_attributes(
    span: Span,
    tool_context: ToolContext,
    input_part: dict = None,
    output_part: dict = None,
    input_tokens: int = None,
    output_tokens: int = None,
    total_tokens: int = None,
    request_model: str = None,
    response_model: str = None,
):
    try:
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

        span.set_attribute("gen_ai.system", "Ark")
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


async def handle_single_task(
    idx: int,
    item: dict,
    timeout: int,
    tool_context: ToolContext,
    model_name: str,
) -> tuple[list[dict], list[str], list[dict]]:
    logger.debug(f"handle_single_task item {idx}: {item}")
    success_list: list[dict] = []
    error_list: list[str] = []
    error_detail_list: list[dict] = []
    total_tokens = 0
    output_tokens = 0
    output_part = {"message.role": "model"}

    input_part = {"role": "user"}
    input_part["parts.0.type"] = "text"
    input_part["parts.0.text"] = json.dumps(item, ensure_ascii=False)

    with tracer.start_as_current_span(f"call_llm_task_{idx}") as span:
        try:
            response = await _call_image_api(item, model_name, timeout)

            if "error" not in response:
                logger.debug(f"task {idx} Image generate response: {response}")

                total_tokens += response.get("usage", {}).get("total_tokens", 0) or 0
                output_tokens += response.get("usage", {}).get("output_tokens", 0) or 0

                data_list = response.get("data", [])
                for i, image_data in enumerate(data_list):
                    image_name = f"task_{idx}_image_{i}"
                    if "error" in image_data:
                        logger.error(f"Image {image_name} error: {image_data.error}")
                        error_list.append(image_name)
                        error_detail_list.append(
                            {
                                "task_idx": idx,
                                "image_name": image_name,
                                "error": image_data.get("error"),
                            }
                        )
                        continue

                    image_url = image_data.get("url")
                    if not image_url:
                        b64 = image_data.get("b64_json")
                        if not b64:
                            logger.error(
                                f"Image {image_name} missing data (no url/b64)"
                            )
                            error_list.append(image_name)
                            error_detail_list.append(
                                {
                                    "task_idx": idx,
                                    "image_name": image_name,
                                    "error": "missing data (no url/b64)",
                                }
                            )
                            continue
                        image_bytes = base64.b64decode(b64)
                        image_url = _upload_image_to_tos(
                            image_bytes=image_bytes,
                            object_key=f"{image_name}.png",
                        )
                        if not image_url:
                            logger.error(f"Upload image to TOS failed: {image_name}")
                            error_list.append(image_name)
                            error_detail_list.append(
                                {
                                    "task_idx": idx,
                                    "image_name": image_name,
                                    "error": "upload to TOS failed",
                                }
                            )
                            continue
                        logger.debug(f"Image saved as ADK artifact: {image_name}")

                    tool_context.state[f"{image_name}_url"] = image_url
                    output_part[f"message.parts.{i}.type"] = "image_url"
                    output_part[f"message.parts.{i}.image_url.name"] = image_name
                    output_part[f"message.parts.{i}.image_url.url"] = image_url
                    logger.debug(
                        f"Image {image_name} generated successfully: {image_url}"
                    )
                    success_list.append({image_name: image_url})
            else:
                error_info = response.get("error", {})
                logger.error(f"Task {idx} No images returned by model: {error_info}")
                error_list.append(f"task_{idx}")
                error_detail_list.append(
                    {
                        "task_idx": idx,
                        "error": error_info,
                    }
                )

        except httpx.HTTPStatusError as e:
            error_text = e.response.text if e.response else str(e)
            logger.error(
                f"HTTP error in task {idx}: {e.response.status_code} - {error_text}"
            )
            error_list.append(f"task_{idx}")
            error_detail = {
                "task_idx": idx,
                "status_code": e.response.status_code if e.response else None,
            }
            try:
                error_detail["error"] = json.loads(error_text)
            except Exception:
                error_detail["error"] = error_text
            error_detail_list.append(error_detail)

        except Exception as e:
            logger.error(f"Error in task {idx}: {e}")
            traceback.print_exc()
            error_list.append(f"task_{idx}")
            error_detail_list.append(
                {
                    "task_idx": idx,
                    "error": str(e),
                }
            )

        finally:
            add_span_attributes(
                span,
                tool_context,
                input_part=input_part,
                output_part=output_part,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                request_model=model_name,
                response_model=model_name,
            )
    logger.debug(
        f"task {idx} Image generate success_list: {success_list}\nerror_list: {error_list}"
    )
    return success_list, error_list, error_detail_list


async def image_generate(
    tasks: list[dict],
    tool_context: ToolContext,
    timeout: int = 600,
    model_name: str = None,
) -> Dict:
    """Generate images with Seedream 4.0 / 4.5 / 5.0

    Commit batch image generation requests via tasks.

    Args:
        tasks (list[dict]):
            A list of image-generation tasks. Each task is a dict.
        timeout (int)
            The timeout limit for the image generation task request, in seconds, with a default value of 600 seconds.
        model_name (str):
            Optional model name. If not specified, use the default model from environment.
            If during execution, this tool encounters a model-related error (note that it must be a model-related error, otherwise do not perform this action), such as `ModelNotOpen`,
            then after reminding about the relevant issue, you can execute this tool again and downgrade the model to the following models, passing this parameter:
            - `doubao-seedream-5-0-260128`
            - `doubao-seedream-4-5-251128`
            - `doubao-seedream-4-0-250828`
    Per-task schema
    ---------------
    Required:
        - task_type (str):
            One of:
              * "multi_image_to_group"   # 多图生组图
              * "single_image_to_group"  # 单图生组图
              * "text_to_group"          # 文生组图
              * "multi_image_to_single"  # 多图生单图
              * "single_image_to_single" # 单图生单图
              * "text_to_single"         # 文生单图
        - prompt (str)
            Text description of the desired image(s). 中文/English 均可。
            若要指定生成图片的数量，请在prompt中添加"生成N张图片"，其中N为具体的数字。
    Optional:
        - size (str)
            指定生成图像的大小，有两种用法（二选一，不可混用）：
            方式 1：分辨率级别
                可选值: "1K", "2K", "4K"
                模型会结合 prompt 中的语义推断合适的宽高比、长宽。
            方式 2：具体宽高值
                格式: "<宽度>x<高度>"，如 "2048x2048", "2384x1728"
                约束:
                    * 总像素数范围: [1024x1024, 4096x4096]
                    * 宽高比范围: [1/16, 16]
                推荐值:
                    - 1:1   → 2048x2048
                    - 4:3   → 2384x1728
                    - 3:4   → 1728x2304
                    - 16:9  → 2560x1440
                    - 9:16  → 1440x2560
                    - 3:2   → 2496x1664
                    - 2:3   → 1664x2496
                    - 21:9  → 3024x1296
            默认值: "2048x2048"
        - response_format (str)
            Return format: "url" (default, URL 24h 过期) | "b64_json".
        - watermark (bool)
            Add watermark. Default: true.
        - image (str | list[str])   # 仅"非文生图"需要。文生图请不要提供 image
            Reference image(s) as URL or Base64.
            * 生成"单图"的任务：传入 string（exactly 1 image）。
            * 生成"组图"的任务：传入 array（2–10 images）。
        - sequential_image_generation (str)
            控制是否生成"组图"。Default: "disabled".
            * 若要生成组图：必须设为 "auto"。
        - max_images (int)
            仅当生成组图时生效。控制模型能生成的最多张数，范围 [1, 15]， 不设置默认为15。
            注意这个参数不等于生成的图片数量，而是模型最多能生成的图片数量。
            在单图组图场景最多 14；多图组图场景需满足 (len(images)+max_images ≤ 15)。
        - tools (list[dict])
            工具配置，用于增强生成能力。目前支持联网搜索工具。
            格式: [{"type": "web_search"}]
            注意：仅文生图（text_to_single / text_to_group）场景支持此参数，
            图生图场景（包含 image 参数）不支持使用 tools。
        - output_format (str)
            输出图片格式。枚举值: "png", "jpeg"。
            默认值: "jpeg"（不传时模型默认）。
            注意：仅 Seedream 5.0 支持该字段，存量模型指定会报错。
    Model 行为说明（如何由参数推断模式）
    ---------------------------------
    1) 文生单图: 不提供 image 且 (S 未设置或 S="disabled") → 1 张图。
    2) 文生组图: 不提供 image 且 S="auto" → 组图，数量由 max_images 控制。
    3) 单图生单图: image=string 且 (S 未设置或 S="disabled") → 1 张图。
    4) 单图生组图: image=string 且 S="auto" → 组图，数量 ≤14。
    5) 多图生单图: image=array (2–10) 且 (S 未设置或 S="disabled") → 1 张图。
    6) 多图生组图: image=array (2–10) 且 S="auto" → 组图，需满足总数 ≤15。
    返回结果
    --------
        Dict with generation summary.
        Example:
        {
            "status": "success",
            "success_list": [
                {"image_name": "url"}
            ],
            "error_list": ["image_name"],
            "error_detail_list": [
                {"task_idx": 0, "error": {"code": "InvalidParameter", "message": "..."}}
            ]
        }
    Notes:
    - 组图任务必须 sequential_image_generation="auto"。
    - 如果想要指定生成组图的数量，请在prompt里添加数量说明，例如："生成3张图片"。
    - size 推荐使用 2048x2048 或表格里的标准比例，确保生成质量。
    """
    model = model_name or getenv("MODEL_IMAGE_NAME", DEFAULT_IMAGE_GENERATE_MODEL_NAME)

    if model.startswith("doubao-seedream-3-0"):
        logger.error(
            f"Image generation by Doubao Seedream 3.0 ({model}) is deprecated. Please use Doubao Seedream 4.0 (e.g., doubao-seedream-4-0-250828) instead."
        )
        return {
            "status": "failed",
            "success_list": [],
            "error_list": [
                f"Image generation by Doubao Seedream 3.0 ({model}) is deprecated. Please use Doubao Seedream 4.0 (e.g., doubao-seedream-4-0-250828) instead."
            ],
            "error_detail_list": [
                {
                    "error": {
                        "code": "ModelDeprecated",
                        "message": f"Image generation by Doubao Seedream 3.0 ({model}) is deprecated. Please use Doubao Seedream 4.0 (e.g., doubao-seedream-4-0-250828) instead.",
                    }
                }
            ],
        }

    logger.debug(f"Using model to generate image: {model}")

    success_list: list[dict] = []
    error_list: list[str] = []
    error_detail_list: list[dict] = []

    logger.debug(f"image_generate tasks: {tasks}")

    with tracer.start_as_current_span("image_generate"):
        coroutines = [
            handle_single_task(idx, item, timeout, tool_context, model)
            for idx, item in enumerate(tasks)
        ]

        results = await asyncio.gather(*coroutines, return_exceptions=True)

        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Task raised exception: {res}")
                error_list.append("unknown_task_exception")
                error_detail_list.append(
                    {
                        "error": str(res),
                    }
                )
                continue
            s, e, ed = res
            success_list.extend(s)
            error_list.extend(e)
            error_detail_list.extend(ed)

    if not success_list:
        logger.debug(
            f"image_generate success_list: {success_list}\nerror_list: {error_list}\nerror_detail_list: {error_detail_list}"
        )
        return {
            "status": "error",
            "success_list": success_list,
            "error_list": error_list,
            "error_detail_list": error_detail_list,
        }
    app_name = tool_context._invocation_context.app_name
    user_id = tool_context._invocation_context.user_id
    session_id = tool_context._invocation_context.session.id
    artifact_service = tool_context._invocation_context.artifact_service

    if artifact_service:
        for image in success_list:
            for _, image_tos_url in image.items():
                filename = f"artifact_{formatted_timestamp()}"
                await artifact_service.save_artifact(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=session_id,
                    filename=filename,
                    artifact=Part(
                        inline_data=Blob(
                            display_name=filename,
                            data=read_file_to_bytes(image_tos_url),
                            mime_type="image/png",
                        )
                    ),
                )

    logger.debug(
        f"image_generate success_list: {success_list}\nerror_list: {error_list}\nerror_detail_list: {error_detail_list}"
    )
    return {
        "status": "success",
        "success_list": success_list,
        "error_list": error_list,
        "error_detail_list": error_detail_list,
    }


def _upload_image_to_tos(image_bytes: bytes, object_key: str) -> Optional[str]:
    try:
        import os
        from datetime import datetime

        from veadk.integrations.ve_tos.ve_tos import VeTOS

        timestamp: str = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
        object_key = f"{timestamp}-{object_key}"
        bucket_name = os.getenv("DATABASE_TOS_BUCKET")
        ve_tos = VeTOS()

        tos_url = ve_tos.build_tos_signed_url(
            object_key=object_key, bucket_name=bucket_name
        )

        ve_tos.upload_bytes(
            data=image_bytes, object_key=object_key, bucket_name=bucket_name
        )

        return tos_url
    except Exception as e:
        logger.error(f"Upload to TOS failed: {e}")
        return None
