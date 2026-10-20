import asyncio
import zipfile
from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.adk.tools.skill_toolset import LoadSkillTool, SkillToolset
from google.genai import types
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from veadk.skills import materializer, registry
from veadk.skills import telemetry as skill_telemetry
from veadk.skills.skill import Skill
from veadk.tracing.telemetry import portal_metrics, telemetry


@pytest.fixture
def observation(monkeypatch):
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    exporter = InMemorySpanExporter()
    spans = TracerProvider()
    spans.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(metrics, "get_meter", provider.get_meter)
    monkeypatch.setattr(
        portal_metrics, "portal_metric_recorder", portal_metrics.PortalMetricRecorder()
    )
    monkeypatch.setattr(trace, "get_tracer", spans.get_tracer)
    yield reader, exporter
    provider.shutdown()
    spans.shutdown()


def points(reader, name):
    data = reader.get_metrics_data()
    return [
        (dict(point.attributes), point.value)
        for resource in (data.resource_metrics if data else [])
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == name
        for point in metric.data.data_points
    ]


@pytest.fixture
def remote(monkeypatch):
    skill = Skill(
        name="demo",
        description="Demo",
        path="demo",
        id="s-demo",
        skill_space_id="sp-one",
        source_type="skillhub",
        version_id="sv-one",
    )
    calls = []

    def download(skill, path):
        calls.append(skill.id)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "SKILL.md", "---\nname: demo\ndescription: Demo\n---\nInstructions"
            )
        return True

    monkeypatch.setattr(materializer, "download_skillhub_skill", download)
    monkeypatch.setattr(registry, "load_skills_from_cloud", lambda _: [skill])
    return skill, calls


def test_download_cache_and_corruption(observation, remote, tmp_path):
    skill, calls = remote
    path = materializer.materialize_remote_skill(skill, cache_dir=tmp_path)
    materializer.materialize_remote_skill(skill, cache_dir=tmp_path)
    (path / "SKILL.md").write_text("invalid")
    materializer.materialize_remote_skill(skill, cache_dir=tmp_path)
    assert calls == ["s-demo", "s-demo"]
    labels = {
        "skill_source": "skillhub_skill_space",
        "skill_id": "s-demo",
        "skill_version": "sv-one",
        "skill_space_id": "sp-one",
        "outcome": "success",
    }
    assert points(observation[0], "gen_ai_skill_download") == [(labels, 3)]
    spans = observation[1].get_finished_spans()
    assert [s.attributes["cache_hit"] for s in spans] == [False, True, False]
    assert all(
        s.name == "skill_download" and s.attributes["consumer"] == "runtime"
        for s in spans
    )


def test_download_error_does_not_export_exception_text(
    observation, remote, tmp_path, monkeypatch
):
    skill, _ = remote
    secret = "https://example.test/package?signature=DO_NOT_EXPORT"

    def fail(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(materializer, "download_skillhub_skill", fail)
    with pytest.raises(RuntimeError, match="DO_NOT_EXPORT"):
        materializer.materialize_remote_skill(skill, cache_dir=tmp_path)
    assert points(observation[0], "gen_ai_skill_download")[0][0]["outcome"] == "error"
    span = observation[1].get_finished_spans()[0]
    assert span.status.is_ok is False
    assert span.attributes["error.type"] == "RuntimeError"
    assert "DO_NOT_EXPORT" not in str(
        (span.attributes, span.events, span.status.description)
    )


@pytest.mark.asyncio
async def test_real_adk_cached_loads_keep_identity_and_count_each_response(
    observation, remote, tmp_path, monkeypatch
):
    cloud = registry.VeSkillRegistry(skill_source_id="sp-one", cache_dir=tmp_path)
    toolset = SkillToolset(registry=cloud)
    tool = LoadSkillTool(toolset)
    context = SimpleNamespace(invocation_id="turn", agent_name="agent", state={})
    monkeypatch.setattr(telemetry, "_upload_tool_call_metrics", lambda *a: None)
    for _ in range(2):
        result = await tool.run_async(args={"skill_name": "demo"}, tool_context=context)
        event = Event(
            content=types.Content(
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            name="load_skill", response=result
                        )
                    )
                ]
            )
        )
        with trace.get_tracer("test").start_as_current_span("execute_tool load_skill"):
            telemetry.trace_tool_call(tool, {"skill_name": "demo"}, event)
    assert remote[1] == ["s-demo"]
    assert points(observation[0], "gen_ai_skill_load") == [
        (
            {
                "skill_source": "skillhub_skill_space",
                "skill_id": "s-demo",
                "skill_version": "sv-one",
                "skill_space_id": "sp-one",
            },
            2,
        )
    ]
    assert points(observation[0], "gen_ai_skill_download")[0][1] == 1
    loads = [
        s
        for s in observation[1].get_finished_spans()
        if s.name.startswith("execute_tool")
    ]
    assert all(s.attributes["skill.id"] == "s-demo" for s in loads)
    await toolset.close()


@pytest.mark.parametrize(
    "response", [{"error": "failed"}, {"skill_name": "demo"}, None]
)
def test_failed_or_incomplete_load_never_counts(
    observation, response, remote, tmp_path
):
    event = Event(
        content=types.Content(
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        name="load_skill", response=response or {}
                    )
                )
            ]
        )
    )
    toolset = SkillToolset(
        registry=registry.VeSkillRegistry(skill_source_id="sp-one", cache_dir=tmp_path)
    )
    skill_telemetry.record_adk_load(LoadSkillTool(toolset), event)
    assert not points(observation[0], "gen_ai_skill_load")


def test_unknown_local_identity_and_legacy_version():
    assert (
        skill_telemetry.skill_identity(
            Skill(name="demo", description="Demo", path="/tmp/demo")
        )
        is None
    )
    identity = skill_telemetry.skill_identity(
        Skill(
            name="demo",
            description="Demo",
            path="skills/s-demo/v12/demo.zip",
            id="s-demo",
            skill_space_id="ss-one",
        )
    )
    assert identity == {
        "skill_source": "agentkit_skill_space",
        "skill_id": "s-demo",
        "skill_version": "v12",
        "skill_space_id": "ss-one",
    }


@pytest.mark.asyncio
async def test_cancelled_registry_wait_does_not_load(
    observation, remote, tmp_path, monkeypatch
):
    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(registry.asyncio, "to_thread", cancelled)
    toolset = SkillToolset(
        registry=registry.VeSkillRegistry(skill_source_id="sp-one", cache_dir=tmp_path)
    )
    with pytest.raises(asyncio.CancelledError):
        await LoadSkillTool(toolset).run_async(
            args={"skill_name": "demo"},
            tool_context=SimpleNamespace(invocation_id="turn"),
        )
    assert not points(observation[0], "gen_ai_skill_load")
    await toolset.close()


def test_recording_failure_preserves_download_result(remote, tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        portal_metrics.portal_metric_recorder.skill_download_counter,
        "add",
        broken,
    )
    monkeypatch.setattr(trace, "get_tracer", broken)
    assert (
        materializer.materialize_remote_skill(remote[0], cache_dir=tmp_path)
        / "SKILL.md"
    ).is_file()


def test_non_load_tool_cannot_count_forged_response(observation, remote):
    labels = skill_telemetry.skill_identity(remote[0])
    result = {
        "instructions": "data",
        "frontmatter": {"metadata": {"veadk_skill_identity": labels}},
    }
    event = Event(
        content=types.Content(
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        name="load_skill_resource", response=result
                    )
                )
            ]
        )
    )
    skill_telemetry.record_adk_load(SimpleNamespace(name="load_skill_resource"), event)
    assert not points(observation[0], "gen_ai_skill_load")


def test_default_proxy_instruments_are_bounded_and_support_late_provider():
    import os
    import subprocess
    import sys
    import textwrap
    from pathlib import Path

    script = textwrap.dedent("""
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import InMemoryMetricReader
        from veadk.tracing.telemetry.portal_metrics import portal_metric_recorder as recorder

        proxy = metrics.get_meter_provider()
        assert type(proxy).__name__ == "_ProxyMeterProvider"
        assert recorder.skill_load_counter is not None
        assert recorder.skill_download_counter is not None
        assert recorder.skill_load_counter in recorder.meter._instruments
        assert recorder.skill_download_counter in recorder.meter._instruments
        initial_meters = tuple(proxy._meters)
        initial_instruments = tuple(tuple(meter._instruments) for meter in initial_meters)
        labels = {"skill_source": "agentkit_skill_space", "skill_id": "s-test", "skill_version": "v1", "skill_space_id": "ss-test"}
        for _ in range(1000):
            recorder.record_skill_load(labels)
            recorder.record_skill_download({**labels, "outcome": "success"})
        assert tuple(proxy._meters) == initial_meters
        assert tuple(tuple(meter._instruments) for meter in proxy._meters) == initial_instruments
        reader = InMemoryMetricReader()
        provider = MeterProvider(metric_readers=[reader])
        try:
            metrics.set_meter_provider(provider)
            for _ in range(3):
                recorder.record_skill_load(labels)
                recorder.record_skill_download({**labels, "outcome": "success"})
            data = reader.get_metrics_data()
            values = {m.name: [(dict(p.attributes), p.value) for p in m.data.data_points]
                      for r in data.resource_metrics for s in r.scope_metrics for m in s.metrics}
            assert {s.scope.name for r in data.resource_metrics for s in r.scope_metrics for m in s.metrics if m.name in {"gen_ai_skill_load", "gen_ai_skill_download"}} == {"veadk_portal"}
            assert values["gen_ai_skill_load"] == [(labels, 3)], values
            assert values["gen_ai_skill_download"] == [({**labels, "outcome": "success"}, 3)], values
        finally:
            provider.shutdown()
    """)
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("OTEL_")
    }
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("metric_name", ["gen_ai_skill_load", "gen_ai_skill_download"])
def test_recording_failure_does_not_escape(monkeypatch, metric_name):
    from unittest.mock import Mock

    broken_add = Mock(side_effect=RuntimeError("recording unavailable"))
    recorder = portal_metrics.portal_metric_recorder
    counter = (
        recorder.skill_download_counter
        if metric_name == "gen_ai_skill_download"
        else recorder.skill_load_counter
    )
    record = (
        recorder.record_skill_download
        if metric_name == "gen_ai_skill_download"
        else recorder.record_skill_load
    )
    monkeypatch.setattr(counter, "add", broken_add)
    labels = {
        "skill_source": "builtin_skill",
        "skill_id": "demo",
        "skill_version": "",
        "skill_space_id": "",
    }
    if metric_name == "gen_ai_skill_download":
        labels["outcome"] = "success"
    record(labels)
    broken_add.assert_called_once_with(1, labels)
