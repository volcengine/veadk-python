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

from __future__ import annotations

import asyncio
import sys
from types import ModuleType

import pytest

from frontend.server.studio_tools.registry import (
    StudioTool,
    StudioToolExecutionContext,
    StudioToolExecutionError,
    StudioToolRegistry,
    build_studio_tool_registry,
)


def _execution_context() -> StudioToolExecutionContext:
    return StudioToolExecutionContext(
        runtime_id="runtime-1",
        app_name="app-1",
        user_id="user-1",
        session_id="session-1",
        run_id="run-1",
        scope_id="scope-1",
        catalog_revision="revision-1",
    )


def _registry() -> StudioToolRegistry:
    registry = StudioToolRegistry()
    registry.register(
        StudioTool(
            name="studio_multiply",
            description="Multiply two integers in Studio.",
            input_schema={
                "type": "object",
                "properties": {
                    "left": {"type": "integer"},
                    "right": {"type": "integer"},
                },
                "required": ["left", "right"],
                "additionalProperties": False,
            },
            executor=lambda args: {"product": args["left"] * args["right"]},
            executor_revision="v1",
        )
    )
    return registry


def _register_echo(registry: StudioToolRegistry) -> None:
    registry.register(
        StudioTool(
            name="studio_echo",
            display_name="Echo",
            description="Echo text in Studio.",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            executor=lambda args: {"text": args["text"]},
            executor_revision="v1",
        )
    )


@pytest.mark.asyncio
async def test_registry_validates_arguments_and_executes_revision() -> None:
    registry = _registry()

    result = await registry.execute(
        name="studio_multiply",
        executor_revision="v1",
        arguments={"left": 6, "right": 7},
    )

    assert result == {"product": 42}
    assert registry.manifests()[0]["executor_revision"] == "v1"
    assert registry.revision.startswith("sha256:")


@pytest.mark.asyncio
async def test_registry_rejects_arguments_before_executor() -> None:
    registry = _registry()

    with pytest.raises(StudioToolExecutionError, match="Invalid arguments"):
        await registry.execute(
            name="studio_multiply",
            executor_revision="v1",
            arguments={"left": "six", "right": 7},
        )


@pytest.mark.asyncio
async def test_registry_injects_server_execution_context_only_when_requested() -> None:
    registry = StudioToolRegistry()
    seen: list[StudioToolExecutionContext] = []

    async def execute(
        arguments: dict[str, object],
        context: StudioToolExecutionContext,
    ) -> dict[str, object]:
        seen.append(context)
        return {"value": arguments["value"], "session_id": context.session_id}

    registry.register(
        StudioTool(
            name="studio_context_echo",
            description="Echo with trusted context.",
            input_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            executor=execute,
            requires_context=True,
        )
    )

    result = await registry.execute(
        name="studio_context_echo",
        executor_revision="v1",
        arguments={"value": "hello"},
        context=_execution_context(),
    )

    assert result == {"value": "hello", "session_id": "session-1"}
    assert seen == [_execution_context()]


@pytest.mark.asyncio
async def test_new_executor_revision_becomes_the_next_catalog_snapshot() -> None:
    registry = _registry()
    first_revision = registry.revision
    registry.register(
        StudioTool(
            name="studio_multiply",
            description="Multiply two integers with the updated Studio executor.",
            input_schema={
                "type": "object",
                "properties": {
                    "left": {"type": "integer"},
                    "right": {"type": "integer"},
                },
                "required": ["left", "right"],
                "additionalProperties": False,
            },
            executor=lambda args: {
                "product": args["left"] * args["right"],
                "revision": "v2",
            },
            executor_revision="v2",
        )
    )

    assert registry.revision != first_revision
    assert registry.manifests()[0]["executor_revision"] == "v2"
    assert await registry.execute(
        name="studio_multiply",
        executor_revision="v2",
        arguments={"left": 3, "right": 5},
    ) == {"product": 15, "revision": "v2"}


@pytest.mark.asyncio
async def test_snapshot_contains_only_selected_tools_and_executors() -> None:
    registry = _registry()
    _register_echo(registry)

    snapshot = registry.snapshot(["studio_echo"])

    assert [item["name"] for item in snapshot.manifests()] == ["studio_echo"]
    assert snapshot.public_items() == [
        {
            "id": "studio_echo",
            "name": "Echo",
            "description": "Echo text in Studio.",
            "riskLevel": "low",
        }
    ]
    assert await snapshot.execute(
        name="studio_echo",
        executor_revision="v1",
        arguments={"text": "hello"},
    ) == {"text": "hello"}
    with pytest.raises(StudioToolExecutionError, match="unavailable in this run"):
        await snapshot.execute(
            name="studio_multiply",
            executor_revision="v1",
            arguments={"left": 6, "right": 7},
        )


def test_snapshots_are_independent_and_do_not_mutate_the_registry() -> None:
    registry = _registry()
    _register_echo(registry)

    first = registry.snapshot(["studio_multiply"])
    second = registry.snapshot(["studio_echo"])

    assert [item["name"] for item in first.manifests()] == ["studio_multiply"]
    assert [item["name"] for item in second.manifests()] == ["studio_echo"]
    assert {item["name"] for item in registry.manifests()} == {
        "studio_echo",
        "studio_multiply",
    }


def test_snapshot_rejects_unknown_tool_ids() -> None:
    with pytest.raises(ValueError, match="Unknown Studio tools: missing"):
        _registry().snapshot(["missing"])


def test_registry_keeps_generic_external_module_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = ModuleType("test_studio_tool_extension")
    module.register_tools = _register_echo  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setenv("VEADK_STUDIO_TOOL_MODULE", module.__name__)

    registry = build_studio_tool_registry()

    assert "studio_echo" in {item["id"] for item in registry.public_items()}


@pytest.mark.asyncio
async def test_concurrent_run_snapshots_do_not_cross_selected_tools() -> None:
    registry = _registry()
    _register_echo(registry)
    multiply_catalog = registry.snapshot(["studio_multiply"])
    echo_catalog = registry.snapshot(["studio_echo"])

    multiply_result, echo_result = await asyncio.gather(
        multiply_catalog.execute(
            name="studio_multiply",
            executor_revision="v1",
            arguments={"left": 8, "right": 9},
        ),
        echo_catalog.execute(
            name="studio_echo",
            executor_revision="v1",
            arguments={"text": "session-b"},
        ),
    )

    assert multiply_result == {"product": 72}
    assert echo_result == {"text": "session-b"}
    with pytest.raises(StudioToolExecutionError, match="unavailable in this run"):
        await echo_catalog.execute(
            name="studio_multiply",
            executor_revision="v1",
            arguments={"left": 8, "right": 9},
        )
