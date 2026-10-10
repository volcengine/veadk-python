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

"""Codex Shim 的模型请求计时，不收集请求或响应正文。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
except ImportError:
    # 与 Shim 的可选观测依赖保持一致，未安装时仍可执行模型请求。
    trace = None

T = TypeVar("T")


async def trace_model_request(call: Callable[[], Awaitable[T]]) -> T:
    if trace is None:
        return await call()
    # 每次库调用独立计时；库内部重试仍包含在该调用中，不冒充底层 HTTP 尝试。
    tracer = trace.get_tracer("veadk.codex.model")
    with tracer.start_as_current_span(
        "codex.model.request",
        attributes={
            "gen_ai.operation.name": "chat",
            "veadk.runtime": "codex",
            "veadk.model.request.scope": "litellm.aresponses",
        },
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            return await call()
        except BaseException as error:
            # 异常正文可能含 Endpoint、提示词或凭证；只记录类型，保留取消语义。
            span.set_attribute("error.type", type(error).__name__)
            span.set_status(Status(StatusCode.ERROR))
            raise
