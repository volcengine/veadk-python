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
async def test_exec_is_single_attempt_and_reports_ambiguous_failure(
    monkeypatch,
) -> None:
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


@pytest.mark.asyncio
async def test_upload_sets_mode_through_nofollow_descriptor(monkeypatch) -> None:
    from types import SimpleNamespace
    from frontend.server import sandbox_remote

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: Response())
    monkeypatch.setattr(sandbox_remote, "uuid4", lambda: SimpleNamespace(hex="marker"))
    transport = SandboxRemoteTransport("https://sandbox")
    commands = []

    async def exec_json(command, *, timeout):
        commands.append(command)
        return {"marker": "marker"}

    monkeypatch.setattr(transport, "exec_json", exec_json)
    await transport.upload("/secrets/cloud.json", b"{}", mode=0o600)

    assert "O_NOFOLLOW" in commands[0]
    assert "os.fchmod(fd,expected)" in commands[0]
    assert "stat.S_ISREG" in commands[0]

    async def wrong_marker(command, *, timeout):
        return {"marker": "wrong"}

    monkeypatch.setattr(transport, "exec_json", wrong_marker)
    with pytest.raises(SandboxRemoteResponseError, match="permission verification"):
        await transport.upload("/secrets/cloud.json", b"{}", mode=0o600)
    with pytest.raises(ValueError, match="permission mode"):
        await transport.upload("/file", b"", mode=0o1000)


def test_transport_rejects_nonpositive_attempt_count() -> None:
    with pytest.raises(ValueError, match="positive"):
        SandboxRemoteTransport("https://sandbox", read_attempts=0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "no data"),
        ({"data": {"output": 1}}, "no output"),
    ],
)
async def test_exec_text_rejects_malformed_success_response(
    monkeypatch, payload, message
) -> None:
    monkeypatch.setattr(
        requests, "post", lambda *args, **kwargs: Response(payload=payload)
    )
    with pytest.raises(SandboxRemoteResponseError, match=message):
        await SandboxRemoteTransport("https://sandbox").exec_text("read")


@pytest.mark.asyncio
async def test_exec_text_downloads_complete_output_and_requires_utf8(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: Response(
            payload={"data": {"output": "truncated", "full_output_file_path": "/full"}}
        ),
    )
    contents = ["完整".encode(), b"\xff"]

    async def download(path, *, max_bytes):
        assert (path, max_bytes) == ("/full", 16 * 1024 * 1024)
        return contents.pop(0)

    transport = SandboxRemoteTransport("https://sandbox")
    monkeypatch.setattr(transport, "download", download)
    assert await transport.exec_text("read") == "完整"
    with pytest.raises(SandboxRemoteResponseError, match="not UTF-8"):
        await transport.exec_text("read")


@pytest.mark.asyncio
async def test_exec_text_rejects_oversized_inline_output(monkeypatch) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        lambda *args, **kwargs: Response(
            payload={"data": {"output": "x" * (16 * 1024 * 1024 + 1)}}
        ),
    )
    with pytest.raises(SandboxRemoteSizeError, match="exceeds"):
        await SandboxRemoteTransport("https://sandbox").exec_text("read")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output, message",
    [
        ("not-json", "not valid JSON"),
        ('"text"', "not a JSON object"),
    ],
)
async def test_exec_json_rejects_invalid_or_nonobject_output(
    monkeypatch, output, message
) -> None:
    transport = SandboxRemoteTransport("https://sandbox")

    async def exec_text(command, *, timeout):
        assert (command, timeout) == ("read", 12)
        return output

    monkeypatch.setattr(transport, "exec_text", exec_text)
    with pytest.raises(SandboxRemoteResponseError, match=message):
        await transport.exec_json("read")


@pytest.mark.asyncio
async def test_exec_json_accepts_single_shell_quoted_json(monkeypatch) -> None:
    transport = SandboxRemoteTransport("https://sandbox")

    async def exec_text(command, *, timeout):
        return "'{\"ready\":true}'"

    monkeypatch.setattr(transport, "exec_text", exec_text)
    assert await transport.exec_json("read") == {"ready": True}


@pytest.mark.asyncio
async def test_transfer_validates_content_and_limits(monkeypatch) -> None:
    transport = SandboxRemoteTransport("https://sandbox")
    with pytest.raises(TypeError, match="bytes"):
        await transport.upload("/file", "text")
    with pytest.raises(ValueError, match="negative"):
        await transport.upload("/file", b"", max_bytes=-1)
    with pytest.raises(ValueError, match="negative"):
        await transport.download("/file", max_bytes=-1)

    monkeypatch.setattr(
        requests, "get", lambda *args, **kwargs: Response(chunks=(b"", b"ok"))
    )
    assert await transport.download("/file") == b"ok"


@pytest.mark.asyncio
async def test_read_retry_reports_transient_exhaustion_and_nontransient_http(
    monkeypatch,
) -> None:
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response(503))
    with pytest.raises(SandboxRemoteError, match="Failed to download") as transient:
        await SandboxRemoteTransport("https://sandbox", read_attempts=1).download(
            "/file"
        )
    assert transient.value.retryable is True

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response(404))
    with pytest.raises(SandboxRemoteError, match="Failed to download") as permanent:
        await SandboxRemoteTransport("https://sandbox").download("/file")
    assert permanent.value.retryable is False


@pytest.mark.asyncio
async def test_exec_rejects_nonobject_json_and_preserves_response_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        requests, "post", lambda *args, **kwargs: Response(payload=["unexpected"])
    )
    with pytest.raises(SandboxRemoteResponseError, match="not a JSON object"):
        await SandboxRemoteTransport("https://sandbox").exec_text("read")

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: Response(400))
    with pytest.raises(SandboxRemoteError, match="Sandbox request failed") as caught:
        await SandboxRemoteTransport("https://sandbox").exec_text("read")
    assert caught.value.retryable is False


@pytest.mark.asyncio
async def test_retry_loop_defensive_failure_if_attempt_invariant_is_corrupted() -> None:
    transport = SandboxRemoteTransport("https://sandbox")
    transport._read_attempts = 0
    with pytest.raises(RuntimeError, match="exited unexpectedly"):
        await transport._read_retry(lambda: b"unused", "read", retry_conflict=False)
