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

"""GitHub-backed CI/CD orchestration for Studio-generated Agent projects."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote, urlparse

import requests

ProgressCallback = Callable[[str], None]

DEFAULT_STATE_PATH = Path.home() / ".veadk" / "github-cicd-pipelines.json"
GITHUB_API = "https://api.github.com"
MAX_PROJECT_FILES = 800
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024


class GitHubCicdError(RuntimeError):
    """User-facing CI/CD setup failure with credentials redacted."""

    def __init__(
        self,
        message: str,
        *,
        phase: str = "validation",
        runtime_id: str = "",
        log_path: str = "",
    ) -> None:
        super().__init__(message)
        self.phase = phase
        self.runtime_id = runtime_id
        self.log_path = log_path

    def to_response(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "failed",
            "phase": self.phase,
            "message": str(self),
        }
        if self.runtime_id:
            payload["runtimeId"] = self.runtime_id
        if self.log_path:
            payload["logPath"] = self.log_path
        return payload


def parse_github_repo_url(url: str) -> tuple[str, str]:
    """Return ``(owner, repo)`` for common GitHub HTTPS and SSH URLs."""
    raw = url.strip()
    if not raw:
        raise GitHubCicdError("GitHub repository URL is required")

    if raw.startswith("git@github.com:"):
        path = raw.removeprefix("git@github.com:")
    else:
        parsed = urlparse(raw)
        if parsed.netloc.lower() != "github.com":
            raise GitHubCicdError("Only github.com repository URLs are supported")
        path = parsed.path.lstrip("/")

    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        raise GitHubCicdError("GitHub repository URL must include owner and repo")
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    if not owner or not repo:
        raise GitHubCicdError("GitHub repository URL must include owner and repo")
    return owner, repo


def create_github_cicd_pipeline(
    *,
    project: object,
    github_url: str,
    github_token: str,
    base_branch: str = "main",
    region: str = "cn-beijing",
    github_client: Any | None = None,
    deployer: Callable[..., dict[str, Any]] | None = None,
    state_path: str | Path | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Create/update the GitHub branch and run the first AgentKit deployment."""
    _emit(progress, "Validating AgentProject...")
    project = _validate_project(project)
    token = github_token.strip()
    if not token:
        raise GitHubCicdError("GitHub token is required")
    base_branch = (base_branch or "main").strip()
    if not base_branch:
        raise GitHubCicdError("GitHub base branch is required")
    owner, repo = parse_github_repo_url(github_url)

    _emit(progress, f"Connecting GitHub repo {owner}/{repo}...")
    client = github_client or GitHubClient(token)
    state_file = Path(state_path) if state_path is not None else DEFAULT_STATE_PATH
    state = _load_state(state_file)
    studio_branch = f"studio/{_slug(project['name'])}"
    pipeline_id = _pipeline_id(owner, repo, studio_branch)
    pipeline_state = state.get(pipeline_id, {})

    client.ensure_repository_access(owner, repo)
    _emit(progress, f"Reading base branch {base_branch}...")
    source_sha = client.get_branch_head(owner, repo, base_branch)
    _emit(progress, f"Ensuring Studio branch {studio_branch}...")
    client.ensure_branch(
        owner,
        repo,
        branch=studio_branch,
        source_sha=source_sha,
    )
    _emit(progress, f"Committing {len(project['files'])} file(s) to {studio_branch}...")
    commit_sha = client.commit_files(
        owner,
        repo,
        branch=studio_branch,
        files=project["files"],
        message=f"Studio: update {project['name']} Agent project",
    )
    _emit(progress, f"Ensuring pull request {studio_branch} -> {base_branch}...")
    pr = client.ensure_pull_request(
        owner,
        repo,
        head_branch=studio_branch,
        base_branch=base_branch,
        title=f"Update {project['name']} from Studio",
        body=(
            "Studio generated this Agent project and triggered a GitHub CI/CD "
            "deployment to AgentKit Runtime."
        ),
    )

    runtime_id = str(pipeline_state.get("runtimeId") or "")
    deploy = deployer or _default_deployer
    deploy_kwargs = {
        "project": project,
        "region": region,
        "runtime_id": runtime_id,
        "description": f"GitHub CI/CD deployment from {owner}/{repo}@{studio_branch}",
    }
    if progress is not None:
        deploy_kwargs["progress"] = progress
    _emit(progress, "Deploying AgentKit Runtime...")
    try:
        deployment = deploy(**deploy_kwargs)
    except GitHubCicdError as error:
        failed_runtime_id = error.runtime_id or runtime_id
        _save_pipeline_state(
            state_file,
            state,
            pipeline_id=pipeline_id,
            github_url=github_url,
            owner=owner,
            repo=repo,
            base_branch=base_branch,
            studio_branch=studio_branch,
            pull_request_url=pr.url,
            runtime_id=failed_runtime_id,
            region=region,
            latest_commit_sha=commit_sha,
            status="failed",
            phase=error.phase,
            last_error=error.to_response(),
        )
        raise
    runtime_id = str(deployment.get("runtimeId") or runtime_id)

    _emit(progress, "Saving GitHub CI/CD pipeline state...")
    updated_at = _save_pipeline_state(
        state_file,
        state,
        pipeline_id=pipeline_id,
        github_url=github_url,
        owner=owner,
        repo=repo,
        base_branch=base_branch,
        studio_branch=studio_branch,
        pull_request_url=pr.url,
        runtime_id=runtime_id,
        region=region,
        latest_commit_sha=commit_sha,
        status="succeeded",
        phase="ready",
        last_error=None,
    )
    _emit(progress, "GitHub CI/CD pipeline ready.")

    return {
        "pipelineId": pipeline_id,
        "status": "succeeded",
        "phase": "ready",
        "updatedAt": updated_at,
        "github": {
            "owner": owner,
            "repo": repo,
            "baseBranch": base_branch,
            "branch": studio_branch,
            "commitSha": commit_sha,
            "pullRequestUrl": pr.url,
            "pullRequestNumber": pr.number,
        },
        "deployment": deployment,
    }


class GitHubClient:
    """Small GitHub REST client for branch, commit, and PR operations."""

    def __init__(self, token: str, *, session: requests.Session | None = None) -> None:
        self._token = token
        self._session = session or requests.Session()

    def ensure_repository_access(self, owner: str, repo: str) -> None:
        self._request("GET", f"/repos/{owner}/{repo}")

    def get_branch_head(self, owner: str, repo: str, branch: str) -> str:
        data = self._request(
            "GET",
            f"/repos/{owner}/{repo}/git/ref/heads/{quote(branch, safe='')}",
        )
        sha = str(((data.get("object") or {}).get("sha")) or "")
        if not sha:
            raise GitHubCicdError(f"GitHub branch has no head commit: {branch}")
        return sha

    def ensure_branch(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        source_sha: str,
    ) -> None:
        try:
            self.get_branch_head(owner, repo, branch)
            return
        except GitHubCicdError as error:
            if "404" not in str(error):
                raise
        self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": source_sha},
        )

    def commit_files(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        files: list[dict[str, str]],
        message: str,
    ) -> str:
        head_sha = self.get_branch_head(owner, repo, branch)
        head_commit = self._request(
            "GET",
            f"/repos/{owner}/{repo}/git/commits/{quote(head_sha, safe='')}",
        )
        base_tree = str(((head_commit.get("tree") or {}).get("sha")) or "")
        if not base_tree:
            raise GitHubCicdError("GitHub branch head commit has no tree")

        tree_entries = []
        for item in files:
            blob = self._request(
                "POST",
                f"/repos/{owner}/{repo}/git/blobs",
                json={"content": item["content"], "encoding": "utf-8"},
            )
            tree_entries.append(
                {
                    "path": item["path"],
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob["sha"],
                }
            )
        tree = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/trees",
            json={"base_tree": base_tree, "tree": tree_entries},
        )
        commit = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/commits",
            json={"message": message, "tree": tree["sha"], "parents": [head_sha]},
        )
        commit_sha = str(commit.get("sha") or "")
        if not commit_sha:
            raise GitHubCicdError("GitHub commit response did not include sha")
        self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/git/refs/heads/{quote(branch, safe='')}",
            json={"sha": commit_sha, "force": False},
        )
        return commit_sha

    def ensure_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> SimpleNamespace:
        pulls = self._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls",
            params={
                "state": "open",
                "head": f"{owner}:{head_branch}",
                "base": base_branch,
            },
        )
        if isinstance(pulls, list) and pulls:
            return _pull_namespace(pulls[0])
        created = self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "head": head_branch,
                "base": base_branch,
                "body": body,
            },
        )
        return _pull_namespace(created)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        response = self._session.request(
            method,
            f"{GITHUB_API}{path}",
            headers=headers,
            timeout=30,
            **kwargs,
        )
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason
            raise GitHubCicdError(
                _redact(
                    f"GitHub API {method} {path} failed: "
                    f"{response.status_code} {detail}",
                    self._token,
                ),
                phase="github",
            )
        if response.status_code == 204:
            return {}
        return response.json()


def _default_deployer(**kwargs: Any) -> dict[str, Any]:
    from veadk.cli.studio_agentkit_deploy import (
        StudioAgentkitDeployError,
        deploy_agentkit_project,
    )

    try:
        return deploy_agentkit_project(**kwargs)
    except StudioAgentkitDeployError as error:
        raise GitHubCicdError(
            str(error),
            phase=error.phase,
            runtime_id=error.runtime_id,
            log_path=error.log_path,
        ) from error


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _pull_namespace(data: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        number=int(data.get("number") or 0),
        url=str(data.get("html_url") or data.get("url") or ""),
    )


def _validate_project(project: object) -> dict[str, Any]:
    if not isinstance(project, dict):
        raise GitHubCicdError("AgentProject must be an object")
    name = str(project.get("name") or "").strip()
    if not name:
        raise GitHubCicdError("AgentProject name is required")
    files = project.get("files")
    if not isinstance(files, list) or not files:
        raise GitHubCicdError("AgentProject files are required")
    if len(files) > MAX_PROJECT_FILES:
        raise GitHubCicdError(f"AgentProject cannot exceed {MAX_PROJECT_FILES} files")

    normalized_files: list[dict[str, str]] = []
    total = 0
    for item in files:
        if not isinstance(item, dict):
            raise GitHubCicdError("AgentProject files must be objects")
        path = str(item.get("path") or "")
        content = item.get("content")
        if not path or path.startswith("/") or "\x00" in path:
            raise GitHubCicdError(f"Illegal file path: {path}")
        parts = Path(path).parts
        if any(part in ("", ".", "..") for part in parts):
            raise GitHubCicdError(f"Illegal file path: {path}")
        if not isinstance(content, str):
            raise GitHubCicdError(f"Invalid file content: {path}")
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            raise GitHubCicdError(f"File too large: {path}")
        total += len(encoded)
        if total > MAX_TOTAL_BYTES:
            raise GitHubCicdError("AgentProject is too large")
        normalized_files.append({"path": path, "content": content})
    return {"name": name, "files": normalized_files}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "agent"


def _pipeline_id(owner: str, repo: str, branch: str) -> str:
    return _slug(f"github-{owner}-{repo}-{branch.replace('/', '-')}")


def _save_pipeline_state(
    path: Path,
    state: dict[str, Any],
    *,
    pipeline_id: str,
    github_url: str,
    owner: str,
    repo: str,
    base_branch: str,
    studio_branch: str,
    pull_request_url: str,
    runtime_id: str,
    region: str,
    latest_commit_sha: str,
    status: str,
    phase: str,
    last_error: dict[str, Any] | None,
) -> str:
    updated_at = datetime.now(UTC).isoformat()
    state[pipeline_id] = {
        "pipelineId": pipeline_id,
        "githubUrl": github_url,
        "owner": owner,
        "repo": repo,
        "baseBranch": base_branch,
        "branch": studio_branch,
        "pullRequestUrl": pull_request_url,
        "runtimeId": runtime_id,
        "region": region,
        "latestCommitSha": latest_commit_sha,
        "status": status,
        "phase": phase,
        "updatedAt": updated_at,
    }
    if last_error is not None:
        state[pipeline_id]["lastError"] = last_error
    _save_state(path, state)
    return updated_at


def _load_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as error:
        raise GitHubCicdError(f"GitHub CI/CD state file is invalid: {path}") from error
    return data if isinstance(data, dict) else {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _redact(text: str, *secrets: str) -> str:
    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, "***")
    return result
