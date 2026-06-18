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

"""Tiny deterministic eval runner for Harness modules."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import Field

from veadk.extensions.harness.schemas import HarnessBaseModel, JsonObject


class GoldenCase(HarnessBaseModel):
    """One deterministic test case."""

    name: str
    input: JsonObject = Field(default_factory=dict)
    expected: JsonObject = Field(default_factory=dict)


class GoldenResult(HarnessBaseModel):
    """Result for one golden case."""

    name: str
    passed: bool
    observed: JsonObject = Field(default_factory=dict)
    expected: JsonObject = Field(default_factory=dict)


def run_golden_cases(
    cases: list[GoldenCase],
    runner: Callable[[GoldenCase], JsonObject],
) -> list[GoldenResult]:
    """Run exact-match deterministic golden cases."""

    results = []
    for case in cases:
        observed = runner(case)
        results.append(
            GoldenResult(
                name=case.name,
                passed=observed == case.expected,
                observed=observed,
                expected=case.expected,
            )
        )
    return results
