from types import SimpleNamespace

import pytest
from google.adk.agents import RunConfig

from veadk import runner as runner_module


class _FakeProcessor:
    def process_run(self, runner, message):
        def decorator(func):
            return func

        return decorator


def _make_runner():
    runner = object.__new__(runner_module.Runner)
    runner.agent = SimpleNamespace(skills=[])
    runner.short_term_memory = None
    runner.app_name = "test-app"
    runner.user_id = "test-user"
    runner.upload_inline_data_to_tos = False
    runner.run_processor = _FakeProcessor()
    runner._print_trace_id = lambda: None
    runner.save_tracing_file = lambda session_id: ""

    async def run_async(**kwargs):
        return
        yield

    runner.run_async = run_async
    return runner


@pytest.mark.asyncio
async def test_run_logs_turn_boundaries(monkeypatch):
    messages: list[str] = []
    monkeypatch.setattr(
        runner_module.logger,
        "info",
        lambda message, *args, **kwargs: messages.append(message),
    )
    monkeypatch.setattr(
        runner_module, "_convert_messages", lambda *args, **kwargs: ["converted"]
    )

    output = await _make_runner().run("hello", run_config=RunConfig())

    assert output == ""
    assert messages[0].startswith("[turn-dispatch] run begin")
    assert messages[0].endswith("messages=1")
    assert messages[-1].startswith("[turn-dispatch] run end")
    assert "output_chars=0" in messages[-1]


@pytest.mark.asyncio
async def test_run_logs_trace_save_boundaries(monkeypatch):
    messages: list[str] = []
    monkeypatch.setattr(
        runner_module.logger,
        "info",
        lambda message, *args, **kwargs: messages.append(message),
    )
    monkeypatch.setattr(
        runner_module, "_convert_messages", lambda *args, **kwargs: ["converted"]
    )

    await _make_runner().run(
        "hello",
        run_config=RunConfig(),
        save_tracing_data=True,
    )

    assert any("trace save begin" in message for message in messages)
    assert any("trace save end" in message for message in messages)


@pytest.mark.asyncio
async def test_run_survives_logging_failure(monkeypatch):
    original_info = runner_module.logger.info

    def fail_info(message, *args, **kwargs):
        if "[turn-dispatch]" in str(message):
            raise RuntimeError("log backend down")
        return original_info(message, *args, **kwargs)

    monkeypatch.setattr(runner_module.logger, "info", fail_info)
    monkeypatch.setattr(
        runner_module, "_convert_messages", lambda *args, **kwargs: ["converted"]
    )

    assert await _make_runner().run("hello", run_config=RunConfig()) == ""
