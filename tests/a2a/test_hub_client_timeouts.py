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

"""Regression tests: A2A hub/remote-agent HTTP calls must be bounded.

The hub liveness probe deliberately runs on a tighter read budget than the
ordinary calls -- a hub that has gone silent should be reported as down
quickly, not after a full minute.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from a2a.types import AgentCapabilities, AgentCard

from veadk.utils.http_defaults import DEFAULT_CONNECT_TIMEOUT, DEFAULT_HTTP_TIMEOUT


def _agent_card() -> AgentCard:
    return AgentCard(
        name="weather-agent",
        description="Weather agent",
        url="http://127.0.0.1:8000",
        version="1.0.0",
        capabilities=AgentCapabilities(),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[],
    )


def _response(payload: dict | None = None, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload if payload is not None else {}
    return response


def test_health_check_read_budget_is_tighter_than_default() -> None:
    from veadk.a2a.hub.a2a_hub_client import HEALTH_CHECK_TIMEOUT

    assert HEALTH_CHECK_TIMEOUT[0] == DEFAULT_CONNECT_TIMEOUT
    assert HEALTH_CHECK_TIMEOUT[1] < DEFAULT_HTTP_TIMEOUT[1]


def test_health_check_passes_health_check_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.a2a.hub import a2a_hub_client as module

    get = MagicMock(return_value=_response())
    monkeypatch.setattr(module.requests, "get", get)

    module.A2AHubClient(server_host="127.0.0.1", server_port=8888)

    assert get.call_count == 1
    assert get.call_args.kwargs["timeout"] == module.HEALTH_CHECK_TIMEOUT


def test_get_agent_cards_passes_default_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.a2a.hub import a2a_hub_client as module

    get = MagicMock(return_value=_response({"agent_infos": [{"agent_id": "a1"}]}))
    monkeypatch.setattr(module.requests, "get", get)

    client = module.A2AHubClient(server_host="127.0.0.1", server_port=8888)
    assert client.get_agent_cards(group_id="g1") == [{"agent_id": "a1"}]

    # First call is the constructor's health check.
    assert get.call_count == 2
    assert get.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT


def test_register_agent_passes_default_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.a2a.hub import a2a_hub_client as module

    monkeypatch.setattr(module.requests, "get", MagicMock(return_value=_response()))
    post = MagicMock(return_value=_response())
    monkeypatch.setattr(module.requests, "post", post)

    client = module.A2AHubClient(server_host="127.0.0.1", server_port=8888)
    client.register_agent(group_id="g1", agent_id="a1", agent_card=_agent_card())

    assert post.call_count == 1
    assert post.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT


def test_create_group_passes_default_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.a2a.hub import a2a_hub_client as module

    monkeypatch.setattr(module.requests, "get", MagicMock(return_value=_response()))
    post = MagicMock(return_value=_response())
    monkeypatch.setattr(module.requests, "post", post)

    client = module.A2AHubClient(server_host="127.0.0.1", server_port=8888)
    client.create_group(group_id="g1")

    assert post.call_count == 1
    assert post.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT


def test_remote_ve_agent_card_fetch_passes_default_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veadk.a2a import remote_ve_agent as module

    card = _agent_card().model_dump(mode="json", by_alias=True)
    get = MagicMock(return_value=_response(card))
    monkeypatch.setattr(module.requests, "get", get)

    agent = module.RemoteVeAgent(name="weather_agent", url="http://127.0.0.1:8000")

    assert agent.name == "weather_agent"
    assert get.call_count == 1
    assert get.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT
