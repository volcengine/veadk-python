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


from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
from prometheus_client.exposition import basic_auth_handler
from pydantic import Field

from veadk.config import getenv
from veadk.evaluation.types import EvalResultCaseData, EvalResultMetadata


class PrometheusPushgatewayConfig:
    """Configures connection to Prometheus Pushgateway for metrics export.

    This class holds settings for pushing evaluation metrics to Prometheus.
    It uses environment variables for default values.

    Attributes:
        url (str): URL of the Prometheus Pushgateway endpoint.
            Defaults to OBSERVABILITY_PROMETHEUS_PUSHGATEWAY_URL environment variable.
        username (str): Username for authentication.
            Defaults to OBSERVABILITY_PROMETHEUS_USERNAME environment variable.
        password (str): Password for authentication.
            Defaults to OBSERVABILITY_PROMETHEUS_PASSWORD environment variable.

    Note:
        All fields are optional and use environment variables if not provided.
    """

    url: str = Field(
        default_factory=lambda: getenv(
            "OBSERVABILITY_PROMETHEUS_PUSHGATEWAY_URL",
        ),
    )
    username: str = Field(
        default_factory=lambda: getenv(
            "OBSERVABILITY_PROMETHEUS_USERNAME",
        ),
    )
    password: str = Field(
        default_factory=lambda: getenv(
            "OBSERVABILITY_PROMETHEUS_PASSWORD",
        ),
    )


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
    grouping_key: dict[str, str] | None = None,
):
    """Pushes metrics to Prometheus Pushgateway with authentication.

    This function sends collected metrics to the specified Pushgateway URL.
    It uses basic authentication and optional grouping keys.

    Args:
        pushgateway_url (str): URL of the Pushgateway endpoint.
        username (str): Authentication username.
        password (str): Authentication password.
        job_name (str): Name of the job for metrics labeling.
        registry (CollectorRegistry): Registry containing metrics to push.
        grouping_key (dict[str, str] | None): Optional key-value pairs for grouping.

    Raises:
        Exception: If push operation fails due to network or auth issues.

    Note:
        Authentication handler is created internally using provided credentials.
    """

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
    """Sets and pushes evaluation metrics to Prometheus.

    This function updates gauge metrics with evaluation results and pushes them.
    It handles counts, thresholds, and specific data labels.

    Args:
        test_name (str): Name of the test for grouping.
        test_cases_total (int): Total number of test cases.
        test_cases_failure (int): Number of failed test cases.
        test_cases_pass (int): Number of passed test cases.
        test_data_list (list[EvalResultCaseData]): List of case data for labeling.
        eval_data (EvalResultMetadata): Metadata for evaluation.
        case_threshold (float): Threshold value for cases. Defaults to 0.5.
        diff_threshold (float): Diff threshold value. Defaults to 0.2.
        url (str): Pushgateway URL. Defaults to empty.
        username (str): Auth username. Defaults to empty.
        password (str): Auth password. Defaults to empty.

    Returns:
        None: Metrics are set and pushed directly.

    Raises:
        ValueError: If required data is invalid.
    """
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
