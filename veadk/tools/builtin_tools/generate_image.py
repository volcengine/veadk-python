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

import base64
import json
import mimetypes
import traceback
from typing import Dict

from google.adk.tools import ToolContext
from google.genai.types import Blob, Part
from opentelemetry import trace
from opentelemetry.trace import Span
from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime.types.images.images import SequentialImageGenerationOptions

from veadk.config import getenv
from veadk.consts import DEFAULT_IMAGE_GENERATE_MODEL_NAME, DEFAULT_MODEL_AGENT_API_BASE
from veadk.utils.logger import get_logger
from veadk.utils.misc import formatted_timestamp, read_file_to_bytes
from veadk.version import VERSION

logger = get_logger(__name__)

client = Ark(
    api_key=getenv("MODEL_AGENT_API_KEY"),
    base_url=getenv("MODEL_AGENT_API_BASE", DEFAULT_MODEL_AGENT_API_BASE),
)


async def image_generate(
    tasks: list,
    tool_context: ToolContext,
) -> Dict:
    """
    Seedream 4.0: batch image generation via tasks.
    Args:
        tasks (list[dict]):
            A list of image-generation tasks. Each task is a dict.
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
        - image (str | list[str])   # 仅“非文生图”需要。文生图请不要提供 image
            Reference image(s) as URL or Base64.
            * 生成“单图”的任务：传入 string（exactly 1 image）。
            * 生成“组图”的任务：传入 array（2–10 images）。
        - sequential_image_generation (str)
            控制是否生成“组图”。Default: "disabled".
            * 若要生成组图：必须设为 "auto"。
        - max_images (int)
            仅当生成组图时生效。控制模型能生成的最多张数，范围 [1, 15]， 不设置默认为15。
            注意这个参数不等于生成的图片数量，而是模型最多能生成的图片数量。
            在单图组图场景最多 14；多图组图场景需满足 (len(images)+max_images ≤ 15)。
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
            "error_list": ["image_name"]
        }
    Notes:
    - 组图任务必须 sequential_image_generation="auto"。
    - 如果想要指定生成组图的数量，请在prompt里添加数量说明，例如："生成3张图片"。
    - size 推荐使用 2048x2048 或表格里的标准比例，确保生成质量。
    """

    success_list: list[dict] = []
    error_list = []

    for idx, item in enumerate(tasks):
        input_part = {"role": "user"}
        output_part = {"message.role": "model"}
        total_tokens = 0
        output_tokens = 0
        tracer = trace.get_tracer("gcp.vertex.agent")
        with tracer.start_as_current_span("call_llm") as span:
            task_type = item.get("task_type", "text_to_single")
            prompt = item.get("prompt", "")
            response_format = item.get("response_format", None)
            size = item.get("size", None)
            watermark = item.get("watermark", None)
            image = item.get("image", None)
            sequential_image_generation = item.get("sequential_image_generation", None)
            max_images = item.get("max_images", None)

            input_part["parts.0.type"] = "text"
            input_part["parts.0.text"] = json.dumps(item, ensure_ascii=False)
            inputs = {
                "prompt": prompt,
            }

            if size:
                inputs["size"] = size
            if response_format:
                inputs["response_format"] = response_format
            if watermark:
                inputs["watermark"] = watermark
            if image:
                if task_type.startswith("single"):
                    assert isinstance(image, str), (
                        f"single_* task_type image must be str, got {type(image)}"
                    )
                    input_part["parts.1.type"] = "image_url"
                    input_part["parts.1.image_url.name"] = "origin_image"
                    input_part["parts.1.image_url.url"] = image
                elif task_type.startswith("multi"):
                    assert isinstance(image, list), (
                        f"multi_* task_type image must be list, got {type(image)}"
                    )
                    assert len(image) <= 10, (
                        f"multi_* task_type image list length must be <= 10, got {len(image)}"
                    )
                    for i, image_url in enumerate(image):
                        input_part[f"parts.{i + 1}.type"] = "image_url"
                        input_part[f"parts.{i + 1}.image_url.name"] = (
                            f"origin_image_{i}"
                        )
                        input_part[f"parts.{i + 1}.image_url.url"] = image_url

            if sequential_image_generation:
                inputs["sequential_image_generation"] = sequential_image_generation

            try:
                if (
                    sequential_image_generation
                    and sequential_image_generation == "auto"
                    and max_images
                ):
                    response = client.images.generate(
                        model=getenv(
                            "MODEL_IMAGE_NAME", DEFAULT_IMAGE_GENERATE_MODEL_NAME
                        ),
                        **inputs,
                        sequential_image_generation_options=SequentialImageGenerationOptions(
                            max_images=max_images
                        ),
                    )
                else:
                    response = client.images.generate(
                        model=getenv(
                            "MODEL_IMAGE_NAME", DEFAULT_IMAGE_GENERATE_MODEL_NAME
                        ),
                        **inputs,
                    )
                if not response.error:
                    for i, image_data in enumerate(response.data):
                        image_name = f"task_{idx}_image_{i}"
                        if "error" in image_data:
                            error_details = (
                                f"Image {image_name} error: {image_data.error}"
                            )
                            logger.error(error_details)
                            error_list.append(image_name)
                            continue
                        if image_data.url:
                            image = image_data.url
                            tool_context.state[f"{image_name}_url"] = image

                            output_part[f"message.parts.{i}.type"] = "image_url"
                            output_part[f"message.parts.{i}.image_url.name"] = (
                                image_name
                            )
                            output_part[f"message.parts.{i}.image_url.url"] = image

                        else:
                            image = image_data.b64_json
                            image_bytes = base64.b64decode(image)

                            tos_url = _upload_image_to_tos(
                                image_bytes=image_bytes, object_key=f"{image_name}.png"
                            )
                            if tos_url:
                                tool_context.state[f"{image_name}_url"] = tos_url
                                image = tos_url
                                output_part[f"message.parts.{i}.type"] = "image_url"
                                output_part[f"message.parts.{i}.image_url.name"] = (
                                    image_name
                                )
                                output_part[f"message.parts.{i}.image_url.url"] = image
                            else:
                                logger.error(
                                    f"Upload image to TOS failed: {image_name}"
                                )
                                error_list.append(image_name)
                                continue

                            logger.debug(f"Image saved as ADK artifact: {image_name}")

                        total_tokens += response.usage.total_tokens
                        output_tokens += response.usage.output_tokens
                        success_list.append({image_name: image})
                else:
                    error_details = (
                        f"No images returned by Doubao model: {response.error}"
                    )
                    logger.error(error_details)
                    error_list.append(f"task_{idx}")

            except Exception as e:
                error_details = f"Error: {e}"
                logger.error(error_details)
                traceback.print_exc()
                error_list.append(f"task_{idx}")

            add_span_attributes(
                span,
                tool_context,
                input_part=input_part,
                output_part=output_part,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                request_model=getenv(
                    "MODEL_IMAGE_NAME", DEFAULT_IMAGE_GENERATE_MODEL_NAME
                ),
                response_model=getenv(
                    "MODEL_IMAGE_NAME", DEFAULT_IMAGE_GENERATE_MODEL_NAME
                ),
            )
    if len(success_list) == 0:
        return {
            "status": "error",
            "success_list": success_list,
            "error_list": error_list,
        }
    else:
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
                                mime_type=mimetypes.guess_type(image_tos_url)[0],
                            )
                        ),
                    )
        return {
            "status": "success",
            "success_list": success_list,
            "error_list": error_list,
        }


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


def _upload_image_to_tos(image_bytes: bytes, object_key: str) -> None:
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
