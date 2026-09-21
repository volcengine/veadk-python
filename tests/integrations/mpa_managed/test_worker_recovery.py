"""Worker retries use persisted intent and never log provider payloads."""

import asyncio
import json
import sys
from unittest.mock import AsyncMock

import pytest
from agentkit.auth.errors import NetworkError
from agentkit.toolkit.errors import ApiError
from requests import HTTPError, Response

from tests.integrations.mpa_managed.test_agent_deployment import Registry
from veadk.integrations.mpa.managed.config import Worker
from veadk.integrations.mpa.managed.database import agent_suffix
from veadk.integrations.mpa.managed.worker import ensure_worker


def ready():
    return {
        "ToolId": "t-test",
        "ProjectName": "default",
        "Status": "Ready",
        "Tags": [
            {"Key": "managed_by", "Value": "mpa-deployment"},
            {"Key": "mpa_agent_key", "Value": agent_suffix("a", "r", "agent")},
        ],
        "Envs": [{"Key": "MPA_AGENT_ID", "Value": "agent"}],
    }


def test_create_timeout_and_owned_not_found_recover_with_same_token(monkeypatch):
    from veadk.integrations.mpa.managed import diagnostics

    async def run():
        monkeypatch.setattr(diagnostics.asyncio, "sleep", AsyncMock())
        cloud = AsyncMock()
        cloud.find.return_value = []
        cloud.create.side_effect = [TimeoutError("private payload"), "t-test"]
        cloud.get.side_effect = [
            ApiError("private URL", error_code="ResourceNotFound"),
            ready(),
        ]
        registry = Registry()
        events = []
        with diagnostics.diagnostic_scope(events.append):
            result = await ensure_worker(
                registry,
                cloud,
                Worker(image="worker:v1"),
                account="a",
                region="r",
                agent_id="agent",
            )
        assert result == "t-test"
        assert cloud.create.call_args_list[0] == cloud.create.call_args_list[1]
        assert (
            cloud.create.call_args.args[0]["ClientToken"]
            == registry.row["worker_token"]
        )
        assert [(x["operation"], x["category"], x["outcome"]) for x in events] == [
            ("create_worker", "timeout", "retrying"),
            ("get_worker", "not_found", "retrying"),
        ]
        assert "private" not in json.dumps(events)

    asyncio.run(run())


@pytest.mark.parametrize("reference", [True, False])
def test_reference_and_existing_not_found_fail_without_retry(monkeypatch, reference):
    from veadk.integrations.mpa.managed import diagnostics

    async def run():
        sleep = AsyncMock()
        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        cloud = AsyncMock()
        cloud.get.side_effect = ApiError("private", error_code="ResourceNotFound")
        options = (
            Worker(image="worker:v1", reference_id="t-ref")
            if reference
            else Worker(existing_id="t-existing")
        )
        with pytest.raises(ApiError):
            await ensure_worker(
                Registry(), cloud, options, account="a", region="r", agent_id="agent"
            )
        cloud.get.assert_awaited_once()
        cloud.create.assert_not_called()
        sleep.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize(
    "code", ["AccessDenied", "InvalidParameter", "UnknownProviderCode"]
)
def test_permanent_discovery_errors_do_not_create(monkeypatch, code):
    from veadk.integrations.mpa.managed import diagnostics

    async def run():
        sleep = AsyncMock()
        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        cloud = AsyncMock()
        cloud.find.side_effect = ApiError("private", error_code=code)
        with pytest.raises(ApiError):
            await ensure_worker(
                Registry(),
                cloud,
                Worker(image="worker:v1"),
                account="a",
                region="r",
                agent_id="agent",
            )
        cloud.find.assert_awaited_once()
        cloud.create.assert_not_called()
        sleep.assert_not_called()

    asyncio.run(run())


def test_exhaustion_is_bounded_and_reports_final_failure(monkeypatch):
    from veadk.integrations.mpa.managed import diagnostics

    async def run():
        sleep = AsyncMock()
        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        cloud = AsyncMock()
        cloud.find.side_effect = ApiError("private", error_code="Throttling")
        events = []
        with diagnostics.diagnostic_scope(events.append), pytest.raises(ApiError):
            await ensure_worker(
                Registry(),
                cloud,
                Worker(image="worker:v1"),
                account="a",
                region="r",
                agent_id="agent",
            )
        assert cloud.find.await_count == 4
        assert [call.args[0] for call in sleep.call_args_list] == [1, 2, 4]
        assert [e["attempt"] for e in events] == [1, 2, 3, 4]
        assert events[-1]["outcome"] == "failed"
        cloud.create.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("cancel", [True, False])
def test_cancel_or_deadline_stops_backoff_without_next_call(monkeypatch, cancel):
    from veadk.integrations.mpa.managed import diagnostics

    async def run():
        waiting = asyncio.Event()

        async def sleep(_):
            waiting.set()
            await asyncio.Future()

        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        cloud = AsyncMock()
        cloud.find.side_effect = TimeoutError()
        task = asyncio.create_task(
            ensure_worker(
                Registry(),
                cloud,
                Worker(image="worker:v1"),
                account="a",
                region="r",
                agent_id="agent",
                timeout=10 if cancel else 0.01,
            )
        )
        await waiting.wait()
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await task
        cloud.find.assert_awaited_once()
        cloud.create.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize(
    "status,category",
    [
        (401, "permission"),
        (403, "permission"),
        (404, "not_found"),
        (429, "throttled"),
        (503, "unavailable"),
        (400, "invalid_request"),
        (418, "provider_error"),
    ],
)
def test_sdk_network_wrapper_preserves_http_classification(status, category):
    from veadk.integrations.mpa.managed.diagnostics import classify_error

    response = Response()
    response.status_code = status
    cause = HTTPError("private token", response=response)
    wrapper = NetworkError("private URL")
    wrapper.__cause__ = cause
    assert classify_error(wrapper) == category


def test_unknown_error_text_is_never_used_for_retry_or_diagnostics():
    from veadk.integrations.mpa.managed.diagnostics import (
        classify_error,
        validate_diagnostic,
    )

    assert (
        classify_error(RuntimeError("TimeoutError AccessDenied 503 private"))
        == "unknown"
    )
    assert (
        validate_diagnostic(
            {
                "operation": "get_worker",
                "category": "timeout",
                "attempt": 1,
                "outcome": "retrying",
                "message": "private",
            }
        )
        is None
    )
    assert (
        validate_diagnostic(
            {
                "operation": "get_worker",
                "category": "private",
                "attempt": 1,
                "outcome": "retrying",
            }
        )
        is None
    )
    assert (
        validate_diagnostic(
            {
                "operation": "get_worker",
                "category": "timeout",
                "attempt": True,
                "outcome": "retrying",
            }
        )
        is None
    )


def test_task_diagnostic_history_survives_retry_and_is_bounded(tmp_path, caplog):
    from veadk.integrations.mpa.managed.tasks import CreationTasks

    async def run():
        service = CreationTasks(tmp_path / "tasks.db")
        valid = {
            "operation": "get_worker",
            "category": "not_found",
            "attempt": 1,
            "outcome": "retrying",
        }
        events = [
            {"stage": "worker"},
            {"diagnostic": {**valid, "message": "private"}},
            {"diagnostic": valid},
        ]
        script = (
            "import json; events="
            + repr(events)
            + "; [print('MPA_EVENT '+json.dumps(e)) for e in events]; raise SystemExit(1)"
        )
        service.command = lambda: [sys.executable, "-c", script]
        payload = {
            "requestId": "11111111-1111-4111-8111-111111111111",
            "agentId": "agent",
            "description": "",
            "region": "cn-beijing",
        }
        task = await service.start("owner", payload, config_path="unused", timeout=60)
        await asyncio.gather(*service.running.values())
        task_id = task["taskId"]
        with service.db() as db:
            rows = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM task_diagnostics WHERE task_id=? ORDER BY id",
                    (task_id,),
                )
            ]
        assert rows[0]["category"] == "not_found" and rows[0]["stage"] == "worker"
        assert rows[-1]["category"] == "child_exit"
        assert "private" not in json.dumps(rows) + caplog.text
        initial_id = rows[0]["id"]
        await service.start("owner", payload, config_path="unused", timeout=60)
        await asyncio.gather(*service.running.values())
        with service.db() as db:
            saved = db.execute(
                "SELECT id FROM task_diagnostics WHERE task_id=? ORDER BY id",
                (task_id,),
            ).fetchall()
        assert len(saved) == 4 and saved[0]["id"] == initial_id
        for _ in range(105):
            service.record_diagnostic(task_id, valid)
        service = CreationTasks(tmp_path / "tasks.db")
        with service.db() as db:
            rows = db.execute(
                "SELECT * FROM task_diagnostics WHERE task_id=? ORDER BY id", (task_id,)
            ).fetchall()
        assert len(rows) == 100 and rows[0]["id"] > initial_id
        assert "diagnostic" not in service.get("owner", task_id)

    asyncio.run(run())


def test_runner_final_failure_emits_only_safe_fields(monkeypatch, capsys):
    import io
    from veadk.integrations.mpa.managed import runner

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"config": "unused", "region": "cn-beijing"})),
    )

    def fail(*args, **kwargs):
        raise ApiError("private URL and credential", error_code="AccessDenied")

    monkeypatch.setattr(runner, "load_profile", fail)
    assert runner.main() == 1
    out = capsys.readouterr().out
    events = [
        json.loads(line[10:])
        for line in out.splitlines()
        if line.startswith("MPA_EVENT ")
    ]
    assert any(e.get("diagnostic", {}).get("category") == "permission" for e in events)
    assert "private" not in out


@pytest.mark.parametrize(
    "problem,category", [("ownership", "ownership"), ("failed", "resource_failed")]
)
def test_owned_worker_validation_does_not_retry(monkeypatch, problem, category):
    from veadk.integrations.mpa.managed import diagnostics
    from veadk.integrations.mpa.managed.database import DeploymentError

    async def run():
        sleep = AsyncMock()
        monkeypatch.setattr(diagnostics.asyncio, "sleep", sleep)
        registry = Registry()
        registry.row = {
            "worker_id": "t-test",
            "worker_token": "intent",
            "worker_managed": True,
        }
        tool = ready()
        if problem == "ownership":
            tool["Tags"] = [{"Key": "managed_by", "Value": "another-owner"}]
        else:
            tool["Status"] = "Failed"
        cloud = AsyncMock()
        cloud.get.return_value = tool
        with pytest.raises(DeploymentError) as failure:
            await ensure_worker(
                registry,
                cloud,
                Worker(image="worker:v1"),
                account="a",
                region="r",
                agent_id="agent",
            )
        assert diagnostics.classify_error(failure.value) == category
        cloud.get.assert_awaited_once()
        sleep.assert_not_called()
        cloud.create.assert_not_called()

    asyncio.run(run())


def test_transport_errors_and_certificate_failure_are_distinct():
    from requests.exceptions import ConnectionError, InvalidURL, SSLError, Timeout
    from veadk.integrations.mpa.managed.diagnostics import classify_error

    for cause, expected in [
        (ConnectionError("private"), "connection"),
        (Timeout("private"), "timeout"),
        (SSLError("private"), "invalid_request"),
        (InvalidURL("private"), "provider_error"),
    ]:
        wrapped = NetworkError("private")
        wrapped.__cause__ = cause
        assert classify_error(wrapped) == expected


def test_runner_scope_covers_async_worker_events(monkeypatch, capsys):
    import io
    from types import SimpleNamespace
    from veadk.integrations.mpa.managed import diagnostics, runner

    async def provision(*args, **kwargs):
        kwargs["progress"]("worker")
        await diagnostics.retry_worker(
            "find_worker", AsyncMock(side_effect=TimeoutError("private"))
        )

    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "config": "unused",
                    "region": "cn-beijing",
                    "owner": "local",
                    "agentId": "agent",
                    "description": "",
                }
            )
        ),
    )
    monkeypatch.setattr(
        runner,
        "load_profile",
        lambda *args, **kwargs: SimpleNamespace(
            managed=SimpleNamespace(timeout_seconds=5)
        ),
    )
    monkeypatch.setattr(runner, "with_creation_images", lambda profile, images: profile)
    monkeypatch.setattr(runner, "provision", provision)
    monkeypatch.setattr(diagnostics.asyncio, "sleep", AsyncMock())
    assert runner.main() == 1
    output = capsys.readouterr().out
    events = [json.loads(line[10:]) for line in output.splitlines()]
    assert events[0] == {"stage": "worker"}
    assert (
        sum(e.get("diagnostic", {}).get("outcome") == "retrying" for e in events) == 3
    )
    assert events[-1] == {"error": "creationFailed"}
    assert "private" not in output
