# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""GitHub integration routes for the Studio applications directory."""

from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any, Protocol
from urllib.parse import quote, urlparse

import requests
from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

_GITHUB_API_ROOT = "https://api.github.com"
_WORKFLOW_PATH = ".github/workflows/publish-agentkit.yml"
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_PROJECT_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_RUNTIME_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_RUNTIME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REGIONS = {"cn-beijing", "cn-shanghai"}


class _HttpSession(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> Any: ...


class _CreatePullRequestBody(BaseModel):
    repository: str = Field(min_length=1, max_length=240)
    base_branch: str = Field(default="main", alias="baseBranch", max_length=200)
    project_path: str = Field(default=".", alias="projectPath", max_length=240)
    runtime_name: str = Field(alias="runtimeName", min_length=1, max_length=64)
    runtime_id: str = Field(alias="runtimeId", min_length=1, max_length=128)
    region: str = Field(default="cn-beijing", max_length=32)
    token: str = Field(min_length=1, max_length=512)

    model_config = {"populate_by_name": True}


class GitHubIntegrationError(RuntimeError):
    """A sanitized GitHub integration error suitable for browser display."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _repository_slug(value: str) -> str:
    candidate = value.strip().removesuffix(".git").strip("/")
    if candidate.startswith("git@github.com:"):
        candidate = candidate.removeprefix("git@github.com:")
    elif "://" in candidate:
        parsed = urlparse(candidate)
        if parsed.hostname not in {"github.com", "www.github.com"}:
            raise GitHubIntegrationError("仅支持 github.com 仓库")
        candidate = parsed.path.strip("/").removesuffix(".git")
    if not _REPOSITORY_RE.fullmatch(candidate):
        raise GitHubIntegrationError("GitHub Repo 格式应为 owner/repository")
    return candidate


def _project_path(value: str) -> str:
    candidate = value.strip() or "."
    path = PurePosixPath(candidate)
    if (
        candidate.startswith("/")
        or not _PROJECT_PATH_RE.fullmatch(candidate)
        or ".." in path.parts
    ):
        raise GitHubIntegrationError("Agent 项目目录必须是仓库内的安全相对路径")
    return candidate.rstrip("/") or "."


def _validate_body(body: _CreatePullRequestBody) -> tuple[str, str]:
    repository = _repository_slug(body.repository)
    project_path = _project_path(body.project_path)
    if not _BRANCH_RE.fullmatch(body.base_branch) or ".." in body.base_branch:
        raise GitHubIntegrationError("目标分支格式不正确")
    if not _RUNTIME_NAME_RE.fullmatch(body.runtime_name):
        raise GitHubIntegrationError(
            "Runtime 名称需以字母开头，且只能包含字母、数字、下划线和连字符"
        )
    if not _RUNTIME_ID_RE.fullmatch(body.runtime_id):
        raise GitHubIntegrationError("Runtime ID 格式不正确")
    if body.region not in _REGIONS:
        raise GitHubIntegrationError("暂仅支持北京或上海地域")
    return repository, project_path


def _workflow(
    *,
    base_branch: str,
    project_path: str,
    runtime_name: str,
    runtime_id: str,
    region: str,
) -> str:
    template = """name: Publish to AgentKit Runtime

on:
  push:
    branches:
      - __BASE_BRANCH__
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: __CONCURRENCY_GROUP__
  cancel-in-progress: true

jobs:
  publish:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: __PROJECT_PATH__
    env:
      VOLC_ACCESSKEY: ${{ secrets.VOLCENGINE_ACCESS_KEY }}
      VOLC_SECRETKEY: ${{ secrets.VOLCENGINE_SECRET_KEY }}
      VOLC_SESSIONTOKEN: ${{ secrets.VOLCENGINE_SESSION_TOKEN }}
      AGENTKIT_RUNTIME_NAME: __RUNTIME_NAME__
      AGENTKIT_RUNTIME_ID: __RUNTIME_ID__
      AGENTKIT_REGION: __REGION__
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install project and AgentKit SDK
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then python -m pip install -r requirements.txt; fi
          python -m pip install "agentkit-sdk-python>=0.8.0"
      - name: Publish Runtime
        shell: bash
        run: |
          python - <<'PY'
          import os
          from pathlib import Path

          import yaml
          from agentkit.sdk.runtime import types as runtime_types
          from agentkit.sdk.runtime.client import AgentkitRuntimeClient
          from agentkit.toolkit import sdk
          from agentkit.toolkit.models import PreflightMode

          runtime_client = AgentkitRuntimeClient(
              access_key=os.environ["VOLC_ACCESSKEY"],
              secret_key=os.environ["VOLC_SECRETKEY"],
              session_token=os.environ.get("VOLC_SESSIONTOKEN", ""),
              region=os.environ["AGENTKIT_REGION"],
          )
          runtime = runtime_client.get_runtime(
              runtime_types.GetRuntimeRequest(
                  runtime_id=os.environ["AGENTKIT_RUNTIME_ID"],
              )
          )
          runtime_name = getattr(runtime, "name", "") or os.environ["AGENTKIT_RUNTIME_NAME"]
          runtime_role_name = getattr(runtime, "role_name", "") or "Auto"
          next_version = (getattr(runtime, "current_version_number", 0) or 0) + 1

          config = {
              "common": {
                  "agent_name": runtime_name,
                  "entry_point": "app.py",
                  "description": "Continuously published from GitHub",
                  "python_version": "3.12",
                  "launch_type": "cloud",
              },
              "launch_types": {
                  "cloud": {
                      "region": os.environ["AGENTKIT_REGION"],
                      "project_name": "default",
                      "image_tag": f"veadk-v{next_version}",
                      "runtime_id": os.environ["AGENTKIT_RUNTIME_ID"],
                      "runtime_name": runtime_name,
                      "runtime_role_name": runtime_role_name,
                      "python_version": "3.12",
                  }
              },
          }
          config_path = Path("agentkit.yaml")
          config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
          result = sdk.launch(
              config_file=str(config_path),
              preflight_mode=PreflightMode.WARN,
          )
          if not result.success:
              raise SystemExit(f"AgentKit publish failed: {result.error}")
          PY
"""
    replacements = {
        "__BASE_BRANCH__": json.dumps(base_branch),
        "__PROJECT_PATH__": json.dumps(project_path),
        "__RUNTIME_NAME__": json.dumps(runtime_name),
        "__RUNTIME_ID__": json.dumps(runtime_id),
        "__REGION__": json.dumps(region),
        "__CONCURRENCY_GROUP__": json.dumps(f"agentkit-runtime-{runtime_id}"),
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


class GitHubIntegrationService:
    def __init__(
        self,
        *,
        session: _HttpSession | None = None,
        branch_factory: Callable[[], str] | None = None,
    ) -> None:
        self._session = session or requests.Session()
        self._branch_factory = branch_factory or (
            lambda: time.strftime("feat/agentkit-release-%Y%m%d%H%M%S", time.gmtime())
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

    def create_pull_request(self, body: _CreatePullRequestBody) -> dict[str, Any]:
        repository, project_path = _validate_body(body)
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

        branch = self._branch_factory()
        if not _BRANCH_RE.fullmatch(branch):
            raise GitHubIntegrationError("生成的发布分支格式不正确", status_code=500)
        self._request(
            "POST",
            f"{repo_path}/git/refs",
            token=body.token,
            expected={201},
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        branch_created = True
        try:
            content_response = self._request(
                "GET",
                f"{repo_path}/contents/{_WORKFLOW_PATH}?ref={quote(body.base_branch, safe='')}",
                token=body.token,
                expected={200, 404},
            )
            content_payload = content_response.json()
            file_sha = (
                str(content_payload.get("sha") or "")
                if content_response.status_code == 200
                else ""
            )
            workflow = _workflow(
                base_branch=body.base_branch,
                project_path=project_path,
                runtime_name=body.runtime_name,
                runtime_id=body.runtime_id,
                region=body.region,
            )
            commit_payload: dict[str, Any] = {
                "message": "feat: publish Agent to AgentKit Runtime",
                "content": base64.b64encode(workflow.encode()).decode(),
                "branch": branch,
            }
            if file_sha:
                commit_payload["sha"] = file_sha
            self._request(
                "PUT",
                f"{repo_path}/contents/{_WORKFLOW_PATH}",
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
                    "title": "feat: 持续发布到 AgentKit Runtime",
                    "head": branch,
                    "base": body.base_branch,
                    "body": (
                        "新增 GitHub Actions 工作流，在目标分支更新时持续发布到 "
                        "AgentKit Runtime。合并前请配置工作流所需的 Volcengine Secrets。"
                    ),
                },
            ).json()
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

        return {
            "number": int(pull_request["number"]),
            "url": str(pull_request["html_url"]),
            "branch": branch,
        }


def mount_github_integration_routes(
    app: Any,
    authorizer: Callable[[Request], object],
    *,
    service: GitHubIntegrationService | None = None,
) -> GitHubIntegrationService:
    """Mount the GitHub PR endpoint with the Studio management boundary."""
    integration = service or GitHubIntegrationService()

    @app.post("/web/integrations/github/pull-requests")
    async def _create_github_pull_request(
        body: _CreatePullRequestBody,
        request: Request,
    ) -> dict[str, Any]:
        authorizer(request)
        try:
            return await run_in_threadpool(integration.create_pull_request, body)
        except GitHubIntegrationError as error:
            raise HTTPException(
                status_code=error.status_code, detail=str(error)
            ) from error

    return integration
