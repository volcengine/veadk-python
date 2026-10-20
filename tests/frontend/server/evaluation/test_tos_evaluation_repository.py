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

import hashlib
import io
import json
from types import SimpleNamespace
from threading import Lock
from typing import Literal
from unittest.mock import MagicMock

import pytest

from frontend.server.evaluation.models import Sample
from frontend.server.evaluation.repository import (
    EvaluationError,
    EvaluationStorage,
    TosEvaluationRepository,
    sample_id,
)


class StorageFailure(Exception):
    def __init__(self, status):
        self.status_code = status


class FakeTos:
    def __init__(self):
        self.objects = {}
        self.lock = Lock()

    def put_object(
        self,
        *,
        bucket,
        key,
        content,
        content_type,
        forbid_overwrite=False,
        if_match=None,
    ):
        with self.lock:
            old = self.objects.get(key)
            if (forbid_overwrite and old) or (
                if_match and (not old or old[1] != if_match)
            ):
                raise StorageFailure(412)
            etag = hashlib.sha256(content).hexdigest()
            self.objects[key] = (content, etag)
            return SimpleNamespace(etag=etag)

    def get_object(self, *, bucket, key):
        if key not in self.objects:
            raise StorageFailure(404)
        data, etag = self.objects[key]
        return SimpleNamespace(read=io.BytesIO(data).read, etag=etag)

    def list_objects_type2(self, *, bucket, prefix, continuation_token, max_keys):
        keys = sorted(key for key in self.objects if key.startswith(prefix))
        start = int(continuation_token or 0)
        end = start + 2  # Deliberately exercise pagination
        return SimpleNamespace(
            contents=[SimpleNamespace(key=key) for key in keys[start:end]],
            is_truncated=end < len(keys),
            next_continuation_token=str(end),
        )


@pytest.fixture
def storage():
    client = FakeTos()
    return client, TosEvaluationRepository("bucket", lambda: client, "runtime")


def sample(
    identifier="message", source: Literal["user", "auto"] = "user", collection="good"
):
    return Sample(
        id=identifier,
        evaluationSetId=collection,
        source=source,
        kind="good",
        input="问题",
        output="回答",
        userId="user",
        sessionId="session",
        messageId="message",
    )


@pytest.mark.asyncio
async def test_two_defaults_contain_both_sources_and_isolate_runtimes(storage):
    client, repo = storage
    await repo.ensure_defaults()
    await repo.save_feedback(sample())
    await repo.save_automatic(sample("automatic", "auto"))
    assert {row.id for row in await repo.list_sets()} == {"good", "bad"}
    assert {row.source for row in await repo.list_samples()} == {"user", "auto"}
    other = TosEvaluationRepository("bucket", lambda: client, "other")
    assert await other.list_samples() == []
    for key, (content, _) in client.objects.items():
        assert key.startswith("veadk-studio/v1/evaluation/runtime/")
        assert "appName" not in json.loads(content)


@pytest.mark.asyncio
async def test_custom_set_rename_move_and_stale_edit(storage):
    _, repo = storage
    custom = await repo.create_set("回归", "说明", "owner")
    row = await repo.save_sample(sample(collection=custom.id))
    renamed = await repo.update_set(custom.id, "回归二", "更新", custom.revision)
    assert renamed.id == custom.id
    with pytest.raises(EvaluationError, match="数据已被修改"):
        await repo.update_set(custom.id, "过期修改", "", custom.revision)
    await repo.ensure_defaults()
    moved = await repo.save_sample(
        row.model_copy(update={"evaluation_set_id": "bad"}), row.revision
    )
    assert moved.kind == "bad"
    assert len(await repo.list_samples()) == 1
    with pytest.raises(EvaluationError):
        await repo.delete_sample(row.id, row.revision)
    assert await repo.delete_sample(row.id, moved.revision)


@pytest.mark.asyncio
async def test_deleted_auto_sample_and_set_do_not_reappear(storage):
    client, repo = storage
    await repo.ensure_defaults()
    row = await repo.save_automatic(sample(source="auto"))
    await repo.delete_sample(row.id, row.revision)
    assert await repo.save_automatic(sample(source="auto")) is None
    assert "回答" not in client.objects[repo._key("samples", row.id)][0].decode()
    collection = await repo.get_set("good")
    await repo.delete_set("good", collection.revision)
    with pytest.raises(EvaluationError, match="评测集不存在"):
        await repo.save_feedback(sample("new"))
    assert {row.id for row in await repo.list_sets()} == {"bad"}


@pytest.mark.asyncio
async def test_feedback_reclassification_updates_one_sample(storage):
    _, repo = storage
    await repo.save_feedback(sample())
    await repo.save_feedback(sample(collection="bad"))
    rows = await repo.list_samples()
    assert len(rows) == 1
    assert rows[0].evaluation_set_id == "bad"
    await repo.delete_sample(rows[0].id)
    assert await repo.list_samples() == []
    await repo.save_feedback(sample())
    assert len(await repo.list_samples()) == 1


def test_id_includes_user_and_source_without_app_or_project():
    assert sample_id("user", "u", "s", "m") != sample_id("auto", "u", "s", "m")
    assert sample_id("user", "u", "s", "m") != sample_id("user", "other", "s", "m")


@pytest.mark.asyncio
async def test_feedback_state_clears_after_sample_or_set_deletion(storage):
    _, repo = storage
    identifier = sample_id("user", "user", "session", "message")
    row = await repo.save_feedback(sample(identifier))
    states = await repo.feedback_states("user", "session", ["message"])
    assert states["veadk_feedback:message"]["rating"] == "good"
    await repo.delete_sample(identifier, row.revision)
    assert (await repo.feedback_states("user", "session", ["message"]))[
        "veadk_feedback:message"
    ]["rating"] is None
    await repo.save_feedback(sample(identifier))
    collection = await repo.get_set("good")
    await repo.delete_set("good", collection.revision)
    assert (await repo.feedback_states("user", "session", ["message"]))[
        "veadk_feedback:message"
    ]["rating"] is None


def test_native_routes_support_custom_sets_and_enforce_runtime_access(storage):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from frontend.server.evaluation.routes import mount_routes

    backend, _ = storage
    app = FastAPI()

    def authorize(request, runtime_id, region, shared=False):
        if runtime_id != "runtime":
            raise HTTPException(404, "not found")
        return SimpleNamespace()

    async def runtime_request(*args, **kwargs):
        if kwargs["method"] == "PATCH":
            return {}
        return {
            "id": "session",
            "events": [
                {
                    "id": "question",
                    "author": "user",
                    "content": {"parts": [{"text": "问题"}]},
                },
                {
                    "id": "message",
                    "author": "agent",
                    "content": {"parts": [{"text": "回答"}]},
                },
            ],
        }

    mount_routes(
        app,
        storage=MagicMock(
            spec=EvaluationStorage,
            for_runtime=lambda runtime_id: TosEvaluationRepository(
                "bucket", lambda: backend, runtime_id
            ),
        ),
        authorize=authorize,
        principal=lambda request: SimpleNamespace(
            owner_id="user", identifiers={"user"}
        ),
        runtime_request=runtime_request,
        normalize_region=lambda region: region or "cn-beijing",
    )
    client = TestClient(app)
    suffix = "?runtimeId=runtime"
    assert client.get("/web/evaluation/sets?runtimeId=other").status_code == 404
    created = client.post(
        "/web/evaluation/sets" + suffix, json={"name": "自定义", "description": "描述"}
    )
    assert created.status_code == 201
    collection = created.json()
    value = {"evaluationSetId": collection["id"], "input": "问题", "output": "回答"}
    response = client.post("/web/evaluation/samples" + suffix, json=value)
    assert response.status_code == 201
    row = response.json()
    assert row["source"] == "user"
    assert "appName" not in row
    edit = {**value, "output": "修改", "revision": row["revision"]}
    assert (
        client.patch(
            f"/web/evaluation/samples/{row['id']}" + suffix, json=edit
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/web/evaluation/samples/{row['id']}" + suffix, json=edit
        ).status_code
        == 409
    )
    assert (
        client.get("/web/evaluation/samples" + suffix + "&q=修改").json()["total"] == 1
    )
    assert client.get("/web/evaluation/samples" + suffix + "&page=0").status_code == 422
    payload = {
        "runtimeId": "runtime",
        "appName": "agent",
        "userId": "user",
        "sessionId": "session",
        "eventId": "message",
        "rating": "good",
    }
    assert client.post("/web/evaluation/feedback", json=payload).status_code == 200
    assert (
        client.post(
            "/web/evaluation/feedback", json={**payload, "rating": "bad"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/web/evaluation/feedback", json={**payload, "userId": "other"}
        ).status_code
        == 403
    )
    assert len(client.get("/web/evaluation/sets" + suffix).json()["items"]) == 3
    assert (
        client.post(
            "/web/evaluation/feedback", json={**payload, "rating": None}
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/web/evaluation/sets/{collection['id']}"
            + suffix
            + "&revision="
            + collection["revision"]
        ).status_code
        == 200
    )
    assert client.get("/web/evaluation/samples" + suffix).json()["total"] == 0


@pytest.mark.asyncio
async def test_session_response_overrides_stale_feedback_without_frontend_changes(
    storage,
):
    from frontend.server.evaluation.sessions import enrich_session, session_identity

    _, repo = storage
    service = MagicMock(
        spec=EvaluationStorage, factory=True, for_runtime=lambda runtime_id: repo
    )
    identifier = sample_id("user", "user", "session", "message")
    row = await repo.save_feedback(sample(identifier))
    original = {
        "state": {"custom": 1, "veadk_feedback:message": {"rating": "bad"}},
        "events": [{"id": "message", "author": "agent"}],
    }
    assert session_identity("apps/agent/users/user/sessions/session") == (
        "user",
        "session",
    )
    assert session_identity("apps/agent/users/user/sessions") is None
    assert session_identity("apps/agent/users/user/sessions/session/events") is None
    result = await enrich_session(service, "runtime", ("user", "session"), original)
    assert result["state"]["custom"] == 1
    assert result["state"]["veadk_feedback:message"]["rating"] == "good"
    await repo.delete_sample(row.id, row.revision)
    result = await enrich_session(service, "runtime", ("user", "session"), original)
    assert result["state"]["veadk_feedback:message"]["rating"] is None
    assert original["state"]["veadk_feedback:message"]["rating"] == "bad"
