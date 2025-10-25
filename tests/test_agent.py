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

import os
from unittest.mock import Mock, patch

from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import load_memory

from veadk import Agent
from veadk.consts import (
    DEFAULT_AGENT_NAME,
    DEFAULT_MODEL_AGENT_API_BASE,
    DEFAULT_MODEL_AGENT_NAME,
    DEFAULT_MODEL_AGENT_PROVIDER,
    DEFAULT_MODEL_EXTRA_CONFIG,
)
from veadk.knowledgebase import KnowledgeBase
from veadk.memory.long_term_memory import LongTermMemory
from veadk.tools import load_knowledgebase_tool
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer


def test_agent():
    os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

    knowledgebase = KnowledgeBase(index="test_index", backend="local")

    long_term_memory = LongTermMemory(backend="local")
    tracer = OpentelemetryTracer()

    extra_config = {
        "extra_headers": {"thinking": "test"},
        "extra_body": {"content": "test"},
    }

    agent = Agent(
        model_name="test_model_name",
        model_provider="test_model_provider",
        model_api_key="test_model_api_key",
        model_api_base="test_model_api_base",
        model_extra_config=extra_config,
        tools=[],
        sub_agents=[],
        knowledgebase=knowledgebase,
        long_term_memory=long_term_memory,
        tracers=[tracer],
    )

    assert agent.model.model == f"{agent.model_provider}/{agent.model_name}"  # type: ignore

    expected_config = DEFAULT_MODEL_EXTRA_CONFIG.copy()
    expected_config["extra_headers"] |= extra_config["extra_headers"]
    expected_config["extra_body"] |= extra_config["extra_body"]

    assert agent.model_extra_config == expected_config

    assert agent.knowledgebase == knowledgebase
    assert agent.knowledgebase.backend == "local"  # type: ignore

    assert agent.long_term_memory.backend == "local"  # type: ignore
    assert load_memory in agent.tools


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_default_values():
    agent = Agent()

    assert agent.name == DEFAULT_AGENT_NAME

    assert agent.model_name == DEFAULT_MODEL_AGENT_NAME
    assert agent.model_provider == DEFAULT_MODEL_AGENT_PROVIDER
    assert agent.model_api_base == DEFAULT_MODEL_AGENT_API_BASE

    assert agent.tools == []
    assert agent.sub_agents == []
    assert agent.knowledgebase is None
    assert agent.long_term_memory is None
    # assert agent.tracers == []


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_without_knowledgebase():
    agent = Agent()

    assert agent.knowledgebase is None
    assert load_knowledgebase_tool.load_knowledgebase_tool not in agent.tools


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_without_long_term_memory():
    agent = Agent()

    assert agent.long_term_memory is None
    assert load_memory not in agent.tools


@patch("veadk.agent.LiteLlm")
def test_agent_model_creation(mock_lite_llm):
    mock_model = Mock()
    mock_lite_llm.return_value = mock_model

    agent = Agent(
        model_name="test_model",
        model_provider="test_provider",
        model_api_key="test_key",
        model_api_base="test_base",
    )

    mock_lite_llm.assert_called_once()
    assert agent.model == mock_model


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_with_existing_model():
    existing_model = LiteLlm(model="test_model")
    agent = Agent(model=existing_model)

    assert agent.model == existing_model


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_model_extra_config_merge():
    user_config = {
        "extra_headers": {"custom": "header"},
        "extra_body": {"custom": "body"},
        "other_param": "value",
    }

    agent = Agent(model_extra_config=user_config)

    expected_headers = DEFAULT_MODEL_EXTRA_CONFIG["extra_headers"].copy()
    expected_headers["custom"] = "header"

    expected_body = DEFAULT_MODEL_EXTRA_CONFIG["extra_body"].copy()
    expected_body["custom"] = "body"

    assert agent.model_extra_config["extra_headers"] == expected_headers
    assert agent.model_extra_config["extra_body"] == expected_body
    assert agent.model_extra_config["other_param"] == "value"


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_empty_model_extra_config():
    agent = Agent(model_extra_config={})

    assert (
        agent.model_extra_config["extra_headers"]
        == DEFAULT_MODEL_EXTRA_CONFIG["extra_headers"]
    )
    assert (
        agent.model_extra_config["extra_body"]
        == DEFAULT_MODEL_EXTRA_CONFIG["extra_body"]
    )


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_with_tools():
    mock_tool = Mock()
    agent = Agent(tools=[mock_tool])

    assert mock_tool in agent.tools


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_with_sub_agents():
    adk_agent = LlmAgent(name="agent")
    veadk_agent = Agent(name="agent")
    agent = Agent(sub_agents=[adk_agent, veadk_agent])

    assert adk_agent in agent.sub_agents
    assert veadk_agent in agent.sub_agents
    assert adk_agent.parent_agent == agent
    assert veadk_agent.parent_agent == agent


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_with_tracers():
    tracer1 = OpentelemetryTracer()
    tracer2 = OpentelemetryTracer()

    agent = Agent(tracers=[tracer1, tracer2])

    assert len(agent.tracers) == 2
    assert tracer1 in agent.tracers
    assert tracer2 in agent.tracers


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_custom_name_and_description():
    custom_name = "CustomAgent"
    custom_description = "A custom agent for testing"

    agent = Agent(name=custom_name, description=custom_description)

    assert agent.name == custom_name
    assert agent.description == custom_description
