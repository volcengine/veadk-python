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

from opentelemetry.metrics._internal import Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from veadk.config import getenv


class MeterContext:
    def __init__(
        self,
        meter: Meter,
        provider: MeterProvider,
        reader: PeriodicExportingMetricReader,
    ):
        self.meter = meter
        self.provider = provider
        self.reader = reader


class MeterUploader:
    def __init__(self, meter_context: MeterContext):
        self.meter = meter_context.meter
        self.provider = meter_context.provider
        self.reader = meter_context.reader

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

    def record(self, prompt_tokens: list[int], completion_tokens: list[int]):
        self.llm_invoke_counter.add(len(completion_tokens), self.base_attributes)

        for prompt_token in prompt_tokens:
            token_attributes = {**self.base_attributes, "gen_ai_token_type": "input"}
            self.token_usage.record(prompt_token, attributes=token_attributes)
        for completion_token in completion_tokens:
            token_attributes = {**self.base_attributes, "gen_ai_token_type": "output"}
            self.token_usage.record(completion_token, attributes=token_attributes)

    def close(self):
        time.sleep(0.05)
        self.reader.force_flush()
        self.provider.shutdown()
