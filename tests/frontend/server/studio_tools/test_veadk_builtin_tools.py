# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

from __future__ import annotations

from typing import Any

import pytest
from google.adk.tools import ToolContext
from google.genai import types

from frontend.server.studio_tools import veadk_builtin_tools
from frontend.server.studio_tools.registry import (
    StudioToolExecutionContext,
    StudioToolRegistry,
)
from veadk.multimodal.models import MediaRecord, MediaRef


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


@pytest.mark.asyncio
async def test_builtin_adapter_reuses_callable_and_injects_bff_tool_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_builtin(value: str, tool_context: ToolContext) -> dict[str, Any]:
        calls = int(tool_context.state.get("calls", 0)) + 1
        tool_context.state["calls"] = calls
        invocation = tool_context._invocation_context
        return {
            "value": value,
            "app_name": invocation.app_name,
            "user_id": invocation.user_id,
            "session_id": invocation.session.id,
            "calls": calls,
        }

    monkeypatch.setattr(veadk_builtin_tools, "list_builtin_tools", lambda: ["fake"])
    monkeypatch.setattr(
        veadk_builtin_tools,
        "get_builtin_tool",
        lambda name: fake_builtin,
    )
    registry = StudioToolRegistry()

    veadk_builtin_tools.register_veadk_builtin_tools(registry)

    manifest = registry.manifests()[0]
    assert manifest["name"] == "fake"
    assert set(manifest["input_schema"]["properties"]) == {"value"}
    first = await registry.execute(
        name="fake",
        executor_revision="veadk-builtin-v1",
        arguments={"value": "first"},
        context=_context(),
    )
    second = await registry.execute(
        name="fake",
        executor_revision="veadk-builtin-v1",
        arguments={"value": "second"},
        context=_context(),
    )

    assert first == {
        "value": "first",
        "app_name": "app-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "calls": 1,
    }
    assert second["calls"] == 2


@pytest.mark.asyncio
async def test_builtin_adapter_publishes_generated_artifacts_to_studio_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_builtin(tool_context: ToolContext) -> dict[str, str]:
        version = await tool_context.save_artifact(
            "deck.pptx",
            types.Part.from_bytes(
                data=b"presentation",
                mime_type=(
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                ),
            ),
        )
        return {"status": "created", "version": str(version)}

    class FakeMediaService:
        async def save_bytes(self, **kwargs: Any) -> MediaRecord:
            assert kwargs == {
                "app_name": "app-1",
                "user_id": "user-1",
                "session_id": "session-1",
                "file_name": "deck.pptx",
                "mime_type": (
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                ),
                "data": b"presentation",
                "origin": "model",
            }
            return MediaRecord.create(
                ref=MediaRef("app-1", "user-1", "session-1", "media-1"),
                file_name="deck.pptx",
                mime_type=kwargs["mime_type"],
                size_bytes=len(kwargs["data"]),
                sha256="digest",
                origin="model",
            )

    monkeypatch.setattr(veadk_builtin_tools, "list_builtin_tools", lambda: ["fake"])
    monkeypatch.setattr(
        veadk_builtin_tools, "get_builtin_tool", lambda name: fake_builtin
    )
    registry = StudioToolRegistry()
    veadk_builtin_tools.register_veadk_builtin_tools(
        registry,
        media_service=FakeMediaService(),  # type: ignore[arg-type]
    )

    result = await registry.execute(
        name="fake",
        executor_revision="veadk-builtin-v1",
        arguments={},
        context=_context(),
    )

    assert result["status"] == "created"
    assert result["studio_artifacts"] == [
        {
            "id": "media-1",
            "uri": (
                "veadk-media://apps/app-1/users/user-1/sessions/session-1/media/media-1"
            ),
            "name": "deck.pptx",
            "mimeType": (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ),
            "sizeBytes": 12,
            "sha256": "digest",
            "origin": "model",
            "createdAt": result["studio_artifacts"][0]["createdAt"],
            "contentUrl": "/web/media/app-1/user-1/session-1/media-1/content",
            "artifactVersion": 0,
        }
    ]
