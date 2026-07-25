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

"""Release job orchestration independent from HTTP and cloud storage details."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

from frontend.service.studio_release_server.builder import ReleaseBuilder
from frontend.service.studio_release_server.models import (
    ReleaseRequest,
    ReleaseServerSettings,
    ReleaseStatus,
    SourceUpload,
)
from frontend.service.studio_release_server.tos_store import JobStore, SourceStore

logger = logging.getLogger(__name__)


class ReleaseNotFoundError(LookupError):
    """Raised when a release status does not exist."""


class ReleaseConflictError(ValueError):
    """Raised when one request ID refers to different release inputs."""


class ReleaseService:
    """Accept idempotent jobs and execute at most one build per instance."""

    def __init__(
        self,
        *,
        settings: ReleaseServerSettings,
        store: JobStore,
        builder: ReleaseBuilder,
        source_store: SourceStore | None = None,
        executor: Executor | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._builder = builder
        self._source_store = source_store
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="studio-release"
        )
        self._active: set[str] = set()
        self._active_lock = threading.Lock()

    def submit(
        self,
        request: ReleaseRequest,
        *,
        run_inline: bool = False,
    ) -> ReleaseStatus:
        """Create one job and optionally keep the request active until completion."""
        if request.repository != self._settings.repository:
            raise ValueError("repository is not allowed by this release server")
        if request.source_key:
            if self._source_store is None:
                raise ValueError("source staging is not configured")
            if request.source_key != self._source_store.expected_key(
                request.request_id
            ):
                raise ValueError("sourceKey does not belong to requestId")
        existing = self._store.get(request.request_id)
        if existing is not None:
            if (
                existing.repository != request.repository
                or existing.git_sha != request.git_sha
                or existing.changelog != request.changelog
                or existing.source_key != request.source_key
            ):
                raise ReleaseConflictError(
                    "requestId already belongs to another release request"
                )
            return existing
        now = _timestamp()
        status = ReleaseStatus(
            jobId=request.request_id,
            state="queued",
            repository=request.repository,
            gitSha=request.git_sha,
            changelog=request.changelog,
            sourceKey=request.source_key,
            stage="queued",
            message="发布任务已入队",
            createdAt=now,
            updatedAt=now,
        )
        self._store.put(status)
        should_submit = False
        with self._active_lock:
            if request.request_id not in self._active:
                self._active.add(request.request_id)
                should_submit = True
        if should_submit:
            if run_inline:
                self._run(request)
            else:
                self._executor.submit(self._run, request)
        return self.get(request.request_id) if run_inline else status

    def prepare_source_upload(self, job_id: str) -> SourceUpload:
        """Create a private, short-lived upload target for one release job."""
        if self._source_store is None:
            raise ValueError("source staging is not configured")
        return self._source_store.prepare_upload(job_id)

    def get(self, job_id: str) -> ReleaseStatus:
        """Return one durable release status."""
        status = self._store.get(job_id)
        if status is None:
            raise ReleaseNotFoundError(job_id)
        return status

    def _run(self, request: ReleaseRequest) -> None:
        try:
            started = _timestamp()
            self._update(
                request.request_id,
                state="running",
                stage="starting",
                message="发布任务开始执行",
                started_at=started,
            )

            def on_progress(stage: str, message: str) -> None:
                self._update(
                    request.request_id,
                    state="running",
                    stage=stage,
                    message=message,
                )

            result = self._builder.build(request, on_progress)
            self._update(
                request.request_id,
                state="succeeded",
                stage="complete",
                message="Studio 发布成功",
                completed_at=_timestamp(),
                result=result,
            )
        except Exception as error:
            logger.exception("Studio release job %s failed", request.request_id)
            self._update(
                request.request_id,
                state="failed",
                stage="failed",
                message="Studio 发布失败",
                completed_at=_timestamp(),
                error=str(error)[-8000:],
            )
        finally:
            with self._active_lock:
                self._active.discard(request.request_id)

    def _update(self, job_id: str, **changes: object) -> None:
        current = self.get(job_id)
        fields = {"updated_at": _timestamp(), **changes}
        self._store.put(current.model_copy(update=fields))


def _timestamp() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


__all__ = [
    "ReleaseConflictError",
    "ReleaseNotFoundError",
    "ReleaseService",
]
