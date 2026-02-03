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
from dataclasses import dataclass
from typing import Any

from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.run_config import StreamingMode
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import BaseTool
from opentelemetry import metrics, trace
from opentelemetry import metrics as metrics_api
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics._internal import Meter
from opentelemetry.sdk import metrics as metrics_sdk
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel, Field
from typing_extensions import override

from veadk.config import settings
from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


_GEN_AI_CLIENT_OPERATION_DURATION_BUCKETS = [
    0.01,
    0.02,
    0.04,
    0.08,
    0.16,
    0.32,
    0.64,
    1.28,
    2.56,
    5.12,
    10.24,
    20.48,
    40.96,
    81.92,
]

_GEN_AI_SERVER_TIME_PER_OUTPUT_TOKEN_BUCKETS = [
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.15,
    0.2,
    0.3,
    0.4,
    0.5,
    0.75,
    1.0,
    2.5,
]

_GEN_AI_SERVER_TIME_TO_FIRST_TOKEN_BUCKETS = [
    0.001,
    0.005,
    0.01,
    0.02,
    0.04,
    0.06,
    0.08,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
]

_GEN_AI_CLIENT_TOKEN_USAGE_BUCKETS = [
    1,
    4,
    16,
    64,
    256,
    1024,
    4096,
    16384,
    65536,
    262144,
    1048576,
    4194304,
    16777216,
    67108864,
]


@dataclass
class Meters:
    """Metric names and identifiers for OpenTelemetry instrumentation.

    This class defines standardized metric names used for LLM and agent
    observability. The metrics follow OpenTelemetry semantic conventions
    for generative AI operations and include custom APMPlus metrics for
    enhanced monitoring capabilities.

    Standard Gen AI Metrics:
        - LLM_CHAT_COUNT: Counter for LLM invocation frequency
        - LLM_TOKEN_USAGE: Histogram for token consumption analysis
        - LLM_OPERATION_DURATION: Histogram for operation latency tracking
        - LLM_COMPLETIONS_EXCEPTIONS: Counter for error rate monitoring
        - Streaming metrics: Performance analysis for streaming responses

    APMPlus Custom Metrics:
        - APMPLUS_SPAN_LATENCY: Span execution time for performance analysis
        - APMPLUS_TOOL_TOKEN_USAGE: Tool-specific token consumption tracking
    """

    LLM_CHAT_COUNT = "gen_ai.chat.count"
    LLM_TOKEN_USAGE = "gen_ai.client.token.usage"
    LLM_OPERATION_DURATION = "gen_ai.client.operation.duration"
    LLM_COMPLETIONS_EXCEPTIONS = "gen_ai.chat_completions.exceptions"
    LLM_STREAMING_TIME_TO_FIRST_TOKEN = (
        "gen_ai.chat_completions.streaming_time_to_first_token"
    )
    LLM_STREAMING_TIME_TO_GENERATE = (
        "gen_ai.chat_completions.streaming_time_to_generate"
    )
    LLM_STREAMING_TIME_PER_OUTPUT_TOKEN = (
        "gen_ai.chat_completions.streaming_time_per_output_token"
    )

    # apmplus metrics
    # span duration
    APMPLUS_SPAN_LATENCY = "apmplus_span_latency"
    # tool token usage
    APMPLUS_TOOL_TOKEN_USAGE = "apmplus_tool_token_usage"


class MeterUploader:
    """Metrics uploader for APMPlus observability platform integration.

    MeterUploader manages the collection and transmission of telemetry metrics
    to Volcengine's APMPlus platform. It creates and maintains OpenTelemetry
    metric instruments for comprehensive agent performance monitoring.

    Key Features:
    - Automatic metric instrument creation with appropriate buckets
    - LLM call metrics including token usage and latency
    - Tool execution metrics for performance analysis
    - Error tracking and exception monitoring
    - Integration with OpenTelemetry metrics SDK

    Metrics Collected:
    - LLM invocation counts and frequencies
    - Token consumption (input/output) with histogram distribution
    - Operation latency with performance bucket analysis
    - Error rates and exception details
    - Span-level performance metrics for APMPlus dashboards
    """

    def __init__(
        self, name: str, endpoint: str, headers: dict, resource_attributes: dict
    ) -> None:
        """Initialize the meter uploader with APMPlus configuration.

        Sets up the global metrics provider, creates metric instruments,
        and configures OTLP export to APMPlus endpoints with proper
        resource attribution and authentication.

        Args:
            name: Meter name for identification and organization
            endpoint: APMPlus OTLP endpoint URL for metric transmission
            headers: Authentication headers including APMPlus app key
            resource_attributes: Service metadata for metric attribution
        """
        # global_metrics_provider -> global_tracer_provider
        # exporter -> exporter
        # metric_reader -> processor
        global_metrics_provider = metrics_api.get_meter_provider()

        # 1. init resource
        if hasattr(global_metrics_provider, "_sdk_config"):
            global_resource = global_metrics_provider._sdk_config.resource  # type: ignore
        else:
            global_resource = Resource.create()

        resource = global_resource.merge(Resource.create(resource_attributes))

        # 2. init exporter and reader
        exporter = OTLPMetricExporter(endpoint=endpoint, headers=headers)
        metric_reader = PeriodicExportingMetricReader(exporter)

        metrics_api.set_meter_provider(
            metrics_sdk.MeterProvider(metric_readers=[metric_reader], resource=resource)
        )

        # 3. init meter
        self.meter: Meter = metrics.get_meter(name=name)

        # create meter attributes
        self.llm_invoke_counter = self.meter.create_counter(
            name=Meters.LLM_CHAT_COUNT,
            description="Number of LLM invocations",
            unit="count",
        )
        self.token_usage = self.meter.create_histogram(
            name=Meters.LLM_TOKEN_USAGE,
            description="Token consumption of LLM invocations",
            unit="count",
            explicit_bucket_boundaries_advisory=_GEN_AI_CLIENT_TOKEN_USAGE_BUCKETS,
        )
        self.duration_histogram = self.meter.create_histogram(
            name=Meters.LLM_OPERATION_DURATION,
            unit="s",
            description="GenAI operation duration",
            explicit_bucket_boundaries_advisory=_GEN_AI_CLIENT_OPERATION_DURATION_BUCKETS,
        )
        self.chat_exception_counter = self.meter.create_counter(
            name=Meters.LLM_COMPLETIONS_EXCEPTIONS,
            unit="time",
            description="Number of exceptions occurred during chat completions",
        )
        self.streaming_time_to_first_token = self.meter.create_histogram(
            name=Meters.LLM_STREAMING_TIME_TO_FIRST_TOKEN,
            unit="s",
            description="Time to first token in streaming chat completions",
            explicit_bucket_boundaries_advisory=_GEN_AI_SERVER_TIME_TO_FIRST_TOKEN_BUCKETS,
        )
        self.streaming_time_to_generate = self.meter.create_histogram(
            name=Meters.LLM_STREAMING_TIME_TO_GENERATE,
            unit="s",
            description="Time between first token and completion in streaming chat completions",
            explicit_bucket_boundaries_advisory=_GEN_AI_CLIENT_OPERATION_DURATION_BUCKETS,
        )
        self.streaming_time_per_output_token = self.meter.create_histogram(
            name=Meters.LLM_STREAMING_TIME_PER_OUTPUT_TOKEN,
            unit="s",
            description="Time per output token in streaming chat completions",
            explicit_bucket_boundaries_advisory=_GEN_AI_SERVER_TIME_PER_OUTPUT_TOKEN_BUCKETS,
        )

        # apmplus metrics for veadk dashboard
        self.apmplus_span_latency = self.meter.create_histogram(
            name=Meters.APMPLUS_SPAN_LATENCY,
            description="Latency of span",
            unit="s",
            explicit_bucket_boundaries_advisory=_GEN_AI_CLIENT_OPERATION_DURATION_BUCKETS,
        )
        self.apmplus_tool_token_usage = self.meter.create_histogram(
            name=Meters.APMPLUS_TOOL_TOKEN_USAGE,
            description="Token consumption of APMPlus tool token",
            unit="count",
            explicit_bucket_boundaries_advisory=_GEN_AI_CLIENT_TOKEN_USAGE_BUCKETS,
        )

    def record_call_llm(
        self,
        invocation_context: InvocationContext,
        event_id: str,
        llm_request: LlmRequest,
        llm_response: LlmResponse,
    ) -> None:
        """Record comprehensive metrics for LLM call operations.

        Captures detailed telemetry data for language model invocations
        including token consumption, latency, and error information.
        This data enables cost optimization, performance analysis, and
        reliability monitoring in APMPlus dashboards.

        Metrics Recorded:
        - Invocation count with model and operation attributes
        - Input/output token usage with separate tracking
        - Operation duration from span timing data
        - Error counts and exception details
        - Span latency for performance analysis

        Args:
            invocation_context: Context with agent, session, and user information
            event_id: Unique identifier for this LLM call event
            llm_request: Request object with model and parameter details
            llm_response: Response object with content and usage metadata
        """
        is_streaming = bool(
            invocation_context.run_config
            and invocation_context.run_config.streaming_mode != StreamingMode.NONE
        )
        server_address = getattr(invocation_context.agent, "model_api_base", "unknown")
        attributes = {
            "gen_ai_system": "volcengine",
            "gen_ai_response_model": llm_request.model,
            "gen_ai_operation_name": "chat",
            "gen_ai_operation_type": "llm",
            "stream": is_streaming,
            "server_address": server_address,
        }  # required by Volcengine APMPlus

        if llm_response.usage_metadata:
            # llm invocation number += 1
            self.llm_invoke_counter.add(1, attributes)

            # upload token usage
            input_token = llm_response.usage_metadata.prompt_token_count
            output_token = llm_response.usage_metadata.candidates_token_count

            if input_token:
                token_attributes = {**attributes, "gen_ai_token_type": "input"}
                self.token_usage.record(input_token, attributes=token_attributes)
            if output_token:
                token_attributes = {**attributes, "gen_ai_token_type": "output"}
                self.token_usage.record(output_token, attributes=token_attributes)

            # Get llm duration
            span = trace.get_current_span()
            if span and hasattr(span, "start_time") and self.duration_histogram:
                # We use span start time as the llm request start time
                tik = span.start_time  # type: ignore
                # We use current time as the llm request end time
                tok = time.time_ns()
                # Calculate duration in seconds
                duration = (tok - tik) / 1e9
                self.duration_histogram.record(
                    duration, attributes=attributes
                )  # unit in seconds

            # Get model request error
            if llm_response.error_code and self.chat_exception_counter:
                exception_attributes = {
                    **attributes,
                    "error_type": llm_response.error_code,
                }
                self.chat_exception_counter.add(1, exception_attributes)

            # TODO: Get streaming time to first token
            # time_to_frist_token = 0.1
            # if self.streaming_time_to_first_token:
            #     self.streaming_time_to_first_token.record(
            #         time_to_frist_token, attributes=attributes
            #     )

            # TODO: Get streaming time to generate
            # time_to_generate = 1.0
            # if self.streaming_time_to_generate:
            #     self.streaming_time_to_generate.record(
            #         time_to_generate, attributes=attributes
            #     )

            # TODO: Get streaming time per output token
            # time_per_output_token = 0.01
            # if self.streaming_time_per_output_token:
            #     self.streaming_time_per_output_token.record(
            #         time_per_output_token, attributes=attributes
            #     )

            # add span name attribute
            span = trace.get_current_span()
            if not span:
                return

            # record span latency
            if hasattr(span, "start_time") and self.apmplus_span_latency:
                # span 耗时
                duration = (time.time_ns() - span.start_time) / 1e9  # type: ignore
                self.apmplus_span_latency.record(duration, attributes=attributes)

    def record_tool_call(
        self,
        tool: BaseTool,
        args: dict[str, Any],
        function_response_event: Event,
    ):
        """Record metrics for tool execution operations.

        Captures performance and usage metrics for tool invocations
        including execution latency and estimated token consumption.
        Enables monitoring of tool performance and resource usage patterns.

        Metrics Recorded:
        - Tool execution latency from span timing
        - Input/output token estimation based on text length
        - Tool-specific attributes for categorization

        Args:
            tool: Tool instance that was executed
            args: Arguments passed to the tool function
            function_response_event: Event containing execution results
        """
        logger.debug(f"Record tool call work in progress. Tool: {tool.name}")
        span = trace.get_current_span()
        if not span:
            return
        operation_type = "tool"
        operation_name = tool.name
        operation_backend = ""
        if hasattr(tool, "custom_metadata") and tool.custom_metadata:
            operation_backend = tool.custom_metadata.get("backend", "")

        attributes = {
            "gen_ai_operation_name": operation_name,
            "gen_ai_operation_type": operation_type,
            "gen_ai_operation_backend": operation_backend,
        }

        if hasattr(span, "start_time") and self.apmplus_span_latency:
            # span 耗时
            duration = (time.time_ns() - span.start_time) / 1e9  # type: ignore
            self.apmplus_span_latency.record(duration, attributes=attributes)

        if self.apmplus_tool_token_usage and hasattr(span, "attributes"):
            tool_input = span.attributes["gen_ai.tool.input"]
            tool_token_usage_input = (
                len(tool_input) / 4
            )  # tool token 数量，使用文本长度/4
            input_tool_token_attributes = {**attributes, "token_type": "input"}
            self.apmplus_tool_token_usage.record(
                tool_token_usage_input, attributes=input_tool_token_attributes
            )

            tool_output = span.attributes["gen_ai.tool.output"]
            tool_token_usage_output = (
                len(tool_output) / 4
            )  # tool token 数量，使用文本长度/4
            output_tool_token_attributes = {**attributes, "token_type": "output"}
            self.apmplus_tool_token_usage.record(
                tool_token_usage_output, attributes=output_tool_token_attributes
            )


class APMPlusExporterConfig(BaseModel):
    """Configuration model for APMPlus exporter settings.

    Manages connection parameters and authentication details for
    integrating with Volcengine's APMPlus observability platform.

    Attributes:
        endpoint: OTLP endpoint URL for APMPlus data ingestion
        app_key: Authentication key for APMPlus API access
        service_name: Service identifier displayed in APMPlus interface
    """

    endpoint: str = Field(
        default_factory=lambda: settings.apmplus_config.otel_exporter_endpoint,
    )
    app_key: str = Field(
        default_factory=lambda: settings.apmplus_config.otel_exporter_api_key,
    )
    service_name: str = Field(
        default_factory=lambda: settings.apmplus_config.otel_exporter_service_name,
        description="Service name shown in APMPlus frontend.",
    )


class APMPlusExporter(BaseExporter):
    """OpenTelemetry exporter for Volcengine APMPlus observability platform.

    APMPlusExporter provides comprehensive integration with Volcengine's APMPlus
    platform, enabling advanced observability for VeADK agents. It combines
    distributed tracing with detailed metrics collection for complete visibility
    into agent performance, costs, and reliability.

    Key Capabilities:
    - OTLP-based span export to APMPlus with authentication
    - Comprehensive metrics collection for LLM and tool operations
    - Automatic resource attribution with service identification
    - Cost tracking through detailed token usage metrics
    - Performance monitoring with latency histograms
    - Error tracking and exception monitoring

    Configuration:
    The exporter uses VeADK settings for automatic configuration but
    can be customized with explicit parameters. Authentication is
    handled through APMPlus app keys in request headers.

    Examples:
        Basic usage with default settings:
        ```python
        exporter = APMPlusExporter()
        tracer = OpentelemetryTracer(exporters=[exporter])
        ```

    Note:
        - Requires valid APMPlus app key for authentication
        - Endpoint should point to APMPlus OTLP ingestion service
        - Service name appears in APMPlus dashboards for identification
        - Metrics and spans are automatically correlated by trace context
        - Supports both development and production environments
    """

    config: APMPlusExporterConfig = Field(default_factory=APMPlusExporterConfig)

    def model_post_init(self, context: Any) -> None:
        """Initialize APMPlus exporter components after model construction.

        Sets up OTLP span exporter, batch processor, and meter uploader
        with proper authentication and resource attribution for APMPlus
        integration.

        Components Initialized:
        - OTLP span exporter with APMPlus endpoint and authentication
        - Batch span processor for efficient data transmission
        - Meter uploader for comprehensive metrics collection
        - Resource attributes for service identification
        """
        logger.info(f"APMPlusExporter sevice name: {self.config.service_name}")

        headers = {
            "x-byteapm-appkey": self.config.app_key,
        }
        self.headers |= headers

        resource_attributes = {
            "service.name": self.config.service_name,
        }
        self.resource_attributes |= resource_attributes

        self._exporter = OTLPSpanExporter(
            endpoint=self.config.endpoint, insecure=True, headers=self.headers
        )
        self.processor = BatchSpanProcessor(self._exporter)

        self.meter_uploader = MeterUploader(
            name="apmplus_meter",
            endpoint=self.config.endpoint,
            headers=self.headers,
            resource_attributes=self.resource_attributes,
        )

    @override
    def export(self) -> None:
        """Force immediate export of pending telemetry data to APMPlus.

        Triggers force flush on the OTLP span exporter to ensure all
        buffered span data is immediately transmitted to APMPlus for
        real-time observability and debugging.

        Operations:
        - Forces flush of span exporter if initialized
        - Logs export status and configuration details
        - Handles cases where exporter is not properly initialized
        """
        if self._exporter:
            self._exporter.force_flush()

            logger.info(
                f"APMPlusExporter exports data to {self.config.endpoint}, service name: {self.config.service_name}"
            )
        else:
            logger.warning("APMPlusExporter internal exporter is not initialized.")
