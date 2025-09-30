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

import os
import time
import uuid
from os import path

from google.adk.evaluation.agent_evaluator import (
    RESPONSE_MATCH_SCORE_KEY,
    TOOL_TRAJECTORY_SCORE_KEY,
    AgentEvaluator,
)
from google.adk.evaluation.eval_case import IntermediateData, Invocation
from google.adk.evaluation.evaluator import EvalStatus
from google.adk.evaluation.eval_set import EvalSet
from typing import Optional
from typing_extensions import override
from veadk.evaluation.base_evaluator import BaseEvaluator
from types import SimpleNamespace
from google.genai import types as genai_types

from google.adk.evaluation.eval_metrics import EvalMetric
from google.adk.evaluation.metric_evaluator_registry import (
    DEFAULT_METRIC_EVALUATOR_REGISTRY,
)
import inspect


def formatted_timestamp():
    # YYYYMMDDHHMMSS
    return time.strftime("%Y%m%d%H%M%S", time.localtime())


class ADKEvaluator(BaseEvaluator):
    def __init__(
        self,
        agent,
        name: str = "veadk_adk_evaluator",
    ):
        super().__init__(agent=agent, name=name)

    @override
    async def evaluate(
        self,
        eval_set: Optional[EvalSet] = None,
        eval_set_file_path: Optional[str] = None,
        eval_id: str = f"test_{formatted_timestamp()}",
        tool_score_threshold: float = 1.0,
        response_match_score_threshold: float = 0.8,
        num_runs: int = 2,
        print_detailed_results: bool = True,
    ):
        """
        End-to-end evaluation flow:
        1) Discover test files (.test.json) or accept a single path.
        2) Build metric criteria (metric_name -> threshold).
        3) For each file, build in-memory eval cases via BaseEvaluator.
        4) For each eval case, construct expected ADK Invocations from expected data.
        5) Repeat for num_runs:
           - Reset all session_ids to isolate state.
           - Generate actual outputs via BaseEvaluator and convert to ADK Invocations.
        6) Repeat expected invocations to match num_runs for 1:1 alignment.
        7) For each metric:
           - Create EvalMetric and get the evaluator from ADK's registry.
           - Call evaluate_invocations (await if async) to get EvaluationResult with:
             overall_score/overall_eval_status + per_invocation_results.
           - Optionally pretty print via AgentEvaluator._print_details.
           - Record failure if overall status != PASSED.
        8) Return (all evaluation_result objects, failures) to the caller.
        """

        # Resolve eval files: accept a directory (scan *.test.json) or a single file
        test_files = []
        eval_dataset_file_path_or_dir = eval_set_file_path
        if isinstance(eval_dataset_file_path_or_dir, str) and os.path.isdir(
            eval_dataset_file_path_or_dir
        ):
            for root, _, files in os.walk(eval_dataset_file_path_or_dir):
                for file in files:
                    if file.endswith(".test.json"):
                        test_files.append(path.join(root, file))
        else:
            test_files = [eval_dataset_file_path_or_dir]

        # Build metric criteria (metric_name -> threshold)
        criteria = {
            TOOL_TRAJECTORY_SCORE_KEY: tool_score_threshold,  # 1-point scale; 1.0 means perfect tool call trajectory
            RESPONSE_MATCH_SCORE_KEY: response_match_score_threshold,  # Rouge-1 text match; 0.8 default threshold
        }

        # Aggregate all evaluation results and failures across files
        result = []
        failures = []

        # Iterate each test file and evaluate per-case, per-metric
        for test_file in test_files:
            # Build in-memory evaluation cases via BaseEvaluator from the provided file
            self.build_eval_set(eval_set, test_file)

            evaluation_result_list = []

            # For each eval case, generate actual outputs num_runs times using BaseEvaluator
            for case_idx, eval_case_data in enumerate(self.invocation_list):
                # Convert BaseEvaluator's expected data into ADK Invocation list
                expected_invocations: list[Invocation] = []
                for inv in eval_case_data.invocations:
                    user_content = genai_types.Content(
                        role="user",
                        parts=[genai_types.Part(text=inv.input or "")],
                    )
                    expected_final = genai_types.Content(
                        role=None,
                        parts=[genai_types.Part(text=inv.expected_output or "")],
                    )
                    expected_tool_calls = [
                        SimpleNamespace(name=t.get("name"), args=t.get("args", {}))
                        for t in (inv.expected_tool or [])
                    ]
                    # Pack a full expected Invocation for ADK metrics
                    expected_invocations.append(
                        Invocation(
                            invocation_id=inv.invocation_id,
                            user_content=user_content,
                            final_response=expected_final,
                            intermediate_data=IntermediateData(
                                tool_uses=expected_tool_calls
                            ),
                        )
                    )

                # Collect actual invocations across runs
                actual_invocations_all_runs: list[Invocation] = []
                for _ in range(num_runs):
                    for agent_information in self.agent_information_list:
                        agent_information["session_id"] = str(uuid.uuid4())

                    # Generate actual outputs for all cases in this run via BaseEvaluator
                    await self.generate_actual_outputs()

                    # Convert BaseEvaluator's actual data into ADK Invocation list
                    for inv in eval_case_data.invocations:
                        user_content = genai_types.Content(
                            role="user",
                            parts=[genai_types.Part(text=inv.input or "")],
                        )
                        actual_final = genai_types.Content(
                            role=None,
                            parts=[genai_types.Part(text=inv.actual_output or "")],
                        )
                        # Collect the tool calls observed during actual execution
                        actual_tool_calls = [
                            SimpleNamespace(name=t.get("name"), args=t.get("args", {}))
                            for t in (inv.actual_tool or [])
                        ]
                        # Pack a full actual Invocation for ADK metrics
                        actual_invocations_all_runs.append(
                            Invocation(
                                invocation_id=inv.invocation_id,
                                user_content=user_content,
                                final_response=actual_final,
                                intermediate_data=IntermediateData(
                                    tool_uses=actual_tool_calls
                                ),
                            )
                        )

                # Repeat expected invocations to align with num_runs
                expected_invocations_repeated = expected_invocations * num_runs

                # Evaluate per metric via ADK metric evaluators obtained from the registry
                for metric_name, threshold in criteria.items():
                    eval_metric = EvalMetric(
                        metric_name=metric_name, threshold=threshold
                    )
                    metric_evaluator = DEFAULT_METRIC_EVALUATOR_REGISTRY.get_evaluator(
                        eval_metric=eval_metric
                    )

                    if inspect.iscoroutinefunction(
                        metric_evaluator.evaluate_invocations
                    ):
                        evaluation_result = await metric_evaluator.evaluate_invocations(
                            actual_invocations=actual_invocations_all_runs,
                            expected_invocations=expected_invocations_repeated,
                        )
                    else:
                        evaluation_result = metric_evaluator.evaluate_invocations(
                            actual_invocations=actual_invocations_all_runs,
                            expected_invocations=expected_invocations_repeated,
                        )

                    if print_detailed_results:
                        per_items = []
                        for i, per in enumerate(
                            getattr(evaluation_result, "per_invocation_results", [])
                            or []
                        ):
                            per_items.append(
                                SimpleNamespace(
                                    actual_invocation=actual_invocations_all_runs[i],
                                    expected_invocation=expected_invocations_repeated[
                                        i
                                    ],
                                    eval_metric_result=SimpleNamespace(
                                        eval_status=per.eval_status,
                                        score=per.score,
                                        threshold=threshold,
                                    ),
                                )
                            )

                        AgentEvaluator._print_details(
                            eval_metric_result_with_invocations=per_items,
                            overall_eval_status=evaluation_result.overall_eval_status,
                            overall_score=evaluation_result.overall_score,
                            metric_name=metric_name,
                            threshold=threshold,
                        )

                    if evaluation_result.overall_eval_status != EvalStatus.PASSED:
                        failures.append(
                            f"{metric_name} for {self.agent.name} Failed. Expected {threshold},"
                            f" but got {evaluation_result.overall_score}."
                        )

                    evaluation_result_list.append(evaluation_result)

            result.append(evaluation_result_list)

        return result, failures
