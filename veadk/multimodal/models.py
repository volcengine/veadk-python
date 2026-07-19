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
"""Data types and URI helpers for stored multimodal media."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from urllib.parse import quote
from urllib.parse import unquote
from urllib.parse import urlparse

MEDIA_URI_SCHEME = "veadk-media"


@dataclass(frozen=True)
class MediaRef:
    """Location of one session-scoped media object."""

    app_name: str
    user_id: str
    session_id: str
    media_id: str

    @property
    def uri(self) -> str:
        """Return the stable URI stored in a Google GenAI ``FileData`` part."""
        segments = (
            "apps",
            self.app_name,
            "users",
            self.user_id,
            "sessions",
            self.session_id,
            "media",
            self.media_id,
        )
        encoded = "/".join(quote(segment, safe="") for segment in segments)
        return f"{MEDIA_URI_SCHEME}://{encoded}"

    @classmethod
    def from_uri(cls, uri: str) -> MediaRef | None:
        """Parse a VeADK media URI, returning ``None`` for other schemes."""
        parsed = urlparse(uri)
        if parsed.scheme != MEDIA_URI_SCHEME:
            return None
        segments = [unquote(parsed.netloc), *map(unquote, parsed.path.split("/")[1:])]
        if len(segments) != 8:
            return None
        if segments[0::2] != ["apps", "users", "sessions", "media"]:
            return None
        return cls(
            app_name=segments[1],
            user_id=segments[3],
            session_id=segments[5],
            media_id=segments[7],
        )


@dataclass(frozen=True)
class MediaRecord:
    """Metadata stored next to a media object's bytes."""

    ref: MediaRef
    file_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    origin: str
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        ref: MediaRef,
        file_name: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        origin: str,
    ) -> MediaRecord:
        """Create metadata with a UTC timestamp."""
        return cls(
            ref=ref,
            file_name=file_name,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            origin=origin,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize metadata for storage."""
        data = asdict(self)
        data["uri"] = self.ref.uri
        return data

    def to_api_dict(self) -> dict[str, object]:
        """Serialize metadata using the frontend's camel-case field names."""
        return {
            "id": self.ref.media_id,
            "uri": self.ref.uri,
            "name": self.file_name,
            "mimeType": self.mime_type,
            "sizeBytes": self.size_bytes,
            "sha256": self.sha256,
            "origin": self.origin,
            "createdAt": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> MediaRecord:
        """Deserialize metadata previously produced by :meth:`to_dict`."""
        raw_ref = data["ref"]
        if not isinstance(raw_ref, dict):
            raise ValueError("Invalid media record ref.")
        ref = MediaRef(
            app_name=str(raw_ref["app_name"]),
            user_id=str(raw_ref["user_id"]),
            session_id=str(raw_ref["session_id"]),
            media_id=str(raw_ref["media_id"]),
        )
        size_bytes = data["size_bytes"]
        if not isinstance(size_bytes, int):
            raise ValueError("Invalid media record size.")
        return cls(
            ref=ref,
            file_name=str(data["file_name"]),
            mime_type=str(data["mime_type"]),
            size_bytes=size_bytes,
            sha256=str(data["sha256"]),
            origin=str(data["origin"]),
            created_at=str(data["created_at"]),
        )
