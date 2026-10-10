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

"""Record retrieval boundaries through the existing telemetry provider."""

from collections.abc import Iterator
from contextlib import contextmanager, suppress

from opentelemetry import context, trace
from opentelemetry.trace import Status, StatusCode

_ALLOWED_ATTRIBUTES = frozenset(
    {
        "veadk.retrieval.backend",
        "veadk.retrieval.top_k",
        "veadk.retrieval.result_count",
        "veadk.memory.event_count",
        "session.id",
    }
)


class RetrievalOperation:
    def __init__(self, span: trace.Span | None):
        self._span = span

    def set_attribute(self, key: str, value: str | int) -> None:
        if self._span is not None and key in _ALLOWED_ATTRIBUTES:
            with suppress(Exception):
                self._span.set_attribute(key, value)

    def fail(self, error: BaseException) -> None:
        if self._span is not None:
            # Error messages can contain queries or credentials; retain only type.
            with suppress(Exception):
                self._span.set_attribute("error.type", type(error).__name__)
                self._span.set_status(Status(StatusCode.ERROR))


@contextmanager
def retrieval_span(name: str, *, backend: str) -> Iterator[RetrievalOperation]:
    span = None
    token = None
    try:
        span = trace.get_tracer("veadk.retrieval").start_span(name)
        token = context.attach(trace.set_span_in_context(span))
    except Exception:
        # Telemetry setup must never rerun or prevent the backend operation.
        pass
    operation = RetrievalOperation(span)
    operation.set_attribute("veadk.retrieval.backend", backend)
    try:
        yield operation
    except BaseException as error:
        operation.fail(error)
        raise
    finally:
        if token is not None:
            with suppress(Exception):
                context.detach(token)
        if span is not None:
            with suppress(Exception):
                span.end()
