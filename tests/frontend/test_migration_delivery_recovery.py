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

"""Checks for rebuilding a migration delivery whose CLI never packaged it.

The AgentKit CLI settles an agentic delivery in two halves, and only the first needs
the model.  These checks hold the second half to the CLI's own behaviour: the same
files, the same verification projection, the same terminal documents, and the same
refusals for a Sandbox that is not a finished project.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from frontend.server.migration import service as service_module
from frontend.server.migration.contracts import validate_delivery_result
from frontend.server.migration.delivery_recovery import (
    RecoveryError,
    _lifecycle_entry_point,
    collect_delivery_files,
    environment_requirements,
    main,
    manifest_digest,
    mirror_delivery,
    resolve_startup,
)
from frontend.server.migration.service import MIGRATION_ROOT, MigrationService
from tests.frontend.test_migration_server import (
    FakeMigrationGateway,
    confirmation_body,
    create_uploaded_task,
    mark_analysis_ready,
)

RUN_ID = "migration-v1-" + "c" * 32
SOURCE_SHA256 = "d" * 64
PROVENANCE_SHA256 = "e" * 64
CLI_VERSION = "0.52.17"

# The shape the CLI's own `ak init` template writes, taken from a real migrated run.
AGENTKIT_YAML = """common:
  agent_name: support-agent
  entry_point: support_agent.py
  description: AgentKit project support-agent - Agent Server App
  language: Python
  language_version: "3.12"
  agent_type: WebServer App
  dependencies_file: requirements.txt
  launch_type: cloud
launch_types:
  cloud:
    region: "cn-beijing"
    runtime_jwt_allowed_clients: []
docker_build: {}
"""


def _project(root: Path, **extra: str) -> Path:
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "agentkit.yaml": AGENTKIT_YAML,
        "support_agent.py": "from veadk import Agent\napp = Agent()\n",
        "convert_report.md": "# Migration Report\n\nMigrated.\n",
        ".env.example": "MODEL_AGENT_API_KEY=\nMODEL_NAME=support\n",
        "support_agent/agent.py": "x = 1\n",
    }
    files.update(extra)
    for name, content in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return output


def _config(root: Path, output: Path, **overrides: object) -> dict[str, object]:
    state = root / "work" / "agentic" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "status.json").write_text(
        json.dumps({"job_id": RUN_ID, "state": "Succeed"}), encoding="utf-8"
    )
    config: dict[str, object] = {
        "output_dir": str(output),
        "delivery_dir": str(root / "delivery"),
        "status_path": str(state / "status.json"),
        "run_id": RUN_ID,
        "framework": "dify",
        "source_sha256": SOURCE_SHA256,
        "provenance_sha256": PROVENANCE_SHA256,
        "cli_version": CLI_VERSION,
    }
    config.update(overrides)
    return config


def _run(
    root: Path,
    output: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    agent_state: str = "Succeed",
    **overrides: object,
) -> tuple[int, dict[str, object]]:
    config = _config(root, output, **overrides)
    Path(str(config["status_path"])).write_text(
        json.dumps({"job_id": RUN_ID, "state": agent_state}), encoding="utf-8"
    )
    request = root / "request.json"
    request.write_text(json.dumps(config), encoding="utf-8")
    code = main([str(request)])
    captured = capsys.readouterr()
    return code, json.loads(captured.out.strip().splitlines()[-1])


def _result(root: Path) -> dict[str, object]:
    return json.loads(
        (root / "delivery" / "migration-result.json").read_text(encoding="utf-8")
    )


def test_mirror_delivery_writes_the_documents_the_cli_would_have_written(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = _project(tmp_path)

    code, verdict = _run(tmp_path, output, capsys)

    assert code == 0
    assert verdict["ok"] is True
    assert verdict["status"] == "succeeded"
    delivery = tmp_path / "delivery"
    result = _result(tmp_path)
    validate_delivery_result(
        result, expected_run_id=RUN_ID, expected_status="succeeded"
    )
    assert result["cli"] == {"name": "agentkit-cli", "version": CLI_VERSION}
    assert result["startup"] == {"module": "support_agent.py", "object": "app"}
    assert result["environment"] == {
        "required": ["MODEL_AGENT_API_KEY"],
        "optional": ["MODEL_NAME"],
    }
    assert result["verification"] == {"status": "passed", "checks": []}
    assert result["report"] == {"path": "convert_report.md"}
    assert result["artifact"]["path"] == "migration-result.zip"
    assert verdict["manifest_sha256"] == manifest_digest(result["files"])
    status = json.loads(
        (delivery / "migration-status.json").read_text(encoding="utf-8")
    )
    assert status["state"] == "succeeded"
    assert status["phase"] == "completed"
    assert status["artifact"] == {
        "state": "ready",
        "preview_ready": True,
        "download_ready": True,
        "deploy_ready": True,
    }
    listed = subprocess.run(
        ["unzip", "-Z1", str(delivery / "migration-result.zip")],
        capture_output=True,
        text=True,
        check=True,
    )
    assert sorted(entry for entry in listed.stdout.splitlines() if entry) == sorted(
        str(item["path"]) for item in result["files"]
    )


def test_mirror_delivery_keeps_the_sequence_the_cli_already_started(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = _project(tmp_path)
    delivery = tmp_path / "delivery"
    delivery.mkdir(parents=True)
    (delivery / "migration-status.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": RUN_ID,
                "sequence": 6,
                "state": "migrating",
                "phase": "preparing",
                "message": "Preparing agentic migration",
                "artifact": {
                    "state": "none",
                    "preview_ready": False,
                    "download_ready": False,
                    "deploy_ready": False,
                },
                "updated_at": "2026-09-23T04:50:00Z",
            }
        ),
        encoding="utf-8",
    )

    code, _ = _run(tmp_path, output, capsys)

    assert code == 0
    status = json.loads(
        (delivery / "migration-status.json").read_text(encoding="utf-8")
    )
    assert status["sequence"] == 7


def test_mirror_delivery_refuses_a_delivery_the_cli_already_settled(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = _project(tmp_path)
    assert _run(tmp_path, output, capsys)[0] == 0

    code, verdict = _run(tmp_path, output, capsys)

    assert code == 1
    assert verdict["ok"] is False
    assert "already settled" in str(verdict["error"])


@pytest.mark.parametrize("state", ["Runnning", "Failed"])
def test_mirror_delivery_refuses_a_run_that_never_finished(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    state: str,
) -> None:
    output = _project(tmp_path)

    code, verdict = _run(tmp_path, output, capsys, agent_state=state)

    assert code == 1
    assert verdict["ok"] is False
    assert not (tmp_path / "delivery" / "migration-result.zip").exists()


def test_mirror_delivery_refuses_a_project_without_its_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = _project(tmp_path)
    (output / "convert_report.md").unlink()

    code, verdict = _run(tmp_path, output, capsys)

    assert code == 1
    assert "report is not part of the project" in str(verdict["error"])


def test_mirror_delivery_refuses_a_delivery_directory_inside_the_project(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = _project(tmp_path)

    code, verdict = _run(
        tmp_path, output, capsys, delivery_dir=str(output / "delivery")
    )

    assert code == 1
    assert "outside the project" in str(verdict["error"])


def test_mirror_delivery_refuses_an_incomplete_request(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = _project(tmp_path)

    code, verdict = _run(tmp_path, output, capsys, source_sha256="")

    assert code == 1
    assert verdict["error"] == "the recovery request is incomplete"


def test_verification_mirrors_the_cli_finding_projection(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Findings become checks and warnings; only the agent state sets the verdict.

    A run that ends ``Succeed`` while carrying repairable findings cannot happen,
    because the CLI demotes it before it ever reaches packaging, so the degraded case
    is the one where a projection difference would actually show.
    """
    output = _project(tmp_path)
    (output / "validation_findings.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fatal": [],
                "repairable": [{"name": "eval:cases", "detail": "missing case"}],
                "degraded": [{"name": "docs:readme"}, "not-an-object"],
                "info": [{"name": "  ", "detail": "trimmed away"}],
            }
        ),
        encoding="utf-8",
    )

    _, verdict = _run(tmp_path, output, capsys, agent_state="SucceedWithWarnings")

    result = _result(tmp_path)
    assert result["verification"]["status"] == "degraded"
    assert result["verification"]["checks"] == [
        {"name": "eval:cases", "status": "failed", "detail": "missing case"},
        {"name": "docs:readme", "status": "passed"},
        {
            "name": "(invalid)",
            "status": "passed",
            "detail": "validation finding is not an object",
        },
        {"name": "(unnamed)", "status": "passed", "detail": "trimmed away"},
    ]
    assert result["warnings"] == [
        "eval:cases: missing case",
        "docs:readme: degraded",
        "(invalid): validation finding is not an object",
    ]
    assert verdict["status"] == "succeeded_with_warnings"


def test_an_unparseable_findings_file_reports_no_findings_at_all(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = _project(tmp_path)
    (output / "validation_findings.json").write_text("{ not json", encoding="utf-8")

    _, verdict = _run(tmp_path, output, capsys)

    result = _result(tmp_path)
    assert result["verification"]["checks"] == []
    assert result["warnings"] == []
    assert verdict["status"] == "succeeded"


def test_a_startup_fallback_degrades_the_delivery(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = _project(
        tmp_path, **{"agentkit.yaml": "common:\n  entry_point: gone.py\n"}
    )
    (output / "main.py").write_text("app = object()\n", encoding="utf-8")
    detail = (
        "agentkit.yaml common.entry_point does not identify a deliverable file; "
        "packaged main.py as a non-deployable partial result."
    )

    _, verdict = _run(tmp_path, output, capsys)

    result = _result(tmp_path)
    assert result["startup"] == {"module": "main.py", "object": "app"}
    assert result["status"] == "partial"
    assert result["verification"]["status"] == "degraded"
    assert result["verification"]["checks"] == [
        {"name": "startup:lifecycle_config", "status": "failed", "detail": detail}
    ]
    assert result["warnings"] == [detail]
    assert verdict["status"] == "partial"
    status = json.loads(
        (tmp_path / "delivery" / "migration-status.json").read_text(encoding="utf-8")
    )
    assert status["artifact"]["deploy_ready"] is False


def test_lifecycle_entry_point_reads_the_generated_configuration(
    tmp_path: Path,
) -> None:
    path = tmp_path / "agentkit.yaml"
    path.write_text(AGENTKIT_YAML, encoding="utf-8")

    assert _lifecycle_entry_point(path) == "support_agent.py"


@pytest.mark.parametrize(
    "body,expected",
    [
        ('  entry_point: "app.py"\n', "app.py"),
        ("  entry_point: app.py  # the generated module\n", "app.py"),
        ("  entry_point: 'app.py'\n", "app.py"),
        ("  entry_point:\n", None),
        ("  other: 1\n", None),
        ("  nested:\n    entry_point: hidden.py\n", None),
        ("  entry_point: [a, b]\n", None),
    ],
)
def test_lifecycle_entry_point_follows_the_cli_fallback_rules(
    tmp_path: Path,
    body: str,
    expected: str | None,
) -> None:
    path = tmp_path / "agentkit.yaml"
    path.write_text(f"common:\n{body}", encoding="utf-8")

    assert _lifecycle_entry_point(path) == expected


def test_lifecycle_entry_point_reports_tabs_as_invalid(tmp_path: Path) -> None:
    path = tmp_path / "agentkit.yaml"
    path.write_text("common:\n\tentry_point: app.py\n", encoding="utf-8")

    with pytest.raises(RecoveryError, match="tab characters"):
        _lifecycle_entry_point(path)


def test_lifecycle_entry_point_ignores_an_inline_common(tmp_path: Path) -> None:
    path = tmp_path / "agentkit.yaml"
    path.write_text("common: app.py\n", encoding="utf-8")

    assert _lifecycle_entry_point(path) is None


def test_resolve_startup_needs_no_yaml_library(tmp_path: Path) -> None:
    output = _project(tmp_path)

    startup, warnings = resolve_startup(output)

    assert startup == {"module": "support_agent.py", "object": "app"}
    assert warnings == []


def test_environment_requirements_mark_secret_names_required(tmp_path: Path) -> None:
    output = _project(
        tmp_path,
        **{
            ".env.example": (
                "# comment\n"
                "MODEL_AGENT_API_KEY=\n"
                "MODEL_AGENT_API_BASE=https://example.invalid\n"
                "PLAIN_NAME=value\n"
                "\n"
                "PORT\n"
            )
        },
    )

    assert environment_requirements(output) == {
        "required": ["MODEL_AGENT_API_KEY"],
        "optional": ["MODEL_AGENT_API_BASE", "PLAIN_NAME"],
    }


def test_collect_delivery_files_skips_what_the_cli_skips(tmp_path: Path) -> None:
    output = _project(
        tmp_path,
        **{
            "notes.pyc": "binary",
            "build.log": "kept: the delivery filter only drops logs from the source",
        },
    )
    (output / ".venv").mkdir()
    (output / ".venv" / "lib.py").write_text("x\n", encoding="utf-8")

    paths = sorted(str(item["path"]) for item in collect_delivery_files(output))

    assert paths == [
        ".env.example",
        "agentkit.yaml",
        "build.log",
        "convert_report.md",
        "support_agent.py",
        "support_agent/agent.py",
    ]


@pytest.mark.parametrize("name", [".env.local", ".env.production", "private.pem"])
def test_collect_delivery_files_refuses_a_secret_bearing_file(
    tmp_path: Path,
    name: str,
) -> None:
    output = _project(tmp_path, **{name: "MODEL_AGENT_API_KEY=abc\n"})

    with pytest.raises(RecoveryError, match="secret-bearing file"):
        collect_delivery_files(output)


def test_collect_delivery_files_refuses_a_symbolic_link(tmp_path: Path) -> None:
    output = _project(tmp_path)
    (output / "linked.py").symlink_to(output / "support_agent.py")

    with pytest.raises(RecoveryError, match="symbolic link"):
        collect_delivery_files(output)


def test_manifest_digest_ignores_the_order_files_were_walked_in() -> None:
    first = [{"path": "b.py", "size": 1, "sha256": "a" * 64, "mode": "0644"}]
    second = first + [{"path": "a.py", "size": 2, "sha256": "b" * 64, "mode": "0644"}]

    assert manifest_digest(second) == manifest_digest(list(reversed(second)))
    assert manifest_digest(first) != manifest_digest(second)


def test_manifest_digest_rejects_a_manifest_that_is_not_a_file_list() -> None:
    with pytest.raises(RecoveryError, match="delivery files must be a list"):
        manifest_digest({"path": "a.py"})


# --- Studio's side of the rebuild -------------------------------------------------


def _driver(task_id: str, state: str, heartbeat_at: int | None = None) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "run_id": task_id,
            "state": state,
            "heartbeat_at": int(time.time()) if heartbeat_at is None else heartbeat_at,
            "finished_at": None,
            "exit_code": None,
            "artifact": None,
        }
    ).encode()


@pytest.fixture
def migrating_task(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MigrationService, FakeMigrationGateway, str]:
    """An agentic migration whose CLI was seen to leave the Sandbox."""
    monkeypatch.setenv("AGENTKIT_MIGRATION_APP_SERVER", "0")
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id, framework="dify", entry=None)
    service.confirm(
        task_id,
        "owner-1",
        confirmation_body(gateway, task_id, framework="dify", entry=None),
    )
    gateway.files[(task_id, f"{MIGRATION_ROOT}/control/migration-driver.json")] = (
        _driver(task_id, "lost")
    )
    gateway.files[(task_id, f"{MIGRATION_ROOT}/work/agentic/state/status.json")] = (
        json.dumps({"job_id": task_id, "state": "Succeed"}).encode()
    )
    return service, gateway, task_id


def _wait(service: MigrationService, task_id: str) -> None:
    deadline = time.time() + 10
    while time.time() < deadline:
        worker = service._delivery_recoveries.get(f"session-{task_id}")
        if worker is None or not worker.is_alive():
            return
        time.sleep(0.02)
    raise AssertionError("the delivery recovery worker never finished")


def test_a_lost_driver_puts_a_recoverable_task_back_into_migration(
    migrating_task: tuple[MigrationService, FakeMigrationGateway, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, gateway, task_id = migrating_task
    seen: list[dict[str, object]] = []

    def rebuild(self, session, request):  # noqa: ANN001, ANN202
        seen.append(request)
        return {"ok": True, "files": 5, "bytes": 100, "manifest_sha256": "f" * 64}

    monkeypatch.setattr(MigrationService, "_run_delivery_recovery", rebuild)

    task = service.get_task(task_id, "owner-1")

    assert task["state"] == "migrating"
    assert task["message"] == "正在整理迁移结果"
    _wait(service, task_id)
    assert len(seen) == 1
    assert seen[0]["run_id"] == task_id
    assert seen[0]["framework"] == "dify"
    assert seen[0]["cli_version"] == "0.52.1"
    assert str(seen[0]["provenance_sha256"]) == _provenance_sha256(gateway, task_id)
    lease = json.loads(
        gateway.files[
            (task_id, f"{MIGRATION_ROOT}/control/delivery-recovery-lease.json")
        ]
    )
    assert lease["state"] == "done"
    assert lease["verdict"] is True
    assert lease["files"] == 5


def _provenance_sha256(gateway: FakeMigrationGateway, task_id: str) -> str:
    import hashlib

    return hashlib.sha256(
        gateway.files[(task_id, f"{MIGRATION_ROOT}/control/route-selection.json")]
    ).hexdigest()


def test_a_lost_driver_without_a_finished_project_stays_a_failure(
    migrating_task: tuple[MigrationService, FakeMigrationGateway, str],
) -> None:
    service, gateway, task_id = migrating_task
    gateway.files[(task_id, f"{MIGRATION_ROOT}/work/agentic/state/status.json")] = (
        json.dumps({"job_id": task_id, "state": "Runnning"}).encode()
    )

    task = service.get_task(task_id, "owner-1")

    assert task["state"] == "failed"
    assert task["error"]["code"] == "MIGRATION_DELIVERY_INTERRUPTED"
    assert not any(
        path == f"{MIGRATION_ROOT}/control/delivery-recovery-lease.json"
        for _, path in gateway.files
    )


def test_a_rebuild_that_cannot_finish_is_not_retried_on_every_read(
    migrating_task: tuple[MigrationService, FakeMigrationGateway, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, gateway, task_id = migrating_task
    attempts: list[dict[str, object]] = []

    def rebuild(self, session, request):  # noqa: ANN001, ANN202
        attempts.append(request)
        return {
            "ok": False,
            "error": "the migration output contains no deliverable files",
        }

    monkeypatch.setattr(MigrationService, "_run_delivery_recovery", rebuild)

    first = service.get_task(task_id, "owner-1")
    _wait(service, task_id)
    second = service.get_task(task_id, "owner-1")
    third = service.get_task(task_id, "owner-1")

    assert first["state"] == "migrating"
    assert len(attempts) == 1
    assert second["state"] == "failed"
    assert third["state"] == "failed"
    assert len(attempts) == 1


def test_a_rebuild_that_lands_settles_the_task_on_the_cli_delivery_contract(
    migrating_task: tuple[MigrationService, FakeMigrationGateway, str],
    tmp_path: Path,
) -> None:
    service, gateway, task_id = migrating_task
    output = _project(tmp_path)
    config = _config(
        tmp_path, output, run_id=task_id, delivery_dir=str(tmp_path / "delivery")
    )
    verdict = mirror_delivery(config)
    for name in ("migration-result.json", "migration-status.json"):
        gateway.files[(task_id, f"{MIGRATION_ROOT}/delivery/{name}")] = (
            tmp_path / "delivery" / name
        ).read_bytes()

    task = service.get_task(task_id, "owner-1")

    assert verdict["status"] == "succeeded"
    assert task["state"] == "succeeded"
    assert task["artifact"] == {
        "state": "ready",
        "previewReady": True,
        "downloadReady": True,
        "deployReady": True,
    }
    assert task["message"] == "迁移产物已生成"


def test_a_live_driver_is_left_alone(
    migrating_task: tuple[MigrationService, FakeMigrationGateway, str],
) -> None:
    service, gateway, task_id = migrating_task
    gateway.files[(task_id, f"{MIGRATION_ROOT}/control/migration-driver.json")] = (
        _driver(task_id, "running")
    )

    task = service.get_task(task_id, "owner-1")

    assert task["state"] == "migrating"
    assert task["message"] == "正在迁移项目"
    assert task_id not in service._delivery_recoveries


def test_a_stale_heartbeat_is_also_a_lost_driver() -> None:
    service = MigrationService(FakeMigrationGateway())

    assert service._migration_driver_lost(
        {"state": "running", "heartbeat_at": int(time.time()) - 3600}
    )
    assert not service._migration_driver_lost(
        {"state": "running", "heartbeat_at": int(time.time())}
    )
    assert service._migration_driver_lost({"state": "lost", "heartbeat_at": 0})
    assert not service._migration_driver_lost({"state": "finished", "heartbeat_at": 0})
    assert not service._migration_driver_lost(None)
    assert not service._migration_driver_lost(
        {"state": "running", "heartbeat_at": "not-a-time"}
    )


def test_the_rebuild_runs_this_repositorys_own_program(
    migrating_task: tuple[MigrationService, FakeMigrationGateway, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, gateway, task_id = migrating_task
    commands: list[tuple[str, int]] = []

    def execute(  # noqa: ANN001, ANN202
        self, session, command, *, operation, timeout_seconds=120
    ):
        commands.append((command, timeout_seconds))
        return {
            "status": "finished",
            "exit_code": 0,
            "stdout": '{"ok": true, "files": 2}\n',
        }

    monkeypatch.setattr(MigrationService, "_execute", execute)
    session = service._session(task_id, "owner-1")
    request = service._delivery_recovery_request(session)

    assert request is not None
    assert request["output_dir"] == service_module._DELIVERY_OUTPUT_DIR
    assert request["run_id"] == task_id
    assert request["framework"] == "dify"
    assert request["cli_version"] == "0.52.1"
    assert (
        request["source_sha256"]
        == json.loads(
            gateway.files[(task_id, f"{MIGRATION_ROOT}/request/source.json")]
        )["sha256"]
    )

    verdict = service._run_delivery_recovery(session, request)

    assert verdict == {"ok": True, "files": 2}
    assert len(commands) == 1
    assert service_module._DELIVERY_RECOVERY_SCRIPT_PATH in commands[0][0]
    assert commands[0][1] == service_module._DELIVERY_RECOVERY_TIMEOUT_SECONDS
    shipped = gateway.files[
        (task_id, service_module._DELIVERY_RECOVERY_SCRIPT_PATH)
    ].decode("utf-8")
    assert "def mirror_delivery" in shipped
    written = json.loads(
        gateway.files[(task_id, service_module._DELIVERY_RECOVERY_REQUEST_PATH)]
    )
    assert written == request
