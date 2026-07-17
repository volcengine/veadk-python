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


def _call_in_fresh_event_loop(method: Callable[[], Any]) -> Any:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        result = method()
        if inspect.isawaitable(result):
            return loop.run_until_complete(result)
        return result
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def _stringify_card_elements(elements: Any) -> str:
    if elements is None:
        return ""
    if isinstance(elements, str):
        return elements
    if isinstance(elements, (list, tuple)):
        parts: list[str] = []
        for element in elements:
            piece = _stringify_card_elements(element)
            if piece:
                parts.append(piece)
        return "\n".join(parts)
    if isinstance(elements, dict):
        for key in ("content", "text", "plain_text", "value"):
            value = elements.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, dict):
                nested = _stringify_card_elements(value)
                if nested:
                    return nested
        nested_parts: list[str] = []
        for key in ("elements", "columns", "actions", "fields"):
            nested = _stringify_card_elements(elements.get(key))
            if nested:
                nested_parts.append(nested)
        if nested_parts:
            return "\n".join(nested_parts)
        return ""
    text = getattr(elements, "text", None) or getattr(elements, "content", None)
    if isinstance(text, str):
        return text
    return ""


try:
    from lark_oapi.channel.types import (
        InteractiveContent,
        MergeForwardContent,
        TextContent,
    )

    _LARK_TYPES_AVAILABLE = True
except ImportError:
    InteractiveContent = None  # type: ignore[assignment,misc]
    MergeForwardContent = None  # type: ignore[assignment,misc]
    TextContent = None  # type: ignore[assignment,misc]
    _LARK_TYPES_AVAILABLE = False


def _extract_interactive_text(content: Any) -> str:
    """Extract title + body text from an ``InteractiveContent``-like value.

    Prefers ``content.raw['title'] / ['elements']`` (matching lark_oapi's
    ``InteractiveContent.raw``, a dict), then falls back to attribute access
    for duck-typed test doubles.
    """
    raw = getattr(content, "raw", None)
    title = ""
    elements: Any = None
    if isinstance(raw, dict):
        title = str(raw.get("title", "") or "")
        elements = raw.get("elements")
    elif raw is not None:
        title = str(getattr(raw, "title", "") or "")
        elements = getattr(raw, "elements", None)
    body = _stringify_card_elements(elements)
    if title and body:
        return f"{title}\n{body}"
    return title or body


def _extract_text_content(content: Any) -> str:
    text = getattr(content, "text", None)
    if isinstance(text, str) and text:
        return text
    raw = getattr(content, "raw", None)
    if isinstance(raw, dict):
        candidate = raw.get("text")
        if isinstance(candidate, str):
            return candidate
    return ""


def _extract_merge_forward_text(content: Any) -> str:
    items = getattr(content, "items", None) or []
    parts: list[str] = []
    for item in items:
        sub_content = getattr(item, "content", None)
        piece = _dispatch_content(sub_content)
        if piece:
            parts.append(piece)
    return "\n\n".join(parts)


def _dispatch_content(content: Any) -> str:
    """Route ``MessageContent`` to a kind-specific extractor.

    Uses ``isinstance`` against the concrete ``lark_oapi.channel.types`` classes
    when available, and falls back to the string ``kind`` discriminator so
    hand-crafted objects (tests, mocks) still work.
    """
    if content is None:
        return ""

    if _LARK_TYPES_AVAILABLE:
        if isinstance(content, InteractiveContent):
            return _extract_interactive_text(content)
        if isinstance(content, MergeForwardContent):
            return _extract_merge_forward_text(content)
        if isinstance(content, TextContent):
            return _extract_text_content(content)

    kind = getattr(content, "kind", None)
    if kind == "interactive":
        return _extract_interactive_text(content)
    if kind == "merge_forward":
        return _extract_merge_forward_text(content)
    if kind == "text":
        return _extract_text_content(content)

    return _extract_text_content(content)


def _extract_message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    text = _dispatch_content(content)
    if text:
        return text
    fallback = getattr(message, "content_text", "")
    return str(fallback or "")


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


FEISHU_EMOJI_ONE_SECOND = "OneSecond"


class FeishuChannelExtension:
    """Bridge a Feishu bot channel with a VeADK runner.

    The extension subscribes to normalized ``message`` events from
    ``lark_oapi.channel.FeishuChannel`` and forwards the incoming text to a VeADK
    ``Runner``. It maps Feishu sender identity to VeADK ``user_id`` and Feishu
    conversation/thread identity to VeADK ``session_id`` so existing short-term
    memory, long-term memory and tracing continue to work without changes.
    """

    CHANNEL_SDK_COMPAT = True

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
        streaming: bool = False,
        reactions: bool = False,
    ) -> None:
        self.runner = runner
        self.session_id_factory = session_id_factory or self.default_session_id_factory
        self.user_id_factory = user_id_factory or self.default_user_id_factory
        self.message_handler = message_handler
        self.response_formatter = response_formatter or self.default_response_formatter
        self.reply_in_thread = reply_in_thread
        self.ignore_empty_messages = ignore_empty_messages
        self.reactions = (
            reactions
            or str(os.getenv("TOOL_FEISHU_CHANNEL_REACTIONS", "")).lower() == "true"
        )
        self.streaming = (
            streaming
            or str(os.getenv("TOOL_FEISHU_CHANNEL_STREAMING", "")).lower() == "true"
        )

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
        connect = getattr(self.channel, "start", None) or self.channel.connect
        if inspect.iscoroutinefunction(connect):
            return await connect()
        return await asyncio.to_thread(_call_in_fresh_event_loop, connect)

    async def disconnect(self) -> Any:
        disconnect = getattr(self.channel, "stop", None) or getattr(
            self.channel, "disconnect", None
        )
        if disconnect is None:
            return None
        if inspect.iscoroutinefunction(disconnect):
            return await disconnect()
        return await asyncio.to_thread(_call_in_fresh_event_loop, disconnect)

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
        text = _extract_message_text(message).strip()
        if self.ignore_empty_messages and not text:
            logger.debug(
                f"Ignore empty Feishu message: {getattr(message, 'message_id', '')}"
            )
            return
        logger.debug(f"Received Feishu message: {getattr(message, 'message_id', '')}")
        context = self.build_message_context(message=message, text=text)

        if self.reactions and context.message_id:
            try:
                import lark_oapi.api.im.v1 as lark_im

                emoji = (
                    lark_im.Emoji.builder().emoji_type(FEISHU_EMOJI_ONE_SECOND).build()
                )
                request = (
                    lark_im.CreateMessageReactionRequest.builder()
                    .message_id(context.message_id)
                    .request_body(
                        lark_im.CreateMessageReactionRequestBody.builder()
                        .reaction_type(emoji)
                        .build()
                    )
                    .build()
                )

                if hasattr(self.channel, "client"):
                    response = await self._maybe_await(
                        self.channel.client.im.v1.message_reaction.create(request)
                    )

                    if not response.success():
                        logger.error(
                            f"Failed to add reaction to message {context.message_id}: {response.code} {response.msg}"
                        )
                else:
                    logger.warning(
                        "Channel has no client attribute, cannot send reaction"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to add reaction to message {context.message_id}: {e}"
                )

        send_options = {}
        if self.reply_in_thread and context.message_id:
            send_options["reply_to"] = context.message_id

        if self.message_handler is not None:
            response_text = await self._maybe_await(self.message_handler(context))
            if not response_text:
                return

            await self._maybe_await(
                self.channel.send(
                    context.chat_id,
                    self.response_formatter(str(response_text)),
                    send_options,
                )
            )
        elif getattr(self, "streaming", False) and hasattr(self.channel, "stream"):
            from google.adk.agents import RunConfig
            from google.adk.agents.run_config import StreamingMode
            from veadk.config import getenv
            from veadk.runner import _convert_messages

            if self.runner.short_term_memory:
                await self.runner.short_term_memory.create_session(
                    app_name=self.runner.app_name,
                    user_id=context.user_id,
                    session_id=context.session_id,
                )

            converted_messages = _convert_messages(
                context.text, self.runner.app_name, context.user_id, context.session_id
            )

            run_config = RunConfig(
                streaming_mode=StreamingMode.SSE,
                max_llm_calls=int(getenv("MODEL_AGENT_MAX_LLM_CALLS", 100)),
            )

            async def stream_to_feishu(stream):
                for converted_message in converted_messages:
                    async for event in self.runner.run_async(
                        user_id=context.user_id,
                        session_id=context.session_id,
                        new_message=converted_message,
                        run_config=run_config,
                    ):
                        if not getattr(event, "partial", False):
                            continue
                        if not (event.content and event.content.parts):
                            continue
                        for part in event.content.parts:
                            if getattr(part, "thought", False):
                                continue
                            if part.text:
                                await stream.append(part.text)

            await self._maybe_await(
                self.channel.stream(
                    context.chat_id,
                    {"markdown": stream_to_feishu},
                    send_options,
                )
            )
        else:
            response_text = await self.runner.run(
                messages=context.text,
                user_id=context.user_id,
                session_id=context.session_id,
            )

            if not response_text:
                return

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
            text=text if text is not None else _extract_message_text(message),
        )

    def _build_channel(
        self,
        *,
        app_id: str | None,
        app_secret: str | None,
        channel_kwargs: dict[str, Any] | None,
    ) -> Any:
        try:
            from lark_channel import FeishuChannel
        except ImportError:
            try:
                from lark_oapi.channel import FeishuChannel
            except ImportError as legacy_exc:
                raise ImportError(
                    "Feishu channel extension requires `lark-channel-sdk` "
                    "(or legacy `lark-oapi`). Install `veadk-python[extensions]`."
                ) from legacy_exc

        resolved_app_id = (
            app_id
            or os.getenv("TOOL_FEISHU_CHANNEL_APP_ID")
            or os.getenv("TOOL_LARK_ENDPOINT")
        )
        resolved_app_secret = (
            app_secret
            or os.getenv("TOOL_FEISHU_CHANNEL_APP_SECRET")
            or os.getenv("TOOL_LARK_API_KEY")
        )

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
