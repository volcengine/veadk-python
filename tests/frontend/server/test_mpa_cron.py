import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from frontend.server import mpa_cron as m


def call(monkeypatch, response, user="trusted"):
    calls = []

    def handle(request):
        calls.append(request)
        if isinstance(response, Exception):
            raise response
        return response

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(m.httpx, "AsyncClient", lambda **kw: client)
    return asyncio.run(
        m.task_request("https://runtime.test/", "Bearer key", user, "GET")
    ), calls


def test_upstream_headers(monkeypatch):
    result, calls = call(monkeypatch, httpx.Response(200, json={"items": []}))
    assert result == {"items": []}
    assert calls[0].headers["x-user-id"] == "trusted"
    assert calls[0].headers["authorization"] == "Bearer key"
    assert "x-jwt-token" not in calls[0].headers
    assert str(calls[0].url) == "https://runtime.test/api/v1/esa-cron-tasks"


@pytest.mark.parametrize(
    "response,code",
    [
        (httpx.Response(401, text="secret"), 401),
        (httpx.Response(403), 403),
        (httpx.Response(404), 404),
        (httpx.Response(409), 409),
        (httpx.Response(422), 422),
        (httpx.Response(302, headers={"location": "https://other.test"}), 502),
        (httpx.Response(200, json=[]), 502),
        (httpx.Response(200, text="not json"), 502),
        (httpx.ConnectError("secret"), 502),
    ],
)
def test_safe_errors(monkeypatch, response, code):
    with pytest.raises(HTTPException) as error:
        call(monkeypatch, response)
    assert error.value.status_code == code
    assert "secret" not in str(error.value)


def test_missing_identity(monkeypatch):
    with pytest.raises(HTTPException) as error:
        call(monkeypatch, httpx.Response(200), user="")
    assert error.value.status_code == 401


def test_routes_use_trusted_identity_and_allowlisted_paths(monkeypatch):
    app = FastAPI()
    outgoing = AsyncMock(return_value={"items": []})
    monkeypatch.setattr(m, "task_request", outgoing)
    authorize = Mock()
    m.mount_routes(
        app,
        authorize=authorize,
        connection=Mock(
            return_value=("https://runtime.test", "key", "key_auth", "public")
        ),
        authorization=lambda *args: "Bearer key",
        region_for=lambda region: region,
        user_for=lambda request: "trusted",
    )
    with TestClient(app) as client:
        base = "/web/mpa-cron/r-one"
        query = "?region=cn-beijing"
        for method, suffix, payload in [
            ("GET", "", None),
            ("POST", "", {"name": "task", "clientToken": "one"}),
            ("POST", "/t1", {"enabled": False, "expectedVersion": 1}),
            ("DELETE", "/t1", None),
            ("POST", "/t1/run", {"clientToken": "two", "mode": "Force"}),
            ("GET", "/t1/runs", None),
        ]:
            response = client.request(
                method,
                base + suffix + query,
                json=payload,
                headers={"x-user-id": "spoof", "X-Jwt-Token": "private"},
            )
            assert response.status_code == 200
            args = outgoing.call_args.args
            assert args[:5] == (
                "https://runtime.test",
                "Bearer key",
                "trusted",
                method,
                suffix,
            )
            if method == "POST":
                assert args[6] == payload
            assert authorize.call_args.args[1:] == ("r-one", "cn-beijing")
        assert client.get(base + query + "&offset=-1").status_code == 422
        assert client.get(base + query + "&query=" + "a" * 201).status_code == 422
        for payload in [[], {"endpoint": "https://other.test"}]:
            assert client.post(base + query, json=payload).status_code == 422
        assert client.post(base + query, content="not json").status_code == 422
        assert client.post(base + query, content="x" * 32769).status_code == 413
        assert client.post(base + "/bad.id" + query, json={}).status_code == 422
        assert client.post(base + "/t1/other" + query, json={}).status_code == 404
        authorize.side_effect = HTTPException(404, "Runtime not found")
        outgoing.reset_mock()
        assert client.get(base + query).status_code == 404
        outgoing.assert_not_called()
