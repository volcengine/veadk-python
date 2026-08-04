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
"""Google ADK plugin that resolves and captures durable media references."""

from __future__ import annotations

import asyncio
from pathlib import Path

from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.plugins import BasePlugin
from google.genai import types

from veadk.utils.pdf_to_images import render_pdf_to_png_parts

from .models import MediaRef
from .service import MediaService
from .service import SUPPORTED_MIME_TYPES
from .service import media_kind
from .storage import MediaStorage
from .storage import create_media_storage


class MultimodalMediaPlugin(BasePlugin):
    """Keep media bytes out of session events while preserving model access."""

    def __init__(
        self,
        name: str = "veadk_multimodal_media",
        *,
        storage: MediaStorage | None = None,
    ) -> None:
        super().__init__(name=name)
        self._service = MediaService(storage or create_media_storage())

    async def before_model_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
    ) -> None:
        """Resolve stable media references only for the outgoing model request."""
        del callback_context
        for content in llm_request.contents:
            resolved_parts: list[types.Part] = []
            for part in content.parts or []:
                file_data = part.file_data
                if not file_data or not file_data.file_uri:
                    resolved_parts.append(part)
                    continue
                ref = MediaRef.from_uri(file_data.file_uri)
                if ref is None:
                    resolved_parts.append(part)
                    continue
                record = await self._service.get_record(ref)
                if record.mime_type in ("text/plain", "text/markdown"):
                    data = await self._service.storage.read_bytes(ref)
                    text = data.decode("utf-8-sig")
                    part.file_data = None
                    part.text = (
                        f'<document name="{record.file_name}" '
                        f'type="{record.mime_type}">\n{text}\n</document>'
                    )
                    resolved_parts.append(part)
                    continue
                data = await self._service.storage.read_bytes(ref)
                if record.mime_type == "application/pdf":
                    resolved_parts.extend(
                        await asyncio.to_thread(
                            render_pdf_to_png_parts,
                            data,
                            10,
                            2.0,
                        )
                    )
                    continue
                part.file_data = None
                part.inline_data = types.Blob(
                    data=data,
                    display_name=record.file_name,
                    mime_type=record.mime_type,
                )
                resolved_parts.append(part)
            content.parts = resolved_parts

    async def on_event_callback(
        self,
        *,
        invocation_context: InvocationContext,
        event: Event,
    ) -> Event | None:
        """Persist model-returned media before the Event reaches SSE/history."""
        if event.partial or not event.content or not event.content.parts:
            return None
        modified = False
        for index, part in enumerate(event.content.parts):
            inline_data = part.inline_data
            if not inline_data or not inline_data.data or not inline_data.mime_type:
                continue
            mime_type = inline_data.mime_type.lower()
            if mime_type not in SUPPORTED_MIME_TYPES:
                continue
            file_name = inline_data.display_name or self._model_file_name(
                event.id, index, mime_type
            )
            record = await self._service.save_bytes(
                app_name=invocation_context.app_name,
                user_id=invocation_context.user_id,
                session_id=invocation_context.session.id,
                file_name=file_name,
                mime_type=mime_type,
                data=bytes(inline_data.data),
                origin="model",
            )
            metadata = dict(part.part_metadata or {})
            metadata["veadkMedia"] = {
                **record.to_api_dict(),
                "kind": media_kind(record.mime_type),
            }
            part.inline_data = None
            part.file_data = types.FileData(
                file_uri=record.ref.uri,
                display_name=record.file_name,
                mime_type=record.mime_type,
            )
            part.part_metadata = metadata
            modified = True
        return event if modified else None

    @staticmethod
    def _model_file_name(event_id: str, index: int, mime_type: str) -> str:
        extension = {
            "application/pdf": ".pdf",
            "image/gif": ".gif",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "text/markdown": ".md",
            "text/plain": ".txt",
            "video/mp4": ".mp4",
            "video/quicktime": ".mov",
            "video/webm": ".webm",
        }.get(mime_type, "")
        return f"model-{Path(event_id).name}-{index}{extension}"
