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

from __future__ import annotations

import json
import time
from typing import Any

from opentelemetry import trace as trace_api
from opentelemetry.sdk import trace as trace_sdk
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanLimits, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import override

from veadk.tracing.base_tracer import BaseTracer
from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.tracing.telemetry.exporters.inmemory_exporter import InMemoryExporter
from veadk.utils.logger import get_logger
from veadk.utils.misc import get_agent_dir
from veadk.utils.patches import patch_google_adk_telemetry

logger = get_logger(__name__)


class OpentelemetryTracer(BaseModel, BaseTracer):
    """OpenTelemetry-based tracer implementation for comprehensive agent observability.

    This class provides a complete tracing solution using OpenTelemetry standards,
    supporting multiple exporters for different observability platforms. It captures
    detailed execution traces including LLM calls, tool invocations, and agent workflow
    patterns for debugging and performance analysis.

    Key Features:
    - Multi-exporter support (APMPlus, in-memory, custom exporters)
    - Thread-safe span processing with configurable limits
    - Local trace dumping with JSON serialization
    - Resource attribute management for metadata enrichment
    - Force flush capabilities for immediate data export

    Architecture:
    The tracer initializes a global TracerProvider with custom span processors for
    each configured exporter. It maintains an internal in-memory exporter for local
    operations while supporting external observability platforms simultaneously.

    Attributes:
        name: Identifier for this tracer instance, used in file naming and logging
        exporters: List of exporter instances for sending trace data to different backends

    Examples:
        Basic usage with APMPlus exporter:
        ```python
        exporters = [
            CozeloopExporter(),
            APMPlusExporter(),
            TLSExporter(),
        ]
        tracer = OpentelemetryTracer(exporters=exporters)
        ```

    Note:
        - InMemoryExporter cannot be explicitly added to exporters list
        - Span limits are set to 4096 attributes for comprehensive data capture
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(
        default="veadk_opentelemetry_tracer", description="The identifier of tracer."
    )

    exporters: list[BaseExporter] = Field(
        default_factory=list,
        description="The exporters to export spans.",
    )

    # Forbid InMemoryExporter in exporters list
    # cause we need to set custom in-memory span processor by VeADK
    @field_validator("exporters")
    @classmethod
    def forbid_inmemory_exporter(cls, v: list[BaseExporter]) -> list[BaseExporter]:
        """Validate that InMemoryExporter is not explicitly added to exporters list.

        InMemoryExporter is automatically managed internally and should not be
        included in the user-provided exporters list to avoid conflicts.

        Args:
            v: List of exporter instances to validate

        Returns:
            list[BaseExporter]: The validated list of exporters

        Raises:
            ValueError: If InMemoryExporter is found in the exporters list
        """
        for e in v:
            if isinstance(e, InMemoryExporter):
                raise ValueError("InMemoryExporter is not allowed in exporters list")
        return v

    def model_post_init(self, context: Any) -> None:
        """Initialize the tracer after model construction.

        This method performs post-initialization setup including Google ADK
        telemetry patching and global tracer provider configuration.
        """
        # Replace Google ADK tracing funcs
        # `trace_call_llm` and `trace_tool_call`
        patch_google_adk_telemetry()

        # We save internal processors for tracing data dump
        self._processors = []

        # Initialize global tracer provider to avoid VeFaaS global tracer
        # provider conflicts
        self._init_global_tracer_provider()

    def _init_global_tracer_provider(self) -> None:
        """Initialize the global OpenTelemetry tracer provider with configured exporters.

        This method sets up the global tracer provider, configures span processors
        for each exporter, and ensures proper resource attribution. It also handles
        duplicate exporter detection and in-memory span collection setup.
        """
        # set provider anyway, then get global provider
        # set if not exist
        trace_api.set_tracer_provider(
            trace_sdk.TracerProvider(
                span_limits=SpanLimits(
                    max_attributes=4096,
                )
            )
        )

        # add in-memory exporter to exporters list
        self._inmemory_exporter = InMemoryExporter()
        self.exporters.append(self._inmemory_exporter)

        # Call each exporter's register method to register with the global tracer provider
        # This allows each exporter to handle its own configuration and registration logic
        for exporter in self.exporters:
            exporter.register()
            
            # Add processor to internal list if exists
            if exporter.processor:
                self._processors.append(exporter.processor)
                logger.debug(
                    f"Add span processor for exporter `{exporter.__class__.__name__}` to OpentelemetryTracer."
                )
            else:
                logger.error(
                    f"Add span processor for exporter `{exporter.__class__.__name__}` to OpentelemetryTracer failed."
                )

        logger.info(
            f"Init OpentelemetryTracer with {len(self._processors)} exporter(s)."
        )

    @property
    def trace_file_path(self) -> str:
        """Get the file path of the most recent trace dump.

        Returns:
            str: Full path to the trace file, or placeholder if not yet dumped
        """
        return self._trace_file_path

    @property
    def trace_id(self) -> str:
        """Get the current trace ID in hexadecimal format.

        Returns:
            str: Hexadecimal representation of the current trace ID, or
                placeholder string if trace ID cannot be retrieved
        """
        try:
            trace_id = hex(int(self._inmemory_exporter._exporter.trace_id))[2:]  # type: ignore
            return trace_id
        except Exception as e:
            logger.error(f"Failed to get trace_id from InMemoryExporter: {e}")
            return self._trace_id

    def force_export(self) -> None:
        """Force immediate export of all pending spans across all processors.

        This method triggers force_flush on all configured span processors,
        ensuring that buffered span data is immediately sent to exporters.
        Includes a small delay between flushes to prevent overwhelming exporters.
        """
        for processor in self._processors:
            time.sleep(0.05)
            processor.force_flush()

    @override
    def dump(
        self,
        user_id: str = "unknown_user_id",
        session_id: str = "unknown_session_id",
        path: str = get_agent_dir(),
    ) -> str:
        """Dump collected trace data to a local JSON file.

        This method exports all spans associated with the current session to a
        structured JSON file for offline analysis. The file includes span metadata,
        timing information, attributes, and parent-child relationships.

        Args:
            user_id: User identifier for trace organization and file naming
            session_id: Session identifier for filtering and organizing spans
            path: Directory path for the output file. Defaults to agents directory

        Returns:
            str: Full path to the created trace file, or empty string if export fails

        Note:
            - Forces export of all pending spans before dumping
            - Filters spans by session_id for relevant data only
            - File format is structured JSON with span details and relationships
            - Supports non-ASCII characters for international content
        """

        def _build_trace_file_path(path: str, user_id: str, session_id: str) -> str:
            return f"{path}/{self.name}_{user_id}_{session_id}_{self.trace_id}.json"

        if not self._inmemory_exporter:
            logger.warning(
                "InMemoryExporter is not initialized. Please check your tracer exporters."
            )
            return ""
        self.force_export()

        spans = self._inmemory_exporter._exporter.get_finished_spans(  # type: ignore
            session_id=session_id
        )
        data = (
            [
                {
                    "name": s.name,
                    "span_id": s.context.span_id,
                    "trace_id": s.context.trace_id,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "attributes": dict(s.attributes),
                    "parent_span_id": s.parent.span_id if s.parent else None,
                }
                for s in spans
            ]
            if spans
            else []
        )

        self._trace_file_path = _build_trace_file_path(path, user_id, session_id)
        with open(self._trace_file_path, "w") as f:
            json.dump(
                data, f, indent=4, ensure_ascii=False
            )  # ensure_ascii=False to support Chinese characters

        logger.info(
            f"OpenTelemetryTracer dumps {len(spans)} spans to {self._trace_file_path}. Trace id: {self.trace_id} (hex)"
        )

        return self._trace_file_path
