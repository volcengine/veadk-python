"""Exercise generated Agents through Studio's real ADK server and SQLite."""

import inspect
import json
import re
import runpy
import sys

import httpx
import pytest
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLLMClient
from google.genai import types
from litellm import ModelResponse

from veadk.cli.generated_agent_codegen import AgentDraft, generate_project_from_draft
from veadk.cli.generated_agent_test_runner import _find_adk_server
from veadk.context.budget import check_payload
from veadk.context.runtime import is_summary
from veadk.context.tool_results import READ_CONTEXT_TOOL
from veadk.models.retrying_lite_llm import RetryingLiteLlm


class ArchiveClient(LiteLLMClient):
    def __init__(self, marker, policy):
        self.marker = marker
        self.policy = policy
        self.calls = 0
        self.reference = None
        self.page = None

    async def acompletion(self, **kwargs):
        assert not is_summary.get()
        check_payload(kwargs, self.policy)
        self.calls += 1
        if self.calls == 1:
            reference = re.search(r"ctx_[a-f0-9]{24}", json.dumps(kwargs["messages"]))
            assert reference is not None
            self.reference = reference[0]
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "read-" + self.marker,
                        "type": "function",
                        "function": {
                            "name": READ_CONTEXT_TOOL,
                            "arguments": json.dumps(
                                {
                                    "reference": self.reference,
                                    "query": self.marker,
                                }
                            ),
                        },
                    }
                ],
            }
        else:
            assert self.calls == 2
            self.page = json.loads(
                next(
                    m["content"]
                    for m in kwargs["messages"]
                    if m.get("tool_call_id") == "read-" + self.marker
                )
            )
            assert "error" not in self.page and self.marker in self.page["text"]
            assert not self.page.get("archived")
            message = {"role": "assistant", "content": "Recovered " + self.marker}
        return ModelResponse(model=kwargs["model"], choices=[{"message": message}])


async def close_server(server):
    for runner in server.runner_dict.values():
        await runner.close()
    service = server.session_service
    # ADK's per-Agent router has no close() on some versions; close its engines.
    services = getattr(service, "_services", {"single": service}).values()
    for item in services:
        close = getattr(item, "close", None)
        if close:
            result = close()
            if inspect.isawaitable(result):
                await result


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_sqlite", [False, True])
async def test_generated_studio_agent_recovers_original_after_server_recreation(
    tmp_path,
    monkeypatch,
    explicit_sqlite,
):
    from google.adk.cli.fast_api import get_fast_api_app

    name = "studio_sqlite_contract"
    project = generate_project_from_draft(
        AgentDraft.model_validate(
            {
                "name": name,
                "contextCompression": {
                    "mode": "auto",
                    "context_window": 64000,
                    "input_limit": 16000,
                    "output_reserve": 1024,
                },
            }
        )
    )
    for file in project.files:
        path = tmp_path / file.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file.content)
    agent_file = next(
        tmp_path / f.path for f in project.files if f.path.endswith("/agent.py")
    )
    agents_root = agent_file.parent.parent
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.syspath_prepend(str(agents_root))
    original_path = list(sys.path)
    # Avoid sharing generated modules with another server or parameterized test.
    for module in (name, name + ".agent"):
        monkeypatch.delitem(sys.modules, module, raising=False)

    source = "".join(
        f"Archive line {i:04d}: preserved fact number {i}.\n" for i in range(2400)
    )
    identity = {"app_name": name, "user_id": "synthetic", "session_id": "stable"}
    original_events = None
    first_reference = None
    source_event = None
    kwargs = {"agents_dir": str(agents_root), "web": False}
    if explicit_sqlite:
        kwargs["session_service_uri"] = "sqlite+aiosqlite:///" + str(
            tmp_path / "explicit.sqlite"
        )

    def fetch_archive() -> str:
        """Fetch archive only when a new business read is requested."""
        raise AssertionError(
            "Recovering a reference must not re-execute a business tool"
        )

    try:
        for round_index, marker in enumerate(
            ("Archive line 0700:", "Archive line 1900:")
        ):
            # Both the generated Agent and FastAPI/session-service instances are new.
            root_agent = runpy.run_path(str(agent_file))["root_agent"]
            client = ArchiveClient(marker, root_agent.context_compression)
            root_agent.model = RetryingLiteLlm(
                model="openai/context-test",
                api_key="offline-test",
                llm_client=client,
                context_compression=root_agent.context_compression,
            )
            root_agent.tools = [fetch_archive]
            app = get_fast_api_app(**kwargs)
            server = _find_adk_server(app)
            assert server is not None
            # Use the actual server Runner factory with the freshly generated Agent.
            monkeypatch.setattr(
                server.agent_loader, "load_agent", lambda _, agent=root_agent: agent
            )
            service = server.session_service
            try:
                if round_index == 0:
                    session = await service.create_session(**identity)
                    contents = [
                        types.Content(
                            role="user", parts=[types.Part(text="Load archive.")]
                        ),
                        types.Content(
                            role="model",
                            parts=[
                                types.Part(
                                    function_call=types.FunctionCall(
                                        name="fetch_archive",
                                        id="business-read",
                                        args={},
                                    )
                                )
                            ],
                        ),
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(
                                    function_response=types.FunctionResponse(
                                        name="fetch_archive",
                                        id="business-read",
                                        response={"result": source},
                                    )
                                )
                            ],
                        ),
                    ]
                    for i, content in enumerate(contents):
                        await service.append_event(
                            session,
                            Event(
                                id=f"original-{i}",
                                invocation_id="seed",
                                timestamp=1700000000 + i,
                                author="user" if i == 0 else root_agent.name,
                                content=content,
                            ),
                        )
                    session = await service.get_session(**identity)
                    original_events = [e.model_dump() for e in session.events]
                    source_event = session.events[-1].id
                else:
                    session = await service.get_session(**identity)
                    assert session is not None
                    assert [
                        e.model_dump() for e in session.events[:3]
                    ] == original_events
                    assert session.state  # Includes the persisted reference catalog.
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as http:
                    response = await http.post(
                        "/run",
                        json={
                            "appName": name,
                            "userId": identity["user_id"],
                            "sessionId": identity["session_id"],
                            "newMessage": {
                                "role": "user",
                                "parts": [{"text": "Find " + marker}],
                            },
                        },
                    )
                assert response.status_code == 200
                assert client.calls == 2 and client.page is not None
                assert (
                    client.page["text"]
                    == source[client.page["offset"] : client.page["end"]]
                )
                if round_index == 0:
                    first_reference = client.reference
                else:
                    assert client.reference == first_reference
                saved = await service.get_session(**identity)
                original = next(e for e in saved.events if e.id == source_event)
                assert (
                    original.content.parts[0].function_response.response["result"]
                    == source
                )
                assert [e.model_dump() for e in saved.events[:3]] == original_events
                assert (
                    await service.get_session(**{**identity, "user_id": "another-user"})
                    is None
                )
                assert (
                    await service.get_session(
                        **{**identity, "session_id": "another-session"}
                    )
                    is None
                )
                assert list(tmp_path.rglob("*.db")) or list(tmp_path.rglob("*.sqlite"))
            finally:
                await close_server(server)
    finally:
        sys.path[:] = original_path
