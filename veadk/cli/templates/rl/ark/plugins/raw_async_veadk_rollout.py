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
import asyncio
from typing import Optional, Any, cast
from loguru import logger
from ark_sdk.resources.pipeline_plugin import rollout
from ark_sdk.types.pipeline_plugin import PluginInstance, Runtime
from ark_sdk.types.pipeline_plugin.pipeline_plugin import PluginContext
from ark_sdk.core.plugin.rollout.trace import coze_monitor
from ark_sdk.types.pipeline_plugin.rollout import (
    ChatCompletionSample,
    ChatCompletionResponse,
    RolloutInferenceProxy,
    RolloutResult,
    PluginStatus,
)
from veadk.agent import Agent
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runner import Runner
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporter
from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporterConfig
from google.adk.models.lite_llm import LiteLLMClient, LiteLlm
from litellm import ModelResponse
from cozeloop.decorator import observe

# BASE_MODEL 格式 : "{model_provider}/{model_name}"
BASE_MODEL = "openai/doubao-seed-1-6-flash-250615"

# 可自定义veadk agent的观测器配置
coze_config = CozeloopExporterConfig(
    endpoint="",
    space_id="",
    token="",
)
exporters = [CozeloopExporter(config=coze_config)]
tracer = OpentelemetryTracer(exporters=cast(Any, exporters))


@observe()
def get_current_weather(location: str, unit="摄氏度"):
    # 实际调用天气查询 API 的逻辑
    # 此处为示例，返回模拟的天气数据
    return f"{location}今天天气晴朗，温度 25 {unit}。"


class RecordingLiteLlm(LiteLlm):
    """
    在调用 LiteLlm 的 completion/acompletion 时，拦截并记录原始 ModelResponse。

    功能要点：
    - 保存最近一次模型响应到 self._last；
    - 将所有响应追加到 self._history（按调用顺序保存）；
    - 通过 get_last_model_response() / get_response_history() 读取记录结果。
    """

    def __init__(self, model: str, **kwargs):
        super().__init__(model=model, **kwargs)
        self._last: Optional[ModelResponse] = None
        self._history: list[ModelResponse] = []

        class _RecordingClient(LiteLLMClient):
            def __init__(self, outer: "RecordingLiteLlm"):
                self._outer = outer

            async def acompletion(self, *args, **kwargs):
                raw: ModelResponse = await super().acompletion(*args, **kwargs)
                self._outer._history.append(raw)
                self._outer._last = raw
                return raw

            def completion(self, *args, **kwargs):
                raw: ModelResponse = super().completion(*args, **kwargs)
                self._outer._history.append(raw)
                self._outer._last = raw
                return raw

        self.llm_client = _RecordingClient(self)

    def get_last_model_response(self) -> Optional[ModelResponse]:
        return self._last

    def get_response_history(self) -> list[ModelResponse]:
        return self._history


def _ensure_str_content(content) -> str:
    """
    将任意形式的 content 转为字符串:
    - 如果是 list[ {type,text/...} ] 试图拼接其中的 text 或 content 字段
    - 如果是 dict/list 做 JSON 序列化兜底
    - 其它直接 str()
    """
    if isinstance(content, list):
        # 尝试提取文本字段
        parts = []
        for item in content:
            if isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item["text"]))
                elif "content" in item:
                    parts.append(str(item["content"]))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if isinstance(content, (dict, tuple, set)):
        try:
            return json.dumps(content, ensure_ascii=False)
        except Exception:
            return str(content)
    return "" if content is None else str(content)


def _get_last_message_content(messages) -> str:
    if not messages:
        return ""
    last = messages[-1]
    if isinstance(last, dict):
        return _ensure_str_content(last.get("content"))
    return _ensure_str_content(last)


@rollout(
    name="demo_veadk_rollout",
    description="Demo rollout plugin using VEADK for async execution",
    runtime=Runtime(
        instance=PluginInstance.CPU1MEM2,
        max_concurrency=100,
        min_replicas=1,
        max_replicas=10,
        timeout=900,
    ),
)
@coze_monitor
async def demo_veadk_rollout(
    context: PluginContext,
    proxy: RolloutInferenceProxy,
    sample: ChatCompletionSample,
) -> Optional[RolloutResult]:
    # 创建veadk_agent
    # 创建litellm model实例
    model_instance = RecordingLiteLlm(
        model=BASE_MODEL,
        api_base=proxy.url,
        api_key=proxy.jwt_token,
        model_provider="openai",
        logprobs=False,
        extra_headers=proxy.headers,
        extra_body=proxy.get_extra_body(),
    )
    # 创建agent
    agent = Agent(
        name="WeatherAgent",
        description="A demo agent for weather information",
        instruction="You are a weather assistant",
        model_provider="openai",
        model_api_key=proxy.jwt_token,
        tracers=[tracer],
        model=model_instance,
    )

    # 初始化Runner
    app_name = "WeatherAgent"
    runner = Runner(
        agent=agent,
        short_term_memory=ShortTermMemory(),
        app_name=app_name,
        user_id="veadk_default_user",
        upload_inline_data_to_tos=False,
    )

    # 获取数据
    req = sample.model_dump()
    messages = req.pop("messages")

    while True:
        proxy.update_state_from_messages(messages)
        # 取最近一条消息作为输入
        last_content = _get_last_message_content(messages)

        _ = await runner.run(
            session_id="123456",
            messages=last_content,
            save_tracing_data=True,
            upload_inline_data_to_tos=True,
        )

        # 获得完整模型响应
        model_response = model_instance.get_last_model_response()
        model_response_dict = model_response.model_dump()
        choices = model_response_dict.get("choices") or []
        if choices:
            if choices[0] is None:
                choices[0] = {}
            first_choice = choices[0]
            psf = first_choice.get("provider_specific_fields")
            if isinstance(psf, dict):
                for k, v in psf.items():
                    if k not in first_choice:
                        first_choice[k] = v
                first_choice.pop("provider_specific_fields", None)

        chat_completion_response = ChatCompletionResponse(**model_response_dict)

        # NOTE: 强化学习特殊逻辑
        proxy.process_completion(chat_completion_response)
        messages.append(model_response.choices[0].message.model_dump())

        if model_response.choices[0].finish_reason != "tool_calls":
            # 模型最终总结，没有调用工具意愿
            break
        tool_calls = model_response.choices[0].message.tool_calls
        for tool_call in tool_calls or []:
            tool_name = tool_call.function.name
            if tool_name == "get_current_weather":
                try:
                    args = json.loads(tool_call.function.arguments)
                    tool_result = get_current_weather(**args)
                except Exception as e:
                    logger.error(f"get_current_weather error: {e}")
                    return RolloutResult(
                        status=PluginStatus.SUCCESS,
                        extra={
                            "reward": -1,
                        },
                    )
                # 将工具结果加入消息列表
                messages.append(
                    {
                        "role": "tool",
                        "content": tool_result,
                        "tool_call_id": tool_call.id,
                    }
                )
    # 默认return None则视为rollout成功
    return None


# 仅用做本地测试
async def main():
    from ark_sdk.core.plugin.rollout.proxy import InferenceProxy, Mode

    # 调试模式，使用公共服务
    mode = Mode.Inference
    base_url = ""
    api_key = ""

    sample = ChatCompletionSample(
        **{
            "model": "doubao-seed-1-6-flash-250615",
            "messages": [
                {
                    "role": "user",
                    "content": "北京天气",
                }
            ],
        }
    )
    proxy = InferenceProxy(
        sample,
        url=base_url,
        jwt_token=api_key,
        mode=mode,
    )

    await demo_veadk_rollout({}, proxy, sample)


if __name__ == "__main__":
    import cozeloop
    import asyncio

    try:
        asyncio.run(main())
    finally:
        cozeloop.close()
