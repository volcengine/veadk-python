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

"""Canonical, hashable evaluation dataset representation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from .dimensions import EVALUATION_DIMENSION_IDS
from .models import (
    EVALUATION_CASES_MAX,
    EVALUATION_DATASET_MAX_BYTES,
    EvaluationDatasetBody,
)

EVALUATION_REASON_MAX_BYTES = 4 * 1024
EVALUATION_EVIDENCE_MAX_BYTES = 2 * 1024
EVALUATION_LIMITATION_MAX_BYTES = 4 * 1024
_VERSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EVALUATION_EVIDENCE_SOURCES = frozenset(
    {
        "user_reference",
        "user_criteria",
        "source_contract",
        "observed_output",
        "deterministic_assertion",
    }
)
EVALUATION_SEVERITIES = frozenset(
    {"none", "low", "medium", "high", "critical", "unknown"}
)


class EvaluationContractError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedEvaluationDataset:
    content: bytes
    sha256: str
    version_id: str
    case_count: int


def normalize_dataset(body: EvaluationDatasetBody) -> NormalizedEvaluationDataset:
    lines = [
        json.dumps(
            item.canonical(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        for item in body.cases
    ]
    content = b"\n".join(lines) + b"\n"
    if len(content) > EVALUATION_DATASET_MAX_BYTES:
        raise EvaluationContractError("标准化后的评测数据集不能超过 10 MiB")
    digest = hashlib.sha256(content).hexdigest()
    return NormalizedEvaluationDataset(
        content=content,
        sha256=digest,
        version_id=digest[:32],
        case_count=len(lines),
    )


EVALUATION_STATES = frozenset(
    {
        "disabled",
        "waiting_dataset",
        "pending",
        "preparing",
        "waiting_environment",
        "deploying",
        "executing",
        "judging",
        "aggregating",
        "cleaning",
        "completed",
        "failed",
        "blocked",
        "cancelled",
    }
)
_ACTIVE_STATES = {
    "preparing",
    "deploying",
    "executing",
    "judging",
    "aggregating",
    "cleaning",
}


def _exact_keys(
    value: dict[str, object],
    *,
    required: set[str],
    optional: set[str] | frozenset[str] = frozenset(),
) -> None:
    keys = set(value)
    if not required.issubset(keys) or not keys.issubset(required | optional):
        raise EvaluationContractError("unexpected object fields")


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise EvaluationContractError("invalid timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvaluationContractError("invalid timestamp") from error
    if parsed.tzinfo is None:
        raise EvaluationContractError("timestamp is missing a timezone")
    return value


def _score(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise EvaluationContractError("invalid score")
    return value


def validate_evaluation_status(
    value: object,
    *,
    expected_task_id: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise EvaluationContractError("evaluation status must be an object")
    _exact_keys(
        value,
        required={
            "schema_version",
            "task_id",
            "attempt",
            "state",
            "message",
            "updated_at",
        },
        optional={
            "required_environment",
            "runtime_name",
            "error",
            "report_asset",
        },
    )
    state = value.get("state")
    attempt = value.get("attempt")
    if (
        value.get("schema_version") != 1
        or value.get("task_id") != expected_task_id
        or state not in EVALUATION_STATES
        or isinstance(attempt, bool)
        or not isinstance(attempt, int)
        or not 0 <= attempt <= 100
        or not isinstance(value.get("message"), str)
        or not str(value["message"]).strip()
    ):
        raise EvaluationContractError("invalid evaluation status")
    _timestamp(value.get("updated_at"))
    required_environment = value.get("required_environment")
    if state == "waiting_environment":
        if (
            not isinstance(required_environment, list)
            or not required_environment
            or any(
                not isinstance(item, str) or not item for item in required_environment
            )
            or len(set(required_environment)) != len(required_environment)
        ):
            raise EvaluationContractError("invalid required environment")
    elif required_environment is not None:
        raise EvaluationContractError("unexpected required environment")
    error = value.get("error")
    if state in {"failed", "blocked"}:
        if not isinstance(error, dict):
            raise EvaluationContractError(
                "terminal evaluation status is missing an error"
            )
        _exact_keys(error, required={"code", "message", "retryable"})
        if (
            not isinstance(error.get("code"), str)
            or not error["code"]
            or not isinstance(error.get("message"), str)
            or not error["message"]
            or not isinstance(error.get("retryable"), bool)
        ):
            raise EvaluationContractError("invalid evaluation error")
    elif error is not None:
        raise EvaluationContractError("non-failed evaluation exposed an error")
    report_asset = value.get("report_asset")
    if state == "completed":
        if not isinstance(report_asset, dict):
            raise EvaluationContractError(
                "completed evaluation is missing its report asset"
            )
        validated_asset = validate_evaluation_asset(report_asset, kind="report")
        if validated_asset["attempt"] != attempt:
            raise EvaluationContractError("report asset attempt does not match status")
    elif report_asset is not None:
        raise EvaluationContractError("non-completed evaluation exposed a report asset")
    runtime_name = value.get("runtime_name")
    if runtime_name is not None and (
        not isinstance(runtime_name, str) or not runtime_name.strip()
    ):
        raise EvaluationContractError("invalid runtime name")
    if state in _ACTIVE_STATES and attempt < 1:
        raise EvaluationContractError("active evaluation is missing an attempt")
    return {str(key): item for key, item in value.items()}


def validate_evaluation_asset(
    value: object,
    *,
    kind: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or kind not in {"dataset", "report"}:
        raise EvaluationContractError("invalid evaluation asset")
    required = {
        "schemaVersion",
        "kind",
        "assetId",
        "version",
        "versionId",
        "sha256",
        "sizeBytes",
        "size",
        "createdAt",
        "acl",
        "viewReady",
        "downloadReady",
    }
    required.add("caseCount" if kind == "dataset" else "attempt")
    _exact_keys(value, required=required)
    size = value.get("size")
    version_id = value.get("versionId")
    sha256 = value.get("sha256")
    if (
        value.get("schemaVersion") != 1
        or value.get("kind") != kind
        or value.get("acl") != "owner"
        or not isinstance(value.get("assetId"), str)
        or not str(value["assetId"]).strip()
        or len(str(value["assetId"])) > 256
        or value.get("version") != version_id
        or not isinstance(version_id, str)
        or _VERSION_ID_RE.fullmatch(version_id) is None
        or not isinstance(sha256, str)
        or _SHA256_RE.fullmatch(sha256) is None
        or version_id != sha256[:32]
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size <= 0
        or value.get("sizeBytes") != size
        or value.get("viewReady") is not True
        or value.get("downloadReady") is not True
    ):
        raise EvaluationContractError("invalid evaluation asset")
    identity = value.get("caseCount" if kind == "dataset" else "attempt")
    if (
        isinstance(identity, bool)
        or not isinstance(identity, int)
        or not 1 <= identity <= EVALUATION_CASES_MAX
    ):
        raise EvaluationContractError("invalid evaluation asset")
    _timestamp(value.get("createdAt"))
    return {str(key): item for key, item in value.items()}


def validate_evaluation_report(
    value: object,
    *,
    expected_task_id: str,
    expected_attempt: int,
    expected_dataset_sha256: str,
    expected_artifact_sha256: str,
    expected_dimensions: list[str],
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise EvaluationContractError("evaluation report must be an object")
    _exact_keys(
        value,
        required={
            "schema_version",
            "task_id",
            "attempt",
            "dataset_sha256",
            "dataset_version",
            "artifact_sha256",
            "prompt_version",
            "model",
            "dimensions",
            "dimension_weights",
            "cases",
            "summary",
            "execution",
            "evidence_coverage",
            "source_contract_only_case_count",
            "lowest_scoring_cases",
            "execution_failures",
            "critical_mismatches",
            "migration_gap_description",
            "runtime_cleanup",
            "limitations",
            "created_at",
        },
    )
    dimensions = value.get("dimensions")
    cases = value.get("cases")
    limitations = value.get("limitations")
    dataset_sha256 = value.get("dataset_sha256")
    artifact_sha256 = value.get("artifact_sha256")
    prompt_version = value.get("prompt_version")
    if (
        value.get("schema_version") != 1
        or value.get("task_id") != expected_task_id
        or value.get("attempt") != expected_attempt
        or dataset_sha256 != expected_dataset_sha256
        or _SHA256_RE.fullmatch(str(dataset_sha256)) is None
        or value.get("dataset_version") != expected_dataset_sha256[:32]
        or artifact_sha256 != expected_artifact_sha256
        or not isinstance(artifact_sha256, str)
        or _SHA256_RE.fullmatch(artifact_sha256) is None
        or isinstance(prompt_version, bool)
        or not isinstance(prompt_version, int)
        or prompt_version < 1
        or dimensions != expected_dimensions
        or any(item not in EVALUATION_DIMENSION_IDS for item in expected_dimensions)
        or not isinstance(cases, list)
        or not 1 <= len(cases) <= 100
        or not isinstance(limitations, list)
        or len(limitations) > 100
        or any(
            not isinstance(item, str)
            or len(item.encode("utf-8")) > EVALUATION_LIMITATION_MAX_BYTES
            for item in limitations
        )
    ):
        raise EvaluationContractError("invalid evaluation report identity")
    _validate_report_model(value.get("model"))
    weights = value.get("dimension_weights")
    if (
        not isinstance(weights, dict)
        or list(weights) != expected_dimensions
        or any(
            isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or weight <= 0
            for weight in weights.values()
        )
    ):
        raise EvaluationContractError("invalid evaluation dimension weights")
    _timestamp(value.get("created_at"))
    case_ids: set[str] = set()
    dimension_scores: dict[str, list[int]] = {
        dimension: [] for dimension in expected_dimensions
    }
    execution_succeeded = 0
    execution_failures: list[dict[str, object]] = []
    case_scores: list[dict[str, object]] = []
    critical_mismatches: list[dict[str, object]] = []
    for case in cases:
        if not isinstance(case, dict):
            raise EvaluationContractError("invalid evaluation case result")
        _exact_keys(
            case,
            required={"case_id", "execution", "output", "dimensions"},
        )
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            raise EvaluationContractError("invalid evaluation case id")
        case_ids.add(case_id)
        execution = _validate_execution(case.get("execution"))
        if execution["state"] == "succeeded":
            execution_succeeded += 1
        else:
            error = execution["error"]
            assert isinstance(error, dict)
            execution_failures.append(
                {
                    "case_id": case_id,
                    "code": error["code"],
                    "message": error["message"],
                }
            )
        _validate_captured_output(case.get("output"))
        result_dimensions = case.get("dimensions")
        if (
            not isinstance(result_dimensions, list)
            or [
                item.get("id") if isinstance(item, dict) else None
                for item in result_dimensions
            ]
            != expected_dimensions
        ):
            raise EvaluationContractError("invalid case dimensions")
        current_scores: list[int] = []
        for result in result_dimensions:
            assert isinstance(result, dict)
            score = _validate_dimension_result(result)
            if execution["state"] == "failed" and score is not None:
                raise EvaluationContractError(
                    "failed execution exposed a dimension score"
                )
            if score is not None:
                dimension_scores[str(result["id"])].append(score)
                current_scores.append(score)
            if result.get("severity") == "critical":
                critical_mismatches.append(
                    {
                        "case_id": case_id,
                        "dimension_id": result["id"],
                        "severity": "critical",
                        "reason": result["reason"],
                        "evidence_sources": result["evidence_sources"],
                    }
                )
        case_score = _rounded_average(current_scores)
        if case_score is not None:
            case_scores.append({"case_id": case_id, "score": case_score})
    summary = value.get("summary")
    if not isinstance(summary, dict):
        raise EvaluationContractError("invalid evaluation summary")
    _exact_keys(summary, required={"score", "dimensions"})
    summary_dimensions = summary.get("dimensions")
    if (
        not isinstance(summary_dimensions, list)
        or [
            item.get("id") if isinstance(item, dict) else None
            for item in summary_dimensions
        ]
        != expected_dimensions
    ):
        raise EvaluationContractError("invalid summary dimensions")
    expected_summary_scores: list[int] = []
    for item in summary_dimensions:
        assert isinstance(item, dict)
        score = _validate_dimension_result(item)
        scores = dimension_scores[str(item["id"])]
        expected = _rounded_average(scores)
        if score != expected:
            raise EvaluationContractError("summary score is not deterministic")
        if score is not None:
            expected_summary_scores.append(score)
    if _score(summary.get("score")) != _rounded_average(expected_summary_scores):
        raise EvaluationContractError("overall score is not deterministic")
    _validate_report_aggregates(
        value,
        case_count=len(cases),
        dimension_count=len(expected_dimensions),
        scored_count=sum(len(scores) for scores in dimension_scores.values()),
        execution_succeeded=execution_succeeded,
        execution_failures=execution_failures,
        case_scores=case_scores,
        critical_mismatches=critical_mismatches,
    )
    return {str(key): item for key, item in value.items()}


def _validate_report_model(value: object) -> None:
    if not isinstance(value, dict):
        raise EvaluationContractError("invalid evaluation model metadata")
    _exact_keys(
        value,
        required={"id", "codex_version", "agentkit_cli_version"},
    )
    if any(
        not isinstance(value.get(key), str)
        or not str(value[key]).strip()
        or len(str(value[key]).encode("utf-8")) > 512
        for key in ("id", "codex_version", "agentkit_cli_version")
    ):
        raise EvaluationContractError("invalid evaluation model metadata")


def _validate_execution(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise EvaluationContractError("invalid case execution result")
    _exact_keys(value, required={"state", "error"})
    state = value.get("state")
    error = value.get("error")
    if state == "succeeded":
        if error is not None:
            raise EvaluationContractError("successful execution exposed an error")
    elif state == "failed":
        if not isinstance(error, dict):
            raise EvaluationContractError("failed execution is missing an error")
        _exact_keys(error, required={"code", "message"})
        if (
            error.get("code") != "MIGRATION_EVALUATION_CASE_EXECUTION_FAILED"
            or not isinstance(error.get("message"), str)
            or not str(error["message"]).strip()
            or len(str(error["message"]).encode("utf-8")) > 1024
        ):
            raise EvaluationContractError("invalid case execution error")
    else:
        raise EvaluationContractError("invalid case execution state")
    return {str(key): item for key, item in value.items()}


def _validate_report_aggregates(
    value: dict[str, object],
    *,
    case_count: int,
    dimension_count: int,
    scored_count: int,
    execution_succeeded: int,
    execution_failures: list[dict[str, object]],
    case_scores: list[dict[str, object]],
    critical_mismatches: list[dict[str, object]],
) -> None:
    execution = value.get("execution")
    expected_execution = {
        "total": case_count,
        "succeeded": execution_succeeded,
        "failed": case_count - execution_succeeded,
        "success_rate": _percentage(execution_succeeded, case_count),
    }
    if execution != expected_execution:
        raise EvaluationContractError("execution summary is not deterministic")
    total_slots = case_count * dimension_count
    expected_coverage = {
        "total": total_slots,
        "scored": scored_count,
        "na": total_slots - scored_count,
        "rate": _percentage(scored_count, total_slots),
    }
    if value.get("evidence_coverage") != expected_coverage:
        raise EvaluationContractError("evidence coverage is not deterministic")
    source_only = value.get("source_contract_only_case_count")
    if (
        isinstance(source_only, bool)
        or not isinstance(source_only, int)
        or not 0 <= source_only <= case_count
    ):
        raise EvaluationContractError("invalid source-contract-only case count")
    expected_lowest = sorted(
        case_scores,
        key=lambda item: (
            cast(int, item["score"]),
            cast(str, item["case_id"]),
        ),
    )[:10]
    if value.get("lowest_scoring_cases") != expected_lowest:
        raise EvaluationContractError("lowest-scoring cases are not deterministic")
    if value.get("execution_failures") != execution_failures:
        raise EvaluationContractError("execution failures are not deterministic")
    if value.get("critical_mismatches") != critical_mismatches:
        raise EvaluationContractError("critical evidence is not deterministic")
    gap = value.get("migration_gap_description")
    if (
        not isinstance(gap, str)
        or not gap.strip()
        or len(gap.encode("utf-8")) > EVALUATION_REASON_MAX_BYTES
    ):
        raise EvaluationContractError("invalid migration gap description")
    cleanup = value.get("runtime_cleanup")
    if cleanup != {"status": "confirmed"}:
        raise EvaluationContractError("runtime cleanup is not confirmed")


def _percentage(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise EvaluationContractError("invalid percentage denominator")
    return (200 * numerator + denominator) // (2 * denominator)


def _validate_captured_output(value: object) -> None:
    if not isinstance(value, dict):
        raise EvaluationContractError("invalid captured output")
    _exact_keys(
        value,
        required={"text", "truncated", "original_bytes", "captured_bytes"},
    )
    text = value.get("text")
    original = value.get("original_bytes")
    captured = value.get("captured_bytes")
    if (
        not isinstance(text, str)
        or not isinstance(value.get("truncated"), bool)
        or isinstance(original, bool)
        or not isinstance(original, int)
        or isinstance(captured, bool)
        or not isinstance(captured, int)
        or not 0 <= captured <= 64 * 1024
        or original < captured
        or len(text.encode("utf-8")) != captured
        or value["truncated"] is not (original > captured)
    ):
        raise EvaluationContractError("invalid captured output")


def _validate_dimension_result(value: dict[str, object]) -> int | None:
    _exact_keys(
        value,
        required={
            "id",
            "score",
            "reason",
            "evidence",
            "evidence_sources",
            "severity",
        },
    )
    score = _score(value.get("score"))
    evidence = value.get("evidence")
    evidence_sources = value.get("evidence_sources")
    severity = value.get("severity")
    if (
        not isinstance(value.get("reason"), str)
        or not str(value["reason"]).strip()
        or len(str(value["reason"]).encode("utf-8")) > EVALUATION_REASON_MAX_BYTES
        or not isinstance(evidence, list)
        or len(evidence) > 20
        or any(
            not isinstance(item, str)
            or len(item.encode("utf-8")) > EVALUATION_EVIDENCE_MAX_BYTES
            for item in evidence
        )
        or not isinstance(evidence_sources, list)
        or any(not isinstance(item, str) for item in evidence_sources)
        or len(evidence_sources) != len(set(evidence_sources))
        or any(item not in EVALUATION_EVIDENCE_SOURCES for item in evidence_sources)
        or severity not in EVALUATION_SEVERITIES
        or ((score is None) is not (severity == "unknown"))
    ):
        raise EvaluationContractError("invalid dimension result")
    return score


def _rounded_average(values: list[int]) -> int | None:
    if not values:
        return None
    return (2 * sum(values) + len(values)) // (2 * len(values))


__all__ = [
    "EVALUATION_STATES",
    "EVALUATION_EVIDENCE_MAX_BYTES",
    "EVALUATION_LIMITATION_MAX_BYTES",
    "EVALUATION_REASON_MAX_BYTES",
    "EvaluationContractError",
    "NormalizedEvaluationDataset",
    "normalize_dataset",
    "validate_evaluation_asset",
    "validate_evaluation_report",
    "validate_evaluation_status",
]
