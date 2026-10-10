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

"""Client for the ma-infra ``/v1/skills`` interface.

The ma-infra control plane owns the customer skill registry (each authenticated
account maps to one default skill space) and exposes the Anthropic-compatible
``/v1/skills`` REST API. This client lets runtime consumers read,
download and publish skills through that interface instead of talking to the
AgentKit Skill TOP service directly.

Connection parameters come from the environment, which the ma-infra dispatcher
injects when it starts the worker process:

- ``MA_SKILLS_BASE_URL`` — ma-infra base URL (e.g. ``https://ma-infra.example``).
- ``MA_SKILLS_API_KEY`` — API key sent as ``x-api-key`` (or ``Authorization``).
- ``MA_SKILLS_ACCOUNT_ID`` — account id sent as ``X-Top-Account-Id``.

All methods are synchronous; the async helpers wrap them with
:func:`asyncio.to_thread` so blocking HTTP stays off the event loop.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx

# Mirror the ma-infra content size cap (internal/skills/top.go maxContentBytes).
MAX_CONTENT_BYTES = 32 * 1024 * 1024

DEFAULT_SKILL_SPACE_ID = "ma_infra_customer_skills"
DEFAULT_SKILL_SPACE_DESCRIPTION = "ma-infra customer skill space"


class MaInfraSkillError(RuntimeError):
    """A failed or rejected ma-infra skills request."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        code: str = "api_error",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class MaInfraSkillConfig:
    """Connection configuration for the ma-infra skills interface."""

    base_url: str
    api_key: str = ""
    account_id: str = ""
    timeout: float = 30.0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "MaInfraSkillConfig | None":
        """Read configuration from the environment, or ``None`` when unset."""
        source = os.environ if env is None else env
        base_url = (source.get("MA_SKILLS_BASE_URL") or "").strip().rstrip("/")
        if not base_url:
            return None
        return cls(
            base_url=base_url,
            api_key=(source.get("MA_SKILLS_API_KEY") or "").strip(),
            account_id=(source.get("MA_SKILLS_ACCOUNT_ID") or "").strip(),
        )


class MaInfraSkillsClient:
    """Thin HTTP client over the ma-infra ``/v1/skills`` REST API."""

    def __init__(
        self, config: MaInfraSkillConfig, *, transport: Any | None = None
    ) -> None:
        self._config = config
        self._http = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    # -- auth -------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["x-api-key"] = self._config.api_key
        if self._config.account_id:
            headers["X-Top-Account-Id"] = self._config.account_id
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        files: Any | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        merged = self._headers()
        if files is not None:
            # multipart requests carry their own content type.
            merged.pop("Content-Type", None)
        if headers:
            merged.update(headers)
        try:
            response = self._http.request(
                method,
                path,
                params=params,
                json=json,
                files=files,
                data=data,
                headers=merged,
            )
        except httpx.HTTPError as error:
            raise MaInfraSkillError(
                "ma-infra skills request failed",
                status_code=502,
                retryable=True,
            ) from error
        if response.status_code // 100 != 2:
            raise self._error(response)
        return response

    @staticmethod
    def _error(response: httpx.Response) -> MaInfraSkillError:
        status = response.status_code
        code, message = "api_error", f"ma-infra skills request failed (HTTP {status})"
        try:
            payload = response.json()
            error = payload.get("error") or payload.get("Error") or {}
            if isinstance(error, dict):
                code = str(
                    error.get("type") or error.get("code") or error.get("Code") or code
                )
                message = str(error.get("message") or error.get("Message") or message)
        except Exception:  # noqa: BLE001 - never fail on a malformed error body
            pass
        return MaInfraSkillError(
            message,
            status_code=status,
            code=code,
            retryable=status >= 500 or status == 429,
        )

    # -- skills (v1 interface) --------------------------------------------

    def list_skills(
        self,
        *,
        limit: int = 100,
        page: int = 1,
        source: str = "custom",
    ) -> list[dict[str, Any]]:
        """Return custom skills for the configured account."""
        return self.list_skills_page(limit=limit, page=page, source=source)["data"]

    def list_skills_page(
        self,
        *,
        limit: int = 100,
        page: int = 1,
        source: str = "custom",
    ) -> dict[str, Any]:
        """Return one skills page together with server pagination metadata."""
        response = self._request(
            "GET",
            "/v1/skills",
            params={"limit": limit, "page": page, "source": source},
        )
        payload = response.json()
        return {
            "data": list(payload.get("data") or []),
            "next_page": payload.get("next_page"),
            "total_count": payload.get("total_count", payload.get("totalCount")),
        }

    def get_skill(self, skill_id: str) -> dict[str, Any]:
        """Return one skill's metadata (display_name, description, latest_version_id)."""
        response = self._request("GET", f"/v1/skills/{skill_id}")
        return response.json()

    def get_version(self, skill_id: str, version: str) -> dict[str, Any]:
        """Return one skill version (name, description, concrete ``id``).

        ``version`` may be ``"latest"``; the returned ``id`` is always a
        concrete version id usable for content download.
        """
        response = self._request("GET", f"/v1/skills/{skill_id}/versions/{version}")
        return response.json()

    def download_content(self, skill_id: str, version: str) -> bytes:
        """Download a skill version's zip archive.

        ``version`` may be ``"latest"``; a concrete version id is resolved first
        because the content endpoint only serves pinned versions.
        """
        version = (version or "").strip()
        if not version or version == "latest":
            meta = self.get_version(skill_id, "latest")
            version = str(meta.get("id") or meta.get("version") or "")
        if not version:
            raise MaInfraSkillError(
                f"ma-infra skill {skill_id} has no downloadable version",
                status_code=404,
                code="skill_version_not_found",
            )
        response = self._request(
            "GET", f"/v1/skills/{skill_id}/versions/{version}/content"
        )
        content = response.content
        if len(content) > MAX_CONTENT_BYTES:
            raise MaInfraSkillError(
                f"ma-infra skill {skill_id} archive exceeds 32 MiB",
                status_code=413,
                code="skill_archive_too_large",
            )
        return content

    def create_skill(self, display_name: str, archive: bytes) -> dict[str, Any]:
        """Publish a new custom skill from a zip archive."""
        if not display_name:
            raise MaInfraSkillError("skill display_name is required", status_code=400)
        response = self._request(
            "POST",
            "/v1/skills",
            files={"archive": ("skill.zip", archive, "application/zip")},
            data={"display_name": display_name},
        )
        return response.json()

    def create_version(
        self, skill_id: str, display_name: str, archive: bytes
    ) -> dict[str, Any]:
        """Publish a new version of an existing custom skill."""
        response = self._request(
            "POST",
            f"/v1/skills/{skill_id}/versions",
            files={"archive": ("skill.zip", archive, "application/zip")},
            data={"display_name": display_name},
        )
        return response.json()

    def delete_skill(self, skill_id: str) -> dict[str, Any]:
        """Delete a custom skill."""
        response = self._request("DELETE", f"/v1/skills/{skill_id}")
        return response.json()

    # -- async helpers ----------------------------------------------------

    async def alist_skills(self, **kwargs: Any) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.list_skills, **kwargs)

    async def aget_skill(self, skill_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self.get_skill, skill_id)

    async def aget_version(self, skill_id: str, version: str) -> dict[str, Any]:
        return await asyncio.to_thread(self.get_version, skill_id, version)

    async def adownload_content(self, skill_id: str, version: str) -> bytes:
        return await asyncio.to_thread(self.download_content, skill_id, version)

    async def acreate_skill(self, display_name: str, archive: bytes) -> dict[str, Any]:
        return await asyncio.to_thread(self.create_skill, display_name, archive)

    async def acreate_version(
        self, skill_id: str, display_name: str, archive: bytes
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self.create_version, skill_id, display_name, archive
        )

    async def adelete_skill(self, skill_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self.delete_skill, skill_id)


__all__ = [
    "DEFAULT_SKILL_SPACE_ID",
    "DEFAULT_SKILL_SPACE_DESCRIPTION",
    "MaInfraSkillConfig",
    "MaInfraSkillError",
    "MaInfraSkillsClient",
]
