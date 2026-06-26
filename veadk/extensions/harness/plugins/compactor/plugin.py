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

"""Tool-result compaction plugin for VeADK Runner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from google.adk.models import LlmRequest, LlmResponse
from google.adk.plugins import BasePlugin

from veadk.extensions.harness.modules.tool_result_compactor import ToolResultCompactor
from veadk.extensions.harness.plugins._shared.callback_utils import (
    run_context_from_callback,
    run_context_from_tool,
    tool_name,
)
from veadk.extensions.harness.plugins.content_adapter import contents_to_messages
from veadk.extensions.harness.schemas import (
    CompactionReport,
    CompressionRequest,
    HarnessEvent,
)
from veadk.extensions.harness.stores import HarnessStoreProtocol, InMemoryHarnessStore
from veadk.extensions.harness.utils import coerce_json_object

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.tool_context import ToolContext


class HarnessCompressPlugin(BasePlugin):
    """Compacts oversized tool results and historical tool context."""

    def __init__(
        self,
        *,
        compactor: ToolResultCompactor | None = None,
        compressor: ToolResultCompactor | None = None,
        store: HarnessStoreProtocol | None = None,
        profile: str = "default",
    ) -> None:
        super().__init__(name="harness_compress_plugin")
        self.compactor = compactor or compressor or ToolResultCompactor()
        self.compressor = self.compactor
        self.store = store or InMemoryHarnessStore()
        self.profile = profile
        self.compaction_reports: list[CompactionReport] = []

    async def before_model_callback(
        self,
        *,
        callback_context: "CallbackContext",
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        tool_reports = self._compact_function_responses(llm_request)
        messages = contents_to_messages(llm_request.contents)
        self.compaction_reports.extend(tool_reports)
        if not messages:
            return None
        result = self.compactor.compress_messages(
            CompressionRequest(
                messages=messages,
                max_context_chars=self.compactor.config.max_context_chars,
            )
        )
        if result.report.changed or tool_reports:
            self.store.append_event(
                HarnessEvent(
                    event_type="compressor.model_context",
                    run_context=run_context_from_callback(
                        callback_context,
                        profile=self.profile,
                    ),
                    payload={
                        "context_report": result.report.model_dump(mode="json"),
                        "tool_reports": [
                            report.model_dump(mode="json") for report in tool_reports
                        ],
                    },
                )
            )
            if result.report.changed:
                self.compaction_reports.append(result.report)
        return None

    async def after_tool_callback(
        self,
        *,
        tool: "BaseTool",
        tool_args: dict[str, object],
        tool_context: "ToolContext",
        result: dict[str, object],
    ) -> dict[str, object] | None:
        compressed, report = self.compactor.compress_tool_result(result)
        if not report.changed:
            return None
        self.compaction_reports.append(report)
        self.store.append_event(
            HarnessEvent(
                event_type="compressor.tool_result",
                run_context=run_context_from_tool(tool_context, profile=self.profile),
                payload={
                    "tool": tool_name(tool),
                    "tool_args": coerce_json_object(tool_args),
                    "report": report.model_dump(mode="json"),
                },
            )
        )
        return compressed if isinstance(compressed, dict) else {"result": compressed}

    def reset_diagnostics(self) -> None:
        self.compaction_reports.clear()

    def _compact_function_responses(
        self, llm_request: LlmRequest
    ) -> list[CompactionReport]:
        reports: list[CompactionReport] = []
        for content in llm_request.contents:
            for part in content.parts or []:
                function_response = part.function_response
                if function_response is None:
                    continue
                response = function_response.response
                if not isinstance(response, dict):
                    continue
                compressed, report = self.compactor.compress_tool_result(response)
                if not report.changed:
                    continue
                function_response.response = compressed
                reports.append(report)
        return reports
