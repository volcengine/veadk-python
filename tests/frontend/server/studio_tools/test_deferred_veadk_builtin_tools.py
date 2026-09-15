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

from collections.abc import Callable
from typing import Any, cast

import pytest
from veadk.tools import list_builtin_tools as list_canonical_builtin_tools

from frontend.server.studio_tools import veadk_builtin_tools
from frontend.server.studio_tools.registry import (
    StudioToolExecutionContext,
    StudioToolRegistry,
)


def _context() -> StudioToolExecutionContext:
    return StudioToolExecutionContext(
        runtime_id="runtime-1",
        app_name="app-1",
        user_id="user-1",
        session_id="session-1",
        run_id="run-1",
        scope_id="scope-1",
        catalog_revision="revision-1",
    )


def test_deferred_builtin_catalog_matches_canonical_names() -> None:
    assert set(veadk_builtin_tools._DEFERRED_BUILTIN_DECLARATIONS) == set(
        list_canonical_builtin_tools()
    )


@pytest.mark.parametrize(
    "name",
    sorted(veadk_builtin_tools._DEFERRED_BUILTIN_DECLARATIONS),
)
def test_deferred_builtin_declaration_matches_canonical_tool(name: str) -> None:
    function_tool = veadk_builtin_tools.FunctionTool(
        cast(Callable[..., Any], veadk_builtin_tools.get_builtin_tool(name))
    )

    assert veadk_builtin_tools._deferred_schema(name) == veadk_builtin_tools._schema(
        function_tool
    )


@pytest.mark.asyncio
async def test_deferred_builtin_resolves_once_on_first_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolutions: list[str] = []
    description, _schema = veadk_builtin_tools._DEFERRED_BUILTIN_DECLARATIONS[
        "link_reader"
    ]

    async def link_reader(url_list: list[str]) -> dict[str, Any]:
        return {"urls": url_list}

    link_reader.__doc__ = description

    def resolve(name: str) -> Any:
        resolutions.append(name)
        return link_reader

    monkeypatch.setattr(
        veadk_builtin_tools,
        "list_builtin_tools",
        lambda: ["link_reader"],
    )
    monkeypatch.setattr(veadk_builtin_tools, "get_builtin_tool", resolve)
    registry = StudioToolRegistry()

    veadk_builtin_tools.register_veadk_builtin_tools(registry)

    assert resolutions == []
    first = await registry.execute(
        name="link_reader",
        executor_revision="veadk-builtin-v1",
        arguments={"url_list": ["https://example.com"]},
        context=_context(),
    )
    second = await registry.execute(
        name="link_reader",
        executor_revision="veadk-builtin-v1",
        arguments={"url_list": ["https://example.org"]},
        context=_context(),
    )

    assert first == {"urls": ["https://example.com"]}
    assert second == {"urls": ["https://example.org"]}
    assert resolutions == ["link_reader"]
