from __future__ import annotations

import json

import httpx
import pytest

from frontend.server.mpa.runtime_client import (
    MpaExecutionConfigChange,
    MpaProfile,
    MpaProfileApplyRequest,
    MpaRuntimeSessionSummary,
    MpaSessionExecutionConfig,
    MpaRuntimeClient,
    MpaRuntimeError,
)


def _profile() -> MpaProfile:
    return MpaProfile(
        name="research",
        description="Research assistant",
        system="Use cited sources.",
        model={"id": "model-1"},
        tools=[],
        skills=[{"skillId": "skill-1", "version": "3"}],
        mcpServers=[],
        metadata={"veadk:agent-type": "mpa"},
    )


def test_profile_digest_is_canonical_and_secret_fields_are_rejected() -> None:
    first = MpaProfileApplyRequest.from_profile(
        source_profile_id="draft-1", profile=_profile()
    )
    second = MpaProfileApplyRequest.from_profile(
        source_profile_id="draft-1", profile=_profile()
    )
    assert first.source_profile_digest == second.source_profile_digest
    assert first.source_profile_digest.startswith("sha256:")

    with pytest.raises(ValueError, match="secret"):
        MpaProfile(
            name="bad",
            system="bad",
            model={"id": "m", "apiKey": "plaintext"},
        )


@pytest.mark.asyncio
async def test_apply_and_status_forward_bearer_etag_and_safe_errors() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "PUT":
            return httpx.Response(
                202,
                headers={"ETag": '"runtime-1"'},
                json={
                    "operationId": "op-1",
                    "status": "accepted",
                    "profileRevision": 1,
                    "runtimeRevision": "1",
                    "etag": '"1"',
                },
            )
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "operationId": "op-1",
                    "status": "passed",
                    "readinessPhase": "execution_ready",
                },
            )
        return httpx.Response(
            200,
            headers={"ETag": '"runtime-1"'},
            json={
                "operationId": "op-1",
                "status": "applied",
                "profileRevision": 1,
                "runtimeRevision": "1",
                "etag": '"1"',
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaRuntimeClient(transport=transport)
        request = MpaProfileApplyRequest.from_profile(
            source_profile_id="draft-1",
            profile=_profile(),
        )
        applied = await client.apply_profile(
            endpoint="https://runtime.example",
            mpa_instance_id="mpa-1",
            bearer_token="bearer-value",
            idempotency_key="idem-1",
            profile=request,
            create=True,
        )
        status = await client.profile_status(
            endpoint="https://runtime.example",
            mpa_instance_id="mpa-1",
            bearer_token="bearer-value",
        )
        smoke = await client.execution_smoke(
            endpoint="https://runtime.example/",
            mpa_instance_id="mpa-1",
            bearer_token="bearer-value",
            idempotency_key="smoke-1",
        )

    assert applied.etag == '"runtime-1"' and status.status == "applied"
    assert smoke["operationId"] == "op-1"
    assert requests[0].headers["authorization"] == "Bearer bearer-value"
    assert requests[0].headers["idempotency-key"] == "idem-1"
    assert requests[0].headers["if-none-match"] == "*"
    assert "if-match" not in requests[0].headers
    assert "sourceProfileRevision" not in json.loads(requests[0].content)
    assert str(requests[2].url) == (
        "https://runtime.example/api/v1/readiness/execution-smoke"
    )
    assert requests[2].headers["authorization"] == "Bearer bearer-value"
    assert requests[2].headers["idempotency-key"] == "smoke-1"


@pytest.mark.asyncio
async def test_update_requires_one_etag_and_redacts_runtime_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            headers={"X-Request-Id": "req-1"},
            json={
                "error": {"code": "profile_version_conflict", "message": "token=secret"}
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaRuntimeClient(transport=transport)
        request = MpaProfileApplyRequest.from_profile(
            source_profile_id="draft-1",
            profile=_profile(),
        )
        with pytest.raises(ValueError, match="runtime revision"):
            await client.apply_profile(
                endpoint="https://runtime.example",
                mpa_instance_id="mpa-1",
                bearer_token="bearer-value",
                idempotency_key="idem-2",
                profile=request,
                create=False,
            )
        with pytest.raises(MpaRuntimeError) as caught:
            await client.apply_profile(
                endpoint="https://runtime.example",
                mpa_instance_id="mpa-1",
                bearer_token="bearer-value",
                idempotency_key="idem-2",
                profile=request,
                runtime_revision='"runtime-1"',
                create=False,
            )
    assert caught.value.code == "profile_version_conflict"
    assert caught.value.request_id == "req-1"
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_runtime_error_reads_fastapi_detail_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            headers={"X-Request-Id": "req-smoke"},
            json={
                "detail": {
                    "code": "smoke_worker_not_ready",
                    "message": "Authorization=secret",
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaRuntimeClient(transport=transport)
        with pytest.raises(MpaRuntimeError) as caught:
            await client.execution_smoke(
                endpoint="https://runtime.example",
                mpa_instance_id="mpa-1",
                bearer_token="bearer-value",
                idempotency_key="smoke-1",
            )

    assert caught.value.code == "smoke_worker_not_ready"
    assert caught.value.request_id == "req-smoke"
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_session_execution_config_methods_forward_headers_and_body() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"ETag": '"2"'},
            json={
                "appName": "default",
                "sessionId": "session-1",
                "revision": 2,
                "etag": '"2"',
                "mpaInstanceId": "mpa-1",
                "profileRevision": 4,
                "profileDefaultRevision": 4,
                "overrides": {},
                "effectiveRefs": {},
                "invalidRefs": [],
                "updatedBy": "user-1",
                "createdAt": "2026-09-15T00:00:00Z",
                "updatedAt": "2026-09-15T00:00:00Z",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaRuntimeClient(transport=transport)
        current = await client.session_execution_config(
            endpoint="https://runtime.example/",
            session_id="session-1",
            bearer_token="bearer-value",
        )
        patched = await client.patch_session_execution_config(
            endpoint="https://runtime.example",
            session_id="session-1",
            bearer_token="bearer-value",
            if_match='"1"',
            changes=[
                MpaExecutionConfigChange(
                    category="mcpServers",
                    mode="replace",
                    value=[{"id": "ais-1"}],
                )
            ],
        )
        upgraded = await client.upgrade_session_profile(
            endpoint="https://runtime.example",
            session_id="session-1",
            bearer_token="bearer-value",
            if_match='"2"',
            idempotency_key="upgrade-1",
            target_profile_revision=5,
        )

    assert isinstance(current, MpaSessionExecutionConfig)
    assert patched.profile_revision == 4
    assert upgraded.etag == '"2"'
    assert str(requests[0].url) == (
        "https://runtime.example/api/v1/sessions/session-1/execution-config"
    )
    assert requests[0].method == "GET"
    assert requests[1].method == "PATCH"
    assert requests[1].headers["authorization"] == "Bearer bearer-value"
    assert requests[1].headers["if-match"] == '"1"'
    assert json.loads(requests[1].content) == {
        "changes": [
            {
                "category": "mcpServers",
                "mode": "replace",
                "value": [{"id": "ais-1"}],
            }
        ]
    }
    assert requests[2].method == "POST"
    assert requests[2].headers["idempotency-key"] == "upgrade-1"
    assert json.loads(requests[2].content) == {"targetProfileRevision": 5}


@pytest.mark.asyncio
async def test_session_list_and_delete_forward_runtime_cleanup_requests() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "sessions": [
                        {
                            "sessionId": "session-1",
                            "appName": "mpa",
                            "status": "idle",
                            "adminDebug": True,
                        }
                    ]
                },
            )
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaRuntimeClient(transport=transport)
        sessions = await client.list_sessions(
            endpoint="https://runtime.example/",
            bearer_token="bearer-value",
            include_a2a=True,
        )
        await client.delete_session(
            endpoint="https://runtime.example/",
            session_id="session-1",
            bearer_token="bearer-value",
        )

    assert sessions == [
        MpaRuntimeSessionSummary(
            sessionId="session-1",
            appName="mpa",
            status="idle",
            adminDebug=True,
        )
    ]
    assert str(requests[0].url) == (
        "https://runtime.example/api/v1/sessions?include_a2a=true"
    )
    assert requests[0].headers["authorization"] == "Bearer bearer-value"
    assert requests[1].method == "DELETE"
    assert str(requests[1].url) == ("https://runtime.example/api/v1/sessions/session-1")
