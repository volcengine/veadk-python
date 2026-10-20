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
from typing import Any

import pytest

from frontend.server.migration.evaluation.contracts import (
    EvaluationContractError,
    validate_evaluation_report,
)
from frontend.server.migration.evaluation.dimensions import STANDARD_DIMENSION_IDS
from frontend.server.migration.evaluation.runner import runner_source

TASK_ID = "migration-v1-" + "1" * 32
DATASET_SHA256 = "a" * 64
ARTIFACT_SHA256 = "b" * 64


@pytest.fixture
def runner() -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "evaluation_report_scoring_test"}
    exec(compile(runner_source(), "evaluation_runner.py", "exec"), namespace)
    return namespace


def _report(
    runner: dict[str, Any],
    raw_scores: list[list[float | None]],
    *,
    failed_case_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    dimensions = list(STANDARD_DIMENSION_IDS)
    config = {
        "task_id": TASK_ID,
        "attempt": 1,
        "dataset_sha256": DATASET_SHA256,
        "artifact_sha256": ARTIFACT_SHA256,
        "dimensions": dimensions,
        "dimension_definitions": [
            {"id": dimension, "default_weight": 1} for dimension in dimensions
        ],
    }
    cases = []
    judged = []
    observations = {}
    for index, scores in enumerate(raw_scores, start=1):
        case_id = f"case-{index}"
        cases.append(
            {"case_id": case_id, "messages": [{"role": "user", "content": "input"}]}
        )
        judged.append(
            {
                "case_id": case_id,
                "dimensions": [
                    {
                        "id": dimension,
                        "score": score,
                        "reason": "Evidence available" if score is not None else "N/A",
                        "evidence": [],
                        "evidence_sources": [],
                        "severity": "low" if score is not None else "unknown",
                    }
                    for dimension, score in zip(dimensions, scores)
                ],
            }
        )
        failed = case_id in failed_case_ids
        captured = {
            "text": "",
            "truncated": False,
            "original_bytes": 0,
            "captured_bytes": 0,
        }
        observations[case_id] = {
            "state": "failed" if failed else "succeeded",
            "error": (
                {
                    "code": "MIGRATION_EVALUATION_CASE_EXECUTION_FAILED",
                    "message": "Runtime invocation failed",
                }
                if failed
                else None
            ),
            "output": captured,
            "runtime_observation": dict(captured),
        }
    return runner["build_report"](
        config,
        cases,
        observations,
        judged,
        {"id": "model", "codex_version": "codex", "agentkit_cli_version": "agentkit"},
        None,
    )


def _validate(report: dict[str, Any]) -> None:
    validate_evaluation_report(
        json.loads(json.dumps(report, sort_keys=True)),
        expected_task_id=TASK_ID,
        expected_attempt=1,
        expected_dataset_sha256=DATASET_SHA256,
        expected_artifact_sha256=ARTIFACT_SHA256,
        expected_dimensions=list(STANDARD_DIMENSION_IDS),
    )


@pytest.mark.parametrize(
    ("raw_score", "expected"),
    [(None, None), (0, 0), (1, 100), (0.5749, 57), (0.575, 58), (0.5751, 58)],
)
def test_display_score_uses_decimal_half_up(
    runner: dict[str, Any], raw_score: float | None, expected: int | None
) -> None:
    assert runner["display_score"](raw_score) == expected


def test_display_score_matches_every_normalized_judge_score(
    runner: dict[str, Any],
) -> None:
    # Judge scores are normalized to four decimal places. The integer oracle
    # covers their entire domain without depending on float or Decimal rounding.
    for units in range(10_001):
        assert runner["display_score"](units / 10_000) == (units + 50) // 100, units


@pytest.mark.parametrize(
    ("raw_scores", "dimension_scores", "overall", "case_scores"),
    [
        pytest.param(
            [[0.7, 0.7, 0.6], [0.15, 0.7, 0.6]],
            [43, 70, 60],
            58,
            [67, 48],
            id="byteplus-report-regression",
        ),
        pytest.param(
            [[0.704, 0.7, 0.6], [0.704, 0.7, 0.6], [0.714, 0.7, 0.6]],
            [70, 70, 60],
            67,
            [67, 67, 67],
            id="rounded-case-dimension-mean",
        ),
        pytest.param(
            [[0.704, 0.704, 0.714]],
            [70, 70, 71],
            70,
            [70],
            id="rounded-case-ranking",
        ),
        pytest.param(
            [[0.4, 0.4, 0.4], [0.41, 0.41, 0.4]],
            [41, 41, 40],
            41,
            [40, 41],
            id="rounded-dimension-overall-mean",
        ),
        pytest.param(
            [[None, 0.8, 0.6], [0.5, None, None]],
            [50, 80, 60],
            63,
            [70, 50],
            id="partial-na",
        ),
        pytest.param(
            [[None, None, None]],
            [None, None, None],
            None,
            [None],
            id="all-na",
        ),
        pytest.param(
            [[0, 0, 0], [1, 1, 1]],
            [50, 50, 50],
            50,
            [0, 100],
            id="zero-and-full-score",
        ),
    ],
)
def test_generated_report_scores_satisfy_storage_contract(
    runner: dict[str, Any],
    raw_scores: list[list[float | None]],
    dimension_scores: list[int | None],
    overall: int | None,
    case_scores: list[int | None],
) -> None:
    report = _report(runner, raw_scores)
    _validate(report)

    assert report["summary"]["score"] == overall
    assert [
        item["score"] for item in report["summary"]["dimensions"]
    ] == dimension_scores
    expected_lowest = sorted(
        [
            {"case_id": f"case-{index}", "score": score}
            for index, score in enumerate(case_scores, start=1)
            if score is not None
        ],
        key=lambda item: (item["score"], item["case_id"]),
    )
    assert report["lowest_scoring_cases"] == expected_lowest


def test_generated_report_excludes_failed_execution_from_scores(
    runner: dict[str, Any],
) -> None:
    report = _report(
        runner,
        [[0.7, 0.7, 0.6], [None, None, None]],
        failed_case_ids=("case-2",),
    )
    _validate(report)

    assert report["summary"]["score"] == 67
    assert report["execution"] == {
        "total": 2,
        "succeeded": 1,
        "failed": 1,
        "success_rate": 50,
    }
    assert report["evidence_coverage"] == {"total": 6, "scored": 3, "na": 3, "rate": 50}
    assert report["lowest_scoring_cases"] == [{"case_id": "case-1", "score": 67}]
    assert report["execution_failures"][0]["case_id"] == "case-2"


@pytest.mark.parametrize(
    ("target", "error"),
    [
        ("overall", "overall score is not deterministic"),
        ("dimension", "summary score is not deterministic"),
        ("ranking", "lowest-scoring cases are not deterministic"),
    ],
)
def test_generated_report_still_rejects_modified_aggregates(
    runner: dict[str, Any], target: str, error: str
) -> None:
    report = _report(runner, [[0.8, 0.8, 0.8]])
    _validate(report)
    if target == "overall":
        report["summary"]["score"] = 81
    elif target == "dimension":
        report["summary"]["dimensions"][0]["score"] = 81
    else:
        report["lowest_scoring_cases"][0]["score"] = 81

    with pytest.raises(EvaluationContractError, match=error):
        _validate(report)
