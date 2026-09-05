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
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

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
_MAX_REVIEW_REPOSITORIES_BYTES = 64 * 1024


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


class TosGitHubAppReviewRepositoryStore:
    """Persist GitHub App PR review enablement in Studio's private TOS bucket."""

    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
        key: str = GITHUB_APP_REVIEW_STORAGE_KEY,
    ) -> None:
        if not bucket.strip():
            raise ValueError("GitHub App review storage requires a bucket.")
        self._bucket = bucket.strip()
        self._client_factory = client_factory
        self._key = key.strip("/")

    async def enabled_repositories(self) -> set[str]:
        return await asyncio.to_thread(self._enabled_repositories)

    async def save_enabled_repositories(self, repositories: list[str]) -> list[str]:
        return await asyncio.to_thread(self._save_enabled_repositories, repositories)

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
