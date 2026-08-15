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

import asyncio
import json
from pathlib import PurePosixPath
import shlex
from typing import Any, Callable, TypeVar
from uuid import uuid4

import requests
from agentkit.toolkit.cli.sandbox.sandbox_client import (
    SANDBOX_FILE_DOWNLOAD_ROUTE,
    build_exec_url,
    build_file_url,
)

_MAX_PATH_BYTES = 512
_MAX_TRANSFER_BYTES = 20 * 1024 * 1024
_MAX_COMMAND_OUTPUT_BYTES = 16 * 1024 * 1024
_RETRYABLE_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}
_T = TypeVar("_T")


class SandboxRemoteError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class SandboxRemoteResponseError(SandboxRemoteError):
    pass


class SandboxRemoteSizeError(SandboxRemoteResponseError):
    pass


def _exact_file_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
        or "\x00" in value
    ):
        raise SandboxRemoteResponseError("Sandbox file path is invalid")
    path = PurePosixPath(value)
    if (
        value != path.as_posix()
        or value.endswith("/")
        or any(part in {"", ".", ".."} for part in path.parts[1:])
        or len(value.encode("utf-8")) > _MAX_PATH_BYTES
        or not path.name
    ):
        raise SandboxRemoteResponseError("Sandbox file path is invalid")
    return value


def _is_transient(error: BaseException, *, retry_conflict: bool) -> bool:
    if isinstance(error, (requests.ConnectionError, requests.Timeout)):
        return True
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    return status in _RETRYABLE_HTTP_STATUSES or (retry_conflict and status == 409)


class SandboxRemoteTransport:
    """Bounded data-plane transport shared by sandbox-backed Studio features."""

    def __init__(self, endpoint: str, *, read_attempts: int = 2) -> None:
        if read_attempts < 1:
            raise ValueError("read_attempts must be positive")
        self._endpoint = endpoint
        self._read_attempts = read_attempts

    async def exec_text(self, command: str, *, timeout: int = 12) -> str:
        """Execute once. Callers reconcile ambiguous mutating outcomes themselves."""
        payload = await asyncio.to_thread(self._post_exec, command, timeout)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise SandboxRemoteResponseError("Sandbox command response has no data")
        output = data.get("output")
        if not isinstance(output, str):
            raise SandboxRemoteResponseError("Sandbox command response has no output")
        complete_path = data.get("full_output_file_path")
        if complete_path is not None:
            content = await self.download(
                _exact_file_path(complete_path), max_bytes=_MAX_COMMAND_OUTPUT_BYTES
            )
            try:
                return content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise SandboxRemoteResponseError(
                    "Sandbox command output is not UTF-8"
                ) from error
        if len(output.encode("utf-8")) > _MAX_COMMAND_OUTPUT_BYTES:
            raise SandboxRemoteSizeError("Sandbox command output exceeds the limit")
        return output

    async def exec_json(self, command: str, *, timeout: int = 12) -> dict[str, Any]:
        output = await self.exec_text(command, timeout=timeout)
        try:
            value: object = json.loads(output)
        except ValueError as first_error:
            try:
                tokens = shlex.split(output)
                if len(tokens) != 1 or tokens[0] == output:
                    raise first_error
                value = json.loads(tokens[0])
            except ValueError as error:
                raise SandboxRemoteResponseError(
                    "Sandbox command output is not valid JSON"
                ) from error
        if not isinstance(value, dict):
            raise SandboxRemoteResponseError(
                "Sandbox command output is not a JSON object"
            )
        return value

    async def upload(
        self,
        path: str,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        max_bytes: int = _MAX_TRANSFER_BYTES,
        mode: int | None = None,
    ) -> None:
        path = _exact_file_path(path)
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        if max_bytes < 0:
            raise ValueError("max_bytes must not be negative")
        if len(content) > max_bytes:
            raise SandboxRemoteSizeError("Sandbox upload exceeds the limit")
        if mode is not None and (
            isinstance(mode, bool) or not isinstance(mode, int) or mode & ~0o777
        ):
            raise ValueError("mode must be a permission mode")

        def operation() -> None:
            response = requests.post(
                build_file_url(self._endpoint, "/v1/file/upload"),
                data={"path": path},
                files={"file": (PurePosixPath(path).name, content, media_type)},
                timeout=(10, 120),
            )
            self._check_response(response, retry_conflict=False)

        await self._read_retry(operation, "upload Sandbox file", retry_conflict=False)
        if mode is not None:
            marker = uuid4().hex
            source = (
                "import json,os,stat\n"
                f"path={path!r}; expected={mode}; marker={marker!r}\n"
                "fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))\n"
                "try:\n"
                " st=os.fstat(fd)\n"
                " if not stat.S_ISREG(st.st_mode): raise ValueError('not regular')\n"
                " os.fchmod(fd,expected)\n"
                " st=os.fstat(fd)\n"
                " if stat.S_IMODE(st.st_mode)!=expected: raise ValueError('mode mismatch')\n"
                "finally: os.close(fd)\n"
                "print(json.dumps({'marker':marker}))\n"
            )
            result = await self.exec_json(
                f"python3 -c {shlex.quote(source)}", timeout=12
            )
            if result != {"marker": marker}:
                raise SandboxRemoteResponseError(
                    "Sandbox upload permission verification failed"
                )

    async def download(
        self, path: str, *, max_bytes: int = _MAX_TRANSFER_BYTES
    ) -> bytes:
        path = _exact_file_path(path)
        if max_bytes < 0:
            raise ValueError("max_bytes must not be negative")

        def operation() -> bytes:
            with requests.get(
                build_file_url(self._endpoint, SANDBOX_FILE_DOWNLOAD_ROUTE),
                params={"path": path, "change_policy": "abort"},
                timeout=(10, 120),
                stream=True,
            ) as response:
                self._check_response(response, retry_conflict=True)
                content = bytearray()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    if len(content) + len(chunk) > max_bytes:
                        raise SandboxRemoteSizeError(
                            "Sandbox download exceeds the limit"
                        )
                    content.extend(chunk)
                return bytes(content)

        return await self._read_retry(
            operation, "download Sandbox file", retry_conflict=True
        )

    def _post_exec(self, command: str, timeout: int) -> dict[str, Any]:
        try:
            response = requests.post(
                build_exec_url(self._endpoint),
                json={"id": "", "exec_dir": "/home/gem", "command": command},
                timeout=(5, timeout),
            )
            self._check_response(response, retry_conflict=False)
            payload: object = response.json()
        except SandboxRemoteError:
            raise
        except Exception as error:
            raise SandboxRemoteError(
                "Sandbox command outcome is unknown",
                retryable=_is_transient(error, retry_conflict=False),
            ) from error
        if not isinstance(payload, dict):
            raise SandboxRemoteResponseError(
                "Sandbox command response is not a JSON object"
            )
        return payload

    async def _read_retry(
        self,
        operation: Callable[[], _T],
        description: str,
        *,
        retry_conflict: bool,
    ) -> _T:
        for attempt in range(self._read_attempts):
            try:
                return await asyncio.to_thread(operation)
            except SandboxRemoteResponseError:
                raise
            except Exception as error:
                retryable = _is_transient(error, retry_conflict=retry_conflict)
                if not retryable or attempt + 1 >= self._read_attempts:
                    raise SandboxRemoteError(
                        f"Failed to {description}", retryable=retryable
                    ) from error
                await asyncio.sleep(0.2 * (2**attempt))
        raise RuntimeError("Sandbox read retry loop exited unexpectedly")

    @staticmethod
    def _check_response(response: requests.Response, *, retry_conflict: bool) -> None:
        status = response.status_code
        if status >= 400:
            error = requests.HTTPError("Sandbox request failed", response=response)
            if _is_transient(error, retry_conflict=retry_conflict):
                raise error
            raise SandboxRemoteError("Sandbox request failed") from error
