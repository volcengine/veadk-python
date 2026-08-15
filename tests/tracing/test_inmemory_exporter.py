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

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from veadk.tracing.telemetry.exporters.inmemory_exporter import (
    _InMemoryExporter,
    _InMemorySpanProcessor,
)


def test_processor_preserves_nested_agent_trace_context():
    exporter = _InMemoryExporter()
    provider = TracerProvider()
    provider.add_span_processor(_InMemorySpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)
    initial_span = trace.get_current_span()

    invocation_span = tracer.start_span("invocation root")
    try:
        assert trace.get_current_span() is invocation_span
        parent_span = tracer.start_span("agent_run parent")
        try:
            assert trace.get_current_span() is parent_span
            child_span = tracer.start_span("agent_run child")
            try:
                assert trace.get_current_span() is child_span
                assert child_span.parent == parent_span.get_span_context()
                assert parent_span.parent == invocation_span.get_span_context()
                assert child_span.get_span_context().trace_id == (
                    parent_span.get_span_context().trace_id
                )
                assert parent_span.get_span_context().trace_id == (
                    invocation_span.get_span_context().trace_id
                )
            finally:
                child_span.end()
            assert trace.get_current_span() is parent_span
        finally:
            parent_span.end()
        assert trace.get_current_span() is invocation_span
    finally:
        invocation_span.end()

    assert trace.get_current_span() is initial_span
