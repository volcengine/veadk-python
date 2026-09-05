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

"""Regression tests for the two hazards fixed in ``image_edit``.

``image_edit`` drives the *synchronous* Ark SDK from an ``async def`` tool, and
both problems follow from that:

1. the client was built with the SDK defaults -- a 600s read timeout, a 60s
   connect timeout and two retries -- so one unresponsive ``images.generate``
   could hold the tool for half an hour, repeated for *every* item in
   ``params``. ``_get_client`` now passes an explicit ``httpx.Timeout`` built
   from ``DEFAULT_IMAGE_EDIT_READ_TIMEOUT`` and the shared
   ``DEFAULT_CONNECT_TIMEOUT``, plus ``DEFAULT_IMAGE_EDIT_MAX_RETRIES``;
2. that blocking call, and the equally blocking ``_upload_image_to_tos`` on the
   ``b64_json`` branch, ran inline on the event loop. Awaiting a coroutine that
   parks the loop for minutes stalls every other agent in the process, so both
   are now handed to ``asyncio.to_thread``.

The timeout tests read their expectations from the module constants rather than
from literals, so retuning the budget stays a one-line change; what they pin is
the *shape* -- connect far tighter than read, and the whole worst-case wait far
below what the SDK would have allowed.

The offload tests are the ones that fail loudly against the pre-fix code: the
SDK stub records ``threading.get_ident()``, and a blocked event loop is caught
directly by watching whether a concurrently scheduled task still gets to run
while the "SDK call" is in flight.

Nothing here touches the network. ``_get_client`` is replaced wherever the tool
is driven end to end, ``MODEL_EDIT_API_KEY`` short-circuits the credential
lookup that would otherwise reach ``settings.model.api_key`` (a cached property
that can fetch a live Ark token), and an autouse tripwire makes every httpx
transport raise. Every awaited call is bounded, so a regression fails the suite
instead of freezing it.
"""

import asyncio
import base64
import contextlib
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from volcenginesdkarkruntime import Ark

from veadk.consts import DEFAULT_IMAGE_EDIT_MODEL_API_BASE
from veadk.tools.builtin_tools import image_edit as image_edit_module
from veadk.tools.builtin_tools.image_edit import image_edit
from veadk.utils.http_defaults import DEFAULT_CONNECT_TIMEOUT

# Wall-clock ceiling on anything awaited here. Generous enough never to flake,
# short enough that a regression fails CI instead of wedging it.
_HARD_BOUND_SECONDS = 15.0

# How long a stubbed SDK call waits for the event loop to show a sign of life
# before giving up. Only reached when the loop is blocked, i.e. on a regression.
_LOOP_PROBE_BOUND_SECONDS = 3.0

# Event-loop iterations the probe below must observe while the stubbed SDK call
# is still running. One would do; three rules out a coincidental wake-up.
_REQUIRED_TICKS = 3

_ORIGIN_IMAGE = "https://example.invalid/origin.png"
_EDITED_URL = "https://example.invalid/edited.png"
_TOS_URL = "https://tos.example.invalid/edited.png"
_IMAGE_BYTES = b"not-really-a-png"


@pytest.fixture(autouse=True)
def image_edit_env(monkeypatch):
    """Deterministic credentials and endpoint, with no live token lookup.

    ``_get_api_key`` falls back to ``settings.model.api_key``, a cached property
    that can fetch a real Ark token, so the env var short-circuits it before it
    gets there. The other two are cleared because a developer's ``.env`` is
    loaded into ``os.environ`` at import time and would otherwise leak in.
    """
    monkeypatch.setenv("MODEL_EDIT_API_KEY", "test_api_key")
    monkeypatch.delenv("MODEL_EDIT_API_BASE", raising=False)
    monkeypatch.delenv("MODEL_EDIT_NAME", raising=False)


@pytest.fixture(autouse=True)
def no_network():
    """Tripwire: a real request fails the test rather than dialing out.

    The timeout tests build a genuine ``Ark`` client, so this guards against a
    stub going missing and the suite quietly talking to the live endpoint.
    """

    def _explode(*args, **kwargs):
        raise AssertionError("image_edit tests must not perform real HTTP")

    with (
        patch.object(httpx.HTTPTransport, "handle_request", _explode),
        patch.object(httpx.AsyncHTTPTransport, "handle_async_request", _explode),
    ):
        yield


def _tool_context() -> SimpleNamespace:
    """A ToolContext-shaped stub.

    ``image_edit`` writes the resulting URL into ``tool_context.state``; the
    rest is what ``add_span_attributes`` reads off the invocation context. That
    helper swallows its own errors, so the fields exist here only to keep a
    passing test from printing a traceback about them.
    """
    return SimpleNamespace(
        state={},
        agent_name="test_agent",
        _invocation_context=SimpleNamespace(
            app_name="test_app",
            user_id="test_user",
            session=SimpleNamespace(id="test_session"),
        ),
    )


def _item(**overrides) -> dict:
    """One entry of the ``params`` list, defaulting to the ``url`` branch."""
    item = {
        "image_name": "edited",
        "prompt": "make it blue",
        "origin_image": _ORIGIN_IMAGE,
    }
    item.update(overrides)
    return item


def _response(*, url: str = None, b64_json: str = None) -> SimpleNamespace:
    """An ``images.generate`` reply, shaped as the tool consumes it."""
    return SimpleNamespace(
        data=[SimpleNamespace(url=url, b64_json=b64_json)],
        usage=SimpleNamespace(output_tokens=1, total_tokens=2),
    )


def _stub_client(generate) -> MagicMock:
    """An Ark-shaped client whose only live part is ``images.generate``."""
    client = MagicMock()
    client.images.generate.side_effect = generate
    return client


@contextlib.contextmanager
def _driving(generate, upload=None):
    """Patch out everything ``image_edit`` would otherwise do for real.

    ``traceback.print_exc`` is silenced too: the tool prints it on every
    per-item failure, which is expected in the tests that exercise that path
    and would otherwise bury the real output in noise.
    """
    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch.object(
                image_edit_module, "_get_client", return_value=_stub_client(generate)
            )
        )
        stack.enter_context(patch.object(image_edit_module.traceback, "print_exc"))
        if upload is not None:
            stack.enter_context(
                patch.object(image_edit_module, "_upload_image_to_tos", upload)
            )
        yield


async def _run(params: list, tool_context) -> dict:
    """Drive the tool under a hard bound, so a stall fails instead of hangs."""
    return await asyncio.wait_for(image_edit(params, tool_context), _HARD_BOUND_SECONDS)


# --------------------------------------------------------------------------
# 1. the SDK client is built with an explicit, bounded budget
# --------------------------------------------------------------------------


def test_client_carries_the_module_timeout_and_retry_budget():
    """The constructed client must actually hold the configured bounds.

    Sourced from the module constants rather than from literals: retuning the
    budget must not need a test edit, only a code one.
    """
    with image_edit_module._get_client() as client:
        assert client.timeout.read == image_edit_module.DEFAULT_IMAGE_EDIT_READ_TIMEOUT
        assert client.timeout.connect == DEFAULT_CONNECT_TIMEOUT
        assert client.max_retries == image_edit_module.DEFAULT_IMAGE_EDIT_MAX_RETRIES
        # httpx fans the single `timeout=` value out to the remaining phases.
        assert client.timeout.write == image_edit_module.DEFAULT_IMAGE_EDIT_READ_TIMEOUT
        assert client.timeout.pool == image_edit_module.DEFAULT_IMAGE_EDIT_READ_TIMEOUT


def test_connect_budget_is_far_tighter_than_the_read_budget():
    """Reaching an unreachable peer must fail fast, generation may take a while.

    The two halves are different quantities: a TCP/TLS handshake that has not
    completed in seconds is not going to, whereas an image edit legitimately
    runs for minutes. The client must use the shared connect default rather
    than the SDK's minute-long one.
    """
    with image_edit_module._get_client() as client:
        assert client.timeout.connect == DEFAULT_CONNECT_TIMEOUT
        assert client.timeout.connect * 5 <= client.timeout.read, (
            "the connect budget is not meaningfully tighter than the read budget: "
            f"connect={client.timeout.connect}s read={client.timeout.read}s"
        )


def test_bounds_improve_substantially_on_the_ark_sdk_defaults():
    """The whole point of the change: a hung call can no longer hold ~30 minutes.

    The comparison is drawn against a client built the way ``_get_client`` used
    to build one, so it tracks whatever the installed SDK's defaults happen to
    be instead of hardcoding 600s and two retries.
    """
    with (
        image_edit_module._get_client() as bounded,
        Ark(api_key="test_api_key", base_url=DEFAULT_IMAGE_EDIT_MODEL_API_BASE) as sdk,
    ):
        assert bounded.timeout.read * 3 <= sdk.timeout.read, (
            "the read budget is not well below the SDK default: "
            f"{bounded.timeout.read}s vs {sdk.timeout.read}s"
        )
        assert bounded.max_retries < sdk.max_retries

        # Worst case for a single item, which `image_edit` pays once per entry
        # in `params`: the initial attempt plus every retry, each able to run
        # the full read budget.
        bounded_worst = (1 + bounded.max_retries) * bounded.timeout.read
        sdk_worst = (1 + sdk.max_retries) * sdk.timeout.read
        assert bounded_worst * 4 <= sdk_worst, (
            "a single hung item can still hold the tool for "
            f"{bounded_worst}s (SDK default: {sdk_worst}s)"
        )


# --------------------------------------------------------------------------
# 2. the blocking SDK calls run off the event loop
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_generate_runs_off_the_event_loop():
    """``images.generate`` is synchronous, so it must not run on the loop thread."""
    loop_thread = threading.get_ident()
    generate_threads: list[int] = []

    def generate(**kwargs):
        generate_threads.append(threading.get_ident())
        return _response(url=_EDITED_URL)

    tool_context = _tool_context()
    with _driving(generate):
        result = await _run([_item()], tool_context)

    assert generate_threads, "images.generate was never called"
    assert loop_thread not in generate_threads, (
        "the blocking Ark call ran on the event-loop thread "
        f"({loop_thread}); it must go through asyncio.to_thread"
    )
    assert result == {
        "status": "success",
        "success_list": [{"edited": _EDITED_URL}],
        "error_list": [],
    }
    assert tool_context.state["edited_url"] == _EDITED_URL


@pytest.mark.asyncio
async def test_event_loop_keeps_turning_while_generate_blocks():
    """A different thread is only useful if the loop is genuinely free.

    A ticker task counts loop iterations; the stubbed SDK call blocks until it
    has seen the count advance. Off the loop that takes milliseconds -- on it,
    the ticker cannot run at all and the call gives up at the probe bound.
    """
    ticks = {"n": 0}
    observed: list[int] = []

    async def ticker():
        while True:
            ticks["n"] += 1
            await asyncio.sleep(0.01)

    def generate(**kwargs):
        start = ticks["n"]
        deadline = time.monotonic() + _LOOP_PROBE_BOUND_SECONDS
        while ticks["n"] - start < _REQUIRED_TICKS and time.monotonic() < deadline:
            time.sleep(0.01)
        observed.append(ticks["n"] - start)
        return _response(url=_EDITED_URL)

    ticker_task = asyncio.create_task(ticker())
    try:
        with _driving(generate):
            result = await _run([_item()], _tool_context())
    finally:
        ticker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ticker_task

    assert observed and observed[0] >= _REQUIRED_TICKS, (
        "the event loop made no progress while images.generate was in flight "
        f"(observed {observed} iterations in {_LOOP_PROBE_BOUND_SECONDS}s): "
        "the blocking SDK call is stalling the loop"
    )
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_tos_upload_runs_off_the_event_loop():
    """The ``b64_json`` branch uploads to TOS, which blocks just as hard."""
    loop_thread = threading.get_ident()
    generate_threads: list[int] = []
    upload_threads: list[int] = []
    upload_calls: list[tuple] = []

    def generate(**kwargs):
        generate_threads.append(threading.get_ident())
        return _response(b64_json=base64.b64encode(_IMAGE_BYTES).decode())

    def upload(image_bytes, object_key):
        upload_threads.append(threading.get_ident())
        # Recorded rather than asserted here: this runs on a worker thread, and
        # the tool would turn an AssertionError into a silent per-item failure.
        upload_calls.append((image_bytes, object_key))
        return _TOS_URL

    tool_context = _tool_context()
    with _driving(generate, upload=upload):
        result = await _run([_item(response_format="b64_json")], tool_context)

    assert upload_threads, "_upload_image_to_tos was never called"
    assert loop_thread not in generate_threads, (
        "the blocking Ark call ran on the event-loop thread "
        f"({loop_thread}); it must go through asyncio.to_thread"
    )
    assert loop_thread not in upload_threads, (
        "the blocking TOS upload ran on the event-loop thread "
        f"({loop_thread}); it must go through asyncio.to_thread"
    )
    assert upload_calls == [(_IMAGE_BYTES, "edited.png")]
    assert result == {
        "status": "success",
        "success_list": [{"edited": _TOS_URL}],
        "error_list": [],
    }
    assert tool_context.state["edited_url"] == _TOS_URL


# --------------------------------------------------------------------------
# 3. moving the calls off the loop did not change how failures are reported
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_failure_on_the_worker_thread_still_lands_in_error_list():
    """An exception raised off-thread must surface exactly as it did inline.

    ``asyncio.to_thread`` re-raises in the awaiting coroutine, so the tool's
    existing ``except Exception`` still catches it and records the failure per
    item: the bad entry goes to ``error_list``, the good one is unaffected, and
    a partial batch is still reported as ``success``.
    """
    loop_thread = threading.get_ident()
    generate_threads: list[int] = []

    def generate(**kwargs):
        generate_threads.append(threading.get_ident())
        if kwargs["prompt"] == "boom":
            raise RuntimeError("ark refused the edit")
        return _response(url=_EDITED_URL)

    tool_context = _tool_context()
    params = [
        _item(image_name="broken", prompt="boom"),
        _item(image_name="fine"),
    ]
    with _driving(generate):
        result = await _run(params, tool_context)

    assert len(generate_threads) == 2
    assert loop_thread not in generate_threads, (
        "the failing Ark call ran on the event-loop thread; a raising SDK call "
        "must still be offloaded"
    )
    assert result == {
        "status": "success",
        "success_list": [{"fine": _EDITED_URL}],
        "error_list": ["broken"],
    }
    assert "broken_url" not in tool_context.state
    assert tool_context.state["fine_url"] == _EDITED_URL


@pytest.mark.asyncio
async def test_failed_tos_upload_still_lands_in_error_list():
    """``_upload_image_to_tos`` swallows its own errors and returns ``None``.

    Running it on a worker thread must not change that: a falsy return is still
    a per-item failure, and with nothing else in the batch the tool reports
    ``error``.
    """
    loop_thread = threading.get_ident()
    upload_threads: list[int] = []

    def generate(**kwargs):
        return _response(b64_json=base64.b64encode(_IMAGE_BYTES).decode())

    def upload(image_bytes, object_key):
        upload_threads.append(threading.get_ident())
        return None

    tool_context = _tool_context()
    with _driving(generate, upload=upload):
        result = await _run([_item(response_format="b64_json")], tool_context)

    assert upload_threads, "_upload_image_to_tos was never called"
    assert loop_thread not in upload_threads, (
        "the failing TOS upload ran on the event-loop thread; it must still be "
        "offloaded"
    )
    assert result == {
        "status": "error",
        "success_list": [],
        "error_list": ["edited"],
    }
    assert tool_context.state == {}
