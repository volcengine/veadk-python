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
        ("oc_chat", {"text": "echo:你好"}, {"reply_to": "om_001"})
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
