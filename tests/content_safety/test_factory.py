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
import builtins
import os
import sys
import threading
from types import SimpleNamespace

import pytest

from veadk.content_safety import (
    ContentSafetyConfig,
    ContentSafetyConfigError,
    build_content_safety,
)
from veadk.content_safety.factory import (
    _ark_defaults,
    _is_ark_api_base,
    _systemone_url,
)
from veadk.content_safety.adapters.llm_shield import LLMShieldPluginAdapter
from veadk.decision import DecisionClient
from veadk.content_safety.plugin import DecisionPlugin


class FakeJudge:
    async def judge(self, *, state, questions):
        return {"questions": {}}


class FakeInner:
    def __init__(self):
        self.seen_app_id = os.getenv("TOOL_LLM_SHIELD_APP_ID")
        self.calls = []

    def before_model_callback(self, **kwargs):
        self.calls.append(("before_model", kwargs))
        return "before-model"

    def after_model_callback(self, **kwargs):
        self.calls.append(("after_model", kwargs))
        return "after-model"

    def before_tool_callback(self, **kwargs):
        self.calls.append(("before_tool", kwargs))
        return "before-tool"

    def after_tool_callback(self, **kwargs):
        self.calls.append(("after_tool", kwargs))
        return "after-tool"


def decision_config():
    return ContentSafetyConfig.from_dict(
        {
            "provider": "decision",
            "questions": {
                "q": {"type": "noul", "instructions": "detect", "threshold": 0.5}
            },
            "decision": {
                "api_url": "https://systemone.example/v1/judge",
                "api_key": "key",
                "model": "judge-model",
            },
        }
    )


def test_none_provider_returns_none():
    assert build_content_safety(ContentSafetyConfig()) is None


def test_decision_provider_uses_injected_client():
    client = FakeJudge()
    plugin = build_content_safety(decision_config(), client=client)
    assert isinstance(plugin, DecisionPlugin)
    assert plugin._client is client


def test_decision_provider_builds_default_client():
    plugin = build_content_safety(decision_config())
    assert isinstance(plugin, DecisionPlugin)
    assert isinstance(plugin._client, DecisionClient)
    assert plugin._client.endpoint == "https://systemone.example/v1/judge"


def test_llm_shield_provider_wraps_injected_inner():
    config = ContentSafetyConfig.from_dict({"provider": "llm_shield"})
    inner = FakeInner()
    adapter = build_content_safety(config, llm_shield_inner=inner)
    assert isinstance(adapter, LLMShieldPluginAdapter)


def test_llm_shield_provider_lazily_imports_legacy_plugin(monkeypatch):
    monkeypatch.delenv("TOOL_LLM_SHIELD_APP_ID", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "veadk.tools.builtin_tools.llm_shield",
        SimpleNamespace(LLMShieldPlugin=FakeInner),
    )
    config = ContentSafetyConfig.from_dict(
        {"provider": "llm_shield", "llm_shield_app_id": "app-from-config"}
    )
    adapter = build_content_safety(config)
    assert isinstance(adapter, LLMShieldPluginAdapter)
    assert adapter._inner.seen_app_id == "app-from-config"
    assert os.getenv("TOOL_LLM_SHIELD_APP_ID") is None


def test_llm_shield_provider_preserves_existing_env(monkeypatch):
    monkeypatch.setenv("TOOL_LLM_SHIELD_APP_ID", "existing")
    monkeypatch.setitem(
        sys.modules,
        "veadk.tools.builtin_tools.llm_shield",
        SimpleNamespace(LLMShieldPlugin=FakeInner),
    )
    config = ContentSafetyConfig.from_dict(
        {"provider": "llm_shield", "llm_shield_app_id": "ignored"}
    )
    adapter = build_content_safety(config)
    assert adapter._inner.seen_app_id == "existing"
    assert os.getenv("TOOL_LLM_SHIELD_APP_ID") == "existing"


def test_llm_shield_provider_sets_app_id_before_legacy_import(monkeypatch):
    monkeypatch.delenv("TOOL_LLM_SHIELD_APP_ID", raising=False)
    real_import = builtins.__import__
    imported_with: list[str | None] = []

    def fake_import(name, *args, **kwargs):
        if name == "veadk.tools.builtin_tools.llm_shield":
            imported_with.append(os.getenv("TOOL_LLM_SHIELD_APP_ID"))
            return SimpleNamespace(LLMShieldPlugin=FakeInner)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    config = ContentSafetyConfig.from_dict(
        {"provider": "llm_shield", "llm_shield_app_id": "app-from-config"}
    )
    adapter = build_content_safety(config)
    assert imported_with == ["app-from-config"]
    assert adapter._inner.seen_app_id == "app-from-config"
    assert os.getenv("TOOL_LLM_SHIELD_APP_ID") is None


def test_llm_shield_provider_restores_env_when_legacy_import_fails(monkeypatch):
    monkeypatch.delenv("TOOL_LLM_SHIELD_APP_ID", raising=False)
    real_import = builtins.__import__
    imported_with: list[str | None] = []

    def fake_import(name, *args, **kwargs):
        if name == "veadk.tools.builtin_tools.llm_shield":
            imported_with.append(os.getenv("TOOL_LLM_SHIELD_APP_ID"))
            raise RuntimeError("legacy import failed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    config = ContentSafetyConfig.from_dict(
        {"provider": "llm_shield", "llm_shield_app_id": "app-from-config"}
    )
    with pytest.raises(RuntimeError, match="legacy import failed"):
        build_content_safety(config)
    assert imported_with == ["app-from-config"]
    assert os.getenv("TOOL_LLM_SHIELD_APP_ID") is None


def test_unsupported_provider_raises():
    with pytest.raises(ValueError, match="unsupported"):
        build_content_safety(SimpleNamespace(provider="bogus"))


def test_adapter_translates_all_callbacks():
    inner = FakeInner()
    adapter = LLMShieldPluginAdapter(inner)
    marker = object()

    assert (
        asyncio.run(
            adapter.before_model_callback(
                callback_context=marker, llm_request="request"
            )
        )
        == "before-model"
    )
    assert (
        asyncio.run(
            adapter.after_model_callback(
                callback_context=marker, llm_response="response"
            )
        )
        == "after-model"
    )
    assert (
        asyncio.run(
            adapter.before_tool_callback(
                tool=marker, tool_args={"a": 1}, tool_context=marker
            )
        )
        == "before-tool"
    )
    assert (
        asyncio.run(
            adapter.after_tool_callback(
                tool=marker,
                tool_args={"a": 1},
                tool_context=marker,
                result={"ok": True},
            )
        )
        == "after-tool"
    )

    assert inner.calls[0] == (
        "before_model",
        {"callback_context": marker, "llm_request": "request"},
    )
    assert inner.calls[3] == (
        "after_tool",
        {
            "tool": marker,
            "args": {"a": 1},
            "tool_context": marker,
            "tool_response": {"ok": True},
        },
    )


def test_adapter_from_config_with_inner_does_not_import():
    config = ContentSafetyConfig.from_dict({"provider": "llm_shield"})
    inner = FakeInner()
    adapter = LLMShieldPluginAdapter.from_config(config, inner=inner)
    assert adapter._inner is inner


@pytest.mark.parametrize(
    "base,expected",
    [
        ("https://ark.example/api/v3", "https://ark.example/api/v1/systemone"),
        ("https://ark.example/api/v3/", "https://ark.example/api/v1/systemone"),
        ("https://ark.example/api/v1", "https://ark.example/api/v1/systemone"),
        (
            "https://gateway.example/prefix",
            "https://gateway.example/prefix/api/v1/systemone",
        ),
    ],
)
def test_systemone_url_derivation(base, expected):
    assert _systemone_url(base) == expected


def test_ark_defaults_uses_explicit_values():
    assert _ark_defaults("https://ark.example", "key") == (
        "https://ark.example",
        "key",
    )


def test_ark_defaults_reads_veadk_settings(monkeypatch):
    import veadk.config as veadk_config

    monkeypatch.setattr(
        veadk_config,
        "settings",
        SimpleNamespace(
            model=SimpleNamespace(
                api_base="https://ark.example/api/v3", api_key="ark-key"
            )
        ),
    )
    assert _ark_defaults(None, None) == (
        "https://ark.example/api/v3",
        "ark-key",
    )
    assert _ark_defaults("https://override", None) == (
        "https://override",
        "ark-key",
    )
    assert _ark_defaults(None, "override-key") == (
        "https://ark.example/api/v3",
        "override-key",
    )


def test_is_ark_api_base_accepts_ark_hosts_and_rejects_unsafe_urls():
    assert _is_ark_api_base("https://ark.cn-beijing.volces.com/api/v3")
    assert _is_ark_api_base("https://ark.ap-southeast.bytepluses.com/api/v3")
    assert not _is_ark_api_base("http://ark.cn-beijing.volces.com/api/v3")
    assert not _is_ark_api_base("https://ark.example/api/v3")
    assert not _is_ark_api_base("https://ark.cn-beijing.volces.com.evil.com/api/v3")
    assert not _is_ark_api_base("https://[::1")


def test_decision_provider_derives_default_connection():
    config = ContentSafetyConfig.from_dict(
        {
            "provider": "decision",
            "questions": {"q": {"instructions": "detect", "threshold": 0.5}},
        }
    )
    plugin = build_content_safety(
        config,
        ark_api_base="https://ark.cn-beijing.volces.com/api/v3",
        ark_api_key="ark-key",
    )
    assert (
        plugin._client.endpoint == "https://ark.cn-beijing.volces.com/api/v1/systemone"
    )
    assert plugin._client._api_key == "ark-key"


def test_decision_provider_derives_from_ark_global_settings(monkeypatch):
    import veadk.config as veadk_config

    monkeypatch.setattr(
        veadk_config,
        "settings",
        SimpleNamespace(
            model=SimpleNamespace(
                api_base="https://ark.cn-beijing.volces.com/api/v3",
                api_key="ark-key",
            )
        ),
    )
    config = ContentSafetyConfig.from_dict(
        {
            "provider": "decision",
            "questions": {"q": {"instructions": "detect", "threshold": 0.5}},
        }
    )
    plugin = build_content_safety(config)
    assert (
        plugin._client.endpoint == "https://ark.cn-beijing.volces.com/api/v1/systemone"
    )
    assert plugin._client._api_key == "ark-key"


def test_decision_provider_rejects_non_ark_fallback_base():
    config = ContentSafetyConfig.from_dict(
        {
            "provider": "decision",
            "questions": {"q": {"instructions": "detect", "threshold": 0.5}},
        }
    )
    with pytest.raises(ContentSafetyConfigError, match="decision.api_url"):
        build_content_safety(
            config,
            ark_api_base="https://api.openai.com/v1",
            ark_api_key="openai-key",
        )


def test_decision_provider_uses_ark_api_url_but_resolves_missing_key(monkeypatch):
    import veadk.config as veadk_config

    monkeypatch.setattr(
        veadk_config,
        "settings",
        SimpleNamespace(
            model=SimpleNamespace(
                api_base="https://ark.cn-beijing.volces.com/api/v3",
                api_key="ark-key",
            )
        ),
    )
    config = ContentSafetyConfig.from_dict(
        {
            "provider": "decision",
            "decision": {
                "api_url": "https://ark.cn-beijing.volces.com/api/v1/systemone"
            },
            "questions": {"q": {"instructions": "detect", "threshold": 0.5}},
        }
    )
    plugin = build_content_safety(config)
    assert (
        plugin._client.endpoint == "https://ark.cn-beijing.volces.com/api/v1/systemone"
    )
    assert plugin._client._api_key == "ark-key"


def test_decision_provider_rejects_custom_api_url_without_key(monkeypatch):
    import veadk.config as veadk_config

    monkeypatch.setattr(
        veadk_config,
        "settings",
        SimpleNamespace(
            model=SimpleNamespace(
                api_base="https://ark.cn-beijing.volces.com/api/v3",
                api_key="ark-key",
            )
        ),
    )
    config = ContentSafetyConfig.from_dict(
        {
            "provider": "decision",
            "decision": {"api_url": "https://custom.example/v1/systemone"},
            "questions": {"q": {"instructions": "detect", "threshold": 0.5}},
        }
    )
    with pytest.raises(ContentSafetyConfigError, match="decision.api_key"):
        build_content_safety(config)


def test_decision_provider_rejects_ark_url_with_non_ark_fallback():
    config = ContentSafetyConfig.from_dict(
        {
            "provider": "decision",
            "decision": {
                "api_url": ("https://ark.cn-beijing.volces.com/api/v1/systemone")
            },
            "questions": {"q": {"instructions": "detect", "threshold": 0.5}},
        }
    )
    with pytest.raises(ContentSafetyConfigError, match="non-Ark"):
        build_content_safety(
            config,
            ark_api_base="https://api.openai.com/v1",
            ark_api_key="openai-key",
        )


def test_adapter_runs_sync_inner_in_worker_thread():
    seen = []

    class RecordingInner(FakeInner):
        def before_model_callback(self, **kwargs):
            seen.append(threading.current_thread())
            return super().before_model_callback(**kwargs)

    adapter = LLMShieldPluginAdapter(RecordingInner())
    asyncio.run(
        adapter.before_model_callback(callback_context=object(), llm_request=object())
    )
    assert seen
    assert seen[0] is not threading.main_thread()
