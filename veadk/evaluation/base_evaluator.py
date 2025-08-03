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


import time
import uuid
from abc import abstractmethod
from typing import Any

from google.adk import Runner
from google.adk.evaluation.eval_set import EvalSet
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel


class InvocationTestData(BaseModel):
    invocation_id: str = ""
    input: str
    actual_output: str
    expected_output: str
    actual_tool: list[dict] = []
    expected_tool: list[dict] = []
    latency: str = ""  # ms


class EvalCaseData(BaseModel):
    invocations: list[InvocationTestData]


class MetricResult(BaseModel):
    metric_type: str
    success: bool
    score: float
    reason: str


class EvalResultData(BaseModel):
    metric_results: list[MetricResult]
    average_score: float = 0.0
    total_reason: str = ""

    def calculate_average_score(self):
        total_score = sum(result.score for result in self.metric_results)
        self.average_score = (
            total_score / len(self.metric_results) if self.metric_results else 0.0
        )

    def generate_total_reason(self):
        self.total_reason = "\n".join(
            f"{result.metric_type:}:{result.reason}" for result in self.metric_results
        )

    def call_before_append(self):
        self.calculate_average_score()
        self.generate_total_reason()


class BaseEvaluator:
    def __init__(
        self,
        agent,
        name: str,
    ):
        self.name = name
        self.agent = agent
        self.invocation_list: list[EvalCaseData] = []
        self.result_list: list[EvalResultData] = []
        self.agent_information_list: list[dict] = []

    def load_eval_set(self, eval_set_file: str) -> list[EvalSet]:
        from .eval_set_file_loader import load_eval_set_from_file

        return load_eval_set_from_file(eval_set_file)

    def generate_eval_data(self, eval_set_file_path: str):
        eval_case_data_list: list[EvalCaseData] = []

        eval_cases = self.load_eval_set(eval_set_file_path).eval_cases
        for eval_case in eval_cases:
            eval_case_data = EvalCaseData(invocations=[])
            self.agent_information_list.append(
                {
                    "app_name": eval_case.session_input.app_name,
                    "user_id": eval_case.session_input.user_id,
                    "session_id": str(
                        uuid.uuid4()
                    ),  # random session id for evaluation,
                }
            )

            for invocation in eval_case.conversation:
                _input: str = ""
                _expected_output: str = ""
                _expected_tool: list[dict] = []

                user_content = invocation.user_content
                _input = user_content.parts[0].text
                _expected_output = invocation.final_response.parts[0].text

                if invocation.intermediate_data.tool_uses:
                    for expected_tool_use in invocation.intermediate_data.tool_uses:
                        _expected_tool.append(
                            {
                                "name": expected_tool_use.name,
                                "args": expected_tool_use.args,
                            }
                        )

                eval_case_data.invocations.append(
                    InvocationTestData(
                        invocation_id=invocation.invocation_id,
                        input=_input,
                        actual_output="",
                        actual_tool=[],
                        expected_output=_expected_output,
                        expected_tool=_expected_tool,
                        latency="",
                    )
                )

            eval_case_data_list.append(eval_case_data)
        self.invocation_list = eval_case_data_list

    async def _run_agent_for_actual_data(self):
        for eval_case_data, agent_information in zip(
            self.invocation_list, self.agent_information_list
        ):
            session_service = InMemorySessionService()
            _ = await session_service.create_session(
                app_name=agent_information["app_name"],
                user_id=agent_information["user_id"],
                state={},
                session_id=agent_information["session_id"],
            )

            if getattr(self.agent, "long_term_memory", None):
                runner = Runner(
                    app_name=agent_information["app_name"],
                    agent=self.agent,
                    session_service=session_service,
                    memory_service=self.agent.long_term_memory,
                )
            else:
                runner = Runner(
                    app_name=agent_information["app_name"],
                    agent=self.agent,
                    session_service=session_service,
                )

            for invocation in eval_case_data.invocations:
                _actual_output: str = ""
                _actual_tool: list[dict] = []
                _latency: str = ""
                final_response = None
                tool_uses = []
                invocation_id = ""

                user_content = types.Content(
                    role="user", parts=[types.Part(text=invocation.input)]
                )
                tik = time.time()
                async for event in runner.run_async(
                    user_id=agent_information["user_id"],
                    session_id=agent_information["session_id"],
                    new_message=user_content,
                ):
                    invocation_id = (
                        event.invocation_id if not invocation_id else invocation_id
                    )
                    if (
                        event.is_final_response()
                        and event.content
                        and event.content.parts
                    ):
                        final_response = event.content
                    elif event.get_function_calls():
                        for call in event.get_function_calls():
                            tool_uses.append(call)
                tok = time.time()
                _latency = str((tok - tik) * 1000)

                if final_response and final_response.parts:
                    _actual_output = final_response.parts[0].text
                for tool_use in tool_uses:
                    _actual_tool.append(
                        {
                            "name": tool_use.name,
                            "args": tool_use.args,
                        }
                    )

                invocation.actual_output = _actual_output
                invocation.actual_tool = _actual_tool
                invocation.latency = _latency

    def get_data(self) -> list[list[dict[str, Any]]]:
        """Merge the evaluation data and return it in the format of list[list[dict]]"""
        result = []
        for i, eval_case in enumerate(self.invocation_list):
            case_data = []
            # Get corresponding eval_result or use default if not available
            eval_result = (
                self.result_list[i]
                if i < len(self.result_list)
                else EvalResultData(metric_results=[])
            )
            for invocation in eval_case.invocations:
                data = {
                    "input": invocation.input,
                    "expected_output": invocation.expected_output,
                    "actual_output": invocation.actual_output,
                    "expected_tool": invocation.expected_tool,
                    "actual_tool": invocation.actual_tool,
                    "score": eval_result.average_score,
                    "reason": eval_result.total_reason,
                    "latency": invocation.latency,
                }
                case_data.append(data)
            result.append(case_data)
        return result

    @abstractmethod
    async def eval(
        self,
        eval_set_file_path: str,
        metrics: list[Any],
        eval_id: str,
    ):
        """An abstract method for evaluation based on metrics。"""
        pass
