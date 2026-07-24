"""Validated configuration and API models for Studio releases."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

ReleaseState = Literal["queued", "running", "succeeded", "failed"]


@dataclass(frozen=True)
class ReleaseServerSettings:
    """Runtime settings injected into the VeFaaS Function."""

    api_key: str
    bucket: str
    region: str
    release_prefix: str
    job_prefix: str
    repository: str

    def __post_init__(self) -> None:
        if len(self.api_key) < 32:
            raise ValueError("STUDIO_RELEASE_SERVER_API_KEY must be at least 32 chars.")
        if not self.bucket:
            raise ValueError("STUDIO_RELEASE_BUCKET is required.")
        if not self.region:
            raise ValueError("STUDIO_RELEASE_REGION is required.")
        for value, name in (
            (self.release_prefix, "STUDIO_RELEASE_PREFIX"),
            (self.job_prefix, "STUDIO_RELEASE_JOB_PREFIX"),
        ):
            normalized = value.strip().strip("/")
            if not normalized or any(
                part in {"", ".", ".."} for part in normalized.split("/")
            ):
                raise ValueError(f"{name} is invalid.")
        if not _REPOSITORY_PATTERN.fullmatch(self.repository):
            raise ValueError("STUDIO_RELEASE_REPOSITORY is invalid.")

    @classmethod
    def from_env(cls) -> ReleaseServerSettings:
        """Load the fail-closed production configuration."""
        return cls(
            api_key=os.getenv("STUDIO_RELEASE_SERVER_API_KEY", "").strip(),
            bucket=os.getenv("STUDIO_RELEASE_BUCKET", "").strip(),
            region=os.getenv("STUDIO_RELEASE_REGION", "cn-beijing").strip(),
            release_prefix=os.getenv(
                "STUDIO_RELEASE_PREFIX", "veadk/studio/main"
            ).strip(),
            job_prefix=os.getenv(
                "STUDIO_RELEASE_JOB_PREFIX", "veadk/studio/release-server/jobs"
            ).strip(),
            repository=os.getenv(
                "STUDIO_RELEASE_REPOSITORY", "volcengine/veadk-python"
            ).strip(),
        )


class ReleaseRequest(BaseModel):
    """Request one immutable release from an exact Git commit."""

    model_config = ConfigDict(populate_by_name=True)

    repository: str
    git_sha: str = Field(alias="gitSha")
    request_id: str = Field(alias="requestId")
    changelog: tuple[str, ...] = ()

    @field_validator("repository")
    @classmethod
    def _validate_repository(cls, value: str) -> str:
        value = value.strip()
        if not _REPOSITORY_PATTERN.fullmatch(value):
            raise ValueError("repository must use owner/name format")
        return value

    @field_validator("git_sha")
    @classmethod
    def _validate_git_sha(cls, value: str) -> str:
        value = value.strip().lower()
        if not _GIT_SHA_PATTERN.fullmatch(value):
            raise ValueError("gitSha must be a 40-digit lowercase SHA")
        return value

    @field_validator("request_id")
    @classmethod
    def _validate_request_id(cls, value: str) -> str:
        value = value.strip()
        if not _JOB_ID_PATTERN.fullmatch(value):
            raise ValueError("requestId contains unsupported characters")
        return value

    @field_validator("changelog")
    @classmethod
    def _validate_changelog(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(item.strip() for item in value)
        if len(cleaned) > 50 or any(not item or len(item) > 240 for item in cleaned):
            raise ValueError("changelog is invalid")
        return cleaned


class BuildResult(BaseModel):
    """Result returned after TOS publication and verification."""

    model_config = ConfigDict(populate_by_name=True)

    version: str
    git_sha: str = Field(alias="gitSha")
    sha256: str
    size: int
    created_at: str = Field(alias="createdAt")
    timings: dict[str, float]


class ReleaseStatus(BaseModel):
    """Durable release state stored in TOS."""

    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(alias="jobId")
    state: ReleaseState
    repository: str
    git_sha: str = Field(alias="gitSha")
    changelog: tuple[str, ...] = ()
    stage: str
    message: str
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    started_at: str | None = Field(default=None, alias="startedAt")
    completed_at: str | None = Field(default=None, alias="completedAt")
    result: BuildResult | None = None
    error: str = ""

    def public_dict(self) -> dict[str, object]:
        """Serialize field aliases for HTTP and TOS."""
        return self.model_dump(by_alias=True, mode="json")
