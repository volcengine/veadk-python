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
"""Resolve stored media references before proxying requests to remote runtimes."""

from __future__ import annotations

import asyncio
import base64
from typing import Any

from veadk.utils.pdf_to_images import render_pdf_to_png_parts

from .models import MediaRef
from .service import MediaService


async def resolve_runtime_media(
    payload: dict[str, Any], service: MediaService
) -> dict[str, Any]:
    """Replace VeADK media references with portable model input parts."""
    message = payload.get("new_message")
    if not isinstance(message, dict):
        return payload
    parts = message.get("parts")
    if not isinstance(parts, list):
        return payload

    resolved_parts: list[object] = []
    for part in parts:
        if not isinstance(part, dict):
            resolved_parts.append(part)
            continue
        file_data = part.get("fileData") or part.get("file_data")
        if not isinstance(file_data, dict):
            resolved_parts.append(part)
            continue
        uri = file_data.get("fileUri") or file_data.get("file_uri")
        ref = MediaRef.from_uri(uri) if isinstance(uri, str) else None
        if ref is None:
            resolved_parts.append(part)
            continue
        _validate_scope(payload, ref)
        record = await service.get_record(ref)
        data = await service.storage.read_bytes(ref)
        metadata = _transport_metadata(part, record.to_api_dict())

        if record.mime_type in ("text/plain", "text/markdown"):
            resolved_parts.append(
                {
                    **_without_file_data(part),
                    "text": (
                        f'<document name="{record.file_name}" '
                        f'type="{record.mime_type}">\n'
                        f"{data.decode('utf-8-sig')}\n</document>"
                    ),
                    "partMetadata": {
                        **metadata,
                        "veadkTransport": {"hideText": True},
                    },
                }
            )
            continue

        if record.mime_type == "application/pdf":
            image_parts = await asyncio.to_thread(
                render_pdf_to_png_parts, data, 10, 2.0
            )
            for index, image_part in enumerate(image_parts):
                if not image_part.inline_data or not image_part.inline_data.data:
                    continue
                page_metadata = (
                    {
                        **metadata,
                        "veadkTransport": {"pdfPage": index + 1},
                    }
                    if index == 0
                    else {"veadkTransport": {"hidden": True, "pdfPage": index + 1}}
                )
                resolved_parts.append(
                    {
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": _base64(bytes(image_part.inline_data.data)),
                            "displayName": f"{record.file_name} page {index + 1}",
                        },
                        "partMetadata": page_metadata,
                    }
                )
            continue

        resolved_parts.append(
            {
                **_without_file_data(part),
                "inlineData": {
                    "mimeType": record.mime_type,
                    "data": _base64(data),
                    "displayName": record.file_name,
                },
                "partMetadata": metadata,
            }
        )

    message["parts"] = resolved_parts
    return payload


def _validate_scope(payload: dict[str, Any], ref: MediaRef) -> None:
    expected = (
        payload.get("app_name"),
        payload.get("user_id"),
        payload.get("session_id"),
    )
    actual = (ref.app_name, ref.user_id, ref.session_id)
    if actual != expected:
        raise ValueError("Media reference does not belong to this session.")


def _without_file_data(part: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in part.items()
        if key not in ("fileData", "file_data", "partMetadata", "part_metadata")
    }


def _transport_metadata(
    part: dict[str, Any], media: dict[str, object]
) -> dict[str, object]:
    existing = part.get("partMetadata") or part.get("part_metadata") or {}
    metadata = dict(existing) if isinstance(existing, dict) else {}
    metadata["veadkMedia"] = media
    return metadata


def _base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
