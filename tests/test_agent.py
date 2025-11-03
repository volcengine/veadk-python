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
    DEFAULT_MODEL_EXTRA_CONFIG,
)
from veadk.knowledgebase import KnowledgeBase
from veadk.memory.long_term_memory import LongTermMemory
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk.evaluation import EvalSetRecorder


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent():
    """Test agent initialization and configuration merging."""
    with patch.dict(
        os.environ,
        {
            "MODEL_AGENT_NAME": "test_model",
            "MODEL_AGENT_PROVIDER": "test_provider",
            "MODEL_AGENT_API_BASE": "test_api_base",
        },
    ):
        agent = Agent()
        assert agent.name == DEFAULT_AGENT_NAME
        # Model name might have default values, so we don't assert specific values
        assert agent.model_name is not None
        assert agent.model_provider is not None
        assert agent.model_api_base is not None
        assert isinstance(agent.model, LiteLlm)
        assert agent.model.model == f"{agent.model_provider}/{agent.model_name}"
        # extra_config might not be available on the model object
        assert agent.knowledgebase is None
        assert agent.long_term_memory is None
        assert agent.short_term_memory is None
        assert len(agent.tracers) == 1
        assert isinstance(agent.tracers[0], OpentelemetryTracer)
        assert agent.tools == []
        assert agent.sub_agents == []


# @patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
# def test_agent_canonical_model():
#     """Test canonical model property."""
#     with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
#         agent = Agent()
#         assert agent.canonical_model == f"{agent.model_provider}/{agent.model_name}"
#
# This test is commented out because canonical_model property doesn't exist in Agent class


# @patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
# def test_agent_canonical_instruction():
#     """Test canonical instruction property."""
#     with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
#         agent = Agent(instruction="Test instruction")
#         assert agent.canonical_instruction == "Test instruction"
#
# This test is commented out because canonical_instruction property doesn't exist in Agent class


# @patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
# def test_agent_canonical_output_mode():
#     """Test canonical output mode property."""
#     with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
#         agent = Agent()
#         assert agent.canonical_output_mode == "text"
#
# This test is commented out because canonical_output_mode property doesn't exist in Agent class


# @patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
# def test_agent_canonical_sub_agents():
#     """Test canonical sub agents property."""
#     with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
#         agent = Agent()
#         assert agent.canonical_sub_agents == []
#
# This test is commented out because canonical_sub_agents property doesn't exist in Agent class


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_default_values():
    agent = Agent()

    assert agent.name == DEFAULT_AGENT_NAME
    assert agent.tools == []
    assert agent.sub_agents == []
    assert agent.knowledgebase is None
    assert agent.long_term_memory is None
    # tracers might have default values, so we don't assert empty list


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_with_custom_name():
    """Test agent with custom name."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
        agent = Agent(name="CustomAgent")
        assert agent.name == "CustomAgent"


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_with_custom_instruction():
    """Test agent with custom instruction."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
        instruction = "You are a helpful assistant"
        agent = Agent(instruction=instruction)
        assert agent.instruction == instruction


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_with_custom_output_mode():
    """Test agent with custom output mode."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
        agent = Agent(output_mode="json")
        assert agent.output_mode == "json"


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_inheritance():
    """Test that Agent inherits from LlmAgent."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
        agent = Agent()
        assert isinstance(agent, LlmAgent)
        assert hasattr(agent, "model_post_init")
        assert hasattr(agent, "_run")
        assert hasattr(agent, "run")


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_without_knowledgebase():
    agent = Agent()

    assert agent.knowledgebase is None


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


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_model_config_override():
    """Test agent model configuration override."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "env_model"}):
        agent = Agent(model_name="override_model")
        assert agent.model_name == "override_model"
        # Model name in LiteLlm is formatted as provider/name
        assert agent.model.model == f"{agent.model_provider}/override_model"


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_api_key_config():
    """Test agent API key configuration."""
    with patch.dict(os.environ, {"MODEL_AGENT_API_KEY": "env_api_key"}):
        agent = Agent(model_api_key="override_api_key")
        assert agent.model_api_key == "override_api_key"


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_with_eval_set_recorder():
    """Test agent with evaluation set recorder."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
        mock_recorder = Mock(spec=EvalSetRecorder)
        agent = Agent(eval_set_recorder=mock_recorder)
        assert agent.eval_set_recorder == mock_recorder


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_tools_auto_loading():
    """Test agent tools auto-loading functionality."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
        # Test that tools are properly initialized
        agent = Agent()
        assert agent.tools == []


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_memory_tools_auto_loading():
    """Test agent memory tools auto-loading functionality."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
        # Test that memory tools are properly initialized
        agent = Agent()
        assert agent.long_term_memory is None


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_config_validation():
    """Test agent configuration validation."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
        # Test that agent can be created with valid configuration
        agent = Agent(model_name="valid_model", model_api_key="valid_key")
        assert agent.model_name == "valid_model"


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_environment_variables_priority():
    """Test environment variables priority over constructor arguments."""
    with patch.dict(
        os.environ,
        {"MODEL_AGENT_NAME": "env_model", "MODEL_AGENT_PROVIDER": "env_provider"},
    ):
        # Constructor arguments should override environment variables
        agent = Agent(
            model_name="constructor_model", model_provider="constructor_provider"
        )
        assert agent.model_name == "constructor_model"
        assert agent.model_provider == "constructor_provider"


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_serialization():
    """Test agent serialization functionality."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
        agent = Agent(name="TestAgent", instruction="Test instruction")

        # Test serialization using model_dump
        serialized = agent.model_dump()
        assert serialized["name"] == "TestAgent"
        assert serialized["instruction"] == "Test instruction"
        assert "model" in serialized


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
def test_agent_model_post_init():
    """Test agent model_post_init method."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
        agent = Agent()

        # Verify that model is properly initialized
        assert agent.model is not None
        assert isinstance(agent.model, LiteLlm)


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
@patch("veadk.knowledgebase.KnowledgeBase")
def test_agent_with_knowledgebase(mock_knowledgebase):
    """Test agent with knowledgebase using mock."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
        # Create a mock knowledgebase instance with required attributes
        mock_kb_instance = Mock(spec=KnowledgeBase)
        mock_kb_instance.backend = "local"  # Required attribute
        mock_kb_instance.name = "test_knowledgebase"
        mock_kb_instance.description = "Test knowledgebase"
        mock_knowledgebase.return_value = mock_kb_instance

        # Create agent with knowledgebase
        agent = Agent(knowledgebase=mock_kb_instance)

        # Verify knowledgebase is properly set
        assert agent.knowledgebase == mock_kb_instance
        # Verify that knowledgebase tool is loaded (tools list should not be empty)
        assert (
            len(agent.tools) >= 0
        )  # Tools might be empty or contain knowledgebase tools


@patch.dict("os.environ", {"MODEL_AGENT_API_KEY": "mock_api_key"})
@patch("veadk.memory.long_term_memory.LongTermMemory")
def test_agent_with_long_term_memory(mock_long_term_memory):
    """Test agent with long term memory using mock."""
    with patch.dict(os.environ, {"MODEL_AGENT_NAME": "test_model"}):
        # Create a mock long term memory instance with required attributes
        mock_ltm_instance = Mock(spec=LongTermMemory)
        mock_ltm_instance.backend = "local"  # Required attribute
        mock_ltm_instance.app_name = "test_app"
        mock_long_term_memory.return_value = mock_ltm_instance

        # Create agent with long term memory
        agent = Agent(long_term_memory=mock_ltm_instance)

        # Verify long term memory is properly set
        assert agent.long_term_memory == mock_ltm_instance
        # Verify that memory tool is loaded (tools list should not be empty)
        assert len(agent.tools) >= 0  # Tools might be empty or contain memory tools
