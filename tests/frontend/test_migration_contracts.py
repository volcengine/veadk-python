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

import copy
from collections.abc import Callable

import pytest

from frontend.server.migration import contracts
from frontend.server.migration.models import (
    ConfirmMigrationBody,
    CreateMigrationTaskBody,
    SubmitAnalysisAnswersBody,
    is_valid_structured_entry,
)

TASK_ID = "migration-v1-" + "1" * 32
SHA256 = "2" * 64
TIMESTAMP = "2026-08-13T08:00:00Z"


def request_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "task_id": TASK_ID,
        "source_file_name": "source.zip",
        "instruction": "保持行为。",
        "session_ttl_seconds": 3600,
        "created_at": TIMESTAMP,
    }


def source_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "sha256": SHA256,
        "size": 10,
        "file_count": 1,
        "expanded_bytes": 20,
    }


def analysis_status_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "attempt": 1,
        "state": "ready",
        "message": "分析完成",
    }


def confirmation_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "task_id": TASK_ID,
        "analysis_attempt": 1,
        "analysis_sha256": SHA256,
        "input_sha256": SHA256,
        "execution_model": "structured",
        "framework": "langchain",
        "entry": "agent.py:agent",
        "app_name": "support-agent",
        "instruction": "保持行为。",
        "boundary_confirmed": True,
        "confirmed_by": "developer",
        "confirmed_at": 1,
    }


def analysis_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "recommendation_ready",
        "attempt": 1,
        "input_sha256": SHA256,
        "summary": "检测到 LangChain Agent。",
        "frameworks": [
            {
                "id": "langchain",
                "confidence": "high",
                "evidence": [{"path": "agent.py", "line": 1, "reason": "Agent 定义"}],
            }
        ],
        "recommended": {
            "framework": "langchain",
            "entry": "agent.py:agent",
            "reason": "入口明确",
        },
        "entries": [
            {
                "value": "agent.py:agent",
                "framework": "langchain",
                "evidence": "agent.py:1",
            }
        ],
        "boundary": {"include": ["Agent 行为"], "exclude": []},
        "assumptions": [],
        "questions": [],
        "warnings": [],
    }


def delivery_status_payload(*, state: str = "succeeded") -> dict[str, object]:
    ready = state in {"succeeded", "succeeded_with_warnings", "partial"}
    return {
        "schema_version": 1,
        "run_id": TASK_ID,
        "sequence": 1,
        "state": state,
        "phase": "completed",
        "message": "迁移完成",
        "artifact": {
            "state": "ready" if ready else "none",
            "preview_ready": ready,
            "download_ready": ready,
            "deploy_ready": ready and state != "partial",
        },
        "updated_at": TIMESTAMP,
    }


def delivery_result_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": TASK_ID,
        "cli": {"name": "agentkit-cli", "version": "0.52.1"},
        "migration": {
            "engine": "structured",
            "framework": "langchain",
            "entry": "agent.py:agent",
            "source_sha256": SHA256,
            "provenance_sha256": SHA256,
        },
        "status": "succeeded",
        "files": [
            {
                "path": "agentkit_app.py",
                "size": 10,
                "sha256": SHA256,
                "mode": "0644",
            },
            {
                "path": "migration-report.md",
                "size": 20,
                "sha256": SHA256,
                "mode": "0644",
            },
        ],
        "startup": {"module": "agentkit_app.py", "object": "app"},
        "environment": {"required": ["MODEL_API_KEY"], "optional": []},
        "verification": {
            "status": "passed",
            "checks": [{"name": "import", "status": "passed"}],
        },
        "warnings": [],
        "report": {"path": "migration-report.md"},
        "artifact": {
            "path": "migration-result.zip",
            "size": 30,
            "sha256": SHA256,
        },
        "created_at": TIMESTAMP,
    }


def invalid(
    validator: Callable[[object], object],
    value: object,
    match: str,
) -> None:
    with pytest.raises(contracts.MigrationContractError, match=match):
        validator(value)


def test_delivery_result_accepts_a_consistent_failed_verification() -> None:
    payload = delivery_result_payload()
    payload["verification"] = {
        "status": "failed",
        "checks": [{"name": "import", "status": "failed"}],
    }

    result = contracts.validate_delivery_result(
        payload,
        expected_run_id=TASK_ID,
        expected_status="succeeded",
    )

    assert result["verification"]["status"] == "failed"


def test_contract_primitives_reject_unsafe_values() -> None:
    invalid(
        lambda value: contracts._text(value, allow_empty=False),
        " ",
        "empty text",
    )
    invalid(
        lambda value: contracts._string_list(value, maximum_items=1),
        "not-a-list",
        "string list",
    )
    invalid(contracts._sha256, "bad", "sha256")
    invalid(contracts._timestamp_text, "not-a-time", "timestamp")
    invalid(contracts._timestamp_text, "2026-08-13T08:00:00", "timezone")
    invalid(
        contracts._reject_path_collisions,
        {"runtime", "runtime/app.py"},
        "collide",
    )
    invalid(contracts._framework, "unsupported", "framework")
    invalid(
        lambda value: contracts._bounded_integer(value, maximum=10),
        True,
        "integer",
    )


def test_request_source_analysis_and_process_contract_rejections() -> None:
    invalid(
        lambda value: contracts.validate_migration_request(
            value,
            expected_task_id=TASK_ID,
            expected_ttl_seconds=3600,
        ),
        None,
        "must be an object",
    )
    for field, value, match in (
        ("schema_version", 2, "identity"),
        ("source_file_name", "../source.zip", "source file"),
    ):
        payload = request_payload()
        payload[field] = value
        invalid(
            lambda item: contracts.validate_migration_request(
                item,
                expected_task_id=TASK_ID,
                expected_ttl_seconds=3600,
            ),
            payload,
            match,
        )
    integer_timestamp = request_payload()
    integer_timestamp["created_at"] = 1
    contracts.validate_migration_request(
        integer_timestamp,
        expected_task_id=TASK_ID,
        expected_ttl_seconds=3600,
    )

    invalid(contracts.validate_source_status, None, "must be an object")
    source = source_payload()
    source["schema_version"] = 2
    invalid(contracts.validate_source_status, source, "source status schema")

    invalid(contracts.validate_analysis_status, None, "must be an object")
    status = analysis_status_payload()
    status["state"] = "unknown"
    invalid(contracts.validate_analysis_status, status, "analysis status")
    failed = analysis_status_payload()
    failed["state"] = "failed"
    invalid(contracts.validate_analysis_status, failed, "missing an error")
    failed["error"] = {
        "code": "ANALYSIS_FAILED",
        "message": "分析失败",
        "retryable": False,
    }
    contracts.validate_analysis_status(failed)
    exposed = analysis_status_payload()
    exposed["error"] = failed["error"]
    invalid(contracts.validate_analysis_status, exposed, "exposed an error")

    invalid(contracts.validate_process_exit, None, "must be an object")
    invalid(
        contracts.validate_process_exit,
        {"schema_version": 2, "exit_code": 1},
        "process exit schema",
    )
    assert (
        contracts.validate_process_exit(
            {"schema_version": 1, "exit_code": 0, "finished_at": 1_786_600_000}
        )["finished_at"]
        == 1_786_600_000
    )
    invalid(
        contracts.validate_process_exit,
        {"schema_version": 1, "exit_code": 0, "finished_at": "now"},
        "integer",
    )
    invalid(contracts.validate_stopped_status, None, "must be an object")
    invalid(
        contracts.validate_stopped_status,
        {"schema_version": 1, "state": "running", "message": "x"},
        "stopped status",
    )


def test_confirmation_contract_rejects_identity_route_and_entry_mismatches() -> None:
    invalid(
        lambda value: contracts.validate_confirmation(value, expected_task_id=TASK_ID),
        None,
        "must be an object",
    )
    for field, value, match in (
        ("task_id", "migration-v1-" + "3" * 32, "identity"),
        ("execution_model", "agentic", "execution model"),
        ("entry", "package.agent:agent", "structured confirmation"),
    ):
        payload = confirmation_payload()
        payload[field] = value
        invalid(
            lambda item: contracts.validate_confirmation(
                item,
                expected_task_id=TASK_ID,
            ),
            payload,
            match,
        )
    agentic = confirmation_payload()
    agentic.update(
        framework="any",
        execution_model="agentic",
        entry="agent.py:agent",
    )
    invalid(
        lambda value: contracts.validate_confirmation(value, expected_task_id=TASK_ID),
        agentic,
        "agentic confirmation",
    )


def test_analysis_contract_rejects_each_untrusted_collection_boundary() -> None:
    invalid(contracts.validate_analysis_result, None, "must be an object")
    cases: list[tuple[Callable[[dict[str, object]], None], str]] = [
        (lambda value: value.update(status="unknown"), "analysis schema"),
        (lambda value: value.update(summary=""), "empty text"),
        (lambda value: value.update(frameworks="bad"), "framework candidates"),
        (lambda value: value.update(frameworks=["bad"]), "framework candidate"),
        (
            lambda value: value["frameworks"][0].update(confidence="invalid"),
            "framework candidate",
        ),
        (
            lambda value: value["frameworks"][0].update(evidence="bad"),
            "framework evidence",
        ),
        (
            lambda value: value["frameworks"][0].update(evidence=["bad"]),
            "framework evidence",
        ),
        (
            lambda value: value["frameworks"][0]["evidence"][0].update(line=0),
            "evidence line",
        ),
        (lambda value: value.update(recommended="bad"), "recommendation"),
        (lambda value: value.update(entries="bad"), "entry candidates"),
        (lambda value: value.update(entries=["bad"]), "entry candidate"),
        (
            lambda value: value["entries"][0].update(value="../agent.py:agent"),
            "entry candidate",
        ),
        (lambda value: value.update(boundary="bad"), "migration boundary"),
        (lambda value: value.update(questions="bad"), "questions"),
        (lambda value: value.update(questions=["bad"]), "question"),
    ]
    for mutate, match in cases:
        payload = analysis_payload()
        mutate(payload)
        invalid(contracts.validate_analysis_result, payload, match)

    duplicate_question = analysis_payload()
    duplicate_question.update(
        status="needs_input",
        questions=[
            {"id": "scope", "prompt": "范围？", "required": True},
            {"id": "scope", "prompt": "范围？", "required": True},
        ],
    )
    invalid(contracts.validate_analysis_result, duplicate_question, "question")

    no_required = analysis_payload()
    no_required.update(
        status="needs_input",
        questions=[{"id": "scope", "prompt": "范围？", "required": False}],
    )
    invalid(contracts.validate_analysis_result, no_required, "no required")

    completed_with_question = analysis_payload()
    completed_with_question["questions"] = [
        {"id": "scope", "prompt": "范围？", "required": True}
    ]
    invalid(
        contracts.validate_analysis_result,
        completed_with_question,
        "completed analysis",
    )

    unsupported = analysis_payload()
    unsupported.update(
        status="unsupported",
        summary=(
            "ZIP 中只有编译产物，没有可分析的项目源码。"
            "请上传包含源码、依赖声明和配置文件的项目 ZIP。"
        ),
        frameworks=[],
        recommended=None,
        entries=[],
        boundary={"include": [], "exclude": ["编译产物"]},
        warnings=["缺少源码，无法还原 Agent 行为。"],
    )
    assert contracts.validate_analysis_result(unsupported)["recommended"] is None

    unsupported_with_recommendation = analysis_payload()
    unsupported_with_recommendation["status"] = "unsupported"
    invalid(
        contracts.validate_analysis_result,
        unsupported_with_recommendation,
        "unsupported analysis has a recommendation",
    )

    unsupported_with_entry = analysis_payload()
    unsupported_with_entry.update(status="unsupported", recommended=None)
    invalid(
        contracts.validate_analysis_result,
        unsupported_with_entry,
        "unsupported analysis has entry candidates",
    )

    ready_without_recommendation = analysis_payload()
    ready_without_recommendation["recommended"] = None
    invalid(
        contracts.validate_analysis_result,
        ready_without_recommendation,
        "analysis recommendation is missing",
    )


def test_delivery_status_contract_rejects_inconsistent_artifact_states() -> None:
    invalid(
        lambda value: contracts.validate_delivery_status(
            value,
            expected_run_id=TASK_ID,
        ),
        None,
        "must be an object",
    )
    cases: list[tuple[Callable[[dict[str, object]], None], str]] = [
        (lambda value: value.update(run_id="wrong"), "delivery status"),
        (lambda value: value.update(artifact="bad"), "artifact status"),
        (
            lambda value: value["artifact"].update(state="bad"),
            "artifact state",
        ),
        (
            lambda value: value["artifact"].update(preview_ready="yes"),
            "artifact readiness",
        ),
    ]
    for mutate, match in cases:
        payload = delivery_status_payload()
        mutate(payload)
        invalid(
            lambda value: contracts.validate_delivery_status(
                value,
                expected_run_id=TASK_ID,
            ),
            payload,
            match,
        )

    active = delivery_status_payload(state="migrating")
    active["artifact"] = {
        "state": "ready",
        "preview_ready": True,
        "download_ready": True,
        "deploy_ready": True,
    }
    invalid(
        lambda value: contracts.validate_delivery_status(
            value,
            expected_run_id=TASK_ID,
        ),
        active,
        "active delivery",
    )

    failed = delivery_status_payload(state="failed")
    invalid(
        lambda value: contracts.validate_delivery_status(
            value,
            expected_run_id=TASK_ID,
        ),
        failed,
        "failed delivery",
    )
    failed["artifact"]["state"] = "unavailable"
    failed["error"] = {
        "code": "MIGRATION_FAILED",
        "message": "迁移失败",
        "retryable": False,
    }
    contracts.validate_delivery_status(failed, expected_run_id=TASK_ID)
    invalid(contracts._error, None, "delivery error")
    invalid(
        contracts._error,
        {"code": "X", "message": "x", "retryable": True},
        "not retryable",
    )


def test_delivery_result_contract_rejects_invalid_descriptors() -> None:
    invalid(
        lambda value: contracts.validate_delivery_result(
            value,
            expected_run_id=TASK_ID,
            expected_status="succeeded",
        ),
        None,
        "must be an object",
    )
    cases: list[tuple[Callable[[dict[str, object]], None], str]] = [
        (lambda value: value.update(run_id="wrong"), "identity"),
        (lambda value: value.update(cli="bad"), "cli descriptor"),
        (lambda value: value["cli"].update(name="bad"), "cli name"),
        (lambda value: value.update(migration="bad"), "migration descriptor"),
        (
            lambda value: value["migration"].update(engine="bad"),
            "migration engine",
        ),
        (
            lambda value: value["migration"].update(entry="../agent.py:agent"),
            "structured migration",
        ),
        (lambda value: value.update(files=[]), "delivery files"),
        (lambda value: value.update(files=["bad"]), "delivery file"),
        (
            lambda value: value["files"].append(copy.deepcopy(value["files"][0])),
            "duplicate delivery file",
        ),
        (
            lambda value: value["files"][0].update(mode="invalid"),
            "file mode",
        ),
        (lambda value: value.update(startup="bad"), "startup descriptor"),
        (
            lambda value: value["startup"].update(module="missing.py"),
            "startup descriptor",
        ),
        (lambda value: value.update(environment="bad"), "environment descriptor"),
        (
            lambda value: value["environment"].update(required=["1INVALID"]),
            "environment key",
        ),
        (lambda value: value.update(verification="bad"), "verification"),
        (
            lambda value: value["verification"].update(checks=["bad"]),
            "verification check",
        ),
        (
            lambda value: value["verification"]["checks"][0].update(status="bad"),
            "verification check",
        ),
        (lambda value: value.update(report="bad"), "report descriptor"),
        (lambda value: value.update(artifact="bad"), "artifact descriptor"),
        (
            lambda value: value["artifact"].update(path="bad.zip"),
            "artifact path",
        ),
    ]
    for mutate, match in cases:
        payload = delivery_result_payload()
        mutate(payload)
        invalid(
            lambda value: contracts.validate_delivery_result(
                value,
                expected_run_id=TASK_ID,
                expected_status="succeeded",
            ),
            payload,
            match,
        )

    agentic = delivery_result_payload()
    agentic["migration"].update(
        engine="agentic",
        framework="any",
        entry="agent.py:agent",
    )
    invalid(
        lambda value: contracts.validate_delivery_result(
            value,
            expected_run_id=TASK_ID,
            expected_status="succeeded",
        ),
        agentic,
        "agentic migration",
    )

    oversized = delivery_result_payload()
    oversized["files"] = [
        {
            "path": f"file-{index}.bin",
            "size": 128 * 1024 * 1024,
            "sha256": SHA256,
            "mode": "0644",
        }
        for index in range(5)
    ]
    invalid(
        lambda value: contracts.validate_delivery_result(
            value,
            expected_run_id=TASK_ID,
            expected_status="succeeded",
        ),
        oversized,
        "size limit",
    )

    empty_command = delivery_result_payload()
    empty_command["startup"]["command"] = []
    invalid(
        lambda value: contracts.validate_delivery_result(
            value,
            expected_run_id=TASK_ID,
            expected_status="succeeded",
        ),
        empty_command,
        "empty startup command",
    )

    inconsistent = delivery_result_payload()
    inconsistent["verification"] = {
        "status": "failed",
        "checks": [{"name": "import", "status": "passed", "detail": "x"}],
    }
    invalid(
        lambda value: contracts.validate_delivery_result(
            value,
            expected_run_id=TASK_ID,
            expected_status="succeeded",
        ),
        inconsistent,
        "inconsistent",
    )


def test_request_models_reject_invalid_ids_hashes_and_answers() -> None:
    assert is_valid_structured_entry(None) is False
    with pytest.raises(ValueError, match="迁移会话 ID"):
        CreateMigrationTaskBody(taskId="bad", sourceFileName="source.zip")
    with pytest.raises(ValueError, match="名称有效"):
        CreateMigrationTaskBody(sourceFileName="../source.zip")

    confirmation = {
        "framework": "langchain",
        "entry": "agent.py:agent",
        "appName": "support-agent",
        "analysisAttempt": 1,
        "analysisSha256": SHA256,
        "inputSha256": SHA256,
        "boundaryConfirmed": True,
    }
    with pytest.raises(ValueError, match="确认引用"):
        ConfirmMigrationBody(**{**confirmation, "analysisSha256": "G" * 64})
    with pytest.raises(ValueError, match="确认迁移边界"):
        ConfirmMigrationBody(**{**confirmation, "boundaryConfirmed": False})
    with pytest.raises(ValueError, match="不接受"):
        ConfirmMigrationBody(**{**confirmation, "framework": "any"})

    answers = {
        "analysisAttempt": 1,
        "analysisSha256": SHA256,
        "inputSha256": SHA256,
        "answers": {"scope": "all"},
    }
    with pytest.raises(ValueError, match="分析结果引用"):
        SubmitAnalysisAnswersBody(**{**answers, "inputSha256": "G" * 64})
    with pytest.raises(ValueError, match="不能超过 50"):
        SubmitAnalysisAnswersBody(
            **{**answers, "answers": {str(index): "x" for index in range(51)}}
        )
    with pytest.raises(ValueError, match="问题 ID"):
        SubmitAnalysisAnswersBody(**{**answers, "answers": {" ": "x"}})
    with pytest.raises(ValueError, match="4000"):
        SubmitAnalysisAnswersBody(**{**answers, "answers": {"scope": "x" * 4001}})
