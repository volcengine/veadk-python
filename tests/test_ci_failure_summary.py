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

"""CI diagnostics must not copy request bodies or parametrized secret values."""

import importlib.util
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1] / ".github/scripts/report_pytest_failures.py"
)
spec = importlib.util.spec_from_file_location("ci_failure_summary", SCRIPT)
assert spec and spec.loader
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


def test_failure_summary_omits_parameters_and_assertion_payloads(tmp_path):
    report = tmp_path / "tests.xml"
    report.write_text(
        '<testsuites><testsuite><testcase classname="tests.context.test_budget" '
        'name="test_admission[private-canary]"><failure message="private-canary">'
        "tests/context/test_budget.py:12: AssertionError\nprivate-canary"
        "</failure></testcase></testsuite></testsuites>"
    )
    assert summary.failure_locations(report) == [
        "tests.context.test_budget.test_admission at tests/context/test_budget.py:12"
    ]


def test_failure_summary_ignores_passes_and_skips(tmp_path):
    report = tmp_path / "tests.xml"
    report.write_text(
        '<testsuite><testcase name="passed"/><testcase name="skipped"><skipped/></testcase></testsuite>'
    )
    assert summary.failure_locations(report) == []


def test_failure_summary_rejects_annotation_injection(tmp_path):
    report = tmp_path / "tests.xml"
    report.write_text(
        '<testsuite><testcase classname="bad%0A::warning::" name="bad%0A::warning::"><error>private-canary</error></testcase></testsuite>'
    )
    assert summary.failure_locations(report) == ["tests.collection"]
