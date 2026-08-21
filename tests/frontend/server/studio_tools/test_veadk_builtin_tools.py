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

import sys
from typing import Any

import pytest
from google.adk.tools import ToolContext
from google.genai import types

from frontend.server.studio_tools import veadk_builtin_tools
from frontend.server.studio_tools.registry import (
    StudioToolExecutionContext,
    StudioToolRegistry,
)
from veadk.config import settings
from veadk.configs import model_configs
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


def test_builtin_registration_does_not_resolve_model_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema discovery must stay offline until a selected tool executes."""

    for env_name in (
        "MODEL_AGENT_API_KEY",
        "MODEL_EDIT_API_KEY",
        "MODEL_IMAGE_API_KEY",
        "MODEL_VIDEO_API_KEY",
    ):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.delitem(settings.model.__dict__, "api_key", raising=False)

    def fail_credential_lookup(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("Studio schema discovery resolved an ARK credential")

    monkeypatch.setattr(model_configs, "get_ark_token", fail_credential_lookup)
    for module_name in (
        "veadk.tools.builtin_tools.image_edit",
        "veadk.tools.builtin_tools.image_generate",
        "veadk.tools.builtin_tools.video_generate",
    ):
        monkeypatch.delitem(sys.modules, module_name, raising=False)

    registry = StudioToolRegistry()
    veadk_builtin_tools.register_veadk_builtin_tools(registry)

    registered_names = {manifest["name"] for manifest in registry.manifests()}
    assert {"image_edit", "image_generate", "video_generate"} <= registered_names


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
