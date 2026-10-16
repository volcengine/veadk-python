# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# SPDX-License-Identifier: Apache-2.0

import asyncio
import builtins
import sys
import tempfile
import types
from pathlib import Path

import httpx
import pytest
import volcenginesdkarkruntime
from volcenginesdkarkruntime._exceptions import ArkAPIStatusError

from veadk.utils import misc


@pytest.fixture
def upload_directory():
    with tempfile.TemporaryDirectory() as directory:
        yield Path(directory)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "upload_error",
        "poll_error",
        "timeout",
        "cancel_upload",
        "cancel_poll",
        "missing_file",
    ],
)
async def test_upload_closes_owned_resources(upload_directory, monkeypatch, outcome):
    path = upload_directory / "video.mp4"
    path.write_bytes(b"local video payload")
    if outcome == "missing_file":
        path.unlink()

    # Keep credential discovery outside this unit test; the SDK, multipart
    # upload, polling, file handles and HTTP client are real.
    config = types.ModuleType("veadk.config")
    config.getenv = lambda name, default: default
    config.settings = types.SimpleNamespace(
        model=types.SimpleNamespace(api_key="test-files-upload")
    )
    monkeypatch.setitem(sys.modules, "veadk.config", config)
    opened = []
    clients = []
    requests = []
    closed_during_poll = []

    def tracked_open(*args, **kwargs):
        handle = builtins.open(*args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(misc, "open", tracked_open, raising=False)

    async def handle_request(request):
        requests.append(request)
        stage = "upload" if request.method == "POST" else "poll"
        if stage == "poll":
            closed_during_poll.append(all(handle.closed for handle in opened))
        if outcome == f"cancel_{stage}":
            raise asyncio.CancelledError()
        if outcome == f"{stage}_error":
            return httpx.Response(500, json={"error": {"message": "test failure"}})
        return httpx.Response(
            200,
            json={
                "id": "file-test",
                "created_at": 1,
                "expire_at": 2,
                "filename": path.name,
                "object": "file",
                "purpose": "user_data",
                "status": "processing" if outcome == "timeout" else "active",
            },
        )

    original_client = volcenginesdkarkruntime.AsyncArk

    def create_client(**kwargs):
        client = original_client(
            **kwargs,
            max_retries=0,
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(handle_request)
            ),
        )
        clients.append(client)
        return client

    monkeypatch.setattr(volcenginesdkarkruntime, "AsyncArk", create_client)
    expected_exception = {
        "upload_error": ArkAPIStatusError,
        "poll_error": ArkAPIStatusError,
        "timeout": RuntimeError,
        "cancel_upload": asyncio.CancelledError,
        "cancel_poll": asyncio.CancelledError,
        "missing_file": FileNotFoundError,
    }.get(outcome)
    try:
        if expected_exception:
            with pytest.raises(expected_exception):
                await misc.upload_to_files_api(
                    str(path), fps=2, poll_interval=0, max_wait_seconds=-1
                )
        else:
            assert await misc.upload_to_files_api(str(path), fps=2) == "file-test"

        assert len(clients) == 1
        assert clients[0].is_closed()
        assert all(handle.closed for handle in opened)
        assert all(closed_during_poll)
        if outcome != "missing_file":
            assert opened
            assert requests[0].method == "POST"
            assert b"local video payload" in requests[0].content
            assert b"user_data" in requests[0].content
            assert b"fps" in requests[0].content
    finally:
        # Clean up even on the unfixed implementation so red runs do not leak.
        for handle in opened:
            handle.close()
        for client in clients:
            await client.close()
