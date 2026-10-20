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

"""GitHub App helpers for Studio PR review automation."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
import time
import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import uuid4

import httpx


GITHUB_API_ROOT = "https://api.github.com"
GITHUB_APP_ID_ENV = "VEADK_GITHUB_APP_ID"
GITHUB_APP_SLUG_ENV = "VEADK_GITHUB_APP_SLUG"
GITHUB_APP_PRIVATE_KEY_ENV = "VEADK_GITHUB_APP_PRIVATE_KEY"
GITHUB_APP_PRIVATE_KEY_B64_ENV = "VEADK_GITHUB_APP_PRIVATE_KEY_B64"
GITHUB_APP_PRIVATE_KEY_PATH_ENV = "VEADK_GITHUB_APP_PRIVATE_KEY_PATH"
GITHUB_APP_WEBHOOK_SECRET_ENV = "VEADK_GITHUB_APP_WEBHOOK_SECRET"
GITHUB_APP_REVIEW_OWNER_ID_ENV = "VEADK_GITHUB_APP_REVIEW_OWNER_ID"
GITHUB_APP_REVIEW_CREATOR_ENV = "VEADK_GITHUB_APP_REVIEW_CREATOR"
GITHUB_APP_REVIEW_STORAGE_KEY = "veadk-studio/v1/github-pr-review/repositories.json"
GITHUB_APP_REVIEW_HISTORY_KEY = "veadk-studio/v1/github-pr-review/history.json"
_MAX_REVIEW_REPOSITORIES_BYTES = 64 * 1024
_MAX_REVIEW_HISTORY_BYTES = 256 * 1024
_MAX_REVIEW_HISTORY_ITEMS = 50


@dataclass(frozen=True)
class PageRequest:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass(frozen=True)
class PageResult:
    page: int
    page_size: int
    has_next_page: bool


class GitHubAppReviewError(RuntimeError):
    """GitHub App review integration failed with a user-safe message."""


class GitHubAppReviewStorageUnavailable(GitHubAppReviewError):
    """GitHub App review enablement cannot be read or written."""


@dataclass(frozen=True)
class GitHubAppConfig:
    app_id: str
    app_slug: str
    private_key: str
    webhook_secret: str
    review_owner_id: str = "github-app"
    review_creator_name: str = "GitHub App"

    @property
    def install_url(self) -> str:
        return f"https://github.com/apps/{self.app_slug}/installations/new"


@dataclass(frozen=True)
class GitHubPullRequestEvent:
    delivery_id: str
    action: str
    installation_id: int
    repository: str
    pull_request_url: str
    pull_request_number: int
    head_repository: str
    draft: bool

    @property
    def should_review(self) -> bool:
        return (
            self.action in {"opened", "synchronize", "reopened", "ready_for_review"}
            and not self.draft
            and self.head_repository == self.repository
        )


@dataclass(frozen=True)
class GitHubInstalledRepository:
    installation_id: int
    account: str
    full_name: str
    html_url: str
    private: bool

    def to_public_dict(self, *, review_enabled: bool) -> dict[str, object]:
        return {
            "installationId": self.installation_id,
            "account": self.account,
            "fullName": self.full_name,
            "htmlUrl": self.html_url,
            "private": self.private,
            "reviewEnabled": review_enabled,
        }


@dataclass(frozen=True)
class GitHubPullRequestReviewRecord:
    record_id: str
    repository: str
    pull_request_url: str
    pull_request_number: int
    status: str
    trigger: str
    created_at: str
    delivery_id: str = ""
    action: str = ""
    session_id: str = ""
    display_name: str = ""
    reason: str = ""

    def to_public_dict(self) -> dict[str, object]:
        return {
            "id": self.record_id,
            "repository": self.repository,
            "pullRequestUrl": self.pull_request_url,
            "pullRequestNumber": self.pull_request_number,
            "status": self.status,
            "trigger": self.trigger,
            "createdAt": self.created_at,
            "deliveryId": self.delivery_id,
            "action": self.action,
            "sessionId": self.session_id,
            "displayName": self.display_name,
            "reason": self.reason,
        }


class TosGitHubAppReviewRepositoryStore:
    """Persist GitHub App PR review enablement in Studio's private TOS bucket."""

    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
        key: str = GITHUB_APP_REVIEW_STORAGE_KEY,
        history_key: str = GITHUB_APP_REVIEW_HISTORY_KEY,
    ) -> None:
        if not bucket.strip():
            raise ValueError("GitHub App review storage requires a bucket.")
        self._bucket = bucket.strip()
        self._client_factory = client_factory
        self._key = key.strip("/")
        self._history_key = history_key.strip("/")

    async def enabled_repositories(self) -> set[str]:
        return await asyncio.to_thread(self._enabled_repositories)

    async def save_enabled_repositories(self, repositories: list[str]) -> list[str]:
        return await asyncio.to_thread(self._save_enabled_repositories, repositories)

    async def review_records(self) -> list[GitHubPullRequestReviewRecord]:
        return await asyncio.to_thread(self._review_records)

    async def review_records_page(
        self,
        page_request: PageRequest,
    ) -> tuple[list[GitHubPullRequestReviewRecord], PageResult]:
        return await asyncio.to_thread(self._review_records_page, page_request)

    async def append_review_record(
        self,
        record: GitHubPullRequestReviewRecord,
    ) -> GitHubPullRequestReviewRecord:
        return await asyncio.to_thread(self._append_review_record, record)

    async def update_review_record_status(
        self,
        record_id: str,
        *,
        status: str,
        reason: str = "",
    ) -> GitHubPullRequestReviewRecord | None:
        return await asyncio.to_thread(
            self._update_review_record_status,
            record_id,
            status=status,
            reason=reason,
        )

    def _enabled_repositories(self) -> set[str]:
        client = self._client_factory()
        try:
            response = client.get_object(bucket=self._bucket, key=self._key)
        except Exception as error:
            if _status_code(error) == 404:
                return set()
            raise GitHubAppReviewStorageUnavailable(
                "无法读取 PR 自动评审仓库配置。"
            ) from error
        content = response.read(_MAX_REVIEW_REPOSITORIES_BYTES + 1)
        if (
            not isinstance(content, bytes)
            or len(content) > _MAX_REVIEW_REPOSITORIES_BYTES
        ):
            raise GitHubAppReviewStorageUnavailable("PR 自动评审仓库配置无效或过大。")
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise GitHubAppReviewStorageUnavailable(
                "PR 自动评审仓库配置不是有效 JSON。"
            ) from error
        repositories = (
            payload.get("repositories") if isinstance(payload, dict) else None
        )
        if not isinstance(repositories, list):
            raise GitHubAppReviewStorageUnavailable("PR 自动评审仓库配置格式无效。")
        normalized: set[str] = set()
        for repository in repositories:
            if not isinstance(repository, str):
                raise GitHubAppReviewStorageUnavailable("PR 自动评审仓库配置格式无效。")
            normalized.add(normalize_review_repository(repository))
        return normalized

    def _save_enabled_repositories(self, repositories: list[str]) -> list[str]:
        normalized = sorted(
            {normalize_review_repository(repository) for repository in repositories},
            key=str.casefold,
        )
        content = json.dumps(
            {"repositories": normalized},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(content) > _MAX_REVIEW_REPOSITORIES_BYTES:
            raise GitHubAppReviewStorageUnavailable("PR 自动评审仓库配置过大。")
        try:
            self._client_factory().put_object(
                bucket=self._bucket,
                key=self._key,
                content=content,
                content_length=len(content),
                content_type="application/json",
            )
        except Exception as error:
            raise GitHubAppReviewStorageUnavailable(
                "无法保存 PR 自动评审仓库配置。"
            ) from error
        return normalized

    def _review_records(self) -> list[GitHubPullRequestReviewRecord]:
        payload = self._read_json_object(
            self._history_key,
            max_bytes=_MAX_REVIEW_HISTORY_BYTES,
            not_found={},
            invalid_message="PR 评审记录格式无效。",
        )
        records = payload.get("records")
        if records is None:
            return []
        if not isinstance(records, list):
            raise GitHubAppReviewStorageUnavailable("PR 评审记录格式无效。")
        parsed: list[GitHubPullRequestReviewRecord] = []
        for item in records:
            if not isinstance(item, dict):
                raise GitHubAppReviewStorageUnavailable("PR 评审记录格式无效。")
            parsed.append(_review_record_from_payload(item))
        return parsed[:_MAX_REVIEW_HISTORY_ITEMS]

    def _review_records_page(
        self,
        page_request: PageRequest,
    ) -> tuple[list[GitHubPullRequestReviewRecord], PageResult]:
        records = self._review_records()
        start = page_request.offset
        end = start + page_request.page_size
        return records[start:end], PageResult(
            page=page_request.page,
            page_size=page_request.page_size,
            has_next_page=end < len(records),
        )

    def _append_review_record(
        self,
        record: GitHubPullRequestReviewRecord,
    ) -> GitHubPullRequestReviewRecord:
        records = [record, *self._review_records()]
        deduped: list[GitHubPullRequestReviewRecord] = []
        seen: set[str] = set()
        for item in records:
            if item.record_id in seen:
                continue
            seen.add(item.record_id)
            deduped.append(item)
            if len(deduped) >= _MAX_REVIEW_HISTORY_ITEMS:
                break
        self._write_review_records(deduped)
        return record

    def _update_review_record_status(
        self,
        record_id: str,
        *,
        status: str,
        reason: str = "",
    ) -> GitHubPullRequestReviewRecord | None:
        normalized_status = _review_record_status(status)
        records = self._review_records()
        updated_record: GitHubPullRequestReviewRecord | None = None
        updated_records: list[GitHubPullRequestReviewRecord] = []
        for item in records:
            if item.record_id == record_id:
                updated_record = replace(
                    item,
                    status=normalized_status,
                    reason=reason.strip()[:240],
                )
                updated_records.append(updated_record)
            else:
                updated_records.append(item)
        if updated_record is None:
            return None
        self._write_review_records(updated_records)
        return updated_record

    def _write_review_records(
        self,
        records: list[GitHubPullRequestReviewRecord],
    ) -> None:
        content = json.dumps(
            {"records": [item.to_public_dict() for item in records]},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(content) > _MAX_REVIEW_HISTORY_BYTES:
            raise GitHubAppReviewStorageUnavailable("PR 评审记录过大。")
        try:
            self._client_factory().put_object(
                bucket=self._bucket,
                key=self._history_key,
                content=content,
                content_length=len(content),
                content_type="application/json",
            )
        except Exception as error:
            raise GitHubAppReviewStorageUnavailable("无法保存 PR 评审记录。") from error

    def _read_json_object(
        self,
        key: str,
        *,
        max_bytes: int,
        not_found: dict[str, Any],
        invalid_message: str,
    ) -> dict[str, Any]:
        client = self._client_factory()
        try:
            response = client.get_object(bucket=self._bucket, key=key)
        except Exception as error:
            if _status_code(error) == 404:
                return dict(not_found)
            raise GitHubAppReviewStorageUnavailable(invalid_message) from error
        content = response.read(max_bytes + 1)
        if not isinstance(content, bytes) or len(content) > max_bytes:
            raise GitHubAppReviewStorageUnavailable(invalid_message)
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise GitHubAppReviewStorageUnavailable(invalid_message) from error
        if not isinstance(payload, dict):
            raise GitHubAppReviewStorageUnavailable(invalid_message)
        return payload


def load_github_app_config() -> GitHubAppConfig | None:
    """Return GitHub App config when the center-service integration is enabled."""
    app_id = (os.getenv(GITHUB_APP_ID_ENV) or "").strip()
    app_slug = (os.getenv(GITHUB_APP_SLUG_ENV) or "").strip()
    webhook_secret = (os.getenv(GITHUB_APP_WEBHOOK_SECRET_ENV) or "").strip()
    private_key = _load_private_key()
    if not any((app_id, app_slug, webhook_secret, private_key)):
        return None
    missing = [
        name
        for name, value in (
            (GITHUB_APP_ID_ENV, app_id),
            (GITHUB_APP_SLUG_ENV, app_slug),
            (GITHUB_APP_WEBHOOK_SECRET_ENV, webhook_secret),
            ("GitHub App private key", private_key),
        )
        if not value
    ]
    if missing:
        raise GitHubAppReviewError("GitHub App 配置不完整：" + "、".join(missing))
    return GitHubAppConfig(
        app_id=app_id,
        app_slug=app_slug,
        private_key=private_key,
        webhook_secret=webhook_secret,
        review_owner_id=(
            os.getenv(GITHUB_APP_REVIEW_OWNER_ID_ENV) or "github-app"
        ).strip()
        or "github-app",
        review_creator_name=(
            os.getenv(GITHUB_APP_REVIEW_CREATOR_ENV) or "GitHub App"
        ).strip()
        or "GitHub App",
    )


def github_app_public_config() -> dict[str, object]:
    """Return browser-safe GitHub App setup state."""
    try:
        config = load_github_app_config()
    except GitHubAppReviewError as error:
        slug = (os.getenv(GITHUB_APP_SLUG_ENV) or "").strip()
        return {
            "configured": False,
            "appSlug": slug,
            "installUrl": (
                f"https://github.com/apps/{slug}/installations/new" if slug else ""
            ),
            "reason": str(error),
        }
    if config is None:
        slug = (os.getenv(GITHUB_APP_SLUG_ENV) or "").strip()
        return {
            "configured": False,
            "appSlug": slug,
            "installUrl": (
                f"https://github.com/apps/{slug}/installations/new" if slug else ""
            ),
            "reason": "管理员未配置 GitHub App。",
        }
    return {
        "configured": True,
        "appSlug": config.app_slug,
        "installUrl": config.install_url,
        "reason": "",
    }


def verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    if not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_pull_request_event(
    payload: dict[str, Any],
    *,
    event_name: str,
    delivery_id: str,
) -> GitHubPullRequestEvent | None:
    if event_name != "pull_request":
        return None
    installation = payload.get("installation")
    repository = payload.get("repository")
    pull_request = payload.get("pull_request")
    if not isinstance(installation, dict) or not isinstance(repository, dict):
        raise GitHubAppReviewError("GitHub webhook 缺少 installation 或 repository。")
    if not isinstance(pull_request, dict):
        raise GitHubAppReviewError("GitHub webhook 缺少 pull_request。")

    installation_id = installation.get("id")
    repository_full_name = repository.get("full_name")
    pull_request_url = pull_request.get("html_url")
    pull_request_number = pull_request.get("number")
    head = pull_request.get("head")
    head_repo = head.get("repo") if isinstance(head, dict) else None
    head_repository = head_repo.get("full_name") if isinstance(head_repo, dict) else ""
    action = payload.get("action")
    if not isinstance(installation_id, int) or installation_id <= 0:
        raise GitHubAppReviewError("GitHub webhook installation id 无效。")
    if not isinstance(repository_full_name, str) or "/" not in repository_full_name:
        raise GitHubAppReviewError("GitHub webhook repository 无效。")
    if not isinstance(pull_request_url, str) or not pull_request_url:
        raise GitHubAppReviewError("GitHub webhook Pull Request URL 无效。")
    if not isinstance(pull_request_number, int) or pull_request_number <= 0:
        raise GitHubAppReviewError("GitHub webhook Pull Request 编号无效。")
    if not isinstance(action, str):
        raise GitHubAppReviewError("GitHub webhook action 无效。")
    return GitHubPullRequestEvent(
        delivery_id=delivery_id,
        action=action,
        installation_id=installation_id,
        repository=repository_full_name,
        pull_request_url=pull_request_url,
        pull_request_number=pull_request_number,
        head_repository=head_repository,
        draft=bool(pull_request.get("draft")),
    )


def create_review_record(
    *,
    repository: str,
    pull_request_url: str,
    pull_request_number: int,
    status: str,
    trigger: str,
    delivery_id: str = "",
    action: str = "",
    session_id: str = "",
    display_name: str = "",
    reason: str = "",
) -> GitHubPullRequestReviewRecord:
    return GitHubPullRequestReviewRecord(
        record_id=uuid4().hex,
        repository=normalize_review_repository(repository),
        pull_request_url=pull_request_url.strip(),
        pull_request_number=pull_request_number,
        status=_review_record_status(status),
        trigger=_review_record_trigger(trigger),
        created_at=datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        delivery_id=delivery_id.strip(),
        action=action.strip(),
        session_id=session_id.strip(),
        display_name=display_name.strip(),
        reason=reason.strip()[:240],
    )


def _review_record_from_payload(
    payload: dict[str, Any],
) -> GitHubPullRequestReviewRecord:
    record_id = _payload_text(payload, "id")
    repository = _payload_text(payload, "repository")
    pull_request_url = _payload_text(payload, "pullRequestUrl")
    pull_request_number = payload.get("pullRequestNumber")
    created_at = _payload_text(payload, "createdAt")
    if (
        not record_id
        or not repository
        or not pull_request_url
        or not isinstance(pull_request_number, int)
        or pull_request_number <= 0
        or not created_at
    ):
        raise GitHubAppReviewStorageUnavailable("PR 评审记录格式无效。")
    return GitHubPullRequestReviewRecord(
        record_id=record_id,
        repository=normalize_review_repository(repository),
        pull_request_url=pull_request_url,
        pull_request_number=pull_request_number,
        status=_review_record_status(_payload_text(payload, "status")),
        trigger=_review_record_trigger(_payload_text(payload, "trigger")),
        created_at=created_at,
        delivery_id=_payload_text(payload, "deliveryId"),
        action=_payload_text(payload, "action"),
        session_id=_payload_text(payload, "sessionId"),
        display_name=_payload_text(payload, "displayName"),
        reason=_payload_text(payload, "reason")[:240],
    )


def _payload_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _review_record_status(value: str) -> str:
    if value not in {"started", "completed", "ignored", "failed"}:
        raise GitHubAppReviewStorageUnavailable("PR 评审记录状态无效。")
    return value


def _review_record_trigger(value: str) -> str:
    if value not in {"manual", "webhook"}:
        raise GitHubAppReviewStorageUnavailable("PR 评审记录触发方式无效。")
    return value


class GitHubAppClient:
    def __init__(
        self,
        config: GitHubAppConfig,
        *,
        api_root: str = GITHUB_API_ROOT,
        timeout: float = 20.0,
    ) -> None:
        self._config = config
        self._api_root = api_root.rstrip("/")
        self._timeout = timeout

    async def installation_token(self, installation_id: int) -> str:
        payload = await self._request(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            token=self._app_jwt(),
        )
        if not isinstance(payload, dict):
            raise GitHubAppReviewError("GitHub App 响应格式无效。")
        token = payload.get("token")
        if not isinstance(token, str) or not token.strip():
            raise GitHubAppReviewError("GitHub 未返回 installation token。")
        return token

    async def repository_installation_id(self, owner: str, repo: str) -> int:
        payload = await self._request(
            "GET",
            f"/repos/{owner}/{repo}/installation",
            token=self._app_jwt(),
        )
        if not isinstance(payload, dict):
            raise GitHubAppReviewError("GitHub App 响应格式无效。")
        installation_id = payload.get("id")
        if not isinstance(installation_id, int) or installation_id <= 0:
            raise GitHubAppReviewError("GitHub 未返回有效 installation id。")
        return installation_id

    async def installed_repositories(self) -> list[GitHubInstalledRepository]:
        installations = await self._request_pages(
            "/app/installations",
            token=self._app_jwt(),
        )
        repositories: list[GitHubInstalledRepository] = []
        for installation in installations:
            if not isinstance(installation, dict):
                continue
            installation_id = installation.get("id")
            account = installation.get("account")
            account_login = account.get("login") if isinstance(account, dict) else ""
            if not isinstance(installation_id, int) or installation_id <= 0:
                continue
            token = await self.installation_token(installation_id)
            payloads = await self._request_pages(
                "/installation/repositories",
                token=token,
                list_key="repositories",
            )
            for repository in payloads:
                if not isinstance(repository, dict):
                    continue
                full_name = repository.get("full_name")
                html_url = repository.get("html_url")
                if not isinstance(full_name, str) or "/" not in full_name:
                    continue
                if not isinstance(html_url, str) or not html_url:
                    html_url = f"https://github.com/{full_name}"
                repositories.append(
                    GitHubInstalledRepository(
                        installation_id=installation_id,
                        account=str(account_login or full_name.split("/", 1)[0]),
                        full_name=full_name,
                        html_url=html_url,
                        private=bool(repository.get("private")),
                    )
                )
        return sorted(repositories, key=lambda item: item.full_name.casefold())

    async def _request(self, method: str, path: str, *, token: str) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method,
                    f"{self._api_root}{path}",
                    headers=headers,
                )
        except httpx.HTTPError as error:
            raise GitHubAppReviewError(
                "连接 GitHub 失败，请检查网络后重试。"
            ) from error
        payload = response.json() if response.content else {}
        if not response.is_success:
            message = payload.get("message") if isinstance(payload, dict) else ""
            detail = str(message or "").strip()
            raise GitHubAppReviewError(
                detail[:240] or f"GitHub App 请求失败（HTTP {response.status_code}）。"
            )
        if not isinstance(payload, (dict, list)):
            raise GitHubAppReviewError("GitHub App 响应格式无效。")
        return payload

    async def _request_pages(
        self,
        path: str,
        *,
        token: str,
        list_key: str | None = None,
    ) -> list[Any]:
        items: list[Any] = []
        separator = "&" if "?" in path else "?"
        for page in range(1, 101):
            payload = await self._request(
                "GET",
                f"{path}{separator}per_page=100&page={page}",
                token=token,
            )
            value: Any = payload.get(list_key) if list_key else payload
            if not isinstance(value, list):
                raise GitHubAppReviewError("GitHub App 响应格式无效。")
            items.extend(value)
            if len(value) < 100:
                break
        return items

    def _app_jwt(self) -> str:
        try:
            import jwt
        except ImportError as error:
            raise GitHubAppReviewError(
                "缺少 PyJWT 依赖，无法生成 GitHub App JWT。"
            ) from error
        issued_at = int(time.time()) - 60
        expires_at = issued_at + 9 * 60
        return jwt.encode(
            {"iat": issued_at, "exp": expires_at, "iss": self._config.app_id},
            self._config.private_key,
            algorithm="RS256",
        )


def _load_private_key() -> str:
    inline = (os.getenv(GITHUB_APP_PRIVATE_KEY_ENV) or "").strip()
    if inline:
        return inline.replace("\\n", "\n")
    encoded = (os.getenv(GITHUB_APP_PRIVATE_KEY_B64_ENV) or "").strip()
    if encoded:
        try:
            return base64.b64decode(encoded).decode().strip()
        except (binascii.Error, UnicodeDecodeError) as error:
            raise GitHubAppReviewError(
                "GitHub App private key base64 无效。"
            ) from error
    path = (os.getenv(GITHUB_APP_PRIVATE_KEY_PATH_ENV) or "").strip()
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as file:
            return file.read().strip()
    except OSError as error:
        raise GitHubAppReviewError("无法读取 GitHub App private key 文件。") from error


def normalize_review_repository(value: str) -> str:
    repository = value.strip().removesuffix(".git").strip("/")
    parts = repository.split("/")
    if (
        len(parts) != 2
        or not parts[0]
        or not parts[1]
        or any(not _is_github_name(part) for part in parts)
    ):
        raise GitHubAppReviewError("GitHub 仓库格式应为 owner/repository。")
    return f"{parts[0]}/{parts[1]}"


def _is_github_name(value: str) -> bool:
    return all(char.isalnum() or char in {"-", "_", "."} for char in value)


def _status_code(error: BaseException) -> int | None:
    for current in (error, error.__cause__, error.__context__):
        if current is None:
            continue
        for name in ("status_code", "status", "http_status"):
            value = getattr(current, name, None)
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                continue
    return None
