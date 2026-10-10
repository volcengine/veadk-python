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


"""远端 Worker 调用的脱敏计时和 W3C 上下文透传。"""

from contextlib import contextmanager

try:
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind, Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )
except ImportError:
    trace = None


def operation_name(method, path):
    # 路由只保留操作类别；Session / Turn ID、查询参数和 Endpoint 不进入 Span 名称。
    if path == "/readyz":
        return "ready"
    if path == "/sessions":
        return "session.create"
    if path.endswith("/events"):
        return "turn.events"
    if path.endswith("/cancel"):
        return "turn.cancel"
    if path.endswith("/turns"):
        return "turn.start"
    if method == "GET" and "/turns/" in path:
        return "turn.status"
    return "request"


@contextmanager
def worker_request_span(method, path, *, activate=True):
    if trace is None:
        yield {}, None
        return
    tracer = trace.get_tracer("veadk.worker.client")
    # Streaming generators must not hold ambient context while yielding to callers.
    factory = tracer.start_as_current_span if activate else tracer.start_span
    with factory(
        "worker." + operation_name(method, path),
        kind=SpanKind.CLIENT,
        attributes={"http.request.method": method},
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        headers = {}
        # 只透传 W3C Trace 上下文，避免全局 propagator 自动带出 baggage 或业务正文。
        TraceContextTextMapPropagator().inject(
            headers, context=trace.set_span_in_context(span)
        )
        try:
            yield headers, span
        except BaseException as error:
            span.set_attribute("error.type", type(error).__name__)
            span.set_status(Status(StatusCode.ERROR))
            raise
