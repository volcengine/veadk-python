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
"""Tests for media transport to remote AgentKit runtimes."""

from __future__ import annotations

import base64
import io
from typing import Any

import pypdfium2 as pdfium
import pytest

from veadk.multimodal.service import MediaService
from veadk.multimodal.storage import LocalMediaStorage
from veadk.multimodal.transport import resolve_runtime_media


async def _payload(
    service: MediaService,
    *,
    mime_type: str,
    data: bytes,
    file_name: str,
) -> tuple[dict[str, Any], str]:
    record = await service.save_bytes(
        app_name="demo",
        user_id="user",
        session_id="session",
        file_name=file_name,
        mime_type=mime_type,
        data=data,
        origin="user",
    )
    return (
        {
            "app_name": "demo",
            "user_id": "user",
            "session_id": "session",
            "new_message": {
                "role": "user",
                "parts": [
                    {
                        "fileData": {
                            "fileUri": record.ref.uri,
                            "mimeType": mime_type,
                        },
                        "partMetadata": {"veadkInvocation": {"skills": []}},
                    }
                ],
            },
        },
        record.ref.uri,
    )


@pytest.mark.asyncio
async def test_image_reference_becomes_inline_data(tmp_path) -> None:
    service = MediaService(LocalMediaStorage(tmp_path))
    payload, uri = await _payload(
        service,
        mime_type="image/png",
        data=b"image-bytes",
        file_name="cat.png",
    )

    resolved = await resolve_runtime_media(payload, service)

    part = resolved["new_message"]["parts"][0]
    assert "fileData" not in part
    assert base64.b64decode(part["inlineData"]["data"]) == b"image-bytes"
    assert part["partMetadata"]["veadkMedia"]["uri"] == uri
    assert part["partMetadata"]["veadkInvocation"] == {"skills": []}


@pytest.mark.asyncio
async def test_text_reference_becomes_hidden_transport_text(tmp_path) -> None:
    service = MediaService(LocalMediaStorage(tmp_path))
    payload, uri = await _payload(
        service,
        mime_type="text/markdown",
        data=b"# Guide",
        file_name="guide.md",
    )

    resolved = await resolve_runtime_media(payload, service)

    part = resolved["new_message"]["parts"][0]
    assert part["text"] == (
        '<document name="guide.md" type="text/markdown">\n# Guide\n</document>'
    )
    assert part["partMetadata"]["veadkMedia"]["uri"] == uri
    assert part["partMetadata"]["veadkTransport"]["hideText"] is True


@pytest.mark.asyncio
async def test_pdf_reference_becomes_page_images(tmp_path) -> None:
    document = pdfium.PdfDocument.new()
    document.new_page(100, 100)
    document.new_page(100, 100)
    buffer = io.BytesIO()
    document.save(buffer)
    service = MediaService(LocalMediaStorage(tmp_path))
    payload, uri = await _payload(
        service,
        mime_type="application/pdf",
        data=buffer.getvalue(),
        file_name="report.pdf",
    )

    resolved = await resolve_runtime_media(payload, service)

    parts = resolved["new_message"]["parts"]
    assert len(parts) == 2
    assert all(part["inlineData"]["mimeType"] == "image/png" for part in parts)
    assert parts[0]["partMetadata"]["veadkMedia"]["uri"] == uri
    assert parts[1]["partMetadata"]["veadkTransport"]["hidden"] is True


@pytest.mark.asyncio
async def test_media_reference_must_match_request_scope(tmp_path) -> None:
    service = MediaService(LocalMediaStorage(tmp_path))
    payload, _ = await _payload(
        service,
        mime_type="image/png",
        data=b"image-bytes",
        file_name="cat.png",
    )
    payload["user_id"] = "another-user"

    with pytest.raises(ValueError, match="does not belong"):
        await resolve_runtime_media(payload, service)
