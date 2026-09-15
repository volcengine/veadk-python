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

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import test_reviews
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from frontend.server.skills.auto_scoring import SkillAutoScoring
from frontend.server.skills.consts import SCORE_STATUS_TAG
from frontend.server.skills.models import SkillIdentity
from frontend.server.skills.routes import mount_skill_routes
from frontend.server.skills.score_store import ScoreConflict, ScoreJob
from frontend.server.skills.service import SkillService
from frontend.server.skills.system_spaces import SystemSpaceManager

review_setup = test_reviews.setup
submit = test_reviews.submit

REGION = "cn-beijing"


class MemoryStore:
    """Store serialized documents and enforce the same conditional-write contract."""

    def __init__(self):
        self.documents = {}
        self.lock = threading.Lock()
        self.revision = 0

    def location(self, region, application_id):
        return "private-test-bucket", f"review-scores/{application_id}.json"

    def read(self, region, application_id):
        with self.lock:
            value = self.documents.get((region, application_id))
            if value is None:
                return None, ""
            content, etag = value
            return ScoreJob.model_validate_json(content), etag

    def write(self, region, application_id, job, etag=""):
        with self.lock:
            current = self.documents.get((region, application_id))
            if (current[1] if current else "") != etag:
                raise ScoreConflict()
            self.revision += 1
            next_etag = str(self.revision)
            self.documents[(region, application_id)] = (
                job.model_dump_json(),
                next_etag,
            )
            return next_etag


def report_for(**request):
    return {
        "applicationId": request["application_id"],
        "skillName": request["name"],
        "skillVersion": request["version"],
        "provider": request["provider"],
        "modelName": "test-planner-model",
        "rubricVersion": "1",
        "scoredAt": "2026-09-11T12:00:00+00:00",
        "overallScore": 80,
        "dimensions": {
            key: {"score": 80, "reason": "SKILL.md 有明确输入输出说明"}
            for key in (
                "safety",
                "usability",
                "completeness",
                "reliability",
                "maintainability",
            )
        },
        "riskFlags": [],
        "suggestions": ["补充失败处理示例"],
        "coverage": {
            "complete": True,
            "totalFiles": len(request["files"]),
            "includedFiles": len(request["files"]),
            "omittedFiles": [],
            "truncatedFiles": [],
        },
    }


async def score(**request):
    return report_for(**request)


def worker(repository, store, scorer=score):
    return SkillAutoScoring(
        repository,
        provider="volcengine",
        regions=[REGION],
        store=store,
        scorer=scorer,
        recovery_interval=0.02,
    )


def identity(request: Request):
    user = request.headers.get("test-user", "alice")
    return SkillIdentity(user, is_admin=user == "admin")


def app_for(repository, scoring, *, lifespan=None):
    app = FastAPI(lifespan=lifespan)
    mount_skill_routes(app, SkillService(repository), identity, scoring=scoring)
    return app


def set_status(cloud, application_id, status):
    skill = cloud.skills[application_id]
    skill.tags = [tag for tag in skill.tags if tag.key != SCORE_STATUS_TAG]
    if status:
        skill.tags.append(SimpleNamespace(key=SCORE_STATUS_TAG, value=status))


@pytest.mark.asyncio
async def test_idle_worker_continues_recovery_after_poll_timeout(
    review_setup, monkeypatch
):
    _, repository = review_setup
    scoring = worker(repository, MemoryStore())
    loop = asyncio.get_running_loop()
    recovered = asyncio.Event()
    scans = 0

    def recover(region):
        nonlocal scans
        scans += 1
        if scans >= 3:
            loop.call_soon_threadsafe(recovered.set)
        return []

    monkeypatch.setattr(scoring, "_recover", recover)
    await scoring.start()
    try:
        await asyncio.wait_for(recovered.wait(), timeout=2)
        assert scoring._task is not None and not scoring._task.done()
    finally:
        await scoring.close()


@pytest.mark.asyncio
async def test_scores_fixed_review_copy_and_persists_source_version_after_restart(
    review_setup, monkeypatch
):
    cloud, repository = review_setup
    application = submit(repository)
    captured = []
    file_requests = []
    original = repository.skill_files

    def files(**request):
        file_requests.append(request)
        return original(**request)

    async def scorer(**request):
        captured.append(request)
        return report_for(**request)

    monkeypatch.setattr(repository, "skill_files", files)
    cloud.relations["alice"][0].version = "v4"
    store = MemoryStore()
    scoring = worker(repository, store, scorer)
    await scoring.process(REGION, application["id"])
    assert len(captured) == 1
    assert captured[0]["version"] == "v3"
    assert any("alice" in item["content"] for item in captured[0]["files"])
    assert file_requests[0]["skill_id"] == application["id"]
    assert file_requests[0]["space_id"] == "review"
    assert file_requests[0]["version"] == "v1"
    restarted = worker(repository, store)
    persisted = restarted.read(SkillIdentity("alice"), REGION, application["id"])
    assert persisted["status"] == "completed"
    assert persisted["result"]["skillVersion"] == "v3"
    assert persisted["result"]["dimensions"]["safety"]["reason"]
    assert (
        repository.reviews.get(
            SkillIdentity("alice"), region=REGION, application_id=application["id"]
        )["aiReview"]["overallScore"]
        == 80
    )


def test_submission_returns_queued_while_background_model_is_blocked(
    review_setup, monkeypatch
):
    _, repository = review_setup
    entered = threading.Event()
    release = threading.Event()

    async def scorer(**request):
        entered.set()
        await asyncio.to_thread(release.wait, 2)
        return report_for(**request)

    scoring = worker(repository, MemoryStore(), scorer)
    monkeypatch.setattr(scoring, "_recover", lambda _: [])
    try:
        with TestClient(app_for(repository, scoring)) as client:
            result = client.post(
                "/web/skill-management/spaces/alice/skills/alice/review",
                json={"region": REGION, "version": "v3"},
            )
            assert result.status_code == 200
            assert result.json()["aiReview"] == {"status": "queued"}
            assert entered.wait(2)
            assert not release.is_set()
            release.set()
    finally:
        release.set()
    assert scoring._task is None


@pytest.mark.asyncio
async def test_conditional_claim_allows_only_one_model_call_across_workers(
    review_setup,
):
    _, repository = review_setup
    application = submit(repository)
    store = MemoryStore()
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def scorer(**request):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return report_for(**request)

    workers = [worker(repository, store, scorer) for _ in range(2)]
    tasks = [
        asyncio.create_task(item.process(REGION, application["id"])) for item in workers
    ]
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        done, _ = await asyncio.wait(
            tasks, timeout=2, return_when=asyncio.FIRST_COMPLETED
        )
        assert len(done) == 1
        assert calls == 1
    finally:
        release.set()
        await asyncio.gather(*tasks)
    job, _ = store.read(REGION, application["id"])
    assert job.status == "completed"
    assert job.attempts == 1


@pytest.mark.asyncio
async def test_recovery_finds_queued_and_expired_running_but_skips_legacy(
    review_setup, monkeypatch
):
    cloud, repository = review_setup
    queued = submit(repository)
    running = submit(repository, "bob")
    cloud.relations["alice"][0].version = "v4"
    legacy = repository.reviews.submit(
        SkillIdentity("alice"),
        region=REGION,
        space_id="alice",
        skill_id="alice",
        version="v4",
    )
    set_status(cloud, running["id"], "running")
    set_status(cloud, legacy["id"], None)
    monkeypatch.setattr(
        SystemSpaceManager,
        "_find",
        staticmethod(lambda *_: SimpleNamespace(id="review")),
    )
    store = MemoryStore()
    store.write(
        REGION,
        running["id"],
        ScoreJob(status="running", attempts=1, leaseUntil=time.time() - 1),
    )
    scoring = worker(repository, store)
    recovered = scoring._recover(REGION)
    assert set(recovered) == {(REGION, queued["id"]), (REGION, running["id"])}
    await asyncio.gather(*(scoring.process(*item) for item in recovered))
    assert store.read(REGION, queued["id"])[0].status == "completed"
    assert store.read(REGION, running["id"])[0].attempts == 2
    assert store.read(REGION, legacy["id"])[0] is None


@pytest.mark.asyncio
async def test_active_lease_does_not_repeat_model_call(review_setup):
    _, repository = review_setup
    application = submit(repository)
    store = MemoryStore()
    store.write(
        REGION,
        application["id"],
        ScoreJob(status="running", attempts=1, leaseUntil=time.time() + 60),
    )

    async def unexpected(**_):
        pytest.fail("An active lease must not invoke the model")

    await worker(repository, store, unexpected).process(REGION, application["id"])
    job, _ = store.read(REGION, application["id"])
    assert job.status == "running"
    assert job.attempts == 1


@pytest.mark.asyncio
async def test_background_loop_recovers_without_notify_and_retries_transient_failure(
    review_setup, monkeypatch
):
    _, repository = review_setup
    application = submit(repository)
    monkeypatch.setattr(
        SystemSpaceManager,
        "_find",
        staticmethod(lambda *_: SimpleNamespace(id="review")),
    )
    calls = 0

    async def transient(**request):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("Original cloud 503 ServiceUnavailable, request first")
        return report_for(**request)

    store = MemoryStore()
    scoring = worker(repository, store, transient)

    async def terminal_job():
        while True:
            job, _ = store.read(REGION, application["id"])
            if job is not None and job.status in {"completed", "failed"}:
                return job
            await asyncio.sleep(0.01)

    await scoring.start()
    try:
        job = await asyncio.wait_for(terminal_job(), timeout=2)
    finally:
        await scoring.close()
    assert job.status == "completed"
    assert job.attempts == 2
    assert calls == 2


@pytest.mark.asyncio
async def test_expired_last_attempt_is_not_replayed(review_setup):
    _, repository = review_setup
    application = submit(repository)
    store = MemoryStore()
    store.write(
        REGION,
        application["id"],
        ScoreJob(status="running", attempts=2, leaseUntil=time.time() - 1),
    )
    calls = 0

    async def unexpected(**request):
        nonlocal calls
        calls += 1
        return report_for(**request)

    await worker(repository, store, unexpected).process(REGION, application["id"])
    job, _ = store.read(REGION, application["id"])
    assert calls == 0
    assert job.status == "failed"
    assert job.attempts == 2


@pytest.mark.asyncio
async def test_model_failure_stops_after_two_attempts_and_preserves_full_error_on_get(
    review_setup,
):
    _, repository = review_setup
    application = submit(repository)
    original_error = (
        'Error code: 429 - {"code":"RateLimitExceeded","message":"'
        + "原始云端错误" * 500
        + '","request_id":"original-request"}'
    )
    calls = 0

    async def failing(**_):
        nonlocal calls
        calls += 1
        raise RuntimeError(original_error)

    store = MemoryStore()
    scoring = worker(repository, store, failing)
    await scoring.process(REGION, application["id"])
    assert store.read(REGION, application["id"])[0].status == "queued"
    await scoring.process(REGION, application["id"])
    await scoring.process(REGION, application["id"])
    assert calls == 2
    restarted = worker(repository, store)
    client = TestClient(app_for(repository, restarted))
    response = client.get(
        f"/web/skill-management/reviews/{application['id']}/score",
        params={"region": REGION},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "failed", "error": original_error}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["range", "version", "application"])
async def test_invalid_model_result_is_not_persisted_as_completed(
    review_setup, failure
):
    _, repository = review_setup
    application = submit(repository)

    async def malformed(**request):
        result = report_for(**request)
        if failure == "range":
            result["dimensions"]["safety"]["score"] = 101
        elif failure == "version":
            result["skillVersion"] = "v999"
        else:
            result["applicationId"] = "another-application"
        return result

    store = MemoryStore()
    scoring = worker(repository, store, malformed)
    await scoring.process(REGION, application["id"])
    await scoring.process(REGION, application["id"])
    job, _ = store.read(REGION, application["id"])
    assert job.status == "failed"
    assert job.result is None
    assert job.error


@pytest.mark.asyncio
async def test_completed_document_survives_tag_failure_without_rescoring(
    review_setup, monkeypatch
):
    _, repository = review_setup
    application = submit(repository)
    calls = 0

    async def scorer(**request):
        nonlocal calls
        calls += 1
        return report_for(**request)

    store = MemoryStore()
    scoring = worker(repository, store, scorer)
    original = scoring._sync_tags

    def fail_completed(region, application_id, job, store=None):
        if job.status == "completed":
            raise RuntimeError("original completed tag write failure")
        original(region, application_id, job, store)

    monkeypatch.setattr(scoring, "_sync_tags", fail_completed)
    await scoring.process(REGION, application["id"])
    assert store.read(REGION, application["id"])[0].status == "completed"
    assert (
        scoring.read(SkillIdentity("alice"), REGION, application["id"])["status"]
        == "completed"
    )
    restarted = worker(repository, store, scorer)
    await restarted.process(REGION, application["id"])
    assert calls == 1
    assert (
        repository.reviews.get(
            SkillIdentity("alice"), region=REGION, application_id=application["id"]
        )["aiReview"]["status"]
        == "completed"
    )


def test_only_admin_can_retry_and_other_users_cannot_read_results(review_setup):
    _, repository = review_setup
    application = submit(repository)
    store = MemoryStore()
    store.write(
        REGION,
        application["id"],
        ScoreJob(status="failed", attempts=2, error="cloud error"),
    )
    scoring = worker(repository, store)
    client = TestClient(app_for(repository, scoring))
    path = f"/web/skill-management/reviews/{application['id']}/score"
    assert client.get(path, params={"region": REGION}).json()["error"] == "cloud error"
    assert (
        client.get(
            path, params={"region": REGION}, headers={"test-user": "bob"}
        ).status_code
        == 403
    )
    assert client.post(path + "/retry", json={"region": REGION}).status_code == 403
    response = client.post(
        path + "/retry", json={"region": REGION}, headers={"test-user": "admin"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "queued"}
    assert store.read(REGION, application["id"])[0].attempts == 0
    assert (REGION, application["id"]) in scoring._pending


def test_scoring_preserves_existing_app_lifespan_state_and_shutdown(
    review_setup, monkeypatch
):
    _, repository = review_setup
    events = []

    @asynccontextmanager
    async def existing_lifespan(_app):
        events.append("existing-start")
        yield {"existing_resource": "available"}
        events.append("existing-close")

    scoring = worker(repository, MemoryStore())
    monkeypatch.setattr(scoring, "_recover", lambda _: [])
    original_start = scoring.start
    original_close = scoring.close

    async def start():
        events.append("scoring-start")
        await original_start()

    async def close():
        await original_close()
        events.append("scoring-close")

    monkeypatch.setattr(scoring, "start", start)
    monkeypatch.setattr(scoring, "close", close)
    app = app_for(repository, scoring, lifespan=existing_lifespan)

    @app.get("/existing-state")
    async def state(request: Request):
        return {"value": request.state.existing_resource}

    with TestClient(app) as client:
        assert client.get("/existing-state").json() == {"value": "available"}
        assert scoring._task is not None
    assert scoring._task is None
    assert events == [
        "existing-start",
        "scoring-start",
        "scoring-close",
        "existing-close",
    ]


@pytest.mark.asyncio
async def test_final_store_503_is_visible_on_get_and_does_not_leave_running_job(
    review_setup, monkeypatch
):
    _, repository = review_setup
    application = submit(repository)
    store = MemoryStore()
    original_write = store.write
    original_error = 'HTTP 503 {"code":"ServiceUnavailable","message":"TOS result write unavailable","request_id":"final-write-request"}'

    def fail_completed(region, application_id, job, etag=""):
        if job.status == "completed":
            raise RuntimeError(original_error)
        return original_write(region, application_id, job, etag)

    monkeypatch.setattr(store, "write", fail_completed)
    scoring = worker(repository, store)
    await scoring.process(REGION, application["id"])
    job, _ = store.read(REGION, application["id"])
    assert job.status == "failed"
    assert job.error == original_error
    restarted = worker(repository, store)
    client = TestClient(app_for(repository, restarted))
    response = client.get(
        f"/web/skill-management/reviews/{application['id']}/score",
        params={"region": REGION},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "failed", "error": original_error}
    await restarted.process(REGION, application["id"])
    assert store.read(REGION, application["id"])[0].status == "failed"


@pytest.mark.asyncio
async def test_failed_result_and_fallback_writes_recover_after_lease_expiry(
    review_setup, monkeypatch
):
    _, repository = review_setup
    application = submit(repository)
    store = MemoryStore()
    original_write = store.write
    failures = 2
    calls = 0
    original_error = "HTTP 503 TOS unavailable, request_id=temporary-storage-outage"

    def fail_final_writes(region, application_id, job, etag=""):
        nonlocal failures
        if job.status in {"completed", "failed"} and failures:
            failures -= 1
            raise RuntimeError(original_error)
        return original_write(region, application_id, job, etag)

    async def scorer(**request):
        nonlocal calls
        calls += 1
        return report_for(**request)

    monkeypatch.setattr(store, "write", fail_final_writes)
    scoring = worker(repository, store, scorer)
    await scoring.process(REGION, application["id"])
    response = TestClient(app_for(repository, scoring)).get(
        f"/web/skill-management/reviews/{application['id']}/score",
        params={"region": REGION},
    )
    assert response.status_code == 200
    assert response.json()["error"] == original_error
    job, etag = store.read(REGION, application["id"])
    assert job.status == "running"
    original_write(
        REGION,
        application["id"],
        job.model_copy(update={"leaseUntil": time.time() - 1}),
        etag,
    )
    await scoring.process(REGION, application["id"])
    assert store.read(REGION, application["id"])[0].status == "completed"
    assert calls == 2
    assert "error" not in scoring.read(
        SkillIdentity("alice"), REGION, application["id"]
    )


@pytest.mark.asyncio
async def test_old_failed_tag_write_cannot_overwrite_new_completed_retry_forever(
    review_setup, monkeypatch
):
    _, repository = review_setup
    application = submit(repository)
    store = MemoryStore()
    failed = ScoreJob(status="failed", attempts=2, error="old failed attempt")
    store.write(REGION, application["id"], failed)
    stale_worker = worker(repository, store)
    retry_worker = worker(repository, store)
    entered = threading.Event()
    release = threading.Event()
    original = stale_worker._write_tags

    def delayed_old_write(region, application_id, job, selected_store):
        if job.status == "failed" and not entered.is_set():
            entered.set()
            assert release.wait(3), (
                "New retry must complete before old tag write resumes"
            )
        original(region, application_id, job, selected_store)

    monkeypatch.setattr(stale_worker, "_write_tags", delayed_old_write)
    old_write = asyncio.create_task(
        asyncio.to_thread(
            stale_worker._sync_tags, REGION, application["id"], failed, store
        )
    )
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        retry_worker.retry(SkillIdentity("admin", True), REGION, application["id"])
        await retry_worker.process(REGION, application["id"])
        assert store.read(REGION, application["id"])[0].status == "completed"
    finally:
        release.set()
        await old_write
    application = repository.reviews.get(
        SkillIdentity("alice"), region=REGION, application_id=application["id"]
    )
    assert application["aiReview"]["status"] == "completed"
    assert application["aiReview"]["overallScore"] == 80


@pytest.mark.asyncio
@pytest.mark.parametrize("summary_status", ["completed", "failed"])
async def test_recovery_reconciles_terminal_summaries_without_rescoring(
    review_setup, monkeypatch, summary_status
):
    cloud, repository = review_setup
    application = submit(repository)
    store = MemoryStore()
    calls = 0

    async def scorer(**request):
        nonlocal calls
        calls += 1
        return report_for(**request)

    scoring = worker(repository, store, scorer)
    await scoring.process(REGION, application["id"])
    set_status(cloud, application["id"], summary_status)
    monkeypatch.setattr(
        SystemSpaceManager,
        "_find",
        staticmethod(lambda *_: SimpleNamespace(id="review")),
    )
    recovered = scoring._recover(REGION)
    assert (REGION, application["id"]) in recovered
    await asyncio.gather(*(scoring.process(*item) for item in recovered))
    assert calls == 1
    assert (
        repository.reviews.get(
            SkillIdentity("alice"), region=REGION, application_id=application["id"]
        )["aiReview"]["status"]
        == "completed"
    )
