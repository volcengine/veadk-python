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

"""Unit tests for ``RemoteVeAgent``.

All network access (the agent-card fetch via ``requests.get``) and the parent
``RemoteA2aAgent`` runtime are mocked. We exercise URL resolution, auth-header /
query-string construction, error paths, and runtime token injection.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from veadk.a2a.remote_ve_agent import (
    AGENT_CARD_WELL_KNOWN_PATH,
    RemoteVeAgent,
    _convert_agent_card_dict_to_obj,
)

MODULE = "veadk.a2a.remote_ve_agent"


def _agent_card_dict():
    return {
        "capabilities": {},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "description": "desc",
        "name": "demo",
        "url": "http://placeholder",
        "version": "1.0",
        "skills": [],
    }


@pytest.fixture
def mock_requests_get():
    """Patch requests.get so the constructor never hits the network."""
    with patch(f"{MODULE}.requests.get") as get:
        response = Mock()
        response.json.return_value = _agent_card_dict()
        get.return_value = response
        yield get


def test_convert_agent_card_dict_to_obj():
    obj = _convert_agent_card_dict_to_obj(_agent_card_dict())
    assert obj.name == "demo"
    assert obj.url == "http://placeholder"


def test_well_known_path_constant():
    assert AGENT_CARD_WELL_KNOWN_PATH == "/.well-known/agent-card.json"


def test_init_with_url_fetches_card_and_overrides_url(mock_requests_get):
    agent = RemoteVeAgent(name="a1", url="http://host:8000")

    # Card fetched from the well-known path on the supplied URL.
    mock_requests_get.assert_called_once_with(
        "http://host:8000" + AGENT_CARD_WELL_KNOWN_PATH,
        headers={},
        params={},
    )
    assert agent.name == "a1"
    # The fetched card's url is overridden with the effective URL.
    assert str(agent._agent_card.url) == "http://host:8000"
    # No client supplied -> we created one and must own its cleanup.
    assert agent._httpx_client_needs_cleanup is True


def test_init_no_url_no_client_raises(mock_requests_get):
    with pytest.raises(ValueError, match="Could not determine agent URL"):
        RemoteVeAgent(name="a1")


def test_init_conflicting_url_and_client_base_url_raises(mock_requests_get):
    client = httpx.AsyncClient(base_url="http://other:9000")
    with pytest.raises(ValueError, match="conflicts with the `base_url`"):
        RemoteVeAgent(name="a1", url="http://host:8000", httpx_client=client)


def test_init_unsupported_auth_method_raises(mock_requests_get):
    with pytest.raises(ValueError, match="Unsupported auth method"):
        RemoteVeAgent(
            name="a1",
            url="http://host:8000",
            auth_token="tok",
            auth_method="cookie",  # type: ignore[arg-type]
        )


def test_init_header_auth_sends_bearer_header(mock_requests_get):
    agent = RemoteVeAgent(
        name="a1",
        url="http://host:8000",
        auth_token="tok",
        auth_method="header",
    )
    _, kwargs = mock_requests_get.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer tok"}
    assert kwargs["params"] == {}
    assert agent.auth_method == "header"


def test_init_querystring_auth_sends_token_param(mock_requests_get):
    agent = RemoteVeAgent(
        name="a1",
        url="http://host:8000",
        auth_token="tok",
        auth_method="querystring",
    )
    _, kwargs = mock_requests_get.call_args
    assert kwargs["params"] == {"token": "tok"}
    assert kwargs["headers"] == {}
    assert agent.auth_method == "querystring"


def test_init_with_provided_client_does_not_set_cleanup_flag(mock_requests_get):
    client = httpx.AsyncClient(base_url="http://host:8000")
    agent = RemoteVeAgent(name="a1", httpx_client=client)
    # Parent sets cleanup False when a client is passed; we only override when
    # we created the client ourselves.
    assert agent._httpx_client_needs_cleanup is False


def test_init_provided_client_gets_header_auth_injected(mock_requests_get):
    client = httpx.AsyncClient(base_url="http://host:8000")
    RemoteVeAgent(
        name="a1",
        httpx_client=client,
        auth_token="tok",
        auth_method="header",
    )
    assert client.headers["Authorization"] == "Bearer tok"


def test_init_provided_client_gets_querystring_auth_injected(mock_requests_get):
    client = httpx.AsyncClient(base_url="http://host:8000")
    RemoteVeAgent(
        name="a1",
        httpx_client=client,
        auth_token="tok",
        auth_method="querystring",
    )
    assert client.params.get("token") == "tok"


def test_init_url_trailing_slash_matches_client_base_url(mock_requests_get):
    # A trailing slash on url must not be treated as a conflict.
    client = httpx.AsyncClient(base_url="http://host:8000")
    agent = RemoteVeAgent(name="a1", url="http://host:8000/", httpx_client=client)
    assert agent.name == "a1"


def _make_agent(mock_requests_get):
    return RemoteVeAgent(name="a1", url="http://host:8000")


@pytest.mark.asyncio
async def test_pre_run_calls_resolve_and_inject(mock_requests_get):
    agent = _make_agent(mock_requests_get)
    ctx = Mock()
    with (
        patch.object(agent, "_ensure_resolved", new=AsyncMock()) as resolve,
        patch.object(agent, "_inject_auth_token", new=AsyncMock()) as inject,
    ):
        await agent._pre_run(ctx)
    resolve.assert_awaited_once_with()
    inject.assert_awaited_once_with(ctx)


@pytest.mark.asyncio
async def test_inject_auth_token_skips_without_credential_service(mock_requests_get):
    agent = _make_agent(mock_requests_get)
    ctx = Mock()
    ctx.credential_service = None
    # Should return early without touching any client.
    await agent._inject_auth_token(ctx)


@pytest.mark.asyncio
async def test_inject_auth_token_skips_when_client_not_base_client(mock_requests_get):
    agent = _make_agent(mock_requests_get)
    ctx = Mock()
    ctx.credential_service = Mock()
    # A freshly constructed agent has _a2a_client = None (not a BaseClient),
    # so injection must short-circuit without loading any credential.
    from a2a.client.base_client import BaseClient

    assert not isinstance(getattr(agent, "_a2a_client", None), BaseClient)
    await agent._inject_auth_token(ctx)
    ctx.credential_service.load_credential.assert_not_called()


def _attach_fake_a2a_client(agent):
    """Give the agent an _a2a_client that passes the isinstance(BaseClient) and
    transport/httpx_client guards in _inject_auth_token."""
    from a2a.client.base_client import BaseClient

    class _FakeClient(BaseClient):
        def __init__(self):  # noqa: D401 - bypass BaseClient.__init__
            pass

    client = _FakeClient()
    transport = Mock()
    transport.httpx_client = httpx.AsyncClient(base_url="http://host:8000")
    client._transport = transport  # type: ignore[attr-defined]
    agent._a2a_client = client
    return transport.httpx_client


@pytest.mark.asyncio
async def test_inject_auth_token_header_path(mock_requests_get):
    agent = RemoteVeAgent(
        name="a1", url="http://host:8000", auth_token="t", auth_method="header"
    )
    httpx_client = _attach_fake_a2a_client(agent)

    ctx = Mock()
    tip_cred = Mock(api_key="tip-key")
    inbound_cred = Mock(api_key="inbound-key")
    ctx.credential_service.load_credential = AsyncMock(
        side_effect=[tip_cred, inbound_cred]
    )

    with (
        patch(f"{MODULE}.generate_headers", return_value={"Authorization": "Bearer X"}),
        patch("veadk.utils.auth.build_auth_config", return_value=Mock()),
        patch("google.adk.agents.callback_context.CallbackContext"),
    ):
        await agent._inject_auth_token(ctx)

    # TIP token header injected, plus the bearer header from generate_headers.
    assert httpx_client.headers["Authorization"] == "Bearer X"
    assert ctx.credential_service.load_credential.await_count == 2


@pytest.mark.asyncio
async def test_inject_auth_token_querystring_path(mock_requests_get):
    agent = RemoteVeAgent(
        name="a1", url="http://host:8000", auth_token="t", auth_method="querystring"
    )
    httpx_client = _attach_fake_a2a_client(agent)

    ctx = Mock()
    tip_cred = Mock(api_key="tip-key")
    inbound_cred = Mock(api_key="inbound-key")
    ctx.credential_service.load_credential = AsyncMock(
        side_effect=[tip_cred, inbound_cred]
    )

    with (
        patch("veadk.utils.auth.build_auth_config", return_value=Mock()),
        patch("google.adk.agents.callback_context.CallbackContext"),
    ):
        await agent._inject_auth_token(ctx)

    assert httpx_client.params.get("token") == "inbound-key"


@pytest.mark.asyncio
async def test_inject_auth_token_no_credential_returns_early(mock_requests_get):
    agent = RemoteVeAgent(name="a1", url="http://host:8000", auth_method="header")
    httpx_client = _attach_fake_a2a_client(agent)

    ctx = Mock()
    # First load (TIP) returns None, second (inbound) returns None -> no header.
    ctx.credential_service.load_credential = AsyncMock(side_effect=[None, None])

    with (
        patch("veadk.utils.auth.build_auth_config", return_value=Mock()),
        patch("google.adk.agents.callback_context.CallbackContext"),
        patch(f"{MODULE}.generate_headers") as gen_headers,
    ):
        await agent._inject_auth_token(ctx)

    # No inbound credential -> generate_headers never invoked.
    gen_headers.assert_not_called()
    assert "Authorization" not in httpx_client.headers


@pytest.mark.asyncio
async def test_inject_auth_token_skips_when_transport_missing(mock_requests_get):
    from a2a.client.base_client import BaseClient

    class _FakeClient(BaseClient):
        def __init__(self):
            pass

    agent = RemoteVeAgent(name="a1", url="http://host:8000", auth_method="header")
    client = _FakeClient()
    # No _transport attribute -> guard must short-circuit.
    agent._a2a_client = client
    ctx = Mock()
    ctx.credential_service = Mock()
    await agent._inject_auth_token(ctx)
    ctx.credential_service.load_credential.assert_not_called()


@pytest.mark.asyncio
async def test_inject_auth_token_swallows_exceptions(mock_requests_get):
    agent = RemoteVeAgent(name="a1", url="http://host:8000", auth_method="header")
    _attach_fake_a2a_client(agent)

    ctx = Mock()
    ctx.credential_service.load_credential = AsyncMock(
        side_effect=RuntimeError("creds down")
    )

    with (
        patch("veadk.utils.auth.build_auth_config", return_value=Mock()),
        patch("google.adk.agents.callback_context.CallbackContext"),
    ):
        # Must not raise: the method logs a warning and returns.
        await agent._inject_auth_token(ctx)


@pytest.mark.asyncio
async def test_run_async_impl_wrapper_yields_error_on_pre_run_failure(
    mock_requests_get,
):
    agent = _make_agent(mock_requests_get)
    ctx = Mock()
    ctx.invocation_id = "inv1"
    ctx.branch = "main"

    with patch.object(
        agent, "_pre_run", new=AsyncMock(side_effect=RuntimeError("boom"))
    ):
        events = [event async for event in agent._run_async_impl(ctx)]

    assert len(events) == 1
    assert events[0].author == "a1"
    assert "Failed to initialize remote A2A agent" in (events[0].error_message or "")
    assert "boom" in (events[0].error_message or "")


@pytest.mark.asyncio
async def test_run_async_impl_wrapper_passes_through_events(mock_requests_get):
    agent = _make_agent(mock_requests_get)
    ctx = Mock()
    ctx.invocation_id = "inv1"
    ctx.branch = "main"

    sentinel = Mock(name="event")

    async def fake_original(_ctx):
        yield sentinel

    # Re-wrap with a controllable original impl to prove pass-through.
    with patch.object(agent, "_pre_run", new=AsyncMock()):
        agent._run_async_impl = fake_original  # type: ignore[method-assign]
        agent._wrap_run_async_impl()
        events = [event async for event in agent._run_async_impl(ctx)]

    assert events == [sentinel]


def test_agent_card_url_override_is_serialized(mock_requests_get):
    # Sanity: the dict mutation in __init__ (agent_card_dict["url"] = url) takes
    # effect through json round-trip rather than the placeholder.
    card = _agent_card_dict()
    card["url"] = "http://placeholder"
    obj = _convert_agent_card_dict_to_obj({**card, "url": "http://real:1"})
    assert json.loads(obj.model_dump_json())["url"] == "http://real:1"
