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

"""Headroom compression adapter for the atomic Harness SDK."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import importlib
from typing import Protocol, cast

from veadk.extensions.harness.schemas import (
    CompactionReport,
    CompressionRequest,
    CompactionResult,
    ConversationMessage,
    JsonObject,
)
from veadk.extensions.harness.utils import coerce_json_object, stringify_json_value


class _HeadroomCompressFn(Protocol):
    def __call__(
        self,
        messages: list[JsonObject],
        *,
        model: str,
        optimize: bool,
    ) -> object: ...


class HeadroomCompressionProvider:
    """Adapter for local in-process Headroom compression."""

    name = "headroom"

    def __init__(
        self,
        *,
        auto_install: bool | None = None,
    ) -> None:
        # Kept for source compatibility; Headroom is now code-only and never
        # installed or started by the provider at runtime.
        self.auto_install = auto_install

    def compress(self, request: CompressionRequest) -> CompactionResult | None:
        """Compress messages with Headroom when a provider is available."""

        return self._compress_via_sdk(request)

    def _compress_via_sdk(self, request: CompressionRequest) -> CompactionResult | None:
        compress = self._load_compress()
        if compress is None:
            return None
        try:
            result = compress(
                self._message_payloads(request.messages),
                model=str(request.metadata.get("model") or "gpt-4o"),
                optimize=True,
            )
        except Exception:
            return None
        compressed = self._messages_from_value(getattr(result, "messages", None))
        if compressed is None:
            return None
        return self._build_result(
            original_messages=request.messages,
            compressed_messages=compressed,
            metrics={
                "tokens_before": getattr(result, "tokens_before", 0),
                "tokens_after": getattr(result, "tokens_after", 0),
                "tokens_saved": getattr(result, "tokens_saved", 0),
                "compression_ratio": getattr(result, "compression_ratio", 0.0),
                "transforms_applied": getattr(result, "transforms_applied", []),
            },
        )

    def _load_compress(self) -> _HeadroomCompressFn | None:
        return self._import_compress()

    def _import_compress(self) -> _HeadroomCompressFn | None:
        try:
            module = importlib.import_module("headroom.compress")
        except Exception:
            return None
        compress = getattr(module, "compress", None)
        if not callable(compress):
            return None
        return cast(_HeadroomCompressFn, compress)

    def _message_payloads(
        self, messages: list[ConversationMessage]
    ) -> list[JsonObject]:
        return [message.model_dump(mode="json") for message in messages]

    def _messages_from_value(self, value: object) -> list[ConversationMessage] | None:
        if not isinstance(value, Sequence) or isinstance(
            value, (str, bytes, bytearray)
        ):
            return None
        messages: list[ConversationMessage] = []
        for item in value:
            message = self._message_from_value(item)
            if message is None:
                return None
            messages.append(message)
        return messages

    def _message_from_value(self, value: object) -> ConversationMessage | None:
        if isinstance(value, ConversationMessage):
            return value
        if not isinstance(value, Mapping):
            return None
        role = value.get("role")
        content = value.get("content")
        if not isinstance(role, str):
            return None
        metadata = value.get("metadata")
        name = value.get("name")
        return ConversationMessage(
            role=role,
            content=content
            if isinstance(content, str)
            else stringify_json_value(content),
            name=name if isinstance(name, str) else "",
            metadata=coerce_json_object(metadata),
        )

    def _build_result(
        self,
        *,
        original_messages: list[ConversationMessage],
        compressed_messages: list[ConversationMessage],
        metrics: Mapping[str, object],
    ) -> CompactionResult:
        original_chars = self._messages_char_count(original_messages)
        compressed_chars = self._messages_char_count(compressed_messages)
        tokens_before = self._int_metric(metrics.get("tokens_before"))
        tokens_after = self._int_metric(metrics.get("tokens_after"))
        tokens_saved = self._int_metric(metrics.get("tokens_saved"))
        if tokens_saved == 0 and tokens_before > tokens_after:
            tokens_saved = tokens_before - tokens_after
        ratio = self._float_metric(metrics.get("compression_ratio"))
        if ratio == 0.0 and original_chars:
            ratio = compressed_chars / original_chars
        return CompactionResult(
            messages=compressed_messages,
            report=CompactionReport(
                provider=self.name,
                original_chars=original_chars,
                compressed_chars=compressed_chars,
                changed=compressed_messages != original_messages,
                tokens_before=tokens_before,
                tokens_after=tokens_after,
                tokens_saved=tokens_saved,
                compression_ratio=ratio,
                transforms_applied=self._string_list_metric(
                    metrics.get("transforms_applied")
                ),
            ),
        )

    def _messages_char_count(self, messages: list[ConversationMessage]) -> int:
        return sum(len(message.content) for message in messages)

    def _int_metric(self, value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _float_metric(self, value: object) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _string_list_metric(self, value: object) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(
            value, (str, bytes, bytearray)
        ):
            return []
        return [str(item) for item in value]
