# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Contract tests for the shared Studio MPA control-plane client."""

from __future__ import annotations

import json

import httpx
import pytest

from veadk.integrations.mpa.control_plane_client import (
    MpaAgentOperationRequest,
    MpaControlPlaneClient,
    MpaControlPlaneError,
    MpaExecutionConfigChange,
    MpaProfile,
)


def _profile() -> MpaProfile:
    return MpaProfile(
        name="Researcher",
        description="Research agent",
        system="Research carefully.",
        model={"provider": "ark", "modelId": "doubao-test"},
        tools=[{"id": "tool-1"}],
        skills=[{"id": "skill-1"}],
        mcpServers=[{"id": "ais-1"}],
        metadata={"veadk:agent-type": "mpa"},
    )


def _operation_request() -> MpaAgentOperationRequest:
    return MpaAgentOperationRequest(
        operationKind="create",
        runtimeId="runtime-1",
        region="cn-beijing",
        mpaInstanceId="mpa-1",
        sourceProfileId="studio-agent:mpa-1",
        targetKey="runtime:cn-beijing:mpa-1",
        profile=_profile(),
    )


@pytest.mark.asyncio
async def test_get_agent_view_sends_bearer_and_preserves_etag() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"ETag": '"profile-7"'},
            json={
                "mpaInstanceId": "mpa-1",
                "bindingStatus": "bound",
                "runtime": {"runtimeId": "runtime-1"},
                "profile": {"profileRevision": 7},
                "capabilities": {"canWrite": True, "canDebug": True},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test/root/",
            bearer_token="studio-token",
            transport=transport,
        )
        result = await client.get_agent_view(
            "mpa-1", runtime_id="runtime-1", region="cn-beijing"
        )

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert request.url == httpx.URL(
        "https://studio.example.test/root/web/mpa/agents/mpa-1/view",
        params={"runtimeId": "runtime-1", "region": "cn-beijing"},
    )
    assert request.headers["Authorization"] == "Bearer studio-token"
    assert result.mpa_instance_id == "mpa-1"
    assert result.binding_status == "bound"
    assert result.profile == {"profileRevision": 7}
    assert result.capabilities.can_write is True
    assert result.capabilities.can_debug is True
    assert result.etag == '"profile-7"'


@pytest.mark.asyncio
async def test_create_agent_sends_camel_case_payload_and_idempotency_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            202,
            json={
                "operationId": "mpaop-1",
                "operationKind": "create",
                "ownerId": "owner-1",
                "targetKey": "runtime:cn-beijing:mpa-1",
                "stage": "runtime_preparing",
                "status": "active",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test",
            bearer_token="studio-token",
            transport=transport,
        )
        operation = await client.create_agent(
            _operation_request(), idempotency_key="create-attempt-1"
        )

    assert operation.operation_id == "mpaop-1"
    assert operation.status == "active"
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/web/mpa/agents"
    assert request.headers["Idempotency-Key"] == "create-attempt-1"
    assert request.headers["Authorization"] == "Bearer studio-token"
    assert request.headers["Content-Type"] == "application/json"
    payload = json.loads(request.content)
    assert payload["operationKind"] == "create"
    assert payload["runtimeId"] == "runtime-1"
    assert payload["sourceProfileId"] == "studio-agent:mpa-1"
    assert payload["profile"]["mcpServers"] == [{"id": "ais-1"}]
    assert "mcp_servers" not in payload["profile"]


@pytest.mark.asyncio
async def test_update_agent_requires_revision_and_preserves_idempotency_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            202,
            json={
                "operationId": "mpaop-2",
                "operationKind": "update",
                "stage": "profile_applying",
                "status": "active",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test", transport=transport
        )
        request = _operation_request().model_copy(
            update={"operation_kind": "update", "runtime_revision": '"7"'}
        )
        operation = await client.update_agent(
            "mpa/with space", request, idempotency_key="update-attempt-1"
        )

    assert operation.operation_kind == "update"
    sent = requests[0]
    assert sent.method == "PATCH"
    assert sent.url.raw_path == b"/web/mpa/agents/mpa%2Fwith%20space"
    assert sent.headers["Idempotency-Key"] == "update-attempt-1"
    assert json.loads(sent.content)["runtimeRevision"] == '"7"'

    request_without_revision = request.model_copy(update={"runtime_revision": ""})
    with pytest.raises(ValueError, match="runtime revision"):
        await client.update_agent(
            "mpa-1",
            request_without_revision,
            idempotency_key="update-attempt-2",
        )
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_list_active_operations_returns_typed_operations() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "operations": [
                    {
                        "operationId": "mpaop-1",
                        "operationKind": "create",
                        "stage": "smoke_running",
                        "status": "active",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test", transport=transport
        )
        operations = await client.list_active_operations()

    assert [operation.operation_id for operation in operations] == ["mpaop-1"]
    assert requests[0].url == httpx.URL(
        "https://studio.example.test/web/mpa/agent-operations",
        params={"status": "active"},
    )


@pytest.mark.asyncio
async def test_get_operation_reads_terminal_operation_by_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "operationId": "mpaop/final 1",
                "operationKind": "create",
                "stage": "runnable",
                "status": "succeeded",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test", transport=transport
        )
        operation = await client.get_operation("mpaop/final 1")

    assert operation.status == "succeeded"
    assert requests[0].url.raw_path == b"/web/mpa/agent-operations/mpaop%2Ffinal%201"


@pytest.mark.asyncio
async def test_retry_operation_reuses_original_request_without_new_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            202,
            json={
                "operationId": "mpaop/retry 1",
                "operationKind": "create",
                "stage": "profile_applying",
                "status": "active",
                "retryCount": 1,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test", transport=transport
        )
        operation = await client.retry_operation("mpaop/retry 1", _operation_request())

    assert operation.retry_count == 1
    sent = requests[0]
    assert sent.method == "POST"
    assert sent.url.raw_path == b"/web/mpa/agent-operations/mpaop%2Fretry%201/retry"
    assert "Idempotency-Key" not in sent.headers
    assert json.loads(sent.content)["operationKind"] == "create"


@pytest.mark.asyncio
async def test_profile_status_and_apply_profile_preserve_etag_and_create_semantics() -> (
    None
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                headers={"ETag": '"7"'},
                json={
                    "operationId": "profile-op-7",
                    "status": "applied",
                    "profileRevision": 7,
                    "runtimeRevision": "7",
                },
            )
        return httpx.Response(
            202,
            headers={"ETag": '"8"'},
            json={
                "operationId": "profile-op-8",
                "status": "applied",
                "profileRevision": 8,
                "runtimeRevision": "8",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test", transport=transport
        )
        status = await client.get_profile_status(
            "mpa-1", runtime_id="runtime-1", region="cn-beijing"
        )
        applied = await client.apply_profile(
            "mpa-1",
            runtime_id="runtime-1",
            region="cn-beijing",
            source_profile_id="studio-agent:mpa-1",
            profile=_profile(),
            create=True,
            idempotency_key="profile-attempt-1",
        )

    assert status.etag == '"7"'
    assert applied.etag == '"8"'
    sent = requests[1]
    assert sent.method == "PUT"
    assert sent.headers["Idempotency-Key"] == "profile-attempt-1"
    assert json.loads(sent.content)["create"] is True
    assert json.loads(sent.content)["runtimeRevision"] == ""


@pytest.mark.asyncio
async def test_execution_config_patch_and_profile_upgrade_send_cas_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        next_revision = 2 if request.method == "PATCH" else 3
        return httpx.Response(
            200,
            headers={"ETag": f'"{next_revision}"'},
            json={
                "appName": "default",
                "sessionId": "session-1",
                "revision": next_revision,
                "mpaInstanceId": "mpa-1",
                "profileRevision": 7,
                "profileDefaultRevision": 7,
                "overrides": {},
                "effectiveRefs": {},
                "invalidRefs": [],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test", transport=transport
        )
        patched = await client.patch_session_execution_config(
            "session-1",
            runtime_id="runtime-1",
            region="cn-beijing",
            etag='"1"',
            changes=[
                MpaExecutionConfigChange(
                    category="mcpServers",
                    mode="replace",
                    value=[{"id": "ais-2"}],
                )
            ],
        )
        upgraded = await client.upgrade_session_profile(
            "session-1",
            runtime_id="runtime-1",
            region="cn-beijing",
            etag='"2"',
            idempotency_key="upgrade-attempt-1",
            target_profile_revision=7,
        )

    assert patched.revision == 2
    assert patched.etag == '"2"'
    assert upgraded.revision == 3
    assert upgraded.etag == '"3"'
    patch_request, upgrade_request = requests
    assert patch_request.headers["If-Match"] == '"1"'
    assert json.loads(patch_request.content)["changes"][0] == {
        "category": "mcpServers",
        "mode": "replace",
        "value": [{"id": "ais-2"}],
    }
    assert upgrade_request.headers["If-Match"] == '"2"'
    assert upgrade_request.headers["Idempotency-Key"] == "upgrade-attempt-1"
    assert json.loads(upgrade_request.content)["targetProfileRevision"] == 7


@pytest.mark.asyncio
async def test_execution_config_read_and_delete_preview_use_runtime_scope() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/execution-config"):
            return httpx.Response(
                200,
                headers={"ETag": '"1"'},
                json={
                    "appName": "default",
                    "sessionId": "session/read 1",
                    "revision": 1,
                    "mpaInstanceId": "mpa-1",
                    "profileRevision": 7,
                    "profileDefaultRevision": 7,
                    "overrides": {},
                    "effectiveRefs": {},
                    "invalidRefs": [],
                },
            )
        return httpx.Response(
            200,
            json={
                "mpaInstanceId": "mpa-1",
                "bindingStatus": "bound",
                "canDelete": False,
                "blockers": ["active_sessions"],
                "sessionCounts": {
                    "total": 1,
                    "active": 1,
                    "idle": 0,
                    "debug": 0,
                },
                "activeSessions": [{"sessionId": "session/read 1"}],
                "cleanupPlan": [],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test", transport=transport
        )
        config = await client.get_session_execution_config(
            "session/read 1", runtime_id="runtime-1"
        )
        preview = await client.get_delete_preview("mpa-1", runtime_id="runtime-1")

    assert config.revision == 1
    assert config.etag == '"1"'
    assert preview.can_delete is False
    assert preview.blockers == ["active_sessions"]
    assert requests[0].url.raw_path == (
        b"/web/mpa/sessions/session%2Fread%201/execution-config"
        b"?runtimeId=runtime-1&region=cn-beijing"
    )
    assert dict(requests[1].url.params) == {
        "runtimeId": "runtime-1",
        "region": "cn-beijing",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "code", "retryable"),
    [
        (409, "profile_version_conflict", False),
        (412, "execution_config_changed", False),
        (428, "precondition_required", False),
        (503, "mpa_operation_service_unavailable", True),
    ],
)
async def test_structured_control_plane_errors(
    status_code: int, code: str, retryable: bool
) -> None:
    current_state = {"revision": 2, "etag": '"2"'}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            headers={"X-Request-Id": "header-request"},
            json={
                "detail": {
                    "code": code,
                    "message": code,
                    "requestId": "body-request",
                    "currentState": current_state,
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test",
            bearer_token="do-not-leak",
            transport=transport,
        )
        with pytest.raises(MpaControlPlaneError) as caught:
            await client.get_agent_view("mpa-1")

    error = caught.value
    assert error.status_code == status_code
    assert error.code == code
    assert error.request_id == "body-request"
    assert error.retryable is retryable
    assert error.current_state == current_state
    assert str(error) == "MPA control-plane request failed: " + code
    assert "do-not-leak" not in repr(error)


@pytest.mark.asyncio
async def test_timeout_is_retryable_and_does_not_disclose_request_secrets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test",
            bearer_token="do-not-leak",
            transport=transport,
        )
        with pytest.raises(MpaControlPlaneError) as caught:
            await client.create_agent(
                _operation_request(), idempotency_key="keep-for-replay"
            )

    error = caught.value
    assert error.status_code == 0
    assert error.code == "control_plane_timeout"
    assert error.retryable is True
    assert "do-not-leak" not in str(error)
    assert "keep-for-replay" not in repr(error)


@pytest.mark.asyncio
async def test_unstructured_error_detail_is_not_exposed_as_error_code() -> None:
    unsafe_detail = "request failed for Authorization: Bearer do-not-leak"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": unsafe_detail})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test", transport=transport
        )
        with pytest.raises(MpaControlPlaneError) as caught:
            await client.get_agent_view("mpa-1")

    assert caught.value.code == "http_500"
    assert caught.value.retryable is True
    assert unsafe_detail not in str(caught.value)
    assert "do-not-leak" not in repr(caught.value)


@pytest.mark.asyncio
async def test_invalid_response_is_mapped_to_safe_structured_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"bindingStatus": "bound"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test", transport=transport
        )
        with pytest.raises(MpaControlPlaneError) as caught:
            await client.get_agent_view("mpa-1")

    assert caught.value.code == "control_plane_invalid_response"
    assert caught.value.status_code == 502
    assert caught.value.retryable is False


@pytest.mark.asyncio
async def test_invalid_operation_list_is_mapped_to_safe_structured_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"operations": "not-a-list"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
        client = MpaControlPlaneClient(
            base_url="https://studio.example.test", transport=transport
        )
        with pytest.raises(MpaControlPlaneError) as caught:
            await client.list_active_operations()

    assert caught.value.code == "control_plane_invalid_response"
    assert caught.value.status_code == 502


def test_profile_rejects_embedded_secrets() -> None:
    with pytest.raises(ValueError, match="secret values"):
        MpaProfile(
            name="Unsafe",
            system="Do work.",
            model={"modelId": "m-1", "apiKey": "plain-text"},
        )


def test_profile_allows_non_secret_model_token_limits() -> None:
    profile = MpaProfile(
        name="Safe",
        system="Do work.",
        model={"modelId": "m-1", "max_tokens": 8192},
    )

    assert profile.model["max_tokens"] == 8192
