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

from frontend.server.migration.evaluation.judge_app_server import (
    JudgeContractError,
    validate_judge_cases,
)
from frontend.server.migration.evaluation.judge_channel import (
    JUDGE_APP_SERVER_ENV,
    JUDGE_CHANNEL_SCHEMA_VERSION,
    JUDGE_TOOL_NAME,
    judge_channel_paths,
)
from frontend.server.migration.evaluation.runner import (
    AGENTKIT_CONFIG_MAX_BYTES,
    AgentkitConfigError,
    SandboxMigrationEvaluationRunner,
    judge_schema,
    normalize_agentkit_config,
    runner_source,
)
from frontend.server.migration.evaluation.service import EVALUATION_ROOT
from frontend.server.migration.gateway import (
    MigrationRemoteFileNotFound,
    MigrationSandboxSession,
)
from frontend.server.migration.service import MIGRATION_ROOT, MigrationError

TASK_ID = "migration-v1-" + "1" * 32
DATASET_SHA256 = "a" * 64
ARTIFACT_SHA256 = "b" * 64
SHARED_RUNTIME_ROLE = "AgentKit_Runtime_Default_ServiceRole"


def _shared_runtime_role(**_kwargs: object) -> str:
    return SHARED_RUNTIME_ROLE


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
        try:
            content = self.files[path]
        except KeyError as error:
            raise MigrationRemoteFileNotFound(path) from error
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
    assert "RUNTIME_OBSERVATION_LIMIT = 16 * 1024" in source
    assert "def capture_runtime_observation" in source
    assert "不得因字段名、事件名或格式不同扣分" in source
    assert 'status(config, "cleaning"' not in source
    assert "MIGRATION_EVALUATION_CLEANUP_UNCONFIRMED" not in source
    assert "import yaml" not in source
    assert "import tomllib" not in source
    assert "cloud_credential_path" in source


def test_start_uploads_non_secret_assets_and_background_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(JUDGE_APP_SERVER_ENV, raising=False)
    gateway = FakeGateway()
    role_calls: list[dict[str, object]] = []

    def resolve_runtime_role(**kwargs: object) -> str:
        role_calls.append(kwargs)
        return SHARED_RUNTIME_ROLE

    runner = SandboxMigrationEvaluationRunner(  # type: ignore[arg-type]
        gateway,
        resolve_credentials=lambda: ("cloud-ak", "cloud-sk", "cloud-token"),
        provider="byteplus",
        resolve_runtime_role=resolve_runtime_role,
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
    assert config["runtime_role_name"] == SHARED_RUNTIME_ROLE
    assert config["artifact_sha256"] == ARTIFACT_SHA256
    assert config["thread_path"].endswith("/attempt-1/thread.json")
    assert config["execution_results_path"].endswith(
        "/attempt-1/execution-results.jsonl"
    )
    judge_request_path, judge_response_path = judge_channel_paths(
        EVALUATION_ROOT,
        1,
    )
    assert config["judge_channel"] == {
        "request_path": judge_request_path,
        "response_path": judge_response_path,
        "tool_name": JUDGE_TOOL_NAME,
    }
    assert config["dimension_definitions"][0]["default_weight"] == 1
    assert config["remote_write_not_after"] == 1_788_777_600.0
    assert config["agentkit_config_protocol"] == "legacy"
    assert config["agentkit_config"]["common"]["agent_name"] == "migrated-agent"
    assert role_calls == [
        {
            "access_key": "cloud-ak",
            "secret_key": "cloud-sk",
            "session_token": "cloud-token",
            "provider": "byteplus",
        }
    ]
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


def test_start_pins_the_scripted_judge_when_the_channel_is_switched_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(JUDGE_APP_SERVER_ENV, "0")
    gateway = FakeGateway()
    runner = SandboxMigrationEvaluationRunner(  # type: ignore[arg-type]
        gateway,
        resolve_credentials=lambda: ("cloud-ak", "cloud-sk", "cloud-token"),
        provider="byteplus",
        resolve_runtime_role=lambda **_kwargs: SHARED_RUNTIME_ROLE,
    )

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

    config = json.loads(gateway.files[f"{EVALUATION_ROOT}/control/runner-1.json"])
    assert config["judge_channel"] is None


def test_start_localizes_english_judge_configuration() -> None:
    gateway = FakeGateway()
    runner = SandboxMigrationEvaluationRunner(  # type: ignore[arg-type]
        gateway,
        resolve_credentials=lambda: ("cloud-ak", "cloud-sk", None),
        resolve_runtime_role=_shared_runtime_role,
    )

    runner.start(
        _session(),
        task_id=TASK_ID,
        attempt=1,
        runtime_name="migration-eval-111111111111-a1",
        dimensions=["semantic_fidelity"],
        locale="en-US",
        dataset_sha256=DATASET_SHA256,
        artifact_sha256=ARTIFACT_SHA256,
        secret_path=None,
    )

    config = json.loads(gateway.files[f"{EVALUATION_ROOT}/control/runner-1.json"])
    assert config["locale"] == "en-US"
    assert config["dimension_definitions"][0]["name"] == ("Semantic and task fidelity")
    assert "verifiable evidence" in config["dimension_definitions"][0]["scoring_rule"]


def test_start_prefers_root_agentkit_yaml_when_both_protocols_exist() -> None:
    gateway = FakeGateway()
    gateway.files[f"{MIGRATION_ROOT}/output/veadk/.agentkit/agentkit.yaml"] = (
        b"name: structured-agent\n"
    )
    runner = SandboxMigrationEvaluationRunner(  # type: ignore[arg-type]
        gateway,
        resolve_credentials=lambda: ("cloud-ak", "cloud-sk", None),
        resolve_runtime_role=_shared_runtime_role,
    )

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

    config = json.loads(gateway.files[f"{EVALUATION_ROOT}/control/runner-1.json"])
    assert config["agentkit_config_protocol"] == "legacy"
    assert config["agentkit_config"]["common"]["agent_name"] == "migrated-agent"


def test_start_uses_structured_protocol_when_only_dot_agentkit_yaml_exists() -> None:
    gateway = FakeGateway()
    gateway.files.pop(f"{MIGRATION_ROOT}/output/veadk/agentkit.yaml")
    gateway.files[f"{MIGRATION_ROOT}/output/veadk/.agentkit/agentkit.yaml"] = (
        b"name: structured-agent\n"
        b"project: default\n"
        b"envs:\n"
        b"  MODEL_AGENT_API_KEY: ${MODEL_AGENT_API_KEY:?required}\n"
    )
    runner = SandboxMigrationEvaluationRunner(  # type: ignore[arg-type]
        gateway,
        resolve_credentials=lambda: ("cloud-ak", "cloud-sk", None),
        resolve_runtime_role=_shared_runtime_role,
    )

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

    config = json.loads(gateway.files[f"{EVALUATION_ROOT}/control/runner-1.json"])
    assert config["agentkit_config_protocol"] == "structured"
    assert config["agentkit_config"]["name"] == "structured-agent"


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


def test_runtime_role_failure_stops_before_remote_start() -> None:
    gateway = FakeGateway()

    def unavailable_role(**_kwargs: object) -> str:
        raise RuntimeError("Exceeded RolesPerAccount quota, quota: 1000")

    runner = SandboxMigrationEvaluationRunner(  # type: ignore[arg-type]
        gateway,
        resolve_credentials=lambda: ("cloud-ak", "cloud-sk", None),
        resolve_runtime_role=unavailable_role,
    )

    with pytest.raises(MigrationError) as raised:
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

    assert raised.value.code == "MIGRATION_EVALUATION_RUNTIME_ROLE_UNAVAILABLE"
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
    assert (
        "runtime_observation"
        in dimension["properties"]["evidence_sources"]["items"]["enum"]
    )
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


def test_english_judge_prompt_and_aggregate_text_are_localized(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    config["locale"] = "en-US"
    config["dimension_definitions"][0].update(
        name="Semantic and task fidelity",
        definition="Preserves intent and task completion.",
        scoring_rule="Use only verifiable evidence.",
    )
    prompts: list[str] = []

    def run_capped(_args: list[str], **kwargs: object) -> tuple[int, bytes, int]:
        prompts.append(str(kwargs["input_text"]))
        events = _judge_events("thread-en", ["case-1"])
        return 0, events, len(events)

    namespace["run_capped"] = run_capped
    observations = {"case-1": _observation("hello")}
    judged = namespace["judge_batch"](
        config,
        0,
        [_case("case-1")],
        observations,
        None,
        {},
    )
    report = namespace["build_report"](
        config,
        [_case("case-1")],
        observations,
        judged,
        {
            "id": "model",
            "codex_version": "codex",
            "agentkit_cli_version": "agentkit",
        },
        None,
    )

    assert "Write all reason and evidence text in English." in prompts[0]
    assert report["summary"]["dimensions"][0]["reason"].startswith("Aggregated from 1")
    assert report["migration_gap_description"] == (
        "Migration differences and limitations are recorded by dimension in the case evidence."
    )


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
        "runtime_observation": {
            "text": '{"output":"' + text + '"}',
            "truncated": False,
            "original_bytes": len(text.encode("utf-8")) + 13,
            "captured_bytes": len(text.encode("utf-8")) + 13,
        },
    }


def _channel_config(tmp_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Point one runner config at a judge channel on disk."""
    channel = tmp_path / "judge"
    channel.mkdir(exist_ok=True)
    request = channel / "request.json"
    response = channel / "response.json"
    config["judge_channel"] = {
        "request_path": str(request),
        "response_path": str(response),
        "tool_name": JUDGE_TOOL_NAME,
    }
    return config


def _judged_case(case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "dimensions": [
            {
                "id": "semantic_fidelity",
                "score": 0.8,
                "reason": "输出与期望一致",
                "evidence": ["输出证据"],
                "evidence_sources": ["observed_output"],
                "severity": "low",
            }
        ],
    }


def _judge_response(
    request_id: str,
    cases: list[dict[str, Any]],
    *,
    thread_id: str = "thread-channel",
) -> bytes:
    return json.dumps(
        {
            "schema_version": JUDGE_CHANNEL_SCHEMA_VERSION,
            "request_id": request_id,
            "ok": True,
            "thread_id": thread_id,
            "cases": cases,
            "created_at": "2026-09-07T10:00:00Z",
        }
    ).encode("utf-8")


def _judge_error_response(
    request_id: str, code: str = "judge_turn_unavailable"
) -> bytes:
    return json.dumps(
        {
            "schema_version": JUDGE_CHANNEL_SCHEMA_VERSION,
            "request_id": request_id,
            "ok": False,
            "thread_id": "",
            "error": {"code": code, "message": "裁判回合不可用"},
            "created_at": "2026-09-07T10:00:00Z",
        }
    ).encode("utf-8")


def _diagnostics(config: dict[str, Any]) -> list[str]:
    path = Path(config["diagnostic_path"])
    if not path.is_file():
        return []
    return [json.loads(line)["event"] for line in path.read_text().splitlines()]


def test_runner_source_keeps_the_channel_contract_in_step() -> None:
    namespace = _runner_namespace()

    assert namespace["JUDGE_CHANNEL_SCHEMA_VERSION"] == JUDGE_CHANNEL_SCHEMA_VERSION


def test_judge_channel_delivers_the_batch_without_running_codex(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    config = _channel_config(tmp_path, _judge_config(tmp_path))
    commands: list[list[str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        raise AssertionError("the channel must not fall back to codex exec")

    namespace["run_capped"] = run_capped
    Path(config["judge_channel"]["response_path"]).write_bytes(
        _judge_response("batch-001-001-attempt-1", [_judged_case("case-1")])
    )

    judged = namespace["judge_batch"](
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("hello")},
        None,
        {},
    )

    assert [item["case_id"] for item in judged] == ["case-1"]
    assert commands == []
    request = json.loads(
        Path(config["judge_channel"]["request_path"]).read_text(encoding="utf-8")
    )
    assert request["request_id"] == "batch-001-001-attempt-1"
    assert request["batch_start"] == 0
    assert request["batch_end"] == 1
    assert request["case_ids"] == ["case-1"]
    assert request["dimensions"] == ["semantic_fidelity"]
    assert request["prompt_version"] == namespace["JUDGE_PROMPT_VERSION"]
    assert request["budget_seconds"] == namespace["JUDGE_CHANNEL_TIMEOUT"]
    assert request["thread_id"] == ""
    assert request["case_context"] == [
        {
            "case_id": "case-1",
            "state": "succeeded",
            "criteria": False,
            "contract": False,
            "runtime_observation": True,
        }
    ]
    assert JUDGE_TOOL_NAME in request["prompt"]
    assert "评测用例与观察结果" in request["prompt"]
    thread_record = json.loads(Path(config["thread_path"]).read_text())
    assert thread_record["thread_id"] == "thread-channel"
    batch_record = json.loads(
        (Path(config["batch_root_path"]) / "batch-001-001.json").read_text()
    )
    assert batch_record["case_ids"] == ["case-1"]
    assert _diagnostics(config) == []


def test_judge_channel_resumes_and_rebinds_the_bound_thread(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _channel_config(tmp_path, _judge_config(tmp_path))
    config["dimensions"] = ["semantic_fidelity"]
    namespace["run_capped"] = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("no codex exec")
    )
    response_path = Path(config["judge_channel"]["response_path"])
    response_path.write_bytes(
        _judge_response(
            "batch-001-001-attempt-1",
            [_judged_case("case-1")],
            thread_id="thread-first",
        )
    )
    observations = {
        "case-1": _observation("one"),
        "case-2": _observation("two"),
    }

    namespace["judge_batch"](config, 0, [_case("case-1")], observations, None, {})
    response_path.write_bytes(
        _judge_response(
            "batch-002-002-attempt-1",
            [_judged_case("case-2")],
            thread_id="thread-second",
        )
    )
    namespace["judge_batch"](config, 1, [_case("case-2")], observations, None, {})

    request = json.loads(
        Path(config["judge_channel"]["request_path"]).read_text(encoding="utf-8")
    )
    assert request["thread_id"] == "thread-first"
    thread_record = json.loads(Path(config["thread_path"]).read_text())
    assert thread_record["thread_id"] == "thread-second"


def test_judge_channel_falls_back_to_codex_exec_on_an_error_envelope(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    config = _channel_config(tmp_path, _judge_config(tmp_path))
    commands: list[list[str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        events = _judge_events("thread-123", ["case-1"])
        return 0, events, len(events)

    namespace["run_capped"] = run_capped
    Path(config["judge_channel"]["response_path"]).write_bytes(
        _judge_error_response("batch-001-001-attempt-1")
    )

    judged = namespace["judge_batch"](
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("hello")},
        None,
        {},
    )

    assert judged[0]["case_id"] == "case-1"
    assert [command[0] for command in commands] == ["codex"]
    assert _diagnostics(config) == ["judge_channel_unavailable"]
    assert json.loads(Path(config["thread_path"]).read_text())["thread_id"] == (
        "thread-123"
    )


def test_judge_channel_rejects_a_verdict_that_is_not_a_case_list(
    tmp_path: Path,
) -> None:
    """Studio must send the case list itself, not the whole tool-call arguments."""
    namespace = _runner_namespace()
    config = _channel_config(tmp_path, _judge_config(tmp_path))
    namespace["run_capped"] = lambda *_args, **_kwargs: (
        0,
        _judge_events("thread-123", ["case-1"]),
        0,
    )
    Path(config["judge_channel"]["response_path"]).write_bytes(
        _judge_response(
            "batch-001-001-attempt-1",
            {"cases": [_judged_case("case-1")]},  # type: ignore[arg-type]
        )
    )

    judged = namespace["judge_batch"](
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("hello")},
        None,
        {},
    )

    assert judged[0]["case_id"] == "case-1"
    assert "judge_channel_output_rejected" in _diagnostics(config)


def test_runner_and_studio_agree_on_the_judge_payload_contract(tmp_path: Path) -> None:
    """The channel's in-turn validator and the runner's authority must not drift.

    Studio rejects a bad payload inside the turn so Codex can correct itself, and the
    runner repeats the checks before caching the batch.  A payload both sides disagree
    about would either waste a whole batch or cache a verdict the runner refuses.
    """
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    config["dimensions"] = ["semantic_fidelity"]
    cases = [_case("case-1")]
    observations = {"case-1": _observation("hello")}
    case_context = namespace["judge_case_context"](cases, observations, None)
    valid = _judged_case("case-1")

    def mutate(**changes: Any) -> dict[str, Any]:
        payload = json.loads(json.dumps(valid))
        payload["dimensions"][0].update(changes)
        return payload

    def studio_accepts(payload: dict[str, Any]) -> bool:
        try:
            validate_judge_cases(
                {"cases": [payload]},
                case_context=case_context,
                dimensions=config["dimensions"],
            )
        except JudgeContractError:
            return False
        return True

    def runner_accepts(payload: dict[str, Any]) -> bool:
        try:
            namespace["validate_judged_cases"](
                config,
                cases,
                [payload],
                observations,
                None,
            )
        except RuntimeError:
            return False
        return True

    payloads = {
        "valid": valid,
        "score above one": mutate(score=1.5),
        "score without severity": mutate(score=None),
        "severity without score": mutate(severity="unknown"),
        "unknown severity": mutate(severity="severe"),
        "unknown evidence source": mutate(evidence_sources=["trust_me"]),
        "duplicate evidence source": mutate(
            evidence_sources=["observed_output", "observed_output"]
        ),
        "empty reason": mutate(reason="   "),
        "evidence not a list": mutate(evidence="输出证据"),
        "missing score": mutate(score=None, severity="unknown"),
    }

    for label, payload in payloads.items():
        assert studio_accepts(payload) == runner_accepts(payload), label

    assert studio_accepts(valid) is True
    assert runner_accepts(valid) is True
    assert studio_accepts(mutate(score=1.5)) is False
    assert runner_accepts(mutate(evidence_sources=["trust_me"])) is False


def test_runner_answers_an_unscored_workflow_dimension_with_na(tmp_path: Path) -> None:
    """The runner rewrites an unsupported workflow verdict; Studio rejects it instead.

    The rewrite only ever applies to the scripted judge, because Studio refuses such a
    payload inside the turn and asks Codex to answer N/A itself.
    """
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    config["dimensions"] = ["workflow_tool_fidelity"]
    config["dimension_definitions"][0]["id"] = "workflow_tool_fidelity"
    cases = [_case("case-1")]
    observations = {"case-1": {**_observation("hello"), "runtime_observation": None}}
    payload = _judged_case("case-1")
    payload["dimensions"][0]["id"] = "workflow_tool_fidelity"

    returned = namespace["validate_judged_cases"](
        config,
        cases,
        [payload],
        observations,
        None,
    )

    dimension = returned[0]["dimensions"][0]
    assert dimension["score"] is None
    assert dimension["severity"] == "unknown"
    assert dimension["evidence"] == []


def test_judge_channel_stays_off_for_the_rest_of_the_run(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _channel_config(tmp_path, _judge_config(tmp_path))
    namespace["JUDGE_CHANNEL_TIMEOUT"] = 0.05
    namespace["JUDGE_CHANNEL_POLL_SECONDS"] = 0.01
    commands: list[list[str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        case_id = "case-1" if len(commands) == 1 else "case-2"
        events = _judge_events("thread-123", [case_id])
        return 0, events, len(events)

    namespace["run_capped"] = run_capped
    Path(config["judge_channel"]["response_path"]).write_bytes(
        _judge_error_response("batch-001-001-attempt-1")
    )
    observations = {
        "case-1": _observation("one"),
        "case-2": _observation("two"),
    }

    namespace["judge_batch"](config, 0, [_case("case-1")], observations, None, {})
    Path(config["judge_channel"]["response_path"]).write_bytes(
        _judge_response("batch-002-002-attempt-1", [_judged_case("case-2")])
    )
    namespace["judge_batch"](config, 1, [_case("case-2")], observations, None, {})

    # 首批失败后，第二批不再尝试通道：既没有新的通道诊断，也没有第二次等待。
    assert [command[0] for command in commands] == ["codex", "codex"]
    assert _diagnostics(config) == ["judge_channel_unavailable"]


def test_judge_channel_times_out_and_falls_back_to_codex_exec(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _channel_config(tmp_path, _judge_config(tmp_path))
    namespace["JUDGE_CHANNEL_TIMEOUT"] = 0.05
    namespace["JUDGE_CHANNEL_POLL_SECONDS"] = 0.01
    commands: list[list[str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        events = _judge_events("thread-123", ["case-1"])
        return 0, events, len(events)

    namespace["run_capped"] = run_capped

    judged = namespace["judge_batch"](
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("hello")},
        None,
        {},
    )

    assert judged[0]["case_id"] == "case-1"
    assert [command[0] for command in commands] == ["codex"]
    assert _diagnostics(config) == ["judge_channel_timeout"]


def test_judge_channel_declares_the_smaller_of_the_two_windows(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _channel_config(tmp_path, _judge_config(tmp_path))
    namespace["JUDGE_CHANNEL_TIMEOUT"] = 240
    Path(config["judge_channel"]["response_path"]).write_bytes(
        _judge_response("batch-001-001-attempt-1", [_judged_case("case-1")])
    )

    namespace["judge_batch"](
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("hello")},
        None,
        {},
    )

    request = json.loads(
        Path(config["judge_channel"]["request_path"]).read_text(encoding="utf-8")
    )
    assert request["budget_seconds"] == 240


def test_judge_fallback_uses_the_budget_left_after_the_channel(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _channel_config(tmp_path, _judge_config(tmp_path))
    namespace["JUDGE_CHANNEL_TIMEOUT"] = 0.15
    namespace["JUDGE_CHANNEL_POLL_SECONDS"] = 0.01
    namespace["JUDGE_TIMEOUT"] = 0.2
    timeouts: list[object] = []

    def run_capped(_args: list[str], **kwargs: object) -> tuple[int, bytes, int]:
        timeouts.append(kwargs["timeout"])
        events = _judge_events("thread-123", ["case-1"])
        return 0, events, len(events)

    namespace["run_capped"] = run_capped

    judged = namespace["judge_batch"](
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("hello")},
        None,
        {},
    )

    assert judged[0]["case_id"] == "case-1"
    request = json.loads(
        Path(config["judge_channel"]["request_path"]).read_text(encoding="utf-8")
    )
    # 声明的是两者中更小的那个：本批还剩 0.2s，通道上限 0.15s。
    assert request["budget_seconds"] == namespace["JUDGE_CHANNEL_TIMEOUT"]
    assert _diagnostics(config) == ["judge_channel_timeout"]
    # 兜底拿到的是通道用完之后的时间，而不是进入本批时的 0.2s。
    assert len(timeouts) == 1
    assert 0 < float(timeouts[0]) < 0.1  # type: ignore[arg-type]


def test_judge_channel_ignores_another_batch_response(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _channel_config(tmp_path, _judge_config(tmp_path))
    namespace["JUDGE_CHANNEL_TIMEOUT"] = 0.05
    namespace["JUDGE_CHANNEL_POLL_SECONDS"] = 0.01
    namespace["run_capped"] = lambda *_args, **_kwargs: (
        0,
        _judge_events("thread-123", ["case-1"]),
        0,
    )
    Path(config["judge_channel"]["response_path"]).write_bytes(
        _judge_response("batch-009-009-attempt-1", [_judged_case("case-9")])
    )

    judged = namespace["judge_batch"](
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("hello")},
        None,
        {},
    )

    assert judged[0]["case_id"] == "case-1"
    assert _diagnostics(config) == ["judge_channel_timeout"]


def test_judge_channel_rejects_a_verdict_that_violates_the_batch_contract(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    config = _channel_config(tmp_path, _judge_config(tmp_path))
    namespace["run_capped"] = lambda *_args, **_kwargs: (
        0,
        _judge_events("thread-123", ["case-1"]),
        0,
    )
    # 返回了别的用例：Studio 侧应当已经拒绝，这里必须再拒绝一次并回退。
    Path(config["judge_channel"]["response_path"]).write_bytes(
        _judge_response("batch-001-001-attempt-1", [_judged_case("case-2")])
    )

    judged = namespace["judge_batch"](
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("hello")},
        None,
        {},
    )

    assert judged[0]["case_id"] == "case-1"
    assert "judge_channel_output_rejected" in _diagnostics(config)


def test_judge_without_a_channel_still_uses_codex_exec(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    config["judge_channel"] = None
    commands: list[list[str]] = []

    def run_capped(args: list[str], **kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        events = _judge_events("thread-123", ["case-1"])
        assert JUDGE_TOOL_NAME not in str(kwargs["input_text"])
        return 0, events, len(events)

    namespace["run_capped"] = run_capped

    namespace["judge_batch"](
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("hello")},
        None,
        {},
    )

    assert [command[0] for command in commands] == ["codex"]
    assert not Path(config["judge_channel"] or tmp_path / "judge").exists()


def test_credential_file_requires_mode_600_and_is_one_shot(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    secret = tmp_path / "secret.json"
    secret.write_text('{"TOKEN":"value"}', encoding="utf-8")
    secret.chmod(0o644)

    with pytest.raises(PermissionError, match="integrity"):
        namespace["load_secrets"](str(secret))

    assert not secret.exists()


def test_legacy_config_uses_shared_runtime_role(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = {
        "agentkit_config_protocol": "legacy",
        "agentkit_config": {
            "common": {"agent_name": "demo", "launch_type": "cloud"},
            "launch_types": {"cloud": {"region": "cn-beijing"}},
        },
        "project_path": str(tmp_path / "project"),
        "runtime_name": "migration-eval-test-a1",
        "runtime_role_name": SHARED_RUNTIME_ROLE,
    }

    deployment = namespace["temporary_config"](config, {}, tmp_path / "work")
    staged = json.loads(Path(deployment["config_file"]).read_text(encoding="utf-8"))

    assert staged["launch_types"]["cloud"]["runtime_role_name"] == (SHARED_RUNTIME_ROLE)


def test_structured_config_is_staged_with_runtime_name_and_environment_refs(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    project = tmp_path / "project"
    (project / ".agentkit").mkdir(parents=True)
    (project / "agent.py").write_text("agent = object()\n", encoding="utf-8")
    original = {
        "name": "strands",
        "cloud_provider": "volcengine",
        "region": "cn-beijing",
        "project": "migration-project",
        "dockerfile": ".agentkit/Dockerfile",
        "runtime": {"memory_mb": 2048},
        "envs": {
            "MODEL_AGENT_API_KEY": "${MODEL_AGENT_API_KEY:?required}",
            "OPTIONAL_VALUE": "current",
        },
        "infrastructure": {"container_registry": {"instance_name": "Auto"}},
    }
    source_config = project / ".agentkit" / "agentkit.yaml"
    source_config.write_text(json.dumps(original), encoding="utf-8")
    config = {
        "agentkit_config_protocol": "structured",
        "agentkit_config": original,
        "project_path": str(project),
        "runtime_name": "migration-eval-test-a2",
        "runtime_role_name": SHARED_RUNTIME_ROLE,
    }

    deployment = namespace["temporary_config"](
        config,
        {"MODEL_AGENT_API_KEY": "model-secret", "OPTIONAL_VALUE": "override"},
        tmp_path / "work",
    )

    staged_project = Path(deployment["project_path"])
    staged = json.loads(
        (staged_project / ".agentkit" / "agentkit.yaml").read_text(encoding="utf-8")
    )
    assert deployment == {
        "protocol": "structured",
        "project_path": staged_project,
        "project_name": "migration-project",
        "config_file": staged_project / ".agentkit" / "agentkit.yaml",
    }
    assert staged["name"] == "migration-eval-test-a2"
    assert staged["role_name"] == SHARED_RUNTIME_ROLE
    assert staged["envs"]["MODEL_AGENT_API_KEY"] == "${MODEL_AGENT_API_KEY}"
    assert staged["envs"]["OPTIONAL_VALUE"] == "${OPTIONAL_VALUE}"
    assert "model-secret" not in json.dumps(staged)
    assert json.loads(source_config.read_text(encoding="utf-8")) == original


def test_structured_deploy_and_invoke_use_current_agentkit_cli(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    project = tmp_path / "project"
    project.mkdir()
    deployment = {
        "protocol": "structured",
        "project_path": project,
        "project_name": "default",
        "config_file": project / ".agentkit" / "agentkit.yaml",
    }
    commands: list[tuple[list[str], Path, bool]] = []

    def run_capped(
        args: list[str],
        *,
        cwd: Path,
        include_stderr: bool = False,
        **_kwargs: object,
    ) -> tuple[int, bytes, int]:
        commands.append((args, cwd, include_stderr))
        if args[:2] == ["agentkit", "release"]:
            output = b"deployed"
        else:
            output = b'{"output":"final answer"}\n'
        return 0, output, len(output)

    namespace["run_capped"] = run_capped
    code, output = namespace["deploy_runtime"](
        deployment,
        {},
    )
    captured = namespace["invoke_case"](
        {"task_id": TASK_ID, "remote_write_not_after": time.time() + 60},
        {
            "case_id": "case-1",
            "messages": [{"role": "user", "content": "hello"}],
        },
        "r-structured",
        {},
        deployment,
    )

    assert (code, output) == (0, b"deployed")
    assert commands[0] == (
        [
            "agentkit",
            "release",
        ],
        project,
        True,
    )
    assert commands[1] == (
        [
            "agentkit",
            "invoke",
            "run",
            "hello",
            "--runtime-id",
            "r-structured",
            "--headers",
            json.dumps(
                {
                    "user_id": "migration-evaluation",
                    "session_id": f"{TASK_ID}-case-1",
                },
                separators=(",", ":"),
            ),
            "--raw",
        ],
        project,
        True,
    )
    assert captured["output"]["text"] == "final answer"
    assert captured["runtime_observation"]["text"] == ('{"output":"final answer"}\n')


def test_runtime_observation_preserves_raw_formats_and_redacts_secrets() -> None:
    namespace = _runner_namespace()
    raw = b"\n".join(
        [
            json.dumps(
                {
                    "author": "root_agent",
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "id": "call-1",
                                    "name": "get_weather",
                                    "args": {
                                        "city": "Beijing",
                                        "api_key": "model-secret",
                                    },
                                }
                            }
                        ]
                    },
                }
            ).encode(),
            json.dumps(
                {
                    "author": "get_weather",
                    "content": {
                        "parts": [
                            {
                                "functionResponse": {
                                    "id": "call-1",
                                    "name": "get_weather",
                                    "response": {
                                        "temperature": 20,
                                        "token": "model-secret",
                                    },
                                }
                            }
                        ]
                    },
                }
            ).encode(),
            b'{"author":"root_agent","content":{"parts":[{"text":"sunny"}]},"partial":false}',
        ]
    )

    observation = namespace["capture_runtime_observation"](
        raw,
        raw_total=len(raw),
        sensitive_values=["model-secret"],
    )

    assert observation["truncated"] is False
    assert observation["captured_bytes"] == len(observation["text"].encode())
    assert "functionCall" in observation["text"]
    assert "functionResponse" in observation["text"]
    assert "get_weather" in observation["text"]
    assert "Beijing" in observation["text"]
    assert "model-secret" not in observation["text"]
    assert "<redacted>" in observation["text"]
    assert "steps" not in observation
    assert "tool_call" not in observation


def test_runtime_observation_keeps_head_and_tail_when_truncated() -> None:
    namespace = _runner_namespace()
    raw = ("head-event\n" + "x" * (20 * 1024) + "\ntail-event").encode()

    observation = namespace["capture_runtime_observation"](
        raw,
        raw_total=len(raw) + 4096,
        sensitive_values=[],
    )

    assert observation["truncated"] is True
    assert observation["captured_bytes"] <= 16 * 1024
    assert observation["original_bytes"] == len(raw) + 4096
    assert observation["text"].startswith("head-event")
    assert observation["text"].endswith("tail-event")
    assert "Runtime 原始数据已截断" in observation["text"]


def test_runtime_observation_preserves_unknown_non_json_content() -> None:
    namespace = _runner_namespace()

    observation = namespace["capture_runtime_observation"](
        b"custom event => final answer\x00\n",
        raw_total=30,
        sensitive_values=[],
    )

    assert observation["text"] == "custom event => final answer\n"
    assert observation["truncated"] is False


def test_workflow_tool_score_becomes_na_without_runtime_data_or_judging_standard(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    config["dimensions"] = ["workflow_tool_fidelity"]
    case = {
        "case_id": "case-1",
        "messages": [{"role": "user", "content": "hello"}],
        "reference_output": "hello",
        "criteria": [],
    }
    returned = [
        {
            "case_id": "case-1",
            "dimensions": [
                {
                    "id": "workflow_tool_fidelity",
                    "score": 0.9,
                    "reason": "模型猜测流程正确",
                    "evidence": ["只有最终输出"],
                    "evidence_sources": ["observed_output"],
                    "severity": "none",
                }
            ],
        }
    ]

    validated = namespace["validate_judged_cases"](
        config,
        [case],
        returned,
        {
            "case-1": {
                **_observation("hello"),
                "runtime_observation": {
                    "text": "",
                    "truncated": False,
                    "original_bytes": 0,
                    "captured_bytes": 0,
                },
            }
        },
        None,
    )

    result = validated[0]["dimensions"][0]
    assert result["score"] is None
    assert result["severity"] == "unknown"
    assert result["evidence"] == []
    assert "N/A" in result["reason"]


def test_command_diagnostics_redact_all_runtime_and_cloud_secret_values() -> None:
    namespace = _runner_namespace()
    detail = namespace["redact_command_output"](
        b"deploy failed: model-secret cloud-secret",
        {"MODEL_KEY": "model-secret", "CLOUD_KEY": "cloud-secret"},
    )

    assert detail == "deploy failed: <redacted> <redacted>"


def test_command_diagnostics_keep_the_failure_tail() -> None:
    namespace = _runner_namespace()
    detail = namespace["redact_command_output"](
        b"build progress\n" + b"x" * 4096 + b"\nModuleNotFoundError: model-secret",
        {"MODEL_KEY": "model-secret"},
    )

    assert detail.endswith("ModuleNotFoundError: <redacted>")
    assert len(detail.encode("utf-8")) <= 2048


def test_runner_failure_status_keeps_sanitized_stage_and_detail(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    status = tmp_path / "status.json"
    diagnostics = tmp_path / "diagnostics.log"
    work = tmp_path / "work"
    config = {
        "schema_version": 1,
        "task_id": TASK_ID,
        "attempt": 2,
        "locale": "zh-CN",
        "runtime_name": "migration-eval-111111111111-a2",
        "project_path": str(tmp_path / "project"),
        "work_path": str(work),
        "status_path": str(status),
        "diagnostic_path": str(diagnostics),
        "secret_path": "unused",
        "cloud_credential_path": "unused",
        "agentkit_config_protocol": "legacy",
        "agentkit_config": {},
    }

    namespace["load_secrets"] = lambda _path: {"MODEL_API_KEY": "model-secret"}

    def fail_cloud_credentials(_path: str) -> dict[str, str]:
        raise RuntimeError("credential rejected: model-secret")

    namespace["load_cloud_credentials"] = fail_cloud_credentials
    namespace["cleanup_runtime"] = lambda *_args, **_kwargs: True

    config_path = tmp_path / "runner.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    namespace["main"](str(config_path))

    failure = json.loads(status.read_text(encoding="utf-8"))
    assert failure["state"] == "failed"
    assert failure["error"] == {
        "code": "MIGRATION_EVALUATION_EXECUTION_FAILED",
        "message": "临时部署或评测执行失败，请重试。",
        "retryable": True,
        "stage": "preparing",
        "detail": "credential rejected: <redacted>",
    }
    assert "model-secret" not in status.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("protocol", "agentkit_config", "deploy_prefix", "invoke_prefix"),
    [
        (
            "legacy",
            {
                "common": {"agent_name": "demo", "launch_type": "cloud"},
                "launch_types": {"cloud": {"region": "cn-beijing"}},
            },
            ["ak", "launch"],
            ["ak", "invoke", "run"],
        ),
        (
            "structured",
            {
                "name": "demo",
                "region": "cn-beijing",
                "project": "default",
                "runtime": {"memory_mb": 2048},
                "envs": {"MODEL_AGENT_API_KEY": "${MODEL_AGENT_API_KEY:?required}"},
                "infrastructure": {"container_registry": {"instance_name": "Auto"}},
            },
            ["agentkit", "release"],
            ["agentkit", "invoke"],
        ),
    ],
)
def test_runner_main_completes_with_python_stdlib_and_fake_cli_boundaries(
    tmp_path: Path,
    protocol: str,
    agentkit_config: dict[str, object],
    deploy_prefix: list[str],
    invoke_prefix: list[str],
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
        "runtime_role_name": SHARED_RUNTIME_ROLE,
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
        "agentkit_config_protocol": protocol,
        "agentkit_config": agentkit_config,
        "remote_write_not_after": time.time() + 3600,
    }
    config_path = tmp_path / "runner.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    commands: list[list[str]] = []
    judge_prompts: list[str] = []
    progress: list[tuple[str, str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        if args[-1:] == ["--version"]:
            output = b"test-version"
        elif args[: len(deploy_prefix)] == deploy_prefix:
            output = b"deployed"
        elif args[: len(invoke_prefix)] == invoke_prefix:
            output = b'{"output":"hello"}\n'
        elif args[0] == "codex":
            judge_prompts.append(str(_kwargs["input_text"]))
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
    assert any(command[: len(deploy_prefix)] == deploy_prefix for command in commands)
    assert any(command[: len(invoke_prefix)] == invoke_prefix for command in commands)
    assert any(command[0] == "codex" for command in commands)
    assert '"runtime_observation"' in judge_prompts[0]
    assert '\\"output\\":\\"hello\\"' in judge_prompts[0]
    assert '"steps"' not in judge_prompts[0]
    assert ("executing", "正在执行用例 1/1 · 已完成 0") in progress
    assert ("executing", "已执行 1/1 · 成功 1 · 失败 0") in progress
    assert (
        "judging",
        "正在执行评测分析 · 第 1/1 批 · 用例 1–1 · 1 个维度",
    ) in progress
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
    assert batch_record["prompt_version"] == 4
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
        "runtime_observation": _observation("one")["runtime_observation"],
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

    # 两次重试共享同一个单批预算：第二次只剩第一次用剩的时间。
    assert timeouts == pytest.approx(
        [namespace["JUDGE_TIMEOUT"], namespace["JUDGE_TIMEOUT"] - 250.0]
    )


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
