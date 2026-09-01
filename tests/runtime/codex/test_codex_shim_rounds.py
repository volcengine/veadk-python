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

"""Multi-round tests for the Responses shim.

These were split out of the 936-line ``test_codex_runtime.py``, whose size was
a proximate cause of the coverage gap they close: every shim test in that file
sent exactly one POST per turn with ``stream: False``, so the ~113-line
``_synth_sse`` had zero coverage and the worst bug -- tool history lost between
two requests under one token -- was a shape no test could express.

Every test here builds :class:`ResponsesShim` **directly** over
``httpx.ASGITransport``. ``get_shim`` is never called, so the process-global
``_SHIMS`` cache (and its uvicorn servers and ports) stays untouched, which is
what makes the file safe under ``pytest -n 16``.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from veadk.runtime.codex import proxy as proxy_module
from veadk.runtime.codex.proxy import ResponsesShim


@pytest.fixture(autouse=True)
def _shim_cache_is_untouched():
    """Fail loudly if a test in this file ever starts a real shim server.

    ``get_shim`` binds a port and leaks a uvicorn task into the process-global
    cache; nothing here may do that.
    """
    before = dict(proxy_module._SHIMS)
    yield
    assert dict(proxy_module._SHIMS) == before, (
        "a test in this file mutated the process-global shim cache; construct "
        "ResponsesShim directly instead of calling get_shim()"
    )


#: Distinguishes "the key is absent" from "the key is present and empty", which
#: select different branches of the shim's tool-advertisement logic.
_UNSET = object()


def _client(shim: ResponsesShim) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=shim._app), base_url="http://shim"
    )


def _message(text: str, role: str = "user") -> dict:
    return {"type": "message", "role": role, "content": [{"text": text}]}


def _text_response(text: str, response_id: str = "resp") -> dict:
    return {
        "id": response_id,
        "model": "model",
        "output": [
            {
                "id": f"msg-{response_id}",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


def _tool_response(name: str, response_id: str, call_id: str) -> dict:
    return {
        "id": response_id,
        "model": "model",
        "output": [
            {
                "id": f"fc-{response_id}",
                "call_id": call_id,
                "type": "function_call",
                "name": name,
                "arguments": "{}",
                "status": "completed",
            }
        ],
    }


def _sse_frames(body: str) -> list[tuple[str, dict]]:
    """Parse a ``text/event-stream`` body into ``(event name, data)`` pairs."""
    frames: list[tuple[str, dict]] = []
    for raw in body.split("\n\n"):
        if not raw.strip():
            continue
        name = None
        data = None
        for line in raw.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        assert name is not None, f"SSE frame without an event line: {raw!r}"
        assert data is not None, f"SSE frame without a data line: {raw!r}"
        frames.append((name, data))
    return frames


# ---------------------------------------------------- the multi-round blocker


@pytest.mark.asyncio
async def test_two_requests_under_one_token_replay_the_tool_transcript(
    monkeypatch,
) -> None:
    """The blocker: the second request must carry round one's tool pair.

    Codex rebuilds ``input`` from its own thread on every request and never saw
    the shim-executed ``function_call``/``function_call_output`` pair, because
    those are deliberately not streamed to it. Without a replay the model sees a
    conversation in which it never called the tool, and re-issues the call --
    re-running its side effects. Every previous shim test sent exactly one POST
    per turn, so this shape could not be expressed at all.
    """
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    executed: list[str] = []
    seen: list[list[dict]] = []

    async def executor(args, call_id):
        executed.append(call_id)
        return json.dumps({"ok": True})

    token = shim.register_turn(
        [{"type": "function", "name": "record", "parameters": {}}],
        {"record": executor},
    )

    async def backend(**kwargs):
        seen.append(json.loads(json.dumps(kwargs["input"])))
        has_output = any(
            item.get("type") == "function_call_output" for item in kwargs["input"]
        )
        if has_output:
            return _text_response("all done", f"final-{len(seen)}")
        return _tool_response("record", f"tool-{len(seen)}", "call-1")

    monkeypatch.setattr(proxy_module.litellm, "aresponses", backend)

    async with _client(shim) as client:
        headers = {"Authorization": f"Bearer {token}"}
        first = await client.post(
            "/v1/responses",
            headers=headers,
            json={"model": "model", "stream": False, "input": [_message("go")]},
        )
        # Codex's own second request: a fresh `input` rebuilt from its thread,
        # with no knowledge of the tool the shim ran on its behalf. Codex
        # appends its *own* items (here a native tool round) and re-sends the
        # same user message -- it does not add a new user turn. That shape
        # matters: a trailing user message is what a compaction pass looks
        # like, and the agent-turn gate rejects those on purpose.
        second = await client.post(
            "/v1/responses",
            headers=headers,
            json={
                "model": "model",
                "stream": False,
                "input": [
                    _message("go"),
                    {
                        "type": "function_call",
                        "call_id": "shell-1",
                        "name": "exec_command",
                        "arguments": "{}",
                        "status": "completed",
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "shell-1",
                        "output": "ok",
                    },
                ],
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert executed == ["call-1"], "the tool must run exactly once for the turn"

    # The replayed ADK pair must be there. Codex's own `shell-1` pair is there
    # too -- it is part of the history Codex rebuilt -- so this asserts on the
    # ADK call id rather than on the request containing nothing else.
    kinds = [
        (item.get("type"), item.get("call_id"))
        for item in seen[-1]
        if item.get("type") in ("function_call", "function_call_output")
    ]
    assert kinds.count(("function_call", "call-1")) == 1, seen[-1]
    assert kinds.count(("function_call_output", "call-1")) == 1, seen[-1]
    # Order matters to the chat bridge: each call must be immediately followed
    # by its own result, or litellm emits an `assistant(tool_calls)` with no
    # matching `tool` message and the backend rejects the request.
    call_index = kinds.index(("function_call", "call-1"))
    assert kinds[call_index + 1] == ("function_call_output", "call-1"), kinds


@pytest.mark.asyncio
async def test_turn_state_is_not_shared_across_tokens(monkeypatch) -> None:
    """One turn's tool transcript must never leak into another turn's request."""
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")

    async def executor(args, call_id):
        return json.dumps({"ok": True})

    specs = [{"type": "function", "name": "record", "parameters": {}}]
    token_a = shim.register_turn(specs, {"record": executor})
    token_b = shim.register_turn(specs, {"record": executor})
    seen: dict[str, list[list[dict]]] = {"a": [], "b": []}
    which = {"value": "a"}

    async def backend(**kwargs):
        seen[which["value"]].append(json.loads(json.dumps(kwargs["input"])))
        if any(i.get("type") == "function_call_output" for i in kwargs["input"]):
            return _text_response("done")
        return _tool_response("record", "tool", f"call-{which['value']}")

    monkeypatch.setattr(proxy_module.litellm, "aresponses", backend)

    async with _client(shim) as client:
        body = {"model": "model", "stream": False, "input": [_message("go")]}
        which["value"] = "a"
        await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token_a}"},
            json=json.loads(json.dumps(body)),
        )
        which["value"] = "b"
        await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token_b}"},
            json=json.loads(json.dumps(body)),
        )

    replayed_into_b = [
        item
        for request in seen["b"]
        for item in request
        if item.get("call_id") == "call-a"
    ]
    assert replayed_into_b == [], replayed_into_b


# ------------------------------------------------------- streamed SSE shape


@pytest.mark.asyncio
async def test_streamed_turn_emits_canonical_dense_sse_sequence(monkeypatch) -> None:
    """``stream: True`` must produce Codex's canonical event order.

    Every pre-existing shim test passed ``stream: False``, so ``_synth_sse``
    -- the ~113 lines that decide what Codex actually acts on -- had no
    coverage at all.
    """
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    token = shim.register_turn([], {})

    async def backend(**kwargs):
        return _text_response("hello there")

    monkeypatch.setattr(proxy_module.litellm, "aresponses", backend)

    async with _client(shim) as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": "model", "stream": True, "input": [_message("go")]},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    frames = _sse_frames(response.text)
    names = [name for name, _ in frames]
    assert names[0] == "response.created"
    assert names[1] == "response.in_progress"
    assert names[-1] == "response.completed"
    assert "response.output_item.added" in names
    assert "response.output_text.delta" in names
    assert "response.output_item.done" in names
    # The `event:` line must match the payload's own `type`, or Codex's parser
    # dispatches on one thing and reads another.
    assert all(name == data["type"] for name, data in frames)
    # Dense, gapless, strictly increasing: Codex rejects a stream with holes.
    assert [data["sequence_number"] for _, data in frames] == list(range(len(frames)))


@pytest.mark.asyncio
async def test_streamed_function_call_survives_synthesis(monkeypatch) -> None:
    """A dropped tool call would silently end the turn at the preamble.

    The tool call is what drives Codex's agentic loop. If ``_synth_sse`` filters
    it out, Codex sees a turn that finished after saying "let me look..." -- no
    error, no retry, just a wrong answer.
    """
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    token = shim.register_turn([], {})  # no executor: the call passes through

    async def backend(**kwargs):
        return {
            "id": "resp",
            "model": "model",
            "output": [
                {
                    "id": "msg",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "let me look..."}],
                },
                {
                    "id": "fc",
                    "call_id": "call-1",
                    "type": "function_call",
                    "name": "shell",
                    "arguments": '{"command":"ls"}',
                    "status": "completed",
                },
            ],
        }

    monkeypatch.setattr(proxy_module.litellm, "aresponses", backend)

    async with _client(shim) as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": "model", "stream": True, "input": [_message("go")]},
        )

    frames = _sse_frames(response.text)
    by_name = {name: data for name, data in frames}
    assert "response.function_call_arguments.delta" in by_name
    assert by_name["response.function_call_arguments.done"]["arguments"] == (
        '{"command":"ls"}'
    )
    done_items = [data["item"] for name, data in frames if name.endswith("item.done")]
    assert [item["type"] for item in done_items] == ["message", "function_call"]
    assert done_items[1]["name"] == "shell"


@pytest.mark.asyncio
async def test_streamed_reasoning_summary_events_are_emitted(monkeypatch) -> None:
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    token = shim.register_turn([], {})

    async def backend(**kwargs):
        return {
            "id": "resp",
            "model": "model",
            "output": [
                {
                    "id": "rs",
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "thinking"}],
                },
                {
                    "id": "msg",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "answer"}],
                },
            ],
        }

    monkeypatch.setattr(proxy_module.litellm, "aresponses", backend)

    async with _client(shim) as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": "model", "stream": True, "input": [_message("go")]},
        )

    names = [name for name, _ in _sse_frames(response.text)]
    assert "response.reasoning_summary_part.added" in names
    assert "response.reasoning_summary_text.delta" in names
    assert "response.reasoning_summary_text.done" in names
    assert "response.reasoning_summary_part.done" in names


@pytest.mark.asyncio
async def test_response_completed_output_equals_the_streamed_items(
    monkeypatch,
) -> None:
    """Pins the silent trimming: the terminal payload must match what streamed.

    ``_synth_sse`` streams only ``message``/``reasoning``/``function_call``
    items and rewrites ``response.completed.output`` to match. If the two ever
    disagree, Codex's reconciliation sees items it never received (or loses ones
    it did) with no error anywhere.
    """
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    token = shim.register_turn([], {})

    async def backend(**kwargs):
        return {
            "id": "resp",
            "model": "model",
            "output": [
                {
                    "id": "msg",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "answer"}],
                },
                # Not one of the streamed kinds: must be trimmed from both.
                {"id": "misc", "type": "web_search_call", "status": "completed"},
            ],
        }

    monkeypatch.setattr(proxy_module.litellm, "aresponses", backend)

    async with _client(shim) as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": "model", "stream": True, "input": [_message("go")]},
        )

    frames = _sse_frames(response.text)
    streamed = [data["item"] for name, data in frames if name.endswith("item.done")]
    completed = frames[-1][1]["response"]
    assert frames[-1][0] == "response.completed"
    assert completed["status"] == "completed"
    assert completed["output"] == streamed
    assert [item["type"] for item in completed["output"]] == ["message"]


# ------------------------------------------------------ Ark status backfill


@pytest.mark.asyncio
async def test_assistant_messages_are_backfilled_with_a_status(monkeypatch) -> None:
    """Ark's Responses API rejects an assistant message with no ``status``.

    Codex replays prior assistant messages without one, so a turn with a model
    preamble followed by a tool call used to die on ``MissingParameter:
    input.status``. This path had zero tests.
    """
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    token = shim.register_turn([], {})
    seen: list[list[dict]] = []

    async def backend(**kwargs):
        seen.append(json.loads(json.dumps(kwargs["input"])))
        return _text_response("ok")

    monkeypatch.setattr(proxy_module.litellm, "aresponses", backend)

    async with _client(shim) as client:
        await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": "model",
                "stream": False,
                "input": [
                    _message("go"),
                    _message("let me look...", role="assistant"),
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "incomplete",
                        "content": [{"text": "partially done"}],
                    },
                ],
            },
        )

    forwarded = seen[0]
    assert forwarded[1]["status"] == "completed", "missing status was not backfilled"
    assert forwarded[2]["status"] == "incomplete", "an explicit status was overwritten"
    assert "status" not in forwarded[0], "a user message must not be given a status"


@pytest.mark.asyncio
async def test_shim_routes_concurrent_turns_to_their_own_executors(
    monkeypatch,
) -> None:
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    calls: list[tuple[str, str]] = []

    async def executor_a(args, call_id):
        await asyncio.sleep(0.01)
        calls.append(("a", call_id))
        return json.dumps({"owner": "a"})

    async def executor_b(args, call_id):
        calls.append(("b", call_id))
        return json.dumps({"owner": "b"})

    token_a = shim.register_turn(
        [{"type": "function", "name": "tool_a", "parameters": {}}],
        {"tool_a": executor_a},
    )
    token_b = shim.register_turn(
        [{"type": "function", "name": "tool_b", "parameters": {}}],
        {"tool_b": executor_b},
    )

    async def fake_aresponses(**kwargs):
        conversation = kwargs["input"]
        if any(item.get("type") == "function_call_output" for item in conversation):
            return {
                "id": "resp-final",
                "model": "model",
                "output": [
                    {
                        "id": "msg",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ],
            }
        tool = next(
            item for item in kwargs["tools"] if item["name"] in {"tool_a", "tool_b"}
        )
        suffix = tool["name"][-1]
        return {
            "id": f"resp-{suffix}",
            "model": "model",
            "output": [
                {
                    "id": f"fc-{suffix}",
                    "call_id": f"call-{suffix}",
                    "type": "function_call",
                    "name": tool["name"],
                    "arguments": "{}",
                    "status": "completed",
                }
            ],
        }

    monkeypatch.setattr("veadk.runtime.codex.proxy.litellm.aresponses", fake_aresponses)
    transport = httpx.ASGITransport(app=shim._app)
    async with httpx.AsyncClient(transport=transport, base_url="http://shim") as client:
        body = {
            "model": "model",
            "stream": False,
            "input": [{"type": "message", "role": "user", "content": "go"}],
        }
        response_a, response_b = await asyncio.gather(
            client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {token_a}"},
                json=body,
            ),
            client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {token_b}"},
                json=body,
            ),
        )

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert sorted(calls) == [("a", "call-a"), ("b", "call-b")]


@pytest.mark.asyncio
async def test_shim_rejects_unknown_invocation_token() -> None:
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    transport = httpx.ASGITransport(app=shim._app)
    async with httpx.AsyncClient(transport=transport, base_url="http://shim") as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": "Bearer unknown"},
            json={"model": "model", "input": []},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_shim_reports_tool_iteration_budget_instead_of_dropping_call(
    monkeypatch,
) -> None:
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")

    async def executor(args, call_id):
        return "{}"

    token = shim.register_turn(
        [{"type": "function", "name": "loop", "parameters": {}}],
        {"loop": executor},
        max_tool_iterations=1,
    )

    async def always_calls_tool(**kwargs):
        return {
            "id": "resp",
            "model": "model",
            "output": [
                {
                    "id": "fc",
                    "call_id": "call-loop",
                    "type": "function_call",
                    "name": "loop",
                    "arguments": "{}",
                    "status": "completed",
                }
            ],
        }

    monkeypatch.setattr(
        "veadk.runtime.codex.proxy.litellm.aresponses", always_calls_tool
    )
    transport = httpx.ASGITransport(app=shim._app)
    async with httpx.AsyncClient(transport=transport, base_url="http://shim") as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": "model",
                "input": [{"type": "message", "role": "user", "content": "go"}],
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["type"] == "tool_iteration_limit"


@pytest.mark.asyncio
async def test_shim_rejects_invalid_tool_json_without_calling_executor(
    monkeypatch,
) -> None:
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    called = False

    async def executor(args, call_id):
        nonlocal called
        called = True
        return "{}"

    token = shim.register_turn(
        [{"type": "function", "name": "parse", "parameters": {}}],
        {"parse": executor},
    )

    async def fake_aresponses(**kwargs):
        if any(item.get("type") == "function_call_output" for item in kwargs["input"]):
            return {
                "id": "final",
                "model": "model",
                "output": [
                    {
                        "id": "msg",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "handled"}],
                    }
                ],
            }
        return {
            "id": "tool",
            "model": "model",
            "output": [
                {
                    "id": "fc",
                    "call_id": "call-invalid",
                    "type": "function_call",
                    "name": "parse",
                    "arguments": "{not-json",
                    "status": "completed",
                }
            ],
        }

    monkeypatch.setattr("veadk.runtime.codex.proxy.litellm.aresponses", fake_aresponses)
    transport = httpx.ASGITransport(app=shim._app)
    async with httpx.AsyncClient(transport=transport, base_url="http://shim") as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": "model", "input": []},
        )

    assert response.status_code == 200
    assert called is False


@pytest.mark.asyncio
async def test_shim_returns_the_turn_total_token_usage(monkeypatch) -> None:
    """The shim's internal tool loop must not throw away tokens it spent.

    Codex sees exactly one request per turn here: the shim executes the agent's
    tools itself and returns only the final, tool-free response. Every
    intermediate backend response -- and the ``usage`` block it carries -- is
    discarded, so the tokens the tool rounds cost never reach Codex, and
    therefore never reach ``usage_metadata``, the ``call_llm`` span, portal
    metrics or the frontend token counter. The turn silently under-reports.

    ``tests/runtime/differential/test_runtime_parity.py::…[usage_accounting]``
    is the same gap observed end to end: ADK reports 18/8, Codex reports 7/3.
    """
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")

    async def executor(args, call_id):
        return json.dumps({"ok": True})

    token = shim.register_turn(
        [{"type": "function", "name": "record", "parameters": {}}],
        {"record": executor},
    )
    rounds = iter(
        [
            {
                **_tool_response("record", "tool", "call-1"),
                "usage": {"input_tokens": 11, "output_tokens": 5, "total_tokens": 16},
            },
            {
                **_text_response("all done"),
                "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
            },
        ]
    )

    async def backend(**kwargs):
        return next(rounds)

    monkeypatch.setattr(proxy_module.litellm, "aresponses", backend)

    async with _client(shim) as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": "model", "stream": False, "input": [_message("go")]},
        )

    usage = response.json().get("usage") or {}
    assert (
        usage.get("input_tokens") == 18
    ), f"the tool round's 11 input tokens were dropped: {usage}"
    assert (
        usage.get("output_tokens") == 8
    ), f"the tool round's 5 output tokens were dropped: {usage}"
    assert usage.get("total_tokens") == 26, usage


# ------------------------------------------- compaction / review contamination
#
# Codex reuses one provider block -- and therefore one bearer token -- for work
# that is not the agent turn. Verified against the Codex source at
# `codex-rs/core/src/compact.rs::run_compact_task_inner_impl`, which builds its
# prompt with an empty `tools` list and sends it through `turn_context.provider`,
# and `codex-rs/core/src/session/review.rs::spawn_review_thread`, which clones
# the parent turn's provider (and `runtime.py` points `review_model` at the same
# model, so there is exactly one provider block).
#
# The shim must not treat those requests as the agent turn: advertising the
# agent's ADK tools to a summarizer, or replaying the turn's tool transcript
# into it, invites a `function_call` in the reply -- and the shim would then
# execute the real tool a second time, the same duplicated side effect the
# multi-round blocker above is about.


def _compaction_body(*, tools: object = _UNSET) -> dict:
    """A request shaped like Codex's compaction pass, not like an agent turn.

    ``tools`` defaults to being absent entirely (the `elif turn_context.specs`
    branch); pass ``[]`` for the shape `compact.rs` actually sends (the
    `isinstance(tools, list)` branch).
    """
    body = {
        "model": "model",
        "stream": False,
        "instructions": "You are summarizing a conversation.",
        "input": [
            _message("Earlier we discussed the deployment."),
            _message("Summarize the conversation so far.", role="user"),
        ],
        "store": False,
    }
    if tools is not _UNSET:
        body["tools"] = tools
    return body


async def _register_turn_with_history(shim, executed, monkeypatch):
    """Run one real agent round so the turn has a tool transcript to leak."""

    async def executor(args, call_id):
        executed.append(call_id)
        return json.dumps({"ok": True})

    token = shim.register_turn(
        [
            {
                "type": "function",
                "name": "record_fact",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        {"record_fact": executor},
    )

    rounds = iter(
        [
            _tool_response("record_fact", "resp-1", "call-1"),
            _text_response("done", "resp-2"),
        ]
    )

    async def backend(**kwargs):
        return next(rounds)

    monkeypatch.setattr(proxy_module.litellm, "aresponses", backend)
    async with _client(shim) as client:
        await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": "model", "stream": False, "input": [_message("go")]},
        )
    assert executed == ["call-1"], "setup failed: the agent round ran no tool"
    return token


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tools", "shape"),
    [
        pytest.param([], "empty-list", id="tools_empty_list"),
        pytest.param(_UNSET, "absent", id="tools_absent"),
    ],
)
async def test_compaction_request_gets_no_adk_tools_and_no_transcript_replay(
    monkeypatch, tools, shape
) -> None:
    """A non-agent-turn request on a live token must be left alone.

    Both shim branches fire on this shape today: ``tools: []`` hits the
    ``isinstance(tools, list)`` branch and an absent ``tools`` hits the
    ``elif turn_context.specs`` branch, so compaction is handed the agent's ADK
    tools either way, plus the turn's ``function_call``/``function_call_output``
    pair.
    """
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    executed: list[str] = []
    token = await _register_turn_with_history(shim, executed, monkeypatch)

    seen: list[dict] = []

    async def backend(**kwargs):
        seen.append(kwargs)
        return _text_response("a summary", "resp-compact")

    monkeypatch.setattr(proxy_module.litellm, "aresponses", backend)

    async with _client(shim) as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json=_compaction_body(tools=tools),
        )

    assert response.status_code == 200, response.text
    assert len(seen) == 1, seen
    sent = seen[0]

    advertised = {
        t.get("name") for t in (sent.get("tools") or []) if isinstance(t, dict)
    }
    assert "record_fact" not in advertised, (
        f"the agent's ADK tool was advertised to a compaction pass ({shape} "
        f"tools): {sent.get('tools')!r}. The summarizer can now emit a "
        "function_call for it, which the shim would execute for real."
    )

    replayed = [
        item
        for item in (sent.get("input") or [])
        if isinstance(item, dict)
        and item.get("type") in ("function_call", "function_call_output")
    ]
    assert replayed == [], (
        f"the agent turn's tool transcript leaked into a compaction pass "
        f"({shape} tools): {replayed!r}"
    )


@pytest.mark.asyncio
async def test_compaction_request_never_executes_an_adk_tool(monkeypatch) -> None:
    """The consequence, asserted directly: no second side effect.

    Even if the summarizer's reply contains a ``function_call`` naming an ADK
    tool, the shim must not run it. This is the assertion that would have caught
    the bug regardless of how tool advertisement is gated.
    """
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    executed: list[str] = []
    token = await _register_turn_with_history(shim, executed, monkeypatch)
    assert executed == ["call-1"]

    calls = 0

    async def backend(**kwargs):
        nonlocal calls
        calls += 1
        # A summarizer that (however unwisely) asks for the agent's tool.
        if calls == 1:
            return _tool_response("record_fact", "resp-compact", "call-compact")
        return _text_response("a summary", "resp-compact-2")

    monkeypatch.setattr(proxy_module.litellm, "aresponses", backend)

    async with _client(shim) as client:
        await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json=_compaction_body(tools=[]),
        )

    assert executed == ["call-1"], (
        "a compaction pass re-executed the agent's tool: the real side effect "
        f"ran twice (call ids: {executed})"
    )


@pytest.mark.asyncio
async def test_degraded_gate_rejects_a_compaction_shaped_request(monkeypatch) -> None:
    """The marker-less fallback must still fail closed on a compaction pass.

    When the turn marker never reaches the model request, the gate falls back to
    matching the first request's user texts. Matching *any* remembered text
    would admit compaction, which re-sends the whole history and therefore
    always carries the turn's opening message -- and a summarizer that emits a
    ``function_call`` would run a real ADK tool a second time. Only the *last*
    user message is anchored, so compaction's appended instruction fails it.
    """
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    executed: list[str] = []
    seen: list[dict] = []

    async def executor(args, call_id):
        executed.append(call_id)
        return json.dumps({"ok": True})

    token = shim.register_turn(
        [{"type": "function", "name": "record", "parameters": {}}],
        {"record": executor},
    )

    async def backend(**kwargs):
        seen.append(json.loads(json.dumps(kwargs)))
        return _text_response("summary", f"resp-{len(seen)}")

    monkeypatch.setattr(proxy_module.litellm, "aresponses", backend)

    async with _client(shim) as client:
        headers = {"Authorization": f"Bearer {token}"}
        # First request establishes the anchors (no marker: degraded path).
        await client.post(
            "/v1/responses",
            headers=headers,
            json={"model": "model", "stream": False, "input": [_message("go")]},
        )
        # Compaction: whole history re-sent, a summarization instruction
        # appended as a trailing user message, and an empty tools list.
        await client.post(
            "/v1/responses",
            headers=headers,
            json={
                "model": "model",
                "stream": False,
                "tools": [],
                "input": [_message("go"), _message("Summarize the conversation.")],
            },
        )

    assert executed == [], "no ADK tool may run for a compaction pass"
    compaction = seen[-1]
    assert not compaction.get("tools"), (
        "the agent's ADK tools must not be advertised to the summarizer, or it "
        f"can call them: {compaction.get('tools')!r}"
    )
    replayed = [
        item
        for item in compaction["input"]
        if item.get("type") in ("function_call", "function_call_output")
    ]
    assert replayed == [], f"tool transcript leaked into compaction: {replayed}"
