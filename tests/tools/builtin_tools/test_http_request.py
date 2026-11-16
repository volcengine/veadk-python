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

"""Hermetic tests for the ``http_request`` built-in tool."""

import inspect
import socket

import httpx
import pytest

from veadk.tools.builtin_tools import http_request as http_request_module
from veadk.tools.builtin_tools.http_request import http_request

_PUBLIC_IP = "93.184.216.34"


def _addrinfo(ip: str) -> list:
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 0))]


def _public_addrinfo(host: str, port: int | None = None) -> list:
    return _addrinfo(_PUBLIC_IP)


@pytest.fixture(autouse=True)
def _hermetic_dns(monkeypatch):
    monkeypatch.setattr(
        "veadk.tools.builtin_tools.web_fetch.socket.getaddrinfo", _public_addrinfo
    )
    monkeypatch.delenv("TOOL_HTTP_ALLOWLIST", raising=False)


class _FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        headers: dict | None = None,
        content: bytes = b"",
        encoding: str | None = None,
        chunks: list[bytes] | None = None,
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self.encoding = encoding
        self._chunks = chunks if chunks is not None else [content]

    def iter_bytes(self):
        yield from self._chunks


class _FakeStream:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def __enter__(self) -> _FakeResponse:
        return self._response

    def __exit__(self, *exc) -> bool:
        return False


class _FakeClient:
    def __init__(self, responses: list[_FakeResponse], **kwargs):
        self._responses = list(responses)
        self.kwargs = kwargs
        self.calls: list[dict] = []
        self.closed = False

    def stream(self, method, url, headers=None, params=None, json=None, content=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "json": json,
                "content": content,
            }
        )
        return _FakeStream(self._responses.pop(0))

    def close(self) -> None:
        self.closed = True


def _patch_client(
    monkeypatch, responses: list[_FakeResponse], client_cls=_FakeClient
) -> list:
    created: list = []

    def factory(**kwargs):
        client = client_cls(responses, **kwargs)
        created.append(client)
        return client

    monkeypatch.setattr(http_request_module.httpx, "Client", factory)
    return created


# --------------------------------------------------------------- contract ----
def test_signature():
    params = inspect.signature(http_request).parameters
    assert list(params) == [
        "url",
        "method",
        "headers",
        "params",
        "json_body",
        "body",
        "timeout",
        "max_bytes",
        "follow_redirects",
    ]


def test_defaults():
    params = inspect.signature(http_request).parameters
    assert params["url"].default is inspect.Parameter.empty
    assert params["method"].default == "GET"
    assert params["headers"].default is None
    assert params["params"].default is None
    assert params["json_body"].default is None
    assert params["body"].default is None
    assert params["timeout"].default == 30
    assert params["max_bytes"].default == 5_000_000
    assert params["follow_redirects"].default is False


# ------------------------------------------------------------ validation ----
@pytest.mark.parametrize("method", ["TRACE", "OPTIONS", "GET ", "", 123, None])
def test_rejects_bad_method(method):
    result = http_request("http://example.com", method=method)
    assert "error" in result


@pytest.mark.parametrize("timeout", [0, 121, True, "30", 1.5, None])
def test_rejects_bad_timeout(timeout):
    result = http_request("http://example.com", timeout=timeout)
    assert "error" in result


@pytest.mark.parametrize("max_bytes", [999, 20_000_001, True, "1000", 1000.0])
def test_rejects_bad_max_bytes(max_bytes):
    result = http_request("http://example.com", max_bytes=max_bytes)
    assert "error" in result


@pytest.mark.parametrize(
    "url", ["ftp://example.com", "not a url", "", None, 123, "http:///no-host"]
)
def test_rejects_bad_url(url):
    result = http_request(url)
    assert "error" in result


def test_blocks_private_address(monkeypatch):
    monkeypatch.setattr(
        "veadk.tools.builtin_tools.web_fetch.socket.getaddrinfo",
        lambda *args, **kwargs: _addrinfo("127.0.0.1"),
    )
    result = http_request("http://internal.example.com")
    assert "error" in result


@pytest.mark.parametrize(
    "headers",
    [
        {"host": "evil.example.com"},
        {"Host": "evil.example.com"},
        {"content-length": "10"},
        {"Content-Length": "10"},
        {1: "value"},
        {"X-Test": 1},
        {"X-Bad\n": "value"},
        {"X-Test": "value\r\nInjected: 1"},
    ],
)
def test_rejects_bad_headers(headers):
    result = http_request("http://example.com", headers=headers)
    assert "error" in result


@pytest.mark.parametrize("headers", [["x", "y"], "x"])
def test_rejects_non_mapping_headers(headers):
    result = http_request("http://example.com", headers=headers)
    assert "error" in result


def test_missing_env_header_returns_error(monkeypatch):
    monkeypatch.delenv("VEADK_TEST_MISSING_TOKEN", raising=False)
    result = http_request(
        "http://example.com",
        headers={"Authorization": "env:VEADK_TEST_MISSING_TOKEN"},
    )
    assert "error" in result


def test_empty_env_name_returns_error(monkeypatch):
    result = http_request("http://example.com", headers={"Authorization": "env:"})
    assert "error" in result


def test_empty_env_value_returns_error(monkeypatch):
    monkeypatch.setenv("VEADK_TEST_EMPTY_TOKEN", "")
    result = http_request(
        "http://example.com",
        headers={"Authorization": "env:VEADK_TEST_EMPTY_TOKEN"},
    )
    assert "error" in result


# --------------------------------------------------------------- allowlist --
def test_allowlist_exact_host(monkeypatch):
    monkeypatch.setenv("TOOL_HTTP_ALLOWLIST", "example.com")
    _patch_client(monkeypatch, [_FakeResponse(200, content=b"ok")])
    result = http_request("http://example.com/path")
    assert result["status_code"] == 200


def test_allowlist_subdomain(monkeypatch):
    monkeypatch.setenv("TOOL_HTTP_ALLOWLIST", "example.com")
    _patch_client(monkeypatch, [_FakeResponse(200, content=b"ok")])
    result = http_request("http://api.example.com/path")
    assert result["status_code"] == 200


def test_allowlist_case_insensitive(monkeypatch):
    monkeypatch.setenv("TOOL_HTTP_ALLOWLIST", "EXAMPLE.COM")
    _patch_client(monkeypatch, [_FakeResponse(200, content=b"ok")])
    result = http_request("http://Example.COM/path")
    assert result["status_code"] == 200


def test_allowlist_denies_other_host(monkeypatch):
    monkeypatch.setenv("TOOL_HTTP_ALLOWLIST", "example.com")
    created = _patch_client(monkeypatch, [_FakeResponse(200, content=b"ok")])
    result = http_request("http://evil.example.org/path")
    assert "error" in result
    assert created[0].calls == []
    assert created[0].closed is True


def test_empty_allowlist_is_unrestricted(monkeypatch):
    monkeypatch.setenv("TOOL_HTTP_ALLOWLIST", " , ")
    _patch_client(monkeypatch, [_FakeResponse(200, content=b"ok")])
    result = http_request("http://example.com/path")
    assert result["status_code"] == 200


def test_allowlist_applies_to_redirect(monkeypatch):
    monkeypatch.setenv("TOOL_HTTP_ALLOWLIST", "example.com")
    _patch_client(
        monkeypatch,
        [
            _FakeResponse(302, {"location": "http://evil.example.org/next"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    result = http_request("http://example.com/start", follow_redirects=True)
    assert "error" in result


# ------------------------------------------------------------ happy paths ---
def test_get_success(monkeypatch):
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(
                200,
                {"Content-Type": "text/plain", "X-Test": "1"},
                b"hello",
            )
        ],
    )
    result = http_request("http://example.com/path")
    assert result == {
        "status_code": 200,
        "url": "http://example.com/path",
        "headers": {"content-type": "text/plain", "x-test": "1"},
        "content_type": "text/plain",
        "body": "hello",
        "bytes": 5,
        "truncated": False,
    }
    client = created[0]
    assert client.closed is True
    assert client.kwargs == {"timeout": 30, "follow_redirects": False}
    assert client.calls[0]["method"] == "GET"


def test_method_is_normalized(monkeypatch):
    created = _patch_client(monkeypatch, [_FakeResponse(200, content=b"ok")])
    http_request("http://example.com", method="get")
    assert created[0].calls[0]["method"] == "GET"


def test_head_response_has_empty_body(monkeypatch):
    _patch_client(monkeypatch, [_FakeResponse(200, content=b"ignored")])
    result = http_request("http://example.com", method="HEAD")
    assert result["body"] == ""
    assert result["bytes"] == 0
    assert result["truncated"] is False


def test_missing_content_type_is_none(monkeypatch):
    _patch_client(monkeypatch, [_FakeResponse(200, content=b"ok")])
    result = http_request("http://example.com")
    assert result["content_type"] is None


def test_resolves_env_header_without_leaking_value(monkeypatch):
    monkeypatch.setenv("VEADK_TEST_TOKEN", "s3cret-value")
    created = _patch_client(monkeypatch, [_FakeResponse(200, content=b"ok")])
    result = http_request(
        "http://example.com",
        headers={"Authorization": "env:VEADK_TEST_TOKEN", "X-Plain": "ok"},
    )
    assert result["status_code"] == 200
    assert created[0].calls[0]["headers"] == {
        "Authorization": "s3cret-value",
        "X-Plain": "ok",
    }
    assert "s3cret-value" not in str(result)


def test_post_json_body_and_params(monkeypatch):
    created = _patch_client(monkeypatch, [_FakeResponse(200, content=b"ok")])
    http_request(
        "http://example.com/api",
        method="POST",
        params={"q": "x"},
        json_body={"a": 1},
    )
    call = created[0].calls[0]
    assert call["method"] == "POST"
    assert call["params"] == {"q": "x"}
    assert call["json"] == {"a": 1}
    assert call["content"] is None


def test_raw_body(monkeypatch):
    created = _patch_client(monkeypatch, [_FakeResponse(200, content=b"ok")])
    http_request("http://example.com/api", method="POST", body="raw")
    call = created[0].calls[0]
    assert call["content"] == "raw"
    assert call["json"] is None


def test_json_body_and_raw_body_are_mutually_exclusive(monkeypatch):
    created = _patch_client(monkeypatch, [_FakeResponse(200, content=b"ok")])
    result = http_request(
        "http://example.com/api", method="POST", json_body={"a": 1}, body="raw"
    )
    assert "error" in result
    assert created == []


# --------------------------------------------------------------- decoding ---
def test_decodes_using_response_encoding(monkeypatch):
    _patch_client(
        monkeypatch,
        [
            _FakeResponse(
                200,
                {"content-type": "text/plain; charset=iso-8859-1"},
                b"caf\xe9",
                encoding="iso-8859-1",
            )
        ],
    )
    result = http_request("http://example.com")
    assert result["body"] == "café"


def test_decodes_as_utf8_by_default(monkeypatch):
    _patch_client(monkeypatch, [_FakeResponse(200, content=b"caf\xc3\xa9")])
    result = http_request("http://example.com")
    assert result["body"] == "café"


def test_unknown_encoding_falls_back_to_utf8(monkeypatch):
    _patch_client(
        monkeypatch,
        [_FakeResponse(200, content=b"ok", encoding="not-a-codec")],
    )
    result = http_request("http://example.com")
    assert result["body"] == "ok"


# -------------------------------------------------------------- truncation --
def test_truncates_at_max_bytes(monkeypatch):
    _patch_client(monkeypatch, [_FakeResponse(200, content=b"a" * 1001)])
    result = http_request("http://example.com", max_bytes=1000)
    assert result["bytes"] == 1000
    assert len(result["body"]) == 1000
    assert result["truncated"] is True


def test_exact_limit_is_not_truncated(monkeypatch):
    _patch_client(monkeypatch, [_FakeResponse(200, content=b"a" * 1000)])
    result = http_request("http://example.com", max_bytes=1000)
    assert result["bytes"] == 1000
    assert result["truncated"] is False


def test_truncates_across_chunks_and_skips_empty(monkeypatch):
    _patch_client(
        monkeypatch,
        [_FakeResponse(200, chunks=[b"", b"a" * 600, b"b" * 600])],
    )
    result = http_request("http://example.com", max_bytes=1000)
    assert result["bytes"] == 1000
    assert result["body"] == "a" * 600 + "b" * 400
    assert result["truncated"] is True


# --------------------------------------------------------------- redirects --
def test_redirect_not_followed_by_default(monkeypatch):
    created = _patch_client(
        monkeypatch, [_FakeResponse(302, {"location": "/next"}, content=b"moved")]
    )
    result = http_request("http://example.com/start")
    assert result["status_code"] == 302
    assert result["body"] == "moved"
    assert result["url"] == "http://example.com/start"
    assert len(created[0].calls) == 1


def test_follows_relative_redirect(monkeypatch):
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(302, {"location": "/next"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    result = http_request(
        "http://example.com/start", params={"a": "1"}, follow_redirects=True
    )
    assert result["url"] == "http://example.com/next"
    assert result["body"] == "ok"
    assert [call["url"] for call in created[0].calls] == [
        "http://example.com/start",
        "http://example.com/next",
    ]
    assert created[0].calls[0]["params"] == {"a": "1"}
    assert created[0].calls[1]["params"] is None


def test_follows_absolute_redirect(monkeypatch):
    _patch_client(
        monkeypatch,
        [
            _FakeResponse(301, {"location": "http://other.example.com/final"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    result = http_request("http://example.com/start", follow_redirects=True)
    assert result["url"] == "http://other.example.com/final"


def test_303_switches_post_to_get_and_drops_body(monkeypatch):
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(303, {"location": "/done"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    http_request(
        "http://example.com/api",
        method="POST",
        json_body={"a": 1},
        follow_redirects=True,
    )
    redirected = created[0].calls[1]
    assert redirected["method"] == "GET"
    assert redirected["json"] is None
    assert redirected["content"] is None


def test_301_switches_post_to_get(monkeypatch):
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(301, {"location": "/done"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    http_request(
        "http://example.com/api", method="POST", body="raw", follow_redirects=True
    )
    assert created[0].calls[1]["method"] == "GET"
    assert created[0].calls[1]["content"] is None


def test_302_preserves_non_post_method(monkeypatch):
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(302, {"location": "/done"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    http_request(
        "http://example.com/api",
        method="PUT",
        body="raw",
        follow_redirects=True,
    )
    assert created[0].calls[1]["method"] == "PUT"
    assert created[0].calls[1]["content"] == "raw"


@pytest.mark.parametrize("status", [307, 308])
def test_307_308_preserve_method_and_body(monkeypatch, status):
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(status, {"location": "/done"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    http_request(
        "http://example.com/api",
        method="POST",
        json_body={"a": 1},
        follow_redirects=True,
    )
    redirected = created[0].calls[1]
    assert redirected["method"] == "POST"
    assert redirected["json"] == {"a": 1}


def test_credentials_are_kept_on_same_origin_redirect(monkeypatch):
    monkeypatch.setenv("VEADK_TEST_TOKEN", "s3cret-value")
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(302, {"location": "/next"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    http_request(
        "https://example.com/start",
        headers={"Authorization": "env:VEADK_TEST_TOKEN", "X-Plain": "ok"},
        follow_redirects=True,
    )
    assert created[0].calls[1]["headers"] == {
        "Authorization": "s3cret-value",
        "X-Plain": "ok",
    }


def test_explicit_default_port_is_same_origin(monkeypatch):
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(302, {"location": "http://example.com/next"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    http_request(
        "http://example.com:80/start",
        headers={"Authorization": "Bearer t"},
        follow_redirects=True,
    )
    assert created[0].calls[1]["headers"] == {"Authorization": "Bearer t"}


def test_credentials_are_kept_on_same_host_https_upgrade(monkeypatch):
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(301, {"location": "https://example.com/next"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    http_request(
        "http://example.com/start",
        headers={"Authorization": "Bearer t", "Cookie": "a=b", "X-Plain": "ok"},
        follow_redirects=True,
    )
    assert created[0].calls[1]["headers"] == {
        "Authorization": "Bearer t",
        "Cookie": "a=b",
        "X-Plain": "ok",
    }


def test_credentials_are_stripped_across_hosts(monkeypatch):
    monkeypatch.setenv("VEADK_TEST_TOKEN", "s3cret-value")
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(302, {"location": "https://evil.example/capture"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    result = http_request(
        "https://safe.example/x",
        headers={
            "Authorization": "env:VEADK_TEST_TOKEN",
            "X-Api-Key": "env:VEADK_TEST_TOKEN",
            "Proxy-Authorization": "Basic abc",
            "Cookie": "session=1",
            "X-Plain": "ok",
        },
        follow_redirects=True,
    )
    assert result["status_code"] == 200
    first_headers = created[0].calls[0]["headers"]
    assert first_headers["Authorization"] == "s3cret-value"
    assert first_headers["X-Api-Key"] == "s3cret-value"
    # Only non-secret, non-sensitive headers survive a cross-origin hop.
    assert created[0].calls[1]["headers"] == {"X-Plain": "ok"}


def test_credentials_are_stripped_on_https_to_http_downgrade(monkeypatch):
    monkeypatch.setenv("VEADK_TEST_TOKEN", "s3cret-value")
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(302, {"location": "http://example.com/next"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    http_request(
        "https://example.com/start",
        headers={
            "Authorization": "env:VEADK_TEST_TOKEN",
            "X-Api-Key": "env:VEADK_TEST_TOKEN",
            "X-Plain": "ok",
        },
        follow_redirects=True,
    )
    assert created[0].calls[1]["headers"] == {"X-Plain": "ok"}


def test_stripped_credentials_stay_stripped_on_later_hops(monkeypatch):
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(302, {"location": "https://evil.example/one"}),
            _FakeResponse(302, {"location": "/two"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    http_request(
        "https://safe.example/x",
        headers={"Authorization": "Bearer t"},
        follow_redirects=True,
    )
    assert created[0].calls[1]["headers"] == {}
    assert created[0].calls[2]["headers"] == {}


def test_303_preserves_head_method(monkeypatch):
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(303, {"location": "/done"}),
            _FakeResponse(200),
        ],
    )
    http_request("http://example.com/api", method="HEAD", follow_redirects=True)
    assert created[0].calls[1]["method"] == "HEAD"


def test_too_many_redirects(monkeypatch):
    created = _patch_client(
        monkeypatch,
        [
            _FakeResponse(302, {"location": "/1"}),
            _FakeResponse(302, {"location": "/2"}),
            _FakeResponse(302, {"location": "/3"}),
            _FakeResponse(302, {"location": "/4"}),
        ],
    )
    result = http_request("http://example.com/start", follow_redirects=True)
    assert "error" in result
    assert "redirect" in result["error"]
    assert created[0].closed is True


def test_redirect_without_location_is_final(monkeypatch):
    _patch_client(monkeypatch, [_FakeResponse(302, {}, content=b"body")])
    result = http_request("http://example.com", follow_redirects=True)
    assert result["status_code"] == 302
    assert result["body"] == "body"


def test_redirect_to_private_address_is_blocked(monkeypatch):
    def mixed_addrinfo(host, port=None):
        if host == "internal.example.com":
            return _addrinfo("10.0.0.1")
        return _public_addrinfo(host, port)

    monkeypatch.setattr(
        "veadk.tools.builtin_tools.web_fetch.socket.getaddrinfo", mixed_addrinfo
    )
    _patch_client(
        monkeypatch,
        [
            _FakeResponse(302, {"location": "http://internal.example.com/x"}),
            _FakeResponse(200, content=b"secret"),
        ],
    )
    result = http_request("http://example.com/start", follow_redirects=True)
    assert "error" in result


def test_redirect_to_non_http_scheme_is_blocked(monkeypatch):
    _patch_client(
        monkeypatch,
        [
            _FakeResponse(302, {"location": "ftp://example.com/x"}),
            _FakeResponse(200, content=b"ok"),
        ],
    )
    result = http_request("http://example.com/start", follow_redirects=True)
    assert "error" in result


# --------------------------------------------------------------- failures ---
def test_client_creation_failure_returns_error(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(http_request_module.httpx, "Client", boom)
    result = http_request("http://example.com")
    assert "error" in result


def test_network_error_returns_error_and_closes_client(monkeypatch):
    class _ExplodingClient(_FakeClient):
        def stream(self, *args, **kwargs):
            raise httpx.ConnectError("boom")

    created = _patch_client(monkeypatch, [], client_cls=_ExplodingClient)
    result = http_request("http://example.com")
    assert "error" in result
    assert created[0].closed is True
