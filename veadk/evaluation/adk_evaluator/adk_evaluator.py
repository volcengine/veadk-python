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
from typing import Any, Optional

from google.adk import Runner
from google.adk.agents.base_agent import BaseAgent
from google.adk.artifacts import BaseArtifactService, InMemoryArtifactService
from google.adk.evaluation.agent_evaluator import (
    NUM_RUNS,
    RESPONSE_MATCH_SCORE_KEY,
    TOOL_TRAJECTORY_SCORE_KEY,
    AgentEvaluator,
)
from google.adk.evaluation.eval_case import IntermediateData, Invocation, SessionInput
from google.adk.evaluation.eval_set import EvalSet
from google.adk.evaluation.evaluation_generator import (
    EvalCaseResponses,
    EvaluationGenerator,
)
from google.adk.evaluation.evaluator import EvalStatus, EvaluationResult
from google.adk.sessions import BaseSessionService, InMemorySessionService
from typing_extensions import override

from veadk.agent import Agent

from ..base_evaluator import BaseEvaluator


def formatted_timestamp():
    # YYYYMMDDHHMMSS
    return time.strftime("%Y%m%d%H%M%S", time.localtime())


class VeEvaluationGenerator(EvaluationGenerator):
    @staticmethod
    async def _ve_process_query(  # done
        invocations: list[Invocation],
        agent: Agent,
        agent_name: Optional[str] = None,
        initial_session: Optional[SessionInput] = None,
    ):
        agent_to_evaluate = agent
        if agent_name:
            agent_to_evaluate = agent.find_agent(agent_name)
            assert agent_to_evaluate, f"Sub-Agent `{agent_name}` not found."

        return await VeEvaluationGenerator._ve_generate_inferences_from_root_agent(
            invocations, agent_to_evaluate, None, initial_session
        )

    @staticmethod
    async def ve_generate_responses(  # done
        eval_set: EvalSet,
        agent: Agent,
        repeat_num: int = 3,
        agent_name: str | None = None,
    ):
        results = []

        for eval_case in eval_set.eval_cases:
            responses = []
            for _ in range(repeat_num):
                response_invocations = await VeEvaluationGenerator._ve_process_query(
                    invocations=eval_case.conversation,
                    agent=agent,
                    agent_name=agent_name,
                    initial_session=eval_case.session_input,
                )
                responses.append(response_invocations)

            results.append(EvalCaseResponses(eval_case=eval_case, responses=responses))

        return results

    @staticmethod
    async def _ve_generate_inferences_from_root_agent(
        invocations: list[Invocation],
        root_agent: BaseAgent,
        reset_func: Any,
        initial_session: Optional[SessionInput] = None,
        session_id: Optional[str] = None,
        session_service: Optional[BaseSessionService] = None,
        artifact_service: Optional[BaseArtifactService] = None,
    ) -> list[Invocation]:
        """Scrapes the root agent given the list of Invocations."""
        if not session_service:
            session_service = InMemorySessionService()

        app_name = (
            initial_session.app_name if initial_session else "EvaluationGenerator"
        )
        user_id = initial_session.user_id if initial_session else "test_user_id"
        session_id = session_id if session_id else str(uuid.uuid4())

        _ = await session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            state=initial_session.state if initial_session else {},
            session_id=session_id,
        )

        if not artifact_service:
            artifact_service = InMemoryArtifactService()

        runner = Runner(
            app_name=app_name,
            agent=root_agent,
            artifact_service=artifact_service,
            session_service=session_service,
            memory_service=root_agent.long_term_memory
            if isinstance(root_agent, Agent)
            else None,
        )

        # Reset agent state for each query
        if callable(reset_func):
            reset_func()

        response_invocations = []

        for invocation in invocations:
            final_response = None
            user_content = invocation.user_content
            tool_uses = []
            invocation_id = ""

            async for event in runner.run_async(
                user_id=user_id, session_id=session_id, new_message=user_content
            ):
                invocation_id = (
                    event.invocation_id if not invocation_id else invocation_id
                )

                if event.is_final_response() and event.content and event.content.parts:
                    final_response = event.content
                elif event.get_function_calls():
                    for call in event.get_function_calls():
                        tool_uses.append(call)

            response_invocations.append(
                Invocation(
                    invocation_id=invocation_id,
                    user_content=user_content,
                    final_response=final_response,
                    intermediate_data=IntermediateData(tool_uses=tool_uses),
                )
            )

        return response_invocations


class VeAgentEvaluator(AgentEvaluator):
    def __init__(
        self,
    ):
        super().__init__()

    @staticmethod
    async def ve_evaluate_eval_set(
        agent: Agent,
        eval_set: EvalSet,
        criteria: dict[str, float],
        num_runs=NUM_RUNS,
        agent_name=None,
        print_detailed_results: bool = True,
    ):
        eval_case_responses_list = await VeEvaluationGenerator.ve_generate_responses(
            eval_set=eval_set,
            agent=agent,
            repeat_num=num_runs,
            agent_name=agent_name,
        )
        failures = []
        evaluation_result_list = []

        for eval_case_responses in eval_case_responses_list:
            actual_invocations = [
                invocation
                for invocations in eval_case_responses.responses
                for invocation in invocations
            ]
            expected_invocations = eval_case_responses.eval_case.conversation * num_runs

            for metric_name, threshold in criteria.items():
                metric_evaluator = AgentEvaluator._get_metric_evaluator(
                    metric_name=metric_name, threshold=threshold
                )

                evaluation_result: EvaluationResult = (
                    metric_evaluator.evaluate_invocations(
                        actual_invocations=actual_invocations,
                        expected_invocations=expected_invocations,
                    )
                )

                if print_detailed_results:
                    AgentEvaluator._print_details(
                        evaluation_result=evaluation_result,
                        metric_name=metric_name,
                        threshold=threshold,
                    )

                # Gather all the failures.
                if evaluation_result.overall_eval_status != EvalStatus.PASSED:
                    failures.append(
                        f"{metric_name} for {agent.name} Failed. Expected {threshold},"
                        f" but got {evaluation_result.overall_score}."
                    )
                evaluation_result_list.append(evaluation_result)

        return evaluation_result_list, failures


class ADKEvaluator(BaseEvaluator):
    def __init__(
        self,
        agent,
        name: str = "veadk_adk_evaluator",
    ):
        super().__init__(agent=agent, name=name)

    # TODO: implement

    @override
    async def eval(
        self,
        eval_set_file_path: str,
        eval_id: str = f"test_{formatted_timestamp()}",
        tool_score_threshold: float = 1.0,
        response_match_score_threshold: float = 0.8,
        num_runs: int = 2,
        print_detailed_results: bool = True,
    ):
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

        initial_session = AgentEvaluator._get_initial_session()

        result = []
        failures = []
        for test_file in test_files:
            criteria = {
                TOOL_TRAJECTORY_SCORE_KEY: tool_score_threshold,  # 1-point scale; 1.0 is perfect.
                RESPONSE_MATCH_SCORE_KEY: response_match_score_threshold,  # Rouge-1 text match; 0.8 is default.
            }
            eval_set = AgentEvaluator._load_eval_set_from_file(
                test_file, criteria, initial_session
            )

            res, fail = await VeAgentEvaluator.ve_evaluate_eval_set(
                agent=self.agent,
                eval_set=eval_set,
                criteria=criteria,
                num_runs=num_runs,
                agent_name=self.agent.name,
                print_detailed_results=print_detailed_results,
            )
            result.append(res)
            failures.extend(fail)

        return result, failures
