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

"""Tests for post-deploy verification probes (FR-6, VC-11/VC-12)."""

import httpx

from veadk.integrations.mpa.mpa_verify import (
    VerificationResult,
    verify_instance,
)


def _transport(
    routes: dict[str, int],
    *,
    require_auth: bool = False,
    agent_card_url: str = "https://app.example.com/a2a/jsonrpc",
):
    """Build an httpx MockTransport returning status per path suffix.

    When ``require_auth`` is True, requests without a Bearer Authorization
    header get 401 regardless of the routed status (models a key-auth runtime).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if require_auth and not request.headers.get("authorization", "").startswith(
            "Bearer "
        ):
            return httpx.Response(401)
        for suffix, status in routes.items():
            if request.url.path.endswith(suffix):
                if suffix == "/.well-known/agent-card.json" and status == 200:
                    return httpx.Response(status, json={"url": agent_card_url})
                return httpx.Response(status)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_verify_passes_when_all_probes_ok() -> None:
    """VC-12: health + readiness + agent-card all 200 -> passed."""
    transport = _transport(
        {
            "/health": 200,
            "/readiness": 200,
            "/.well-known/agent-card.json": 200,
        }
    )
    result = verify_instance(
        "https://app.example.com",
        client=httpx.Client(transport=transport),
    )
    assert isinstance(result, VerificationResult)
    assert result.passed is True
    assert result.failures == []


def test_verify_fails_when_readiness_down() -> None:
    """VC-11: readiness non-200 fails the whole verification."""
    transport = _transport(
        {
            "/health": 200,
            "/readiness": 503,
            "/.well-known/agent-card.json": 200,
        }
    )
    result = verify_instance(
        "https://app.example.com",
        client=httpx.Client(transport=transport),
    )
    assert result.passed is False
    assert any("readiness" in f for f in result.failures)


def test_verify_fails_when_agent_card_missing() -> None:
    """VC-11: agent-card 404 fails verification (Studio cannot connect)."""
    transport = _transport(
        {
            "/health": 200,
            "/readiness": 200,
            "/.well-known/agent-card.json": 404,
        }
    )
    result = verify_instance(
        "https://app.example.com",
        client=httpx.Client(transport=transport),
    )
    assert result.passed is False
    assert any("agent-card" in f for f in result.failures)


def test_verify_rejects_stale_or_foreign_agent_card_url() -> None:
    """Studio follows card.url, so a 200 card with a stale URL must fail."""
    routes = {
        "/health": 200,
        "/readiness": 200,
        "/.well-known/agent-card.json": 200,
    }
    stale = verify_instance(
        "https://app.example.com",
        client=httpx.Client(
            transport=_transport(
                routes, agent_card_url="https://<pending-endpoint>:443/a2a/jsonrpc"
            )
        ),
    )
    assert stale.passed is False
    assert any("agent-card-url" in failure for failure in stale.failures)

    foreign = verify_instance(
        "https://app.example.com",
        client=httpx.Client(
            transport=_transport(
                routes, agent_card_url="https://other.example.com/a2a/jsonrpc"
            )
        ),
    )
    assert foreign.passed is False
    assert any("agent-card-url" in failure for failure in foreign.failures)


def test_verify_report_contains_no_secret() -> None:
    """Failure report text must not leak any provided secret material."""
    transport = _transport({"/health": 500, "/readiness": 500})
    result = verify_instance(
        "https://app.example.com",
        client=httpx.Client(transport=transport),
    )
    assert result.passed is False
    # The report summarizes probes/status only; assert no bearer-like tokens.
    text = result.summary()
    assert "Bearer" not in text
    assert "api_key" not in text.lower()


def test_verify_key_auth_runtime_requires_api_key() -> None:
    """A key-auth runtime returns 401 without a key and 200 with it."""
    routes = {
        "/health": 200,
        "/readiness": 200,
        "/.well-known/agent-card.json": 200,
    }
    # Without api_key -> 401 -> fail.
    no_key = verify_instance(
        "https://app.example.com",
        client=httpx.Client(transport=_transport(routes, require_auth=True)),
    )
    assert no_key.passed is False
    assert all(no_key.statuses[label] == 401 for label in no_key.statuses)

    # With api_key -> Bearer header -> 200 -> pass.
    with_key = verify_instance(
        "https://app.example.com",
        api_key="rk-secret",
        client=httpx.Client(transport=_transport(routes, require_auth=True)),
    )
    assert with_key.passed is True
    assert with_key.failures == []
    # The key must not appear in the summary.
    assert "rk-secret" not in with_key.summary()
