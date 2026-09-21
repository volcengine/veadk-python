from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.mpa.test_scenarios import mount_test_scenario_routes


def _token_file(tmp_path: Path, token: str = "scenario-token") -> Path:
    path = tmp_path / "scenario.token"
    path.write_text(token, encoding="utf-8")
    path.chmod(0o600)
    return path


def test_routes_are_absent_outside_explicit_test_mode(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()

    assert mount_test_scenario_routes(app, token_file=_token_file(tmp_path)) is False
    assert TestClient(app).get("/__test/mpa/scenarios").status_code == 404


def test_routes_require_loopback_and_bearer_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    assert mount_test_scenario_routes(app, token_file=_token_file(tmp_path)) is True
    client = TestClient(app)

    assert client.get("/__test/mpa/scenarios").status_code == 401
    assert (
        client.get(
            "/__test/mpa/scenarios",
            headers={
                "Authorization": "Bearer scenario-token",
                "X-MPA-Test-Remote-Addr": "198.51.100.7",
            },
        ).status_code
        == 403
    )
    response = client.get(
        "/__test/mpa/scenarios",
        headers={"Authorization": "Bearer scenario-token"},
    )
    assert response.status_code == 200
    assert response.json() == {"scenarios": []}


def test_scenario_barrier_and_call_count_are_deterministic(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app, headers={"Authorization": "Bearer scenario-token"})

    created = client.put(
        "/__test/mpa/scenarios/turn_lifecycle",
        json={"barriers": ["participant_ack"]},
    )
    assert created.status_code == 200
    assert (
        client.post("/__test/mpa/scenarios/turn_lifecycle/calls/dispatch").json()[
            "count"
        ]
        == 1
    )
    assert (
        client.post(
            "/__test/mpa/scenarios/turn_lifecycle/barriers/participant_ack/release"
        ).status_code
        == 200
    )
    state = client.get("/__test/mpa/scenarios/turn_lifecycle").json()
    assert state["calls"] == {"dispatch": 1}
    assert state["barriers"] == {"participant_ack": "released"}


def test_create_success_scenario_isolates_the_complete_public_write_chain(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app)
    control_headers = {"Authorization": "Bearer scenario-token"}

    seeded = client.put(
        "/__test/mpa/scenarios/create_success",
        headers=control_headers,
        json={"barriers": []},
    )
    assert seeded.status_code == 200

    availability = client.get(
        "/web/runtime-name-availability",
        params={"name": "scenario-runtime", "region": "cn-beijing"},
    )
    assert availability.status_code == 200
    assert availability.json() == {"available": True}

    generated = client.post(
        "/web/generated-agent-projects",
        json={
            "draft": {
                "name": "scenario-agent",
                "description": "Scenario Agent",
                "instruction": "Stay isolated.",
            }
        },
    )
    assert generated.status_code == 200
    assert generated.json()["name"] == "scenario_agent"
    assert generated.json()["files"]

    deployed = client.post(
        "/web/deploy-agentkit",
        json={
            "name": "scenario_agent",
            "files": generated.json()["files"],
            "config": {"region": "cn-beijing", "projectName": "default"},
            "runtimeName": "scenario-runtime",
            "agentCategory": "mpa",
            "taskId": "scenario-task",
        },
    )
    assert deployed.status_code == 200
    assert '"done": true' in deployed.text
    assert "runtime-mpa-s2" in deployed.text

    operation_payload = {
        "operationKind": "create",
        "runtimeId": "runtime-mpa-s2",
        "region": "cn-beijing",
        "mpaInstanceId": "runtime-mpa-s2",
        "sourceProfileId": "studio-agent:scenario-agent:scenario-task",
        "targetKey": "runtime:cn-beijing:scenario-runtime",
        "profile": {
            "name": "scenario-agent",
            "description": "Scenario Agent",
            "system": "Stay isolated.",
            "model": {},
            "tools": [],
            "skills": [],
            "mcpServers": [],
            "metadata": {"veadk:agent-type": "mpa"},
        },
    }
    created = client.post(
        "/web/mpa/agents",
        headers={"Idempotency-Key": "scenario-task:mpa-profile"},
        json=operation_payload,
    )
    assert created.status_code == 202
    assert created.json()["status"] == "succeeded"
    assert created.json()["stage"] == "runnable"

    listed = client.get("/web/mpa/agent-operations", params={"status": "active"})
    recovered = client.get(f"/web/mpa/agent-operations/{created.json()['operationId']}")
    assert listed.status_code == 200
    assert listed.json() == {"operations": []}
    assert recovered.status_code == 200
    assert recovered.json() == created.json()

    state = client.get(
        "/__test/mpa/scenarios/create_success", headers=control_headers
    ).json()
    assert state["calls"] == {
        "runtime-name-availability": 1,
        "generated-agent-projects": 1,
        "deploy-agentkit": 1,
        "mpa-agent-create": 1,
        "mpa-operation-list": 1,
        "mpa-operation-get": 1,
    }
    assert state["data"]["payloads"]["deploy-agentkit"][0]["agentCategory"] == "mpa"
    assert state["data"]["payloads"]["mpa-agent-create"][0] == operation_payload


def test_creation_failure_scenarios_retry_without_redeploying_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app)
    control_headers = {"Authorization": "Bearer scenario-token"}
    operation_payload = {
        "operationKind": "create",
        "runtimeId": "runtime-mpa-s2",
        "region": "cn-beijing",
        "mpaInstanceId": "runtime-mpa-s2",
        "sourceProfileId": "studio-agent:scenario-agent:scenario-task",
        "targetKey": "runtime:cn-beijing:scenario-runtime",
        "profile": {
            "name": "scenario-agent",
            "description": "Scenario Agent",
            "system": "Stay isolated.",
            "model": {},
            "tools": [],
            "skills": [],
            "mcpServers": [],
            "metadata": {"veadk:agent-type": "mpa"},
        },
    }
    expected = {
        "profile_apply_failed": ("profile_applying", "profile_apply_failed"),
        "smoke_worker_not_ready": ("smoke_running", "smoke_worker_not_ready"),
        "smoke_output_mismatch": ("smoke_running", "smoke_output_mismatch"),
        "cleanup_failed": ("smoke_running", "cleanup_failed"),
    }

    for scenario, (stage, error_code) in expected.items():
        seeded = client.put(
            f"/__test/mpa/scenarios/{scenario}",
            headers=control_headers,
            json={"barriers": ["retry_complete"]},
        )
        assert seeded.status_code == 200

        deployed = client.post(
            "/web/deploy-agentkit",
            json={
                "name": "scenario_agent",
                "files": [{"path": "app.py", "content": "# isolated\n"}],
                "config": {"region": "cn-beijing"},
                "runtimeName": "scenario-runtime",
                "agentCategory": "mpa",
            },
        )
        assert deployed.status_code == 200

        failed = client.post(
            "/web/mpa/agents",
            headers={"Idempotency-Key": f"{scenario}:mpa-profile"},
            json=operation_payload,
        )
        assert failed.status_code == 202
        failed_body = failed.json()
        assert failed_body["status"] == "failed_retryable"
        assert failed_body["stage"] == stage
        assert failed_body["safeErrorCode"] == error_code
        view = client.get(
            "/web/mpa/agents/runtime-mpa-s2/view",
            params={"region": "cn-beijing"},
        )
        assert view.status_code == 200
        assert view.json()["activeOperation"] == failed_body
        assert view.json()["capabilities"]["canDebug"] is False

        replay = client.post(
            "/web/mpa/agents",
            headers={"Idempotency-Key": f"{scenario}:mpa-profile"},
            json=operation_payload,
        )
        assert replay.status_code == 202
        assert replay.json() == failed_body
        active = client.get("/web/mpa/agent-operations", params={"status": "active"})
        assert active.status_code == 200
        assert active.json()["operations"] == [failed_body]

        retry_result: dict[str, object] = {}

        def retry_operation() -> None:
            response = client.post(
                f"/web/mpa/agent-operations/{failed_body['operationId']}/retry",
                json=operation_payload,
            )
            retry_result["status"] = response.status_code
            retry_result["body"] = response.json()

        thread = threading.Thread(target=retry_operation)
        thread.start()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            scenario_state = client.get(
                f"/__test/mpa/scenarios/{scenario}", headers=control_headers
            ).json()
            if scenario_state["calls"].get("mpa-operation-retry") == 1:
                break
            time.sleep(0.01)
        assert thread.is_alive()

        released = client.post(
            f"/__test/mpa/scenarios/{scenario}/barriers/retry_complete/release",
            headers=control_headers,
        )
        assert released.status_code == 200
        thread.join(timeout=2)
        assert thread.is_alive() is False
        assert retry_result["status"] == 202
        assert retry_result["body"]["status"] == "succeeded"
        assert retry_result["body"]["stage"] == "runnable"
        assert retry_result["body"]["retryCount"] == 1
        recovered_view = client.get(
            "/web/mpa/agents/runtime-mpa-s2/view",
            params={"region": "cn-beijing"},
        )
        assert recovered_view.json()["activeOperation"] is None
        assert recovered_view.json()["capabilities"]["canDebug"] is True

        state = client.get(
            f"/__test/mpa/scenarios/{scenario}", headers=control_headers
        ).json()
        assert state["calls"]["deploy-agentkit"] == 1
        assert state["calls"]["mpa-agent-create"] == 2
        assert state["calls"]["mpa-operation-retry"] == 1


def test_create_success_deploy_can_be_held_busy_without_completing_early(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app)
    control_headers = {"Authorization": "Bearer scenario-token"}
    client.put(
        "/__test/mpa/scenarios/create_success",
        headers=control_headers,
        json={"barriers": ["deploy_complete"]},
    )
    result: dict[str, object] = {}

    def deploy() -> None:
        response = client.post(
            "/web/deploy-agentkit",
            json={
                "name": "scenario_agent",
                "files": [{"path": "app.py", "content": "# isolated\n"}],
                "config": {"region": "cn-beijing"},
                "runtimeName": "scenario-runtime",
                "agentCategory": "mpa",
            },
        )
        result["status"] = response.status_code
        result["text"] = response.text

    thread = threading.Thread(target=deploy)
    thread.start()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        scenario_state = client.get(
            "/__test/mpa/scenarios/create_success", headers=control_headers
        ).json()
        if scenario_state["calls"].get("deploy-agentkit") == 1:
            break
        time.sleep(0.01)
    assert thread.is_alive()

    client.post(
        "/__test/mpa/scenarios/create_success/barriers/deploy_complete/release",
        headers=control_headers,
    )
    thread.join(timeout=2)
    assert thread.is_alive() is False
    assert result["status"] == 200
    assert '"done": true' in str(result["text"])


def test_create_success_operation_is_recoverable_while_completion_is_blocked(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app)
    control_headers = {"Authorization": "Bearer scenario-token"}
    client.put(
        "/__test/mpa/scenarios/create_success",
        headers=control_headers,
        json={"barriers": ["operation_complete"]},
    )
    result: dict[str, object] = {}
    payload = {
        "operationKind": "create",
        "runtimeId": "runtime-mpa-s2",
        "region": "cn-beijing",
        "mpaInstanceId": "runtime-mpa-s2",
        "sourceProfileId": "studio-agent:scenario-agent:scenario-task",
        "targetKey": "runtime:cn-beijing:scenario-runtime",
        "profile": {
            "name": "scenario-agent",
            "system": "Stay isolated.",
            "model": {},
            "tools": [],
            "skills": [],
            "mcpServers": [],
            "metadata": {"veadk:agent-type": "mpa"},
        },
    }

    def create_operation() -> None:
        response = client.post(
            "/web/mpa/agents",
            headers={"Idempotency-Key": "scenario-task:mpa-profile"},
            json=payload,
        )
        result["status"] = response.status_code
        result["body"] = response.json()

    thread = threading.Thread(target=create_operation)
    thread.start()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        scenario_state = client.get(
            "/__test/mpa/scenarios/create_success", headers=control_headers
        ).json()
        if scenario_state["calls"].get("mpa-agent-create") == 1:
            break
        time.sleep(0.01)
    assert thread.is_alive()

    active = client.get("/web/mpa/agent-operations", params={"status": "active"})
    assert active.status_code == 200
    active_operation = active.json()["operations"][0]
    assert active_operation["status"] == "active"
    assert active_operation["stage"] == "profile_applying"
    recovered = client.get(
        f"/web/mpa/agent-operations/{active_operation['operationId']}"
    )
    assert recovered.json() == active_operation

    client.post(
        "/__test/mpa/scenarios/create_success/barriers/operation_complete/release",
        headers=control_headers,
    )
    thread.join(timeout=2)
    assert thread.is_alive() is False
    assert result["status"] == 202
    assert result["body"]["status"] == "succeeded"
    terminal = client.get(
        f"/web/mpa/agent-operations/{active_operation['operationId']}"
    )
    assert terminal.json()["stage"] == "runnable"


def test_slow_scope_switch_isolates_principal_region_and_denied_results(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app)
    control_headers = {"Authorization": "Bearer scenario-token"}
    client.put(
        "/__test/mpa/scenarios/slow_scope_switch",
        headers=control_headers,
        json={"barriers": ["old_scope_response"]},
    )
    old_result: dict[str, object] = {}

    def load_old_scope() -> None:
        response = client.get(
            "/web/runtimes",
            headers={"X-VeADK-Local-User": "alice"},
            params={
                "agentCategory": "mpa",
                "scope": "mine",
                "region": "cn-beijing",
            },
        )
        old_result["status"] = response.status_code
        old_result["body"] = response.json()

    thread = threading.Thread(target=load_old_scope)
    thread.start()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        scenario_state = client.get(
            "/__test/mpa/scenarios/slow_scope_switch", headers=control_headers
        ).json()
        if scenario_state["calls"].get("runtime-list-old") == 1:
            break
        time.sleep(0.01)
    assert thread.is_alive()

    current = client.get(
        "/web/runtimes",
        headers={"X-VeADK-Local-User": "bob"},
        params={
            "agentCategory": "mpa",
            "scope": "mine",
            "region": "cn-shanghai",
        },
    )
    assert current.status_code == 200
    assert current.json()["runtimes"][0]["name"] == "MPA Scope Bob"
    assert current.json()["runtimes"][0]["runtimeId"] == "runtime-same-id"

    denied = client.get(
        "/web/mpa/agents/runtime-same-id/view",
        headers={"X-VeADK-Local-User": "mallory"},
        params={"region": "cn-shanghai"},
    )
    assert denied.status_code == 404
    assert denied.json() == {"detail": "resource_not_found"}

    client.post(
        "/__test/mpa/scenarios/slow_scope_switch/barriers/old_scope_response/release",
        headers=control_headers,
    )
    thread.join(timeout=2)
    assert thread.is_alive() is False
    assert old_result["status"] == 200
    assert old_result["body"]["runtimes"][0]["name"] == "MPA Scope Alice"
    assert old_result["body"]["runtimes"][0]["runtimeId"] == "runtime-same-id"

    state = client.get(
        "/__test/mpa/scenarios/slow_scope_switch", headers=control_headers
    ).json()
    assert state["calls"] == {
        "runtime-list-old": 1,
        "runtime-list-current": 1,
        "mpa-view-denied": 1,
    }


def test_agent_view_scenarios_expose_binding_states_through_public_route(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app, headers={"Authorization": "Bearer scenario-token"})

    expected = {
        "session_revision_6": ("bound", True, True),
        "runtime_missing": ("runtime_missing", False, False),
        "binding_ambiguous": ("binding_ambiguous", False, False),
        "orphan_runtime": ("orphan_runtime", True, False),
        "old_runtime": ("bound", False, False),
    }
    for scenario, (binding_status, can_write, can_debug) in expected.items():
        client.put(f"/__test/mpa/scenarios/{scenario}", json={"barriers": []})
        response = client.get(
            "/web/mpa/agents/runtime-mpa-s2/view",
            params={"region": "cn-beijing"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["bindingStatus"] == binding_status
        assert body["capabilities"]["canWrite"] is can_write
        assert body["capabilities"]["canDebug"] is can_debug


def test_turn_lifecycle_scenario_serves_control_and_continuation_contract(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app, headers={"Authorization": "Bearer scenario-token"})

    seeded = client.put(
        "/__test/mpa/scenarios/turn_lifecycle",
        json={"barriers": ["primary_ack", "worker_1_ack", "worker_2_ack"]},
    )
    assert seeded.status_code == 200

    agent_info = client.get(
        "/web/runtime-proxy/runtime-mpa-s2/web/agent-info/a2a-default"
    )
    assert agent_info.status_code == 200
    assert agent_info.json()["turnLifecycleControl"] == {
        "actions": ["pause", "resume"],
        "pauseMode": "cooperative-safe-point",
        "processReplacementResume": False,
    }

    initial = client.get(
        "/web/runtime-proxy/runtime-mpa-s2/"
        "api/v1/a2a/tasks/by-session/turn_lifecycle-session/control"
    )
    assert initial.status_code == 200
    assert initial.json()["state"] == "running"
    assert initial.json()["allowedActions"] == ["pause"]

    pausing = client.post(
        "/web/runtime-proxy/runtime-mpa-s2/"
        "api/v1/a2a/tasks/by-session/turn_lifecycle-session/control/pause",
        headers={"Idempotency-Key": "pause-key"},
        json={"expectedGeneration": 0},
    )
    assert pausing.status_code == 200
    assert pausing.json()["state"] == "pausing"
    assert pausing.json()["allowedActions"] == []

    client.post("/__test/mpa/scenarios/turn_lifecycle/barriers/primary_ack/release")
    partial = client.get(
        "/web/runtime-proxy/runtime-mpa-s2/api/v1/a2a/tasks/turn_lifecycle-task/control"
    )
    assert partial.status_code == 200
    assert partial.json()["state"] == "pausing"

    client.post("/__test/mpa/scenarios/turn_lifecycle/barriers/worker_1_ack/release")
    client.post("/__test/mpa/scenarios/turn_lifecycle/barriers/worker_2_ack/release")
    paused = client.get(
        "/web/runtime-proxy/runtime-mpa-s2/"
        "api/v1/a2a/tasks/by-session/turn_lifecycle-session/control"
    )
    assert paused.status_code == 200
    assert paused.json()["state"] == "paused"
    assert paused.json()["allowedActions"] == ["resume"]

    resumed = client.post(
        "/web/runtime-proxy/runtime-mpa-s2/"
        "api/v1/a2a/tasks/by-session/turn_lifecycle-session/control/resume",
        headers={"Idempotency-Key": "resume-key"},
        json={"expectedGeneration": 1},
    )
    assert resumed.status_code == 200
    assert resumed.json()["state"] == "running"
    assert resumed.json()["generation"] == 2

    new_turn = client.post("/__test/mpa/scenarios/turn_lifecycle/new-turn-required")
    assert new_turn.status_code == 200
    assert new_turn.json()["resumeDisposition"] == "new_turn_required"
    assert new_turn.json()["allowedActions"] == ["resume"]

    resume_again = client.post(
        "/web/runtime-proxy/runtime-mpa-s2/"
        "api/v1/a2a/tasks/by-session/turn_lifecycle-session/control/resume",
        headers={"Idempotency-Key": "resume-new-turn"},
        json={"expectedGeneration": new_turn.json()["generation"]},
    )
    assert resume_again.status_code == 200
    assert resume_again.json()["resumeDisposition"] == "new_turn_required"

    continued = client.post(
        "/web/runtime-proxy/runtime-mpa-s2/"
        "api/v1/a2a/tasks/turn_lifecycle-task/continue",
        headers={"Idempotency-Key": "continue-key"},
        json={"expectedGeneration": new_turn.json()["generation"]},
    )
    replay = client.post(
        "/web/runtime-proxy/runtime-mpa-s2/"
        "api/v1/a2a/tasks/turn_lifecycle-task/continue",
        headers={"Idempotency-Key": "continue-key"},
        json={"expectedGeneration": new_turn.json()["generation"]},
    )
    assert continued.status_code == 200
    assert continued.json()["idempotentReplay"] is False
    assert continued.json()["continuationOf"] == "turn_lifecycle-turn"
    assert replay.status_code == 200
    assert replay.json()["turnId"] == continued.json()["turnId"]
    assert replay.json()["idempotentReplay"] is True

    sse = client.post(
        "/web/runtime-proxy/runtime-mpa-s2/api/v1/sessions/turn_lifecycle-session/sse",
        json={
            "invocationId": "turn_lifecycle-continued-invocation",
            "lastEventId": "event-before-continue",
        },
    )
    assert sse.status_code == 200
    assert "event-after-continue" in sse.text
    state = client.get("/__test/mpa/scenarios/turn_lifecycle").json()
    assert state["calls"]["runtime-continue"] == 1
    assert state["calls"]["runtime-continue-replay"] == 1
    assert state["data"]["payloads"]["control"] == [
        {
            "action": "pause",
            "expectedGeneration": 0,
            "idempotencyKey": "pause-key",
        },
        {
            "action": "resume",
            "expectedGeneration": 1,
            "idempotencyKey": "resume-key",
        },
        {
            "action": "resume",
            "expectedGeneration": new_turn.json()["generation"],
            "idempotencyKey": "resume-new-turn",
        },
    ]


def test_turn_lifecycle_stream_waits_for_explicit_completion_barrier(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app, headers={"Authorization": "Bearer scenario-token"})
    client.put(
        "/__test/mpa/scenarios/turn_lifecycle",
        json={"barriers": ["stream_complete"]},
    )
    result: dict[str, object] = {}

    def consume_stream() -> None:
        response = client.post(
            "/web/runtime-proxy/runtime-mpa-s2/"
            "api/v1/sessions/turn_lifecycle-session/sse",
            json={"invocationId": "turn_lifecycle-invocation"},
        )
        result["status"] = response.status_code
        result["text"] = response.text

    thread = threading.Thread(target=consume_stream)
    thread.start()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        state = client.get("/__test/mpa/scenarios/turn_lifecycle").json()
        if state["calls"].get("runtime-sse") == 1:
            break
        time.sleep(0.01)
    assert thread.is_alive()

    released = client.post(
        "/__test/mpa/scenarios/turn_lifecycle/barriers/stream_complete/release"
    )
    assert released.status_code == 200
    thread.join(timeout=2)
    assert thread.is_alive() is False
    assert result["status"] == 200
    assert "event-lifecycle-running" in str(result["text"])
    assert "event-after-refresh" in str(result["text"])


def test_session_revision_scenario_serves_studio_runtime_paths(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app)
    control_headers = {"Authorization": "Bearer scenario-token"}

    seed = client.put(
        "/__test/mpa/scenarios/session_revision_6",
        headers=control_headers,
        json={"barriers": []},
    )
    assert seed.status_code == 200

    runtimes = client.get(
        "/web/runtimes",
        params={"agentCategory": "mpa"},
    )
    assert runtimes.status_code == 200
    assert runtimes.json()["runtimes"][0]["agentCategory"] == "mpa"

    apps = client.get("/web/runtime-proxy/runtime-mpa-s2/list-apps")
    assert apps.status_code == 200
    assert apps.json() == ["a2a-default"]

    detail = client.get("/web/runtime-proxy/runtime-mpa-s2/web/agent-info/a2a-default")
    assert detail.status_code == 200
    assert detail.json()["name"] == "MPA S2 Fixture"

    assert client.get("/web/workspaces").json() == {"items": []}
    assert client.get("/web/v3/environments").json() == {"items": []}
    tool_capability = client.get(
        "/web/runtime-tool-channel/runtime-mpa-s2/capabilities",
        params={"region": "cn-beijing"},
    )
    assert tool_capability.status_code == 200
    assert tool_capability.json() == {
        "enabled": False,
        "supported": False,
        "tools": [],
    }

    created = client.post(
        "/web/runtime-proxy/runtime-mpa-s2/apps/a2a-default/users/scenario-user/sessions"
    )
    assert created.status_code == 200
    assert created.json()["id"] == "session-s2"

    profile_status = client.get(
        "/web/runtime-proxy/runtime-mpa-s2/api/v1/agents/runtime-mpa-s2/profile-status"
    )
    assert profile_status.status_code == 200
    assert profile_status.json()["profileRevision"] == 7

    mpa_created = client.post(
        "/web/runtime-proxy/runtime-mpa-s2/api/v1/sessions",
        json={"mpaInstanceId": "runtime-mpa-s2", "profileRevision": 7},
    )
    assert mpa_created.status_code == 200
    assert mpa_created.json()["sessionId"] == "session-s2"

    listed = client.get("/web/runtime-proxy/runtime-mpa-s2/api/v1/sessions")
    assert listed.status_code == 200
    assert listed.json() == [
        {
            "sessionId": "session-s2",
            "id": "session-s2",
            "appName": "a2a-default",
            "userId": "scenario-user",
            "mpaInstanceId": "runtime-mpa-s2",
            "profileRevision": 6,
        }
    ]

    events = client.get(
        "/web/runtime-proxy/runtime-mpa-s2/api/v1/sessions/session-s2/events"
    )
    assert events.status_code == 200
    assert events.json() == {"events": []}


def test_session_revision_scenario_provides_cas_current_state(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app, headers={"Authorization": "Bearer scenario-token"})
    client.put("/__test/mpa/scenarios/session_revision_6", json={"barriers": []})

    initial = client.get("/web/mpa/sessions/session-s2/execution-config")
    assert initial.status_code == 200
    assert initial.headers["etag"] == '"6"'

    first = client.patch(
        "/web/mpa/sessions/session-s2/execution-config",
        headers={"If-Match": '"6"'},
        json={
            "runtimeId": "runtime-mpa-s2",
            "region": "cn-beijing",
            "changes": [
                {"category": "model", "mode": "replace", "value": {"id": "model-a"}}
            ],
        },
    )
    assert first.status_code == 200
    assert first.json()["revision"] == 7

    stale = client.patch(
        "/web/mpa/sessions/session-s2/execution-config",
        headers={"If-Match": '"6"'},
        json={
            "runtimeId": "runtime-mpa-s2",
            "region": "cn-beijing",
            "changes": [{"category": "mcpServers", "mode": "clear"}],
        },
    )
    assert stale.status_code == 412
    payload = stale.json()["detail"]
    assert payload["code"] == "execution_config_changed"
    assert payload["currentState"]["revision"] == 7
    assert payload["currentState"]["effectiveRefs"]["model"] == {"id": "model-a"}


def test_session_revision_scenario_upgrades_profile_idempotently(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app, headers={"Authorization": "Bearer scenario-token"})
    client.put("/__test/mpa/scenarios/session_revision_6", json={"barriers": []})

    upgraded = client.post(
        "/web/mpa/sessions/session-s2/profile-upgrade",
        headers={"If-Match": '"6"', "Idempotency-Key": "upgrade-key"},
        json={
            "runtimeId": "runtime-mpa-s2",
            "region": "cn-beijing",
            "targetProfileRevision": 7,
        },
    )
    assert upgraded.status_code == 200
    assert upgraded.json()["profileRevision"] == 7
    assert upgraded.headers["etag"] == '"7"'

    replay = client.post(
        "/web/mpa/sessions/session-s2/profile-upgrade",
        headers={"If-Match": '"6"', "Idempotency-Key": "upgrade-key"},
        json={
            "runtimeId": "runtime-mpa-s2",
            "region": "cn-beijing",
            "targetProfileRevision": 7,
        },
    )
    assert replay.status_code == 200
    assert replay.json()["revision"] == 7

    mismatch = client.post(
        "/web/mpa/sessions/session-s2/profile-upgrade",
        headers={"If-Match": '"7"', "Idempotency-Key": "upgrade-key"},
        json={
            "runtimeId": "runtime-mpa-s2",
            "region": "cn-beijing",
            "targetProfileRevision": 8,
        },
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "idempotency_mismatch"


def test_cursor_expired_scenario_serves_runtime_run_and_cursor_sse(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    app = FastAPI()
    mount_test_scenario_routes(app, token_file=_token_file(tmp_path))
    client = TestClient(app, headers={"Authorization": "Bearer scenario-token"})
    client.put("/__test/mpa/scenarios/cursor_expired", json={"barriers": []})

    session = client.get(
        "/web/runtime-proxy/runtime-mpa-s2/"
        "apps/a2a-default/users/scenario-user/sessions/cursor_expired-session"
    )
    assert session.status_code == 200
    assert session.json()["events"][0]["id"] == "event-before-refresh"

    accepted = client.post(
        "/web/runtime-proxy/runtime-mpa-s2/api/v1/sessions/cursor_expired-session/run",
        headers={"Idempotency-Key": "cursor-key"},
        json={"content": "continue", "executionConfigVersion": 6},
    )
    assert accepted.status_code == 200
    assert accepted.json()["invocationId"] == "cursor_expired-invocation"

    resumed = client.post(
        "/web/runtime-proxy/runtime-mpa-s2/api/v1/sessions/cursor_expired-session/sse",
        json={
            "invocationId": "cursor_expired-invocation",
            "lastEventId": "event-before-refresh",
        },
    )
    assert resumed.status_code == 200
    assert "Before refresh" not in resumed.text
    assert "event-after-refresh" in resumed.text
    assert "After refresh" in resumed.text
    persisted = client.get(
        "/web/runtime-proxy/runtime-mpa-s2/"
        "api/v1/sessions/cursor_expired-session/events"
    )
    assert persisted.status_code == 200
    assert [event["id"] for event in persisted.json()["events"]] == [
        "event-before-refresh",
        "event-after-refresh",
    ]

    expired = client.post(
        "/web/runtime-proxy/runtime-mpa-s2/api/v1/sessions/cursor_expired-session/sse",
        json={
            "invocationId": "cursor_expired-invocation",
            "lastEventId": "missing-event",
        },
    )
    assert expired.status_code == 410
    assert expired.json()["detail"]["code"] == "cursor_expired"

    state = client.get("/__test/mpa/scenarios/cursor_expired").json()
    assert state["calls"] == {
        "runtime-run": 1,
        "runtime-sse": 2,
        "runtime-session-events": 1,
    }
    assert state["data"]["payloads"]["run"] == [
        {"content": "continue", "executionConfigVersion": 6}
    ]
    assert state["data"]["payloads"]["sse"] == [
        {
            "invocationId": "cursor_expired-invocation",
            "lastEventId": "event-before-refresh",
        },
        {
            "invocationId": "cursor_expired-invocation",
            "lastEventId": "missing-event",
        },
    ]


def test_token_file_must_not_be_group_or_world_readable(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("VEADK_MPA_TEST_SCENARIOS", "1")
    token_file = _token_file(tmp_path)
    token_file.chmod(0o644)

    app = FastAPI()
    try:
        mount_test_scenario_routes(app, token_file=token_file)
    except ValueError as error:
        assert "0600" in str(error)
    else:
        raise AssertionError("insecure token file was accepted")
