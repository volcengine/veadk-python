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


import json
import time
import uuid
from abc import abstractmethod
from typing import Any

from google.adk import Runner
from google.adk.evaluation.eval_set import EvalSet
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from veadk.utils.misc import formatted_timestamp


class ToolInvocation(BaseModel):
    tool_name: str
    tool_args: dict[str, Any] = {}
    tool_result: Any = None


class Invocation(BaseModel):
    invocation_id: str = ""
    input: str
    actual_output: str
    expected_output: str
    actual_tool: list[dict] = []
    expected_tool: list[dict] = []
    latency: str = ""  # ms


class EvalTestCase(BaseModel):
    invocations: list[Invocation]


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
        self.invocation_list: list[EvalTestCase] = []
        self.result_list: list[EvalResultData] = []
        self.agent_information_list: list[dict] = []

    def _build_eval_set_from_eval_json(self, eval_json_path: str) -> EvalSet:
        from veadk.evaluation.eval_set_file_loader import load_eval_set_from_file

        return load_eval_set_from_file(eval_json_path)

    def _build_eval_set_from_tracing_json(self, tracing_json_path: str) -> EvalSet:
        try:
            with open(tracing_json_path, "r") as f:
                tracing_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in file {tracing_json_path}: {e}")
        except Exception as e:
            raise ValueError(f"Error reading file {tracing_json_path}: {e}")

        # Group spans by trace_id
        trace_groups = {}
        for span in tracing_data:
            trace_id = span["trace_id"]
            if trace_id not in trace_groups:
                trace_groups[trace_id] = []
            trace_groups[trace_id].append(span)

        # Convert to evalset format
        eval_cases, conversation = [], []
        app_name, user_id = "", ""
        creation_timestamp = 0
        for trace_id, spans in trace_groups.items():
            tool_uses = []

            # Extract tool_uses from spans with name starting with "execute_tool"
            for span in spans:
                if span["name"].startswith("execute_tool"):
                    tool_uses.append(
                        {
                            "id": span["attributes"].get("gen_ai.tool.call.id", None),
                            "args": json.loads(
                                span["attributes"].get(
                                    "gcp.vertex.agent.tool_call_args", "{}"
                                )
                            ),
                            "name": span["attributes"].get("gen_ai.tool.name", None),
                        }
                    )

            # Extract conversation data from spans with name starting with "invocation"
            for span in spans:
                if span["name"].startswith("invocation"):
                    # Parse input.value and output.value as JSON
                    input_value = json.loads(
                        span["attributes"].get("input.value", "{}")
                    )
                    output_value = json.loads(
                        span["attributes"].get("output.value", "{}")
                    )

                    user_content = json.loads(input_value.get("new_message", {}))
                    final_response = json.loads(json.dumps(user_content))
                    final_response["parts"][0]["text"] = (
                        output_value.get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", None)
                    )
                    final_response["role"] = None
                    conversation.append(
                        {
                            "invocation_id": output_value.get(
                                "invocation_id", str(uuid.uuid4())
                            ),
                            "user_content": user_content,
                            "final_response": final_response,
                            "intermediate_data": {
                                "tool_uses": tool_uses,
                                "intermediate_responses": [],
                            },
                            "creation_timestamp": span["start_time"] / 1e9,
                        }
                    )
                    user_id = input_value.get("user_id", None)
                    app_name = (
                        span["name"].replace("invocation", "").strip().strip("[]")
                    )
                    creation_timestamp = span["start_time"] / 1e9

        eval_cases.append(
            {
                "eval_id": f"veadk_eval_{formatted_timestamp()}",
                "conversation": conversation,
                "session_input": {
                    "app_name": app_name,
                    "user_id": user_id,
                    "state": {},
                },
                "creation_timestamp": creation_timestamp,
            }
        )

        evalset = EvalSet(
            eval_set_id="default",
            name="default",
            description=None,
            eval_cases=eval_cases,
            creation_timestamp=creation_timestamp,
        )

        return evalset

    def build_eval_set(self, file_path: str):
        """Generate evaluation data from a given file and assign it to the class attribute `invocation_list`."""
        eval_case_data_list: list[EvalTestCase] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                file_content = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in file {file_path}: {e}")
        except Exception as e:
            raise ValueError(f"Error reading file {file_path}: {e}")

        if isinstance(file_content, dict) and "eval_cases" in file_content:
            eval_cases = self._build_eval_set_from_eval_json(file_path).eval_cases
        elif (
            isinstance(file_content, list)
            and len(file_content) > 0
            and all(
                isinstance(span, dict) and "trace_id" in span for span in file_content
            )
        ):
            eval_cases = self._build_eval_set_from_tracing_json(file_path).eval_cases
        else:
            raise ValueError(
                f"Unsupported file format in {file_path}. Please provide a valid file."
            )

        for eval_case in eval_cases:
            eval_case_data = EvalTestCase(invocations=[])
            if eval_case.session_input:
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
                    Invocation(
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

    async def generate_actual_outputs(self):
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

    def get_eval_set_information(self) -> list[list[dict[str, Any]]]:
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
    async def evaluate(
        self,
        eval_set_file_path: str,
        metrics: list[Any],
        eval_id: str,
    ):
        """An abstract method for evaluation based on metrics。"""
        pass
