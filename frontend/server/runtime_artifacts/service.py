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

"""Read authorized session artifacts from Studio storage or a Runtime mount"""

from __future__ import annotations

import asyncio
import mimetypes
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from frontend.server.storage import StudioStorageConfig

PREVIEW_MAX_BYTES = 16 * 1024 * 1024
DOWNLOAD_MAX_BYTES = 256 * 1024 * 1024
MOUNT_PATH = "/mnt/artifacts"


class RuntimeArtifactError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class RuntimeArtifactAccess:
    """Created after Runtime authorization with the authenticated user identity"""

    user_id: str
    provider: str
    region: str
    runtime_detail: Mapping[str, Any]


@dataclass(frozen=True)
class ArtifactMount:
    bucket: str
    prefix: str


@dataclass
class ArtifactContent:
    stream: Any
    name: str
    mime_type: str
    size: int
    total_size: int
    byte_range: tuple[int, int] | None
    _closed: bool = field(default=False, init=False, repr=False)

    def chunks(self) -> Iterator[bytes]:
        remaining = self.size
        try:
            while remaining:
                chunk = self.stream.read(min(64 * 1024, remaining))
                if not isinstance(chunk, bytes) or not chunk:
                    raise RuntimeError("Artifact content stream ended unexpectedly")
                if len(chunk) > remaining:
                    raise RuntimeError("Artifact content exceeded its declared size")
                remaining -= len(chunk)
                yield chunk
            if self.stream.read(1):
                raise RuntimeError("Artifact content exceeded its declared size")
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _close_response(self.stream)


def _close_response(stream: Any) -> None:
    close = getattr(stream, "close", None)
    if callable(close):
        close()
        return
    # TOS GetObjectOutput has no close method: its HTTP response lives under
    # content, optionally wrapped by CRC/progress/rate-limit adapters
    content = getattr(stream, "content", None)
    for _ in range(8):
        if content is None:
            break
        response = getattr(content, "resp", None)
        close = getattr(response, "close", None)
        if callable(close):
            close()
            return
        content = getattr(content, "data", None)


def _content_size(metadata: Any, download: bool) -> int:
    size = getattr(metadata, "content_length", None)
    if type(size) is not int or size < 0:
        raise RuntimeArtifactError("产物大小信息无效，请稍后重试", 502)
    maximum = DOWNLOAD_MAX_BYTES if download else PREVIEW_MAX_BYTES
    if size > maximum:
        message = (
            "文件超过下载大小限制" if download else "文件超过预览大小限制，请下载后查看"
        )
        raise RuntimeArtifactError(message, 413)
    return size


def _path(value: str, *, single_segment: bool = False) -> str:
    # Percent escapes are rejected even after URL decoding to prevent ambiguities
    # between the browser, ASGI router, and the object key namespace
    parts = value.split("/")
    if (
        not value
        or len(value.encode("utf-8")) > 1024
        or any(part in {"", ".", ".."} for part in parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or "\\" in value
        or "%" in value
        or (single_segment and len(parts) != 1)
    ):
        raise RuntimeArtifactError("产物路径无效")
    return value


def _mount(access: RuntimeArtifactAccess, session_id: str) -> ArtifactMount | None:
    user_id = _path(access.user_id, single_segment=True)
    session_id = _path(session_id, single_segment=True)
    config = access.runtime_detail.get("TosMountConfig")
    if not isinstance(config, Mapping) or config.get("EnableTos") is not True:
        return None
    points = config.get("MountPoints")
    if not isinstance(points, list):
        return None
    dedicated = [
        point
        for point in points
        if isinstance(point, Mapping)
        and str(point.get("LocalMountPath") or "").rstrip("/") == MOUNT_PATH
    ]
    if not dedicated:
        return None
    if len(dedicated) != 1:
        raise RuntimeArtifactError("Runtime 产物挂载配置存在冲突", 409)
    point = dedicated[0]
    bucket = str(point.get("BucketName") or "")
    bucket_path = str(point.get("BucketPath") or "/")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise RuntimeArtifactError("Runtime 产物存储桶配置无效", 409)
    if not bucket_path.startswith("/"):
        raise RuntimeArtifactError("Runtime 产物挂载路径配置无效", 409)
    root = bucket_path.strip("/")
    if root:
        root = _path(root)
    if root == "artifacts" or root.startswith("artifacts/"):
        parts = root.split("/")
        if len(parts) != 2:
            raise RuntimeArtifactError("Runtime 用户产物挂载路径配置无效", 409)
        if parts[1] != user_id:
            raise RuntimeArtifactError("当前用户无权访问此 Runtime 的产物存储", 403)
        return ArtifactMount(bucket, f"{root}/{session_id}/")
    # Keep already deployed root-mount Runtimes readable under their original layout
    prefix = f"{root}/" if root else ""
    return ArtifactMount(bucket, f"{prefix}artifacts/{user_id}/{session_id}/")


def _mime_type(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


def _storage_error(error: Exception) -> RuntimeArtifactError:
    status = getattr(error, "status_code", None)
    if status == 404:
        return RuntimeArtifactError("产物不存在或已被删除", 404)
    if status == 403:
        return RuntimeArtifactError("无法读取产物存储，请检查服务端 TOS 访问权限", 502)
    if status == 412:
        return RuntimeArtifactError("产物正在更新，请刷新后重试", 409)
    return RuntimeArtifactError("读取产物存储失败，请稍后重试", 502)


def _invalid_list_cursor(error: Exception) -> bool:
    if (
        getattr(error, "status_code", None) != 400
        or getattr(error, "code", None) != "InvalidArgument"
    ):
        return False
    message = str(getattr(error, "message", "") or "")
    return message == "The continuation token provided is incorrect" or bool(
        re.fullmatch(
            r"the key-marker\[.*\] does not start with prefix\[.*\]\.", message
        )
    )


def _range(header: str | None, size: int) -> tuple[int, int] | None:
    if header is None:
        return None
    if len(header) > 128:
        raise RuntimeArtifactError("文件读取范围无效", 416)
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
    if not match or size == 0 or not any(match.groups()):
        raise RuntimeArtifactError("文件读取范围无效", 416)
    start_text, end_text = match.groups()
    if not start_text:
        suffix = int(end_text)
        if not suffix:
            raise RuntimeArtifactError("文件读取范围无效", 416)
        return max(size - suffix, 0), size - 1
    start = int(start_text)
    end = min(int(end_text), size - 1) if end_text else size - 1
    if start >= size or end < start:
        raise RuntimeArtifactError("文件读取范围超出产物大小", 416)
    return start, end


class RuntimeArtifactService:
    def __init__(
        self,
        client_factory: Callable[[str, str], Any],
        *,
        studio_storage: StudioStorageConfig | None = None,
        studio_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._studio_storage = studio_storage
        self._studio_client_factory = studio_client_factory

    def _source(
        self, access: RuntimeArtifactAccess, session_id: str
    ) -> tuple[ArtifactMount | None, Callable[[], Any]]:
        user_id = _path(access.user_id, single_segment=True)
        session_id = _path(session_id, single_segment=True)
        storage = self._studio_storage
        if storage is not None and (storage.bucket or storage.region):
            if (
                not storage.configured
                or storage.provider != access.provider
                or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", storage.bucket)
                or self._studio_client_factory is None
            ):
                raise RuntimeArtifactError("Studio 产物存储配置无效", 409)
            return (
                ArtifactMount(storage.bucket, f"artifacts/{user_id}/{session_id}/"),
                self._studio_client_factory,
            )
        return (
            _mount(access, session_id),
            lambda: self._client_factory(access.provider, access.region),
        )

    async def list(
        self,
        access: RuntimeArtifactAccess,
        session_id: str,
        *,
        limit: int = 200,
        cursor: str = "",
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._list, access, session_id, limit, cursor)

    def _list(
        self, access: RuntimeArtifactAccess, session_id: str, limit: int, cursor: str
    ) -> dict[str, Any]:
        mount, client_factory = self._source(access, session_id)
        if mount is None:
            return {
                "available": False,
                "reason": "Studio 尚未配置会话产物存储",
                "items": [],
                "nextCursor": None,
            }
        if not 1 <= limit <= 500 or len(cursor) > 4096:
            raise RuntimeArtifactError("产物分页参数无效")
        try:
            client = client_factory()
            output = client.list_objects_type2(
                bucket=mount.bucket,
                prefix=mount.prefix,
                max_keys=limit,
                continuation_token=cursor,
            )
        except Exception as error:
            if cursor and _invalid_list_cursor(error):
                raise RuntimeArtifactError(
                    "产物分页游标无效或不属于当前会话，请重新加载产物列表", 400
                ) from error
            raise _storage_error(error) from error
        items = []
        for item in (getattr(output, "contents", None) or [])[:limit]:
            key = str(getattr(item, "key", ""))
            if not key.startswith(mount.prefix) or key.endswith("/"):
                continue
            path = key[len(mount.prefix) :]
            try:
                _path(path)
            except RuntimeArtifactError:
                continue
            modified = getattr(item, "last_modified", None)
            items.append(
                {
                    "path": path,
                    "name": PurePosixPath(path).name,
                    "sizeBytes": int(getattr(item, "size", 0)),
                    "mimeType": _mime_type(path),
                    "updatedAt": modified.isoformat()
                    if isinstance(modified, datetime)
                    else None,
                }
            )
        token = str(getattr(output, "next_continuation_token", "") or "")
        truncated = bool(getattr(output, "is_truncated", False))
        if truncated and (not token or token == cursor):
            raise RuntimeArtifactError("产物列表分页响应无效，请稍后重试", 502)
        return {
            "available": True,
            "reason": None,
            "items": items,
            "nextCursor": token if truncated else None,
        }

    async def open_content(
        self,
        access: RuntimeArtifactAccess,
        session_id: str,
        path: str,
        *,
        download: bool = False,
        range_header: str | None = None,
    ) -> ArtifactContent:
        return await asyncio.to_thread(
            self._open_content, access, session_id, path, download, range_header
        )

    def _open_content(
        self,
        access: RuntimeArtifactAccess,
        session_id: str,
        path: str,
        download: bool,
        range_header: str | None,
    ) -> ArtifactContent:
        path = _path(path)
        mount, client_factory = self._source(access, session_id)
        if mount is None:
            raise RuntimeArtifactError("Studio 尚未配置会话产物存储", 409)
        key = mount.prefix + path
        kwargs: dict[str, Any] = {"bucket": mount.bucket, "key": key}
        total_size = 0
        size = 0
        byte_range = None
        try:
            client = client_factory()
            if range_header is not None:
                metadata = client.head_object(bucket=mount.bucket, key=key)
                total_size = _content_size(metadata, download)
                byte_range = _range(range_header, total_size)
                if byte_range is not None:
                    kwargs["range_start"], kwargs["range_end"] = byte_range
                    size = byte_range[1] - byte_range[0] + 1
                etag = getattr(metadata, "etag", None)
                if etag:
                    kwargs["if_match"] = etag
            # GetObjectOutput includes content_length from the response headers
            # The SDK keeps GET bodies streaming, so a separate HEAD is unnecessary
            stream = client.get_object(**kwargs)
        except RuntimeArtifactError:
            raise
        except Exception as error:
            raise _storage_error(error) from error
        try:
            response_size = _content_size(stream, download)
            if byte_range is None:
                size = total_size = response_size
            elif response_size != size:
                raise RuntimeArtifactError("产物读取范围响应无效，请稍后重试", 502)
        except RuntimeArtifactError:
            _close_response(stream)
            raise
        return ArtifactContent(
            stream,
            PurePosixPath(path).name,
            _mime_type(path),
            size,
            total_size,
            byte_range,
        )
