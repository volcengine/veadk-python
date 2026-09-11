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

"""Private JSON score jobs with conditional writes in the Skill archive bucket."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .scoring_model import SkillAssessmentReport

_MAX_SCORE_BYTES = 512 * 1024


class ScoreJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["queued", "running", "completed", "failed"] = "queued"
    attempts: int = Field(default=0, ge=0)
    leaseUntil: float = 0
    result: SkillAssessmentReport | None = None
    error: str = ""

    def public(self) -> dict[str, Any]:
        result: dict[str, Any] = {"status": self.status}
        if self.error:
            result["error"] = self.error
        if self.result is not None:
            result.update(
                overallScore=self.result.overallScore,
                scoredAt=self.result.scoredAt,
                modelName=self.result.modelName,
                rubricVersion=self.result.rubricVersion,
                result=self.result.model_dump(),
            )
        return result


class ScoreConflict(Exception):
    """Another process owns or has updated this job."""


class TosScoreStore:
    def __init__(self) -> None:
        self._bound_location: tuple[str, str, str] | None = None

    def for_location(self, bucket: str, key: str, application_id: str) -> TosScoreStore:
        """Bind a validated persisted location without changing the default store."""
        self._key("", application_id)
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket):
            raise ValueError("Invalid score storage bucket")
        parts = key.split("/")
        if (
            not key
            or len(key.encode("utf-8")) > 1024
            or "\\" in key
            or re.match(r"^[A-Za-z]:", key)
            or any(ord(character) < 32 or ord(character) == 127 for character in key)
            or any(part in {"", ".", ".."} for part in parts)
            or parts[-2:] != ["review-scores", f"{application_id}.json"]
        ):
            raise ValueError("Invalid score storage key for review application")
        bound = TosScoreStore()
        bound._bound_location = (bucket, key, application_id)
        return bound

    def _storage(self, region: str) -> tuple[Any, Any]:
        from agentkit.toolkit.config import GlobalConfigManager
        from .storage import (
            resolve_skill_publish_storage,
            resolve_skill_publish_credentials,
        )

        config = GlobalConfigManager().load()
        storage = resolve_skill_publish_storage(
            region=region,
            config_bucket=config.tos.bucket or "",
            config_prefix=config.tos.prefix or "",
        )
        if self._bound_location is not None:
            storage = replace(storage, bucket=self._bound_location[0])
        credentials = resolve_skill_publish_credentials(provider=storage.provider)
        return storage, credentials

    @staticmethod
    def _key(prefix: str, application_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", application_id):
            raise ValueError("Invalid review application ID")
        return "/".join(
            filter(None, (prefix.strip("/"), "review-scores", f"{application_id}.json"))
        )

    def _object_key(self, prefix: str, application_id: str) -> str:
        if self._bound_location is not None:
            if application_id != self._bound_location[2]:
                raise ValueError(
                    "Score storage location belongs to another application"
                )
            return self._bound_location[1]
        return self._key(prefix, application_id)

    @staticmethod
    def _validate_application(job: ScoreJob, application_id: str) -> None:
        if job.result is not None and job.result.applicationId != application_id:
            raise ValueError("Score report belongs to another review application")

    def location(self, region: str, application_id: str) -> tuple[str, str]:
        storage, _ = self._storage(region)
        return storage.bucket, self._object_key(storage.prefix, application_id)

    def read(self, region: str, application_id: str) -> tuple[ScoreJob | None, str]:
        from tos.exceptions import TosServerError

        from .storage import _create_tos_client

        storage, credentials = self._storage(region)
        client = _create_tos_client(storage, credentials)
        try:
            response = client.get_object(
                storage.bucket, self._object_key(storage.prefix, application_id)
            )
        except TosServerError as error:
            if error.status_code == 404 and error.code == "NoSuchKey":
                return None, ""
            raise
        try:
            if not response.etag:
                raise ValueError("Score storage did not return an ETag")
            if (
                response.content_length is not None
                and response.content_length > _MAX_SCORE_BYTES
            ):
                raise ValueError("Score report is too large")
            content = bytearray()
            while True:
                chunk = response.read(_MAX_SCORE_BYTES + 1 - len(content))
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > _MAX_SCORE_BYTES:
                    raise ValueError("Score report is too large")
            job = ScoreJob.model_validate_json(content)
            self._validate_application(job, application_id)
            return job, response.etag
        finally:
            # GetObjectOutput has no close method; its HTTP response owns the stream
            response.resp.resp.close()

    def write(
        self, region: str, application_id: str, job: ScoreJob, etag: str = ""
    ) -> str:
        from tos.enum import ACLType
        from tos.exceptions import TosServerError

        from .storage import _create_tos_client

        storage, credentials = self._storage(region)
        self._validate_application(job, application_id)
        content = job.model_dump_json().encode()
        if len(content) > _MAX_SCORE_BYTES:
            raise ValueError("Score report is too large")
        client = _create_tos_client(storage, credentials)
        try:
            response = client.put_object(
                storage.bucket,
                self._object_key(storage.prefix, application_id),
                content=content,
                acl=ACLType.ACL_Private,
                content_type="application/json; charset=utf-8",
                cache_control="no-store",
                **({"if_match": etag} if etag else {"forbid_overwrite": True}),
            )
        except TosServerError as error:
            if error.status_code in {409, 412}:
                raise ScoreConflict() from error
            raise
        if not response.etag:
            raise ValueError("Score storage did not return an ETag")
        return response.etag
