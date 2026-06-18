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

from veadk.extensions.harness.testing import GoldenCase, run_golden_cases


def test_run_golden_cases_exact_match():
    cases = [
        GoldenCase(name="case-1", input={"value": "a"}, expected={"value": "a"}),
        GoldenCase(name="case-2", input={"value": "b"}, expected={"value": "c"}),
    ]

    results = run_golden_cases(cases, lambda case: case.input)

    assert [result.passed for result in results] == [True, False]
