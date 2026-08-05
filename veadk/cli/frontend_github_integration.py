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

"""GitHub integration routes for the Studio applications directory."""

from __future__ import annotations

import base64
import time
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import quote

import requests
from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from veadk.cli.github_automations import (
    PullRequestReviewBody,
    RuntimeDeliveryBody,
    TemplateProjectBody,
    build_pull_request_review,
    build_runtime_delivery,
    build_template_project,
)
from veadk.cli.github_automations._shared import (
    AutomationPullRequest,
    AutomationValidationError,
    PullRequestFile,
    RepositoryPullRequestBody,
    branch_is_valid,
)

_GITHUB_API_ROOT = "https://api.github.com"


class _HttpSession(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> Any: ...


class GitHubIntegrationError(RuntimeError):
    """A sanitized GitHub integration error suitable for browser display."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubIntegrationService:
    def __init__(
        self,
        *,
        session: _HttpSession | None = None,
        branch_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._session = session or requests.Session()
        self._branch_factory = branch_factory or (
            lambda prefix: time.strftime(f"{prefix}-%Y%m%d%H%M%S", time.gmtime())
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        expected: set[int],
        **kwargs: Any,
    ) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            response = self._session.request(
                method,
                f"{_GITHUB_API_ROOT}{path}",
                headers=headers,
                timeout=20,
                **kwargs,
            )
        except requests.RequestException as error:
            raise GitHubIntegrationError(
                "连接 GitHub 失败，请稍后重试", status_code=502
            ) from error
        if response.status_code not in expected:
            try:
                message = str(response.json().get("message") or "")
            except (ValueError, AttributeError):
                message = ""
            message = message.replace(token, "***").strip()
            if response.status_code in {401, 403}:
                detail = "GitHub Token 无效或没有仓库写入权限"
            elif response.status_code == 404:
                detail = "仓库、分支或文件不存在，或 Token 无权访问"
            elif response.status_code == 422:
                detail = "GitHub 拒绝了提交，请检查分支是否已存在"
            else:
                detail = message[:240] or "GitHub 请求失败"
            raise GitHubIntegrationError(detail, status_code=502)
        return response

    def _create_automation_pull_request(
        self,
        *,
        body: RepositoryPullRequestBody,
        repository: str,
        files: tuple[PullRequestFile, ...],
        branch_prefix: str,
        title: str,
        description: str,
    ) -> dict[str, Any]:
        repo_path = f"/repos/{repository}"
        self._request("GET", repo_path, token=body.token, expected={200})
        base_ref = self._request(
            "GET",
            f"{repo_path}/git/ref/heads/{quote(body.base_branch, safe='/')}",
            token=body.token,
            expected={200},
        ).json()
        base_sha = str((base_ref.get("object") or {}).get("sha") or "")
        if not base_sha:
            raise GitHubIntegrationError("目标分支缺少有效 Git SHA", status_code=502)

        branch = self._branch_factory(branch_prefix)
        if not branch_is_valid(branch):
            raise GitHubIntegrationError("生成的分支格式不正确", status_code=500)
        self._request(
            "POST",
            f"{repo_path}/git/refs",
            token=body.token,
            expected={201},
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        branch_created = True
        try:
            for file in files:
                encoded_path = quote(file.path, safe="/")
                content_response = self._request(
                    "GET",
                    (
                        f"{repo_path}/contents/{encoded_path}"
                        f"?ref={quote(body.base_branch, safe='')}"
                    ),
                    token=body.token,
                    expected={200, 404},
                )
                if file.must_be_new and content_response.status_code == 200:
                    raise GitHubIntegrationError(
                        f"目标仓库中已存在 {file.path}，未覆盖现有文件"
                    )
                content_payload = content_response.json()
                file_sha = (
                    str(content_payload.get("sha") or "")
                    if content_response.status_code == 200
                    and isinstance(content_payload, dict)
                    else ""
                )
                if content_response.status_code == 200 and not file_sha:
                    raise GitHubIntegrationError(
                        f"目标路径 {file.path} 不是可更新的文件"
                    )
                commit_payload: dict[str, Any] = {
                    "message": file.commit_message,
                    "content": base64.b64encode(file.content.encode()).decode(),
                    "branch": branch,
                }
                if file_sha:
                    commit_payload["sha"] = file_sha
                self._request(
                    "PUT",
                    f"{repo_path}/contents/{encoded_path}",
                    token=body.token,
                    expected={200, 201},
                    json=commit_payload,
                )

            pull_request = self._request(
                "POST",
                f"{repo_path}/pulls",
                token=body.token,
                expected={201},
                json={
                    "title": title,
                    "head": branch,
                    "base": body.base_branch,
                    "body": description,
                },
            ).json()
            result = {
                "number": int(pull_request["number"]),
                "url": str(pull_request["html_url"]),
                "branch": branch,
            }
            branch_created = False
        finally:
            if branch_created:
                try:
                    self._request(
                        "DELETE",
                        f"{repo_path}/git/refs/heads/{quote(branch, safe='/')}",
                        token=body.token,
                        expected={204},
                    )
                except GitHubIntegrationError:
                    pass

        return result

    def _create_from_spec(
        self,
        body: RepositoryPullRequestBody,
        spec: AutomationPullRequest,
    ) -> dict[str, Any]:
        return self._create_automation_pull_request(
            body=body,
            repository=spec.repository,
            files=spec.files,
            branch_prefix=spec.branch_prefix,
            title=spec.title,
            description=spec.description,
        )

    def create_pull_request(self, body: RuntimeDeliveryBody) -> dict[str, Any]:
        return self._create_from_spec(body, build_runtime_delivery(body))

    def create_template_pull_request(self, body: TemplateProjectBody) -> dict[str, Any]:
        return self._create_from_spec(body, build_template_project(body))

    def create_review_pull_request(self, body: PullRequestReviewBody) -> dict[str, Any]:
        return self._create_from_spec(body, build_pull_request_review(body))


def mount_github_integration_routes(
    app: Any,
    authorizer: Callable[[Request], object],
    *,
    service: GitHubIntegrationService | None = None,
) -> GitHubIntegrationService:
    """Mount the GitHub PR endpoint with the Studio management boundary."""
    integration = service or GitHubIntegrationService()

    async def _run(
        callback: Callable[[Any], dict[str, Any]],
        body: BaseModel,
        request: Request,
    ) -> dict[str, Any]:
        authorizer(request)
        try:
            return await run_in_threadpool(callback, body)
        except AutomationValidationError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except GitHubIntegrationError as error:
            raise HTTPException(
                status_code=error.status_code, detail=str(error)
            ) from error

    @app.post("/web/integrations/github/pull-requests")
    async def _create_github_pull_request(
        body: RuntimeDeliveryBody,
        request: Request,
    ) -> dict[str, Any]:
        return await _run(integration.create_pull_request, body, request)

    @app.post("/web/integrations/github/template-pull-requests")
    async def _create_template_pull_request(
        body: TemplateProjectBody,
        request: Request,
    ) -> dict[str, Any]:
        return await _run(integration.create_template_pull_request, body, request)

    @app.post("/web/integrations/github/review-pull-requests")
    async def _create_review_pull_request(
        body: PullRequestReviewBody,
        request: Request,
    ) -> dict[str, Any]:
        return await _run(integration.create_review_pull_request, body, request)

    return integration
