import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from frontend.server import mpa_cron as m


def runtime(**env):
    values = {"MPA_AGENT_ID": "mi-one", "MPA_SPACE_ID": "space", **env}
    return NS(envs=[NS(key=k, value=v) for k, v in values.items()])


def test_trusted_identity(monkeypatch):
    app = FastAPI()
    request = Request(
        {"type": "http", "headers": [(b"x-veadk-local-user", b"spoofed")]}
    )
    monkeypatch.delenv("VEADK_STUDIO_MPA_USER_UID", raising=False)
    with pytest.raises(HTTPException, match="mpa_identity_required"):
        m.user_uid(request, app, False, Mock())
    monkeypatch.setenv("VEADK_STUDIO_MPA_USER_UID", " configured-user ")
    assert m.user_uid(request, app, False, Mock()) == "configured-user"
    assert (
        m.user_uid(
            request,
            app,
            True,
            Mock(return_value={"user_pool_user_uid": "gateway-user"}),
        )
        == "gateway-user"
    )
    with pytest.raises(HTTPException):
        m.user_uid(request, app, True, Mock(return_value=None))
    handler = NS(
        get_session_from_request=Mock(
            return_value=NS(user_info={"user_pool_user_uid": "oauth-user"})
        )
    )
    app.state.oauth2_handler = handler
    assert m.user_uid(request, app, False, Mock()) == "oauth-user"
    for session in [None, NS(user_info={}), NS(user_info={"user_pool_user_uid": 3})]:
        handler.get_session_from_request.return_value = session
        with pytest.raises(HTTPException):
            m.user_uid(request, app, False, Mock())


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        " ",
        "http://host.test",
        "https://user@host.test",
        "https://u:p@host.test",
        "https://host.test:443",
        "https://host.test/x",
        "https://host.test?a=1",
        "https://host.test#x",
        "https://",
    ],
)
def test_bad_endpoint(value):
    with pytest.raises(HTTPException):
        m.endpoint_origin(value)


@pytest.mark.parametrize(
    "value", ["host.test", "`https://host.test/api/v1/`", "https://host.test/"]
)
def test_endpoint(value):
    assert m.endpoint_origin(value) == "https://host.test"


def run_list(monkeypatch, responses, rt=None, token=None):
    calls = []

    def handle(request):
        calls.append(request)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(m.httpx, "AsyncClient", lambda **kw: client)
    result = asyncio.run(
        m.list_tasks(
            rt or runtime(),
            "https://host.test",
            "uid",
            "cn-beijing",
            ("ak", "sk", token),
            20,
            "report",
        )
    )
    return result, calls


TOKEN = {"PublicEndpoint": "host.test", "ApiKey": "test-api", "Token": "test-jwt"}


def test_top_then_data_plane(monkeypatch):
    page = {"items": [], "total": 0}
    result, calls = run_list(
        monkeypatch,
        [httpx.Response(200, json={"Result": TOKEN}), httpx.Response(200, json=page)],
        runtime(MPA_IS_DEBUG_RUNTIME="true"),
        "sts",
    )
    assert result == page
    import json

    assert json.loads(calls[0].content) == {
        "id": "mi-one",
        "SpaceId": "space",
        "UserPoolUserUid": "uid",
        "type": "Debug",
    }
    assert dict(calls[0].url.params) == {
        "Action": "GetMpaInstanceToken",
        "Version": "2026-03-01",
    }
    assert calls[0].headers["X-Security-Token"] == "sts"
    assert "x-security-token" in calls[0].headers["Authorization"]
    assert calls[1].url.path == "/api/v1/esa-cron-tasks"
    assert calls[1].headers["X-Jwt-Token"] == "test-jwt"
    assert calls[1].headers["Authorization"] == "Bearer test-api"
    assert calls[1].url.params["offset"] == "20"
    assert calls[1].url.params["query"] == "report"


def test_formal_and_legacy_fields(monkeypatch):
    _, calls = run_list(
        monkeypatch,
        [
            httpx.Response(
                200,
                json={
                    "Result": {
                        "public_endpoint": "host.test",
                        "api_key": "key",
                        "jwt_token": "jwt",
                    }
                },
            ),
            httpx.Response(200, json={}),
        ],
        runtime(MPA_SPACE_ID="", CLAW_SPACE_ID="space"),
    )
    assert b'"type"' not in calls[0].content
    assert "X-Security-Token" not in calls[0].headers


@pytest.mark.parametrize(
    "env",
    [{"MPA_AGENT_ID": ""}, {"MPA_SPACE_ID": ""}, {"ARKCLAW_TOP_SERVICE": "unknown"}],
)
def test_runtime_config(monkeypatch, env):
    with pytest.raises(HTTPException, match="mpa_runtime_config_required"):
        run_list(monkeypatch, [], runtime(**env))


@pytest.mark.parametrize(
    "responses,detail",
    [
        ([httpx.Response(403, json={})], "mpa_top_failed"),
        (
            [
                httpx.Response(
                    200, json={"ResponseMetadata": {"Error": {"Message": "secret"}}}
                )
            ],
            "mpa_top_failed",
        ),
        (
            [
                httpx.Response(
                    200, json={"Result": {**TOKEN, "PublicEndpoint": "other.test"}}
                )
            ],
            "mpa_runtime_mismatch",
        ),
        (
            [httpx.Response(200, json={"Result": {**TOKEN, "Token": ""}})],
            "mpa_invalid_credentials",
        ),
        (
            [httpx.Response(200, json={"Result": {**TOKEN, "ApiKey": 3}})],
            "mpa_invalid_credentials",
        ),
        (
            [
                httpx.Response(200, json={"Result": TOKEN}),
                httpx.Response(401, json={"secret": "private"}),
            ],
            "mpa_tasks_failed",
        ),
        (
            [httpx.Response(200, json={"Result": TOKEN}), httpx.Response(200, json=[])],
            "mpa_upstream_failed",
        ),
        ([httpx.Response(200, content=b"not json")], "mpa_upstream_failed"),
        ([httpx.Response(200, json=[])], "mpa_upstream_failed"),
        ([httpx.ConnectError("secret")], "mpa_upstream_failed"),
    ],
)
def test_upstream_failures(monkeypatch, responses, detail):
    with pytest.raises(HTTPException, match=detail) as caught:
        run_list(monkeypatch, responses)
    assert "secret" not in str(caught.value)


def test_route_authorization_and_query_validation(monkeypatch):
    app = FastAPI()
    authorize = Mock(return_value=runtime())
    identity = Mock(return_value="uid")
    listing = AsyncMock(return_value={"items": []})
    monkeypatch.setattr(m, "list_tasks", listing)
    m.mount_routes(
        app,
        authorize=authorize,
        connection=Mock(return_value=("https://host.test", "unused")),
        identity=identity,
        credentials=lambda: ("ak", "sk", None),
        region_for=lambda r: r,
    )
    with TestClient(app) as client:
        url = "/web/mpa-cron/r-one?region=cn-beijing"
        assert client.get(url + "&offset=-1").status_code == 422
        assert client.get(url + "&query=" + "x" * 201).status_code == 422
        assert client.get(
            url + "&offset=20&query=report", headers={"X-Jwt-Token": "spoofed"}
        ).json() == {"items": []}
        assert authorize.call_args.args[1:] == ("r-one", "cn-beijing")
        assert listing.call_args.args[1:] == (
            "https://host.test",
            "uid",
            "cn-beijing",
            ("ak", "sk", None),
            20,
            "report",
        )
        authorize.side_effect = HTTPException(404, "Runtime not found")
        identity.reset_mock()
        assert client.get(url).status_code == 404
        identity.assert_not_called()
        assert client.post(url).status_code == 405
