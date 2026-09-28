import asyncio
import sys

import pytest

from veadk.integrations.mpa.managed.tasks import CreationTasks, TaskError


def test_tasks_are_owner_scoped_and_duplicate_submission_reuses_identity(tmp_path):
    async def run():
        service = CreationTasks(tmp_path / "tasks.sqlite3")
        service.command = lambda: [sys.executable, "-c", "import time; time.sleep(30)"]
        payload = {
            "requestId": "11111111-1111-4111-8111-111111111111",
            "agentId": "mi-test",
            "description": "",
            "region": "cn-beijing",
        }
        task = await service.start(
            "owner", payload, config_path="not-read-by-fake", timeout=60
        )
        duplicate = await service.start(
            "owner", payload, config_path="not-read-by-fake", timeout=60
        )
        assert task["taskId"] == duplicate["taskId"]
        with pytest.raises(TaskError):
            service.get("someone-else", task["taskId"])
        with pytest.raises(TaskError):
            await service.start(
                "owner",
                {**payload, "description": "changed"},
                config_path="x",
                timeout=60,
            )
        with pytest.raises(TaskError):
            await service.start(
                "owner",
                {**payload, "pgHost": "different.example"},
                config_path="x",
                timeout=60,
            )
        await service.cancel("owner", task["taskId"])
        await service.close()
        assert service.get("owner", task["taskId"])["state"] == "cancelled"
        assert not service.running

    asyncio.run(run())


def test_raw_child_errors_never_reach_task_response(tmp_path):
    async def run():
        service = CreationTasks(tmp_path / "tasks.sqlite3")
        service.command = lambda: [
            sys.executable,
            "-c",
            "print('secret-should-not-escape'); raise SystemExit(1)",
        ]
        payload = {
            "requestId": "22222222-2222-4222-8222-222222222222",
            "agentId": "mi-test",
            "description": "",
            "region": "cn-beijing",
        }
        task = await service.start("owner", payload, config_path="unused", timeout=60)
        await asyncio.gather(*service.running.values())
        result = service.get("owner", task["taskId"])
        assert result["state"] == "failed"
        assert "secret-should-not-escape" not in str(result)
        await service.close()

    asyncio.run(run())


def test_studio_task_sends_builtin_profile_marker_to_child(tmp_path):
    import json

    async def run():
        service = CreationTasks(tmp_path / "tasks.sqlite3")
        received = tmp_path / "profile.json"
        code = (
            "import json,sys,pathlib; "
            "data=json.loads(sys.stdin.read()); "
            f"pathlib.Path({str(received)!r}).write_text(json.dumps(data['config'])); "
            "print('MPA_EVENT '+json.dumps({'result': "
            "{'runtime_id':'r-test','skill_space_id':'ss-test',"
            "'gateway_id':'gw-test','agent_id':'mi-test',"
            "'region':'cn-beijing','state':'ready'}}))"
        )
        service.command = lambda: [sys.executable, "-c", code]
        payload = {
            "requestId": "99999999-9999-4999-8999-999999999999",
            "agentId": "mi-test",
            "description": "",
            "region": "cn-beijing",
        }
        task = await service.start("owner", payload, config_path=None, timeout=60)
        await asyncio.gather(*service.running.values())
        assert service.get("owner", task["taskId"])["state"] == "succeeded"
        assert json.loads(received.read_text()) is None
        await service.close()

    asyncio.run(run())


def test_nonsecret_resource_choices_reach_child_and_retain_request_identity(tmp_path):
    import json

    async def run():
        service = CreationTasks(tmp_path / "tasks.sqlite3")
        received = tmp_path / "resources.json"
        result = {
            "runtime_id": "r-test",
            "skill_space_id": "ss-test",
            "gateway_id": "gw-test",
            "agent_id": "mi-test",
            "region": "cn-beijing",
            "state": "ready",
        }
        code = (
            "import json,sys,pathlib; "
            "data=json.loads(sys.stdin.read()); "
            f"pathlib.Path({str(received)!r}).write_text(json.dumps(data['resources'])); "
            f"print('MPA_EVENT '+json.dumps({{'result': {result!r}}}))"
        )
        service.command = lambda: [sys.executable, "-c", code]
        payload = {
            "requestId": "77777777-7777-4777-8777-777777777777",
            "agentId": "mi-test",
            "description": "",
            "region": "cn-beijing",
            "pgHost": "db.example",
            "pgPort": "5432",
            "openvikingUrl": "https://api.example.test/openviking",
            "openvikingResourceId": "ov-test",
        }
        task = await service.start("owner", payload, config_path="unused", timeout=60)
        await asyncio.gather(*service.running.values())
        assert service.get("owner", task["taskId"])["state"] == "succeeded"
        assert json.loads(received.read_text()) == {
            key: payload[key]
            for key in ("pgHost", "pgPort", "openvikingUrl", "openvikingResourceId")
        }
        await service.close()

    asyncio.run(run())


def test_openviking_key_reaches_child_without_persisting_or_returning_it(tmp_path):
    import json

    async def run():
        service = CreationTasks(tmp_path / "tasks.sqlite3")
        received = tmp_path / "received.json"
        result = {
            "runtime_id": "r-test",
            "skill_space_id": "ss-test",
            "gateway_id": "gw-test",
            "agent_id": "mi-test",
            "region": "cn-beijing",
            "state": "ready",
        }
        code = (
            "import json,sys,pathlib; "
            "data=json.loads(sys.stdin.read()); "
            f"pathlib.Path({str(received)!r}).write_text("
            "json.dumps(data['resources'])); "
            f"print('MPA_EVENT '+json.dumps({{'result': {result!r}}}))"
        )
        service.command = lambda: [sys.executable, "-c", code]
        payload = {
            "requestId": "88888888-8888-4888-8888-888888888888",
            "agentId": "mi-test",
            "description": "",
            "region": "cn-beijing",
            "openvikingUrl": "https://api.example.test/openviking",
            "openvikingResourceId": "ov-test",
        }
        secret = "private-ov-key-for-test"
        with pytest.raises(TaskError, match="Secrets"):
            await service.start(
                "owner",
                {**payload, "openvikingApiKey": secret},
                config_path="unused",
                timeout=60,
            )
        task = await service.start(
            "owner",
            payload,
            config_path="unused",
            timeout=60,
            secrets={"openvikingApiKey": secret},
        )
        await asyncio.gather(*service.running.values())
        assert json.loads(received.read_text())["openvikingApiKey"] == secret
        assert secret not in str(task)
        assert secret not in str(service.get("owner", task["taskId"]))
        assert secret.encode() not in service.path.read_bytes()
        await service.close()

    asyncio.run(run())


def test_stopped_supervisor_retries_original_task_without_nested_writer(tmp_path):
    async def run():
        service = CreationTasks(tmp_path / "tasks.sqlite3")
        service.command = lambda: [sys.executable, "-c", "import time; time.sleep(30)"]
        payload = {
            "requestId": "33333333-3333-4333-8333-333333333333",
            "agentId": "mi-test",
            "description": "",
            "region": "cn-beijing",
        }
        task = await service.start("owner", payload, config_path="unused", timeout=60)
        await service.cancel("owner", task["taskId"])
        service._update(task["taskId"], state="running", supervisor=99999999)
        resumed = await service.start(
            "owner", payload, config_path="unused", timeout=60
        )
        assert resumed["taskId"] == task["taskId"]
        await service.close()

    asyncio.run(run())


def test_task_store_closes_connections(tmp_path):
    import sqlite3

    service = CreationTasks(tmp_path / "tasks.sqlite3")
    with service.db() as connection:
        connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_timeout_reaps_child_before_reporting_terminal_state(tmp_path):
    import os

    async def run():
        service = CreationTasks(tmp_path / "tasks.sqlite3")
        pid_file = tmp_path / "child.pid"
        service.command = lambda: [
            sys.executable,
            "-c",
            f"import os,time,pathlib; pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(30)",
        ]
        payload = {
            "requestId": "44444444-4444-4444-8444-444444444444",
            "agentId": "mi-test",
            "description": "",
            "region": "cn-beijing",
        }
        task = await service.start("owner", payload, config_path="unused", timeout=0.1)
        await asyncio.wait_for(asyncio.gather(*service.running.values()), 5)
        result = service.get("owner", task["taskId"])
        assert result["state"] == "failed" and result["error"] == "timeout"
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)
        await service.close()

    asyncio.run(run())


@pytest.mark.parametrize("extra", [False, True])
def test_success_requires_allowlisted_matching_result(tmp_path, extra):
    import json

    async def run():
        service = CreationTasks(tmp_path / "tasks.sqlite3")
        result = {
            "runtime_id": "r-test",
            "skill_space_id": "space-test",
            "gateway_id": "g-test",
            "agent_id": "mi-test",
            "region": "cn-beijing",
            "state": "ready",
        }
        if extra:
            result["token"] = "not-returned"
        event = "MPA_EVENT " + json.dumps({"result": result})
        service.command = lambda: [sys.executable, "-c", f"print({event!r})"]
        payload = {
            "requestId": "55555555-5555-4555-8555-555555555555",
            "agentId": "mi-test",
            "description": "",
            "region": "cn-beijing",
        }
        task = await service.start("owner", payload, config_path="unused", timeout=60)
        await asyncio.gather(*service.running.values())
        final = service.get("owner", task["taskId"])
        assert final["state"] == ("failed" if extra else "succeeded")
        assert "not-returned" not in str(final)
        if not extra:
            assert (
                await service.start("owner", payload, config_path="unused", timeout=60)
            )["taskId"] == task["taskId"]
            assert not service.running
        await service.close()

    asyncio.run(run())


def test_duplicate_cancel_and_shutdown_do_not_interrupt_reaping(tmp_path):
    import os
    import signal

    async def run():
        service = CreationTasks(tmp_path / "tasks.sqlite3")
        pid_file = tmp_path / "child.pid"
        service.command = lambda: [
            sys.executable,
            "-c",
            f"import os,time,pathlib,signal; signal.signal(signal.SIGTERM,signal.SIG_IGN); pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(30)",
        ]
        payload = {
            "requestId": "66666666-6666-4666-8666-666666666666",
            "agentId": "mi-test",
            "description": "",
            "region": "cn-beijing",
        }
        task = await service.start("owner", payload, config_path="unused", timeout=60)

        async def started():
            while not pid_file.exists():
                await asyncio.sleep(0.01)

        await asyncio.wait_for(started(), 3)
        pid = int(pid_file.read_text())
        try:
            cancelling = asyncio.create_task(service.cancel("owner", task["taskId"]))
            # Let the first cancellation enter the child termination grace period.
            await asyncio.sleep(0.05)
            await asyncio.gather(
                cancelling, service.cancel("owner", task["taskId"]), service.close()
            )
            assert service.get("owner", task["taskId"])["state"] == "cancelled"
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
        finally:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    asyncio.run(run())
