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

"""Default local sessions must survive reconstruction without losing sources."""

import copy
import json
import stat

import pytest
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.sessions import DatabaseSessionService, InMemorySessionService
from google.genai import types
from litellm import ModelResponse

from veadk import Agent, Runner
from veadk.context.references import saved_references
from veadk.context.runtime import ContextScope
from veadk.context.tool_results import READ_CONTEXT_TOOL
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.models.retrying_lite_llm import RetryingLiteLlm


class SourceClient(LiteLLMClient):
    def __init__(self, reference=None):
        self.reference = reference
        self.requests = []

    async def acompletion(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        tools = [m for m in kwargs["messages"] if m["role"] == "tool"]
        if self.reference:
            if len(self.requests) == 1:
                message = self.call(
                    READ_CONTEXT_TOOL,
                    {
                        "operation": "read",
                        "reference": self.reference,
                        "query": "TAIL_ID=8921",
                    },
                    "reloaded-read",
                )
            else:
                assert "TAIL_ID=8921" in json.loads(tools[-1]["content"])["text"]
                message = {"role": "assistant", "content": "TAIL_ID=8921"}
        elif not tools:
            message = self.call("fetch_report", {}, "fetch-original")
        else:
            preview = json.loads(tools[-1]["content"])["result"]
            assert "Preview only" in preview
            self.reference = preview.split("reference='")[1].split("'")[0]
            assert "TAIL_ID=8921" not in preview
            message = {"role": "assistant", "content": "Report saved"}
        return ModelResponse(
            model="openai/context-test", choices=[{"message": message}]
        )

    @staticmethod
    def call(name, arguments, identifier):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": identifier,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        }


def make_agent(client=None, tools=(), memory=None):
    return Agent(
        name="persistent_agent",
        model_api_key="offline-test",
        model=RetryingLiteLlm(
            model="openai/context-test",
            llm_client=client or SourceClient(),
            context_compression={
                "context_window": 24000,
                "output_reserve": 2000,
                "safety_margin": 256,
                "tool_result_max_bytes": 4000,
                "retrieval_max_bytes": 2000,
            },
        ),
        tools=list(tools),
        short_term_memory=memory,
    )


async def invoke(runner, question):
    return [
        event
        async for event in runner.run_async(
            user_id="owner",
            session_id="session",
            new_message=types.Content(role="user", parts=[types.Part(text=question)]),
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("hybrid_enabled", [False, True])
async def test_default_runner_preserves_original_and_reference_after_recreation(
    tmp_path, monkeypatch, hybrid_enabled
):
    from veadk.context import defaults
    from test_hybrid_index import FakeEmbedding

    embedding = FakeEmbedding()
    monkeypatch.setattr(
        defaults, "create_embedder", lambda *_: embedding if hybrid_enabled else None
    )
    monkeypatch.chdir(tmp_path)
    executions = 0
    original = "prefix " * 5000 + "TAIL_ID=8921" + " suffix" * 5000

    def fetch_report() -> str:
        """Read an immutable report."""
        nonlocal executions
        executions += 1
        return original

    first = SourceClient()
    runner = Runner(agent=make_agent(first, [fetch_report]), app_name="project")
    service = runner.session_service
    identity = dict(app_name="project", user_id="owner", session_id="session")
    await service.create_session(**identity)
    try:
        await invoke(runner, "Save the report")
        saved = await service.get_session(**identity)
        originals = [e.model_dump(mode="json") for e in saved.events]
        assert first.reference
        assert bool(embedding.calls) == hybrid_enabled
    finally:
        if isinstance(service, DatabaseSessionService):
            await service.close()

    second = SourceClient(first.reference)
    runner = Runner(agent=make_agent(second, [fetch_report]), app_name="project")
    service = runner.session_service
    try:
        restored = await service.get_session(**identity)
        assert restored is not None, (
            "Default Runner lost the saved Session after reconstruction"
        )
        assert [e.model_dump(mode="json") for e in restored.events] == originals
        assert first.reference in saved_references(
            ContextScope(
                session=restored,
                agent_name="persistent_agent",
                branch="",
            )
        )
        events = await invoke(runner, "Read the tail identifier from the saved report")
        assert any(
            p.text == "TAIL_ID=8921"
            for e in events
            if e.content
            for p in e.content.parts
        )
        after = await service.get_session(**identity)
        values = [
            p.function_response.response["result"]
            for e in after.events
            if e.content
            for p in e.content.parts
            if p.function_response and p.function_response.name == "fetch_report"
        ]
        assert values == [original] and executions == 1
        for field, value in (
            ("user_id", "other-user"),
            ("session_id", "other-session"),
            ("app_name", "other-app"),
        ):
            assert await service.get_session(**(identity | {field: value})) is None
        assert (
            max(
                len(json.dumps(r["messages"])) for r in first.requests + second.requests
            )
            < 24000
        )
    finally:
        if isinstance(service, DatabaseSessionService):
            await service.close()


@pytest.mark.asyncio
async def test_default_sqlite_creates_private_project_database(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = Runner(agent=make_agent())
    try:
        assert isinstance(runner.session_service, DatabaseSessionService)
        database = tmp_path / ".adk/session.db"
        assert database.is_file()
        assert stat.S_IMODE(database.stat().st_mode) == 0o600
        assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
    finally:
        if isinstance(runner.session_service, DatabaseSessionService):
            await runner.session_service.close()


@pytest.mark.parametrize(
    "selection",
    ["runner-memory", "agent-memory", "external-service", "external-over-memory"],
)
def test_explicit_session_choice_does_not_create_default_database(
    tmp_path, monkeypatch, selection
):
    monkeypatch.chdir(tmp_path)
    memory = ShortTermMemory(backend="local")
    external = InMemorySessionService()
    agent = make_agent(
        memory=memory if selection in {"agent-memory", "external-over-memory"} else None
    )
    kwargs = {"short_term_memory": memory} if selection == "runner-memory" else {}
    if selection in {"external-service", "external-over-memory"}:
        kwargs["session_service"] = external
    runner = Runner(agent=agent, **kwargs)
    expected = external if "external" in selection else memory.session_service
    assert runner.session_service is expected
    assert not (tmp_path / ".adk").exists()


def test_unavailable_default_storage_fails_without_memory_fallback(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".adk").write_text("occupied")
    with pytest.raises(OSError):
        Runner(agent=make_agent())
    assert (tmp_path / ".adk").read_text() == "occupied"
