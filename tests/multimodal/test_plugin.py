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
"""Tests for the ADK multimodal media plugin."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from veadk.multimodal.models import MediaRecord
from veadk.multimodal.models import MediaRef
from veadk.multimodal.plugin import MultimodalMediaPlugin
from veadk.multimodal.storage import LocalMediaStorage


class _SignedUrlStorage(LocalMediaStorage):
    async def signed_url(self, ref: MediaRef) -> str | None:
        del ref
        return "https://tos.example/media?signature=short-lived"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mime_type", "file_name"),
    [
        ("image/png", "pixel.png"),
        ("video/mp4", "clip.mp4"),
    ],
)
async def test_before_model_resolves_local_binary_media_to_inline_data(
    tmp_path: Path, mime_type: str, file_name: str
) -> None:
    storage = LocalMediaStorage(tmp_path)
    ref = MediaRef("demo", "user", "session", "binary")
    record = MediaRecord.create(
        ref=ref,
        file_name=file_name,
        mime_type=mime_type,
        size_bytes=11,
        sha256="hash",
        origin="user",
    )
    await storage.save_bytes(record, b"binary-data")
    plugin = MultimodalMediaPlugin(storage=storage)
    request = LlmRequest(
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        file_data=types.FileData(
                            file_uri=ref.uri,
                            mime_type=mime_type,
                            display_name=file_name,
                        )
                    )
                ],
            )
        ]
    )

    await plugin.before_model_callback(callback_context=None, llm_request=request)  # type: ignore[arg-type]

    parts = request.contents[0].parts
    assert parts is not None
    part = parts[0]
    assert part.file_data is None
    assert part.inline_data is not None
    assert part.inline_data.data == b"binary-data"
    assert part.inline_data.display_name == file_name
    assert part.inline_data.mime_type == mime_type


@pytest.mark.asyncio
async def test_before_model_renders_pdf_to_page_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalMediaStorage(tmp_path)
    ref = MediaRef("demo", "user", "session", "pdf")
    record = MediaRecord.create(
        ref=ref,
        file_name="guide.pdf",
        mime_type="application/pdf",
        size_bytes=9,
        sha256="hash",
        origin="user",
    )
    await storage.save_bytes(record, b"pdf-bytes")
    rendered_parts = [
        types.Part.from_bytes(data=b"page-1", mime_type="image/png"),
        types.Part.from_bytes(data=b"page-2", mime_type="image/png"),
    ]
    calls: list[tuple[bytes, int, float]] = []

    def _render(data: bytes, max_pages: int, scale: float) -> list[types.Part]:
        calls.append((data, max_pages, scale))
        return rendered_parts

    monkeypatch.setattr("veadk.multimodal.plugin.render_pdf_to_png_parts", _render)
    plugin = MultimodalMediaPlugin(storage=storage)
    request = LlmRequest(
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_uri(file_uri=ref.uri, mime_type="application/pdf"),
                    types.Part(text="Summarize this PDF."),
                ],
            )
        ]
    )

    await plugin.before_model_callback(callback_context=None, llm_request=request)  # type: ignore[arg-type]

    assert calls == [(b"pdf-bytes", 10, 2.0)]
    assert request.contents[0].parts == [
        *rendered_parts,
        types.Part(text="Summarize this PDF."),
    ]


@pytest.mark.asyncio
async def test_before_model_does_not_send_tos_url_as_file_data(tmp_path: Path) -> None:
    storage = _SignedUrlStorage(tmp_path)
    ref = MediaRef("demo", "user", "session", "image")
    record = MediaRecord.create(
        ref=ref,
        file_name="pixel.png",
        mime_type="image/png",
        size_bytes=8,
        sha256="hash",
        origin="user",
    )
    await storage.save_bytes(record, b"png-data")
    plugin = MultimodalMediaPlugin(storage=storage)
    request = LlmRequest(
        contents=[
            types.Content(
                role="user",
                parts=[types.Part.from_uri(file_uri=ref.uri, mime_type="image/png")],
            )
        ]
    )

    await plugin.before_model_callback(callback_context=None, llm_request=request)  # type: ignore[arg-type]

    parts = request.contents[0].parts
    assert parts is not None
    part = parts[0]
    assert part.file_data is None
    assert part.inline_data is not None
    assert part.inline_data.data == b"png-data"


@pytest.mark.asyncio
async def test_before_model_turns_text_document_into_text(tmp_path: Path) -> None:
    storage = LocalMediaStorage(tmp_path)
    ref = MediaRef("demo", "user", "session", "document")
    record = MediaRecord.create(
        ref=ref,
        file_name="notes.md",
        mime_type="text/markdown",
        size_bytes=7,
        sha256="hash",
        origin="user",
    )
    await storage.save_bytes(record, b"# Notes")
    plugin = MultimodalMediaPlugin(storage=storage)
    request = LlmRequest(
        contents=[
            types.Content(
                parts=[types.Part.from_uri(file_uri=ref.uri, mime_type="text/markdown")]
            )
        ]
    )

    await plugin.before_model_callback(callback_context=None, llm_request=request)  # type: ignore[arg-type]

    parts = request.contents[0].parts
    assert parts is not None
    part = parts[0]
    assert part.file_data is None
    assert part.text is not None
    assert '<document name="notes.md" type="text/markdown">' in part.text
    assert "# Notes" in part.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mime_type", "file_name", "kind"),
    [
        ("image/png", "answer.png", "image"),
        ("text/markdown", "answer.md", "markdown"),
        ("text/plain", "answer.txt", "text"),
        ("application/pdf", "answer.pdf", "pdf"),
        ("video/mp4", "answer.mp4", "video"),
    ],
)
async def test_on_event_persists_model_media_before_history(
    tmp_path: Path, mime_type: str, file_name: str, kind: str
) -> None:
    storage = LocalMediaStorage(tmp_path)
    plugin = MultimodalMediaPlugin(storage=storage)
    event = Event(
        invocation_id="invocation",
        author="model",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    inline_data=types.Blob(
                        data=b"generated-media",
                        mime_type=mime_type,
                        display_name=file_name,
                    )
                )
            ],
        ),
    )
    context = SimpleNamespace(
        app_name="demo",
        user_id="user",
        session=SimpleNamespace(id="session"),
    )

    modified = await plugin.on_event_callback(
        invocation_context=context,  # type: ignore[arg-type]
        event=event,
    )

    assert modified is event
    assert event.content is not None
    assert event.content.parts is not None
    part = event.content.parts[0]
    assert part.inline_data is None
    assert part.file_data is not None
    assert part.file_data.file_uri is not None
    ref = MediaRef.from_uri(part.file_data.file_uri)
    assert ref is not None
    assert await storage.read_bytes(ref) == b"generated-media"
    assert part.part_metadata is not None
    assert part.part_metadata["veadkMedia"]["origin"] == "model"
    assert part.part_metadata["veadkMedia"]["kind"] == kind
