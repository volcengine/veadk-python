# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import dataclass


@dataclass
class EvalResultCaseData:
    """Holds data for a single evaluation case result.

    This dataclass stores input, outputs, score, and status for one test case.
    Used in evaluation reporting and metrics export.

    Attributes:
        id (str): Unique ID of the case.
        input (str): User input for the case.
        actual_output (str): Actual agent response.
        expected_output (str): Expected agent response.
        score (str): Score as string from evaluation.
        reason (str): Reason for the score.
        status (str): Status like 'PASSED' or 'FAILURE'.
        latency (str): Latency in milliseconds as string.

    Note:
        Score and latency are strings for compatibility with external systems.
    """

    id: str
    input: str
    actual_output: str
    expected_output: str
    score: str
    reason: str
    status: str  # `PASSED` or `FAILURE`
    latency: str


@dataclass
class EvalResultMetadata:
    """Stores metadata about the evaluation run.

    This dataclass captures model information for the evaluation.
    Used in reporting and tracing.

    Attributes:
        tested_model (str): Name of the model being tested.
        judge_model (str): Name of the judge model used.

    Note:
        Simple structure for quick metadata access.
    """

    tested_model: str
    judge_model: str
