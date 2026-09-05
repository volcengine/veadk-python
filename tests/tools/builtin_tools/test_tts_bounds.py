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

"""Regression tests for the unbounded waits removed from ``text_to_speech``.

``text_to_speech`` is a synchronous function tool: ADK invokes it inline on the
event loop, so anything that blocks forever inside it stalls the whole process.
Four places could do exactly that, and each is pinned here:

1. the streaming ``session.post`` carried no timeout at all;
2. the ``iter_lines`` loop had no wall-clock deadline -- a server that streams
   valid ``code == 0`` frames forever resets the socket read timeout on every
   frame, so only a deadline ends the loop;
3. the player thread called ``audio_queue.task_done()`` only on the success
   path, so a raising ``output_stream.write`` left the queue with unfinished
   tasks and wedged ``audio_queue.join()`` in the ``finally``;
4. that same ``audio_queue.join()`` -- which takes no timeout -- ran *before*
   the stop event was set, so a player wedged *inside* a blocking
   ``output_stream.write`` (a stalled device: the realistic hang) never
   reached ``task_done()``, never saw a reason to stop, and left the bounded
   thread join below it unreachable.

Nothing here touches the network or an audio device. ``requests.Session`` is
mocked, and ``veadk.utils.audio_manager`` is replaced by a stub module injected
into ``sys.modules``: that module reads ``pyaudio.paInt16`` at import time, so
it cannot even be imported without pyaudio (absent in CI) and *would* open a
real output device on a box that has it. Stubbing -- rather than
``importorskip`` -- keeps the audio-side branches genuinely exercised in CI
instead of silently skipped. ``settings.tool.vespeech.api_key`` is stubbed for
the same reason: it is a ``cached_property`` that falls back to a live token
fetch.

Every test that could hang on a regression is bounded, so a regression fails
the suite instead of freezing it.
"""

import base64
import contextlib
import json
import queue
import sys
import threading
import time
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from veadk.tools.builtin_tools import tts
from veadk.tools.builtin_tools.tts import _audio_player_thread, text_to_speech
from veadk.utils.http_defaults import (
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_STREAM_BUDGET_SECONDS,
)

_AUDIO_FRAME = json.dumps({"code": 0, "data": base64.b64encode(b"pcm").decode()})
_DONE_FRAME = json.dumps({"code": 20000000})


def _tool_context() -> SimpleNamespace:
    """A ToolContext-shaped stub.

    ``text_to_speech`` reads exactly one attribute off the tool context --
    ``tool_context._invocation_context.user_id`` -- so that is all this stubs.
    """
    return SimpleNamespace(_invocation_context=SimpleNamespace(user_id="test_user"))


@pytest.fixture
def tts_env(monkeypatch, tmp_path):
    """Credentials and an output directory, with no network access anywhere."""
    monkeypatch.setenv("TOOL_VESPEECH_APP_ID", "test_app_id")
    monkeypatch.setenv("TOOL_VESPEECH_SPEAKER", "test_speaker")
    monkeypatch.setenv("TOOL_VESPEECH_AUDIO_OUTPUT_PATH", str(tmp_path))
    monkeypatch.setattr(
        tts,
        "settings",
        SimpleNamespace(tool=SimpleNamespace(vespeech=SimpleNamespace(api_key="k"))),
    )


@contextlib.contextmanager
def _stubbed_audio(output_stream=None):
    """Swap in a fake ``veadk.utils.audio_manager`` for the duration of a block.

    With ``output_stream=None`` the device fails to open, which is the headless
    path the tool already takes in CI; passing a stream exercises the player
    thread against a mock instead of real hardware.
    """
    module = types.ModuleType("veadk.utils.audio_manager")
    module.AudioConfig = lambda **kwargs: SimpleNamespace(**kwargs)
    module.input_audio_config = {}
    module.output_audio_config = {}
    if output_stream is None:
        module.AudioDeviceManager = MagicMock(
            side_effect=RuntimeError("no audio device under test")
        )
    else:
        device = MagicMock()
        device.open_output_stream.return_value = output_stream
        module.AudioDeviceManager = MagicMock(return_value=device)
    with patch.dict(sys.modules, {"veadk.utils.audio_manager": module}):
        yield module


def _run_bounded(func, timeout: float = 15.0):
    """Run ``func`` on a daemon thread and fail -- never hang -- on a regression.

    Each of these calls loops forever against the pre-fix code, so the bound is
    what turns a regression into a red test rather than a stuck CI job.
    """
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


def _assert_queue_drains(audio_queue: queue.Queue, timeout: float = 15.0) -> None:
    """Assert ``audio_queue.join()`` returns, without blocking the test on it."""
    joiner = threading.Thread(target=audio_queue.join, daemon=True)
    joiner.start()
    joiner.join(timeout)
    assert not joiner.is_alive(), (
        f"audio_queue.join() still blocked after {timeout}s: "
        f"{audio_queue.unfinished_tasks} task(s) never marked done"
    )


class _JumpingClock:
    """A monotonic clock that leaps forward on every read.

    Deterministic and instant: the deadline trips after a known number of
    frames instead of after a real wall-clock wait.
    """

    def __init__(self, step: float):
        self._now = 0.0
        self._step = step

    def monotonic(self) -> float:
        value = self._now
        self._now += self._step
        return value


def _endless_frames(stop: threading.Event):
    """A server that never stops sending valid audio frames."""
    while True:
        if stop.is_set():
            # Let the worker thread unwind once the assertions are done.
            raise RuntimeError("test tore down the endless stream")
        yield _AUDIO_FRAME


def test_streaming_post_carries_transfer_timeout(tts_env):
    """The streaming POST must pass the shared transfer timeout, not None."""
    response = MagicMock()
    response.iter_lines.return_value = [_AUDIO_FRAME, _DONE_FRAME]

    with _stubbed_audio(), patch.object(tts.requests, "Session") as session_cls:
        session_cls.return_value.post.return_value = response
        result = text_to_speech("hello", _tool_context())

    assert "saved_audio_path" in result
    post = session_cls.return_value.post
    post.assert_called_once()
    assert post.call_args.kwargs["timeout"] == DEFAULT_HTTP_TIMEOUT


def test_endless_frame_stream_trips_wall_clock_deadline(tts_env):
    """Valid frames forever must still end the read loop, via the deadline.

    Every frame resets the socket read timeout, so the ``requests`` timeout
    alone can never fire here -- only the ``time.monotonic()`` deadline does.
    """
    stop = threading.Event()
    response = MagicMock()
    response.iter_lines.return_value = _endless_frames(stop)

    # First read seeds the deadline (0 + budget); each later read jumps a full
    # budget, so the deadline trips on the second pass through the loop.
    clock = _JumpingClock(step=DEFAULT_STREAM_BUDGET_SECONDS)
    fake_time = SimpleNamespace(monotonic=clock.monotonic, sleep=time.sleep)

    try:
        with (
            _stubbed_audio(),
            patch.object(tts.requests, "Session") as session_cls,
            patch.object(tts, "time", fake_time),
        ):
            session_cls.return_value.post.return_value = response
            result = _run_bounded(lambda: text_to_speech("hello", _tool_context()))
    finally:
        stop.set()

    # The new TimeoutError must flow through the existing handler, so the tool
    # keeps its documented error shape instead of raising into the event loop.
    assert isinstance(result, dict)
    assert set(result) == {"error"}
    assert "not finished within" in result["error"]


def test_player_thread_marks_task_done_when_playback_raises():
    """``task_done()`` runs on the failure path too, so the queue can drain."""
    audio_queue: queue.Queue = queue.Queue()
    for _ in range(3):
        audio_queue.put(b"pcm")

    output_stream = MagicMock()
    output_stream.write.side_effect = RuntimeError("audio device went away")
    stop_event = threading.Event()

    worker = threading.Thread(
        target=_audio_player_thread,
        args=(audio_queue, output_stream, stop_event),
        daemon=True,
    )
    worker.start()
    try:
        _assert_queue_drains(audio_queue)
    finally:
        stop_event.set()
        worker.join(timeout=15.0)

    assert audio_queue.unfinished_tasks == 0
    assert output_stream.write.call_count == 3
    assert not worker.is_alive()


def test_failing_playback_does_not_wedge_the_tool(tts_env):
    """End to end: playback raising every time must not block the finally."""
    output_stream = MagicMock()
    output_stream.write.side_effect = RuntimeError("audio device went away")

    response = MagicMock()
    response.iter_lines.return_value = [_AUDIO_FRAME] * 3 + [_DONE_FRAME]

    with (
        _stubbed_audio(output_stream),
        patch.object(tts.requests, "Session") as session_cls,
    ):
        session_cls.return_value.post.return_value = response
        result = _run_bounded(lambda: text_to_speech("hello", _tool_context()))

    assert "saved_audio_path" in result
    assert output_stream.write.call_count == 3
    output_stream.close.assert_called_once()


def test_blocking_playback_teardown_is_bounded_and_logged(tts_env):
    """A player wedged *inside* ``output_stream.write`` must not stall teardown.

    This is the realistic hang, and it is the one nothing queue-shaped can
    catch: the write never returns, so ``task_done()`` never runs and
    ``audio_queue.join()`` -- which takes no timeout -- never returns either.
    Only a wait on the thread itself is bounded, and only if the stop flag is
    already set when it is entered, since a wedged thread cannot observe a flag
    raised after the wait it is blocking. The write parks on an event the test
    releases only once the assertions are done, so the hang here is real rather
    than simulated with a mock thread.
    """
    entered_write = threading.Event()
    release_write = threading.Event()

    def blocking_write(_chunk):
        entered_write.set()
        # Not released while the tool runs: this is a device that went away
        # mid-write, holding the player thread inside PortAudio.
        release_write.wait(30.0)

    output_stream = MagicMock()
    output_stream.write.side_effect = blocking_write

    response = MagicMock()
    response.iter_lines.return_value = [_AUDIO_FRAME] * 3 + [_DONE_FRAME]

    try:
        with (
            _stubbed_audio(output_stream),
            patch.object(tts.requests, "Session") as session_cls,
            patch.object(tts, "_PLAYER_JOIN_TIMEOUT", 0.2),
            patch.object(tts, "logger") as logger,
        ):
            session_cls.return_value.post.return_value = response
            result = _run_bounded(
                lambda: text_to_speech("hello", _tool_context()), timeout=5.0
            )
    finally:
        # Let the wedged daemon player unwind instead of leaking into later tests.
        release_write.set()

    assert entered_write.wait(5.0), "playback never reached the blocking write"
    assert "saved_audio_path" in result
    # Chunks are still unplayed and the thread is still stuck: a correct
    # teardown gave up on the thread and closed the device anyway.
    output_stream.close.assert_called_once()
    assert any(
        "did not exit in time" in str(call) for call in logger.error.call_args_list
    )


def test_healthy_playback_drains_every_queued_chunk(tts_env):
    """A slow but working device still plays out everything already queued.

    This is what put the queue join first in the original teardown, and it has
    to survive the fix: the wait on the player is renewed while the player is
    still marking chunks done, so a backlog that takes longer than a single
    ``_PLAYER_JOIN_TIMEOUT`` window is not cut off mid-sentence. The writes
    sleep for real -- a fake clock cannot make another thread take time -- but
    only briefly, and ``_run_bounded`` still caps the test.
    """
    chunks = 8
    write_seconds = 0.15
    # Deliberately shorter than chunks * write_seconds: a flat bound on the
    # join would truncate the backlog here.
    join_timeout = 0.5

    output_stream = MagicMock()
    output_stream.write.side_effect = lambda _chunk: time.sleep(write_seconds)
    played_before_close: list = []
    output_stream.close.side_effect = lambda: played_before_close.append(
        output_stream.write.call_count
    )

    response = MagicMock()
    response.iter_lines.return_value = [_AUDIO_FRAME] * chunks + [_DONE_FRAME]

    with (
        _stubbed_audio(output_stream),
        patch.object(tts.requests, "Session") as session_cls,
        patch.object(tts, "_PLAYER_JOIN_TIMEOUT", join_timeout),
    ):
        session_cls.return_value.post.return_value = response
        result = _run_bounded(lambda: text_to_speech("hello", _tool_context()))

    assert "saved_audio_path" in result
    assert output_stream.write.call_count == chunks
    # The device is closed only after the last queued chunk has been played.
    assert played_before_close == [chunks]
