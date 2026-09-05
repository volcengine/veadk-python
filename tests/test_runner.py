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

import inspect
import os

import pytest
from google.genai import types

from veadk.agent import Agent
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.short_term_memory import ShortTermMemory

# Import the standalone function instead of accessing as class method
from veadk.runner import Runner, _convert_messages


def _test_convert_messages(runner):
    """Test message conversion logic using standalone _convert_messages function"""
    # Test single text message conversion
    message = "test message"
    expected_message = [
        types.Content(
            parts=[types.Part(text=message)],
            role="user",
        )
    ]
    # Modified: Call _convert_messages directly (not as runner method)
    actual_message = _convert_messages(
        message,
        app_name=runner.app_name,
        user_id=runner.user_id,
        session_id="test_session_id",
    )
    assert actual_message == expected_message

    # Test multiple text messages conversion
    message = ["test message 1", "test message 2"]
    expected_message = [
        types.Content(
            parts=[types.Part(text="test message 1")],
            role="user",
        ),
        types.Content(
            parts=[types.Part(text="test message 2")],
            role="user",
        ),
    ]
    # Modified: Call _convert_messages directly (not as runner method)
    actual_message = _convert_messages(
        message,
        app_name=runner.app_name,
        user_id=runner.user_id,
        session_id="test_session_id",
    )
    assert actual_message == expected_message


def test_runner():
    """Test Runner class initialization and core properties"""
    # `LongTermMemory(backend="local")` below resolves its backend class
    # lazily, and the local one imports `llama_index.core`.
    pytest.importorskip(
        "llama_index.core",
        reason=(
            "the local KnowledgeBase/LongTermMemory backends need llama-index: "
            'pip install "veadk-python[extensions]"'
        ),
    )

    os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"

    short_term_memory = ShortTermMemory()
    long_term_memory = LongTermMemory(backend="local")
    agent = Agent(
        model_name="test_model_name",
        model_provider="test_model_provider",
        model_api_key="test_model_api_key",
        model_api_base="test_model_api_base",
        long_term_memory=long_term_memory,
    )

    runner = Runner(agent=agent, short_term_memory=short_term_memory)
    assert runner.long_term_memory == agent.long_term_memory

    # Verify inherited ADKRunner properties
    assert runner.memory_service == agent.long_term_memory
    assert runner.session_service == runner.short_term_memory.session_service

    # Run message conversion tests
    _test_convert_messages(runner)


def _make_offline_runner() -> tuple[Runner, list[str]]:
    """Build a Runner whose ``run_async`` is stubbed out.

    ``Runner.run`` still executes end to end; only the LLM-backed event stream
    is replaced, so the returned list records the exact ``session_id`` that each
    run forwarded downstream.
    """
    agent = Agent(
        model_name="test_model_name",
        model_provider="test_model_provider",
        model_api_key="test_model_api_key",
        model_api_base="test_model_api_base",
    )
    runner = Runner(agent=agent, short_term_memory=ShortTermMemory())

    seen_session_ids: list[str] = []

    async def fake_run_async(*, user_id, session_id, new_message, **kwargs):
        seen_session_ids.append(session_id)
        return
        yield  # pragma: no cover - makes this a generator, never reached

    runner.run_async = fake_run_async
    return runner, seen_session_ids


def test_run_session_id_default_is_a_sentinel():
    """``session_id`` must default to ``None``, not to a call expression.

    A default such as ``f"tmp-session-{formatted_timestamp()}"`` is evaluated
    once, when the function is defined, so every run omitting ``session_id``
    would share a single id frozen at import time.
    """
    default = inspect.signature(Runner.run).parameters["session_id"].default
    assert default is None


@pytest.mark.asyncio
async def test_run_generates_a_fresh_session_id_per_call(monkeypatch):
    """Two runs that omit ``session_id`` must get different ids.

    UUID generation is patched with deterministic values so the test pins both
    per-call evaluation and the public ``tmp-session-`` prefix.
    """
    runner, seen_session_ids = _make_offline_runner()

    generated = iter(["uuid-one", "uuid-two"])
    monkeypatch.setattr(
        "veadk.runner.uuid.uuid4",
        lambda: type("UUID", (), {"hex": next(generated)})(),
    )

    await runner.run(messages="first")
    await runner.run(messages="second")

    assert seen_session_ids == ["tmp-session-uuid-one", "tmp-session-uuid-two"]


@pytest.mark.asyncio
async def test_run_uses_an_explicit_session_id_unchanged():
    """An explicitly passed ``session_id`` is forwarded verbatim."""
    runner, seen_session_ids = _make_offline_runner()

    await runner.run(messages="hi", session_id="explicit-session-id")

    assert seen_session_ids == ["explicit-session-id"]
