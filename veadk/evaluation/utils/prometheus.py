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

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
from prometheus_client.exposition import basic_auth_handler

from veadk.config import getenv


@dataclass
class EvalResultCaseData:
    id: str
    input: str
    actual_output: str
    expected_output: str
    score: str
    reason: str
    status: str  # `PASSED` or `FAILURE`
    latency: str


@dataclass
class EvalResultMetadata:
    tested_model: str
    judge_model: str


class PrometheusPushgatewayConfig:
    url: str = getenv(
        "OBSERVABILITY_PROMETHEUS_PUSHGATEWAY_URL",
    )
    username: str = getenv("OBSERVABILITY_PROMETHEUS_USERNAME")
    password: str = getenv("OBSERVABILITY_PROMETHEUS_PASSWORD")


registry = CollectorRegistry()

test_cases_total_metric = Gauge(
    "test_cases_total",
    "Total number of test cases in this evaluation",
    registry=registry,
)

test_cases_success_metric = Gauge(
    "test_cases_success", "Success number of test cases", registry=registry
)

test_cases_pass_metric = Gauge(
    "test_cases_pass", "Passed number of test cases", registry=registry
)

test_cases_failure_metric = Gauge(
    "test_cases_failure", "Failuer number of test cases", registry=registry
)

case_threshold_metric = Gauge("threshold", "Threshold of test cases", registry=registry)
diff_threshold_metric = Gauge(
    "diff_threshold", "Diff threshold of test cases", registry=registry
)

test_cases_data_metric = Gauge(
    "test_cases_data",
    "Specific data of test cases",
    registry=registry,
    labelnames=["data"],
)

eval_data_metric = Gauge(
    "eval_data",
    "Specific data of evaluation",
    registry=registry,
    labelnames=["data"],
)


def post_pushgateway(
    pushgateway_url: str,
    username: str,
    password: str,
    job_name: str,
    registry: CollectorRegistry,
    grouping_key: dict[str, str] = None,
):
    def auth_handler(url, method, timeout, headers, data):
        return basic_auth_handler(
            url, method, timeout, headers, data, username, password
        )

    push_to_gateway(
        gateway=pushgateway_url,
        job=job_name,
        registry=registry,
        grouping_key=grouping_key,
        handler=auth_handler,
    )


def push_to_prometheus(
    test_name: str,
    test_cases_total: int,
    test_cases_failure: int,
    test_cases_pass: int,
    test_data_list: list[EvalResultCaseData],
    eval_data: EvalResultMetadata,
    case_threshold: float = 0.5,
    diff_threshold: float = 0.2,
    url: str = "",
    username: str = "",
    password: str = "",
):
    test_cases_total_metric.set(test_cases_total)
    test_cases_failure_metric.set(test_cases_failure)
    test_cases_pass_metric.set(test_cases_pass)

    for test_data in test_data_list:
        test_cases_data_metric.labels(data=str(test_data.__dict__)).set(1)

    eval_data_metric.labels(data=str(eval_data.__dict__)).set(1)
    case_threshold_metric.set(case_threshold)
    diff_threshold_metric.set(diff_threshold)

    post_pushgateway(
        pushgateway_url=url,
        username=username,
        password=password,
        job_name="veadk_eval_job",
        registry=registry,
        grouping_key={"test_name": test_name},
    )
