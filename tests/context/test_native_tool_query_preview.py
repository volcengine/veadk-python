"""Exercise query clues at the real Runner boundary and across SQLite reloads."""

import asyncio
import copy

import pytest
from test_native_tool_lookup_preview import run_case
from veadk.context.client import BudgetedLiteLLMClient
from veadk.context.runtime import current_scope


@pytest.mark.asyncio
@pytest.mark.parametrize("source_format", ["string", "mcp"])
@pytest.mark.parametrize("sessions", [1, 2])
async def test_native_query_clues_survive_source_binding_and_sqlite_reload(
    tmp_path, source_format, sessions, monkeypatch
):
    normal = {f"s-{i}": [] for i in range(sessions)}
    actual_client = BudgetedLiteLLMClient.acompletion

    async def capture(self, model, messages, tools=None, **kwargs):
        scope = current_scope.get()
        normal[scope.session.id].append(copy.deepcopy(messages))
        budget = (scope.retrieval_headroom, scope.retrieval_read_bytes)
        response = await actual_client(self, model, messages, tools, **kwargs)
        assert current_scope.get() is scope
        assert (scope.retrieval_headroom, scope.retrieval_read_bytes) == budget
        return response

    monkeypatch.setattr(BudgetedLiteLLMClient, "acompletion", capture)
    arrived = 0
    ready = asyncio.Event()

    async def checkpoint():
        nonlocal arrived
        arrived += 1
        if arrived == sessions:
            ready.set()
        await ready.wait()

    await asyncio.gather(
        *(
            run_case(
                tmp_path,
                source_format,
                label,
                normal[label],
                checkpoint,
                question_clues=True,
            )
            for label in normal
        )
    )
