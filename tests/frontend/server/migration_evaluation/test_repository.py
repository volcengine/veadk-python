# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import hashlib
import io
from types import SimpleNamespace

import pytest

from frontend.server.migration.evaluation.repository import (
    EvaluationAssetConflict,
    EvaluationAssetIntegrityError,
    EvaluationAssetStorageUnavailable,
    TosMigrationEvaluationRepository,
    _status_code,
)

TASK_ID = "migration-v1-" + "1" * 32


class TosError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(str(status_code))
        self.status_code = status_code


class FakeTos:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.puts: list[str] = []

    def put_object(
        self, *, key: str, content: bytes, forbid_overwrite: bool, **_kwargs: object
    ) -> None:
        if forbid_overwrite and key in self.objects:
            raise TosError(409)
        self.objects[key] = content
        self.puts.append(key)

    def get_object(self, *, key: str, **_kwargs: object) -> io.BytesIO:
        if key not in self.objects:
            raise TosError(404)
        return io.BytesIO(self.objects[key])

    def delete_object(self, *, key: str, **_kwargs: object) -> SimpleNamespace:
        self.objects.pop(key, None)
        return SimpleNamespace()


class MarkerFailingTos(FakeTos):
    def __init__(self, *, fail_delete: bool) -> None:
        super().__init__()
        self.fail_delete = fail_delete

    def put_object(self, *, key: str, **kwargs: object) -> None:
        if key.endswith("/asset.json"):
            raise RuntimeError("marker write failed")
        super().put_object(key=key, **kwargs)  # type: ignore[arg-type]

    def delete_object(self, *, key: str, **kwargs: object) -> SimpleNamespace:
        if self.fail_delete:
            raise RuntimeError("cleanup failed")
        return super().delete_object(key=key, **kwargs)


def _repository(tos: FakeTos) -> TosMigrationEvaluationRepository:
    return TosMigrationEvaluationRepository(
        bucket="studio",
        client_factory=lambda: tos,
    )


def test_dataset_is_owner_scoped_immutable_and_marker_is_written_last() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    content = b'{"case_id":"one"}\n'
    digest = hashlib.sha256(content).hexdigest()

    metadata = repository.commit_dataset(
        owner_id="owner/a",
        task_id=TASK_ID,
        version_id=digest[:32],
        sha256=digest,
        content=content,
        case_count=1,
        created_at="2026-09-07T10:00:00Z",
    )
    repeated = repository.commit_dataset(
        owner_id="owner/a",
        task_id=TASK_ID,
        version_id=digest[:32],
        sha256=digest,
        content=content,
        case_count=1,
        created_at="2026-09-07T10:00:00Z",
    )

    assert metadata == repeated
    assert "/users/owner%2Fa/migration-evaluations/" in tos.puts[0]
    assert tos.puts[0].endswith("/data.jsonl")
    assert tos.puts[1].endswith("/asset.json")
    loaded, loaded_content = repository.load(
        owner_id="owner/a",
        task_id=TASK_ID,
        kind="dataset",
        version_id=digest[:32],
    )
    assert loaded == metadata
    assert loaded_content == content
    assert loaded.public()["acl"] == "owner"


def test_report_is_a_separate_versioned_asset() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    content = b'{"schema_version":1,"state":"completed"}'
    digest = hashlib.sha256(content).hexdigest()

    metadata = repository.commit_report(
        owner_id="owner",
        task_id=TASK_ID,
        version_id=digest[:32],
        sha256=digest,
        content=content,
        attempt=2,
        created_at="2026-09-07T10:00:00Z",
    )

    assert metadata.kind == "report"
    assert metadata.attempt == 2
    assert any(
        "/reports/" in key and key.endswith("report.json") for key in tos.objects
    )
    assert not any("/datasets/" in key for key in tos.objects)


def test_existing_different_content_is_rejected() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    content = b'{"case_id":"one"}\n'
    digest = hashlib.sha256(content).hexdigest()
    repository.commit_dataset(
        owner_id="owner",
        task_id=TASK_ID,
        version_id=digest[:32],
        sha256=digest,
        content=content,
        case_count=1,
        created_at="2026-09-07T10:00:00Z",
    )
    data_key = next(key for key in tos.objects if key.endswith("data.jsonl"))
    tos.objects[data_key] = b"tampered"

    with pytest.raises(EvaluationAssetConflict):
        repository.commit_dataset(
            owner_id="owner",
            task_id=TASK_ID,
            version_id=digest[:32],
            sha256=digest,
            content=content,
            case_count=1,
            created_at="2026-09-07T10:00:00Z",
        )


def test_load_rejects_tampered_content() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    content = b'{"case_id":"one"}\n'
    digest = hashlib.sha256(content).hexdigest()
    repository.commit_dataset(
        owner_id="owner",
        task_id=TASK_ID,
        version_id=digest[:32],
        sha256=digest,
        content=content,
        case_count=1,
        created_at="2026-09-07T10:00:00Z",
    )
    data_key = next(key for key in tos.objects if key.endswith("data.jsonl"))
    tos.objects[data_key] = b"tampered"

    with pytest.raises(EvaluationAssetIntegrityError):
        repository.load(
            owner_id="owner",
            task_id=TASK_ID,
            kind="dataset",
            version_id=digest[:32],
        )


@pytest.mark.parametrize("fail_delete", [False, True])
def test_failed_marker_write_rolls_back_content_and_logs_cleanup_failure(
    fail_delete: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tos = MarkerFailingTos(fail_delete=fail_delete)
    content = b'{"case_id":"one"}\n'
    digest = hashlib.sha256(content).hexdigest()

    with pytest.raises(EvaluationAssetStorageUnavailable):
        _repository(tos).commit_dataset(
            owner_id="owner",
            task_id=TASK_ID,
            version_id=digest[:32],
            sha256=digest,
            content=content,
            case_count=1,
            created_at="2026-09-07T10:00:00Z",
        )

    content_keys = [key for key in tos.objects if key.endswith("/data.jsonl")]
    assert bool(content_keys) is fail_delete
    assert ("Could not remove uncommitted" in caplog.text) is fail_delete


@pytest.mark.parametrize("attribute", ["status_code", "status", "http_status"])
def test_status_code_recognizes_all_supported_error_attributes(attribute: str) -> None:
    error = RuntimeError("conflict")
    setattr(error, attribute, "409")
    assert _status_code(error) == 409

    wrapped = RuntimeError("wrapped")
    wrapped.__cause__ = error
    assert _status_code(wrapped) == 409
