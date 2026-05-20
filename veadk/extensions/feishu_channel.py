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

import inspect
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from veadk.runner import Runner

logger = get_logger(__name__)

MessageHandler = Callable[["FeishuMessageContext"], Awaitable[str | None] | str | None]
SessionIdFactory = Callable[[Any], str]
UserIdFactory = Callable[[Any], str]


def _coalesce(*values: Any) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def _read_attr(obj: Any, *path: str) -> Any:
    current = obj
    for key in path:
        if current is None:
            return None
        current = getattr(current, key, None)
    return current


@dataclass(slots=True)
class FeishuMessageContext:
    message_id: str
    chat_id: str
    chat_type: str
    thread_id: str
    reply_to_message_id: str
    user_id: str
    session_id: str
    union_id: str
    open_id: str
    raw_message: Any
    text: str


class FeishuChannelExtension:
    """Bridge a Feishu bot channel with a VeADK runner.

    The extension subscribes to normalized ``message`` events from
    ``lark_oapi.channel.FeishuChannel`` and forwards the incoming text to a VeADK
    ``Runner``. It maps Feishu sender identity to VeADK ``user_id`` and Feishu
    conversation/thread identity to VeADK ``session_id`` so existing short-term
    memory, long-term memory and tracing continue to work without changes.
    """

    def __init__(
        self,
        runner: "Runner",
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
        channel: Any | None = None,
        session_id_factory: SessionIdFactory | None = None,
        user_id_factory: UserIdFactory | None = None,
        message_handler: MessageHandler | None = None,
        response_formatter: Callable[[str], dict[str, str]] | None = None,
        reply_in_thread: bool = True,
        ignore_empty_messages: bool = True,
        channel_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.runner = runner
        self.session_id_factory = session_id_factory or self.default_session_id_factory
        self.user_id_factory = user_id_factory or self.default_user_id_factory
        self.message_handler = message_handler
        self.response_formatter = response_formatter or self.default_response_formatter
        self.reply_in_thread = reply_in_thread
        self.ignore_empty_messages = ignore_empty_messages

        if channel is not None:
            self.channel = channel
        else:
            self.channel = self._build_channel(
                app_id=app_id,
                app_secret=app_secret,
                channel_kwargs=channel_kwargs,
            )

        self.channel.on("message", self._on_message)

    @staticmethod
    def default_user_id_factory(message: Any) -> str:
        sender = _read_attr(message, "sender")
        user_id = _coalesce(
            getattr(sender, "union_id", None),
            getattr(sender, "open_id", None),
            getattr(sender, "user_id", None),
            getattr(message, "sender_id", None),
        )
        if user_id:
            return user_id
        raise ValueError("Cannot resolve Feishu sender identity into a VeADK user_id.")

    @staticmethod
    def default_session_id_factory(message: Any) -> str:
        thread_id = _coalesce(
            _read_attr(message, "conversation", "thread_id"),
            getattr(message, "thread_id", None),
            getattr(message, "reply_to_message_id", None),
        )
        chat_id = _coalesce(
            getattr(message, "chat_id", None),
            _read_attr(message, "conversation", "chat_id"),
        )
        return thread_id or chat_id or getattr(message, "message_id", "")

    @staticmethod
    def default_response_formatter(text: str) -> dict[str, str]:
        return {"text": text}

    async def connect(self) -> Any:
        return await self._maybe_await(self.channel.connect())

    async def disconnect(self) -> Any:
        disconnect = getattr(self.channel, "disconnect", None)
        if disconnect is None:
            return None
        result = disconnect()
        if inspect.isawaitable(result):
            return await result
        return result

    async def handle_webhook_request(
        self, headers: dict[str, str], body: bytes | str
    ) -> Any:
        handler = getattr(self.channel, "handle_webhook_request", None)
        if handler is None:
            raise AttributeError("Current channel does not support webhook requests.")
        result = handler(headers, body)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _on_message(self, message: Any) -> None:
        text = str(getattr(message, "content_text", "") or "").strip()
        if self.ignore_empty_messages and not text:
            logger.debug(
                f"Ignore empty Feishu message: {getattr(message, 'message_id', '')}"
            )
            return

        context = self.build_message_context(message=message, text=text)

        if self.message_handler is not None:
            response_text = await self._maybe_await(self.message_handler(context))
        else:
            response_text = await self.runner.run(
                messages=context.text,
                user_id=context.user_id,
                session_id=context.session_id,
            )

        if not response_text:
            return

        send_options = {}
        if self.reply_in_thread and context.message_id:
            send_options["reply_to"] = context.message_id

        await self._maybe_await(
            self.channel.send(
                context.chat_id,
                self.response_formatter(str(response_text)),
                send_options,
            )
        )

    def build_message_context(
        self, message: Any, text: str | None = None
    ) -> FeishuMessageContext:
        user_id = self.user_id_factory(message)
        session_id = self.session_id_factory(message)
        message_id = _coalesce(
            getattr(message, "message_id", None),
            getattr(message, "id", None),
        )
        chat_id = _coalesce(
            getattr(message, "chat_id", None),
            _read_attr(message, "conversation", "chat_id"),
        )
        chat_type = _coalesce(
            getattr(message, "chat_type", None),
            _read_attr(message, "conversation", "chat_type"),
        )
        thread_id = _coalesce(
            getattr(message, "thread_id", None),
            _read_attr(message, "conversation", "thread_id"),
        )
        reply_to_message_id = _coalesce(
            getattr(message, "reply_to_message_id", None),
            _read_attr(message, "reply", "message_id"),
        )
        union_id = _coalesce(_read_attr(message, "sender", "union_id"))
        open_id = _coalesce(
            _read_attr(message, "sender", "open_id"),
            getattr(message, "sender_id", None),
        )

        return FeishuMessageContext(
            message_id=message_id,
            chat_id=chat_id,
            chat_type=chat_type,
            thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
            user_id=user_id,
            session_id=session_id,
            union_id=union_id,
            open_id=open_id,
            raw_message=message,
            text=text
            if text is not None
            else str(getattr(message, "content_text", "") or ""),
        )

    def _build_channel(
        self,
        *,
        app_id: str | None,
        app_secret: str | None,
        channel_kwargs: dict[str, Any] | None,
    ) -> Any:
        try:
            from lark_oapi.channel import FeishuChannel
        except ImportError as exc:
            raise ImportError(
                "Feishu channel extension requires `lark-oapi`. "
                "Install `veadk-python[extensions]` or `pip install lark-oapi`."
            ) from exc

        resolved_app_id = app_id or os.getenv("TOOL_FEISHU_CHANNEL_APP_ID") or os.getenv(
            "TOOL_LARK_ENDPOINT"
        )
        resolved_app_secret = app_secret or os.getenv(
            "TOOL_FEISHU_CHANNEL_APP_SECRET"
        ) or os.getenv("TOOL_LARK_API_KEY")

        if not resolved_app_id or not resolved_app_secret:
            raise ValueError(
                "Missing Feishu app credentials. Set `app_id` / `app_secret` or configure "
                "`TOOL_FEISHU_CHANNEL_APP_ID` / `TOOL_FEISHU_CHANNEL_APP_SECRET` "
                "(compatible fallback: `TOOL_LARK_ENDPOINT` / `TOOL_LARK_API_KEY`)."
            )

        resolved_channel_kwargs = dict(channel_kwargs or {})
        resolved_channel_kwargs.setdefault(
            "transport", os.getenv("TOOL_FEISHU_CHANNEL_TRANSPORT", "ws")
        )

        return FeishuChannel(
            app_id=resolved_app_id,
            app_secret=resolved_app_secret,
            **resolved_channel_kwargs,
        )

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value
