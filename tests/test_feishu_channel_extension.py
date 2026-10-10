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

import asyncio
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest

from veadk.extensions.feishu_channel import (
    FeishuChannelExtension,
    _call_in_fresh_event_loop,
    _format_tool_payload,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeChannel:
    def __init__(self):
        self.handlers = {}
        self.sent_messages = []

    def on(self, event_name, handler):
        self.handlers[event_name] = handler

    async def send(self, chat_id, body, options=None):
        self.sent_messages.append((chat_id, body, options))


class FakeStreamController:
    def __init__(self):
        self.chunks = []

    async def append(self, chunk):
        self.chunks.append(chunk)


class FakeStreamChannel(FakeChannel):
    def __init__(self):
        super().__init__()
        self.stream_calls = []

    async def stream(self, chat_id, spec, options=None):
        controller = FakeStreamController()
        await spec["markdown"](controller)
        if controller.chunks:
            self.stream_calls.append((chat_id, controller.chunks, options))


class FakeBlockingChannel(FakeChannel):
    def __init__(self):
        super().__init__()
        self.connect_thread_id = None
        self.disconnect_thread_id = None
        self.connect_loop_running = None
        self.disconnect_loop_running = None

    def connect(self):
        self.connect_thread_id = threading.get_ident()
        self.connect_loop_running = asyncio.get_event_loop().is_running()
        return "connected"

    def disconnect(self):
        self.disconnect_thread_id = threading.get_ident()
        self.disconnect_loop_running = asyncio.get_event_loop().is_running()
        return "disconnected"


class FakeLoopBoundChannel(FakeChannel):
    created = []

    def __init__(self, **kwargs):
        super().__init__()
        self.kwargs = kwargs
        self.init_thread_id = threading.get_ident()
        try:
            self.init_loop_running = asyncio.get_event_loop().is_running()
        except RuntimeError:
            self.init_loop_running = False
        self.connect_thread_id = None
        self.connect_loop_running = None
        FakeLoopBoundChannel.created.append(self)

    def connect(self):
        self.connect_thread_id = threading.get_ident()
        try:
            self.connect_loop_running = asyncio.get_event_loop().is_running()
        except RuntimeError:
            self.connect_loop_running = False
        return "connected"


class FakeLegacyChannel(FakeChannel):
    created = []

    def __init__(self, **kwargs):
        super().__init__()
        self.kwargs = kwargs
        FakeLegacyChannel.created.append(self)


class FakeStartStopChannel(FakeChannel):
    def __init__(self):
        super().__init__()
        self.start_called = False
        self.stop_called = False
        self.start_loop_running = None
        self.stop_loop_running = None

    async def connect(self):
        raise RuntimeError("async connect should not be used")

    def start(self):
        self.start_called = True
        self.start_loop_running = asyncio.get_event_loop().is_running()
        return "started"

    def stop(self):
        self.stop_called = True
        self.stop_loop_running = asyncio.get_event_loop().is_running()
        return "stopped"


class FakeRunner:
    def __init__(self):
        self.calls = []

    async def run(self, messages, user_id="", session_id="", **kwargs):
        self.calls.append(
            {
                "messages": messages,
                "user_id": user_id,
                "session_id": session_id,
            }
        )
        return f"echo:{messages}"


class FakeStreamingMemory:
    def __init__(self):
        self.sessions = []
        self.session_service = object()

    async def create_session(self, app_name, user_id, session_id):
        self.sessions.append(
            {"app_name": app_name, "user_id": user_id, "session_id": session_id}
        )
        return True


class FakeStreamingRunner:
    def __init__(self):
        self.app_name = "stream_app"
        self.short_term_memory = FakeStreamingMemory()
        self.run_async_calls = []

    async def run_async(self, user_id, session_id, new_message, run_config=None):
        self.run_async_calls.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "new_message": new_message,
                "run_config": run_config,
            }
        )
        yield SimpleNamespace(
            partial=True,
            content=SimpleNamespace(
                parts=[
                    SimpleNamespace(text="hel", thought=False),
                    SimpleNamespace(text="thinking", thought=True),
                ]
            ),
        )
        yield SimpleNamespace(
            partial=True,
            content=SimpleNamespace(parts=[SimpleNamespace(text="lo", thought=False)]),
        )


def build_stream_event(
    *,
    partial=False,
    parts=None,
    calls=None,
    responses=None,
):
    return SimpleNamespace(
        partial=partial,
        content=SimpleNamespace(parts=parts or []),
        get_function_calls=lambda: calls or [],
        get_function_responses=lambda: responses or [],
    )


class FakeDetailedStreamingRunner(FakeStreamingRunner):
    async def run_async(self, user_id, session_id, new_message, run_config=None):
        self.run_async_calls.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "new_message": new_message,
                "run_config": run_config,
            }
        )
        call = SimpleNamespace(
            id="call-1",
            name="bash",
            args={"command": "printf ok", "api_key": "secret-value"},
        )
        response = SimpleNamespace(
            id="call-1",
            name="bash",
            response={"output": "ok", "access_token": "secret-token"},
        )
        thinking = "The\noutput\nshows one item: skills.\nI'll report it."
        yield build_stream_event(
            partial=True,
            parts=[SimpleNamespace(text="The\noutput\n", thought=True)],
        )
        yield build_stream_event(
            partial=True,
            parts=[
                SimpleNamespace(
                    text="shows one item: skills.\nI'll report it.", thought=True
                )
            ],
        )
        # Providers may repeat the accumulated thinking in a completed event.
        yield build_stream_event(
            parts=[SimpleNamespace(text=thinking, thought=True)],
        )
        yield build_stream_event(calls=[call])
        yield build_stream_event(calls=[call])
        yield build_stream_event(responses=[response])
        yield build_stream_event(
            partial=True,
            parts=[SimpleNamespace(text="完成", thought=False)],
        )
        # Some providers insert an empty reasoning event immediately before
        # repeating the completed answer.
        yield build_stream_event(
            partial=True,
            parts=[SimpleNamespace(text="\n", thought=True)],
        )
        yield build_stream_event(
            parts=[SimpleNamespace(text="完成", thought=False)],
        )
        yield build_stream_event(
            partial=True,
            parts=[SimpleNamespace(text=".", thought=True)],
        )


class FakeSeparateToolCardRunner(FakeStreamingRunner):
    async def run_async(self, user_id, session_id, new_message, run_config=None):
        calls = [
            SimpleNamespace(id="call-1", name="bash", args={"command": "one"}),
            SimpleNamespace(id="call-2", name="python", args={"code": "two"}),
        ]
        responses = [
            SimpleNamespace(
                id="call-2",
                name="python",
                response={"status": "failed", "error": "bad"},
            ),
            SimpleNamespace(
                id="call-1",
                name="bash",
                response={"output": "ok"},
            ),
        ]
        yield build_stream_event(calls=calls)
        yield build_stream_event(calls=calls)
        yield build_stream_event(responses=responses)
        yield build_stream_event(responses=responses)
        yield build_stream_event(
            partial=True,
            parts=[SimpleNamespace(text="done", thought=False)],
        )


class FakeToolOnlyRunner(FakeStreamingRunner):
    async def run_async(self, user_id, session_id, new_message, run_config=None):
        call = SimpleNamespace(id="call-1", name="bash", args={"command": "one"})
        response = SimpleNamespace(
            id="call-1",
            name="bash",
            response={"output": "ok"},
        )
        yield build_stream_event(calls=[call])
        yield build_stream_event(responses=[response])


def build_message(**overrides):
    message = SimpleNamespace(
        id="om_001",
        message_id="om_001",
        chat_id="oc_chat",
        chat_type="p2p",
        thread_id="",
        reply_to_message_id="",
        content_text="你好",
        sender_id="ou_sender",
        sender=SimpleNamespace(
            union_id="on_union",
            open_id="ou_sender",
            user_id="u_sender",
        ),
        conversation=SimpleNamespace(
            chat_id="oc_chat",
            chat_type="p2p",
            thread_id="",
        ),
        reply=SimpleNamespace(message_id=""),
    )
    for key, value in overrides.items():
        setattr(message, key, value)
    return message


def test_tool_payload_is_redacted_and_truncated():
    rendered = _format_tool_payload(
        {
            "password": "do-not-show",
            "nested": {"authorization": "Bearer secret"},
            "output": "x" * 200,
        },
        max_length=100,
    )

    assert len(rendered) == 100
    assert rendered.endswith("…")
    assert "do-not-show" not in rendered
    assert "Bearer secret" not in rendered
    assert '"password": "***"' in rendered


def test_tool_payload_fallback_preserves_redaction_and_escapes_fences():
    rendered = _format_tool_payload(
        {("unsupported", "json-key"): "```", "password": "do-not-show"},
        max_length=4000,
    )

    assert "do-not-show" not in rendered
    assert "***" in rendered
    assert "```" not in rendered


@pytest.mark.anyio
async def test_shutdown_closes_channel_then_drains_accepted_message():
    entered = asyncio.Event()
    finish = asyncio.Event()
    closed = asyncio.Event()

    class DrainingChannel(FakeChannel):
        async def disconnect(self):
            closed.set()

    async def handler(context):
        entered.set()
        await finish.wait()
        return "finished"

    channel = DrainingChannel()
    extension = FeishuChannelExtension(
        runner=FakeRunner(), channel=channel, message_handler=handler
    )
    extension._loop = asyncio.get_running_loop()
    await extension._on_message(build_message())
    await entered.wait()
    shutdown = asyncio.create_task(extension.shutdown(drain_timeout=1))
    await closed.wait()

    assert extension.is_draining
    assert not shutdown.done()
    assert len(extension._inflight) == 1

    finish.set()
    await shutdown
    assert channel.sent_messages[0][1] == {"text": "finished"}
    assert not extension._inflight


@pytest.mark.anyio
async def test_separate_tool_card_is_settled_when_runner_fails():
    class FailingRunner(FakeStreamingRunner):
        async def run_async(self, **kwargs):
            yield build_stream_event(
                calls=[SimpleNamespace(id="pending", name="bash", args={})]
            )
            raise RuntimeError("runner failed")

    channel = FakeStreamChannel()
    extension = FeishuChannelExtension(
        runner=FailingRunner(),
        channel=channel,
        streaming=True,
        show_tool_calls=True,
        separate_tool_call_cards=True,
    )

    with pytest.raises(RuntimeError, match="runner failed"):
        await asyncio.wait_for(extension._on_message(build_message()), timeout=10)

    assert len(channel.stream_calls) == 1
    assert "pending" not in "".join(channel.stream_calls[0][1])


@pytest.mark.anyio
async def test_separate_card_failure_during_cleanup_is_propagated():
    class MissingResultRunner(FakeStreamingRunner):
        async def run_async(self, **kwargs):
            yield build_stream_event(
                calls=[SimpleNamespace(id="pending", name="bash", args={})]
            )

    class FailingCardChannel(FakeStreamChannel):
        async def stream(self, chat_id, spec, options=None):
            controller = FakeStreamController()
            await spec["markdown"](controller)
            if controller.chunks:
                raise RuntimeError("card failed")

    extension = FeishuChannelExtension(
        runner=MissingResultRunner(),
        channel=FailingCardChannel(),
        streaming=True,
        show_tool_calls=True,
        separate_tool_call_cards=True,
    )

    with pytest.raises(RuntimeError, match="card failed"):
        await extension._on_message(build_message())


def test_separate_cards_and_topic_can_be_enabled_from_environment(monkeypatch):
    monkeypatch.setenv("TOOL_FEISHU_CHANNEL_SEPARATE_TOOL_CALL_CARDS", "true")
    monkeypatch.setenv("TOOL_FEISHU_CHANNEL_SEPARATE_THINKING_CARD", "true")
    monkeypatch.setenv("TOOL_FEISHU_CHANNEL_CREATE_TOPIC", "true")

    extension = FeishuChannelExtension(runner=FakeRunner(), channel=FakeChannel())

    assert extension.separate_tool_call_cards is True
    assert extension.separate_thinking_card is True
    assert extension.create_topic is True


@pytest.mark.anyio
async def test_extension_uses_union_id_and_thread_id():
    runner = FakeRunner()
    channel = FakeChannel()
    extension = FeishuChannelExtension(runner=runner, channel=channel)

    message = build_message(
        thread_id="thread_1",
        conversation=SimpleNamespace(
            chat_id="oc_chat",
            chat_type="group",
            thread_id="thread_1",
        ),
    )

    await extension._on_message(message)

    assert runner.calls == [
        {
            "messages": "你好",
            "user_id": "on_union",
            "session_id": "thread_1",
        }
    ]
    assert channel.sent_messages == [
        (
            "oc_chat",
            {"text": "echo:你好"},
            {"reply_to": "om_001", "reply_in_thread": True},
        )
    ]


@pytest.mark.anyio
async def test_extension_falls_back_to_chat_id_when_thread_missing():
    runner = FakeRunner()
    channel = FakeChannel()
    extension = FeishuChannelExtension(runner=runner, channel=channel)

    message = build_message(
        sender=SimpleNamespace(union_id="", open_id="ou_fallback", user_id="u_sender")
    )

    await extension._on_message(message)

    assert runner.calls[0]["user_id"] == "ou_fallback"
    assert runner.calls[0]["session_id"] == "oc_chat"


@pytest.mark.anyio
async def test_extension_ignores_empty_message_by_default():
    runner = FakeRunner()
    channel = FakeChannel()
    extension = FeishuChannelExtension(runner=runner, channel=channel)

    message = build_message(content_text="   ")

    await extension._on_message(message)

    assert runner.calls == []
    assert channel.sent_messages == []


@pytest.mark.anyio
async def test_extension_streaming_uses_markdown_producer_controller():
    runner = FakeStreamingRunner()
    channel = FakeStreamChannel()
    extension = FeishuChannelExtension(
        runner=runner,
        channel=channel,
        streaming=True,
    )

    await extension._on_message(build_message())

    assert runner.short_term_memory.sessions == [
        {
            "app_name": "stream_app",
            "user_id": "on_union",
            "session_id": "oc_chat",
        }
    ]
    assert len(runner.run_async_calls) == 1
    assert channel.stream_calls == [("oc_chat", ["hel", "lo"], {"reply_to": "om_001"})]


@pytest.mark.anyio
async def test_extension_streams_thinking_tool_calls_results_and_answer():
    runner = FakeDetailedStreamingRunner()
    channel = FakeStreamChannel()
    extension = FeishuChannelExtension(
        runner=runner,
        channel=channel,
        streaming=True,
        show_thinking=True,
        show_tool_calls=True,
        show_tool_results=True,
    )

    await extension._on_message(build_message())

    assert len(channel.stream_calls) == 1
    rendered = "".join(channel.stream_calls[0][1])
    assert rendered.count("💭 **Thinking**") == 1
    assert rendered.count("🔧 **调用工具 `bash`**") == 1
    assert rendered.count("✅ **工具 `bash` 返回**") == 1
    assert rendered.count("💬 **回答**") == 1
    assert "The output shows one item: skills. I'll report it." in rendered
    assert "The\noutput" not in rendered
    assert rendered.count("完成") == 1
    assert rendered.endswith("完成")
    assert '"api_key": "***"' in rendered
    assert '"access_token": "***"' in rendered
    assert "secret-value" not in rendered
    assert "secret-token" not in rendered
    assert rendered.index("Thinking") < rendered.index("调用工具")
    assert rendered.index("调用工具") < rendered.index("工具 `bash` 返回")
    assert rendered.index("工具 `bash` 返回") < rendered.index("回答")


@pytest.mark.anyio
async def test_extension_streams_each_tool_call_and_result_in_separate_card():
    runner = FakeSeparateToolCardRunner()
    channel = FakeStreamChannel()
    extension = FeishuChannelExtension(
        runner=runner,
        channel=channel,
        streaming=True,
        show_tool_calls=True,
        show_tool_results=True,
        separate_tool_call_cards=True,
    )

    await extension._on_message(build_message())

    assert len(channel.stream_calls) == 3
    rendered_cards = ["".join(call[1]) for call in channel.stream_calls]
    bash_card = next(card for card in rendered_cards if "`bash`" in card)
    python_card = next(card for card in rendered_cards if "`python`" in card)
    answer_card = next(card for card in rendered_cards if card == "done")

    assert bash_card.count("🔧 **调用工具 `bash`**") == 1
    assert bash_card.count("✅ **工具 `bash` 返回**") == 1
    assert '"command": "one"' in bash_card
    assert '"output": "ok"' in bash_card
    assert "python" not in bash_card

    assert python_card.count("🔧 **调用工具 `python`**") == 1
    assert python_card.count("❌ **工具 `python` 返回**") == 1
    assert '"code": "two"' in python_card
    assert '"error": "bad"' in python_card
    assert "bash" not in python_card
    assert answer_card == "done"


@pytest.mark.anyio
async def test_extension_streams_thinking_tools_and_answer_as_topic_cards():
    runner = FakeDetailedStreamingRunner()
    channel = FakeStreamChannel()
    extension = FeishuChannelExtension(
        runner=runner,
        channel=channel,
        streaming=True,
        show_thinking=True,
        show_tool_calls=True,
        show_tool_results=True,
        separate_tool_call_cards=True,
        separate_thinking_card=True,
        create_topic=True,
    )

    await extension._on_message(build_message())

    assert len(channel.stream_calls) == 3
    rendered_cards = ["".join(call[1]) for call in channel.stream_calls]
    thinking_card = next(card for card in rendered_cards if "Thinking" in card)
    tool_card = next(card for card in rendered_cards if "`bash`" in card)
    answer_card = next(card for card in rendered_cards if card == "完成")

    assert "The output shows one item: skills. I'll report it." in thinking_card
    assert "调用工具" not in thinking_card
    assert "回答" not in thinking_card
    assert tool_card.count("🔧 **调用工具 `bash`**") == 1
    assert tool_card.count("✅ **工具 `bash` 返回**") == 1
    assert "Thinking" not in tool_card
    assert answer_card == "完成"
    assert all(
        call[2] == {"reply_to": "om_001", "reply_in_thread": True}
        for call in channel.stream_calls
    )


@pytest.mark.anyio
async def test_extension_does_not_create_cards_for_missing_stages():
    channel = FakeStreamChannel()
    extension = FeishuChannelExtension(
        runner=FakeToolOnlyRunner(),
        channel=channel,
        streaming=True,
        show_thinking=True,
        show_tool_calls=True,
        show_tool_results=True,
        separate_tool_call_cards=True,
        separate_thinking_card=True,
        create_topic=True,
    )

    await extension._on_message(build_message())

    assert len(channel.stream_calls) == 1
    rendered = "".join(channel.stream_calls[0][1])
    assert "🔧 **调用工具 `bash`**" in rendered
    assert "✅ **工具 `bash` 返回**" in rendered
    assert "Thinking" not in rendered
    assert "回答" not in rendered


@pytest.mark.anyio
async def test_extension_runs_sync_channel_connect_in_worker_thread():
    runner = FakeRunner()
    channel = FakeBlockingChannel()
    extension = FeishuChannelExtension(runner=runner, channel=channel)
    main_thread_id = threading.get_ident()

    assert await extension.connect() == "connected"
    assert await extension.disconnect() == "disconnected"

    assert channel.connect_thread_id is not None
    assert channel.disconnect_thread_id is not None
    assert channel.connect_thread_id != main_thread_id
    assert channel.disconnect_thread_id != main_thread_id
    assert channel.connect_loop_running is False
    assert channel.disconnect_loop_running is False


@pytest.mark.anyio
async def test_extension_can_be_constructed_and_connected_in_worker_thread(monkeypatch):
    fake_lark = ModuleType("lark_oapi")
    fake_channel_module = ModuleType("lark_oapi.channel")
    fake_channel_module.FeishuChannel = FakeLoopBoundChannel
    monkeypatch.setitem(sys.modules, "lark_channel", None)
    monkeypatch.setitem(sys.modules, "lark_oapi", fake_lark)
    monkeypatch.setitem(sys.modules, "lark_oapi.channel", fake_channel_module)
    FakeLoopBoundChannel.created = []
    main_thread_id = threading.get_ident()

    def build_and_connect():
        extension = FeishuChannelExtension(
            runner=FakeRunner(),
            app_id="cli_test",
            app_secret="secret",
            channel_kwargs={"transport": "ws"},
        )
        return extension.channel.connect()

    assert (
        await asyncio.to_thread(_call_in_fresh_event_loop, build_and_connect)
        == "connected"
    )

    channel = FakeLoopBoundChannel.created[0]
    assert channel.kwargs == {
        "app_id": "cli_test",
        "app_secret": "secret",
        "transport": "ws",
    }
    assert channel.init_thread_id != main_thread_id
    assert channel.connect_thread_id == channel.init_thread_id
    assert channel.init_loop_running is False
    assert channel.connect_loop_running is False


def test_extension_prefers_lark_channel_sdk(monkeypatch):
    fake_lark_channel = ModuleType("lark_channel")
    fake_lark_channel.FeishuChannel = FakeLoopBoundChannel
    fake_lark_oapi = ModuleType("lark_oapi")
    fake_legacy_channel_module = ModuleType("lark_oapi.channel")
    fake_legacy_channel_module.FeishuChannel = FakeLegacyChannel
    monkeypatch.setitem(sys.modules, "lark_channel", fake_lark_channel)
    monkeypatch.setitem(sys.modules, "lark_oapi", fake_lark_oapi)
    monkeypatch.setitem(sys.modules, "lark_oapi.channel", fake_legacy_channel_module)
    FakeLoopBoundChannel.created = []
    FakeLegacyChannel.created = []

    extension = FeishuChannelExtension(
        runner=FakeRunner(),
        app_id="cli_test",
        app_secret="secret",
        channel_kwargs={"transport": "ws"},
    )

    assert extension.channel is FakeLoopBoundChannel.created[0]
    assert FakeLegacyChannel.created == []


@pytest.mark.anyio
async def test_extension_prefers_sync_start_stop_over_async_connect():
    runner = FakeRunner()
    channel = FakeStartStopChannel()
    extension = FeishuChannelExtension(runner=runner, channel=channel)

    assert await extension.connect() == "started"
    assert await extension.disconnect() == "stopped"

    assert channel.start_called is True
    assert channel.stop_called is True
    assert channel.start_loop_running is False
    assert channel.stop_loop_running is False
