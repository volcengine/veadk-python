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

import copy
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from frontend.service.studio_release_notifier.app import (
    Release,
    app,
    broadcast,
    build_card,
)


class MemoryStore:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return copy.deepcopy(self.values.get(key))

    def put(self, key, value, *, create=False):
        if create and key in self.values:
            return False
        self.values[key] = copy.deepcopy(value)
        return True


class Bot:
    def __init__(self):
        self.sent = []
        self.fail = {"oc_b"}

    def groups(self):
        return ["oc_a", "oc_b"]

    def send(self, group, card, uuid):
        if group in self.fail:
            raise RuntimeError("Transient failure")
        self.sent.append((group, uuid))
        return "om_" + group


def release(text="新增功能；优化体验;修复问题;; "):
    return Release(version="20260909160000", date="2026.09.09", changelog=text)


def test_split_and_escape_card():
    value = release(
        "新增功能；优化体验; <at id=all>全体</at>;[链接](https://example.com)"
    )
    assert len(value.changelog) == 4
    card = build_card(value)
    content = card["body"]["elements"][0]["columns"][0]["elements"][1]["content"]
    assert len(content.splitlines()) == 4
    assert "<at" not in content
    assert "[链接]" not in content
    assert "适用环境" not in str(card)


def test_retry_skips_successful_group_and_reuses_uuid():
    bot, store = Bot(), MemoryStore()
    first = broadcast(release(), bot, store)
    assert first["ok"] is False
    bot.fail.clear()
    second = broadcast(release(), bot, store)
    assert second["ok"] is True
    assert [entry[0] for entry in bot.sent] == ["oc_a", "oc_b"]
    broadcast(release(), bot, store)
    assert len(bot.sent) == 2


def test_changed_payload_is_rejected():
    bot, store = Bot(), MemoryStore()
    broadcast(release(), bot, store)
    with pytest.raises(HTTPException) as error:
        broadcast(release("different"), bot, store)
    assert error.value.status_code == 409


def test_old_ambiguous_attempt_is_not_resent():
    bot, store = Bot(), MemoryStore()
    broadcast(release(), bot, store)
    for key, value in store.values.items():
        if key.endswith("oc_b"):
            value["started"] = time.time() - 3601
    bot.fail.clear()
    result = broadcast(release(), bot, store)
    assert result["deliveries"][1]["status"] == "needs_review"
    assert len(bot.sent) == 1


def test_http_auth_and_validation(monkeypatch):
    monkeypatch.setenv("STUDIO_RELEASE_WEBHOOK_KEY", "k" * 40)
    with TestClient(app) as client:
        assert client.post("/release", json={}).status_code == 401
        assert (
            client.post(
                "/release", json={}, headers={"X-API-Key": "k" * 40}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/release", content=b"x" * 32001, headers={"X-API-Key": "k" * 40}
            ).status_code
            == 413
        )


def test_no_groups_does_not_mark_release_delivered():
    bot, store = Bot(), MemoryStore()
    bot.groups = lambda: []
    with pytest.raises(HTTPException) as error:
        broadcast(release(), bot, store)
    assert error.value.status_code == 409
    assert store.values == {}


def test_empty_changelog_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        release(" ;； \n")
