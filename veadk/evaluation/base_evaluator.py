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
from typing import Any, Optional

from google.adk import Runner
from google.adk.evaluation.eval_set import EvalSet
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from veadk.utils.misc import formatted_timestamp


class ToolInvocation(BaseModel):
    """Represents a single tool invocation in agent execution.

    This model holds tool name, arguments, and result.
    Used in tracking tool usage during evaluation.

    Attributes:
        tool_name (str): Name of the tool called.
        tool_args (dict[str, Any]): Arguments passed to the tool. Defaults to empty dict.
        tool_result (Any): Result from tool execution. Defaults to None.

    Note:
        Flexible for various tool types and results.
    """

    tool_name: str
    tool_args: dict[str, Any] = {}
    tool_result: Any = None


class Invocation(BaseModel):
    """Models a single invocation in the evaluation process.

    This class stores input, expected and actual outputs, tools, and latency.
    Essential for comparing agent behavior.

    Attributes:
        invocation_id (str): Unique ID for the invocation. Defaults to empty.
        input (str): User input prompt.
        actual_output (str): Actual response from agent.
        expected_output (str): Expected response.
        actual_tool (list[dict]): List of actual tools called with details.
        expected_tool (list[dict]): List of expected tools.
        latency (str): Execution time in ms. Defaults to empty.

    Note:
        Tools are dicts with 'name' and 'args'.
    """

    invocation_id: str = ""
    input: str
    actual_output: str
    expected_output: str
    actual_tool: list[dict] = []
    expected_tool: list[dict] = []
    latency: str = ""  # ms


class EvalTestCase(BaseModel):
    """Groups invocations for a single test case.

    This model contains a list of invocations for one evaluation scenario.
    Used to structure test data.

    Attributes:
        invocations (list[Invocation]): List of invocation objects in the case.

    Note:
        Each case corresponds to one session or conversation.
    """

    invocations: list[Invocation]


class MetricResult(BaseModel):
    """Stores result of a single metric evaluation.

    This model holds the outcome of one metric application.
    Includes success, score, and reason.

    Attributes:
        metric_type (str): Type or name of the metric.
        success (bool): If the metric passed.
        score (float): Numerical score from evaluation.
        reason (str): Explanation for the score.

    Note:
        Score is float between 0 and 1 typically.
    """

    metric_type: str
    success: bool
    score: float
    reason: str


class EvalResultData(BaseModel):
    """Aggregates metric results for an evaluation.

    This class collects multiple metric results and computes averages.
    Used for overall case scoring.

    Attributes:
        metric_results (list[MetricResult]): List of individual metric outcomes.
        average_score (float): Computed average score. Defaults to 0.0.
        total_reason (str): Combined reasons. Defaults to empty.

    Note:
        Call call_before_append to compute averages and reasons.
    """

    metric_results: list[MetricResult]
    average_score: float = 0.0
    total_reason: str = ""

    def calculate_average_score(self):
        """Calculates the average score from metric results.

        This method sums scores and divides by count.
        Updates average_score attribute.

        Returns:
            None: Updates internal state.

        Raises:
            ZeroDivisionError: If no metrics.
        """
        total_score = sum(result.score for result in self.metric_results)
        self.average_score = (
            total_score / len(self.metric_results) if self.metric_results else 0.0
        )

    def generate_total_reason(self):
        """Generates a combined reason string from all metrics.

        This method joins reasons with metric types.
        Updates total_reason attribute.

        Returns:
            None: Updates internal state.

        Note:
            Format: 'metric_type: reason'
        """
        self.total_reason = "\n".join(
            f"{result.metric_type:}:{result.reason}" for result in self.metric_results
        )

    def call_before_append(self):
        """Computes average score and total reason before adding to list.

        This method calls calculate_average_score and generate_total_reason.
        Ensures data is ready for storage.

        Returns:
            None: Updates internal state.
        """
        self.calculate_average_score()
        self.generate_total_reason()


class BaseEvaluator:
    """Base class for all evaluators in the system.

    This abstract class provides common functionality for evaluation.
    Handles building eval sets, generating outputs, and abstract evaluate.

    Attributes:
        name (str): Name of the evaluator.
        agent: The agent being evaluated.
        invocation_list (list[EvalTestCase]): List of test cases.
        result_list (list[EvalResultData]): List of evaluation results.
        agent_information_list (list[dict]): List of agent config info.

    Note:
        Subclasses must implement evaluate method.
        Supports JSON and tracing formats for input.
    """

    def __init__(
        self,
        agent,
        name: str,
    ):
        """Initializes the base evaluator with agent and name.

        Args:
            agent: Agent instance to evaluate.
            name (str): Identifier for the evaluator.

        Raises:
            ValueError: If agent or name invalid.
        """
        self.name = name
        self.agent = agent
        self.invocation_list: list[EvalTestCase] = []
        self.result_list: list[EvalResultData] = []
        self.agent_information_list: list[dict] = []

    def _build_eval_set_from_eval_json(self, eval_json_path: str) -> EvalSet:
        """Builds eval set from standard eval JSON file.

        This private method loads using file loader.

        Args:
            eval_json_path (str): Path to JSON file.

        Returns:
            EvalSet: Loaded set.

        Raises:
            ValueError: If loading fails.
        """
        from veadk.evaluation.eval_set_file_loader import load_eval_set_from_file

        return load_eval_set_from_file(eval_json_path)

    def _build_eval_set_from_tracing_json(self, tracing_json_path: str) -> EvalSet:
        """Builds eval set from tracing JSON spans.

        This private method parses spans, groups by trace, extracts tools and conversation.

        Args:
            tracing_json_path (str): Path to tracing JSON.

        Returns:
            EvalSet: Constructed set from traces.

        Raises:
            ValueError: If JSON invalid or parsing fails.
            json.JSONDecodeError: For malformed JSON.

        Note:
            Assumes spans have gen_ai attributes for tools and content.
        """
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
                    # Extract tool parameters from gen_ai.tool.input
                    tool_input_str = span["attributes"].get("gen_ai.tool.input", "{}")
                    try:
                        tool_input = json.loads(tool_input_str)
                        tool_args = tool_input.get("parameters", {})
                    except json.JSONDecodeError:
                        tool_args = {}

                    # Extract the tool call ID from gen_ai.tool.output
                    tool_output_str = span["attributes"].get("gen_ai.tool.output", "{}")
                    tool_call_id = None
                    try:
                        tool_output = json.loads(tool_output_str)
                        tool_call_id = tool_output.get("id", None)
                    except json.JSONDecodeError:
                        tool_call_id = None

                    tool_uses.append(
                        {
                            "id": tool_call_id,
                            "args": tool_args,
                            "name": span["attributes"].get("gen_ai.tool.name", None),
                        }
                    )

            # Extract conversation data from call_llm spans
            user_input = ""
            final_output = ""

            # Find the first call_llm span for user input and the last one for final output
            call_llm_spans = [span for span in spans if span["name"] == "call_llm"]

            if call_llm_spans:
                # Get user input from the first call_llm span
                first_span = call_llm_spans[0]
                user_input = first_span["attributes"].get("gen_ai.prompt.0.content", "")

                # Get final output from the last call_llm span
                last_span = call_llm_spans[-1]
                final_output = last_span["attributes"].get(
                    "gen_ai.completion.0.content", ""
                )

                # Get metadata from any span
                app_name = first_span["attributes"].get("gen_ai.app.name", "")
                user_id = first_span["attributes"].get("gen_ai.user.id", "")
                creation_timestamp = first_span["start_time"] / 1e9

            if user_input and final_output:
                # Create user_content and final_response in the expected format
                user_content = {"role": "user", "parts": [{"text": user_input}]}

                final_response = {"role": "model", "parts": [{"text": final_output}]}

                conversation.append(
                    {
                        "invocation_id": str(uuid.uuid4()),
                        "user_content": user_content,
                        "final_response": final_response,
                        "intermediate_data": {
                            "tool_uses": tool_uses,
                            "intermediate_responses": [],
                        },
                        "creation_timestamp": creation_timestamp,
                    }
                )

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

    def build_eval_set(
        self, eval_set: Optional[EvalSet] = None, file_path: Optional[str] = None
    ):
        """Builds invocation list from eval set or file.

        This method parses input, extracts invocations with expected data.
        Supports eval JSON and tracing JSON formats.

        Args:
            eval_set (Optional[EvalSet]): Direct eval set object.
            file_path (Optional[str]): Path to file for loading.

        Raises:
            ValueError: If neither provided or format unsupported.

        Note:
        Generates random session IDs for isolation.
        """

        if eval_set is None and file_path is None:
            raise ValueError("eval_set or file_path is required")
        if eval_set:
            eval_cases = eval_set.eval_cases
        else:
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
                    isinstance(span, dict) and "trace_id" in span
                    for span in file_content
                )
            ):
                eval_cases = self._build_eval_set_from_tracing_json(
                    file_path
                ).eval_cases
            else:
                raise ValueError(
                    f"Unsupported file format in {file_path}. Please provide a valid file."
                )

        eval_case_data_list: list[EvalTestCase] = []
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
        """Generates actual outputs by running the agent on inputs.

        This method uses Runner to execute agent for each invocation.
        Captures outputs, tools, and latency.

        Returns:
            None: Updates invocation actual fields.

        Raises:
            Exception: If runner or execution fails.

        Note:
        Uses InMemorySessionService for isolation.
        Supports long-term memory if present.
        """
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
        """Retrieves combined evaluation information.

        This method merges invocations and results into dict lists.
        Useful for reporting.

        Returns:
            list[list[dict[str, Any]]]: Nested list of case data dicts.

        Note:
        Defaults to empty results if not evaluated yet.
        """
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
        metrics: list[Any],
        eval_set: Optional[EvalSet],
        eval_set_file_path: Optional[str],
        eval_id: str,
    ):
        """Abstract method for performing the evaluation.

        Subclasses implement specific metric evaluation logic.

        Args:
            metrics (list[Any]): Metrics to apply.
            eval_set (Optional[EvalSet]): Eval set.
            eval_set_file_path (Optional[str]): File path.
            eval_id (str): Evaluation ID.

        Returns:
            Any: Evaluation results specific to subclass.

        Raises:
            NotImplementedError: If not overridden.

        Note:
        Must populate result_list after evaluation.
        """
        pass
