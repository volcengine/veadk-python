# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

from __future__ import annotations

import re
from types import ModuleType, SimpleNamespace

import pytest

from frontend.server.studio_tools import extensions
from frontend.server.studio_tools.extensions import register_studio_tool_extensions
from frontend.server.studio_tools.registry import (
    StudioToolExecutionError,
    StudioToolRegistry,
)


@pytest.mark.asyncio
async def test_current_time_extension_is_discovered_and_executable() -> None:
    registry = StudioToolRegistry()

    register_studio_tool_extensions(registry)

    assert registry.public_items() == [
        {
            "id": "current_time",
            "name": "当前时间",
            "description": "Return the current date and time in an IANA timezone.",
            "riskLevel": "low",
        }
    ]
    result = await registry.execute(
        name="current_time",
        executor_revision="studio-extension-current-time-v1",
        arguments={"timezone": "UTC"},
    )
    assert result["timezone"] == "UTC"
    assert result["iso8601"].endswith("+00:00")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", result["date"])
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", result["time"])


@pytest.mark.asyncio
async def test_current_time_extension_rejects_unknown_timezone() -> None:
    registry = StudioToolRegistry()
    register_studio_tool_extensions(registry)

    with pytest.raises(StudioToolExecutionError, match="Unknown IANA timezone"):
        await registry.execute(
            name="current_time",
            executor_revision="studio-extension-current-time-v1",
            arguments={"timezone": "Mars/Olympus_Mons"},
        )


def test_extension_discovery_is_sorted_and_ignores_private_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported: list[str] = []
    registered: list[str] = []

    monkeypatch.setattr(
        extensions,
        "iter_modules",
        lambda paths: [
            SimpleNamespace(name="z_last", ispkg=False),
            SimpleNamespace(name="_template", ispkg=False),
            SimpleNamespace(name="nested", ispkg=True),
            SimpleNamespace(name="a_first", ispkg=False),
        ],
    )

    def fake_import_module(name: str) -> ModuleType:
        imported.append(name)
        module = ModuleType(name)
        module.register_tools = lambda registry: registered.append(name)  # type: ignore[attr-defined]
        return module

    monkeypatch.setattr(extensions, "import_module", fake_import_module)

    register_studio_tool_extensions(StudioToolRegistry())

    assert imported == [
        "frontend.server.studio_tools.extensions.a_first",
        "frontend.server.studio_tools.extensions.z_last",
    ]
    assert registered == imported


def test_extension_discovery_rejects_module_without_registration_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        extensions,
        "iter_modules",
        lambda paths: [SimpleNamespace(name="invalid", ispkg=False)],
    )
    monkeypatch.setattr(
        extensions,
        "import_module",
        lambda name: ModuleType(name),
    )

    with pytest.raises(RuntimeError, match=r"must export register_tools\(registry\)"):
        register_studio_tool_extensions(StudioToolRegistry())
