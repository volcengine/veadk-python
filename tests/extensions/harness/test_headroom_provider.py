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
import importlib
import sys
from types import ModuleType, SimpleNamespace

from pytest import MonkeyPatch

from veadk.extensions.harness.adk import HarnessCompressPlugin
from veadk.extensions.harness.modules.headroom_provider import (
    HeadroomCompressionProvider,
)
from veadk.extensions.harness.modules.tool_result_compactor import (
    ToolResultCompactor,
    ToolResultCompactorConfig,
)
from veadk.extensions.harness.schemas import CompressionRequest, ConversationMessage
from veadk.extensions.harness.stores import InMemoryHarnessStore


_HEADROOM_CALLS: list[dict[str, object]] = []


def _install_fake_headroom(monkeypatch: MonkeyPatch) -> None:
    package = ModuleType("headroom")
    package.__path__ = []
    compress_module = ModuleType("headroom.compress")

    def compress(
        messages: list[dict[str, object]],
        *,
        model: str,
        optimize: bool,
    ) -> object:
        _HEADROOM_CALLS.append(
            {"messages": messages, "model": model, "optimize": optimize}
        )
        return SimpleNamespace(
            messages=[
                {
                    "role": "tool",
                    "content": "HEADROOM_SUMMARY: preserved key facts only.",
                    "metadata": {"source": "test"},
                }
            ],
            tokens_before=2000,
            tokens_after=40,
            tokens_saved=1960,
            compression_ratio=0.02,
            transforms_applied=["headroom_test_compaction"],
        )

    compress_module.compress = compress
    _HEADROOM_CALLS.clear()
    monkeypatch.setitem(sys.modules, "headroom", package)
    monkeypatch.setitem(sys.modules, "headroom.compress", compress_module)


def test_headroom_sdk_provider_compresses_tool_result(monkeypatch: MonkeyPatch) -> None:
    _install_fake_headroom(monkeypatch)
    compactor = ToolResultCompactor(
        ToolResultCompactorConfig(
            provider="headroom",
            max_tool_result_chars=200,
        )
    )

    compressed, report = compactor.compress_tool_result({"rows": "x" * 8000})

    assert compressed["harness_compressed"] is True
    assert compressed["provider"] == "headroom"
    assert "HEADROOM_SUMMARY" in str(compressed["summary"])
    assert report.provider == "headroom"
    assert report.tokens_saved == 1960
    assert report.compressed_chars < report.original_chars
    assert _HEADROOM_CALLS[0]["model"] == "gpt-4o"
    assert _HEADROOM_CALLS[0]["optimize"] is True


def test_compress_plugin_after_tool_callback_uses_headroom(
    monkeypatch: MonkeyPatch,
) -> None:
    _install_fake_headroom(monkeypatch)
    plugin = HarnessCompressPlugin(
        compressor=ToolResultCompactor(
            ToolResultCompactorConfig(
                provider="headroom",
                max_tool_result_chars=200,
            )
        ),
        store=InMemoryHarnessStore(),
    )

    compressed = asyncio.run(
        plugin.after_tool_callback(
            tool=SimpleNamespace(name="query_data"),
            tool_args={},
            tool_context=SimpleNamespace(
                session=SimpleNamespace(id="s1", app_name="app", user_id="u1"),
                user_id="u1",
                invocation_id="r1",
            ),
            result={"rows": "x" * 8000},
        )
    )

    assert compressed is not None
    assert compressed["provider"] == "headroom"
    assert "HEADROOM_SUMMARY" in str(compressed["summary"])


def test_headroom_sdk_provider_compresses_candidate_context(
    monkeypatch: MonkeyPatch,
) -> None:
    _install_fake_headroom(monkeypatch)
    compactor = ToolResultCompactor(
        ToolResultCompactorConfig(
            provider="headroom",
            max_context_chars=1500,
            min_candidate_chars=100,
            protect_recent_messages=1,
        )
    )
    messages = [
        ConversationMessage(role="user", content="summarize"),
        ConversationMessage(role="tool", content="a" * 1000),
        ConversationMessage(role="tool", content="b" * 1000),
    ]

    result = compactor.compress_messages(
        CompressionRequest(messages=messages, max_context_chars=1500)
    )

    assert result.report.provider == "headroom"
    assert result.report.changed is True
    assert result.report.policy["candidate_count"] == 1
    assert "HEADROOM_SUMMARY" in result.messages[1].content
    assert result.messages[-1].content == "b" * 1000


def test_headroom_provider_does_not_install_when_unavailable(
    monkeypatch: MonkeyPatch,
) -> None:
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> ModuleType:
        if name == "headroom.compress":
            raise ImportError(name)
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    provider = HeadroomCompressionProvider(auto_install=True)

    result = provider.compress(
        CompressionRequest(
            messages=[ConversationMessage(role="tool", content="x" * 8000)],
            max_context_chars=200,
        )
    )

    assert result is None


def test_headroom_provider_falls_back_when_unavailable(
    monkeypatch: MonkeyPatch,
) -> None:
    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None) -> ModuleType:
        if name == "headroom.compress":
            raise ImportError(name)
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    compactor = ToolResultCompactor(
        ToolResultCompactorConfig(provider="headroom", max_tool_result_chars=200)
    )

    compressed, report = compactor.compress_tool_result({"rows": "x" * 1000})

    assert compressed["harness_compressed"] is True
    assert report.provider == "heuristic"
    assert "headroom provider unavailable" in report.warnings[0]
    assert report.compressed_chars < report.original_chars
