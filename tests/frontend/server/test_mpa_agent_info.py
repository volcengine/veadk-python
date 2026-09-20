import httpx
import pytest

from frontend.server.mpa_agent_info import load_mpa_agent_info


def card(nodes=None, edges=None):
    return {
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:veadk:mpa:resource-topology:v1",
                    "params": {"nodes": nodes or [], "edges": edges or []},
                }
            ]
        }
    }


async def load(monkeypatch, response, topology=None):
    original = httpx.AsyncClient

    def handler(request):
        assert request.url == "https://runtime.example/api/v1/agents"
        assert request.headers["Authorization"] == "Bearer example"
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(handler)),
    )
    return await load_mpa_agent_info(
        "https://runtime.example",
        {"Authorization": "Bearer example"},
        topology,
        "cn-shanghai",
    )


@pytest.mark.asyncio
async def test_real_document_and_only_bound_spaces_are_exposed(monkeypatch):
    topology = card(
        [
            {"id": "agent", "kind": "agent"},
            {
                "id": "bound",
                "kind": "skill-space",
                "status": "configured",
                "resourceId": "space-1",
            },
            {
                "id": "other",
                "kind": "skill-space",
                "status": "configured",
                "resourceId": "space-2",
            },
        ],
        [{"source": "agent", "target": "bound", "relation": "mounts"}],
    )
    result = await load(
        monkeypatch,
        httpx.Response(
            200,
            json={
                "agentsMd": "# Instructions\n\nKeep spacing.\n",
                "name": "MPA",
                "metadata": {"credential": "must-not-be-exposed"},
                "skills": [{"name": "obsolete"}],
            },
        ),
        topology,
    )
    assert result["agentsMd"] == "# Instructions\n\nKeep spacing.\n"
    assert result["agentsMdStatus"] == "ready"
    assert result["skillSpacesStatus"] == "ready"
    assert result["skillSpaces"] == [{"id": "space-1", "region": "cn-shanghai"}]
    assert "must-not-be-exposed" not in str(result)
    assert "obsolete" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,state",
    [(401, "forbidden"), (403, "forbidden"), (404, "unsupported"), (500, "error")],
)
async def test_upstream_failures_are_not_empty_success(monkeypatch, status, state):
    result = await load(
        monkeypatch,
        httpx.Response(status, json={"detail": "private upstream error"}),
        card(),
    )
    assert result["agentsMdStatus"] == state
    assert result["agentsMd"] is None
    assert "private upstream" not in str(result)
    assert result["skillSpacesStatus"] == "ready"


@pytest.mark.asyncio
async def test_absent_topology_is_not_empty_binding(monkeypatch):
    result = await load(monkeypatch, httpx.Response(200, json={"agentsMd": None}))
    assert result["agentsMdStatus"] == "ready"
    assert result["skillSpacesStatus"] == "unsupported"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [[], {"agentsMd": 12}, {}])
async def test_invalid_payload_is_explicit_error(monkeypatch, body):
    result = await load(monkeypatch, httpx.Response(200, json=body), card())
    assert result["agentsMdStatus"] == "error"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [httpx.ReadTimeout("private diagnostic"), httpx.Response(200, text="not-json")],
)
async def test_transport_and_json_errors_preserve_independent_space_state(
    monkeypatch, response
):
    result = await load(monkeypatch, response, card())
    assert result["agentsMdStatus"] == "error"
    assert result["skillSpacesStatus"] == "ready"
    assert "private diagnostic" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 401, 404])
async def test_studio_auth_uses_only_server_key_and_safe_legacy_fallback(
    monkeypatch, status
):
    original = httpx.AsyncClient
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/api/v1/studio/agent-info":
            assert request.headers["X-MPA-Studio-Key"] == "server-runtime-key"
            return httpx.Response(status, json={"agentsMd": "# Real document"})
        assert "x-mpa-studio-key" not in request.headers
        assert request.url.path == "/api/v1/agents"
        return httpx.Response(403)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(**kw, transport=httpx.MockTransport(handler)),
    )
    result = await load_mpa_agent_info(
        "https://runtime.example",
        {"X-MPA-Studio-Key": "untrusted-browser-key"},
        card(),
        "cn-beijing",
        runtime_api_key="Bearer server-runtime-key",
    )
    assert (
        result["agentsMdStatus"]
        == {200: "ready", 401: "forbidden", 404: "unsupported"}[status]
    )
    assert len(paths) == (2 if status == 404 else 1)
    assert "server-runtime-key" not in str(result)
