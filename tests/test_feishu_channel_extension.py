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
from types import SimpleNamespace

import pytest

from veadk.extensions.feishu_channel import FeishuChannelExtension


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
            content=SimpleNamespace(
                parts=[
                    SimpleNamespace(text="hel", thought=False),
                    SimpleNamespace(text="thinking", thought=True),
                ]
            )
        )
        yield SimpleNamespace(
            content=SimpleNamespace(parts=[SimpleNamespace(text="lo", thought=False)])
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
async def test_concurrent_mode_isolates_session_per_sender():
    """In concurrent mode, two senders in the same chat get separate sessions
    (chat_id:user_id) so parallel runs don't share one chat session."""
    runner = FakeRunner()
    channel = FakeChannel()
    extension = FeishuChannelExtension(runner=runner, channel=channel, concurrent=True)

    a = build_message(
        message_id="om_a",
        sender=SimpleNamespace(union_id="on_a", open_id="ou_a", user_id="u_a"),
    )
    b = build_message(
        message_id="om_b",
        sender=SimpleNamespace(union_id="on_b", open_id="ou_b", user_id="u_b"),
    )

    await asyncio.gather(extension._on_message(a), extension._on_message(b))

    sessions = {c["user_id"]: c["session_id"] for c in runner.calls}
    assert sessions == {
        "on_a": "oc_chat:on_a",
        "on_b": "oc_chat:on_b",
    }


@pytest.mark.anyio
async def test_default_mode_shares_chat_session():
    """Without concurrent mode, senders in the same chat share the chat-wide
    session (the historical behavior)."""
    runner = FakeRunner()
    channel = FakeChannel()
    extension = FeishuChannelExtension(runner=runner, channel=channel)

    a = build_message(
        message_id="om_a",
        sender=SimpleNamespace(union_id="on_a", open_id="ou_a", user_id="u_a"),
    )
    b = build_message(
        message_id="om_b",
        sender=SimpleNamespace(union_id="on_b", open_id="ou_b", user_id="u_b"),
    )

    await asyncio.gather(extension._on_message(a), extension._on_message(b))

    assert {c["session_id"] for c in runner.calls} == {"oc_chat"}


@pytest.mark.anyio
async def test_concurrent_mode_caps_in_flight_runs():
    """max_concurrency bounds how many runs are in flight at once."""
    peak = 0
    active = 0
    gate = asyncio.Event()

    class BlockingRunner:
        def __init__(self):
            self.calls = []

        async def run(self, messages, user_id="", session_id="", **kwargs):
            nonlocal peak, active
            active += 1
            peak = max(peak, active)
            self.calls.append(session_id)
            await gate.wait()
            active -= 1
            return "ok"

    runner = BlockingRunner()
    extension = FeishuChannelExtension(
        runner=runner, channel=FakeChannel(), concurrent=True, max_concurrency=2
    )

    messages = [
        build_message(
            message_id=f"om_{i}",
            sender=SimpleNamespace(
                union_id=f"on_{i}", open_id=f"ou_{i}", user_id=f"u_{i}"
            ),
        )
        for i in range(5)
    ]
    tasks = [asyncio.create_task(extension._on_message(m)) for m in messages]
    # let the semaphore admit up to the cap, then release everyone
    await asyncio.sleep(0.05)
    admitted = peak
    gate.set()
    await asyncio.gather(*tasks)

    assert admitted == 2
    assert peak == 2
    assert len(runner.calls) == 5


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
