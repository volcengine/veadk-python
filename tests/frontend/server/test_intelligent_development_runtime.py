from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

from frontend.server.intelligent_development import StudioCredentials
from frontend.server.intelligent_development_runtime import (
    IntelligentDevelopmentRuntimeOperations,
)


RUNTIME_NAME = "idv-session-abc123"
CREDENTIALS = StudioCredentials("access-id", "secret-key", "session-token")


class JsonResponse:
    def __init__(self, value: dict[str, object]) -> None:
        self.value = value

    def model_dump_json(self, *, by_alias: bool) -> str:
        assert by_alias is True
        return json.dumps(self.value, separators=(",", ":"))


class FakeClient:
    def __init__(self, runtimes: list[SimpleNamespace] | None = None) -> None:
        self.runtimes = runtimes or []
        self.requests: list[tuple[str, object]] = []
        self.instances: list[SimpleNamespace] = []
        self.logs: dict[str, str | None] = {}

    def list_runtimes(self, request):
        self.requests.append(("list", request))
        return SimpleNamespace(agent_kit_runtimes=self.runtimes, next_token=None)

    def get_runtime(self, request):
        self.requests.append(("get", request))
        return JsonResponse({"RuntimeId": request.runtime_id, "Status": "Ready"})

    def update_runtime(self, request):
        self.requests.append(("tag", request))
        return SimpleNamespace()

    def list_runtime_instances(self, request):
        self.requests.append(("list-instances", request))
        return SimpleNamespace(instance_items=self.instances)

    def get_runtime_instance_logs(self, request):
        self.requests.append(("logs", request))
        return SimpleNamespace(logs=self.logs.get(request.instance_name))

    def delete_runtime(self, request):
        self.requests.append(("delete", request))
        return SimpleNamespace()


def _runtime(name: str = RUNTIME_NAME, runtime_id: str | None = "runtime-1"):
    return SimpleNamespace(name=name, runtime_id=runtime_id)


def _operations(client: FakeClient) -> IntelligentDevelopmentRuntimeOperations:
    operations = IntelligentDevelopmentRuntimeOperations(lambda: "cn-beijing")
    operations._client = lambda credentials: client
    return operations


def _run(
    client: FakeClient,
    operation: str,
    arguments: tuple[str, ...] = (),
):
    return _operations(client)._run(operation, RUNTIME_NAME, CREDENTIALS, arguments)


def test_client_uses_fresh_credentials_and_resolved_region(monkeypatch) -> None:
    captured: list[dict[str, object]] = []

    class Client:
        def __init__(self, **kwargs: object) -> None:
            captured.append(kwargs)

    monkeypatch.setattr("agentkit.sdk.runtime.client.AgentkitRuntimeClient", Client)
    regions: list[str] = []
    operations = IntelligentDevelopmentRuntimeOperations(
        lambda: regions.append("resolved") or "ap-southeast-1"
    )

    assert isinstance(operations._client(CREDENTIALS), Client)
    assert captured == [
        {
            "access_key": "access-id",
            "secret_key": "secret-key",
            "session_token": "session-token",
            "region": "ap-southeast-1",
        }
    ]
    assert regions == ["resolved"]

    without_token = StudioCredentials("other-access", "other-secret")
    operations._client(without_token)
    assert captured[-1]["session_token"] == ""
    assert captured[-1]["access_key"] == "other-access"


@pytest.mark.asyncio
async def test_async_entrypoint_forwards_operation_name_credentials_and_arguments(
    monkeypatch,
) -> None:
    operations = IntelligentDevelopmentRuntimeOperations(lambda: "unused")
    observed: list[tuple[object, ...]] = []

    def run(*arguments: object):
        observed.append(arguments)
        return SimpleNamespace(exit_code=0, stdout="ok")

    monkeypatch.setattr(operations, "_run", run)
    result = await operations("tag", RUNTIME_NAME, CREDENTIALS, ("[]",))
    assert result.stdout == "ok"
    assert observed == [("tag", RUNTIME_NAME, CREDENTIALS, ("[]",))]


@pytest.mark.asyncio
async def test_stale_validation_runtime_reconciler_deletes_only_expired_tags() -> None:
    client = FakeClient(
        [
            SimpleNamespace(
                runtime_id="stale",
                created_at="2020-01-01T00:00:00Z",
            ),
            SimpleNamespace(
                runtime_id="fresh",
                created_at="2099-01-01T00:00:00Z",
            ),
            SimpleNamespace(runtime_id=None, created_at=None),
            SimpleNamespace(runtime_id="naive", created_at="2020-01-01T00:00:00"),
            SimpleNamespace(runtime_id="invalid-date", created_at="invalid"),
        ]
    )
    operations = _operations(client)
    removed = await operations.cleanup_stale_validation_runtimes(
        lambda: CREDENTIALS,
    )
    assert removed == 2
    assert [request.runtime_id for kind, request in client.requests if kind == "delete"] == ["stale", "naive"]
    list_request = next(request for kind, request in client.requests if kind == "list")
    assert list_request.tag_filters[0].key == "veadk:lifecycle"

    class PagedClient(FakeClient):
        def __init__(self) -> None:
            super().__init__([])
            self.pages = 0

        def list_runtimes(self, request):
            self.pages += 1
            self.requests.append(("list", request))
            return SimpleNamespace(
                agent_kit_runtimes=[],
                next_token="next" if self.pages == 1 else None,
            )

    paged = PagedClient()
    assert _operations(paged)._cleanup_stale_validation_runtimes(
        CREDENTIALS, timedelta(hours=1)
    ) == 0
    assert paged.pages == 2
    with pytest.raises(ValueError, match="positive"):
        operations._cleanup_stale_validation_runtimes(CREDENTIALS, timedelta(0))


def test_runtime_resolution_uses_exact_name_filter_and_immutable_id() -> None:
    client = FakeClient(
        [
            _runtime("similar-name", "runtime-wrong"),
            _runtime(RUNTIME_NAME, None),
            _runtime(RUNTIME_NAME, "runtime-exact"),
        ]
    )

    result = _run(client, "get")

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "RuntimeId": "runtime-exact",
        "Status": "Ready",
    }
    list_request = client.requests[0][1]
    assert list_request.max_results == 10
    assert len(list_request.filters) == 1
    assert list_request.filters[0].name == "Name"
    assert list_request.filters[0].values == [RUNTIME_NAME]
    get_request = client.requests[1][1]
    assert get_request.runtime_id == "runtime-exact"


def test_runtime_name_ambiguity_fails_before_any_mutation() -> None:
    client = FakeClient([_runtime(runtime_id="runtime-1"), _runtime(runtime_id="runtime-2")])
    with pytest.raises(RuntimeError, match="ambiguous"):
        _run(client, "delete")
    assert [name for name, _ in client.requests] == ["list"]


@pytest.mark.parametrize("operation", ["get", "tag", "logs"])
def test_missing_runtime_is_reported_without_followup_calls(operation: str) -> None:
    client = FakeClient()
    arguments = ("[]",) if operation == "tag" else ()
    result = _run(client, operation, arguments)
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "Validation Runtime not found"
    assert [name for name, _ in client.requests] == ["list"]


def test_delete_uses_resolved_runtime_id() -> None:
    client = FakeClient([_runtime(runtime_id="runtime-delete")])
    result = _run(client, "delete")
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"runtimeId": "runtime-delete"}
    request = client.requests[-1][1]
    assert request.runtime_id == "runtime-delete"


def test_delete_is_idempotent_when_runtime_is_absent() -> None:
    client = FakeClient()
    first = _run(client, "delete")
    second = _run(client, "delete")
    assert first.exit_code == second.exit_code == 0
    assert json.loads(first.stdout) == json.loads(second.stdout) == {
        "alreadyAbsent": True
    }
    assert [name for name, _ in client.requests] == ["list", "list"]


def test_tag_validates_and_sends_only_exact_string_pairs() -> None:
    client = FakeClient([_runtime(runtime_id="runtime-tag")])
    raw = json.dumps(
        [
            {"Key": "intelligent-development", "Value": "validation"},
            {"Key": "runtime-name", "Value": RUNTIME_NAME},
        ]
    )
    result = _run(client, "tag", (raw,))
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"runtimeId": "runtime-tag"}
    request = client.requests[-1][1]
    assert request.runtime_id == "runtime-tag"
    assert [(tag.key, tag.value) for tag in request.tags] == [
        ("intelligent-development", "validation"),
        ("runtime-name", RUNTIME_NAME),
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        ("[]", "extra"),
        ("not-json",),
        ("{}",),
        (json.dumps(["bad"]),),
        (json.dumps([{"Key": "key"}]),),
        (json.dumps([{"Key": 1, "Value": "value"}]),),
        (json.dumps([{"Key": "key", "Value": 1}]),),
    ],
    ids=("missing", "extra", "bad-json", "not-list", "not-object", "missing-value", "bad-key", "bad-value"),
)
def test_tag_rejects_malformed_arguments_without_update(
    arguments: tuple[str, ...]
) -> None:
    client = FakeClient([_runtime()])
    with pytest.raises((ValueError, json.JSONDecodeError)):
        _run(client, "tag", arguments)
    assert "tag" not in [name for name, _ in client.requests]


def test_logs_use_runtime_id_skip_unnamed_instances_and_join_nonempty_logs() -> None:
    client = FakeClient([_runtime(runtime_id="runtime-logs")])
    client.instances = [
        SimpleNamespace(instance_name="instance-a"),
        SimpleNamespace(instance_name=""),
        SimpleNamespace(instance_name=None),
        SimpleNamespace(instance_name="instance-b"),
        SimpleNamespace(instance_name="instance-c"),
    ]
    client.logs = {
        "instance-a": "first log",
        "instance-b": None,
        "instance-c": "third log",
    }

    result = _run(client, "logs")

    assert result.exit_code == 0
    assert result.stdout == "first log\nthird log"
    instance_request = next(
        request for name, request in client.requests if name == "list-instances"
    )
    assert instance_request.runtime_id == "runtime-logs"
    log_requests = [request for name, request in client.requests if name == "logs"]
    assert [request.instance_name for request in log_requests] == [
        "instance-a",
        "instance-b",
        "instance-c",
    ]
    assert all(request.runtime_id == "runtime-logs" for request in log_requests)
    assert all(request.limit == 200 for request in log_requests)


def test_unsupported_operation_fails_without_mutation() -> None:
    client = FakeClient([_runtime()])
    with pytest.raises(ValueError, match="Unsupported"):
        _run(client, "restart")
    assert [name for name, _ in client.requests] == ["list"]
