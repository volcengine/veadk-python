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

"""Behavior tests for ``veadk.runner.Runner`` and its module helpers.

These cover the ``run()`` orchestration flow (message conversion, session
auto-creation, event collection, llm-call-limit handling, tracing dump,
trace-id logging and the temporary upload toggle), the standalone
``_convert_messages`` media/error branches, ``_upload_image_to_tos``,
``pre_run_process``, ``get_trace_id`` / ``_print_trace_id`` and
``save_session_to_long_term_memory``.

All model, network and storage dependencies are mocked; ``run_async`` is
replaced with an in-memory async generator so no real LLM/agent loop executes.
"""

import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.events.event import Event
from google.genai import types

from veadk.agent import Agent
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runner import (
    Runner,
    _convert_messages,
    _upload_image_to_tos,
    pre_run_process,
)
from veadk.types import MediaMessage

_ENV = {"MODEL_AGENT_API_KEY": "mock_api_key"}


def _make_runner(**kwargs) -> Runner:
    """Build a Runner backed by a real in-memory ShortTermMemory and Agent."""
    agent = Agent()
    stm = ShortTermMemory()
    return Runner(agent=agent, short_term_memory=stm, **kwargs)


def _text_event(text: str, *, thought: bool = False) -> Event:
    return Event(
        author="model",
        content=types.Content(
            role="model", parts=[types.Part(text=text, thought=thought)]
        ),
    )


# ---------------------------------------------------------------------------
# _convert_messages branches
# ---------------------------------------------------------------------------


def test_convert_messages_media_message():
    msg = MediaMessage(text="describe", media="/tmp/pic.png")
    kind = Mock()
    kind.mime = "image/png"
    with (
        patch("veadk.runner.read_file_to_bytes", return_value=b"rawbytes"),
        patch("filetype.guess", return_value=kind),
    ):
        result = _convert_messages(msg, app_name="app", user_id="u", session_id="s")
    assert len(result) == 1
    parts = result[0].parts
    assert parts[0].text == "describe"
    assert parts[1].inline_data.mime_type == "image/png"
    assert parts[1].inline_data.data == b"rawbytes"


def test_convert_messages_unknown_filetype_raises():
    msg = MediaMessage(text="t", media="/tmp/x.bin")
    with (
        patch("veadk.runner.read_file_to_bytes", return_value=b"x"),
        patch("filetype.guess", return_value=None),
        pytest.raises(ValueError, match="Unsupported or unknown file type"),
    ):
        _convert_messages(msg, app_name="a", user_id="u", session_id="s")


def test_convert_messages_unsupported_mime_asserts():
    msg = MediaMessage(text="t", media="/tmp/x.pdf")
    kind = Mock()
    kind.mime = "application/pdf"
    with (
        patch("veadk.runner.read_file_to_bytes", return_value=b"x"),
        patch("filetype.guess", return_value=kind),
        pytest.raises(AssertionError, match="Unsupported media type"),
    ):
        _convert_messages(msg, app_name="a", user_id="u", session_id="s")


def test_convert_messages_mixed_list():
    media = MediaMessage(text="img", media="/tmp/v.mp4")
    kind = Mock()
    kind.mime = "video/mp4"
    with (
        patch("veadk.runner.read_file_to_bytes", return_value=b"vid"),
        patch("filetype.guess", return_value=kind),
    ):
        result = _convert_messages(
            ["hi", media], app_name="a", user_id="u", session_id="s"
        )
    assert len(result) == 2
    assert result[0].parts[0].text == "hi"
    assert result[1].parts[1].inline_data.mime_type == "video/mp4"


def test_convert_messages_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown message type"):
        _convert_messages(12345, app_name="a", user_id="u", session_id="s")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _upload_image_to_tos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_image_to_tos_success_rewrites_display_name():
    part = types.Part(
        inline_data=types.Blob(
            display_name="orig.png", data=b"bytes", mime_type="image/png"
        )
    )
    fake_tos = Mock()
    fake_tos.build_tos_signed_url.return_value = "https://signed/url"
    fake_tos.async_upload_bytes = AsyncMock()
    with patch("veadk.integrations.ve_tos.ve_tos.VeTOS", return_value=fake_tos):
        await _upload_image_to_tos(part, "app", "user", "sess")
    assert part.inline_data is not None
    assert part.inline_data.display_name == "https://signed/url"
    fake_tos.async_upload_bytes.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_image_to_tos_swallows_exceptions():
    part = types.Part(
        inline_data=types.Blob(
            display_name="orig.png", data=b"bytes", mime_type="image/png"
        )
    )
    with patch(
        "veadk.integrations.ve_tos.ve_tos.VeTOS", side_effect=RuntimeError("boom")
    ):
        # Should not raise; exception is logged and swallowed.
        await _upload_image_to_tos(part, "app", "user", "sess")


# ---------------------------------------------------------------------------
# pre_run_process
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pre_run_process_invokes_process_func_when_enabled():
    self_mock = Mock()
    self_mock.upload_inline_data_to_tos = True
    self_mock.app_name = "app"
    process_func = AsyncMock()

    part = types.Part(
        inline_data=types.Blob(display_name="f.png", data=b"d", mime_type="image/png")
    )
    new_message = types.Content(role="user", parts=[part])

    await pre_run_process(self_mock, process_func, new_message, "u", "s")
    process_func.assert_awaited_once_with(part, "app", "u", "s")


@pytest.mark.asyncio
async def test_pre_run_process_skips_when_upload_disabled():
    self_mock = Mock()
    self_mock.upload_inline_data_to_tos = False
    process_func = AsyncMock()
    part = types.Part(
        inline_data=types.Blob(display_name="f.png", data=b"d", mime_type="image/png")
    )
    new_message = types.Content(role="user", parts=[part])
    await pre_run_process(self_mock, process_func, new_message, "u", "s")
    process_func.assert_not_awaited()


# ---------------------------------------------------------------------------
# Runner.__init__ branches
# ---------------------------------------------------------------------------


@patch.dict(os.environ, _ENV)
def test_runner_creates_default_short_term_memory():
    agent = Agent()
    runner = Runner(agent=agent)
    assert runner.short_term_memory is not None
    assert runner.session_service is runner.short_term_memory.session_service
    assert runner.app_name == "veadk_default_app"


@patch.dict(os.environ, _ENV)
def test_runner_run_processor_arg_takes_priority():
    from veadk.processors import NoOpRunProcessor

    custom = NoOpRunProcessor()
    runner = _make_runner(run_processor=custom)
    assert runner.run_processor is custom


@patch.dict(os.environ, _ENV)
def test_runner_inherits_run_processor_from_agent():
    from veadk.processors import NoOpRunProcessor

    agent = Agent()
    agent_processor = NoOpRunProcessor()
    agent.run_processor = agent_processor
    runner = Runner(agent=agent, short_term_memory=ShortTermMemory())
    assert runner.run_processor is agent_processor


# ---------------------------------------------------------------------------
# Runner.run flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch.dict(os.environ, _ENV)
async def test_run_returns_last_text_and_auto_creates_session():
    runner = _make_runner()

    async def fake_run_async(**kwargs):
        yield _text_event("thinking...", thought=True)
        yield _text_event("final answer")

    runner.run_async = fake_run_async  # type: ignore[assignment]

    out = await runner.run("hello", session_id="sess-1")
    assert out == "final answer"

    # The run() flow auto-creates the session in the session service.
    session = await runner.session_service.get_session(
        app_name=runner.app_name,
        user_id=runner.user_id,
        session_id="sess-1",
    )
    assert session is not None


@pytest.mark.asyncio
@patch.dict(os.environ, _ENV)
async def test_run_handles_llm_calls_limit_exceeded():
    runner = _make_runner()

    async def fake_run_async(**kwargs):
        raise LlmCallsLimitExceededError("limit")
        yield  # pragma: no cover - generator marker

    runner.run_async = fake_run_async  # type: ignore[assignment]
    out = await runner.run("hello", session_id="sess-limit")
    assert out == ""


@pytest.mark.asyncio
@patch.dict(os.environ, _ENV)
async def test_run_saves_tracing_when_requested():
    runner = _make_runner()

    async def fake_run_async(**kwargs):
        yield _text_event("done")

    runner.run_async = fake_run_async  # type: ignore[assignment]
    with patch.object(runner, "save_tracing_file") as mock_save:
        await runner.run("hi", session_id="sess-trace", save_tracing_data=True)
    mock_save.assert_called_once_with("sess-trace")


@pytest.mark.asyncio
@patch.dict(os.environ, _ENV)
async def test_run_temporarily_toggles_upload_flag():
    runner = _make_runner()
    assert runner.upload_inline_data_to_tos is False

    captured = {}

    async def fake_run_async(**kwargs):
        captured["during"] = runner.upload_inline_data_to_tos
        yield _text_event("ok")

    runner.run_async = fake_run_async  # type: ignore[assignment]
    await runner.run("hi", session_id="sess-upload", upload_inline_data_to_tos=True)
    assert captured["during"] is True
    # Flag restored after the run.
    assert runner.upload_inline_data_to_tos is False


@pytest.mark.asyncio
@patch.dict(os.environ, _ENV)
async def test_run_uses_run_processor_override():
    runner = _make_runner()

    async def fake_run_async(**kwargs):
        yield _text_event("answer")

    runner.run_async = fake_run_async  # type: ignore[assignment]

    calls = {"count": 0}

    class _Processor:
        def process_run(self, runner, message, **kwargs):
            calls["count"] += 1

            def decorator(func):
                return func

            return decorator

    out = await runner.run(
        "hi",
        session_id="sess-proc",
        run_processor=_Processor(),  # type: ignore[arg-type]
    )
    assert out == "answer"
    assert calls["count"] == 1


@pytest.mark.asyncio
@patch.dict(os.environ, _ENV)
async def test_run_initializes_session_path_when_agent_has_skills():
    runner = _make_runner()
    # Force the skills branch without loading real skills.
    object.__setattr__(runner.agent, "skills", ["alpha"])

    async def fake_run_async(**kwargs):
        yield _text_event("ok")

    runner.run_async = fake_run_async  # type: ignore[assignment]
    with patch(
        "veadk.tools.skills_tools.session_path.initialize_session_path"
    ) as mock_init:
        await runner.run("hi", session_id="sess-skills")
    mock_init.assert_called_once_with("sess-skills")


# ---------------------------------------------------------------------------
# get_trace_id / _print_trace_id
# ---------------------------------------------------------------------------


@patch.dict(os.environ, _ENV)
def test_get_trace_id_non_veadk_agent_returns_unknown():
    from google.adk.agents import LlmAgent

    runner = Runner(agent=LlmAgent(name="plain"), short_term_memory=ShortTermMemory())
    assert runner.get_trace_id() == "<unknown_trace_id>"


@patch.dict(os.environ, _ENV)
def test_get_trace_id_no_tracer_returns_unknown():
    runner = _make_runner()
    assert runner.agent.tracers == []  # type: ignore[attr-defined]
    assert runner.get_trace_id() == "<unknown_trace_id>"


@patch.dict(os.environ, _ENV)
def test_get_trace_id_returns_tracer_value():
    runner = _make_runner()
    tracer = Mock()
    tracer.trace_id = "trace-xyz"
    runner.agent.tracers = [tracer]  # type: ignore[attr-defined]
    assert runner.get_trace_id() == "trace-xyz"


@patch.dict(os.environ, _ENV)
def test_print_trace_id_no_tracer_is_noop():
    runner = _make_runner()
    # Should not raise even with no tracer configured.
    runner._print_trace_id()


@patch.dict(os.environ, _ENV)
def test_print_trace_id_logs_value():
    runner = _make_runner()
    tracer = Mock()
    tracer.trace_id = "trace-abc"
    runner.agent.tracers = [tracer]  # type: ignore[attr-defined]
    runner._print_trace_id()  # exercises the success path


# ---------------------------------------------------------------------------
# save_tracing_file
# ---------------------------------------------------------------------------


@patch.dict(os.environ, _ENV)
def test_save_tracing_file_wrong_agent_type_returns_empty():
    from google.adk.agents import LlmAgent

    runner = Runner(agent=LlmAgent(name="plain"), short_term_memory=ShortTermMemory())
    assert runner.save_tracing_file("sess") == ""


@patch.dict(os.environ, _ENV)
def test_save_tracing_file_no_tracer_returns_empty():
    runner = _make_runner()
    assert runner.save_tracing_file("sess") == ""


@patch.dict(os.environ, _ENV)
def test_save_tracing_file_dumps_and_returns_path():
    runner = _make_runner()
    tracer = Mock()
    tracer.dump.return_value = "/tmp/trace.json"
    runner.agent.tracers = [tracer]  # type: ignore[attr-defined]
    path = runner.save_tracing_file("sess-7")
    assert path == "/tmp/trace.json"
    tracer.dump.assert_called_once_with(user_id=runner.user_id, session_id="sess-7")


@patch.dict(os.environ, _ENV)
def test_save_tracing_file_returns_empty_on_dump_error():
    runner = _make_runner()
    tracer = Mock()
    tracer.dump.side_effect = RuntimeError("disk full")
    runner.agent.tracers = [tracer]  # type: ignore[attr-defined]
    assert runner.save_tracing_file("sess-err") == ""


# ---------------------------------------------------------------------------
# save_session_to_long_term_memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch.dict(os.environ, _ENV)
async def test_save_session_no_long_term_memory_returns_early():
    runner = _make_runner()
    assert runner.long_term_memory is None
    # Should simply warn and return without raising.
    await runner.save_session_to_long_term_memory(session_id="s")


@pytest.mark.asyncio
@patch.dict(os.environ, _ENV)
async def test_save_session_session_not_found_returns_early():
    runner = _make_runner()
    runner.long_term_memory = Mock()
    runner.long_term_memory.add_session_to_memory = AsyncMock()
    runner.session_service.get_session = AsyncMock(return_value=None)  # type: ignore[method-assign]

    await runner.save_session_to_long_term_memory(session_id="missing")
    runner.long_term_memory.add_session_to_memory.assert_not_awaited()


@pytest.mark.asyncio
@patch.dict(os.environ, _ENV)
async def test_save_session_persists_when_found():
    runner = _make_runner()
    runner.long_term_memory = Mock()
    runner.long_term_memory.add_session_to_memory = AsyncMock()

    session = Mock()
    session.id = "sess-found"
    runner.session_service.get_session = AsyncMock(return_value=session)  # type: ignore[method-assign]

    await runner.save_session_to_long_term_memory(
        session_id="sess-found", user_id="bob", app_name="myapp"
    )
    runner.session_service.get_session.assert_awaited_once_with(
        app_name="myapp", user_id="bob", session_id="sess-found"
    )
    runner.long_term_memory.add_session_to_memory.assert_awaited_once()
