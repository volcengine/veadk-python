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

"""Recover and assess queued review snapshots without blocking submission."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from veadk.utils.logger import get_logger

from .consts import (
    SCORE_STATUS_TAG,
    SCORE_TOTAL_TAG,
    SCORE_TIME_TAG,
    SCORE_MODEL_TAG,
    SCORE_RUBRIC_TAG,
    SCORE_BUCKET_TAG,
    SCORE_KEY_TAG,
    REVIEW_SPACE,
)
from .models import SkillIdentity
from .errors import skill_error_text
from .repository import AgentKitSkillRepository, SkillRepositoryError
from .score_store import ScoreConflict, ScoreJob, TosScoreStore
from .scoring_model import SkillAssessmentReport, score_skill_snapshot
from .tags import update_skill_tags

logger = get_logger(__name__)
_LEASE_SECONDS = 600


def scoring_error(error: Exception) -> str:
    return skill_error_text(error)


class SkillAutoScoring:
    def __init__(
        self,
        repository: AgentKitSkillRepository,
        *,
        provider: str,
        regions: list[str],
        store: Any = None,
        scorer: Callable[..., Awaitable[dict[str, Any]]] = score_skill_snapshot,
        recovery_interval: float = 30,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.regions = regions
        self.store = store if store is not None else TosScoreStore()
        self.scorer = scorer
        self.recovery_interval = recovery_interval
        self._pending: set[tuple[str, str]] = set()
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._limit = asyncio.Semaphore(2)
        self._operational_errors: dict[tuple[str, str], str] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def _store_for(self, application: dict[str, Any]) -> Any:
        location = application.get("scoreStorage")
        if location and isinstance(self.store, TosScoreStore):
            return self.store.for_location(
                location["bucket"], location["key"], application["id"]
            )
        return self.store

    def notify(self, region: str, application_id: str) -> None:
        self._pending.add((region, application_id))
        self._wake.set()

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._loop = None

    def read(
        self, identity: SkillIdentity, region: str, application_id: str
    ) -> dict[str, Any]:
        application = self.repository.reviews.get(
            identity, region=region, application_id=application_id
        )
        job, _ = self._store_for(application).read(region, application_id)
        error = self._operational_errors.get((region, application_id))
        if job is None:
            if error:
                return {"status": "failed", "error": error}
            return application.get("aiReview") or {"status": "not_requested"}
        return {**job.public(), **({"error": error} if error else {})}

    def retry(
        self, identity: SkillIdentity, region: str, application_id: str
    ) -> dict[str, Any]:
        self.repository.reviews.require_admin(identity)
        application = self.repository.reviews.get(
            identity, region=region, application_id=application_id
        )
        store = self._store_for(application)
        job, etag = store.read(region, application_id)
        if job is not None and job.status in {"queued", "running", "completed"}:
            return job.public()
        queued = ScoreJob()
        try:
            store.write(region, application_id, queued, etag)
        except ScoreConflict:
            raise SkillRepositoryError(
                "SKILL_SCORE_CONFLICT", "评分任务已更新，请刷新", status_code=409
            ) from None
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self.notify, region, application_id)
        self._sync_tags(region, application_id, queued, store)
        self._operational_errors.pop((region, application_id), None)
        return queued.public()

    def _recover(self, region: str) -> list[tuple[str, str]]:
        import os
        from .system_spaces import SystemSpaceManager

        client = self.repository._client_factory(region)
        project = os.getenv("VEADK_STUDIO_PROJECT", "").strip() or "default"
        space = SystemSpaceManager._find(client, project, REVIEW_SPACE)
        if space is None:
            return []
        return [
            (region, item["id"])
            for item in self.repository.reviews._applications(client, space.id, region)
            if item.get("aiReview")
        ]

    async def _run(self) -> None:
        recover_at = 0.0
        while True:
            self._wake.clear()
            if time.monotonic() >= recover_at:
                for region in self.regions:
                    try:
                        self._pending.update(
                            await asyncio.to_thread(self._recover, region)
                        )
                    except Exception as error:
                        logger.warning(
                            "Skill score recovery failed for %s (%s)",
                            region,
                            type(error).__name__,
                        )
                recover_at = time.monotonic() + self.recovery_interval
            pending, self._pending = self._pending, set()
            await asyncio.gather(
                *(self.process(region, identifier) for region, identifier in pending)
            )
            if self._pending:
                continue
            try:
                await asyncio.wait_for(
                    self._wake.wait(), timeout=self.recovery_interval
                )
            except (TimeoutError, asyncio.TimeoutError):
                pass

    def _sync_tags(
        self, region: str, application_id: str, job: ScoreJob, store: Any = None
    ) -> None:
        store = store if store is not None else self.store
        for _ in range(3):
            latest, etag = store.read(region, application_id)
            self._write_tags(region, application_id, latest or job, store)
            _, current_etag = store.read(region, application_id)
            if current_etag == etag:
                return
        # A subsequent recovery scan reconciles tags if another attempt kept changing

    def _write_tags(
        self, region: str, application_id: str, job: ScoreJob, store: Any
    ) -> None:
        # Errors live in the private JSON document without tag length limits
        bucket, key = store.location(region, application_id)
        tags = {
            SCORE_STATUS_TAG: job.status,
            SCORE_BUCKET_TAG: bucket,
            SCORE_KEY_TAG: key,
        }
        if job.result is not None:
            tags.update(
                {
                    SCORE_TOTAL_TAG: ""
                    if job.result.overallScore is None
                    else str(job.result.overallScore),
                    SCORE_TIME_TAG: job.result.scoredAt,
                    SCORE_MODEL_TAG: job.result.modelName,
                    SCORE_RUBRIC_TAG: job.result.rubricVersion,
                }
            )
        update_skill_tags(self.repository._client_factory(region), application_id, tags)

    async def process(self, region: str, application_id: str) -> None:
        async with self._limit:
            try:
                await self._process(region, application_id)
            except ScoreConflict:
                return
            except Exception as error:
                logger.warning(
                    "Skill score job %s failed (%s)",
                    application_id,
                    type(error).__name__,
                )
                self._operational_errors[(region, application_id)] = scoring_error(
                    error
                )
                try:
                    application = await asyncio.to_thread(
                        self.repository.reviews.get,
                        SkillIdentity("", True),
                        region=region,
                        application_id=application_id,
                    )
                    store = self._store_for(application)
                    job, etag = await asyncio.to_thread(
                        store.read, region, application_id
                    )
                    if job is None:
                        job = ScoreJob(status="failed", error=scoring_error(error))
                    elif job.status == "completed":
                        job = job.model_copy(update={"error": scoring_error(error)})
                    if job.status in {"completed", "failed"}:
                        await asyncio.to_thread(
                            store.write, region, application_id, job, etag
                        )
                    await asyncio.to_thread(
                        self._sync_tags, region, application_id, job, store
                    )
                except Exception as write_error:
                    logger.warning(
                        "Skill score state write failed (%s)",
                        type(write_error).__name__,
                    )

    async def _process(self, region: str, application_id: str) -> None:
        application = await asyncio.to_thread(
            self.repository.reviews.get,
            SkillIdentity("", True),
            region=region,
            application_id=application_id,
        )
        store = self._store_for(application)
        job, etag = await asyncio.to_thread(store.read, region, application_id)
        if job is not None and job.status in {"completed", "failed"}:
            await asyncio.to_thread(self._sync_tags, region, application_id, job, store)
            if job.status == "completed" and job.error:
                job = job.model_copy(update={"error": ""})
                await asyncio.to_thread(store.write, region, application_id, job, etag)
            self._operational_errors.pop((region, application_id), None)
            return
        if job is not None and job.status == "running" and job.leaseUntil > time.time():
            return
        if job is not None and job.attempts >= 2:
            job = ScoreJob(
                status="failed",
                attempts=job.attempts,
                error=job.error or "Scoring worker interrupted after the final attempt",
            )
            await asyncio.to_thread(store.write, region, application_id, job, etag)
            await asyncio.to_thread(self._sync_tags, region, application_id, job, store)
            return
        job = ScoreJob(
            status="running",
            attempts=(job.attempts if job else 0) + 1,
            leaseUntil=time.time() + _LEASE_SECONDS,
            error=job.error if job else "",
        )
        etag = await asyncio.to_thread(store.write, region, application_id, job, etag)
        try:
            await asyncio.to_thread(self._sync_tags, region, application_id, job, store)
            snapshot = await asyncio.to_thread(
                self.repository.reviews.files,
                SkillIdentity("", True),
                region=region,
                application_id=application_id,
            )
            report = SkillAssessmentReport.model_validate(
                await self.scorer(
                    provider=self.provider,
                    name=application["name"],
                    version=application["version"],
                    files=snapshot["files"],
                    application_id=application_id,
                )
            )
            if (
                report.applicationId != application_id
                or report.skillVersion != application["version"]
            ):
                raise ValueError("Score result does not match the submitted version")
            job = ScoreJob(status="completed", attempts=job.attempts, result=report)
        except asyncio.CancelledError:
            # The persisted lease allows another process to recover after shutdown
            raise
        except Exception as error:
            retryable = job.attempts < 2 and "modelnotopen" not in str(error).lower()
            job = ScoreJob(
                status="queued" if retryable else "failed",
                attempts=job.attempts,
                error=scoring_error(error),
            )
        try:
            await asyncio.to_thread(store.write, region, application_id, job, etag)
        except ScoreConflict:
            raise
        except Exception as error:
            # Only our claimed ETag may record a failed final persistence attempt
            failed = ScoreJob(
                status="failed", attempts=job.attempts, error=scoring_error(error)
            )
            try:
                await asyncio.to_thread(
                    store.write, region, application_id, failed, etag
                )
            except Exception:
                pass
            raise
        await asyncio.to_thread(self._sync_tags, region, application_id, job, store)
        self._operational_errors.pop((region, application_id), None)
