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
from deepeval.evaluate.types import EvaluationResult
from deepeval.key_handler import KEY_FILE_HANDLER, ModelKeyValues
from deepeval.metrics import BaseMetric
from deepeval.models import LocalModel
from deepeval.test_case import LLMTestCase
from deepeval.test_case.llm_test_case import ToolCall
from pydantic import Field
from typing_extensions import override

from veadk.config import getenv
from veadk.evaluation.types import EvalResultCaseData, EvalResultMetadata
from veadk.utils.logger import get_logger

from ..base_evaluator import BaseEvaluator, EvalResultData, MetricResult
from ..utils.prometheus import PrometheusPushgatewayConfig, push_to_prometheus

logger = get_logger(__name__)


def formatted_timestamp():
    # YYYYMMDDHHMMSS
    return time.strftime("%Y%m%d%H%M%S", time.localtime())


class DeepevalEvaluator(BaseEvaluator):
    def __init__(
        self,
        agent,
        judge_model_api_key: str = Field(
            ...,
            default_factory=lambda: getenv("MODEL_JUDGE_API_KEY"),
        ),
        judge_model_name: str = Field(
            ...,
            default_factory=lambda: getenv(
                "MODEL_JUDGE_NAME",
                "doubao-seed-1-6-250615",
            ),
        ),
        judge_model_api_base: str = Field(
            ...,
            default_factory=lambda: getenv(
                "MODEL_JUDGE_API_BASE",
                "https://ark.cn-beijing.volces.com/api/v3/",
            ),
        ),
        name: str = "veadk_deepeval_evaluator",
        prometheus_config: PrometheusPushgatewayConfig = None,
    ):
        super().__init__(agent=agent, name=name)

        self.judge_model_name = judge_model_name
        self.judge_model = self.create_judge_model(
            model_name=judge_model_name,
            api_key=judge_model_api_key,
            api_base=judge_model_api_base,
        )

        self.prometheus_config = prometheus_config

    def create_judge_model(
        self,
        model_name: str,
        api_key: str,
        api_base: str,
    ):
        KEY_FILE_HANDLER.write_key(ModelKeyValues.LOCAL_MODEL_NAME, model_name)
        KEY_FILE_HANDLER.write_key(ModelKeyValues.LOCAL_MODEL_BASE_URL, api_base)
        KEY_FILE_HANDLER.write_key(ModelKeyValues.LOCAL_MODEL_API_KEY, api_key)
        KEY_FILE_HANDLER.write_key(ModelKeyValues.USE_LOCAL_MODEL, "YES")
        KEY_FILE_HANDLER.write_key(ModelKeyValues.USE_AZURE_OPENAI, "NO")
        return LocalModel()

    @override
    async def eval(
        self,
        eval_set_file_path: str,
        metrics: list[BaseMetric],
        eval_id: str = f"test_{formatted_timestamp()}",
    ):
        """Target to Google ADK, we will use the same evaluation case format as Google ADK."""

        # Get evaluation data by parsing eval set file
        self.generate_eval_data(eval_set_file_path)
        # Get actual data by running agent
        logger.info("Start to run agent for actual data.")
        await self._run_agent_for_actual_data()
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
        test_results = evaluate(test_cases=test_cases, metrics=metrics)
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
