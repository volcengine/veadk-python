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

import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.mpa_identity_callback import (
    MpaCallbackTarget,
    MpaIdentityCallbackError,
    MpaRuntimeCredentials,
    RuntimeCallbackResult,
    _call_runtime_callback,
    _parse_runtime_payload,
    _runtime_result_response,
    build_user_pool_hosted_callback_url,
    mount_mpa_identity_callback,
    parse_identity_relay_state,
    parse_mpa_runtime_state,
    select_mpa_runtime,
)


def _state(payload: dict[str, object]) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()
    return encoded.rstrip("=")


def _relay_state(*, target: str = "mi-agent1", **target_metadata: object) -> str:
    return _state(
        {
            "request_id": "request-1",
            "provider_id": "provider-1",
            "request_state": _state(
                {"target": target, "type": "esa", **target_metadata}
            ),
        }
    )


def _runtime_state(*, target: str = "mi-agent1") -> str:
    return _state({"target": target, "type": "esa", "nonce": "nonce-1"})


def test_parse_identity_relay_state_accepts_mpa_target() -> None:
    parsed = parse_identity_relay_state(_relay_state())

    assert parsed is not None
    assert parsed.request_id == "request-1"
    assert parsed.provider_id == "provider-1"
    assert parsed.target == MpaCallbackTarget("mi-agent1")


@pytest.mark.parametrize(
    "state",
    [
        "",
        "not-base64",
        _state({"request_id": "request-1"}),
        _state(
            {
                "request_id": "request-1",
                "provider_id": "provider-1",
                "request_state": "not-base64",
            }
        ),
        _state(
            {
                "request_id": "request-1",
                "provider_id": "provider-1",
                "request_state": _state({"target": "ci-claw1", "is_debug": False}),
            }
        ),
    ],
)
def test_parse_identity_relay_state_rejects_invalid_payloads(state: str) -> None:
    assert parse_identity_relay_state(state) is None


def test_parse_mpa_runtime_state_accepts_mpa_target() -> None:
    assert parse_mpa_runtime_state(_runtime_state()) == MpaCallbackTarget("mi-agent1")


@pytest.mark.parametrize("state", ["", "not-base64", _state({"target": "ci-claw1"})])
def test_parse_mpa_runtime_state_rejects_invalid_payloads(state: str) -> None:
    assert parse_mpa_runtime_state(state) is None


@pytest.mark.parametrize(
    ("connection_type", "expected_path"),
    [
        ("OAuth", "/login/generic_oauth/callback"),
        ("OIDC", "/login/generic_oidc/callback"),
    ],
)
def test_build_user_pool_hosted_callback_url(
    connection_type: str,
    expected_path: str,
) -> None:
    assert (
        build_user_pool_hosted_callback_url(
            "https://pool.example.com/oidc",
            connection_type,
        )
        == f"https://pool.example.com{expected_path}"
    )


@pytest.mark.parametrize(
    ("issuer", "connection_type"),
    [
        ("http://pool.example.com", "OAuth"),
        ("https://127.0.0.1", "OAuth"),
        ("https://pool.exämple.com", "OAuth"),
        ("https://pool.example.com", "SAML"),
    ],
)
def test_build_user_pool_hosted_callback_url_rejects_unsafe_values(
    issuer: str,
    connection_type: str,
) -> None:
    with pytest.raises(ValueError):
        build_user_pool_hosted_callback_url(issuer, connection_type)


def test_select_mpa_runtime_matches_agent_id_only() -> None:
    runtime = SimpleNamespace(
        envs=[
            SimpleNamespace(key="MPA_AGENT_ID", value="mi-agent1"),
            SimpleNamespace(key="MPA_IS_DEBUG_RUNTIME", value="true"),
        ]
    )

    assert select_mpa_runtime(
        [("cn-beijing", runtime)],
        MpaCallbackTarget("mi-agent1"),
    ) == ("cn-beijing", runtime)


@pytest.mark.parametrize("candidates", [[], [("cn-beijing", object())]])
def test_select_mpa_runtime_rejects_missing_match(candidates) -> None:
    with pytest.raises(ValueError, match="not found"):
        select_mpa_runtime(candidates, MpaCallbackTarget("mi-agent1"))


def test_select_mpa_runtime_rejects_duplicate_match() -> None:
    runtime = SimpleNamespace(
        envs=[SimpleNamespace(key="MPA_AGENT_ID", value="mi-agent1")]
    )
    with pytest.raises(ValueError, match="not unique"):
        select_mpa_runtime(
            [("cn-beijing", runtime), ("cn-shanghai", runtime)],
            MpaCallbackTarget("mi-agent1"),
        )


def _app(
    *,
    runtime_payload: dict[str, object] | None = None,
    runtime_status: int = 200,
    hosted_callback_error: Exception | None = None,
    runtime_credentials_error: Exception | None = None,
):
    requests: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            runtime_status,
            json=runtime_payload or {"code": 0, "message": "authorized", "error": ""},
        )

    app = FastAPI()
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(upstream),
        follow_redirects=False,
    )

    async def hosted_callback(provider_id: str) -> str:
        assert provider_id == "provider-1"
        if hosted_callback_error is not None:
            raise hosted_callback_error
        return "https://pool.example.com/login/generic_oauth/callback"

    async def runtime_credentials(target: MpaCallbackTarget) -> MpaRuntimeCredentials:
        assert target == MpaCallbackTarget("mi-agent1")
        if runtime_credentials_error is not None:
            raise runtime_credentials_error
        return MpaRuntimeCredentials(
            endpoint_origin="https://runtime.example.com",
            api_key="runtime-api-key",
        )

    mount_mpa_identity_callback(
        app,
        hosted_callback_resolver=hosted_callback,
        runtime_credentials_resolver=runtime_credentials,
        http_client=http_client,
    )
    return app, http_client, requests


def test_callback_redirects_browser_through_user_pool_then_calls_runtime() -> None:
    app, _, requests = _app()

    with TestClient(app, base_url="https://studio.example.com") as client:
        relay_response = client.get(
            "/oauth/callback",
            params={"code": "idp-code", "state": _relay_state()},
            follow_redirects=False,
        )
        response = client.get(
            "/oauth/callback",
            params={"code": "user-pool-code", "state": _runtime_state()},
        )

    assert relay_response.status_code == 302
    assert relay_response.headers["location"] == (
        "https://pool.example.com/login/generic_oauth/callback"
        f"?code=idp-code&state={_relay_state()}"
    )
    assert relay_response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.status_code == 200
    assert "授权成功" in response.text
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert "set-cookie" not in response.headers
    assert len(requests) == 1
    assert requests[0].url.path == "/identity/oauth/callback"
    assert dict(requests[0].url.params) == {
        "code": "user-pool-code",
        "state": _runtime_state(),
    }
    assert requests[0].headers["authorization"] == "Bearer runtime-api-key"
    assert "x-jwt-token" not in requests[0].headers


def test_callback_preserves_runtime_expired_result() -> None:
    app, _, _ = _app(
        runtime_status=400,
        runtime_payload={
            "code": 4003,
            "message": "",
            "error": "Invalid or expired state",
        },
    )

    with TestClient(app, base_url="https://studio.example.com") as client:
        response = client.get(
            "/oauth/callback",
            params={"code": "user-pool-code", "state": _runtime_state()},
        )

    assert response.status_code == 400
    assert "授权链接已失效" in response.text


@pytest.mark.parametrize(
    ("params", "expected_status"),
    [
        ({"state": _relay_state()}, 400),
        ({"code": "idp-code", "state": "invalid"}, 400),
    ],
)
def test_callback_rejects_invalid_browser_input(
    params: dict[str, str],
    expected_status: int,
) -> None:
    app, _, requests = _app()

    with TestClient(app, base_url="https://studio.example.com") as client:
        response = client.get("/oauth/callback", params=params)

    assert response.status_code == expected_status
    assert response.json()["code"] == 4002
    assert requests == []


def test_callback_rejects_runtime_redirect_without_leaking_credentials() -> None:
    requests: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "pool.example.com":
            return httpx.Response(
                302,
                headers={
                    "location": "https://studio.example.com/oauth/callback?code=c&state=s"
                },
            )
        return httpx.Response(302, headers={"location": "https://evil.example.com"})

    app = FastAPI()
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))

    async def callback_url(_provider_id: str) -> str:
        return "https://pool.example.com/login/generic_oauth/callback"

    async def credentials(_target: MpaCallbackTarget) -> MpaRuntimeCredentials:
        return MpaRuntimeCredentials("https://runtime.example.com", "secret-key")

    mount_mpa_identity_callback(
        app,
        hosted_callback_resolver=callback_url,
        runtime_credentials_resolver=credentials,
        http_client=http_client,
    )

    with TestClient(app, base_url="https://studio.example.com") as client:
        response = client.get(
            "/oauth/callback",
            params={"code": "user-pool-code", "state": _runtime_state()},
        )

    assert response.status_code == 502
    assert response.json() == {
        "code": 5000,
        "message": "",
        "error": "MPA authorization failed",
    }
    assert len(requests) == 1


def test_callback_hides_runtime_resolution_details() -> None:
    app, _, requests = _app(
        runtime_credentials_error=MpaIdentityCallbackError("MPA Runtime not found")
    )

    with TestClient(app, base_url="https://studio.example.com") as client:
        response = client.get(
            "/oauth/callback",
            params={"code": "user-pool-code", "state": _runtime_state()},
        )

    assert response.status_code == 502
    assert response.json() == {
        "code": 5000,
        "message": "",
        "error": "MPA authorization failed",
    }
    assert requests == []


def test_callback_hides_unexpected_error_and_logs_stage(caplog) -> None:
    app, _, requests = _app(
        hosted_callback_error=RuntimeError("must-not-leak-idp-code")
    )

    with TestClient(app, base_url="https://studio.example.com") as client:
        response = client.get(
            "/oauth/callback",
            params={"code": "idp-code", "state": _relay_state()},
        )

    assert response.status_code == 502
    assert response.json() == {
        "code": 5000,
        "message": "",
        "error": "MPA authorization failed",
    }
    assert "stage=resolve_userpool_callback error=RuntimeError" in caplog.text
    assert "request_id=request-1 target=mi-agent1" in caplog.text
    assert "must-not-leak-idp-code" not in caplog.text
    assert requests == []


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(
            200,
            headers={"content-length": "70000"},
            content=b"{}",
        ),
        httpx.Response(200, content=b"x" * 70000),
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"code": True, "message": "", "error": ""}),
    ],
)
def test_runtime_payload_rejects_invalid_responses(response: httpx.Response) -> None:
    with pytest.raises(MpaIdentityCallbackError):
        _parse_runtime_payload(response)


@pytest.mark.asyncio
async def test_runtime_callback_requires_api_key() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500))
    )
    try:
        with pytest.raises(MpaIdentityCallbackError, match="key authentication"):
            await _call_runtime_callback(
                client,
                MpaRuntimeCredentials("https://runtime.example.com", ""),
                "code",
                "state",
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_runtime_callback_rejects_endpoint_paths() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500))
    )
    try:
        with pytest.raises(MpaIdentityCallbackError, match="Runtime endpoint"):
            await _call_runtime_callback(
                client,
                MpaRuntimeCredentials(
                    "https://runtime.example.com/attacker-controlled",
                    "api-key",
                ),
                "code",
                "state",
            )
    finally:
        await client.aclose()


def test_runtime_nonstandard_error_is_preserved_as_json() -> None:
    response = _runtime_result_response(
        RuntimeCallbackResult(
            400,
            {"code": 4004, "message": "", "error": "token exchange failed"},
        )
    )

    assert response.status_code == 400
    assert json.loads(bytes(response.body)) == {
        "code": 4004,
        "message": "",
        "error": "token exchange failed",
    }
