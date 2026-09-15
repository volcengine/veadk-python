import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from frontend.server import mpa_cron as m


def run_list(monkeypatch, response):
    calls = []

    def handle(request):
        calls.append(request)
        if isinstance(response, Exception):
            raise response
        return response

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(m.httpx, "AsyncClient", lambda **kw: client)
    result = asyncio.run(
        m.list_tasks("https://runtime.test/", "Bearer gateway-key", 20, "report")
    )
    return result, calls


def test_direct_request_without_top_or_jwt(monkeypatch):
    page = {"items": [], "total": 0}
    result, calls = run_list(monkeypatch, httpx.Response(200, json=page))
    assert result == page
    assert len(calls) == 1
    request = calls[0]
    assert request.method == "GET"
    assert str(request.url).startswith("https://runtime.test/api/v1/esa-cron-tasks?")
    assert "x-user-id" not in request.headers
    assert "x-space-id" not in request.headers
    assert "x-mpa-id" not in request.headers
    assert request.headers["Authorization"] == "Bearer gateway-key"
    assert "x-jwt-token" not in request.headers
    assert dict(request.url.params) == {
        "offset": "20",
        "query": "report",
        "includeDisabled": "true",
        "limit": "20",
    }


@pytest.mark.parametrize(
    "response,detail",
    [
        (httpx.Response(401, json={"private": "secret"}), "mpa_tasks_failed"),
        (httpx.Response(403, json={}), "mpa_tasks_failed"),
        (httpx.Response(404, json={}), "mpa_tasks_failed"),
        (httpx.Response(200, json=[]), "mpa_upstream_failed"),
        (httpx.Response(200, content=b"not json"), "mpa_upstream_failed"),
        (httpx.ConnectError("secret"), "mpa_upstream_failed"),
    ],
)
def test_failures(monkeypatch, response, detail):
    with pytest.raises(HTTPException, match=detail) as error:
        run_list(monkeypatch, response)
    assert "secret" not in str(error.value)


def test_route_preserves_authorization_and_ignores_browser_credentials(monkeypatch):
    app = FastAPI()
    runtime = NS(envs=None)
    authorize = Mock(return_value=runtime)
    authorization = Mock(return_value="Bearer gateway-key")
    listing = AsyncMock(return_value={"items": []})
    monkeypatch.setattr(m, "list_tasks", listing)
    m.mount_routes(
        app,
        authorize=authorize,
        connection=Mock(
            return_value=("https://runtime.test", "key", "key_auth", "public")
        ),
        authorization=authorization,
        region_for=lambda r: r,
    )
    with TestClient(app) as client:
        url = "/web/mpa-cron/r-one?region=cn-beijing"
        assert client.get(url + "&offset=-1").status_code == 422
        assert client.get(url + "&query=" + "x" * 201).status_code == 422
        assert client.get(
            url + "&offset=20&query=report",
            headers={"X-Jwt-Token": "unused", "x-user-id": "untrusted"},
        ).json() == {"items": []}
        assert authorize.call_args.args[1:] == ("r-one", "cn-beijing")
        assert authorization.call_args.args[1:] == ("key", "key_auth")
        assert listing.call_args.args == (
            "https://runtime.test",
            "Bearer gateway-key",
            20,
            "report",
        )
        authorize.side_effect = HTTPException(404, "Runtime not found")
        assert client.get(url).status_code == 404
        assert client.post(url).status_code == 405
