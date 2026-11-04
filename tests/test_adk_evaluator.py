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


from types import SimpleNamespace

import pytest
from google.adk.evaluation.eval_case import (
    EvalCase,
    IntermediateData,
    Invocation,
    SessionInput,
)
from google.adk.evaluation.eval_set import EvalSet
from google.genai import types

from veadk.evaluation.adk_evaluator import ADKEvaluator


def _eval_set(case_count: int) -> EvalSet:
    """`case_count` single-turn cases, each expecting one distinct tool call."""
    cases = []
    for i in range(case_count):
        cases.append(
            EvalCase(
                eval_id=f"case-{i}",
                conversation=[
                    Invocation(
                        invocation_id=f"case-{i}-inv",
                        user_content=types.Content(
                            role="user", parts=[types.Part(text=f"question {i}")]
                        ),
                        final_response=types.Content(
                            role="model", parts=[types.Part(text="ok")]
                        ),
                        intermediate_data=IntermediateData(
                            tool_uses=[
                                types.FunctionCall(name=f"tool_{i}", args={"n": i})
                            ]
                        ),
                    )
                ],
                session_input=SessionInput(
                    app_name="test_app", user_id="test_user", state={}
                ),
            )
        )
    return EvalSet(eval_set_id="test_set", eval_cases=cases)


class _FakeRunEvaluator(ADKEvaluator):
    """Replaces the model run: every pass reports each case's expected values as actual.

    `generate_actual_outputs()` runs the agent on ALL cases, so each call is one real model
    call per case in production. `wrong_tool` makes one case call the wrong tool.
    """

    def __init__(self, wrong_tool: str | None = None) -> None:
        super().__init__(agent=SimpleNamespace(name="fake_agent"))
        self.passes = 0
        self._wrong_tool = wrong_tool

    async def generate_actual_outputs(self):
        self.passes += 1
        for case in self.invocation_list:
            for inv in case.invocations:
                inv.actual_output = inv.expected_output
                inv.actual_tool = list(inv.expected_tool)
        if self._wrong_tool and self.invocation_list:
            self.invocation_list[1].invocations[0].actual_tool = [
                {"name": self._wrong_tool, "args": {}}
            ]


@pytest.mark.asyncio
async def test_each_run_runs_the_cases_once():
    # 3 cases x 2 runs must cost 2 passes over the cases, not 3 x 2 = 6.
    evaluator = _FakeRunEvaluator()

    _, failures = await evaluator.evaluate(
        eval_set=_eval_set(3), num_runs=2, print_detailed_results=False
    )

    assert failures == []
    assert evaluator.passes == 2


@pytest.mark.asyncio
async def test_a_failing_case_is_still_reported_for_that_case_only():
    evaluator = _FakeRunEvaluator(wrong_tool="some_other_tool")

    results, failures = await evaluator.evaluate(
        eval_set=_eval_set(3), num_runs=2, print_detailed_results=False
    )

    assert len(results) == 1  # one eval file
    assert len(results[0]) == 6  # 3 cases x 2 metrics
    assert len(failures) == 1
    assert "tool_trajectory_avg_score" in failures[0]
