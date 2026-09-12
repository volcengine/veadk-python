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

"""Regression tests for the unbounded download inside ``read_file_to_bytes``.

``read_file_to_bytes`` fetches user-supplied media URLs (``Runner`` turns a
``MediaMessage`` into bytes with it, and ``image_generate`` reads generated
images back through it), so the peer -- not VeADK -- decides how long the
transfer runs and how many bytes it delivers. It used to read
``response.content`` in one go behind nothing but ``DEFAULT_HTTP_TIMEOUT``,
whose read half bounds only the gap between two socket reads. A server
dribbling one chunk every 59s resets that gap forever, so the call was bounded
in neither wall-clock time nor memory.

Two limits are pinned here: ``DEFAULT_STREAM_BUDGET_SECONDS`` as a total
deadline, and ``MAX_DOWNLOAD_BYTES`` as a ceiling on what lands in the heap.

Nothing here touches the network or sleeps: ``requests.get`` is replaced by a
fake response and ``time.monotonic`` by a clock that leaps a full budget on
every read, so the deadline trips deterministically and instantly. The
trickling stream stops itself after ``_RUNAWAY_CHUNKS`` and the call runs on a
joined thread, so a regression fails the suite twice over instead of hanging
CI.
"""

import importlib
import os
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from veadk.utils import misc
from veadk.utils.http_defaults import (
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_STREAM_BUDGET_SECONDS,
)

_URL = "https://example.invalid/media.png"

# How far a "server" is allowed to trickle before the stream gives up on the
# code under test. Reached only when no deadline is enforced at all.
_RUNAWAY_CHUNKS = 50_000


class _FakeResponse:
    """The slice of ``requests.Response`` that ``read_file_to_bytes`` uses.

    ``content`` is implemented the way ``requests`` implements it -- buffer the
    whole body -- so the pre-fix code path is reproduced faithfully rather than
    quietly returning a mock.
    """

    def __init__(self, chunks, status_code: int = 200):
        self._chunks = chunks
        self.status_code = status_code
        self.closed = False
        self.chunks_served = 0

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info) -> bool:
        self.close()
        return False

    def close(self) -> None:
        self.closed = True

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for {_URL}")

    def iter_content(self, chunk_size=None):
        for chunk in self._chunks:
            self.chunks_served += 1
            yield chunk

    @property
    def content(self) -> bytes:
        return b"".join(self.iter_content())


class _JumpingClock:
    """A monotonic clock that leaps forward on every read.

    Models the trickling server without waiting for one: every chunk arrives
    comfortably inside the socket read timeout, yet the transfer as a whole
    blows the total budget.
    """

    def __init__(self, step: float):
        self._now = 0.0
        self._step = step

    def monotonic(self) -> float:
        value = self._now
        self._now += self._step
        return value


def _trickling_chunks():
    """A body that never ends -- until the safety valve gives up on the caller."""
    for _ in range(_RUNAWAY_CHUNKS):
        yield b"\0" * 8
    raise RuntimeError(
        f"the stream was consumed to exhaustion ({_RUNAWAY_CHUNKS} chunks): "
        "no wall-clock budget was enforced"
    )


def _run_bounded(func, timeout: float = 15.0):
    """Run ``func`` on a daemon thread so a regression fails instead of hanging."""
    box: dict = {}

    def target():
        try:
            box["value"] = func()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the main thread
            box["error"] = exc

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout)
    assert not worker.is_alive(), f"call did not return within {timeout}s"
    if "error" in box:
        raise box["error"]
    return box["value"]


def test_normal_download_returns_the_exact_bytes():
    """The streamed path must rebuild the body byte for byte."""
    payload = bytes(range(256)) * 40
    chunks = [payload[i : i + 1000] for i in range(0, len(payload), 1000)]
    response = _FakeResponse(chunks)

    with patch.object(misc.requests, "get", return_value=response):
        result = _run_bounded(lambda: misc.read_file_to_bytes(_URL))

    assert isinstance(result, bytes)
    assert result == payload


def test_download_streams_with_the_shared_socket_timeout():
    """Streaming is what makes the budget enforceable, so pin the call shape."""
    response = _FakeResponse([b"data"])

    with patch.object(misc.requests, "get", return_value=response) as get:
        assert misc.read_file_to_bytes(_URL) == b"data"

    get.assert_called_once()
    assert get.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT
    assert get.call_args.kwargs["stream"] is True
    assert response.closed, "the connection must be released"


def test_trickling_server_trips_the_wall_clock_budget():
    """Chunks forever, each within the read timeout, must still end the call.

    Every chunk resets the socket read timeout, so ``DEFAULT_HTTP_TIMEOUT``
    alone can never fire here -- only the total deadline does.
    """
    response = _FakeResponse(_trickling_chunks())
    clock = _JumpingClock(step=DEFAULT_STREAM_BUDGET_SECONDS)

    with (
        patch.object(misc.requests, "get", return_value=response),
        patch.object(misc, "time", SimpleNamespace(monotonic=clock.monotonic)),
        pytest.raises(requests.exceptions.Timeout) as excinfo,
    ):
        _run_bounded(lambda: misc.read_file_to_bytes(_URL))

    assert "not finished within" in str(excinfo.value)
    assert response.chunks_served < _RUNAWAY_CHUNKS, "the stream was drained"
    assert response.closed


def test_oversized_download_is_rejected_before_it_is_buffered(monkeypatch):
    """The budget bounds time; only the size cap bounds memory."""
    monkeypatch.setattr(misc, "MAX_DOWNLOAD_BYTES", 16)
    response = _FakeResponse([b"\0" * 8] * 100)

    with (
        patch.object(misc.requests, "get", return_value=response),
        pytest.raises(ValueError) as excinfo,
    ):
        _run_bounded(lambda: misc.read_file_to_bytes(_URL))

    assert "16 byte limit" in str(excinfo.value)
    # Three chunks: the first two fill the cap, the third exceeds it. The rest
    # of the body is never pulled into memory.
    assert response.chunks_served == 3
    assert response.closed


def test_http_errors_still_propagate():
    """Streaming must not change how a failed response is reported."""
    response = _FakeResponse([b"nope"], status_code=404)

    with (
        patch.object(misc.requests, "get", return_value=response),
        pytest.raises(requests.HTTPError),
    ):
        misc.read_file_to_bytes(_URL)

    assert response.closed


def test_local_paths_are_untouched(tmp_path):
    """Only the http(s) branch changed; the file branch must still round-trip."""
    payload = b"\x00\x01local bytes\xff"
    path = tmp_path / "media.bin"
    path.write_bytes(payload)

    assert misc.read_file_to_bytes(str(path)) == payload


def test_download_url_to_file_streams_and_replaces_atomically(tmp_path):
    """Disk downloads use the same bounded stream without buffering the body."""
    destination = tmp_path / "skill.zip"
    destination.write_bytes(b"old")
    response = _FakeResponse([b"zip-", b"bytes"])

    with patch.object(misc.requests, "get", return_value=response) as get:
        downloaded = misc.download_url_to_file(_URL, destination)

    assert downloaded == len(b"zip-bytes")
    assert destination.read_bytes() == b"zip-bytes"
    assert response.closed
    assert get.call_args.kwargs == {
        "timeout": DEFAULT_HTTP_TIMEOUT,
        "stream": True,
    }
    assert list(tmp_path.glob("*.part")) == []


def test_failed_disk_download_preserves_existing_destination(monkeypatch, tmp_path):
    """An oversized partial response must not replace a valid cached archive."""
    destination = tmp_path / "skill.zip"
    destination.write_bytes(b"known-good")
    monkeypatch.setattr(misc, "MAX_DOWNLOAD_BYTES", 4)
    response = _FakeResponse([b"1234", b"5"])

    with (
        patch.object(misc.requests, "get", return_value=response),
        pytest.raises(ValueError, match="4 byte limit"),
    ):
        misc.download_url_to_file(_URL, destination)

    assert destination.read_bytes() == b"known-good"
    assert list(tmp_path.glob("*.part")) == []


def _reload_misc(override: str | None = None):
    """Reload `misc` with the cap override set, or scrubbed if none is given.

    Scrubbing matters: the constant is read at import time, so an ambient
    `VEADK_MAX_DOWNLOAD_BYTES` on a developer's machine would otherwise decide
    what the default assertions see.
    """
    env = {"VEADK_MAX_DOWNLOAD_BYTES": override} if override is not None else {}
    with patch.dict(os.environ, env, clear=False):
        if override is None:
            os.environ.pop("VEADK_MAX_DOWNLOAD_BYTES", None)
        return importlib.reload(misc)


def test_size_cap_is_overridable_from_the_environment():
    """Same env-var style as `http_defaults`: read once, at import time."""
    try:
        assert _reload_misc("1024").MAX_DOWNLOAD_BYTES == 1024
        # A malformed override falls back to the default rather than
        # disabling the cap.
        assert _reload_misc("not-a-number").MAX_DOWNLOAD_BYTES == 256 * 1024 * 1024
        assert _reload_misc().MAX_DOWNLOAD_BYTES == 256 * 1024 * 1024
    finally:
        # Restore the module object the rest of the session imported.
        importlib.reload(misc)
