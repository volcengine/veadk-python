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

from deepeval import evaluate
from deepeval.evaluate import CacheConfig
from deepeval.evaluate.types import EvaluationResult
from deepeval.metrics import BaseMetric
from deepeval.models import LocalModel
from deepeval.test_case import LLMTestCase
from deepeval.test_case.llm_test_case import ToolCall
from typing_extensions import override
from typing import Optional
from google.adk.evaluation.eval_set import EvalSet
from veadk.config import getenv
from veadk.evaluation.base_evaluator import BaseEvaluator, EvalResultData, MetricResult
from veadk.evaluation.types import EvalResultCaseData, EvalResultMetadata
from veadk.evaluation.utils.prometheus import (
    PrometheusPushgatewayConfig,
    push_to_prometheus,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def formatted_timestamp():
    """Generates a formatted timestamp string in YYYYMMDDHHMMSS format.

    This function creates a string representation of the current time.
    It uses local time for formatting.

    Returns:
        str: Timestamp string like '20251028123045'.
    """
    # YYYYMMDDHHMMSS
    return time.strftime("%Y%m%d%H%M%S", time.localtime())


class DeepevalEvaluator(BaseEvaluator):
    """Evaluates agents using DeepEval metrics with Prometheus export.

    This class uses DeepEval to test agent performance.
    It runs agents on test cases and scores them.
    Results can be sent to Prometheus for monitoring.

    Attributes:
        judge_model_name (str): Name of the model that judges the agent.
        judge_model (LocalModel): The judge model instance.
        prometheus_config (PrometheusPushgatewayConfig | None): Settings for
            Prometheus export. If None, no export happens.

    Note:
        Needs judge model credentials from environment if not given.
        Turns off cache to get fresh results each time.

    Examples:
        ```python
        agent = Agent(tools=[get_city_weather])
        evaluator = DeepevalEvaluator(agent=agent)
        metrics = [GEval(threshold=0.8)]
        results = await evaluator.evaluate(metrics, eval_set_file_path="test.json")
        ```
    """

    def __init__(
        self,
        agent,
        judge_model_api_key: str = "",
        judge_model_name: str = "",
        judge_model_api_base: str = "",
        name: str = "veadk_deepeval_evaluator",
        prometheus_config: PrometheusPushgatewayConfig | None = None,
    ):
        """Sets up the DeepEval evaluator with agent and judge model.

        Args:
            agent: The agent to test.
            judge_model_api_key: API key for the judge model. If empty,
                gets from MODEL_JUDGE_API_KEY environment variable.
            judge_model_name: Name of the judge model. If empty,
                gets from MODEL_JUDGE_NAME environment variable.
            judge_model_api_base: Base URL for judge model API. If empty,
                gets from MODEL_JUDGE_API_BASE environment variable.
            name: Name for this evaluator. Defaults to 'veadk_deepeval_evaluator'.
            prometheus_config: Settings for Prometheus export. If None,
                no export happens.

        Raises:
            ValueError: If model settings are wrong.
            EnvironmentError: If environment variables are missing.

        Examples:
            ```python
            evaluator = DeepevalEvaluator(
                agent=my_agent,
                judge_model_api_key="sk-...",
                prometheus_config=prometheus_config)
            ```
        """
        super().__init__(agent=agent, name=name)

        if not judge_model_api_key:
            judge_model_api_key = getenv("MODEL_JUDGE_API_KEY")
        if not judge_model_name:
            judge_model_name = getenv(
                "MODEL_JUDGE_NAME",
                "doubao-seed-1-6-250615",
            )
        if not judge_model_api_base:
            judge_model_api_base = getenv(
                "MODEL_JUDGE_API_BASE",
                "https://ark.cn-beijing.volces.com/api/v3/",
            )

        self.judge_model_name = judge_model_name
        self.judge_model = LocalModel(
            model=judge_model_name,
            base_url=judge_model_api_base,
            api_key=judge_model_api_key,
        )

        self.prometheus_config = prometheus_config

    @override
    async def evaluate(
        self,
        metrics: list[BaseMetric],
        eval_set: Optional[EvalSet] = None,
        eval_set_file_path: Optional[str] = None,
        eval_id: str = f"test_{formatted_timestamp()}",
    ):
        """Tests agent using DeepEval on given test cases.

        This method does these steps:
        1. Loads test cases from memory or file
        2. Runs agent to get actual responses
        3. Converts to DeepEval test format
        4. Runs metrics evaluation
        5. Sends results to Prometheus if needed

        Args:
            metrics: List of DeepEval metrics to use for scoring.
            eval_set: Test cases in memory. If given, used first.
            eval_set_file_path: Path to test case file. Used if no eval_set.
            eval_id: Unique name for this test run. Used for tracking.

        Returns:
            EvaluationResult: Results from DeepEval with scores and details.

        Raises:
            ValueError: If no test cases found.
            FileNotFoundError: If test file not found.
            EvaluationError: If agent fails or metrics fail.

        Examples:
            ```python
            metrics = [GEval(threshold=0.8), ToolCorrectnessMetric(threshold=0.5)]
            results = await evaluator.evaluate(
                metrics=metrics,
                eval_set_file_path="test_cases.json")
            print(f"Test cases run: {len(results.test_results)}")
            ```
        """
        # Get evaluation data by parsing eval set file
        self.build_eval_set(eval_set, eval_set_file_path)

        # Get actual data by running agent
        logger.info("Start to run agent for actual data.")
        await self.generate_actual_outputs()
        eval_case_data_list = self.invocation_list

        # Build test cases in Deepeval format
        logger.info("Start to build test cases in Deepeval format.")
        test_cases = []
        for eval_case_data in eval_case_data_list:
            for invocation in eval_case_data.invocations:
                invocations_context_actual: str = (
                    ""  # {"role": "user", "content": "xxxxx"}
                )
                invocations_context_expect: str = ""

                test_case = LLMTestCase(
                    input=invocation.input,
                    actual_output=invocation.actual_output,
                    expected_output=invocation.expected_output,
                    tools_called=[
                        ToolCall(name=tool["name"], input_parameters=tool["args"])
                        for tool in invocation.actual_tool
                    ],
                    expected_tools=[
                        ToolCall(name=tool["name"], input_parameters=tool["args"])
                        for tool in invocation.expected_tool
                    ],
                    additional_metadata={"latency": invocation.latency},
                    context=[
                        "actual_conversation_history: "
                        + (invocations_context_actual or "Empty"),
                        "expect_conversation_history: "
                        + (invocations_context_expect or "Empty"),
                    ],
                )
                invocations_context_actual += (
                    f'{{"role": "user", "content": "{invocation.input}"}}\n'
                )
                invocations_context_actual += f'{{"role": "assistant", "content": "{invocation.actual_output}"}}\n'
                invocations_context_expect += (
                    f'{{"role": "user", "content": "{invocation.input}"}}\n'
                )
                invocations_context_expect += f'{{"role": "assistant", "content": "{invocation.expected_output}"}}\n'

                test_cases.append(test_case)

        # Run Deepeval evaluation according to metrics
        logger.info("Start to run Deepeval evaluation according to metrics.")
        test_results = evaluate(
            test_cases=test_cases,
            metrics=metrics,
            cache_config=CacheConfig(write_cache=False),
        )
        for test_result in test_results.test_results:
            eval_result_data = EvalResultData(metric_results=[])
            for metrics_data_item in test_result.metrics_data:
                metric_result = MetricResult(
                    metric_type=metrics_data_item.name,
                    success=metrics_data_item.success,
                    score=metrics_data_item.score,
                    reason=metrics_data_item.reason,
                )
                eval_result_data.metric_results.append(metric_result)

            eval_result_data.call_before_append()  # calculate average score and generate total reason
            self.result_list.append(eval_result_data)
            self.result_list.reverse()  # deepeval test_results is in reverse order

        # export to Prometheus if needed
        if self.prometheus_config is not None:
            self.export_results(eval_id, test_results)

        return test_results

    def export_results(self, eval_id: str, test_results: EvaluationResult):
        """Sends evaluation results to Prometheus for monitoring.

        This method takes test results, counts passes and failures,
        and sends metrics to Prometheus.

        Args:
            eval_id: Unique name for this test. Used as label in Prometheus.
            test_results: Results from DeepEval evaluation.

        Returns:
            None: Results are sent directly to Prometheus.

        Raises:
            PrometheusConnectionError: If cannot connect to Prometheus.
            PrometheusPushError: If sending data fails.

        Note:
            Uses fixed thresholds for now: case_threshold=0.5, diff_threshold=0.2.
            These may change later.

        Examples:
            ```python
            evaluator.export_results("test_20240101", test_results)
            ```
        """
        # fixed attributions
        test_name = eval_id
        test_cases_total = len(test_results.test_results)
        eval_data = EvalResultMetadata(
            tested_model=self.agent.model_name,
            judge_model=self.judge_model_name,
        )
        # parsed attributions
        test_cases_failure = 0
        test_cases_pass = 0
        test_data_list = []
        # NOTE: we hard-coding the following two attributions for development
        case_threshold = 0.5
        diff_threshold = 0.2

        for idx, test_result in enumerate(test_results.test_results):
            pass_flag = "PASSED"
            if test_result.success:
                test_cases_pass += 1
            else:
                pass_flag = "FAILURE"
                test_cases_failure += 1

            test_data_list.append(
                EvalResultCaseData(
                    id=str(idx),
                    input=test_result.input,
                    actual_output=test_result.actual_output,
                    expected_output=test_result.expected_output,
                    # [temporary] score: This method is not generally applicable now and is currently only available in the GEval mode.
                    score=str(test_result.metrics_data[0].score),
                    reason=test_result.metrics_data[0].reason,
                    status=pass_flag,
                    latency=test_result.additional_metadata["latency"],
                )
            )

        exported_data = {
            "test_name": test_name,
            "test_cases_total": test_cases_total,
            "test_cases_failure": test_cases_failure,
            "test_cases_pass": test_cases_pass,
            "test_data_list": test_data_list,
            "eval_data": eval_data,
            "case_threshold": case_threshold,
            "diff_threshold": diff_threshold,
        }

        push_to_prometheus(
            **exported_data,
            url=self.prometheus_config.url,
            username=self.prometheus_config.username,
            password=self.prometheus_config.password,
        )
        logger.info(
            f"Upload to Prometheus Pushgateway ({self.prometheus_config.url}) successfully! Test name: {eval_id}"
        )
