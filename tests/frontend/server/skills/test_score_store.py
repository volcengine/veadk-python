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

"""CAS, raw cloud errors and bounded private score storage."""

from __future__ import annotations

import inspect
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError
from tos import TosClientV2
from tos.enum import ACLType
from tos.exceptions import TosClientError, TosServerError

from frontend.server.skills import storage
from frontend.server.skills.score_store import ScoreConflict, ScoreJob, TosScoreStore
from frontend.server.skills.scoring_model import SkillAssessmentReport


def cloud_error(status: int, code: str) -> TosServerError:
    return TosServerError(
        SimpleNamespace(status=status, request_id="cloud-log-id", headers={}),
        "Original cloud error",
        code,
        "host",
        "resource",
    )


class ReadResponse:
    def __init__(
        self, body: bytes, *, etag: str = "current-etag", length: int | None = None
    ) -> None:
        self.body = BytesIO(body)
        self.etag = etag
        self.content_length = length
        self.closed = False
        self.reads: list[int] = []
        self.error: Exception | None = None
        self.resp = SimpleNamespace(resp=self)

    def read(self, amount: int) -> bytes:
        self.reads.append(amount)
        if self.error is not None:
            raise self.error
        return self.body.read(min(amount, 113))

    def close(self) -> None:
        self.closed = True


class Client:
    def __init__(self) -> None:
        self.response = ReadResponse(ScoreJob().model_dump_json().encode())
        self.put_etag = "next-etag"
        self.error: Exception | None = None
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_object(self, *args: object, **kwargs: object) -> ReadResponse:
        bound = inspect.signature(TosClientV2.get_object).bind(self, *args, **kwargs)
        self.calls.append(("get", bound.arguments))
        if self.error is not None:
            raise self.error
        return self.response

    def put_object(self, *args: object, **kwargs: object) -> SimpleNamespace:
        bound = inspect.signature(TosClientV2.put_object).bind(self, *args, **kwargs)
        self.calls.append(("put", bound.arguments))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(etag=self.put_etag)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> tuple[TosScoreStore, Client]:
    client = Client()
    instance = TosScoreStore()
    monkeypatch.setattr(
        instance,
        "_storage",
        lambda region: (
            SimpleNamespace(bucket="private-skills", prefix="/studio/skills/"),
            object(),
        ),
    )
    monkeypatch.setattr(storage, "_create_tos_client", lambda *_: client)
    monkeypatch.setattr(
        storage,
        "ensure_skill_publish_bucket",
        lambda *_: pytest.fail("Score jobs must not create or list buckets"),
    )
    return instance, client


def test_create_is_private_json_and_does_not_overwrite(
    store: tuple[TosScoreStore, Client],
) -> None:
    instance, client = store
    job = ScoreJob(error="中文信息")
    assert instance.write("cn-beijing", "s-review-1", job) == "next-etag"
    operation, request = client.calls[-1]
    assert operation == "put"
    assert request["bucket"] == "private-skills"
    assert request["key"] == "studio/skills/review-scores/s-review-1.json"
    assert request["forbid_overwrite"] is True
    assert "if_match" not in request
    assert request["acl"] is ACLType.ACL_Private
    assert request["content_type"] == "application/json; charset=utf-8"
    assert request["cache_control"] == "no-store"
    assert ScoreJob.model_validate_json(request["content"]) == job


def test_update_uses_the_read_etag_for_compare_and_swap(
    store: tuple[TosScoreStore, Client],
) -> None:
    instance, client = store
    job, etag = instance.read("cn-beijing", "s-review-1")
    assert job == ScoreJob()
    assert etag == "current-etag"
    assert (
        instance.write("cn-beijing", "s-review-1", ScoreJob(status="running"), etag)
        == "next-etag"
    )
    request = client.calls[-1][1]
    assert request["if_match"] == "current-etag"
    assert "forbid_overwrite" not in request


@pytest.mark.parametrize("status", [409, 412])
def test_conditional_conflict_keeps_cloud_error_as_cause(
    store: tuple[TosScoreStore, Client], status: int
) -> None:
    instance, client = store
    client.error = cloud_error(status, "PreconditionFailed")
    with pytest.raises(ScoreConflict) as captured:
        instance.write("cn-beijing", "s-review-1", ScoreJob(), "stale-etag")
    assert captured.value.__cause__ is client.error


@pytest.mark.parametrize(
    "error",
    [
        cloud_error(403, "AccessDenied"),
        cloud_error(404, "NoSuchBucket"),
        cloud_error(503, "ServiceUnavailable"),
        TosClientError("network failure"),
    ],
)
@pytest.mark.parametrize("operation", ["read", "write"])
def test_other_cloud_errors_propagate_unchanged(
    store: tuple[TosScoreStore, Client], error: Exception, operation: str
) -> None:
    instance, client = store
    client.error = error
    with pytest.raises(type(error)) as captured:
        if operation == "read":
            instance.read("cn-beijing", "s-review-1")
        else:
            instance.write("cn-beijing", "s-review-1", ScoreJob())
    assert captured.value is error


def test_only_missing_object_is_an_empty_job(
    store: tuple[TosScoreStore, Client],
) -> None:
    instance, client = store
    client.error = cloud_error(404, "NoSuchKey")
    assert instance.read("cn-beijing", "s-review-1") == (None, "")


def test_stream_is_read_until_eof_and_closed(
    store: tuple[TosScoreStore, Client],
) -> None:
    instance, client = store
    job = ScoreJob(error="审核说明" * 100)
    client.response = ReadResponse(job.model_dump_json().encode())
    assert instance.read("cn-beijing", "s-review-1")[0] == job
    assert len(client.response.reads) > 2
    assert client.response.closed


def test_stream_error_remains_original_and_closes_response(
    store: tuple[TosScoreStore, Client],
) -> None:
    instance, client = store
    error = TosClientError("CRC mismatch")
    client.response.error = error
    with pytest.raises(TosClientError) as captured:
        instance.read("cn-beijing", "s-review-1")
    assert captured.value is error
    assert client.response.closed


@pytest.mark.parametrize(
    "body",
    [b"not-json", b'{"status":"invented"}', b'{"status":"queued","injected":true}'],
)
def test_invalid_persisted_job_fails_explicitly(
    store: tuple[TosScoreStore, Client], body: bytes
) -> None:
    instance, client = store
    client.response = ReadResponse(body)
    with pytest.raises(ValidationError):
        instance.read("cn-beijing", "s-review-1")
    assert client.response.closed


@pytest.mark.parametrize("declared_length", [None, 512 * 1024 + 1])
def test_read_rejects_large_report_even_without_content_length(
    store: tuple[TosScoreStore, Client], declared_length: int | None
) -> None:
    instance, client = store
    client.response = ReadResponse(b"x" * (512 * 1024 + 1), length=declared_length)
    with pytest.raises(ValueError, match="too large"):
        instance.read("cn-beijing", "s-review-1")
    assert client.response.closed


def test_write_cannot_save_a_report_larger_than_the_read_limit(
    store: tuple[TosScoreStore, Client],
) -> None:
    instance, client = store
    with pytest.raises(ValueError, match="too large"):
        instance.write("cn-beijing", "s-review-1", ScoreJob(error="x" * (512 * 1024)))
    assert client.calls == []


@pytest.mark.parametrize("operation", ["read", "write"])
def test_missing_etag_fails_instead_of_allowing_unconditional_update(
    store: tuple[TosScoreStore, Client], operation: str
) -> None:
    instance, client = store
    client.response.etag = client.put_etag = ""
    with pytest.raises(ValueError, match="ETag"):
        if operation == "read":
            instance.read("cn-beijing", "s-review-1")
        else:
            instance.write("cn-beijing", "s-review-1", ScoreJob())


@pytest.mark.parametrize(
    "identifier", ["", "../other", "s/review", "a.json?x=1", "a" * 129]
)
def test_application_id_cannot_escape_score_prefix(identifier: str) -> None:
    with pytest.raises(ValueError, match="application ID"):
        TosScoreStore._key("studio", identifier)


def test_location_uses_existing_bucket_and_normalizes_prefix(
    store: tuple[TosScoreStore, Client],
) -> None:
    instance, client = store
    assert instance.location("cn-beijing", "s-review-1") == (
        "private-skills",
        "studio/skills/review-scores/s-review-1.json",
    )
    assert TosScoreStore._key("/", "s-review-1") == "review-scores/s-review-1.json"
    assert client.calls == []


def test_public_job_hides_internal_lease_and_attempts() -> None:
    job = ScoreJob(status="running", attempts=2, leaseUntil=123456)
    assert job.public() == {"status": "running"}


@pytest.mark.parametrize(
    ("provider", "region", "endpoint"),
    [
        ("volcengine", "cn-beijing", "tos-cn-beijing.volces.com"),
        ("byteplus", "ap-southeast-1", "tos-ap-southeast-1.bytepluses.com"),
    ],
)
def test_persisted_location_survives_bucket_and_prefix_configuration_changes(
    monkeypatch: pytest.MonkeyPatch,
    provider: storage.StudioProvider,
    region: str,
    endpoint: str,
) -> None:
    from agentkit.toolkit.config import GlobalConfigManager

    configuration = {"bucket": "old-private-skills", "prefix": "old-prefix"}
    credentials = object()
    clients = []
    client = Client()
    expected = ScoreJob(status="failed", attempts=2, error="Original model failure")
    client.response = ReadResponse(expected.model_dump_json().encode())

    def resolve(**kwargs: Any) -> storage.SkillPublishStorage:
        assert kwargs["region"] == region
        return storage.SkillPublishStorage(
            provider=provider,
            region=region,
            endpoint=endpoint,
            bucket=configuration["bucket"],
            prefix=configuration["prefix"],
            bucket_mode="config",
        )

    def create(config: storage.SkillPublishStorage, auth: object) -> Client:
        clients.append((config, auth))
        return client

    monkeypatch.setattr(
        GlobalConfigManager,
        "load",
        lambda _: SimpleNamespace(tos=SimpleNamespace(bucket="", prefix="")),
    )
    monkeypatch.setattr(storage, "resolve_skill_publish_storage", resolve)
    monkeypatch.setattr(
        storage, "resolve_skill_publish_credentials", lambda **_: credentials
    )
    monkeypatch.setattr(storage, "_create_tos_client", create)
    default_store = TosScoreStore()
    old_bucket, old_key = default_store.location(region, "s-review-1")
    bound_store = default_store.for_location(old_bucket, old_key, "s-review-1")
    assert bound_store is not default_store

    configuration.update(bucket="new-private-skills", prefix="new-prefix")
    assert default_store.location(region, "s-review-1") == (
        "new-private-skills",
        "new-prefix/review-scores/s-review-1.json",
    )
    assert bound_store.location(region, "s-review-1") == (old_bucket, old_key)
    job, etag = bound_store.read(region, "s-review-1")
    assert job == expected
    bound_store.write(region, "s-review-1", ScoreJob(), etag)
    assert all(call[1]["bucket"] == old_bucket for call in client.calls)
    assert all(call[1]["key"] == old_key for call in client.calls)
    assert client.calls[-1][1]["if_match"] == etag
    assert all(config.provider == provider for config, _ in clients)
    assert all(config.region == region for config, _ in clients)
    assert all(config.endpoint == endpoint for config, _ in clients)
    assert all(auth is credentials for _, auth in clients)


@pytest.mark.parametrize(
    "bucket",
    [
        "",
        "ab",
        "a" * 64,
        "Uppercase",
        "with_underlines",
        "with.dots",
        "-start",
        "end-",
        "https://bucket",
        "bucket/other",
    ],
)
def test_bound_location_rejects_invalid_bucket_names(bucket: str) -> None:
    with pytest.raises(ValueError, match="bucket"):
        TosScoreStore().for_location(
            bucket, "review-scores/s-review-1.json", "s-review-1"
        )


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/review-scores/s-review-1.json",
        "../review-scores/s-review-1.json",
        "a/../review-scores/s-review-1.json",
        "a/./review-scores/s-review-1.json",
        "a//review-scores/s-review-1.json",
        "C:/review-scores/s-review-1.json",
        "a\\review-scores/s-review-1.json",
        "a\x00/review-scores/s-review-1.json",
        "a\n/review-scores/s-review-1.json",
        "wrong-review-scores/s-review-1.json",
        "review-scores/s-other.json",
        "review-scores/s-review-1.json/extra",
        "review-scores/s-review-1.json?query=value",
        "a" * 1024 + "/review-scores/s-review-1.json",
    ],
)
def test_bound_location_rejects_unsafe_or_mismatched_object_keys(key: str) -> None:
    with pytest.raises(ValueError, match="key"):
        TosScoreStore().for_location("valid-bucket", key, "s-review-1")


def completed_job(application_id: str) -> ScoreJob:
    report = SkillAssessmentReport.model_validate(
        {
            "applicationId": application_id,
            "skillName": "test",
            "skillVersion": "v3",
            "provider": "volcengine",
            "modelName": "planner",
            "rubricVersion": "1",
            "scoredAt": "2026-09-11T12:00:00Z",
            "overallScore": 80,
            "dimensions": {
                name: {"score": 80, "reason": "SKILL.md 有输入输出说明"}
                for name in (
                    "safety",
                    "usability",
                    "completeness",
                    "reliability",
                    "maintainability",
                )
            },
            "riskFlags": [],
            "suggestions": [],
            "coverage": {
                "complete": True,
                "totalFiles": 1,
                "includedFiles": 1,
                "omittedFiles": [],
                "truncatedFiles": [],
            },
        }
    )
    return ScoreJob(status="completed", attempts=1, result=report)


def test_read_rejects_report_for_another_application_and_closes_stream(
    store: tuple[TosScoreStore, Client],
) -> None:
    instance, client = store
    client.response = ReadResponse(completed_job("s-other").model_dump_json().encode())
    with pytest.raises(ValueError, match="another review application"):
        instance.read("cn-beijing", "s-review-1")
    assert client.response.closed


def test_write_rejects_report_for_another_application_before_cloud_write(
    store: tuple[TosScoreStore, Client],
) -> None:
    instance, client = store
    with pytest.raises(ValueError, match="another review application"):
        instance.write("cn-beijing", "s-review-1", completed_job("s-other"))
    assert client.calls == []


@pytest.mark.parametrize("operation", ["location", "read", "write"])
def test_bound_location_cannot_be_reused_for_another_application(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    bound = TosScoreStore().for_location(
        "valid-bucket", "prefix/review-scores/s-review-1.json", "s-review-1"
    )
    client = Client()
    monkeypatch.setattr(
        bound,
        "_storage",
        lambda _: (SimpleNamespace(bucket="valid-bucket", prefix=""), object()),
    )
    monkeypatch.setattr(storage, "_create_tos_client", lambda *_: client)
    with pytest.raises(ValueError, match="another application"):
        if operation == "write":
            bound.write("cn-beijing", "s-other", ScoreJob())
        elif operation == "read":
            bound.read("cn-beijing", "s-other")
        else:
            bound.location("cn-beijing", "s-other")
    assert client.calls == []
