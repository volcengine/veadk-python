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

"""Run the actual workflow notification script against a mocked HTTP boundary."""

import copy
import io
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

from frontend.service.studio_release_notifier import app as notifier

WORKFLOW = (
    Path(__file__).resolve().parents[4]
    / ".github/workflows/publish-studio-release.yaml"
)


@pytest.fixture
def workflow_script(monkeypatch):
    workflow = yaml.safe_load(WORKFLOW.read_text())
    script = workflow["jobs"]["notify"]["steps"][0]["run"]
    source = script.split("<<'PYTHON'\n", 1)[1].rsplit("PYTHON", 1)[0]
    for name, value in {
        "WEBHOOK_URL": "https://notifier.example/release",
        "WEBHOOK_KEY": "test-key-" * 5,
        "STUDIO_RELEASE_WEBHOOK_KEY": "test-key-" * 5,
        "RELEASE_VERSION": "20260909210000",
        "RELEASE_CHANGELOG": "新增功能；优化体验;修复问题",
    }.items():
        monkeypatch.setenv(name, value)
    return compile(source, str(WORKFLOW) + ":notify", "exec")


def test_notification_is_downstream_of_both_publish_jobs():
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    assert jobs["notify"]["needs"] == ["release-context", "publish"]
    assert "notify" not in jobs["publish"]["needs"]
    assert {
        entry["provider"] for entry in jobs["publish"]["strategy"]["matrix"]["include"]
    } == {"volcengine", "byteplus"}
    # GitHub applies success() by default unless a status function overrides it.
    assert not any(
        token in jobs["notify"]["if"] for token in ("always(", "failure(", "cancelled(")
    )
    assert not jobs["notify"].get("continue-on-error", False)


@pytest.mark.parametrize(
    ("outcomes", "calls", "delays", "success"),
    [
        ([200], 1, [], True),
        ([502, 200], 2, [5], True),
        ([502, 502, 502], 3, [5, 10], False),
        ([429, 200], 2, [5], True),
        ([401], 1, [], False),
        ([409], 1, [], False),
        (["timeout", 200], 2, [5], True),
    ],
)
def test_actual_workflow_retry_policy(
    monkeypatch, workflow_script, outcomes, calls, delays, success
):
    requests, sleeps = [], []

    def urlopen(request, timeout):
        assert timeout == 190
        assert request.full_url == "https://notifier.example/release"
        assert request.get_header("X-api-key") == "test-key-" * 5
        requests.append(json.loads(request.data))
        outcome = outcomes[len(requests) - 1]
        if outcome == "timeout":
            raise urllib.error.URLError("simulated timeout")
        if outcome != 200:
            raise urllib.error.HTTPError(
                request.full_url, outcome, "simulated failure", {}, None
            )
        return io.BytesIO(b'{"ok":true}')

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(time, "sleep", sleeps.append)
    if success:
        exec(workflow_script, {"__name__": "__main__"})
    else:
        with pytest.raises(SystemExit):
            exec(workflow_script, {"__name__": "__main__"})
    assert len(requests) == calls
    assert sleeps == delays
    assert all(payload == requests[0] for payload in requests)
    assert requests[0] == {
        "version": "20260909210000",
        "date": "2026.09.09",
        "changelog": "新增功能；优化体验;修复问题",
    }


@pytest.mark.parametrize("permanent_failure", [False, True])
def test_workflow_through_real_http_handler_and_broadcast(
    monkeypatch, workflow_script, permanent_failure
):
    records, attempts, sent, requests = {}, [], [], []

    class Store:
        def get(self, key):
            return copy.deepcopy(records.get(key))

        def put(self, key, value, *, create=False):
            if create and key in records:
                return False
            records[key] = copy.deepcopy(value)
            return True

    class Bot:
        client = SimpleNamespace(close=lambda: None)

        def groups(self):
            return ["oc_a", "oc_b"]

        def send(self, group, card, uuid):
            attempts.append((group, uuid))
            count = sum(item[0] == "oc_b" for item in attempts)
            if group == "oc_b" and (permanent_failure or count == 1):
                raise RuntimeError("simulated group delivery failure")
            content = card["body"]["elements"][0]["columns"][0]["elements"][1][
                "content"
            ]
            assert content == "- 新增功能\n- 优化体验\n- 修复问题"
            assert "适用环境" not in str(card)
            sent.append(group)
            return "om_" + group

    monkeypatch.setattr(notifier, "Store", Store)
    monkeypatch.setattr(notifier, "Feishu", Bot)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    with TestClient(notifier.app) as client:

        def urlopen(request, timeout):
            requests.append(request.data)
            response = client.post(
                "/release", content=request.data, headers=dict(request.header_items())
            )
            if response.status_code != 200:
                raise urllib.error.HTTPError(
                    request.full_url,
                    response.status_code,
                    "mock gateway",
                    {},
                    io.BytesIO(response.content),
                )
            return io.BytesIO(response.content)

        monkeypatch.setattr(urllib.request, "urlopen", urlopen)
        if permanent_failure:
            with pytest.raises(
                SystemExit, match="Release succeeded, but notification failed"
            ):
                exec(workflow_script, {"__name__": "__main__"})
        else:
            exec(workflow_script, {"__name__": "__main__"})

    assert len(requests) == (3 if permanent_failure else 2)
    assert sent == (["oc_a"] if permanent_failure else ["oc_a", "oc_b"])
    assert len({uuid for group, uuid in attempts if group == "oc_b"}) == 1
    assert sum(bool(record.get("message_id")) for record in records.values()) == len(
        sent
    )
