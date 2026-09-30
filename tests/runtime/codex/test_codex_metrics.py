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

"""Codex business metrics: names, values, bounded attributes, best effort."""

from __future__ import annotations

import pytest
from opentelemetry import metrics as metrics_api
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from veadk.runtime.codex import metrics as codex_metrics

ALLOWED_ATTR_KEYS = {"outcome", "status", "transport", "kind"}


@pytest.fixture
def reader():
    """Inject a private SDK meter; the global MeterProvider is never touched."""
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    codex_metrics.set_meter_for_testing(provider.get_meter(codex_metrics.METER_NAME))
    yield reader
    codex_metrics.set_meter_for_testing(None)
    provider.shutdown()


def _points(reader, name):
    data = reader.get_metrics_data()
    out = []
    if data is None:
        return out
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == name:
                    for p in metric.data.data_points:
                        out.append((dict(p.attributes), p))
    return out


def _sums(reader, name):
    return {tuple(sorted(a.items())): p.value for a, p in _points(reader, name)}


def test_global_provider_untouched(reader):
    before = metrics_api.get_meter_provider()
    codex_metrics.record_resume("resumed")
    assert metrics_api.get_meter_provider() is before


def test_record_resume(reader):
    codex_metrics.record_resume("resumed")
    codex_metrics.record_resume("resumed")
    codex_metrics.record_resume("store_error")
    assert _sums(reader, codex_metrics.THREAD_RESUME) == {
        (("outcome", "resumed"),): 2,
        (("outcome", "store_error"),): 1,
    }


@pytest.mark.parametrize("outcome", sorted(codex_metrics.RESUME_OUTCOMES))
def test_all_resume_outcomes_kept(reader, outcome):
    codex_metrics.record_resume(outcome)
    assert _sums(reader, codex_metrics.THREAD_RESUME) == {(("outcome", outcome),): 1}


@pytest.mark.parametrize("outcome", sorted(codex_metrics.SAVE_OUTCOMES))
def test_record_save(reader, outcome):
    codex_metrics.record_save(outcome)
    assert _sums(reader, codex_metrics.THREAD_SAVE) == {(("outcome", outcome),): 1}


def test_record_turn_counts_and_duration(reader):
    codex_metrics.record_turn("completed", "direct", 2.5)
    codex_metrics.record_turn("timeout", "shim", 30)
    assert _sums(reader, codex_metrics.TURN) == {
        (("status", "completed"), ("transport", "direct")): 1,
        (("status", "timeout"), ("transport", "shim")): 1,
    }
    hist = {
        tuple(sorted(a.items())): (p.count, p.sum)
        for a, p in _points(reader, codex_metrics.TURN_DURATION)
    }
    assert hist == {
        (("status", "completed"), ("transport", "direct")): (1, 2.5),
        (("status", "timeout"), ("transport", "shim")): (1, 30.0),
    }


@pytest.mark.parametrize("bad", [None, -1, float("nan"), float("inf"), "3", True])
def test_record_turn_invalid_duration_still_counts(reader, bad):
    codex_metrics.record_turn("failed", "direct", bad)
    assert _sums(reader, codex_metrics.TURN) == {
        (("status", "failed"), ("transport", "direct")): 1
    }
    assert _points(reader, codex_metrics.TURN_DURATION) == []


def test_record_startup(reader):
    codex_metrics.record_startup("shim", 0.75)
    codex_metrics.record_startup("direct", None)
    pts = _points(reader, codex_metrics.TURN_STARTUP)
    assert [(a, p.count, p.sum) for a, p in pts] == [({"transport": "shim"}, 1, 0.75)]


def test_record_tokens(reader):
    codex_metrics.record_tokens(
        "direct",
        {
            "input_tokens": 100,
            "output_tokens": 20,
            "cached_input_tokens": 60,
            "reasoning_output_tokens": 5,
            "total_tokens": 125,
        },
    )
    codex_metrics.record_tokens("direct", {"input_tokens": 1})
    assert _sums(reader, codex_metrics.TURN_TOKENS) == {
        (("kind", "input"), ("transport", "direct")): 101,
        (("kind", "output"), ("transport", "direct")): 20,
        (("kind", "cached_input"), ("transport", "direct")): 60,
        (("kind", "reasoning_output"), ("transport", "direct")): 5,
    }


def test_record_tokens_ignores_missing_and_non_int(reader):
    codex_metrics.record_tokens(
        "shim",
        {
            "input_tokens": "10",
            "output_tokens": 3.5,
            "cached_input_tokens": True,
            "reasoning_output_tokens": -4,
        },
    )
    codex_metrics.record_tokens("shim", None)
    codex_metrics.record_tokens("shim", ["input_tokens"])
    codex_metrics.record_tokens("shim", {"output_tokens": 7})
    assert _sums(reader, codex_metrics.TURN_TOKENS) == {
        (("kind", "output"), ("transport", "shim")): 7
    }


def test_unknown_values_become_other(reader):
    codex_metrics.record_resume("sess-1234")
    codex_metrics.record_save(None)
    codex_metrics.record_turn("weird", "grpc", 1)
    codex_metrics.record_startup(42, 1)
    codex_metrics.record_tokens("thread-abc", {"input_tokens": 1})
    assert _sums(reader, codex_metrics.THREAD_RESUME) == {(("outcome", "other"),): 1}
    assert _sums(reader, codex_metrics.THREAD_SAVE) == {(("outcome", "other"),): 1}
    assert _sums(reader, codex_metrics.TURN) == {
        (("status", "other"), ("transport", "other")): 1
    }
    assert [a for a, _ in _points(reader, codex_metrics.TURN_STARTUP)] == [
        {"transport": "other"}
    ]
    assert _sums(reader, codex_metrics.TURN_TOKENS) == {
        (("kind", "input"), ("transport", "other")): 1
    }


def test_no_id_like_attributes(reader):
    codex_metrics.record_resume("resumed")
    codex_metrics.record_save("saved")
    codex_metrics.record_turn("completed", "direct", 1)
    codex_metrics.record_startup("direct", 1)
    codex_metrics.record_tokens("direct", {"input_tokens": 1, "session_id": 9})
    names = [
        codex_metrics.THREAD_RESUME,
        codex_metrics.THREAD_SAVE,
        codex_metrics.TURN,
        codex_metrics.TURN_DURATION,
        codex_metrics.TURN_STARTUP,
        codex_metrics.TURN_TOKENS,
    ]
    for name in names:
        pts = _points(reader, name)
        assert pts, name
        for attrs, _ in pts:
            assert set(attrs) <= ALLOWED_ATTR_KEYS
            assert not any("id" in key for key in attrs)


def test_instruments_created_once(monkeypatch):
    calls = []

    class _Meter:
        def __getattr__(self, attr):
            def create(**kwargs):
                calls.append(kwargs["name"])
                return type(
                    "I", (), {"add": lambda *a: None, "record": lambda *a: None}
                )()

            return create

    codex_metrics.set_meter_for_testing(_Meter())
    try:
        for _ in range(3):
            codex_metrics.record_resume("resumed")
            codex_metrics.record_turn("completed", "direct", 1)
        assert sorted(calls) == sorted(
            [
                codex_metrics.THREAD_RESUME,
                codex_metrics.THREAD_SAVE,
                codex_metrics.TURN,
                codex_metrics.TURN_DURATION,
                codex_metrics.TURN_STARTUP,
                codex_metrics.TURN_TOKENS,
            ]
        )
    finally:
        codex_metrics.set_meter_for_testing(None)


def test_helpers_never_raise_when_instruments_raise(reader, monkeypatch):
    codex_metrics.record_resume("resumed")  # force instrument creation
    inst = codex_metrics._get()

    def boom(*args, **kwargs):
        raise RuntimeError("sdk broken")

    for attr in ("resume", "save", "turn", "turn_duration", "startup", "tokens"):
        instrument = getattr(inst, attr)
        method = "record" if attr in ("turn_duration", "startup") else "add"
        monkeypatch.setattr(instrument, method, boom)
        with pytest.raises(RuntimeError):
            getattr(instrument, method)(1, {})

    codex_metrics.record_resume("resumed")
    codex_metrics.record_save("saved")
    codex_metrics.record_turn("completed", "direct", 1)
    codex_metrics.record_startup("direct", 1)
    codex_metrics.record_tokens("direct", {"input_tokens": 1})


def test_helpers_never_raise_when_meter_creation_fails():
    class _BadMeter:
        def __getattr__(self, attr):
            raise RuntimeError("no meter")

    codex_metrics.set_meter_for_testing(_BadMeter())
    try:
        codex_metrics.record_resume("resumed")
        codex_metrics.record_save("saved")
        codex_metrics.record_turn("completed", "direct", 1)
        codex_metrics.record_startup("direct", 1)
        codex_metrics.record_tokens("direct", {"input_tokens": 1})
    finally:
        codex_metrics.set_meter_for_testing(None)


def test_noop_without_configured_provider():
    """With the default proxy provider the helpers run and record nothing."""
    codex_metrics.set_meter_for_testing(None)
    codex_metrics.record_turn("completed", "direct", 1)
    codex_metrics.record_tokens("direct", {"input_tokens": 1})
