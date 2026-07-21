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
import json
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


def _extract_text_from_body(msg_type: str, content_json: str) -> str:
    """Extract readable text from an ``im/v1`` ``Message.body.content`` payload.

    ``body.content`` is a JSON string whose shape depends on ``msg_type``
    (text / post / interactive / merge_forward / ...). This is used to inline
    parent/thread history that we fetch via the OpenAPI, which returns raw JSON
    rather than the parsed ``MessageContent`` objects delivered over WebSocket.
    """
    if not content_json:
        return ""
    try:
        payload = json.loads(content_json)
    except Exception:
        return content_json.strip()

    if not isinstance(payload, dict):
        return str(payload)

    if msg_type == "text":
        return str(payload.get("text", "") or "").strip()
    if msg_type == "post":
        title = str(payload.get("title", "") or "")
        pieces: list[str] = []
        for paragraph in payload.get("content", []) or []:
            if not isinstance(paragraph, list):
                continue
            line_parts: list[str] = []
            for node in paragraph:
                if isinstance(node, dict):
                    text = (
                        node.get("text") or node.get("content") or node.get("user_name")
                    )
                    if isinstance(text, str) and text:
                        line_parts.append(text)
            if line_parts:
                pieces.append("".join(line_parts))
        body = "\n".join(pieces)
        return f"{title}\n{body}".strip() if title else body
    if msg_type == "interactive":
        title_data = (
            payload.get("header", {}).get("title", {})
            if isinstance(payload.get("header"), dict)
            else {}
        )
        title = ""
        if isinstance(title_data, dict):
            title = str(title_data.get("content", "") or "")
        body = _stringify_card_elements(payload.get("elements") or payload.get("card"))
        return f"{title}\n{body}".strip() if title else body
    if msg_type == "merge_forward":
        return str(payload.get("content", "") or payload.get("text", "") or "").strip()

    return _stringify_card_elements(payload)


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
        include_parent_message: bool = True,
        include_thread_history: bool = True,
        thread_history_limit: int = 20,
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
        self.include_parent_message = include_parent_message
        self.include_thread_history = include_thread_history
        self.thread_history_limit = max(1, int(thread_history_limit))
        self._app_id = (
            app_id
            or os.getenv("TOOL_FEISHU_CHANNEL_APP_ID")
            or os.getenv("TOOL_LARK_ENDPOINT")
        )
        self._app_secret = (
            app_secret
            or os.getenv("TOOL_FEISHU_CHANNEL_APP_SECRET")
            or os.getenv("TOOL_LARK_API_KEY")
        )
        self._openapi_client: Any = None

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

        prefix = await self._collect_reference_context(message)
        composed_text = f"{prefix}\n\n{text}".strip() if prefix else text

        context = self.build_message_context(message=message, text=composed_text)

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
                    openapi_client = self._get_openapi_client() or self.channel.client
                    response = await asyncio.to_thread(
                        openapi_client.im.v1.message_reaction.create, request
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

    def _get_openapi_client(self) -> Any:
        """Return a lark ``Client`` that can call OpenAPI (im/v1 message.get etc.).

        ``FeishuChannel.client`` on the WebSocket path is a CallbackClient that
        does NOT carry a tenant_access_token when calling HTTP OpenAPI, so
        requests come back with code=99991661 "Missing access token". We build
        (and cache) a dedicated ``lark.Client`` from app_id/app_secret for HTTP
        calls instead.
        """
        if self._openapi_client is not None:
            return self._openapi_client
        if not self._app_id or not self._app_secret:
            logger.debug(
                "Cannot build OpenAPI client: app_id/app_secret not configured."
            )
            return None
        try:
            import lark_oapi as lark
        except ImportError:
            return None
        try:
            self._openapi_client = (
                lark.Client.builder()
                .app_id(self._app_id)
                .app_secret(self._app_secret)
                .build()
            )
        except Exception as exc:
            logger.warning("Failed to build lark OpenAPI client: %s", exc)
            return None
        return self._openapi_client

    async def _collect_reference_context(self, message: Any) -> str:
        if not (self.include_parent_message or self.include_thread_history):
            return ""
        client = self._get_openapi_client()
        if client is None:
            return ""

        thread_id = _coalesce(
            _read_attr(message, "conversation", "thread_id"),
            getattr(message, "thread_id", None),
        )
        parent_id = _coalesce(
            getattr(message, "parent_id", None),
            getattr(message, "reply_to_message_id", None),
            _read_attr(message, "reply", "message_id"),
        )
        root_id = getattr(message, "root_id", None) or thread_id
        message_id = getattr(message, "message_id", "")

        blocks: list[str] = []

        if self.include_thread_history and thread_id:
            history = await self._fetch_thread_messages(client, thread_id)
            rendered = self._render_history_block(history, exclude_ids={message_id})
            if rendered:
                blocks.append(f"[飞书话题历史 thread_id={thread_id}]\n{rendered}")
        elif self.include_parent_message and parent_id:
            parent = await self._fetch_message(client, parent_id)
            rendered = self._render_message_line(parent) if parent else ""
            if rendered:
                blocks.append(f"[引用消息 message_id={parent_id}]\n{rendered}")
            elif root_id and root_id != parent_id:
                root_msg = await self._fetch_message(client, root_id)
                rendered = self._render_message_line(root_msg) if root_msg else ""
                if rendered:
                    blocks.append(f"[根消息 message_id={root_id}]\n{rendered}")

        return "\n\n".join(blocks)

    async def _fetch_message(self, client: Any, message_id: str) -> Any:
        try:
            from lark_oapi.api.im.v1 import GetMessageRequest
        except ImportError:
            return None
        req = GetMessageRequest.builder().message_id(message_id).build()
        try:
            resp = await asyncio.to_thread(client.im.v1.message.get, req)
        except Exception as exc:
            logger.warning("Feishu get message %s failed: %s", message_id, exc)
            return None
        if not getattr(resp, "success", lambda: False)():
            logger.error(
                "Feishu get message %s non-success: code=%s msg=%s",
                message_id,
                getattr(resp, "code", None),
                getattr(resp, "msg", None),
            )
            return None
        items = getattr(getattr(resp, "data", None), "items", None) or []
        return items[0] if items else None

    async def _fetch_thread_messages(self, client: Any, thread_id: str) -> list[Any]:
        try:
            from lark_oapi.api.im.v1 import ListMessageRequest
        except ImportError:
            return []
        req = (
            ListMessageRequest.builder()
            .container_id_type("thread")
            .container_id(thread_id)
            .sort_type("ByCreateTimeAsc")
            .page_size(self.thread_history_limit)
            .build()
        )
        try:
            resp = await asyncio.to_thread(client.im.v1.message.list, req)
        except Exception as exc:
            logger.warning("Feishu list thread %s failed: %s", thread_id, exc)
            return []
        if not getattr(resp, "success", lambda: False)():
            logger.debug(
                "Feishu list thread %s non-success: code=%s msg=%s",
                thread_id,
                getattr(resp, "code", None),
                getattr(resp, "msg", None),
            )
            return []
        return list(getattr(getattr(resp, "data", None), "items", None) or [])

    def _render_history_block(
        self, messages: list[Any], exclude_ids: set[str] | None = None
    ) -> str:
        exclude_ids = exclude_ids or set()
        lines: list[str] = []
        for msg in messages:
            if getattr(msg, "message_id", None) in exclude_ids:
                continue
            line = self._render_message_line(msg)
            if line:
                lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _render_message_line(msg: Any) -> str:
        if msg is None:
            return ""
        msg_type = getattr(msg, "msg_type", "") or ""
        body = getattr(msg, "body", None)
        content = getattr(body, "content", "") if body is not None else ""
        text = _extract_text_from_body(msg_type, content).strip()
        if not text:
            return ""
        sender = getattr(msg, "sender", None)
        sender_id = _coalesce(
            getattr(sender, "id", None),
            getattr(sender, "sender_id", None),
            getattr(msg, "sender_id", None),
        )
        prefix = f"@{sender_id}" if sender_id else "user"
        return f"{prefix} ({msg_type}): {text}"
