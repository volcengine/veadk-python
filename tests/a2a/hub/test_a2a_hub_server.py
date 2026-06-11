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

"""Behavioral tests for ``A2AHubServer``.

Drives the FastAPI app through ``TestClient`` (no network / no uvicorn) to pin
the register/lookup routing logic and the in-memory group/agent bookkeeping.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from veadk.a2a.hub.a2a_hub_server import A2AHubServer


@pytest.fixture
def client():
    server = A2AHubServer()
    return TestClient(server.app)


def test_initial_state_empty():
    server = A2AHubServer()
    assert server.groups == []
    assert server.agent_cards == {}


def test_ping(client):
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.json() == {"msg": "pong!"}


def test_create_group_adds_group_and_empty_card_map(client):
    resp = client.post("/create_group", params={"group_id": "g1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["group_id"] == "g1"
    assert body["err_code"] == 0
    # subsequent /groups lookup reflects the new group.
    groups = client.get("/groups").json()
    assert groups["group_ids"] == ["g1"]


def test_register_agent_into_missing_group_errors(client):
    resp = client.post(
        "/register_agent",
        json={"group_id": "ghost", "agent_id": "a1", "agent_card": {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["err_code"] == 1
    assert "not exist" in body["msg"]


def test_register_agent_success(client):
    client.post("/create_group", params={"group_id": "g1"})
    card = {"name": "demo", "url": "http://x"}
    resp = client.post(
        "/register_agent",
        json={"group_id": "g1", "agent_id": "a1", "agent_card": card},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["err_code"] == 0
    assert body["group_id"] == "g1"
    assert body["agent_id"] == "a1"
    assert body["agent_card"] == card


def test_register_duplicate_agent_errors(client):
    client.post("/create_group", params={"group_id": "g1"})
    payload = {"group_id": "g1", "agent_id": "a1", "agent_card": {}}
    client.post("/register_agent", json=payload)
    resp = client.post("/register_agent", json=payload)
    body = resp.json()
    assert body["err_code"] == 1
    assert "already exist" in body["msg"]


def test_get_agents_for_missing_group_errors(client):
    body = client.get("/group/ghost/agents").json()
    assert body["err_code"] == 1
    assert "not exist" in body["msg"]


def test_get_agents_returns_registered_agents(client):
    client.post("/create_group", params={"group_id": "g1"})
    client.post(
        "/register_agent",
        json={"group_id": "g1", "agent_id": "a1", "agent_card": {"x": 1}},
    )
    client.post(
        "/register_agent",
        json={"group_id": "g1", "agent_id": "a2", "agent_card": {"y": 2}},
    )
    body = client.get("/group/g1/agents").json()
    assert body["err_code"] == 0
    assert body["group_id"] == "g1"
    ids = {a["agent_id"] for a in body["agent_infos"]}
    assert ids == {"a1", "a2"}


def test_get_single_agent_missing_group(client):
    body = client.get("/group/ghost/agent/a1").json()
    assert body["err_code"] == 1
    assert "group ghost not exist" in body["msg"]


def test_get_single_agent_missing_agent(client):
    client.post("/create_group", params={"group_id": "g1"})
    body = client.get("/group/g1/agent/ghost").json()
    assert body["err_code"] == 1
    assert "agent ghost in group g1 not exist" in body["msg"]


def test_get_single_agent_success(client):
    client.post("/create_group", params={"group_id": "g1"})
    card = {"name": "demo"}
    client.post(
        "/register_agent",
        json={"group_id": "g1", "agent_id": "a1", "agent_card": card},
    )
    body = client.get("/group/g1/agent/a1").json()
    assert body["err_code"] == 0
    assert body["agent_id"] == "a1"
    assert body["agent_card"] == card


def test_groups_empty_initially(client):
    assert client.get("/groups").json()["group_ids"] == []


def test_serve_delegates_to_uvicorn_run():
    server = A2AHubServer()
    with patch("veadk.a2a.hub.a2a_hub_server.uvicorn.run") as mock_run:
        server.serve(host="0.0.0.0", port=1234)
    mock_run.assert_called_once_with(server.app, host="0.0.0.0", port=1234)
