"""Shared contracts and boundary validation for GitHub automations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse

from pydantic import BaseModel, Field

_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_PROJECT_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_RUNTIME_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_RUNTIME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SANDBOX_TOOL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
REGIONS = {"cn-beijing", "cn-shanghai"}


class AutomationValidationError(RuntimeError):
    """A sanitized validation error suitable for browser display."""


class RepositoryPullRequestBody(BaseModel):
    repository: str = Field(min_length=1, max_length=240)
    base_branch: str = Field(default="main", alias="baseBranch", max_length=200)
    token: str = Field(min_length=1, max_length=512)

    model_config = {"populate_by_name": True}


class RuntimePullRequestBody(RepositoryPullRequestBody):
    project_path: str = Field(default=".", alias="projectPath", max_length=240)
    runtime_name: str = Field(alias="runtimeName", min_length=1, max_length=64)
    runtime_id: str = Field(alias="runtimeId", min_length=1, max_length=128)
    region: str = Field(default="cn-beijing", max_length=32)


@dataclass(frozen=True)
class PullRequestFile:
    path: str
    content: str
    commit_message: str
    must_be_new: bool = False


@dataclass(frozen=True)
class AutomationPullRequest:
    repository: str
    files: tuple[PullRequestFile, ...]
    branch_prefix: str
    title: str
    description: str


def repository_slug(value: str) -> str:
    candidate = value.strip().removesuffix(".git").strip("/")
    if candidate.startswith("git@github.com:"):
        candidate = candidate.removeprefix("git@github.com:")
    elif "://" in candidate:
        parsed = urlparse(candidate)
        if parsed.hostname not in {"github.com", "www.github.com"}:
            raise AutomationValidationError("仅支持 github.com 仓库")
        candidate = parsed.path.strip("/").removesuffix(".git")
    if not _REPOSITORY_RE.fullmatch(candidate):
        raise AutomationValidationError("GitHub Repo 格式应为 owner/repository")
    return candidate


def project_path(value: str) -> str:
    candidate = value.strip() or "."
    path = PurePosixPath(candidate)
    if (
        candidate.startswith("/")
        or not _PROJECT_PATH_RE.fullmatch(candidate)
        or ".." in path.parts
    ):
        raise AutomationValidationError("Agent 项目目录必须是仓库内的安全相对路径")
    return candidate.rstrip("/") or "."


def validate_repository(body: RepositoryPullRequestBody) -> str:
    repository = repository_slug(body.repository)
    if not _BRANCH_RE.fullmatch(body.base_branch) or ".." in body.base_branch:
        raise AutomationValidationError("目标分支格式不正确")
    return repository


def validate_runtime(body: RuntimePullRequestBody) -> tuple[str, str]:
    repository = validate_repository(body)
    normalized_project_path = project_path(body.project_path)
    if not _RUNTIME_NAME_RE.fullmatch(body.runtime_name):
        raise AutomationValidationError(
            "Runtime 名称需以字母开头，且只能包含字母、数字、下划线和连字符"
        )
    if not _RUNTIME_ID_RE.fullmatch(body.runtime_id):
        raise AutomationValidationError("Runtime ID 格式不正确")
    validate_region(body.region)
    return repository, normalized_project_path


def validate_sandbox_tool_id(value: str) -> None:
    if not _SANDBOX_TOOL_ID_RE.fullmatch(value):
        raise AutomationValidationError("Sandbox Tool ID 格式不正确")


def validate_model_name(value: str) -> None:
    if not _MODEL_NAME_RE.fullmatch(value):
        raise AutomationValidationError("模型名称格式不正确")


def validate_model_base_url(value: str) -> None:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise AutomationValidationError("模型 API 地址必须是安全的 HTTPS URL")


def validate_region(value: str) -> None:
    if value not in REGIONS:
        raise AutomationValidationError("暂仅支持北京或上海地域")


def join_repo_path(directory: str, path: str) -> str:
    return path if directory == "." else f"{directory}/{path}"


def workflow_path(prefix: str, project_path_value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", project_path_value).strip("-").lower()
    return f".github/workflows/{prefix}-{slug or 'root'}.yml"


def branch_is_valid(value: str) -> bool:
    return bool(_BRANCH_RE.fullmatch(value))
