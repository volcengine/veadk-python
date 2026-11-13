"""Real ADK + stdio + Ark adapter; only cloud and model HTTP are simulated."""

import copy

import pytest
from google.adk.models import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from test_toolset import toolset
from veadk.models.ark_llm import ArkLlm, request_reorganization_by_ark


@pytest.mark.asyncio
async def test_expired_model_response_uses_original_ark_retry_without_cua_history(
    monkeypatch,
):
    import httpx
    from google.adk.agents import Agent
    from volcenginesdkarkruntime._exceptions import ArkBadRequestError

    async def run_case(use_cua):
        requests = []

        async def fake_generate(self, args, stream=False):
            requests.append(copy.deepcopy(args))
            if len(requests) == 2:
                request = httpx.Request("POST", "https://model.example.test/responses")
                raise ArkBadRequestError(
                    "expired",
                    response=httpx.Response(400, request=request),
                    body={"code": "InvalidParameter.PreviousResponseNotFound"},
                    request_id="test",
                )
            yield LlmResponse(
                model_version="offline",
                content=types.Content(role="model", parts=[types.Part(text="done")]),
                interaction_id=f"resp-{len(requests)}",
            )

        monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)
        cua = toolset() if use_cua else None
        runner = InMemoryRunner(
            agent=Agent(
                name="agent",
                model=ArkLlm(model="openai/offline"),
                tools=[cua] if cua else [],
            ),
            app_name="app",
        )
        await runner.session_service.create_session(
            app_name="app", user_id="user", session_id="one"
        )
        try:
            for text in ["remember-me", "continue"]:
                _ = [
                    e
                    async for e in runner.run_async(
                        user_id="user",
                        session_id="one",
                        new_message=types.Content(
                            role="user", parts=[types.Part(text=text)]
                        ),
                    )
                ]
            assert len(requests) == 3
            assert requests[1]["previous_response_id"] == "resp-1"
            assert not requests[2].get("previous_response_id")
            if cua:
                saved = await runner.session_service.get_session(
                    app_name="app", user_id="user", session_id="one"
                )
                assert not any(k.startswith(cua.state_key) for k in saved.state)
            return requests
        finally:
            await runner.close()

    baseline = await run_case(use_cua=False)
    with_cua = await run_case(use_cua=True)
    # CUA must not augment either the normal request or the provider's retry.
    assert [r["input"] for r in with_cua] == [r["input"] for r in baseline]


@pytest.mark.asyncio
async def test_real_ark_serialization_does_not_leak_internal_markers(monkeypatch):
    from google.adk.agents import Agent
    from veadk.models.ark_llm import ArkLlmClient, ArkTypeResponse

    wire_requests = []

    async def aresponses(self, **kwargs):
        wire_requests.append(kwargs)
        return ArkTypeResponse.model_validate(
            {
                "id": f"resp-{len(wire_requests)}",
                "object": "response",
                "created_at": 1,
                "model": "provider-resolved-model-version",
                "status": "completed",
                "incomplete_details": None,
                "tools": [],
                "output": [
                    {
                        "type": "message",
                        "id": "msg",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": "done", "annotations": []}
                        ],
                    }
                ],
            }
        )

    monkeypatch.setattr(ArkLlmClient, "aresponses", aresponses)
    cua = toolset()
    runner = InMemoryRunner(
        agent=Agent(
            name="agent",
            model=ArkLlm(
                model="openai/offline", extra_body={"parallel_tool_calls": False}
            ),
            tools=[cua],
        ),
        app_name="app",
    )
    await runner.session_service.create_session(
        app_name="app", user_id="user", session_id="one"
    )
    try:
        for text in ["first", "second", "third"]:
            _ = [
                e
                async for e in runner.run_async(
                    user_id="user",
                    session_id="one",
                    new_message=types.Content(
                        role="user", parts=[types.Part(text=text)]
                    ),
                )
            ]
        assert "tools" in wire_requests[0]
        assert wire_requests[1]["previous_response_id"] == "resp-1"
        assert "tools" not in wire_requests[1]
        assert wire_requests[2]["previous_response_id"] == "resp-2"
        assert not any(k.startswith("_veadk") for w in wire_requests for k in w)
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_same_model_and_toolset_do_not_share_response_chain_between_sessions(
    monkeypatch,
):
    from google.adk.agents import Agent

    calls = []

    async def fake_generate(self, args, stream=False):
        calls.append(copy.deepcopy(args))
        yield LlmResponse(
            model_version="offline",
            interaction_id=f"resp-{len(calls)}",
            content=types.Content(role="model", parts=[types.Part(text="done")]),
        )

    monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)
    cua = toolset()
    runner = InMemoryRunner(
        agent=Agent(name="agent", model=ArkLlm(model="openai/offline"), tools=[cua]),
        app_name="app",
    )
    for session_id in ["one", "two"]:
        await runner.session_service.create_session(
            app_name="app", user_id="user", session_id=session_id
        )
    try:
        for session_id in ["one", "two", "one", "two"]:
            _ = [
                e
                async for e in runner.run_async(
                    user_id="user",
                    session_id=session_id,
                    new_message=types.Content(
                        role="user", parts=[types.Part(text=session_id)]
                    ),
                )
            ]
        assert [c.get("previous_response_id") for c in calls] == [
            None,
            None,
            "resp-1",
            "resp-2",
        ]
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_explicit_cache_disable_and_disabled_cua_preserve_original_context(
    monkeypatch,
):
    import sys
    from pathlib import Path
    from mcp import StdioServerParameters
    from google.adk.agents import Agent
    from veadk.tools.builtin_tools.computer_use import create_computer_use_toolset

    def run_code(code: str) -> str:
        """Stub existing AIO tool for model-visible catalog checks."""
        return code

    async def run_case(use_cua):
        requests = []

        async def fake_generate(self, args, stream=False):
            requests.append(copy.deepcopy(args))
            yield LlmResponse(
                model_version="offline",
                interaction_id="response",
                content=types.Content(role="model", parts=[types.Part(text="done")]),
            )

        monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)
        tools = [run_code]
        if use_cua:
            tools.append(
                create_computer_use_toolset(
                    tool_id="t-example",
                    connection_params=StdioServerParameters(
                        command=sys.executable,
                        args=[
                            str(Path(__file__).with_name("stdio_fixture.py")),
                            "--disabled",
                        ],
                    ),
                )
            )
        runner = InMemoryRunner(
            agent=Agent(
                name="agent",
                model=ArkLlm(model="openai/offline", enable_responses_cache=False),
                tools=tools,
            ),
            app_name="app",
        )
        await runner.session_service.create_session(
            app_name="app", user_id="user", session_id="one"
        )
        try:
            for text in ["original-detail", "second-turn"]:
                _ = [
                    e
                    async for e in runner.run_async(
                        user_id="user",
                        session_id="one",
                        new_message=types.Content(
                            role="user", parts=[types.Part(text=text)]
                        ),
                    )
                ]
            assert {t["name"] for t in requests[0]["tools"]} == (
                {"run_code", "ensure_sandbox"} if use_cua else {"run_code"}
            )
            assert all(not r.get("previous_response_id") for r in requests)
            return requests
        finally:
            await runner.close()

    baseline = await run_case(use_cua=False)
    with_cua = await run_case(use_cua=True)
    assert [r["input"] for r in with_cua] == [r["input"] for r in baseline]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,args",
    [("cua_screenshot", {}), ("cua_click", {"include_screenshot": True})],
)
async def test_fixed_tools_and_images_with_original_ark_cache(
    monkeypatch, tool_name, args
):
    from google.adk.agents import Agent

    requests = []

    async def fake_generate(self, response_args, stream=False):
        wire = request_reorganization_by_ark(copy.deepcopy(response_args))
        assert "parallel_tool_calls" not in wire
        assert "parallel_tool_calls" not in wire.get("extra_body", {})
        requests.append(wire)
        n = len(requests)
        yield LlmResponse(
            interaction_id=f"resp-{n}",
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            id="action", name=tool_name, args=args
                        )
                    )
                    if n == 1
                    else types.Part(text="done")
                ],
            ),
        )

    monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)
    cua = toolset()
    model = ArkLlm(model="openai/offline", extra_body={"caching": {"type": "enabled"}})
    runner = InMemoryRunner(
        agent=Agent(name="agent", model=model, tools=[cua]), app_name="app"
    )
    await runner.session_service.create_session(
        app_name="app", user_id="user", session_id="one"
    )
    try:
        for text in ["first", "next"]:
            _ = [
                e
                async for e in runner.run_async(
                    user_id="user",
                    session_id="one",
                    new_message=types.Content(
                        role="user", parts=[types.Part(text=text)]
                    ),
                )
            ]
        assert "cua_accessibility_nodes" in {t["name"] for t in requests[0]["tools"]}
        assert requests[1]["previous_response_id"] == "resp-1"
        assert "tools" not in requests[1]
        assert (
            sum(
                p.get("type") == "input_image"
                for i in requests[1]["input"]
                for p in i.get("content", [])
            )
            == 1
        )
        assert requests[2]["previous_response_id"] == "resp-2"
        assert runner.agent.model is model
        saved = await runner.session_service.get_session(
            app_name="app", user_id="user", session_id="one"
        )
        assert (
            saved.state[
                cua.binding_state_key(type("Ctx", (), {"agent_name": "agent"})())
            ]["session_id"]
            == "s-1"
        )
    finally:
        await runner.close()


def test_original_ark_parallel_parameter_behavior_is_not_silently_patched():
    # This provider limitation is not fixed by static discovery. Keep visible.
    wire = request_reorganization_by_ark(
        {
            "model": "openai/offline",
            "input": [],
            "previous_response_id": "old",
            "extra_body": {"parallel_tool_calls": False},
        }
    )
    assert wire["extra_body"]["parallel_tool_calls"] is False
