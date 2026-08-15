# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from frontend.server.migration import gateway as gateway_module
from frontend.server.migration.gateway import (
    MigrationGatewayError,
    MigrationSandboxGateway,
    MigrationSandboxSession,
)
from veadk.cli.frontend_skill_creator import _sandbox_model_config

TASK_ID = "migration-v1-" + "1" * 32


def session(**overrides: object) -> MigrationSandboxSession:
    values: dict[str, object] = {
        "tool_id": "tool-dev",
        "session_id": "session-1",
        "task_id": TASK_ID,
        "endpoint": "https://sandbox.invalid/proxy",
        "region": "cn-beijing",
        "status": "Ready",
        "created_at": "2026-08-11T08:00:00Z",
        "expire_at": "2026-08-11T09:00:00Z",
        "owner_id": "owner-1",
    }
    values.update(overrides)
    return MigrationSandboxSession(**values)  # type: ignore[arg-type]


def session_info(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "session_id": "session-1",
        "user_session_id": TASK_ID,
        "endpoint": "https://sandbox.invalid/proxy",
        "status": "Ready",
        "created_at": "2026-08-11T08:00:00Z",
        "expire_at": "2026-08-11T09:00:00Z",
        "metadata": [SimpleNamespace(key="Username", value="owner-1")],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def gateway(
    client: object | None = None,
    *,
    tool_id: str | None = "tool-dev",
) -> MigrationSandboxGateway:
    return MigrationSandboxGateway(
        tool_id=tool_id,
        region="cn-beijing",
        tools_client_factory=lambda _region: client,
    )


def assert_code(error: pytest.ExceptionInfo[MigrationGatewayError], code: str) -> None:
    assert error.value.code == code


def test_tool_lookup_and_capability_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = gateway(tool_id="")
    with pytest.raises(MigrationGatewayError) as raised:
        missing._get_tool()
    assert_code(raised, "MIGRATION_DEVENV_NOT_CONFIGURED")

    no_regions = gateway()
    no_regions._regions = []
    with pytest.raises(MigrationGatewayError) as unavailable_regions:
        no_regions._get_tool()
    assert_code(unavailable_regions, "MIGRATION_DEVENV_UNAVAILABLE")

    unavailable = gateway(
        SimpleNamespace(
            get_tool=lambda _request: (_ for _ in ()).throw(RuntimeError("down"))
        )
    )
    assert unavailable.capabilities()["enabled"] is False

    _, base_url = _sandbox_model_config("volcengine")
    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("VEADK_DEVENV_IMAGE", "expected-image")
    invalid_tool = SimpleNamespace(
        tool_type="DevEnv",
        status="Ready",
        image_url="other-image",
        envs=[
            SimpleNamespace(key="CODEX_MODEL", value="model"),
            SimpleNamespace(key="CODEX_API_KEY", value="secret"),
            SimpleNamespace(key="CODEX_BASE_URL", value=base_url),
        ],
    )
    assert (
        gateway(SimpleNamespace(get_tool=lambda _request: invalid_tool)).capabilities()[
            "enabled"
        ]
        is False
    )

    monkeypatch.delenv("VEADK_DEVENV_IMAGE")
    no_model = SimpleNamespace(
        tool_type="DevEnv",
        status="Ready",
        image_url="",
        envs=[],
    )
    capability = gateway(
        SimpleNamespace(get_tool=lambda _request: no_model)
    ).capabilities()
    assert capability["enabled"] is False
    assert capability["model"] == {"configured": False, "id": ""}

    with pytest.raises(MigrationGatewayError) as invalid_response:
        MigrationSandboxGateway._session(
            SimpleNamespace(),
            tool_id="tool-dev",
            region="cn-beijing",
        )
    assert_code(invalid_response, "MIGRATION_SESSION_RESPONSE_INVALID")


def test_tool_lookup_falls_back_only_for_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Client:
        def __init__(self, region: str) -> None:
            self.region = region

        def get_tool(self, _request: object) -> object:
            calls.append(self.region)
            if self.region == "first":
                raise RuntimeError("missing")
            return SimpleNamespace(tool_type="DevEnv")

    adapter = MigrationSandboxGateway(
        tool_id="tool-dev",
        region="cn-beijing",
        tools_client_factory=Client,
    )
    adapter._regions = ["first", "second"]
    monkeypatch.setattr(
        gateway_module,
        "is_agentkit_resource_not_found",
        lambda error: str(error) == "missing",
    )

    tool, region = adapter._get_tool()

    assert tool.tool_type == "DevEnv"
    assert region == "second"
    assert calls == ["first", "second"]


def test_session_listing_filters_sorts_and_validates_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        SimpleNamespace(
            session_infos=[
                session_info(session_id="ignored-prefix", user_session_id="other"),
                session_info(session_id="ignored-task", user_session_id=TASK_ID + "x"),
                session_info(
                    session_id="ignored-owner",
                    metadata=[SimpleNamespace(key="Username", value="other")],
                ),
                session_info(session_id="older", created_at="2026-08-11T07:00:00Z"),
            ],
            next_token="next",
        ),
        SimpleNamespace(
            session_infos=[session_info(session_id="newer")],
            next_token=None,
        ),
    ]
    client = SimpleNamespace(list_sessions=lambda _request: responses.pop(0))
    adapter = gateway(client)

    listed = adapter._list_region(
        "cn-beijing",
        owner_id="owner-1",
        task_id=TASK_ID,
    )

    assert [item.session_id for item in listed] == ["newer", "older"]

    repeated = gateway(
        SimpleNamespace(
            list_sessions=lambda _request: SimpleNamespace(
                session_infos=[],
                next_token="same",
            )
        )
    )
    with pytest.raises(MigrationGatewayError) as repeated_error:
        repeated._list_region("cn-beijing", owner_id="owner-1")
    assert_code(repeated_error, "MIGRATION_SESSION_LIST_INVALID")

    counter = iter(range(101))
    endless = gateway(
        SimpleNamespace(
            list_sessions=lambda _request: SimpleNamespace(
                session_infos=[],
                next_token=f"next-{next(counter)}",
            )
        )
    )
    with pytest.raises(MigrationGatewayError) as limit_error:
        endless._list_region("cn-beijing", owner_id="owner-1")
    assert_code(limit_error, "MIGRATION_SESSION_LIST_INVALID")

    monkeypatch.setattr(gateway_module.time, "sleep", lambda _seconds: None)


def test_public_session_queries_map_fallbacks_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert gateway(tool_id="").list_sessions("owner-1") == []

    adapter = gateway()
    adapter._regions = []
    assert adapter.list_sessions("owner-1") == []

    adapter._regions = ["first", "second"]
    calls: list[str] = []

    def list_region(region: str, **_kwargs: object) -> list[MigrationSandboxSession]:
        calls.append(region)
        if region == "first":
            raise RuntimeError("missing")
        return [session()]

    monkeypatch.setattr(adapter, "_list_region", list_region)
    monkeypatch.setattr(
        gateway_module,
        "is_agentkit_resource_not_found",
        lambda error: str(error) == "missing",
    )
    assert adapter.list_sessions("owner-1") == [session()]
    assert adapter.find_session(TASK_ID, "owner-1") == session()
    assert calls == ["first", "second", "first", "second"]

    monkeypatch.setattr(
        adapter,
        "_list_region",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.Timeout("late")),
    )
    with pytest.raises(MigrationGatewayError) as list_error:
        adapter.list_sessions("owner-1")
    assert_code(list_error, "MIGRATION_SESSION_LIST_FAILED")
    assert list_error.value.retryable is True

    with pytest.raises(MigrationGatewayError) as read_error:
        adapter.find_session(TASK_ID, "owner-1")
    assert_code(read_error, "MIGRATION_SESSION_READ_FAILED")
    assert read_error.value.retryable is True

    propagated = MigrationGatewayError("UPSTREAM", "upstream")
    monkeypatch.setattr(
        adapter,
        "_list_region",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(propagated),
    )
    with pytest.raises(MigrationGatewayError) as propagated_list:
        adapter.list_sessions("owner-1")
    assert propagated_list.value is propagated
    with pytest.raises(MigrationGatewayError) as propagated_read:
        adapter.find_session(TASK_ID, "owner-1")
    assert propagated_read.value is propagated


def test_find_session_rejects_missing_and_ambiguous_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(MigrationGatewayError) as unconfigured:
        gateway(tool_id="").find_session(TASK_ID, "owner-1")
    assert_code(unconfigured, "MIGRATION_DEVENV_NOT_CONFIGURED")

    adapter = gateway()
    monkeypatch.setattr(adapter, "_list_region", lambda *_args, **_kwargs: [])
    with pytest.raises(MigrationGatewayError) as missing:
        adapter.find_session(TASK_ID, "owner-1")
    assert_code(missing, "MIGRATION_TASK_NOT_FOUND")

    monkeypatch.setattr(
        adapter,
        "_list_region",
        lambda *_args, **_kwargs: [session(), session(session_id="session-2")],
    )
    with pytest.raises(MigrationGatewayError) as ambiguous:
        adapter.find_session(TASK_ID, "owner-1")
    assert_code(ambiguous, "MIGRATION_SESSION_AMBIGUOUS")


def test_ready_wait_and_create_failure_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = gateway()
    monkeypatch.setattr(gateway_module, "_SESSION_READY_ATTEMPTS", 2)
    monkeypatch.setattr(gateway_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(MigrationGatewayError) as released:
        adapter._wait_for_ready_session(
            "cn-beijing",
            task_id=TASK_ID,
            owner_id="owner-1",
            initial=session(status="Expired", endpoint=""),
        )
    assert_code(released, "MIGRATION_SESSION_CREATE_FAILED")

    monkeypatch.setattr(
        adapter,
        "_list_region",
        lambda *_args, **_kwargs: [session(), session(session_id="session-2")],
    )
    with pytest.raises(MigrationGatewayError) as ambiguous:
        adapter._wait_for_ready_session(
            "cn-beijing",
            task_id=TASK_ID,
            owner_id="owner-1",
        )
    assert_code(ambiguous, "MIGRATION_SESSION_AMBIGUOUS")

    monkeypatch.setattr(adapter, "_list_region", lambda *_args, **_kwargs: [])
    assert (
        adapter._wait_for_ready_session(
            "cn-beijing",
            task_id=TASK_ID,
            owner_id="owner-1",
        )
        is None
    )

    monkeypatch.setattr(adapter, "_get_tool", lambda: (object(), "cn-beijing"))
    monkeypatch.setattr(
        adapter,
        "_list_region",
        lambda *_args, **_kwargs: [session(), session(session_id="session-2")],
    )
    with pytest.raises(MigrationGatewayError) as create_ambiguous:
        adapter.create_session(
            task_id=TASK_ID,
            owner_id="owner-1",
            creator_name="Owner",
            display_name="Migration",
            ttl_seconds=3600,
        )
    assert_code(create_ambiguous, "MIGRATION_SESSION_AMBIGUOUS")

    monkeypatch.setattr(
        adapter,
        "_list_region",
        lambda *_args, **_kwargs: [session(endpoint="", status="Creating")],
    )
    monkeypatch.setattr(
        adapter, "_wait_for_ready_session", lambda *_args, **_kwargs: None
    )
    with pytest.raises(MigrationGatewayError) as incomplete_existing:
        adapter.create_session(
            task_id=TASK_ID,
            owner_id="owner-1",
            creator_name="Owner",
            display_name="Migration",
            ttl_seconds=3600,
        )
    assert_code(incomplete_existing, "MIGRATION_SESSION_CREATE_INCOMPLETE")


def test_create_maps_uncertain_and_incomplete_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Client:
        def create_session(self, _request: object) -> object:
            raise requests.ConnectionError("closed")

    adapter = gateway(Client())
    monkeypatch.setattr(adapter, "_get_tool", lambda: (object(), "cn-beijing"))
    monkeypatch.setattr(adapter, "_list_region", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        adapter,
        "_wait_for_ready_session",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("recovery failed")
        ),
    )
    with pytest.raises(MigrationGatewayError) as uncertain:
        adapter.create_session(
            task_id=TASK_ID,
            owner_id="owner-1",
            creator_name="Owner",
            display_name="Migration",
            ttl_seconds=3600,
        )
    assert_code(uncertain, "MIGRATION_SESSION_CREATE_UNCERTAIN")
    assert uncertain.value.retryable is False

    response = session_info(endpoint="", status="Creating")
    adapter = gateway(SimpleNamespace(create_session=lambda _request: response))
    monkeypatch.setattr(adapter, "_get_tool", lambda: (object(), "cn-beijing"))
    monkeypatch.setattr(adapter, "_list_region", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        adapter, "_wait_for_ready_session", lambda *_args, **_kwargs: None
    )
    with pytest.raises(MigrationGatewayError) as incomplete:
        adapter.create_session(
            task_id=TASK_ID,
            owner_id="owner-1",
            creator_name="Owner",
            display_name="Migration",
            ttl_seconds=3600,
        )
    assert_code(incomplete, "MIGRATION_SESSION_CREATE_INCOMPLETE")


class HttpResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        data: bytes = b"",
        headers: dict[str, str] | None = None,
        payload: object = None,
        json_error: bool = False,
        chunks: list[bytes] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = data
        self.headers = headers or {}
        self.payload = payload
        self.json_error = json_error
        self.chunks = chunks if chunks is not None else [data]
        self.closed = False

    def json(self) -> object:
        if self.json_error:
            raise ValueError("invalid json")
        return self.payload

    def iter_content(self, _size: int) -> list[bytes]:
        return self.chunks

    def close(self) -> None:
        self.closed = True


def test_remote_file_operations_map_network_http_and_size_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = gateway()
    with pytest.raises(MigrationGatewayError) as expired:
        adapter.get_file(session(status="Expired", endpoint=""), "file", max_bytes=1)
    assert_code(expired, "MIGRATION_SESSION_EXPIRED")

    monkeypatch.setattr(
        gateway_module.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.Timeout("late")),
    )
    with pytest.raises(MigrationGatewayError) as uncertain_write:
        adapter.put_file(session(), "file", b"x", media_type="text/plain")
    assert_code(uncertain_write, "MIGRATION_REMOTE_WRITE_UNCERTAIN")

    monkeypatch.setattr(
        gateway_module.requests,
        "post",
        lambda *_args, **_kwargs: HttpResponse(status_code=500),
    )
    with pytest.raises(MigrationGatewayError) as failed_write:
        adapter.put_file(session(), "file", b"x", media_type="text/plain")
    assert_code(failed_write, "MIGRATION_REMOTE_WRITE_FAILED")

    monkeypatch.setattr(
        gateway_module.requests,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            requests.ConnectionError("down")
        ),
    )
    with pytest.raises(MigrationGatewayError) as failed_read:
        adapter.get_file(session(), "file", max_bytes=1)
    assert_code(failed_read, "MIGRATION_REMOTE_READ_FAILED")
    assert failed_read.value.retryable is True

    for status_code, expected, retryable in (
        (404, "MIGRATION_REMOTE_FILE_NOT_FOUND", False),
        (503, "MIGRATION_REMOTE_READ_FAILED", True),
        (403, "MIGRATION_REMOTE_READ_FAILED", False),
    ):
        response = HttpResponse(status_code=status_code)
        monkeypatch.setattr(
            gateway_module.requests,
            "get",
            lambda *_args, _response=response, **_kwargs: _response,
        )
        with pytest.raises(MigrationGatewayError) as raised:
            adapter.get_file(session(), "file", max_bytes=1)
        assert_code(raised, expected)
        assert raised.value.retryable is retryable
        assert response.closed is True

    declared = HttpResponse(headers={"content-length": "2"}, data=b"xx")
    monkeypatch.setattr(
        gateway_module.requests, "get", lambda *_args, **_kwargs: declared
    )
    with pytest.raises(MigrationGatewayError) as too_large:
        adapter.get_file(session(), "file", max_bytes=1)
    assert_code(too_large, "MIGRATION_REMOTE_FILE_TOO_LARGE")
    assert declared.closed is True

    streamed = HttpResponse(
        headers={"content-length": "invalid"}, chunks=[b"", b"x", b"y"]
    )
    monkeypatch.setattr(
        gateway_module.requests, "get", lambda *_args, **_kwargs: streamed
    )
    with pytest.raises(MigrationGatewayError) as stream_too_large:
        adapter.get_file(session(), "file", max_bytes=1)
    assert_code(stream_too_large, "MIGRATION_REMOTE_FILE_TOO_LARGE")
    assert streamed.closed is True

    success = HttpResponse(headers={"content-length": "1"}, chunks=[b"", b"x"])
    monkeypatch.setattr(
        gateway_module.requests, "get", lambda *_args, **_kwargs: success
    )
    assert adapter.get_file(session(), "file", max_bytes=1) == b"x"
    assert success.closed is True


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (HttpResponse(status_code=500), "MIGRATION_REMOTE_EXEC_FAILED"),
        (HttpResponse(payload=None, json_error=True), "MIGRATION_REMOTE_EXEC_INVALID"),
        (HttpResponse(payload={"data": []}), "MIGRATION_REMOTE_EXEC_INVALID"),
    ],
)
def test_remote_exec_rejects_http_and_payload_errors(
    monkeypatch: pytest.MonkeyPatch,
    response: HttpResponse,
    expected: str,
) -> None:
    monkeypatch.setattr(
        gateway_module.requests, "post", lambda *_args, **_kwargs: response
    )
    with pytest.raises(MigrationGatewayError) as raised:
        gateway().execute_bash(
            session(),
            "true",
            operation="prepare_source",
            timeout_seconds=1,
        )
    assert_code(raised, expected)


def test_remote_exec_maps_network_and_poll_timeout_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = gateway()
    monkeypatch.setattr(
        gateway_module.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.Timeout("late")),
    )
    with pytest.raises(MigrationGatewayError) as uncertain:
        adapter.execute_bash(
            session(),
            "true",
            operation="prepare_source",
            timeout_seconds=1,
        )
    assert_code(uncertain, "MIGRATION_REMOTE_EXEC_UNCERTAIN")

    running = HttpResponse(
        payload={
            "data": {
                "status": "running",
                "session_id": "bash-session",
                "command_id": "command-1",
                "offset": 0,
                "stderr_offset": 0,
            }
        }
    )
    monkeypatch.setattr(
        gateway_module.requests, "post", lambda *_args, **_kwargs: running
    )
    monotonic = iter([0.0, 100.0])
    monkeypatch.setattr(gateway_module.time, "monotonic", lambda: next(monotonic))
    with pytest.raises(MigrationGatewayError) as timed_out:
        adapter.execute_bash(
            session(),
            "true",
            operation="prepare_source",
            timeout_seconds=1,
        )
    assert_code(timed_out, "MIGRATION_REMOTE_EXEC_TIMEOUT")

    calls = 0

    def post(*_args: object, **_kwargs: object) -> HttpResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return running
        raise requests.ConnectionError("poll failed")

    monkeypatch.setattr(gateway_module.requests, "post", post)
    monkeypatch.setattr(gateway_module.time, "monotonic", lambda: 0.0)
    with pytest.raises(MigrationGatewayError) as poll_uncertain:
        adapter.execute_bash(
            session(),
            "true",
            operation="prepare_source",
            timeout_seconds=1,
        )
    assert_code(poll_uncertain, "MIGRATION_REMOTE_EXEC_UNCERTAIN")


def test_delete_session_is_idempotent_only_for_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SimpleNamespace(
        delete_session=lambda _request: (_ for _ in ()).throw(RuntimeError("missing"))
    )
    adapter = gateway(client)
    monkeypatch.setattr(
        gateway_module,
        "is_agentkit_resource_not_found",
        lambda error: str(error) == "missing",
    )
    adapter.delete_session(session())

    client.delete_session = lambda _request: (_ for _ in ()).throw(
        RuntimeError("denied")
    )
    with pytest.raises(MigrationGatewayError) as raised:
        adapter.delete_session(session())
    assert_code(raised, "MIGRATION_SESSION_DELETE_FAILED")
