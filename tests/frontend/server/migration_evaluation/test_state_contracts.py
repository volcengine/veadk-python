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

import pytest

from frontend.server.migration.evaluation.contracts import (
    EVALUATION_STATES,
    EvaluationContractError,
    validate_evaluation_asset,
    validate_evaluation_report,
    validate_evaluation_status,
)

TASK_ID = "migration-v1-" + "1" * 32
SHA256 = "a" * 64
ARTIFACT_SHA256 = "b" * 64
DIMENSIONS = ["semantic_fidelity", "output_contract"]


def _status(state: str, **extra: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "task_id": TASK_ID,
        "attempt": 1,
        "state": state,
        "message": "正在评测",
        "updated_at": "2026-09-07T10:00:00Z",
        **extra,
    }


def _dimension(dimension: str, score: int | None) -> dict[str, object]:
    return {
        "id": dimension,
        "score": score,
        "reason": "有证据" if score is not None else "证据不足，记为 N/A",
        "evidence": ["观察到的输出"] if score is not None else [],
        "evidence_sources": ["observed_output"] if score is not None else [],
        "severity": "low" if score is not None else "unknown",
    }


def _report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "task_id": TASK_ID,
        "attempt": 1,
        "dataset_sha256": SHA256,
        "dataset_version": SHA256[:32],
        "artifact_sha256": ARTIFACT_SHA256,
        "prompt_version": 1,
        "model": {
            "id": "model-1",
            "codex_version": "codex-cli 0.139.0",
            "agentkit_cli_version": "0.52.16",
        },
        "dimensions": DIMENSIONS,
        "dimension_weights": {dimension: 1 for dimension in DIMENSIONS},
        "cases": [
            {
                "case_id": "case-1",
                "execution": {"state": "succeeded", "error": None},
                "output": {
                    "text": "answer",
                    "truncated": False,
                    "original_bytes": 6,
                    "captured_bytes": 6,
                },
                "dimensions": [
                    _dimension("semantic_fidelity", 80),
                    _dimension("output_contract", None),
                ],
            },
            {
                "case_id": "case-2",
                "execution": {"state": "succeeded", "error": None},
                "output": {
                    "text": "response",
                    "truncated": False,
                    "original_bytes": 8,
                    "captured_bytes": 8,
                },
                "dimensions": [
                    _dimension("semantic_fidelity", 81),
                    _dimension("output_contract", 60),
                ],
            },
        ],
        "summary": {
            "score": 71,
            "dimensions": [
                {
                    "id": "semantic_fidelity",
                    "score": 81,
                    "reason": "汇总",
                    "evidence": [],
                    "evidence_sources": ["observed_output"],
                    "severity": "low",
                },
                {
                    "id": "output_contract",
                    "score": 60,
                    "reason": "汇总",
                    "evidence": [],
                    "evidence_sources": ["observed_output"],
                    "severity": "low",
                },
            ],
        },
        "execution": {
            "total": 2,
            "succeeded": 2,
            "failed": 0,
            "success_rate": 100,
        },
        "evidence_coverage": {"total": 4, "scored": 3, "na": 1, "rate": 75},
        "source_contract_only_case_count": 0,
        "lowest_scoring_cases": [
            {"case_id": "case-2", "score": 71},
            {"case_id": "case-1", "score": 80},
        ],
        "execution_failures": [],
        "critical_mismatches": [],
        "migration_gap_description": "差距详情见案例证据。",
        "limitations": ["历史 assistant 消息仅作为裁判证据。"],
        "created_at": "2026-09-07T10:00:00Z",
    }


def test_all_required_evaluation_states_are_registered() -> None:
    assert EVALUATION_STATES == {
        "disabled",
        "waiting_dataset",
        "pending",
        "preparing",
        "waiting_environment",
        "deploying",
        "executing",
        "judging",
        "aggregating",
        "completed",
        "failed",
        "blocked",
        "cancelled",
    }


def test_status_requires_environment_names_errors_and_report_by_state() -> None:
    validate_evaluation_status(
        _status(
            "waiting_environment",
            environment={
                "required": ["ARK_API_KEY"],
                "optional": ["TZ"],
                "defaults": {"TZ": "Asia/Shanghai"},
            },
        ),
        expected_task_id=TASK_ID,
    )
    with pytest.raises(EvaluationContractError, match="environment descriptor"):
        validate_evaluation_status(
            _status("waiting_environment"), expected_task_id=TASK_ID
        )
    with pytest.raises(EvaluationContractError, match="environment descriptor"):
        validate_evaluation_status(
            _status(
                "waiting_environment",
                environment={
                    "required": ["ARK_API_KEY"],
                    "optional": ["ARK_API_KEY"],
                    "defaults": {},
                },
            ),
            expected_task_id=TASK_ID,
        )
    with pytest.raises(EvaluationContractError, match="environment descriptor"):
        validate_evaluation_status(
            _status(
                "waiting_environment",
                environment={
                    "required": ["1INVALID"],
                    "optional": [],
                    "defaults": {},
                },
            ),
            expected_task_id=TASK_ID,
        )
    with pytest.raises(EvaluationContractError, match="environment descriptor"):
        validate_evaluation_status(
            _status(
                "waiting_environment",
                environment={
                    "required": ["ARK_API_KEY"],
                    "optional": ["TZ"],
                    "defaults": {"UNDECLARED": "value"},
                },
            ),
            expected_task_id=TASK_ID,
        )
    with pytest.raises(EvaluationContractError, match="missing an error"):
        validate_evaluation_status(_status("failed"), expected_task_id=TASK_ID)
    with pytest.raises(EvaluationContractError, match="report asset"):
        validate_evaluation_status(_status("completed"), expected_task_id=TASK_ID)


def test_public_assets_are_content_bound_and_validate_kind_identity() -> None:
    dataset = {
        "schemaVersion": 1,
        "kind": "dataset",
        "assetId": f"{TASK_ID}/dataset/{SHA256[:32]}",
        "version": SHA256[:32],
        "versionId": SHA256[:32],
        "sha256": SHA256,
        "sizeBytes": 128,
        "size": 128,
        "createdAt": "2026-09-07T10:00:00Z",
        "acl": "owner",
        "viewReady": True,
        "downloadReady": True,
        "caseCount": 2,
    }
    assert validate_evaluation_asset(dataset, kind="dataset") == dataset

    invalid = dict(dataset, versionId="g" * 32)
    with pytest.raises(EvaluationContractError, match="asset"):
        validate_evaluation_asset(invalid, kind="dataset")
    invalid = dict(dataset, caseCount=True)
    with pytest.raises(EvaluationContractError, match="asset"):
        validate_evaluation_asset(invalid, kind="dataset")
    invalid = dict(dataset)
    invalid.pop("caseCount")
    with pytest.raises(EvaluationContractError, match="fields"):
        validate_evaluation_asset(invalid, kind="dataset")

    report = {
        **dataset,
        "kind": "report",
        "attempt": 2,
    }
    report.pop("caseCount")
    assert validate_evaluation_asset(report, kind="report") == report
    with pytest.raises(EvaluationContractError, match="attempt"):
        validate_evaluation_status(
            _status("completed", report_asset=report),
            expected_task_id=TASK_ID,
        )


def test_report_accepts_na_and_recomputes_scores_deterministically() -> None:
    report = _report()
    assert (
        validate_evaluation_report(
            report,
            expected_task_id=TASK_ID,
            expected_attempt=1,
            expected_dataset_sha256=SHA256,
            expected_artifact_sha256=ARTIFACT_SHA256,
            expected_dimensions=DIMENSIONS,
        )["summary"]
        == report["summary"]
    )

    report["summary"]["score"] = 70  # type: ignore[index]
    with pytest.raises(EvaluationContractError, match="overall score"):
        validate_evaluation_report(
            report,
            expected_task_id=TASK_ID,
            expected_attempt=1,
            expected_dataset_sha256=SHA256,
            expected_artifact_sha256=ARTIFACT_SHA256,
            expected_dimensions=DIMENSIONS,
        )


def test_report_accepts_json_object_keys_in_serialized_order() -> None:
    report = json.loads(json.dumps(_report(), sort_keys=True))

    validate_evaluation_report(
        report,
        expected_task_id=TASK_ID,
        expected_attempt=1,
        expected_dataset_sha256=SHA256,
        expected_artifact_sha256=ARTIFACT_SHA256,
        expected_dimensions=DIMENSIONS,
    )


def test_report_rejects_runtime_cleanup_as_non_evaluation_data() -> None:
    report = _report()
    report["runtime_cleanup"] = {"status": "confirmed"}

    with pytest.raises(EvaluationContractError, match="fields"):
        validate_evaluation_report(
            report,
            expected_task_id=TASK_ID,
            expected_attempt=1,
            expected_dataset_sha256=SHA256,
            expected_artifact_sha256=ARTIFACT_SHA256,
            expected_dimensions=DIMENSIONS,
        )


def test_report_enforces_output_capture_limit_and_dimension_order() -> None:
    report = _report()
    report["cases"][0]["output"] = {  # type: ignore[index]
        "text": "x",
        "truncated": False,
        "original_bytes": 70_000,
        "captured_bytes": 70_000,
    }
    with pytest.raises(EvaluationContractError, match="captured output"):
        validate_evaluation_report(
            report,
            expected_task_id=TASK_ID,
            expected_attempt=1,
            expected_dataset_sha256=SHA256,
            expected_artifact_sha256=ARTIFACT_SHA256,
            expected_dimensions=DIMENSIONS,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reason", "中" * (4 * 1024 // 3 + 1)),
        ("evidence", ["中" * (2 * 1024 // 3 + 1)]),
    ],
)
def test_report_enforces_utf8_byte_limits(
    field: str,
    value: object,
) -> None:
    report = _report()
    report["cases"][0]["dimensions"][0][field] = value  # type: ignore[index]

    with pytest.raises(EvaluationContractError, match="dimension result"):
        validate_evaluation_report(
            report,
            expected_task_id=TASK_ID,
            expected_attempt=1,
            expected_dataset_sha256=SHA256,
            expected_artifact_sha256=ARTIFACT_SHA256,
            expected_dimensions=DIMENSIONS,
        )


def test_retrying_is_not_a_terminal_evaluation_state() -> None:
    assert "retrying" not in EVALUATION_STATES
    task_id = "migration-v1-" + "1" * 32
    with pytest.raises(EvaluationContractError):
        validate_evaluation_status(
            {
                "schema_version": 1,
                "task_id": task_id,
                "attempt": 1,
                "state": "retrying",
                "message": "正在准备重新评测",
                "updated_at": "2026-09-07T10:00:00Z",
            },
            expected_task_id=task_id,
        )
