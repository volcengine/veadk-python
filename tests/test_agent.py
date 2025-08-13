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

from google.adk.tools import load_memory

from veadk import Agent
from veadk.knowledgebase import KnowledgeBase
from veadk.memory.long_term_memory import LongTermMemory
from veadk.tools import load_knowledgebase_tool
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer


def test_agent():
    knowledgebase = KnowledgeBase()
    long_term_memory = LongTermMemory(backend="local")
    tracer = OpentelemetryTracer()

    agent = Agent(
        model_name="test_model_name",
        model_provider="test_model_provider",
        model_api_key="test_model_api_key",
        model_api_base="test_model_api_base",
        tools=[],
        sub_agents=[],
        knowledgebase=knowledgebase,
        long_term_memory=long_term_memory,
        tracers=[tracer],
        serve_url="",
    )

    assert agent.model.model == f"{agent.model_provider}/{agent.model_name}"

    assert agent.knowledgebase == knowledgebase
    assert agent.knowledgebase.backend == "local"
    assert load_knowledgebase_tool.knowledgebase == agent.knowledgebase
    assert load_knowledgebase_tool.load_knowledgebase_tool in agent.tools

    assert agent.long_term_memory.backend == "local"
    assert load_memory in agent.tools

    assert tracer.tracer_hook_before_model in agent.before_model_callback
    assert tracer.tracer_hook_after_model in agent.after_model_callback
    assert tracer.tracer_hook_after_tool in agent.after_tool_callback
