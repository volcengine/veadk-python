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

import base64
import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote, urlparse

import requests

from veadk.utils.cloud_provider import (
    DEFAULT_BYTEPLUS_VIKING_MEMORY_REGION,
    DEFAULT_CLOUD_PROVIDER,
    CloudProvider,
    normalize_cloud_provider,
)

ProgressCallback = Callable[[str], None]

UTC = timezone.utc
DEFAULT_STATE_PATH = Path.home() / ".veadk" / "github-cicd-pipelines.json"
GITHUB_API = "https://api.github.com"
WORKFLOW_PATH = ".github/workflows/publish-agentkit.yml"
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
    cloud_provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
    github_client: Any | None = None,
    state_path: str | Path | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Push the Agent project source to a Studio-managed GitHub branch."""
    _emit(progress, "Validating AgentProject...")
    project = _validate_project(project)
    token = github_token.strip()
    if not token:
        raise GitHubCicdError("GitHub token is required")
    base_branch = (base_branch or "main").strip()
    if not base_branch:
        raise GitHubCicdError("GitHub base branch is required")
    cloud_provider = _normalize_delivery_cloud_provider(cloud_provider)
    owner, repo = parse_github_repo_url(github_url)

    _emit(progress, f"Connecting GitHub repo {owner}/{repo}...")
    client = github_client or GitHubClient(token)
    state_file = Path(state_path) if state_path is not None else DEFAULT_STATE_PATH
    state = _load_state(state_file)
    target_branch = base_branch
    pipeline_id = _pipeline_id(owner, repo, target_branch)
    existing = state.get(pipeline_id, {})

    github = _push_github_source(
        client=client,
        owner=owner,
        repo=repo,
        project=project,
        branch=target_branch,
        progress=progress,
    )

    _emit(progress, "Saving GitHub source sync state...")
    updated_at = _save_pipeline_state(
        state_file,
        state,
        pipeline_id=pipeline_id,
        github_url=github_url,
        owner=owner,
        repo=repo,
        base_branch=base_branch,
        studio_branch=target_branch,
        pull_request_url="",
        pull_request_number=0,
        runtime_id=str(existing.get("runtimeId") or ""),
        region=region,
        cloud_provider=cloud_provider,
        latest_commit_sha=github["commitSha"],
        github_token=token,
        status="succeeded",
        phase="ready",
        last_error=None,
    )
    _emit(progress, "GitHub source sync ready.")

    return {
        "pipelineId": pipeline_id,
        "status": "succeeded",
        "phase": "ready",
        "updatedAt": updated_at,
        "cloudProvider": cloud_provider,
        "github": github,
    }


def create_github_delivery_cicd_pipeline(
    *,
    github_url: str,
    github_token: str,
    base_branch: str = "main",
    runtime_name: str,
    runtime_id: str,
    region: str = "cn-beijing",
    cloud_provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
    project_path: str = ".",
    volcengine_access_key: str = "",
    volcengine_secret_key: str = "",
    volcengine_session_token: str = "",
    github_client: Any | None = None,
    state_path: str | Path | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Create/update the GitHub Actions workflow for Runtime continuous delivery."""
    token = github_token.strip()
    if not token:
        raise GitHubCicdError("GitHub token is required")
    base_branch = (base_branch or "main").strip()
    if not base_branch:
        raise GitHubCicdError("GitHub base branch is required")
    runtime_name = runtime_name.strip()
    runtime_id = runtime_id.strip()
    if not runtime_name:
        raise GitHubCicdError("Runtime name is required", phase="cicd")
    if not runtime_id:
        raise GitHubCicdError("Runtime ID is required", phase="cicd")
    cloud_provider = _normalize_delivery_cloud_provider(cloud_provider)
    project_path = _validate_project_path(project_path)
    owner, repo = parse_github_repo_url(github_url)

    client = github_client or GitHubClient(token)
    state_file = Path(state_path) if state_path is not None else DEFAULT_STATE_PATH
    state = _load_state(state_file)
    pipeline_id = _pipeline_id(owner, repo, base_branch)

    _emit(progress, f"Connecting GitHub repo {owner}/{repo}...")
    client.ensure_repository_access(owner, repo)
    _configure_runtime_delivery_secrets(
        client,
        owner,
        repo,
        access_key=volcengine_access_key,
        secret_key=volcengine_secret_key,
        session_token=volcengine_session_token,
        cloud_provider=cloud_provider,
        progress=progress,
    )
    _emit(progress, f"Writing GitHub Actions workflow to {base_branch}...")
    commit_sha = client.commit_files(
        owner,
        repo,
        branch=base_branch,
        files=[
            {
                "path": WORKFLOW_PATH,
                "content": _agentkit_runtime_workflow(
                    base_branch=base_branch,
                    project_path=project_path,
                    runtime_name=runtime_name,
                    runtime_id=runtime_id,
                    region=region,
                    cloud_provider=cloud_provider,
                ),
            }
        ],
        message="Studio: add GitHub Actions AgentKit Runtime delivery",
    )

    updated_at = _save_pipeline_state(
        state_file,
        state,
        pipeline_id=pipeline_id,
        github_url=github_url,
        owner=owner,
        repo=repo,
        base_branch=base_branch,
        studio_branch=base_branch,
        pull_request_url="",
        pull_request_number=0,
        runtime_id=runtime_id,
        region=region,
        cloud_provider=cloud_provider,
        latest_commit_sha=commit_sha,
        github_token=token,
        status="cicd-bound",
        phase="ready",
        last_error=None,
    )
    state[pipeline_id]["cicdEnabled"] = True
    state[pipeline_id]["workflowPath"] = WORKFLOW_PATH
    state[pipeline_id]["projectPath"] = project_path
    _append_version(
        state[pipeline_id],
        commit_sha=commit_sha,
        branch=base_branch,
        pull_request_url="",
        pull_request_number=0,
        author="Studio",
        status="current",
        source="github-cicd",
        description="挂载 GitHub 持续交付",
        created_at=updated_at,
    )
    _save_state(state_file, state)
    result = _state_to_response(state[pipeline_id])
    result["updatedAt"] = updated_at
    return result


def initialize_github_delivery_main(
    *,
    project: object,
    github_url: str,
    github_token: str,
    base_branch: str = "main",
    runtime_name: str,
    runtime_id: str,
    region: str = "cn-beijing",
    cloud_provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
    project_path: str = ".",
    volcengine_access_key: str = "",
    volcengine_secret_key: str = "",
    volcengine_session_token: str = "",
    github_client: Any | None = None,
    state_path: str | Path | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Initialize the target branch with Agent source and Runtime workflow."""
    _emit(progress, "Validating AgentProject...")
    project = _validate_project(project)
    token = github_token.strip()
    if not token:
        raise GitHubCicdError("GitHub token is required")
    base_branch = (base_branch or "main").strip()
    if not base_branch:
        raise GitHubCicdError("GitHub base branch is required")
    runtime_name = runtime_name.strip()
    runtime_id = runtime_id.strip()
    if not runtime_name:
        raise GitHubCicdError("Runtime name is required", phase="cicd")
    if not runtime_id:
        raise GitHubCicdError("Runtime ID is required", phase="cicd")
    cloud_provider = _normalize_delivery_cloud_provider(cloud_provider)
    project_path = _validate_project_path(project_path)
    owner, repo = parse_github_repo_url(github_url)

    _emit(progress, f"Connecting GitHub repo {owner}/{repo}...")
    client = github_client or GitHubClient(token)
    state_file = Path(state_path) if state_path is not None else DEFAULT_STATE_PATH
    state = _load_state(state_file)
    pipeline_id = _pipeline_id(owner, repo, base_branch)

    client.ensure_repository_access(owner, repo)
    _configure_runtime_delivery_secrets(
        client,
        owner,
        repo,
        access_key=volcengine_access_key,
        secret_key=volcengine_secret_key,
        session_token=volcengine_session_token,
        cloud_provider=cloud_provider,
        progress=progress,
    )
    files = [
        *project["files"],
        {
            "path": WORKFLOW_PATH,
            "content": _agentkit_runtime_workflow(
                base_branch=base_branch,
                project_path=project_path,
                runtime_name=runtime_name,
                runtime_id=runtime_id,
                region=region,
                cloud_provider=cloud_provider,
            ),
        },
    ]
    _emit(progress, f"Initializing {base_branch} with Agent source and workflow...")
    commit_sha = client.commit_files(
        owner,
        repo,
        branch=base_branch,
        files=files,
        message=f"Studio: initialize {project['name']} delivery [skip runtime]",
    )

    updated_at = _save_pipeline_state(
        state_file,
        state,
        pipeline_id=pipeline_id,
        github_url=github_url,
        owner=owner,
        repo=repo,
        base_branch=base_branch,
        studio_branch=base_branch,
        pull_request_url="",
        pull_request_number=0,
        runtime_id=runtime_id,
        region=region,
        cloud_provider=cloud_provider,
        latest_commit_sha=commit_sha,
        github_token=token,
        status="cicd-bound",
        phase="ready",
        last_error=None,
    )
    record = state[pipeline_id]
    record["cicdEnabled"] = True
    record["workflowPath"] = WORKFLOW_PATH
    record["projectPath"] = project_path
    _append_version(
        record,
        commit_sha=commit_sha,
        branch=base_branch,
        pull_request_url="",
        pull_request_number=0,
        author="Studio",
        status="current",
        source="github-cicd",
        description="初始化 GitHub 持续交付",
        created_at=updated_at,
    )
    _save_state(state_file, state)
    result = _state_to_response(record)
    result["updatedAt"] = updated_at
    return result


def attach_github_delivery_cicd_pipeline(
    *,
    pipeline_id: str,
    runtime_name: str,
    runtime_id: str,
    region: str = "cn-beijing",
    cloud_provider: CloudProvider | None = None,
    project_path: str = ".",
    github_token: str = "",
    volcengine_access_key: str = "",
    volcengine_secret_key: str = "",
    volcengine_session_token: str = "",
    github_client: Any | None = None,
    state_path: str | Path | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Attach GitHub Actions Runtime delivery to an existing source sync branch."""
    pipeline_id = pipeline_id.strip()
    runtime_name = runtime_name.strip()
    runtime_id = runtime_id.strip()
    if not pipeline_id:
        raise GitHubCicdError("GitHub CI/CD pipelineId is required", phase="cicd")
    if not runtime_name:
        raise GitHubCicdError("Runtime name is required", phase="cicd")
    if not runtime_id:
        raise GitHubCicdError("Runtime ID is required", phase="cicd")
    project_path = _validate_project_path(project_path)
    state_file = Path(state_path) if state_path is not None else DEFAULT_STATE_PATH
    state = _load_state(state_file)
    record = state.get(pipeline_id)
    if not isinstance(record, dict):
        raise GitHubCicdError(
            f"GitHub source sync binding is not found: {pipeline_id}",
            phase="cicd",
            runtime_id=runtime_id,
        )
    cloud_provider = _normalize_delivery_cloud_provider(
        cloud_provider or str(record.get("cloudProvider") or DEFAULT_CLOUD_PROVIDER)
    )

    token = github_token.strip() or str(record.get("githubToken") or "").strip()
    if not token:
        raise GitHubCicdError(
            "GitHub token is required to attach CICD to this source sync branch",
            phase="github",
            runtime_id=runtime_id,
        )
    owner = str(record.get("owner") or "")
    repo = str(record.get("repo") or "")
    base_branch = str(record.get("baseBranch") or "main")
    studio_branch = str(record.get("branch") or "")
    if not owner or not repo or not studio_branch:
        raise GitHubCicdError(
            "GitHub source sync binding is incomplete",
            phase="cicd",
            runtime_id=runtime_id,
        )

    _emit(progress, f"Writing GitHub Actions workflow to {studio_branch}...")
    client = github_client or GitHubClient(token)
    _configure_runtime_delivery_secrets(
        client,
        owner,
        repo,
        access_key=volcengine_access_key,
        secret_key=volcengine_secret_key,
        session_token=volcengine_session_token,
        cloud_provider=cloud_provider,
        progress=progress,
    )
    commit_sha = client.commit_files(
        owner,
        repo,
        branch=studio_branch,
        files=[
            {
                "path": WORKFLOW_PATH,
                "content": _agentkit_runtime_workflow(
                    base_branch=base_branch,
                    project_path=project_path,
                    runtime_name=runtime_name,
                    runtime_id=runtime_id,
                    region=region,
                    cloud_provider=cloud_provider,
                ),
            }
        ],
        message="Studio: add GitHub Actions AgentKit Runtime delivery",
    )

    record["runtimeId"] = runtime_id
    record["region"] = region
    record["cloudProvider"] = cloud_provider
    record["latestCommitSha"] = commit_sha
    record["githubToken"] = token
    record["status"] = "cicd-bound"
    record["phase"] = "ready"
    record["updatedAt"] = datetime.now(UTC).isoformat()
    record["cicdEnabled"] = True
    record["workflowPath"] = WORKFLOW_PATH
    record["projectPath"] = project_path
    _append_version(
        record,
        commit_sha=commit_sha,
        branch=studio_branch,
        pull_request_url="",
        pull_request_number=0,
        author="Studio",
        status="pending",
        source="github-cicd",
        description="挂载 GitHub 持续交付",
        created_at=str(record["updatedAt"]),
    )
    _save_state(state_file, state)
    return _state_to_response(record)


def bind_github_cicd_runtime(
    *,
    pipeline_id: str,
    runtime_id: str,
    region: str = "cn-beijing",
    cloud_provider: CloudProvider | None = None,
    state_path: str | Path | None = None,
) -> dict[str, Any]:
    """Bind an existing GitHub CI/CD pipeline record to an AgentKit Runtime."""
    pipeline_id = pipeline_id.strip()
    runtime_id = runtime_id.strip()
    if not pipeline_id:
        raise GitHubCicdError("GitHub CI/CD pipelineId is required", phase="binding")
    if not runtime_id:
        raise GitHubCicdError("Runtime ID is required", phase="binding")
    state_file = Path(state_path) if state_path is not None else DEFAULT_STATE_PATH
    state = _load_state(state_file)
    record = state.get(pipeline_id)
    if not isinstance(record, dict):
        raise GitHubCicdError(
            f"GitHub CI/CD pipeline is not found: {pipeline_id}",
            phase="binding",
        )
    cloud_provider = _normalize_delivery_cloud_provider(
        cloud_provider or str(record.get("cloudProvider") or DEFAULT_CLOUD_PROVIDER)
    )
    record["runtimeId"] = runtime_id
    record["region"] = region
    record["cloudProvider"] = cloud_provider
    record["status"] = "bound"
    record["phase"] = "ready"
    record["updatedAt"] = datetime.now(UTC).isoformat()
    _save_state(state_file, state)
    return _state_to_response(record)


def get_github_cicd_runtime_binding(
    *,
    runtime_id: str,
    state_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return the GitHub CI/CD binding for a Runtime, or an empty object."""
    runtime_id = runtime_id.strip()
    if not runtime_id:
        raise GitHubCicdError("Runtime ID is required", phase="binding")
    state_file = Path(state_path) if state_path is not None else DEFAULT_STATE_PATH
    record = _find_state_by_runtime_id(_load_state(state_file), runtime_id)
    return _state_to_response(record) if record else {}


def sync_github_cicd_runtime(
    *,
    runtime_id: str,
    project: object,
    github_token: str = "",
    github_client: Any | None = None,
    state_path: str | Path | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Sync the current Agent project to the GitHub branch bound to ``runtime_id``."""
    runtime_id = runtime_id.strip()
    if not runtime_id:
        raise GitHubCicdError("Runtime ID is required", phase="binding")
    _emit(progress, "Checking GitHub CI/CD binding...")
    project = _validate_project(project)
    state_file = Path(state_path) if state_path is not None else DEFAULT_STATE_PATH
    state = _load_state(state_file)
    record = _find_state_by_runtime_id(state, runtime_id)
    if record is None:
        raise GitHubCicdError(
            f"Runtime is not bound to GitHub CI/CD: {runtime_id}",
            phase="binding",
            runtime_id=runtime_id,
        )
    token = github_token.strip() or str(record.get("githubToken") or "").strip()
    if not token:
        raise GitHubCicdError(
            "GitHub token is required to sync this Runtime",
            phase="github",
            runtime_id=runtime_id,
        )
    owner = str(record.get("owner") or "")
    repo = str(record.get("repo") or "")
    base_branch = str(record.get("baseBranch") or "main")
    bound_branch = str(record.get("branch") or "")
    if not owner or not repo or not bound_branch:
        raise GitHubCicdError(
            "GitHub CI/CD binding is incomplete",
            phase="binding",
            runtime_id=runtime_id,
        )
    client = github_client or GitHubClient(token)
    github = _push_github_source(
        client=client,
        owner=owner,
        repo=repo,
        project=project,
        branch=bound_branch,
        progress=progress,
    )
    latest_commit_sha = github["commitSha"]
    saved_branch = bound_branch
    if bool(record.get("cicdEnabled")):
        status = "submitted"
        version_status = "submitted"
        version_source = "github-cicd"
        version_description = "提交 Agent 源码并触发 GitHub Actions"
    else:
        status = "succeeded"
        version_status = "current"
        version_source = "github-source-sync"
        version_description = "同步 Agent 源码"
    updated_at = _save_pipeline_state(
        state_file,
        state,
        pipeline_id=str(record["pipelineId"]),
        github_url=str(record.get("githubUrl") or f"https://github.com/{owner}/{repo}"),
        owner=owner,
        repo=repo,
        base_branch=base_branch,
        studio_branch=saved_branch,
        pull_request_url="",
        pull_request_number=0,
        runtime_id=runtime_id,
        region=str(record.get("region") or "cn-beijing"),
        cloud_provider=_normalize_delivery_cloud_provider(
            str(record.get("cloudProvider") or DEFAULT_CLOUD_PROVIDER)
        ),
        latest_commit_sha=latest_commit_sha,
        github_token=token,
        status=status,
        phase="ready",
        last_error=None,
    )
    saved = state[str(record["pipelineId"])]
    _append_version(
        saved,
        commit_sha=latest_commit_sha,
        branch=saved_branch,
        pull_request_url="",
        pull_request_number=0,
        author="Studio",
        status=version_status,
        source=version_source,
        description=version_description,
        created_at=updated_at,
    )
    _save_state(state_file, state)
    result = _state_to_response(saved)
    result["updatedAt"] = updated_at
    return result


def list_github_delivery_versions(
    *,
    runtime_id: str,
    github_client: Any | None = None,
    state_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return GitHub delivery versions recorded for a Runtime."""
    runtime_id = runtime_id.strip()
    if not runtime_id:
        raise GitHubCicdError("Runtime ID is required", phase="versions")
    state_file = Path(state_path) if state_path is not None else DEFAULT_STATE_PATH
    record = _find_state_by_runtime_id(_load_state(state_file), runtime_id)
    if record is None:
        return {
            "runtimeId": runtime_id,
            "currentCommitSha": "",
            "github": {},
            "versions": [],
        }
    owner = str(record.get("owner") or "")
    repo = str(record.get("repo") or "")
    base_branch = str(record.get("baseBranch") or "main")
    token = str(record.get("githubToken") or "").strip()
    github_error = ""
    github_versions: list[dict[str, Any]] = []
    if owner and repo and token:
        try:
            client = github_client or GitHubClient(token)
            commits = client.list_branch_commits(
                owner,
                repo,
                branch=base_branch,
                limit=30,
            )
            workflow_runs: list[dict[str, Any]] = []
            if bool(record.get("cicdEnabled")):
                workflow_path = str(record.get("workflowPath") or WORKFLOW_PATH)
                try:
                    workflow_runs = client.list_workflow_runs(
                        owner,
                        repo,
                        workflow_path=workflow_path,
                        branch=base_branch,
                        limit=100,
                    )
                except GitHubCicdError as error:
                    github_error = str(error)
            github_versions = _github_commits_to_versions(
                client=client,
                owner=owner,
                repo=repo,
                branch=base_branch,
                commits=commits,
                workflow_runs=workflow_runs,
                recorded_versions=_normalized_versions(record),
                rollback_events=_normalized_rollback_events(record),
            )
        except GitHubCicdError as error:
            github_error = str(error)

    versions = github_versions or _normalized_versions(record)
    current_commit_sha = _current_runtime_commit_sha(versions, record)
    versions = _mark_current_runtime_version(versions, current_commit_sha)
    response = {
        "runtimeId": runtime_id,
        "currentCommitSha": current_commit_sha,
        "runtimeStatus": "published" if current_commit_sha else "unknown",
        "latestSourceRuntimeStatus": (
            str(versions[0].get("runtimeStatus") or "unknown")
            if versions
            else "unknown"
        ),
        "github": _state_to_response(record)["github"],
        "cicd": _state_to_response(record)["cicd"],
        "versions": versions,
    }
    if github_error:
        response["githubSyncError"] = github_error
    return response


def create_github_delivery_rollback_pr(
    *,
    runtime_id: str,
    target_commit_sha: str,
    github_token: str = "",
    github_client: Any | None = None,
    state_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create a PR that rolls the target branch back to ``target_commit_sha``."""
    runtime_id = runtime_id.strip()
    target_commit_sha = target_commit_sha.strip()
    if not runtime_id:
        raise GitHubCicdError("Runtime ID is required", phase="rollback")
    if not target_commit_sha:
        raise GitHubCicdError("Target commit sha is required", phase="rollback")
    state_file = Path(state_path) if state_path is not None else DEFAULT_STATE_PATH
    state = _load_state(state_file)
    record = _find_state_by_runtime_id(state, runtime_id)
    if record is None:
        raise GitHubCicdError(
            f"Runtime is not bound to GitHub CI/CD: {runtime_id}",
            phase="rollback",
            runtime_id=runtime_id,
        )
    token = github_token.strip() or str(record.get("githubToken") or "").strip()
    if not token:
        raise GitHubCicdError(
            "GitHub token is required to create rollback PR",
            phase="github",
            runtime_id=runtime_id,
        )
    owner = str(record.get("owner") or "")
    repo = str(record.get("repo") or "")
    base_branch = str(record.get("baseBranch") or "main")
    if not owner or not repo:
        raise GitHubCicdError(
            "GitHub CI/CD binding is incomplete",
            phase="rollback",
            runtime_id=runtime_id,
        )

    client = github_client or GitHubClient(token)
    rollback_branch = f"studio/rollback-{_slug(target_commit_sha[:8])}"
    pr = client.create_rollback_pull_request(
        owner,
        repo,
        base_branch=base_branch,
        target_commit_sha=target_commit_sha,
        rollback_branch=rollback_branch,
        title=f"Rollback Agent Runtime to {target_commit_sha[:12]}",
        body=(
            "Studio generated this rollback PR. Merge it to restore the "
            "target branch to the selected Agent source version."
        ),
    )
    commit_sha = str(getattr(pr, "commit_sha", "") or target_commit_sha)
    created_at = datetime.now(UTC).isoformat()
    status = "rollback-pr-created"
    branch = rollback_branch
    version_status = "pending"
    runtime_status = "pending"
    if bool(record.get("cicdEnabled")):
        commit_sha = client.merge_pull_request(
            owner,
            repo,
            pull_request_number=int(pr.number),
            commit_title=f"Studio: rollback Agent Runtime to {target_commit_sha[:12]}",
        )
        status = "rollback-merged"
        branch = base_branch
        version_status = "merged"
        runtime_status = "publishing"
    record["pullRequestUrl"] = str(pr.url)
    record["pullRequestNumber"] = int(pr.number)
    record["latestCommitSha"] = commit_sha
    record["branch"] = branch
    record["status"] = status
    record["updatedAt"] = created_at
    if bool(record.get("cicdEnabled")):
        _append_rollback_event(
            record,
            commit_sha=commit_sha,
            target_commit_sha=target_commit_sha,
            branch=branch,
            pull_request_url=str(pr.url),
            pull_request_number=int(pr.number),
            author="Studio",
            status=version_status,
            runtime_status=runtime_status,
            description=f"回退到 {target_commit_sha[:12]}",
            created_at=created_at,
        )
    else:
        _append_version(
            record,
            commit_sha=commit_sha,
            branch=branch,
            pull_request_url=str(pr.url),
            pull_request_number=int(pr.number),
            author="Studio",
            status=version_status,
            source="rollback",
            description=f"回退到 {target_commit_sha[:12]}",
            created_at=created_at,
        )
    _save_state(state_file, state)
    return {
        "runtimeId": runtime_id,
        "status": status,
        "github": {
            "owner": owner,
            "repo": repo,
            "baseBranch": base_branch,
            "branch": branch,
            "commitSha": commit_sha,
            "pullRequestUrl": str(pr.url),
            "pullRequestNumber": int(pr.number),
        },
        "rollback": _normalized_rollback_events(record)[0],
    }


class GitHubClient:
    """Small GitHub REST client for branch, commit, and PR operations."""

    def __init__(self, token: str, *, session: requests.Session | None = None) -> None:
        self._token = token
        self._session = session or requests.Session()

    def ensure_repository_access(self, owner: str, repo: str) -> None:
        self._request("GET", f"/repos/{owner}/{repo}")

    def set_actions_secret(
        self,
        owner: str,
        repo: str,
        *,
        name: str,
        value: str,
    ) -> None:
        public_key = self._request(
            "GET",
            f"/repos/{owner}/{repo}/actions/secrets/public-key",
        )
        key_id = str(public_key.get("key_id") or "")
        key = str(public_key.get("key") or "")
        if not key_id or not key:
            raise GitHubCicdError(
                "GitHub Actions secret public key response is incomplete",
                phase="github",
            )
        self._request(
            "PUT",
            f"/repos/{owner}/{repo}/actions/secrets/{quote(name, safe='')}",
            json={
                "encrypted_value": _encrypt_github_actions_secret(value, key),
                "key_id": key_id,
            },
        )

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
        try:
            head_sha = self.get_branch_head(owner, repo, branch)
        except GitHubCicdError as error:
            if not _is_empty_repository_error(error):
                raise
            return self._commit_files_to_empty_branch(
                owner,
                repo,
                branch=branch,
                files=files,
                message=message,
            )
        head_commit = self._request(
            "GET",
            f"/repos/{owner}/{repo}/git/commits/{quote(head_sha, safe='')}",
        )
        base_tree = str(((head_commit.get("tree") or {}).get("sha")) or "")
        if not base_tree:
            raise GitHubCicdError("GitHub branch head commit has no tree")

        tree_entries = self._tree_entries_for_files(owner, repo, files=files)
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

    def _commit_files_to_empty_branch(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        files: list[dict[str, str]],
        message: str,
    ) -> str:
        tree = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/trees",
            json={"tree": self._tree_entries_for_files(owner, repo, files=files)},
        )
        commit = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/commits",
            json={"message": message, "tree": tree["sha"], "parents": []},
        )
        commit_sha = str(commit.get("sha") or "")
        if not commit_sha:
            raise GitHubCicdError("GitHub commit response did not include sha")
        self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": commit_sha},
        )
        return commit_sha

    def _tree_entries_for_files(
        self,
        owner: str,
        repo: str,
        *,
        files: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        tree_entries: list[dict[str, str]] = []
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
        return tree_entries

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

    def merge_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        pull_request_number: int,
        commit_title: str,
    ) -> str:
        if pull_request_number <= 0:
            raise GitHubCicdError(
                "GitHub pull request number is required", phase="github"
            )
        merged = self._request(
            "PUT",
            f"/repos/{owner}/{repo}/pulls/{pull_request_number}/merge",
            json={"commit_title": commit_title},
        )
        sha = str(merged.get("sha") or "")
        if not sha:
            raise GitHubCicdError("GitHub merge response did not include sha")
        return sha

    def list_branch_commits(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        commits = self._request(
            "GET",
            f"/repos/{owner}/{repo}/commits",
            params={"sha": branch, "per_page": max(1, min(limit, 100))},
        )
        return commits if isinstance(commits, list) else []

    def list_commit_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        commit_sha: str,
    ) -> list[SimpleNamespace]:
        pulls = self._request(
            "GET",
            f"/repos/{owner}/{repo}/commits/{quote(commit_sha, safe='')}/pulls",
        )
        if not isinstance(pulls, list):
            return []
        return [_pull_namespace(item) for item in pulls if isinstance(item, dict)]

    def list_workflow_runs(
        self,
        owner: str,
        repo: str,
        *,
        workflow_path: str,
        branch: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        data = self._request(
            "GET",
            (
                f"/repos/{owner}/{repo}/actions/workflows/"
                f"{quote(workflow_path, safe='')}/runs"
            ),
            params={"branch": branch, "per_page": max(1, min(limit, 100))},
        )
        runs = data.get("workflow_runs") if isinstance(data, dict) else None
        return runs if isinstance(runs, list) else []

    def create_rollback_pull_request(
        self,
        owner: str,
        repo: str,
        *,
        base_branch: str,
        target_commit_sha: str,
        rollback_branch: str,
        title: str,
        body: str,
    ) -> SimpleNamespace:
        base_sha = self.get_branch_head(owner, repo, base_branch)
        target_commit = self._request(
            "GET",
            f"/repos/{owner}/{repo}/git/commits/{quote(target_commit_sha, safe='')}",
        )
        target_tree = str(((target_commit.get("tree") or {}).get("sha")) or "")
        if not target_tree:
            raise GitHubCicdError("Target GitHub commit has no tree", phase="github")
        self.ensure_branch(
            owner,
            repo,
            branch=rollback_branch,
            source_sha=base_sha,
        )
        commit = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/commits",
            json={
                "message": f"Studio: rollback Agent to {target_commit_sha[:12]}",
                "tree": target_tree,
                "parents": [base_sha],
            },
        )
        rollback_sha = str(commit.get("sha") or "")
        if not rollback_sha:
            raise GitHubCicdError("GitHub rollback commit response did not include sha")
        self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/git/refs/heads/{quote(rollback_branch, safe='')}",
            json={"sha": rollback_sha, "force": True},
        )
        pr = self.ensure_pull_request(
            owner,
            repo,
            head_branch=rollback_branch,
            base_branch=base_branch,
            title=title,
            body=body,
        )
        pr.commit_sha = rollback_sha
        return pr

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


def _sync_github_pr(
    *,
    client: Any,
    owner: str,
    repo: str,
    project: dict[str, Any],
    base_branch: str,
    studio_branch: str,
    progress: ProgressCallback | None,
) -> dict[str, Any]:
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
            "Studio generated this Agent project. The bound AgentKit Runtime "
            "is updated through Studio deployment."
        ),
    )
    return {
        "owner": owner,
        "repo": repo,
        "baseBranch": base_branch,
        "branch": studio_branch,
        "commitSha": commit_sha,
        "pullRequestUrl": pr.url,
        "pullRequestNumber": pr.number,
    }


def _push_github_source(
    *,
    client: Any,
    owner: str,
    repo: str,
    project: dict[str, Any],
    branch: str,
    progress: ProgressCallback | None,
) -> dict[str, Any]:
    client.ensure_repository_access(owner, repo)
    _emit(progress, f"Pushing {len(project['files'])} file(s) to {branch}...")
    commit_sha = client.commit_files(
        owner,
        repo,
        branch=branch,
        files=project["files"],
        message=f"Studio: sync {project['name']} Agent source",
    )
    return {
        "owner": owner,
        "repo": repo,
        "baseBranch": branch,
        "branch": branch,
        "commitSha": commit_sha,
        "pullRequestUrl": "",
        "pullRequestNumber": 0,
    }


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _pull_namespace(data: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        number=int(data.get("number") or 0),
        url=str(data.get("html_url") or data.get("url") or ""),
    )


def _is_empty_repository_error(error: GitHubCicdError) -> bool:
    message = str(error)
    return "409" in message and "Git Repository is empty" in message


def _validate_project_path(value: str) -> str:
    candidate = (value or ".").strip() or "."
    if candidate.startswith("/") or "\x00" in candidate:
        raise GitHubCicdError("Project path must be a repository-relative path")
    parts = Path(candidate).parts
    if any(part in ("", "..") for part in parts):
        raise GitHubCicdError("Project path must be a safe repository-relative path")
    return "." if candidate == "." else candidate.rstrip("/")


def _normalize_delivery_cloud_provider(value: str | None) -> CloudProvider:
    try:
        return normalize_cloud_provider(value)
    except ValueError as error:
        raise GitHubCicdError(str(error), phase="cicd") from error


def _credential_secret_names(cloud_provider: CloudProvider) -> tuple[str, str, str]:
    if cloud_provider == "byteplus":
        return (
            "BYTEPLUS_ACCESS_KEY",
            "BYTEPLUS_SECRET_KEY",
            "BYTEPLUS_SESSION_TOKEN",
        )
    return (
        "VOLCENGINE_ACCESS_KEY",
        "VOLCENGINE_SECRET_KEY",
        "VOLCENGINE_SESSION_TOKEN",
    )


def _cloud_provider_display_name(cloud_provider: CloudProvider) -> str:
    return "BytePlus" if cloud_provider == "byteplus" else "Volcengine"


def _runtime_delivery_secrets(
    *,
    access_key: str,
    secret_key: str,
    session_token: str,
    cloud_provider: CloudProvider,
) -> dict[str, str]:
    access_key = access_key.strip()
    secret_key = secret_key.strip()
    session_token = session_token.strip()
    provider_name = _cloud_provider_display_name(cloud_provider)
    if not access_key:
        raise GitHubCicdError(
            f"{provider_name} access key is required for GitHub Runtime delivery",
            phase="cicd",
        )
    if not secret_key:
        raise GitHubCicdError(
            f"{provider_name} secret key is required for GitHub Runtime delivery",
            phase="cicd",
        )
    access_key_name, secret_key_name, session_token_name = _credential_secret_names(
        cloud_provider
    )
    secrets = {
        access_key_name: access_key,
        secret_key_name: secret_key,
    }
    if session_token:
        secrets[session_token_name] = session_token
    return secrets


def _configure_runtime_delivery_secrets(
    client: Any,
    owner: str,
    repo: str,
    *,
    access_key: str,
    secret_key: str,
    session_token: str,
    cloud_provider: CloudProvider,
    progress: ProgressCallback | None,
) -> None:
    secrets = _runtime_delivery_secrets(
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        cloud_provider=cloud_provider,
    )
    _emit(progress, "Writing GitHub Actions secrets...")
    for name, value in secrets.items():
        client.set_actions_secret(owner, repo, name=name, value=value)


def _encrypt_github_actions_secret(value: str, public_key: str) -> str:
    try:
        from nacl import encoding, public
    except ImportError as error:
        raise GitHubCicdError(
            "PyNaCl is required to write GitHub Actions secrets. "
            'Install it with `pip install "veadk-python[github-cicd]"`.',
            phase="github",
        ) from error

    sealed_box = public.SealedBox(
        public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder()),
    )
    encrypted = sealed_box.encrypt(value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def _agentkit_runtime_workflow(
    *,
    base_branch: str,
    project_path: str,
    runtime_name: str,
    runtime_id: str,
    region: str,
    cloud_provider: CloudProvider,
) -> str:
    access_key_secret, secret_key_secret, session_token_secret = (
        _credential_secret_names(cloud_provider)
    )
    byteplus_env = ""
    byteplus_runtime_env = ""
    if cloud_provider == "byteplus":
        byteplus_env = f"""
      VOLCENGINE_ACCESS_KEY: ${{{{ secrets.{access_key_secret} }}}}
      VOLCENGINE_SECRET_KEY: ${{{{ secrets.{secret_key_secret} }}}}
      VOLCENGINE_SESSION_TOKEN: ${{{{ secrets.{session_token_secret} }}}}
      BYTEPLUS_REGION: {json.dumps(region)}"""
        byteplus_runtime_env = f"""
                          "DATABASE_VIKING_REGION": {json.dumps(DEFAULT_BYTEPLUS_VIKING_MEMORY_REGION)},"""
    return f"""name: Publish to AgentKit Runtime

on:
  push:
    branches:
      - {json.dumps(base_branch)}
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: {json.dumps(f"agentkit-runtime-{runtime_id}")}
  cancel-in-progress: true

jobs:
  publish:
    if: ${{{{ github.event_name != 'push' || !contains(github.event.head_commit.message, '[skip runtime]') }}}}
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: {json.dumps(project_path)}
    env:
      AGENTKIT_CLOUD_PROVIDER: {json.dumps(cloud_provider)}
      CLOUD_PROVIDER: {json.dumps(cloud_provider)}
      {access_key_secret}: ${{{{ secrets.{access_key_secret} }}}}
      {secret_key_secret}: ${{{{ secrets.{secret_key_secret} }}}}
      {session_token_secret}: ${{{{ secrets.{session_token_secret} }}}}{byteplus_env}
      AGENTKIT_RUNTIME_NAME: {json.dumps(runtime_name)}
      AGENTKIT_RUNTIME_ID: {json.dumps(runtime_id)}
      AGENTKIT_REGION: {json.dumps(region)}
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

          credential_prefix = (
              "BYTEPLUS"
              if os.environ["AGENTKIT_CLOUD_PROVIDER"] == "byteplus"
              else "VOLCENGINE"
          )
          runtime_client = AgentkitRuntimeClient(
              access_key=os.environ[f"{{credential_prefix}}_ACCESS_KEY"],
              secret_key=os.environ[f"{{credential_prefix}}_SECRET_KEY"],
              session_token=os.environ.get(f"{{credential_prefix}}_SESSION_TOKEN", ""),
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

          config = {{
              "common": {{
                  "agent_name": runtime_name,
                  "entry_point": "app.py",
                  "description": "Continuously published from GitHub",
                  "python_version": "3.12",
                  "launch_type": "cloud",
              }},
              "launch_types": {{
                  "cloud": {{
                      "region": os.environ["AGENTKIT_REGION"],
                      "project_name": "default",
                      "image_tag": f"veadk-v{{next_version}}",
                      "runtime_id": os.environ["AGENTKIT_RUNTIME_ID"],
                      "runtime_name": runtime_name,
                      "runtime_role_name": runtime_role_name,
                      "python_version": "3.12",
                      "runtime_envs": {{
                          "CLOUD_PROVIDER": os.environ["CLOUD_PROVIDER"],
                          "AGENTKIT_CLOUD_PROVIDER": os.environ["AGENTKIT_CLOUD_PROVIDER"],{byteplus_runtime_env}
                      }},
                  }}
              }},
          }}
          config_path = Path("agentkit.yaml")
          config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
          result = sdk.launch(
              config_file=str(config_path),
              preflight_mode=PreflightMode.WARN,
          )
          if not result.success:
              raise SystemExit(f"AgentKit publish failed: {{result.error}}")
          PY
"""


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
    pull_request_number: int,
    runtime_id: str,
    region: str,
    cloud_provider: CloudProvider,
    latest_commit_sha: str,
    github_token: str,
    status: str,
    phase: str,
    last_error: dict[str, Any] | None,
) -> str:
    updated_at = datetime.now(UTC).isoformat()
    previous = state.get(pipeline_id)
    previous_record = previous if isinstance(previous, dict) else {}
    next_record: dict[str, Any] = {
        "pipelineId": pipeline_id,
        "githubUrl": github_url,
        "owner": owner,
        "repo": repo,
        "baseBranch": base_branch,
        "branch": studio_branch,
        "pullRequestUrl": pull_request_url,
        "pullRequestNumber": pull_request_number,
        "runtimeId": runtime_id,
        "region": region,
        "cloudProvider": cloud_provider,
        "latestCommitSha": latest_commit_sha,
        "githubToken": github_token,
        "status": status,
        "phase": phase,
        "updatedAt": updated_at,
    }
    for key in (
        "cicdEnabled",
        "workflowPath",
        "projectPath",
        "versions",
        "rollbackEvents",
    ):
        if key in previous_record:
            next_record[key] = previous_record[key]
    if last_error is not None:
        next_record["lastError"] = last_error
    state[pipeline_id] = next_record
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


def _find_state_by_runtime_id(
    state: dict[str, Any],
    runtime_id: str,
) -> dict[str, Any] | None:
    for record in state.values():
        if (
            isinstance(record, dict)
            and str(record.get("runtimeId") or "") == runtime_id
        ):
            return record
    return None


def _state_to_response(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "pipelineId": str(record.get("pipelineId") or ""),
        "status": str(record.get("status") or ""),
        "phase": str(record.get("phase") or ""),
        "updatedAt": str(record.get("updatedAt") or ""),
        "runtimeId": str(record.get("runtimeId") or ""),
        "region": str(record.get("region") or ""),
        "cloudProvider": str(record.get("cloudProvider") or DEFAULT_CLOUD_PROVIDER),
        "github": {
            "owner": str(record.get("owner") or ""),
            "repo": str(record.get("repo") or ""),
            "baseBranch": str(record.get("baseBranch") or ""),
            "branch": str(record.get("branch") or ""),
            "commitSha": str(record.get("latestCommitSha") or ""),
            "pullRequestUrl": str(record.get("pullRequestUrl") or ""),
            "pullRequestNumber": int(record.get("pullRequestNumber") or 0),
        },
        "cicd": {
            "enabled": bool(record.get("cicdEnabled")),
            "workflowPath": str(record.get("workflowPath") or ""),
            "projectPath": str(record.get("projectPath") or ""),
        },
    }


def _append_version(
    record: dict[str, Any],
    *,
    commit_sha: str,
    branch: str,
    pull_request_url: str,
    pull_request_number: int,
    author: str,
    status: str,
    source: str,
    description: str,
    created_at: str,
) -> None:
    versions = record.get("versions")
    if not isinstance(versions, list):
        versions = []
    next_version = {
        "version": f"v{len(versions) + 1}",
        "createdAt": created_at,
        "source": source,
        "description": description,
        "commitSha": commit_sha,
        "branch": branch,
        "pullRequestUrl": pull_request_url,
        "pullRequestNumber": pull_request_number,
        "author": author,
        "status": status,
    }
    record["versions"] = [next_version, *versions]


def _append_rollback_event(
    record: dict[str, Any],
    *,
    commit_sha: str,
    target_commit_sha: str,
    branch: str,
    pull_request_url: str,
    pull_request_number: int,
    author: str,
    status: str,
    runtime_status: str,
    description: str,
    created_at: str,
) -> None:
    events = record.get("rollbackEvents")
    if not isinstance(events, list):
        events = []
    next_event = {
        "version": "回退事件",
        "createdAt": created_at,
        "source": "rollback",
        "changeType": "rollback",
        "description": description,
        "commitSha": commit_sha,
        "targetCommitSha": target_commit_sha,
        "rollbackTargetCommitSha": target_commit_sha,
        "branch": branch,
        "pullRequestUrl": pull_request_url,
        "pullRequestNumber": pull_request_number,
        "author": author,
        "status": status,
        "runtimeStatus": runtime_status,
    }
    record["rollbackEvents"] = [next_event, *events]


def _normalized_versions(record: dict[str, Any]) -> list[dict[str, Any]]:
    versions = record.get("versions")
    if not isinstance(versions, list) or not versions:
        commit_sha = str(record.get("latestCommitSha") or "")
        if not commit_sha:
            return []
        versions = [
            {
                "version": "v1",
                "createdAt": str(record.get("updatedAt") or ""),
                "source": "studio",
                "description": "Studio 更新",
                "commitSha": commit_sha,
                "branch": str(record.get("branch") or ""),
                "pullRequestUrl": str(record.get("pullRequestUrl") or ""),
                "pullRequestNumber": int(record.get("pullRequestNumber") or 0),
                "author": "Studio",
                "status": "current",
                "runtimeStatus": "published",
                "changeType": "source",
            }
        ]
    normalized: list[dict[str, Any]] = []
    current_commit = str(record.get("latestCommitSha") or "")
    for index, item in enumerate(versions):
        if not isinstance(item, dict):
            continue
        commit_sha = str(item.get("commitSha") or "")
        normalized.append(
            {
                "version": str(item.get("version") or f"v{len(versions) - index}"),
                "createdAt": str(item.get("createdAt") or ""),
                "source": str(item.get("source") or "studio"),
                "description": str(item.get("description") or ""),
                "commitSha": commit_sha,
                "branch": str(item.get("branch") or ""),
                "pullRequestUrl": str(item.get("pullRequestUrl") or ""),
                "pullRequestNumber": int(item.get("pullRequestNumber") or 0),
                "author": str(item.get("author") or "Studio"),
                "runtimeStatus": str(item.get("runtimeStatus") or "published"),
                "changeType": str(item.get("changeType") or "source"),
                "status": str(
                    item.get("status")
                    or ("current" if commit_sha == current_commit else "pending")
                ),
            }
        )
    return normalized


def _normalized_rollback_events(record: dict[str, Any]) -> list[dict[str, Any]]:
    events = record.get("rollbackEvents")
    if not isinstance(events, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "version": str(item.get("version") or "回退事件"),
                "createdAt": str(item.get("createdAt") or ""),
                "source": "rollback",
                "changeType": "rollback",
                "description": str(item.get("description") or "回退版本"),
                "commitSha": str(item.get("commitSha") or ""),
                "targetCommitSha": str(
                    item.get("targetCommitSha")
                    or item.get("rollbackTargetCommitSha")
                    or ""
                ),
                "rollbackTargetCommitSha": str(
                    item.get("rollbackTargetCommitSha")
                    or item.get("targetCommitSha")
                    or ""
                ),
                "branch": str(item.get("branch") or ""),
                "pullRequestUrl": str(item.get("pullRequestUrl") or ""),
                "pullRequestNumber": int(item.get("pullRequestNumber") or 0),
                "author": str(item.get("author") or "Studio"),
                "runtimeStatus": str(item.get("runtimeStatus") or "publishing"),
                "status": str(item.get("status") or "merged"),
            }
        )
    return normalized


def _github_commits_to_versions(
    *,
    client: Any,
    owner: str,
    repo: str,
    branch: str,
    commits: list[dict[str, Any]],
    workflow_runs: list[dict[str, Any]],
    recorded_versions: list[dict[str, Any]],
    rollback_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    workflow_runs_by_sha = _workflow_runs_by_head_sha(workflow_runs)
    recorded_by_sha = {
        str(item.get("commitSha") or ""): item
        for item in recorded_versions
        if str(item.get("commitSha") or "")
    }
    rollback_by_sha = {
        str(item.get("commitSha") or ""): item
        for item in rollback_events
        if str(item.get("commitSha") or "")
    }
    non_rollback_total = sum(
        1
        for item in commits
        if isinstance(item, dict)
        and str(item.get("sha") or "")
        and str(item.get("sha") or "") not in rollback_by_sha
    )
    non_rollback_index = 0
    versions: list[dict[str, Any]] = []
    for item in commits:
        if not isinstance(item, dict):
            continue
        commit_sha = str(item.get("sha") or "")
        if not commit_sha:
            continue
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        message = str(commit.get("message") or "").splitlines()[0].strip()
        author_info = (
            commit.get("author") if isinstance(commit.get("author"), dict) else {}
        )
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        pull_request_url = ""
        pull_request_number = 0
        try:
            pulls = client.list_commit_pull_requests(
                owner,
                repo,
                commit_sha=commit_sha,
            )
        except GitHubCicdError:
            pulls = []
        if pulls:
            pull_request_url = str(getattr(pulls[0], "url", "") or "")
            pull_request_number = int(getattr(pulls[0], "number", 0) or 0)
        run = workflow_runs_by_sha.get(commit_sha)
        rollback_event = rollback_by_sha.get(commit_sha)
        recorded = recorded_by_sha.get(commit_sha, {})
        runtime_status = _runtime_status_for_commit(
            run=run,
            recorded_version=recorded,
            rollback_event=rollback_event,
        )
        workflow_run_url = str((run or {}).get("html_url") or "")
        if rollback_event:
            versions.append(
                {
                    **rollback_event,
                    "createdAt": str(
                        author_info.get("date") or rollback_event.get("createdAt") or ""
                    ),
                    "description": str(rollback_event.get("description") or message),
                    "commitSha": commit_sha,
                    "branch": branch,
                    "pullRequestUrl": pull_request_url
                    or str(rollback_event.get("pullRequestUrl") or ""),
                    "pullRequestNumber": pull_request_number
                    or int(rollback_event.get("pullRequestNumber") or 0),
                    "author": str(
                        author.get("login")
                        or author_info.get("name")
                        or rollback_event.get("author")
                        or "GitHub"
                    ),
                    "runtimeStatus": runtime_status,
                    "workflowRunUrl": workflow_run_url,
                }
            )
            continue
        non_rollback_index += 1
        versions.append(
            {
                "version": f"v{non_rollback_total - non_rollback_index + 1}",
                "createdAt": str(author_info.get("date") or ""),
                "source": "github-main",
                "changeType": "source",
                "description": message,
                "commitSha": commit_sha,
                "branch": branch,
                "pullRequestUrl": pull_request_url,
                "pullRequestNumber": pull_request_number,
                "author": str(
                    author.get("login") or author_info.get("name") or "GitHub"
                ),
                "runtimeStatus": runtime_status,
                "workflowRunUrl": workflow_run_url,
                "status": runtime_status,
            }
        )
    return versions


def _workflow_runs_by_head_sha(
    workflow_runs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    runs_by_sha: dict[str, dict[str, Any]] = {}
    for run in workflow_runs:
        if not isinstance(run, dict):
            continue
        sha = str(run.get("head_sha") or "")
        if sha and sha not in runs_by_sha:
            runs_by_sha[sha] = run
    return runs_by_sha


def _runtime_status_for_commit(
    *,
    run: dict[str, Any] | None,
    recorded_version: dict[str, Any],
    rollback_event: dict[str, Any] | None,
) -> str:
    if run:
        status = str(run.get("status") or "")
        conclusion = str(run.get("conclusion") or "")
        if status == "completed":
            return "published" if conclusion == "success" else "failed"
        return "publishing"
    recorded_runtime_status = str(recorded_version.get("runtimeStatus") or "")
    if recorded_runtime_status:
        return recorded_runtime_status
    if str(recorded_version.get("status") or "") == "current":
        return "published"
    if rollback_event:
        return str(rollback_event.get("runtimeStatus") or "publishing")
    return "unknown"


def _current_runtime_commit_sha(
    versions: list[dict[str, Any]],
    record: dict[str, Any],
) -> str:
    for item in versions:
        if str(item.get("runtimeStatus") or "") != "published":
            continue
        if str(item.get("changeType") or "") == "rollback":
            target = str(item.get("rollbackTargetCommitSha") or "")
            if target:
                return target
        commit_sha = str(item.get("commitSha") or "")
        if commit_sha:
            return commit_sha
    for item in _normalized_versions(record):
        if str(item.get("status") or "") == "current":
            return str(item.get("commitSha") or "")
    return ""


def _mark_current_runtime_version(
    versions: list[dict[str, Any]],
    current_commit_sha: str,
) -> list[dict[str, Any]]:
    marked: list[dict[str, Any]] = []
    for item in versions:
        next_item = dict(item)
        runtime_status = str(next_item.get("runtimeStatus") or "unknown")
        commit_sha = str(next_item.get("commitSha") or "")
        rollback_target = str(next_item.get("rollbackTargetCommitSha") or "")
        if commit_sha == current_commit_sha or rollback_target == current_commit_sha:
            next_item["status"] = "current"
        elif runtime_status == "publishing":
            next_item["status"] = "publishing"
        elif runtime_status == "failed":
            next_item["status"] = "failed"
        else:
            next_item["status"] = "historical"
        marked.append(next_item)
    return marked


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _redact(text: str, *secrets: str) -> str:
    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, "***")
    return result
