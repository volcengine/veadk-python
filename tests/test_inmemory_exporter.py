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

import gc
import weakref
from concurrent.futures import ThreadPoolExecutor

import pytest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.trace import Link, SpanContext, TraceFlags

from veadk.tracing.telemetry.exporters.inmemory_exporter import _InMemoryExporter


def make_span(number, *, session="session", trace_id=None, name="call_llm", **kwargs):
    context = SpanContext(
        trace_id=trace_id or number,
        span_id=number,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    attributes = kwargs.pop("attributes", {"gen_ai.session.id": session})
    return ReadableSpan(name=name, context=context, attributes=attributes, **kwargs)


def test_default_retention_is_bounded_and_releases_old_spans():
    exporter = _InMemoryExporter()
    old = make_span(1)
    reference = weakref.ref(old)
    exporter.export([old])
    del old
    for number in range(2, 1200):
        exporter.export([make_span(number)])
    gc.collect()
    assert reference() is None
    assert len(exporter.get_finished_spans("session")) == 1024
    assert len(exporter.session_trace_dict["session"]) == 1024


def test_fifo_eviction_preserves_session_filtering_and_related_spans():
    exporter = _InMemoryExporter(max_spans=3)
    exporter.export([make_span(1, session="old")])
    anchor = make_span(2, trace_id=20)
    related = make_span(3, trace_id=20, name="invoke", attributes={})
    other = make_span(4, session="other")
    exporter.export([anchor, related, other])
    assert "old" not in exporter.session_trace_dict
    assert exporter.get_finished_spans("session") == [anchor, related]
    snapshot = exporter.get_finished_spans("session")
    snapshot.clear()
    assert exporter.get_finished_spans("session") == [anchor, related]
    assert exporter.get_finished_spans("other") == [other]


def test_session_index_is_deduplicated_and_disappears_with_evicted_anchors():
    exporter = _InMemoryExporter(max_spans=3)
    exporter.export([make_span(n, trace_id=1) for n in range(1, 4)])
    assert exporter.session_trace_dict == {"session": [1]}
    exporter.export([make_span(n, session="new") for n in range(4, 7)])
    assert "session" not in exporter.session_trace_dict


def test_byte_budget_evicts_large_responses_before_count_limit():
    exporter = _InMemoryExporter(max_spans=100, max_bytes=16 * 1024)
    refs = []
    for number in range(1, 30):
        span = make_span(
            number,
            attributes={
                "gen_ai.session.id": "session",
                "gen_ai.output": str(number) + "x" * 6000,
            },
        )
        refs.append(weakref.ref(span))
        exporter.export([span])
    del span
    gc.collect()
    retained = exporter.get_finished_spans("session")
    assert 0 < len(retained) < 3
    assert refs[0]() is None
    assert retained[-1].context.span_id == 29
    assert exporter._retained_bytes <= 16 * 1024


@pytest.mark.parametrize("location", ["attributes", "events", "links", "resource"])
def test_oversized_span_is_skipped_without_mutation_or_eviction(location):
    exporter = _InMemoryExporter(max_bytes=16 * 1024)
    previous = make_span(1)
    exporter.export([previous])
    payload = "large" * 20000
    values = {"gen_ai.output": payload}
    kwargs = {
        "attributes": {"attributes": values},
        "events": {"events": [Event("event", attributes=values)]},
        "links": {"links": [Link(previous.context, attributes=values)]},
        "resource": {"resource": Resource(values)},
    }[location]
    huge = make_span(2, **kwargs)
    exporter.export([huge])
    assert list(exporter._spans) == [previous]
    assert exporter.trace_id == 2
    if location == "attributes":
        assert huge.attributes["gen_ai.output"] == payload


@pytest.mark.parametrize("limits", [{"max_spans": 0}, {"max_bytes": 0}])
def test_zero_limit_preserves_latest_trace_id_without_retention(limits):
    exporter = _InMemoryExporter(**limits)
    exporter.export([make_span(1), make_span(2)])
    assert exporter.get_finished_spans("session") == []
    assert exporter.session_trace_dict == {}
    assert exporter.trace_id == 2


def test_clear_and_shutdown_release_all_cache_state():
    exporter = _InMemoryExporter()
    exporter.export([make_span(1)])
    exporter.clear()
    assert list(exporter._spans) == []
    assert exporter.session_trace_dict == {}
    assert exporter.trace_id == ""
    assert exporter._retained_bytes == 0
    exporter.export([make_span(2)])
    assert exporter.get_finished_spans("session")
    exporter.shutdown()
    exporter.export([make_span(3)])
    assert list(exporter._spans) == []
    assert exporter.session_trace_dict == {}
    assert exporter.trace_id == ""
    assert exporter._retained_bytes == 0


def test_concurrent_export_read_and_clear_remain_consistent():
    exporter = _InMemoryExporter(max_spans=32, max_bytes=64 * 1024)

    def export_spans():
        for n in range(1, 500):
            exporter.export([make_span(n)])

    def read_spans():
        for _ in range(200):
            assert len(exporter.get_finished_spans("session")) <= 32

    def clear_spans():
        for _ in range(100):
            exporter.clear()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(fn)
            for fn in (export_spans, export_spans, read_spans, clear_spans)
        ]
        for future in futures:
            future.result()
    assert len(exporter._spans) <= 32
    assert 0 <= exporter._retained_bytes <= 64 * 1024
    assert exporter._retained_bytes == sum(exporter._span_sizes)
