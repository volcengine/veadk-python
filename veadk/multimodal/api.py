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
"""FastAPI routes for browser uploads and authenticated media delivery."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi import File
from fastapi import Form
from fastapi import HTTPException
from fastapi import UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from fastapi.responses import Response

from .models import MediaRef
from .service import MediaService
from .service import SUPPORTED_MIME_TYPES


def mount_media_routes(app: FastAPI, service: MediaService) -> None:
    """Mount the multimodal upload, delivery, and cleanup endpoints."""

    @app.get("/web/media/capabilities")
    async def media_capabilities() -> dict[str, object]:
        return {
            "maxFileBytes": service.max_file_bytes,
            "mimeTypes": sorted(SUPPORTED_MIME_TYPES),
            "storage": os.getenv("VEADK_MEDIA_STORAGE", "local").lower(),
        }

    @app.post("/web/media")
    async def upload_media(
        app_name: str = Form(...),
        user_id: str = Form(...),
        session_id: str = Form(...),
        file: UploadFile = File(...),
    ) -> dict[str, object]:
        suffix = Path(file.filename or "attachment").suffix
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
                temp_path = Path(temp.name)
                size_bytes = 0
                while chunk := await file.read(1024 * 1024):
                    size_bytes += len(chunk)
                    if size_bytes > service.max_file_bytes:
                        limit_mb = service.max_file_bytes // (1024 * 1024)
                        raise HTTPException(
                            status_code=413,
                            detail=f"File exceeds the {limit_mb} MB upload limit.",
                        )
                    temp.write(chunk)
            record = await service.save_file(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                file_name=file.filename or "attachment",
                declared_mime_type=file.content_type or "",
                source=temp_path,
            )
            return record.to_api_dict()
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        finally:
            await file.close()
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    @app.get("/web/media/{app_name}/{user_id}/{session_id}/{media_id}")
    async def get_media_metadata(
        app_name: str, user_id: str, session_id: str, media_id: str
    ) -> dict[str, object]:
        try:
            record = await service.get_record(
                _media_ref(app_name, user_id, session_id, media_id)
            )
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Media not found.") from error
        return record.to_api_dict()

    @app.get("/web/media/{app_name}/{user_id}/{session_id}/{media_id}/content")
    async def get_media_content(
        app_name: str, user_id: str, session_id: str, media_id: str
    ) -> Response:
        ref = _media_ref(app_name, user_id, session_id, media_id)
        try:
            record = await service.get_record(ref)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="Media not found.") from error
        local_path = service.storage.local_path(ref)
        if local_path is not None:
            return FileResponse(
                local_path,
                media_type=record.mime_type,
                filename=record.file_name,
                content_disposition_type="inline",
                headers={"Cache-Control": "private, max-age=300"},
            )
        signed_url = await service.storage.signed_url(ref)
        if not signed_url:
            raise HTTPException(status_code=404, detail="Media content unavailable.")
        return RedirectResponse(signed_url, status_code=307)

    @app.delete("/web/media/{app_name}/{user_id}/{session_id}/{media_id}")
    async def delete_media(
        app_name: str, user_id: str, session_id: str, media_id: str
    ) -> None:
        await service.storage.delete(
            _media_ref(app_name, user_id, session_id, media_id)
        )

    @app.delete("/web/media/{app_name}/{user_id}/{session_id}")
    async def delete_session_media(
        app_name: str, user_id: str, session_id: str
    ) -> None:
        await service.storage.delete_session(app_name, user_id, session_id)


def _media_ref(app_name: str, user_id: str, session_id: str, media_id: str) -> MediaRef:
    return MediaRef(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        media_id=media_id,
    )
