# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = (
    Path(__file__).parents[2]
    / "examples"
    / "16_self_host_sandbox"
    / "preflight_probe.py"
)
SPEC = importlib.util.spec_from_file_location("preflight_probe_tested", MODULE_PATH)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(probe)


def test_event_trace_whitelists_tool_linkage_and_error(tmp_path):
    output = tmp_path / "events.jsonl"
    probe.append_event_trace(
        output,
        turn="tool-123",
        event=SimpleNamespace(
            type="agent.tool_result",
            id="event-1",
            event_id="event-0",
            tool_use_id="toolu-1",
            is_error=True,
            sequence=9,
            content="secret tool output",
            input={"token": "secret"},
        ),
    )
    probe.append_event_trace(output, turn="tool-123", error_type="TimeoutError")

    lines = [json.loads(line) for line in output.read_text().splitlines()]
    assert lines == [
        {
            "event_id": "event-0",
            "id": "event-1",
            "is_error": True,
            "sequence": 9,
            "tool_use_id": "toolu-1",
            "turn": "tool-123",
            "type": "agent.tool_result",
        },
        {"error_type": "TimeoutError", "turn": "tool-123", "type": "probe.error"},
    ]
    rendered = output.read_text()
    assert "secret tool output" not in rendered
    assert "token" not in rendered


def test_controlled_tool_events_preserve_probe_correlation(tmp_path):
    output = tmp_path / "controlled.jsonl"
    tool_use = SimpleNamespace(
        type="agent.tool_use",
        id="toolu-safe-1",
        event_id=None,
        tool_use_id=None,
        is_error=None,
        sequence=3,
        input={"command": "printf controlled"},
    )
    tool_result = SimpleNamespace(
        type="agent.tool_result",
        id="event-result-1",
        event_id=None,
        tool_use_id="toolu-safe-1",
        is_error=False,
        sequence=4,
        content="controlled output",
    )
    probe.append_event_trace(output, turn="tool-controlled", event=tool_use)
    probe.append_event_trace(output, turn="tool-controlled", event=tool_result)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert rows[0]["id"] == rows[1]["tool_use_id"] == "toolu-safe-1"
    assert rows[1]["is_error"] is False
    assert "printf controlled" not in output.read_text()
    assert "controlled output" not in output.read_text()
