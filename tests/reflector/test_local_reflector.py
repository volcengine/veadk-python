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

"""Unit tests for ``veadk.reflector.local_reflector`` (and ``base_reflector``).

The reflector builds an ``Agent`` + ``Runner`` and calls the model; both are
mocked so no model / network access happens.
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from veadk.reflector import local_reflector as lr
from veadk.reflector.base_reflector import BaseReflector, ReflectorResult
from veadk.reflector.local_reflector import LocalReflector


def _make_agent(instruction: str = "SYSTEM_PROMPT") -> MagicMock:
    agent = MagicMock()
    agent.instruction = instruction
    return agent


# --- base_reflector ---------------------------------------------------------


def test_reflector_result_model_fields():
    result = ReflectorResult(optimized_prompt="opt", reason="because")
    assert result.optimized_prompt == "opt"
    assert result.reason == "because"


def test_base_reflector_is_abstract():
    with pytest.raises(TypeError):
        BaseReflector(_make_agent())  # type: ignore[abstract]


def test_local_reflector_stores_agent():
    agent = _make_agent()
    reflector = LocalReflector(agent)
    assert reflector.agent is agent
    assert isinstance(reflector, BaseReflector)


# --- _read_traces_from_dir --------------------------------------------------


def test_read_traces_from_dir_reads_only_json(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"step": 1}))
    (tmp_path / "b.json").write_text(json.dumps({"step": 2}))
    (tmp_path / "ignore.txt").write_text("not json")

    reflector = LocalReflector(_make_agent())
    traces = reflector._read_traces_from_dir(str(tmp_path))

    assert len(traces) == 2
    assert {"step": 1} in traces
    assert {"step": 2} in traces


# --- reflect ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_reflect_parses_valid_json_response(tmp_path):
    trace_file = tmp_path / "trace.json"
    trace_file.write_text(json.dumps([{"event": "x"}]))

    runner = MagicMock()
    runner.run = AsyncMock(
        return_value=json.dumps(
            {"optimized_prompt": "better prompt", "reason": "clearer"}
        )
    )

    with (
        patch.object(lr, "Agent") as mock_agent_cls,
        patch.object(lr, "Runner", return_value=runner) as mock_runner_cls,
    ):
        reflector = LocalReflector(_make_agent("OLD_PROMPT"))
        result = await reflector.reflect(str(trace_file))

    assert isinstance(result, ReflectorResult)
    assert result.optimized_prompt == "better prompt"
    assert result.reason == "clearer"

    # An Agent + Runner are constructed and run is awaited with the prompt.
    mock_agent_cls.assert_called_once()
    mock_runner_cls.assert_called_once()
    runner.run.assert_awaited_once()
    sent = runner.run.await_args.kwargs["messages"]
    assert "OLD_PROMPT" in sent


@pytest.mark.asyncio
async def test_reflect_handles_invalid_json_response(tmp_path):
    trace_file = tmp_path / "trace.json"
    trace_file.write_text(json.dumps([]))

    runner = MagicMock()
    runner.run = AsyncMock(return_value="this is not json")

    with (
        patch.object(lr, "Agent"),
        patch.object(lr, "Runner", return_value=runner),
    ):
        reflector = LocalReflector(_make_agent())
        result = await reflector.reflect(str(trace_file))

    assert result.optimized_prompt == ""
    assert "not valid json" in result.reason


@pytest.mark.asyncio
async def test_reflect_handles_empty_response(tmp_path):
    trace_file = tmp_path / "trace.json"
    trace_file.write_text(json.dumps([]))

    runner = MagicMock()
    runner.run = AsyncMock(return_value="")

    with (
        patch.object(lr, "Agent"),
        patch.object(lr, "Runner", return_value=runner),
    ):
        reflector = LocalReflector(_make_agent())
        result = await reflector.reflect(str(trace_file))

    assert result.optimized_prompt == ""
    assert result.reason == "response from optimizer is empty"


@pytest.mark.asyncio
async def test_reflect_asserts_on_non_json_file(tmp_path):
    txt_file = tmp_path / "trace.txt"
    txt_file.write_text("[]")

    reflector = LocalReflector(_make_agent())
    with pytest.raises(AssertionError, match="not a valid json file"):
        await reflector.reflect(str(txt_file))


@pytest.mark.asyncio
async def test_reflect_asserts_on_missing_file(tmp_path):
    missing = os.path.join(str(tmp_path), "does_not_exist.json")

    reflector = LocalReflector(_make_agent())
    with pytest.raises(AssertionError, match="is not a file"):
        await reflector.reflect(missing)
