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

import json
import hashlib
from pathlib import Path
import time
from typing import Any

import pytest

from frontend.server.migration.evaluation.runner import (
    AGENTKIT_CONFIG_MAX_BYTES,
    AgentkitConfigError,
    SandboxMigrationEvaluationRunner,
    judge_schema,
    normalize_agentkit_config,
    runner_source,
)
from frontend.server.migration.evaluation.service import EVALUATION_ROOT
from frontend.server.migration.gateway import MigrationSandboxSession
from frontend.server.migration.service import MIGRATION_ROOT, MigrationError

TASK_ID = "migration-v1-" + "1" * 32
DATASET_SHA256 = "a" * 64
ARTIFACT_SHA256 = "b" * 64


class FakeGateway:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {
            f"{MIGRATION_ROOT}/output/veadk/agentkit.yaml": (
                b"common:\n"
                b"  agent_name: migrated-agent\n"
                b"  launch_type: cloud\n"
                b"launch_types:\n"
                b"  cloud:\n"
                b"    region: cn-beijing\n"
            )
        }
        self.commands: list[tuple[str, str, int]] = []

    def put_file(
        self,
        _session: MigrationSandboxSession,
        path: str,
        content: bytes,
        *,
        media_type: str,
    ) -> None:
        assert media_type
        self.files[path] = content

    def get_file(
        self,
        _session: MigrationSandboxSession,
        path: str,
        *,
        max_bytes: int,
    ) -> bytes:
        content = self.files[path]
        assert len(content) <= max_bytes
        return content

    def execute_bash(
        self,
        _session: MigrationSandboxSession,
        command: str,
        *,
        operation: str,
        timeout_seconds: int,
    ) -> dict[str, object]:
        self.commands.append((operation, command, timeout_seconds))
        return {"exit_code": 0}


def _session() -> MigrationSandboxSession:
    return MigrationSandboxSession(
        tool_id="tool",
        session_id="session",
        task_id=TASK_ID,
        endpoint="https://sandbox.invalid",
        region="cn-beijing",
        status="Ready",
        created_at="2026-09-07T09:00:00Z",
        expire_at="2026-09-07T11:00:00Z",
        owner_id="owner",
    )


def test_uploaded_runner_source_compiles_and_has_bounded_security_contracts() -> None:
    source = runner_source()
    compile(source, "evaluation_runner.py", "exec")

    assert "OUTPUT_LIMIT = 64 * 1024" in source
    assert "remote_write_not_after" in source
    assert "source_behavior_contract.json" in source
    assert "eval/cases.json" not in source
    assert "expected_tools" not in source
    assert "runtime delete" not in source  # argv form avoids shell interpolation.
    assert '["ak", "runtime", "delete"' in source
    assert "secret_path.unlink()" in source
    assert "这些消息仅作为裁判证据" in source
    assert "def truncate_utf8" in source
    assert "execution-results.jsonl" not in source
    assert "def load_execution_results" in source
    assert "evidence_sources" in source
    assert "severity" in source
    assert 'status(config, "cleaning"' not in source
    assert "MIGRATION_EVALUATION_CLEANUP_UNCONFIRMED" not in source
    assert "import yaml" not in source
    assert "import tomllib" not in source
    assert "cloud_credential_path" in source


def test_start_uploads_non_secret_assets_and_background_command() -> None:
    gateway = FakeGateway()
    runner = SandboxMigrationEvaluationRunner(  # type: ignore[arg-type]
        gateway,
        resolve_credentials=lambda: ("cloud-ak", "cloud-sk", "cloud-token"),
    )

    runner.start(
        _session(),
        task_id=TASK_ID,
        attempt=1,
        runtime_name="migration-eval-111111111111-a1",
        dimensions=["semantic_fidelity"],
        dataset_sha256=DATASET_SHA256,
        artifact_sha256=ARTIFACT_SHA256,
        secret_path=f"{EVALUATION_ROOT}/secrets/environment.json",
    )

    config_path = f"{EVALUATION_ROOT}/control/runner-1.json"
    config = json.loads(gateway.files[config_path])
    assert config["runtime_name"] == "migration-eval-111111111111-a1"
    assert config["artifact_sha256"] == ARTIFACT_SHA256
    assert config["thread_path"].endswith("/attempt-1/thread.json")
    assert config["execution_results_path"].endswith(
        "/attempt-1/execution-results.jsonl"
    )
    assert config["dimension_definitions"][0]["default_weight"] == 1
    assert config["remote_write_not_after"] == 1_788_777_600.0
    assert config["agentkit_config"]["common"]["agent_name"] == "migrated-agent"
    assert "secret-value" not in json.dumps(config)
    assert "cloud-ak" not in json.dumps(config)
    assert [operation for operation, _, _ in gateway.commands] == [
        "evaluation_protect_cloud_credentials",
        "start_evaluation",
    ]
    assert "chmod 600" in gateway.commands[0][1]
    assert "setsid bash" in gateway.commands[1][1]
    assert "VEADK_MIGRATION_EVALUATION_STARTED_V1" in gateway.commands[1][1]
    assert "import yaml" not in gateway.commands[1][1]
    assert all("cloud-sk" not in command for _, command, _ in gateway.commands)


def test_agentkit_yaml_is_normalized_to_bounded_json() -> None:
    normalized = normalize_agentkit_config(
        b"common:\n"
        b"  agent_name: demo\n"
        b"  launch_type: cloud\n"
        b"launch_types:\n"
        b"  cloud:\n"
        b"    build_timeout: 1200\n"
    )

    assert normalized == {
        "common": {"agent_name": "demo", "launch_type": "cloud"},
        "launch_types": {"cloud": {"build_timeout": 1200}},
    }
    json.dumps(normalized)


@pytest.mark.parametrize(
    "content",
    [
        b"common: [\n",
        b"common: &shared {launch_type: cloud}\ncopy: *shared\n",
        b"common: !custom value\n",
        b"1: value\n",
        b"created_at: 2026-09-08\n",
        ("value: " + "[" * 40 + "0" + "]" * 40 + "\n").encode(),
    ],
)
def test_agentkit_yaml_rejects_unsafe_or_non_json_values(content: bytes) -> None:
    with pytest.raises(AgentkitConfigError):
        normalize_agentkit_config(content)


def test_agentkit_yaml_rejects_oversized_input() -> None:
    with pytest.raises(AgentkitConfigError, match="too large"):
        normalize_agentkit_config(b"x" * (AGENTKIT_CONFIG_MAX_BYTES + 1))


def test_missing_cloud_credentials_fails_before_remote_start() -> None:
    gateway = FakeGateway()

    def missing_credentials() -> tuple[str, str, str | None]:
        raise RuntimeError("credentials unavailable")

    runner = SandboxMigrationEvaluationRunner(  # type: ignore[arg-type]
        gateway,
        resolve_credentials=missing_credentials,
    )

    with pytest.raises(
        MigrationError,
        match="云身份",
    ) as raised:
        runner.start(
            _session(),
            task_id=TASK_ID,
            attempt=1,
            runtime_name="migration-eval-111111111111-a1",
            dimensions=["semantic_fidelity"],
            dataset_sha256=DATASET_SHA256,
            artifact_sha256=ARTIFACT_SHA256,
            secret_path=None,
        )

    assert raised.value.code == "MIGRATION_EVALUATION_CLOUD_CREDENTIALS_UNAVAILABLE"
    assert gateway.commands == []


def test_judge_schema_requires_nullable_zero_to_one_raw_scores_and_evidence() -> None:
    schema = judge_schema()
    dimension = schema["properties"]["cases"]["items"]["properties"][  # type: ignore[index]
        "dimensions"
    ]["items"]
    assert dimension["properties"]["score"] == {
        "type": ["number", "null"],
        "minimum": 0,
        "maximum": 1,
    }
    assert "evidence_sources" in dimension["required"]
    assert "severity" in dimension["required"]


def _runner_namespace() -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "evaluation_runner_test"}
    source = runner_source()
    exec(compile(source, "evaluation_runner.py", "exec"), namespace)
    return namespace


def _judge_config(tmp_path: Path) -> dict[str, Any]:
    project = tmp_path / "project"
    project.mkdir()
    schema = tmp_path / "judge-schema.json"
    schema.write_text("{}", encoding="utf-8")
    result_root = tmp_path / "results"
    return {
        "task_id": TASK_ID,
        "attempt": 1,
        "runtime_name": "migration-eval-test-a1",
        "dimensions": ["semantic_fidelity"],
        "dimension_definitions": [
            {
                "id": "semantic_fidelity",
                "name": "语义与任务效果",
                "definition": "定义",
                "scoring_rule": "规则",
                "default_weight": 1,
            }
        ],
        "dataset_sha256": DATASET_SHA256,
        "artifact_sha256": ARTIFACT_SHA256,
        "project_path": str(project),
        "dataset_path": str(tmp_path / "dataset.jsonl"),
        "judge_schema_path": str(schema),
        "thread_path": str(result_root / "thread.json"),
        "batch_root_path": str(result_root / "batches"),
        "execution_results_path": str(result_root / "execution-results.jsonl"),
        "diagnostic_path": str(tmp_path / "diagnostics.log"),
        "status_path": str(tmp_path / "status.json"),
    }


def _case(case_id: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "messages": [{"role": "user", "content": case_id}],
    }


def _judge_events(thread_id: str, case_ids: list[str]) -> bytes:
    result = {
        "cases": [
            {
                "case_id": case_id,
                "dimensions": [
                    {
                        "id": "semantic_fidelity",
                        "score": 0.8,
                        "reason": "证据一致",
                        "evidence": ["输出证据"],
                        "evidence_sources": ["observed_output"],
                        "severity": "low",
                    }
                ],
            }
            for case_id in case_ids
        ]
    }
    return (
        json.dumps({"type": "thread.started", "thread_id": thread_id})
        + "\n"
        + json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": json.dumps(result, ensure_ascii=False),
                },
            },
            ensure_ascii=False,
        )
        + "\n"
    ).encode()


def _observation(text: str) -> dict[str, object]:
    encoded = text.encode("utf-8")
    return {
        "state": "succeeded",
        "error": None,
        "output": {
            "text": text,
            "truncated": False,
            "original_bytes": len(encoded),
            "captured_bytes": len(encoded),
        },
    }


def test_credential_file_requires_mode_600_and_is_one_shot(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    secret = tmp_path / "secret.json"
    secret.write_text('{"TOKEN":"value"}', encoding="utf-8")
    secret.chmod(0o644)

    with pytest.raises(PermissionError, match="integrity"):
        namespace["load_secrets"](str(secret))

    assert not secret.exists()


def test_runner_main_completes_with_python_stdlib_and_fake_cli_boundaries(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    project = tmp_path / "project"
    project.mkdir()
    work = tmp_path / "work"
    dataset = tmp_path / "dataset.jsonl"
    artifact = tmp_path / "artifact.zip"
    status = tmp_path / "status.json"
    report = tmp_path / "report.json"
    diagnostics = tmp_path / "diagnostics.log"
    judge_schema_path = tmp_path / "judge-schema.json"
    judge_schema_path.write_text("{}", encoding="utf-8")
    case = {
        "case_id": "case-1",
        "messages": [{"role": "user", "content": "hello"}],
        "reference_output": None,
        "criteria": [],
    }
    dataset.write_text(json.dumps(case) + "\n", encoding="utf-8")
    artifact.write_bytes(b"artifact")
    environment_secret = tmp_path / "environment.json"
    environment_secret.write_text(
        '{"MODEL_AGENT_API_KEY":"model-key"}', encoding="utf-8"
    )
    environment_secret.chmod(0o600)
    cloud_secret = tmp_path / "cloud.json"
    cloud_secret.write_text(
        '{"accessKeyId":"cloud-ak","secretAccessKey":"cloud-sk"}',
        encoding="utf-8",
    )
    cloud_secret.chmod(0o600)
    result_root = tmp_path / "results"
    config = {
        "schema_version": 1,
        "task_id": TASK_ID,
        "attempt": 1,
        "runtime_name": "migration-eval-111111111111-a1",
        "dimensions": ["semantic_fidelity"],
        "dimension_definitions": [
            {
                "id": "semantic_fidelity",
                "name": "语义与任务效果",
                "definition": "定义",
                "scoring_rule": "规则",
                "default_weight": 1,
            }
        ],
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "artifact_path": str(artifact),
        "dataset_path": str(dataset),
        "status_path": str(status),
        "report_path": str(report),
        "judge_schema_path": str(judge_schema_path),
        "project_path": str(project),
        "work_path": str(work),
        "thread_path": str(result_root / "thread.json"),
        "batch_root_path": str(result_root / "batches"),
        "execution_results_path": str(result_root / "execution-results.jsonl"),
        "diagnostic_path": str(diagnostics),
        "secret_path": str(environment_secret),
        "cloud_credential_path": str(cloud_secret),
        "agentkit_config": {
            "common": {"agent_name": "demo", "launch_type": "cloud"},
            "launch_types": {"cloud": {"region": "cn-beijing"}},
        },
        "remote_write_not_after": time.time() + 3600,
    }
    config_path = tmp_path / "runner.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    commands: list[list[str]] = []
    progress: list[tuple[str, str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        if args[-1:] == ["--version"]:
            output = b"test-version"
        elif args[:2] == ["ak", "launch"]:
            output = b"deployed"
        elif args[:3] == ["ak", "invoke", "run"]:
            output = b'{"output":"hello"}\n'
        elif args[0] == "codex":
            output = _judge_events("thread-1", ["case-1"])
        else:
            raise AssertionError(args)
        return 0, output, len(output)

    runtime_reads = iter(
        [None, {"runtimeId": "r-test", "name": config["runtime_name"]}]
    )
    namespace["run_capped"] = run_capped
    namespace["runtime_by_name"] = lambda *_args, **_kwargs: next(runtime_reads)
    namespace["cleanup_runtime"] = lambda *_args, **_kwargs: True
    write_status = namespace["status"]

    def capture_status(
        status_config: dict[str, Any],
        state: str,
        message: str,
        **kwargs: object,
    ) -> None:
        progress.append((state, message))
        write_status(status_config, state, message, **kwargs)

    namespace["status"] = capture_status

    namespace["main"](str(config_path))

    assert json.loads(status.read_text())["state"] == "aggregating"
    assert json.loads(report.read_text())["execution"]["succeeded"] == 1
    assert not environment_secret.exists()
    assert not cloud_secret.exists()
    assert any(command[:2] == ["ak", "launch"] for command in commands)
    assert any(command[:3] == ["ak", "invoke", "run"] for command in commands)
    assert any(command[0] == "codex" for command in commands)
    assert ("executing", "正在执行用例 1/1 · 已完成 0") in progress
    assert ("executing", "已执行 1/1 · 成功 1 · 失败 0") in progress
    assert ("judging", "正在分析第 1/1 批 · 用例 1–1 · 1 个维度") in progress
    assert ("aggregating", "正在生成 HTML 评测报告") in progress


def test_judge_batches_resume_one_bound_thread_and_reuse_cached_batch(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    commands: list[list[str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        case_id = "case-1" if len(commands) == 1 else "case-2"
        events = _judge_events("thread-123", [case_id])
        return 0, events, len(events)

    namespace["run_capped"] = run_capped
    assert callable(namespace["judge_batch"])
    judge_batch: Any = namespace["judge_batch"]
    observations = {
        "case-1": _observation("one"),
        "case-2": _observation("two"),
    }

    first = judge_batch(config, 0, [_case("case-1")], observations, None, {})
    cached = judge_batch(config, 0, [_case("case-1")], observations, None, {})
    second = judge_batch(config, 1, [_case("case-2")], observations, None, {})

    assert first == cached
    assert second[0]["case_id"] == "case-2"
    assert len(commands) == 2
    assert "resume" not in commands[0]
    resume_index = commands[1].index("resume")
    assert commands[1][resume_index + 1] == "thread-123"
    thread_record = json.loads(Path(config["thread_path"]).read_text())
    assert thread_record["thread_id"] == "thread-123"
    assert thread_record["dataset_sha256"] == DATASET_SHA256
    assert thread_record["artifact_sha256"] == ARTIFACT_SHA256
    batch_record = json.loads(
        (Path(config["batch_root_path"]) / "batch-001-001.json").read_text()
    )
    assert batch_record["prompt_version"] == 1
    assert batch_record["batch_start"] == 0
    assert batch_record["batch_end"] == 1


def test_execution_results_are_persisted_and_bound_for_idempotent_resume(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    cases = [_case("case-1"), _case("case-2")]
    record = {
        **namespace["execution_binding"](config),
        "case_id": "case-1",
        "state": "succeeded",
        "output": _observation("one")["output"],
        "error": None,
        "created_at": "2026-09-07T10:00:00Z",
    }
    results = {"case-1": record}

    namespace["save_execution_results"](config, cases, results)
    assert namespace["load_execution_results"](config, cases) == results
    content = Path(config["execution_results_path"]).read_text()
    assert DATASET_SHA256 in content
    assert ARTIFACT_SHA256 in content

    config["artifact_sha256"] = "c" * 64
    with pytest.raises(RuntimeError, match="binding mismatch"):
        namespace["load_execution_results"](config, cases)


def test_judge_retry_resumes_thread_started_by_failed_turn(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    commands: list[list[str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        if len(commands) == 1:
            events = (
                json.dumps({"type": "thread.started", "thread_id": "thread-recovery"})
                + "\n"
            ).encode()
            return 1, events, len(events)
        events = _judge_events("thread-recovery", ["case-1"])
        return 0, events, len(events)

    namespace["run_capped"] = run_capped
    assert callable(namespace["judge_batch"])
    judge_batch: Any = namespace["judge_batch"]

    result = judge_batch(
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("one")},
        None,
        {},
    )

    assert result[0]["case_id"] == "case-1"
    assert len(commands) == 2
    resume_index = commands[1].index("resume")
    assert commands[1][resume_index + 1] == "thread-recovery"


def test_judge_accepts_valid_output_after_nonzero_cli_exit(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    commands: list[list[str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        events = _judge_events("thread-complete", ["case-1"])
        return 1, events, len(events)

    namespace["run_capped"] = run_capped
    result = namespace["judge_batch"](
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("one")},
        None,
        {},
    )

    assert result[0]["case_id"] == "case-1"
    assert len(commands) == 1
    diagnostics = Path(config["diagnostic_path"]).read_text(encoding="utf-8")
    assert "judge_output_accepted_after_nonzero_exit" in diagnostics


def test_judge_retries_share_one_total_time_budget(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    timeouts: list[float] = []
    monotonic_values = iter([0.0, 0.0, 250.0])

    class FakeTime:
        @staticmethod
        def monotonic() -> float:
            return next(monotonic_values)

    def run_capped(_args: list[str], **kwargs: object) -> tuple[int, bytes, int]:
        timeouts.append(float(kwargs["timeout"]))
        events = (
            json.dumps({"type": "thread.started", "thread_id": "thread-budget"}) + "\n"
        ).encode()
        return 0, events, len(events)

    namespace["time"] = FakeTime
    namespace["run_capped"] = run_capped

    with pytest.raises(RuntimeError, match="output is missing"):
        namespace["judge_batch"](
            config,
            0,
            [_case("case-1")],
            {"case-1": _observation("one")},
            None,
            {},
        )

    assert timeouts == pytest.approx([300.0, 50.0])


def test_judge_resumes_persisted_thread_after_runner_restart(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    assert callable(namespace["save_judge_thread"])
    assert callable(namespace["judge_batch"])
    save_judge_thread: Any = namespace["save_judge_thread"]
    judge_batch: Any = namespace["judge_batch"]
    save_judge_thread(config, "thread-persisted")
    commands: list[list[str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        events = _judge_events("thread-persisted", ["case-1"])
        return 0, events, len(events)

    namespace["run_capped"] = run_capped
    judge_batch(
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("one")},
        None,
        {},
    )

    resume_index = commands[0].index("resume")
    assert commands[0][resume_index + 1] == "thread-persisted"


def test_judge_rejects_persisted_thread_with_different_artifact_binding(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    assert callable(namespace["save_judge_thread"])
    assert callable(namespace["judge_batch"])
    save_judge_thread: Any = namespace["save_judge_thread"]
    judge_batch: Any = namespace["judge_batch"]
    save_judge_thread(config, "thread-123")
    config["artifact_sha256"] = "c" * 64

    with pytest.raises(RuntimeError, match="thread binding mismatch"):
        judge_batch(
            config,
            0,
            [_case("case-1")],
            {"case-1": _observation("one")},
            None,
            {},
        )


def test_stop_schedules_detached_cleanup_without_waiting_for_runtime_deletion() -> None:
    gateway = FakeGateway()
    runner = SandboxMigrationEvaluationRunner(  # type: ignore[arg-type]
        gateway,
        resolve_credentials=lambda: ("cloud-ak", "cloud-sk", None),
    )

    runner.stop(
        _session(),
        attempt=2,
    )

    assert [operation for operation, _, _ in gateway.commands] == [
        "evaluation_protect_cloud_credentials",
        "evaluation_cancel",
    ]
    operation, command, timeout = gateway.commands[1]
    assert operation == "evaluation_cancel"
    assert timeout == 30
    assert "runner-2.pid" in command
    assert "--cleanup" in command
    assert "runner-2.json" in command
    assert "setsid bash" in command
    assert ") || true" in command
