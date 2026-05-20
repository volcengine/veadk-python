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

from types import SimpleNamespace

import pytest

from veadk.extensions.feishu_channel import FeishuChannelExtension


class FakeChannel:
    def __init__(self):
        self.handlers = {}
        self.sent_messages = []

    def on(self, event_name, handler):
        self.handlers[event_name] = handler

    async def send(self, chat_id, body, options=None):
        self.sent_messages.append((chat_id, body, options))


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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_extension_ignores_empty_message_by_default():
    runner = FakeRunner()
    channel = FakeChannel()
    extension = FeishuChannelExtension(runner=runner, channel=channel)

    message = build_message(content_text="   ")

    await extension._on_message(message)

    assert runner.calls == []
    assert channel.sent_messages == []
