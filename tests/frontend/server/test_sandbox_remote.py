from __future__ import annotations

import pytest
import requests

from frontend.server.sandbox_remote import (
    SandboxRemoteError,
    SandboxRemoteResponseError,
    SandboxRemoteSizeError,
    SandboxRemoteTransport,
)


class Response:
    def __init__(self, status=200, *, payload=None, chunks=()):
        self.status_code = status
        self.payload = payload
        self.chunks = chunks

    def json(self):
        return self.payload

    def iter_content(self, chunk_size):
        assert chunk_size == 64 * 1024
        yield from self.chunks

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


@pytest.mark.asyncio
async def test_exec_is_single_attempt_and_reports_ambiguous_failure(monkeypatch) -> None:
    calls = 0

    def post(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise requests.ConnectionError("lost")

    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(SandboxRemoteError) as caught:
        await SandboxRemoteTransport("https://sandbox").exec_text("mutate")
    assert caught.value.retryable is True
    assert calls == 1


@pytest.mark.asyncio
async def test_exec_json_validates_response(monkeypatch) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: Response(
            payload={"data": {"output": '{"state":"ready"}'}}
        ),
    )
    assert await SandboxRemoteTransport("https://sandbox").exec_json("read") == {
        "state": "ready"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["relative", "/a/../secret", "//a", "/a/", "/a//b", "/控制" * 200],
)
async def test_exact_path_rejects_non_normalized_or_oversized(path) -> None:
    with pytest.raises(SandboxRemoteResponseError):
        await SandboxRemoteTransport("https://sandbox").download(path)


@pytest.mark.asyncio
async def test_download_streams_and_caps_before_full_buffer(monkeypatch) -> None:
    monkeypatch.setattr(
        requests,
        "get",
        lambda *args, **kwargs: Response(chunks=(b"ab", b"cd")),
    )
    transport = SandboxRemoteTransport("https://sandbox")
    assert await transport.download("/artifact.zip", max_bytes=4) == b"abcd"
    with pytest.raises(SandboxRemoteSizeError):
        await transport.download("/artifact.zip", max_bytes=3)


@pytest.mark.asyncio
async def test_download_retries_transient_read(monkeypatch) -> None:
    responses = [Response(503), Response(chunks=(b"ok",))]
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: responses.pop(0))
    assert await SandboxRemoteTransport("https://sandbox").download("/file") == b"ok"


@pytest.mark.asyncio
async def test_upload_is_bounded_and_uses_exact_path(monkeypatch) -> None:
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(requests, "post", post)
    transport = SandboxRemoteTransport("https://sandbox")
    await transport.upload("/secrets/cloud.json", b"{}")
    assert calls[0][1]["data"] == {"path": "/secrets/cloud.json"}
    with pytest.raises(SandboxRemoteSizeError):
        await transport.upload("/file", b"large", max_bytes=1)
