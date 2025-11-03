"""Tests for BaseAgent."""

import asyncio
import pytest
from typing import Callable, Optional

from google.adk.agents.base_agent import BaseAgent

# from google.adk.agents.llm_agent import LlmAgent
# from google.adk.agents.sequential_agent import SequentialAgent
# from google.adk.agents.parallel_agent import ParallelAgent
# from google.adk.agents.loop_agent import LoopAgent
# from google.adk.agents.agent_config import AgentConfig
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import ResumabilityConfig
from google.adk.sessions import InMemorySessionService
from google.adk.agents.base_agent import BaseAgentState
from google.adk.events import Event
from google.genai import types


class _TestingAgent(BaseAgent):
    """A testing agent that implements the abstract methods."""

    def __init__(
        self,
        name: str,
        description: str = "",
        sub_agents: list[BaseAgent] | None = None,
        before_agent_callback: Optional[Callable] = None,
        after_agent_callback: Optional[Callable] = None,
    ):
        # Convert None to empty list to avoid Pydantic validation errors
        sub_agents_list = sub_agents if sub_agents is not None else []
        super().__init__(
            name=name,
            description=description,
            sub_agents=sub_agents_list,
            before_agent_callback=before_agent_callback,
            after_agent_callback=after_agent_callback,
        )

    async def _run_async_impl(self, ctx: InvocationContext):
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            content=types.Content(parts=[types.Part(text="Hello, async!")]),
            branch=ctx.branch,
        )

    async def _run_live_impl(self, ctx: InvocationContext):
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            content=types.Content(parts=[types.Part(text="Hello, live!")]),
            branch=ctx.branch,
        )


class _IncompleteAgent(BaseAgent):
    """An incomplete agent that doesn't implement abstract methods."""

    def __init__(
        self,
        name: str,
        description: str = "",
        sub_agents: list[BaseAgent] | None = None,
    ):
        # Convert None to empty list to avoid Pydantic validation errors
        sub_agents_list = sub_agents if sub_agents is not None else []
        super().__init__(name=name, description=description, sub_agents=sub_agents_list)


async def _create_parent_invocation_context(
    test_name: str, agent: BaseAgent, branch: str | None = None
) -> InvocationContext:
    """Create a parent invocation context for testing."""
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=f"{test_name}_app", user_id=f"{test_name}_user"
    )
    return InvocationContext(
        invocation_id=f"{test_name}_invocation",
        agent=agent,
        session=session,
        session_service=session_service,
        branch=branch,
    )


def test_agent_name_validation():
    """Test that agent names are validated correctly."""
    # Valid names
    _TestingAgent(name="valid_name")
    _TestingAgent(name="valid_name_123")
    _TestingAgent(name="_valid_name")

    # Invalid names
    with pytest.raises(ValueError):
        _TestingAgent(name="")
    with pytest.raises(ValueError):
        _TestingAgent(name="invalid name")
    with pytest.raises(ValueError):
        _TestingAgent(name="invalid@name")
    with pytest.raises(ValueError):
        _TestingAgent(name="123invalid")
    with pytest.raises(ValueError):
        _TestingAgent(name="invalid-name")


def test_agent_initialization():
    """Test that agents are initialized correctly."""
    agent = _TestingAgent(name="test_agent", description="A test agent")
    assert agent.name == "test_agent"
    assert agent.description == "A test agent"
    assert agent.sub_agents == []
    assert agent.parent_agent is None


def test_agent_with_sub_agents():
    """Test that agents with sub-agents are initialized correctly."""
    sub_agent_1 = _TestingAgent(name="sub_agent_1")
    sub_agent_2 = _TestingAgent(name="sub_agent_2")
    agent = _TestingAgent(name="parent_agent", sub_agents=[sub_agent_1, sub_agent_2])
    assert agent.sub_agents == [sub_agent_1, sub_agent_2]
    assert sub_agent_1.parent_agent == agent
    assert sub_agent_2.parent_agent == agent


def test_agent_str_and_repr():
    """Test the string representation of agents."""
    agent = _TestingAgent(name="test_agent")
    # The actual string representation includes more details than just the name
    assert agent.name in str(agent)
    assert repr(agent).startswith("_TestingAgent")
    assert "name='test_agent'" in repr(agent)


@pytest.mark.asyncio
async def test_run_async(request: pytest.FixtureRequest):
    """Test the async run method."""
    agent = _TestingAgent(name=f"{request.function.__name__}_test_agent")
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    events = [e async for e in agent.run_async(parent_ctx)]

    assert len(events) == 1
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Hello, async!"


@pytest.mark.asyncio
async def test_run_async_with_branch(request: pytest.FixtureRequest):
    """Test the async run method with a branch."""
    agent = _TestingAgent(name=f"{request.function.__name__}_test_agent")
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent, branch="parent_branch"
    )

    events = [e async for e in agent.run_async(parent_ctx)]

    assert len(events) == 1
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Hello, async!"
    assert events[0].branch == "parent_branch"


@pytest.mark.asyncio
async def test_run_async_with_before_agent_callback(request: pytest.FixtureRequest):
    """Test the async run method with a before_agent callback."""

    def mock_callback(callback_context: CallbackContext):
        # Return None to not modify the events
        return None

    agent = _TestingAgent(
        name=f"{request.function.__name__}_test_agent",
        before_agent_callback=mock_callback,
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    events = [e async for e in agent.run_async(parent_ctx)]

    assert len(events) == 1
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Hello, async!"


@pytest.mark.asyncio
async def test_run_async_with_after_agent_callback(request: pytest.FixtureRequest):
    """Test the async run method with an after_agent callback."""

    def mock_callback(callback_context: CallbackContext):
        # Return None to not modify the events
        return None

    agent = _TestingAgent(
        name=f"{request.function.__name__}_test_agent",
        after_agent_callback=mock_callback,
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    events = [e async for e in agent.run_async(parent_ctx)]

    assert len(events) == 1
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Hello, async!"


@pytest.mark.asyncio
async def test_run_async_with_both_callbacks(request: pytest.FixtureRequest):
    """Test the async run method with both before_agent and after_agent callbacks."""

    def mock_before(callback_context: CallbackContext):
        # Return None to not modify the events
        return None

    def mock_after(callback_context: CallbackContext):
        # Return None to not modify the events
        return None

    agent = _TestingAgent(
        name=f"{request.function.__name__}_test_agent",
        before_agent_callback=mock_before,
        after_agent_callback=mock_after,
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    events = [e async for e in agent.run_async(parent_ctx)]

    assert len(events) == 1
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Hello, async!"


@pytest.mark.asyncio
async def test_run_async_with_async_before_agent_callback(
    request: pytest.FixtureRequest,
):
    """Test the async run method with an async before_agent callback."""

    async def async_before_agent(callback_context: CallbackContext):
        await asyncio.sleep(0.01)

    agent = _TestingAgent(
        name=f"{request.function.__name__}_test_agent",
        before_agent_callback=async_before_agent,
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    events = [e async for e in agent.run_async(parent_ctx)]

    assert len(events) == 1
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Hello, async!"


@pytest.mark.asyncio
async def test_run_async_with_async_after_agent_callback(
    request: pytest.FixtureRequest,
):
    """Test the async run method with an async after_agent callback."""

    async def async_after_agent(callback_context: CallbackContext):
        await asyncio.sleep(0.01)

    agent = _TestingAgent(
        name=f"{request.function.__name__}_test_agent",
        after_agent_callback=async_after_agent,
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    events = [e async for e in agent.run_async(parent_ctx)]

    assert len(events) == 1
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Hello, async!"


@pytest.mark.asyncio
async def test_run_async_with_before_agent_callback_modifying_events(
    request: pytest.FixtureRequest,
):
    """Test the async run method with a before_agent callback that modifies events."""

    def before_agent(callback_context: CallbackContext):
        return types.Content(parts=[types.Part(text="Before agent callback.")])

    agent = _TestingAgent(
        name=f"{request.function.__name__}_test_agent",
        before_agent_callback=before_agent,
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    events = [e async for e in agent.run_async(parent_ctx)]

    assert len(events) == 1
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Before agent callback."


@pytest.mark.asyncio
async def test_run_async_with_after_agent_callback_modifying_events(
    request: pytest.FixtureRequest,
):
    """Test the async run method with an after_agent callback that modifies events."""

    def after_agent(callback_context: CallbackContext):
        return types.Content(parts=[types.Part(text="After agent callback.")])

    agent = _TestingAgent(
        name=f"{request.function.__name__}_test_agent", after_agent_callback=after_agent
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    events = [e async for e in agent.run_async(parent_ctx)]

    assert len(events) == 2
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Hello, async!"
    assert events[1].author == agent.name
    assert events[1].content.parts[0].text == "After agent callback."


@pytest.mark.asyncio
async def test_run_async_with_both_callbacks_modifying_events(
    request: pytest.FixtureRequest,
):
    """Test the async run method with both callbacks modifying events."""

    def before_agent(callback_context: CallbackContext):
        return types.Content(parts=[types.Part(text="Before agent callback.")])

    def after_agent(callback_context: CallbackContext):
        return types.Content(parts=[types.Part(text="After agent callback.")])

    agent = _TestingAgent(
        name=f"{request.function.__name__}_test_agent",
        before_agent_callback=before_agent,
        after_agent_callback=after_agent,
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    events = [e async for e in agent.run_async(parent_ctx)]

    assert len(events) == 1
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Before agent callback."


@pytest.mark.asyncio
async def test_run_async_with_before_agent_callback_returning_event(
    request: pytest.FixtureRequest,
):
    """Test the async run method with a before_agent callback that returns an event."""

    def before_agent(callback_context: CallbackContext):
        return types.Content(
            parts=[types.Part(text="Agent reply from before agent callback.")]
        )

    agent = _TestingAgent(
        name=f"{request.function.__name__}_test_agent",
        before_agent_callback=before_agent,
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    events = [e async for e in agent.run_async(parent_ctx)]

    assert len(events) == 1
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Agent reply from before agent callback."


@pytest.mark.asyncio
async def test_run_async_with_after_agent_callback_returning_event(
    request: pytest.FixtureRequest,
):
    """Test the async run method with an after_agent callback that returns an event."""

    def after_agent(callback_context: CallbackContext):
        return types.Content(
            parts=[types.Part(text="Agent reply from after agent callback.")]
        )

    agent = _TestingAgent(
        name=f"{request.function.__name__}_test_agent", after_agent_callback=after_agent
    )
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    events = [e async for e in agent.run_async(parent_ctx)]

    assert len(events) == 2
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Hello, async!"
    assert events[1].author == agent.name
    assert events[1].content.parts[0].text == "Agent reply from after agent callback."


@pytest.mark.asyncio
async def test_run_async_incomplete_agent(request: pytest.FixtureRequest):
    agent = _IncompleteAgent(name=f"{request.function.__name__}_test_agent")
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    with pytest.raises(NotImplementedError):
        [e async for e in agent.run_async(parent_ctx)]


@pytest.mark.asyncio
async def test_run_live(request: pytest.FixtureRequest):
    agent = _TestingAgent(name=f"{request.function.__name__}_test_agent")
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    events = [e async for e in agent.run_live(parent_ctx)]

    assert len(events) == 1
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Hello, live!"


@pytest.mark.asyncio
async def test_run_live_with_branch(request: pytest.FixtureRequest):
    agent = _TestingAgent(name=f"{request.function.__name__}_test_agent")
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent, branch="parent_branch"
    )

    events = [e async for e in agent.run_live(parent_ctx)]

    assert len(events) == 1
    assert events[0].author == agent.name
    assert events[0].content.parts[0].text == "Hello, live!"
    assert events[0].branch == "parent_branch"


@pytest.mark.asyncio
async def test_run_live_incomplete_agent(request: pytest.FixtureRequest):
    agent = _IncompleteAgent(name=f"{request.function.__name__}_test_agent")
    parent_ctx = await _create_parent_invocation_context(
        request.function.__name__, agent
    )

    with pytest.raises(NotImplementedError):
        [e async for e in agent.run_live(parent_ctx)]


def test_set_parent_agent_for_sub_agents(request: pytest.FixtureRequest):
    sub_agents: list[BaseAgent] = [
        _TestingAgent(name=f"{request.function.__name__}_sub_agent_1"),
        _TestingAgent(name=f"{request.function.__name__}_sub_agent_2"),
    ]
    parent = _TestingAgent(
        name=f"{request.function.__name__}_parent",
        sub_agents=sub_agents,
    )

    for sub_agent in sub_agents:
        assert sub_agent.parent_agent == parent


def test_find_agent(request: pytest.FixtureRequest):
    grand_sub_agent_1 = _TestingAgent(
        name=f"{request.function.__name__}__grand_sub_agent_1"
    )
    grand_sub_agent_2 = _TestingAgent(
        name=f"{request.function.__name__}__grand_sub_agent_2"
    )
    sub_agent_1 = _TestingAgent(
        name=f"{request.function.__name__}_sub_agent_1",
        sub_agents=[grand_sub_agent_1],
    )
    sub_agent_2 = _TestingAgent(
        name=f"{request.function.__name__}_sub_agent_2",
        sub_agents=[grand_sub_agent_2],
    )
    parent = _TestingAgent(
        name=f"{request.function.__name__}_parent",
        sub_agents=[sub_agent_1, sub_agent_2],
    )

    assert parent.find_agent(parent.name) == parent
    assert parent.find_agent(sub_agent_1.name) == sub_agent_1
    assert parent.find_agent(sub_agent_2.name) == sub_agent_2
    assert parent.find_agent(grand_sub_agent_1.name) == grand_sub_agent_1
    assert parent.find_agent(grand_sub_agent_2.name) == grand_sub_agent_2
    assert sub_agent_1.find_agent(grand_sub_agent_1.name) == grand_sub_agent_1
    assert sub_agent_1.find_agent(grand_sub_agent_2.name) is None
    assert sub_agent_2.find_agent(grand_sub_agent_1.name) is None
    assert sub_agent_2.find_agent(sub_agent_2.name) == sub_agent_2
    assert parent.find_agent("not_exist") is None


def test_find_sub_agent(request: pytest.FixtureRequest):
    grand_sub_agent_1 = _TestingAgent(
        name=f"{request.function.__name__}__grand_sub_agent_1"
    )
    grand_sub_agent_2 = _TestingAgent(
        name=f"{request.function.__name__}__grand_sub_agent_2"
    )
    sub_agent_1 = _TestingAgent(
        name=f"{request.function.__name__}_sub_agent_1",
        sub_agents=[grand_sub_agent_1],
    )
    sub_agent_2 = _TestingAgent(
        name=f"{request.function.__name__}_sub_agent_2",
        sub_agents=[grand_sub_agent_2],
    )
    parent = _TestingAgent(
        name=f"{request.function.__name__}_parent",
        sub_agents=[sub_agent_1, sub_agent_2],
    )

    assert parent.find_sub_agent(sub_agent_1.name) == sub_agent_1
    assert parent.find_sub_agent(sub_agent_2.name) == sub_agent_2
    assert parent.find_sub_agent(grand_sub_agent_1.name) == grand_sub_agent_1
    assert parent.find_sub_agent(grand_sub_agent_2.name) == grand_sub_agent_2
    assert sub_agent_1.find_sub_agent(grand_sub_agent_1.name) == grand_sub_agent_1
    assert sub_agent_1.find_sub_agent(grand_sub_agent_2.name) is None
    assert sub_agent_2.find_sub_agent(grand_sub_agent_1.name) is None
    assert sub_agent_2.find_sub_agent(grand_sub_agent_2.name) == grand_sub_agent_2
    assert parent.find_sub_agent(parent.name) is None
    assert parent.find_sub_agent("not_exist") is None


def test_root_agent(request: pytest.FixtureRequest):
    grand_sub_agent_1 = _TestingAgent(
        name=f"{request.function.__name__}__grand_sub_agent_1"
    )
    grand_sub_agent_2 = _TestingAgent(
        name=f"{request.function.__name__}__grand_sub_agent_2"
    )
    sub_agent_1 = _TestingAgent(
        name=f"{request.function.__name__}_sub_agent_1",
        sub_agents=[grand_sub_agent_1],
    )
    sub_agent_2 = _TestingAgent(
        name=f"{request.function.__name__}_sub_agent_2",
        sub_agents=[grand_sub_agent_2],
    )
    parent = _TestingAgent(
        name=f"{request.function.__name__}_parent",
        sub_agents=[sub_agent_1, sub_agent_2],
    )

    assert parent.root_agent == parent
    assert sub_agent_1.root_agent == parent
    assert sub_agent_2.root_agent == parent
    assert grand_sub_agent_1.root_agent == parent
    assert grand_sub_agent_2.root_agent == parent


def test_set_parent_agent_for_sub_agent_twice(
    request: pytest.FixtureRequest,
):
    sub_agent = _TestingAgent(name=f"{request.function.__name__}_sub_agent")
    _ = _TestingAgent(
        name=f"{request.function.__name__}_parent_1",
        sub_agents=[sub_agent],
    )
    with pytest.raises(ValueError):
        _ = _TestingAgent(
            name=f"{request.function.__name__}_parent_2",
            sub_agents=[sub_agent],
        )


if __name__ == "__main__":
    pytest.main([__file__])


class _TestAgentState(BaseAgentState):
    test_field: str = ""


@pytest.mark.asyncio
async def test_load_agent_state_not_resumable():
    agent = BaseAgent(name="test_agent")
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="test_app", user_id="test_user"
    )
    ctx = InvocationContext(
        invocation_id="test_invocation",
        agent=agent,
        session=session,
        session_service=session_service,
    )

    # Test case 1: resumability_config is None
    state = agent._load_agent_state(ctx, _TestAgentState)
    assert state is None

    # Test case 2: is_resumable is False
    ctx.resumability_config = ResumabilityConfig(is_resumable=False)
    state = agent._load_agent_state(ctx, _TestAgentState)
    assert state is None


@pytest.mark.asyncio
async def test_load_agent_state_with_resume():
    agent = BaseAgent(name="test_agent")
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="test_app", user_id="test_user"
    )
    ctx = InvocationContext(
        invocation_id="test_invocation",
        agent=agent,
        session=session,
        session_service=session_service,
        resumability_config=ResumabilityConfig(is_resumable=True),
    )

    # Test case 1: agent state not in context
    state = agent._load_agent_state(ctx, _TestAgentState)
    assert state is None

    # Test case 2: agent state in context
    persisted_state = _TestAgentState(test_field="resumed")
    ctx.agent_states[agent.name] = persisted_state.model_dump(mode="json")

    state = agent._load_agent_state(ctx, _TestAgentState)
    assert state == persisted_state


@pytest.mark.asyncio
async def test_create_agent_state_event():
    agent = BaseAgent(name="test_agent")
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="test_app", user_id="test_user"
    )
    ctx = InvocationContext(
        invocation_id="test_invocation",
        agent=agent,
        session=session,
        session_service=session_service,
    )

    ctx.branch = "test_branch"

    # Test case 1: set agent state in context
    state = _TestAgentState(test_field="checkpoint")
    ctx.set_agent_state(agent.name, agent_state=state)
    event = agent._create_agent_state_event(ctx)
    assert event is not None
    assert event.invocation_id == ctx.invocation_id
    assert event.author == agent.name
    assert event.branch == "test_branch"
    assert event.actions is not None
    assert event.actions.agent_state is not None
    assert event.actions.agent_state == state.model_dump(mode="json")
    assert not event.actions.end_of_agent

    # Test case 2: set end_of_agent in context
    ctx.set_agent_state(agent.name, end_of_agent=True)
    event = agent._create_agent_state_event(ctx)
    assert event is not None
    assert event.invocation_id == ctx.invocation_id
    assert event.author == agent.name
    assert event.branch == "test_branch"
    assert event.actions is not None
    assert event.actions.end_of_agent
    assert event.actions.agent_state is None

    # Test case 3: reset agent state and end_of_agent in context
    ctx.set_agent_state(agent.name)
    event = agent._create_agent_state_event(ctx)
    assert event is not None
    assert event.actions.agent_state is None
    assert not event.actions.end_of_agent
