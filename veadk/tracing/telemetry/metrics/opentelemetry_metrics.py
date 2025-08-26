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

from google.adk.models.llm_response import LlmResponse
from opentelemetry import metrics
from opentelemetry.metrics._internal import Meter

from veadk.config import getenv

METER_NAME_TEMPLATE = "veadk.{exporter_id}.meter"


class MeterUploader:
    def __init__(self, exporter_id: str):
        self.meter: Meter = metrics.get_meter(
            METER_NAME_TEMPLATE.format(exporter_id=exporter_id)
        )

        self.base_attributes = {
            "gen_ai_system": "volcengine",
            "server_address": "api.volcengine.com",
            "gen_ai_response_model": getenv("MODEL_AGENT_NAME", "unknown"),
            "stream": "false",
            "gen_ai_operation_name": "chat_completions",
        }
        self.llm_invoke_counter = self.meter.create_counter(
            name="gen_ai.chat.count",
            description="Number of LLM invocations",
            unit="count",
        )
        self.token_usage = self.meter.create_histogram(
            name="gen_ai.client.token.usage",
            description="Token consumption of LLM invocations",
            unit="count",
        )

    def record(self, llm_response: LlmResponse):
        input_token = llm_response.usage_metadata.prompt_token_count
        output_token = llm_response.usage_metadata.candidates_token_count
        self.llm_invoke_counter.add(1, self.base_attributes)
        token_attributes = {**self.base_attributes, "gen_ai_token_type": "input"}
        self.token_usage.record(input_token, attributes=token_attributes)
        token_attributes = {**self.base_attributes, "gen_ai_token_type": "output"}
        self.token_usage.record(output_token, attributes=token_attributes)
