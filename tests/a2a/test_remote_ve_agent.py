from __future__ import annotations

import asyncio
from unittest.mock import Mock, patch

import pytest
import requests

from veadk.a2a.remote_ve_agent import RemoteVeAgent


def _agent_card(url: str) -> dict:
    return {
        "name": "skill-agent",
        "description": "Skill sandbox agent",
        "url": url,
        "version": "1.0.0",
        "capabilities": {"streaming": True},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [
            {
                "id": "chat",
                "name": "chat",
                "description": "Chat with the skill agent",
                "tags": ["chat"],
            }
        ],
    }


def _build_agent(endpoint: str, card_url: str) -> tuple[RemoteVeAgent, Mock]:
    response = Mock()
    response.json.return_value = _agent_card(card_url)
    with patch("veadk.a2a.remote_ve_agent.requests.get", return_value=response) as get:
        agent = RemoteVeAgent(name="remote", url=endpoint)
    return agent, get


def _close(agent: RemoteVeAgent) -> None:
    asyncio.run(agent._httpx_client.aclose())


def test_remote_agent_preserves_a2a_path_from_agent_card() -> None:
    agent, get = _build_agent("https://sandbox.test", "https://sandbox.test/a2a")
    try:
        assert agent._agent_card.url == "https://sandbox.test/a2a"
        assert get.call_args.args[0] == (
            "https://sandbox.test/.well-known/agent-card.json"
        )
    finally:
        _close(agent)


def test_remote_agent_discovers_root_card_when_url_is_a2a_rpc_path() -> None:
    agent, get = _build_agent("https://sandbox.test/a2a", "https://sandbox.test/a2a")
    try:
        assert get.call_args.args[0] == (
            "https://sandbox.test/.well-known/agent-card.json"
        )
        assert agent._agent_card.url == "https://sandbox.test/a2a"
    finally:
        _close(agent)


def test_remote_agent_preserves_same_origin_session_authorization_query() -> None:
    agent, get = _build_agent(
        "https://sandbox.test/?faasInstanceName=inst&Authorization=key",
        "https://sandbox.test/a2a",
    )
    try:
        assert get.call_args.args[0] == (
            "https://sandbox.test/.well-known/agent-card.json"
        )
        assert get.call_args.kwargs["params"] == {
            "faasInstanceName": "inst",
            "Authorization": "key",
        }
        assert dict(agent._httpx_client.params) == {
            "faasInstanceName": "inst",
            "Authorization": "key",
        }
    finally:
        _close(agent)


def test_remote_agent_does_not_forward_session_query_to_different_origin() -> None:
    agent, _ = _build_agent(
        "https://sandbox.test/?Authorization=key",
        "https://different.test/a2a",
    )
    try:
        assert agent._agent_card.url == "https://different.test/a2a"
        assert "Authorization" not in dict(agent._httpx_client.params)
    finally:
        _close(agent)


def test_remote_agent_keeps_explicit_query_auth_for_different_origin() -> None:
    response = Mock()
    response.json.return_value = _agent_card("https://different.test/a2a")
    with patch("veadk.a2a.remote_ve_agent.requests.get", return_value=response):
        agent = RemoteVeAgent(
            name="remote",
            url="https://sandbox.test",
            auth_token="explicit-token",
            auth_method="querystring",
        )
    try:
        assert dict(agent._httpx_client.params) == {"token": "explicit-token"}
    finally:
        _close(agent)


def test_remote_agent_replaces_loopback_host_but_keeps_card_path() -> None:
    agent, _ = _build_agent("https://sandbox.test", "http://localhost:8000/a2a")
    try:
        assert agent._agent_card.url == "https://sandbox.test/a2a"
    finally:
        _close(agent)


def test_remote_agent_raises_clear_error_for_agent_card_http_failure() -> None:
    response = Mock()
    response.status_code = 503
    response.reason = "Service Unavailable"
    response.raise_for_status.side_effect = requests.HTTPError(response=response)

    with patch("veadk.a2a.remote_ve_agent.requests.get", return_value=response):
        with pytest.raises(
            RuntimeError,
            match="Failed to fetch A2A Agent Card: HTTP 503 Service Unavailable",
        ):
            RemoteVeAgent(name="remote", url="https://sandbox.test")


def test_remote_agent_rejects_invalid_endpoint_scheme() -> None:
    with pytest.raises(ValueError, match="Invalid A2A endpoint URL"):
        RemoteVeAgent(name="remote", url="ftp://sandbox.test")
