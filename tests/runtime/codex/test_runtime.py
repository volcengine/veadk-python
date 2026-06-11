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

"""Unit tests for veadk.runtime.codex.runtime.

The Codex SDK (``AsyncCodex``), the Responses shim and the filesystem-touching
``_prepare_codex_home`` are all mocked; no subprocess, network or model is used.
"""

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from veadk.runtime.base_runtime import BaseRuntime
from veadk.runtime.codex import runtime as runtime_mod
from veadk.runtime.codex.runtime import CodexRuntime


def _agent(
    model_name: Any = "my-model",
    model_api_base: str = "https://backend/v1",
    model_api_key: str = "sk-1",
    name: str = "agent",
    description: str = "",
    instruction: Any = "",
) -> Any:
    return SimpleNamespace(
        model_name=model_name,
        model_api_base=model_api_base,
        model_api_key=model_api_key,
        name=name,
        description=description,
        instruction=instruction,
    )


def _ctx(invocation_id: str = "inv-1") -> Any:
    return SimpleNamespace(
        invocation_id=invocation_id,
        session=SimpleNamespace(events=[]),
    )


class TestContract:
    def test_is_base_runtime_subclass(self):
        assert issubclass(CodexRuntime, BaseRuntime)

    def test_name_is_codex(self):
        assert CodexRuntime.name == "codex"

    def test_instantiable(self):
        assert isinstance(CodexRuntime(), CodexRuntime)


class TestResolveModel:
    def test_string_model_name(self):
        assert CodexRuntime()._resolve_model(_agent(model_name="gpt-x")) == "gpt-x"

    def test_list_model_name_uses_first(self):
        agent = _agent(model_name=["primary", "fallback"])
        assert CodexRuntime()._resolve_model(agent) == "primary"

    def test_empty_list_falls_back_to_env(self):
        agent = _agent(model_name=[])
        with patch.dict(os.environ, {"OPENAI_MODEL": "env-model"}):
            assert CodexRuntime()._resolve_model(agent) == "env-model"

    def test_empty_name_falls_back_to_env(self):
        agent = _agent(model_name="")
        with patch.dict(os.environ, {"OPENAI_MODEL": "env-model"}):
            assert CodexRuntime()._resolve_model(agent) == "env-model"

    def test_no_model_anywhere_raises(self):
        agent = _agent(model_name="")
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="codex runtime requires a model"):
                CodexRuntime()._resolve_model(agent)


class TestPrepareCodexHome:
    def test_writes_config_toml_and_caches(self, tmp_path):
        runtime_mod._CODEX_HOMES.clear()
        with patch.object(
            runtime_mod.tempfile, "mkdtemp", return_value=str(tmp_path)
        ) as mkdtemp:
            home = runtime_mod._prepare_codex_home("http://127.0.0.1:1234", "m-1")

        assert home == str(tmp_path)
        config_path = os.path.join(home, "config.toml")
        assert os.path.exists(config_path)
        with open(config_path, encoding="utf-8") as f:
            config = f.read()
        assert 'model = "m-1"' in config
        assert 'model_provider = "veadk"' in config
        assert "[model_providers.veadk]" in config
        assert 'base_url = "http://127.0.0.1:1234/v1"' in config
        assert 'env_key = "VEADK_CODEX_API_KEY"' in config
        assert 'wire_api = "responses"' in config

        # A second call with the same key is cached: no new mkdtemp.
        mkdtemp.reset_mock()
        with patch.object(runtime_mod.tempfile, "mkdtemp") as mkdtemp2:
            again = runtime_mod._prepare_codex_home("http://127.0.0.1:1234", "m-1")
        assert again == home
        mkdtemp2.assert_not_called()
        runtime_mod._CODEX_HOMES.clear()

    def test_distinct_keys_get_distinct_homes(self, tmp_path):
        runtime_mod._CODEX_HOMES.clear()
        homes = [str(tmp_path / "a"), str(tmp_path / "b")]
        for h in homes:
            os.makedirs(h, exist_ok=True)
        with patch.object(runtime_mod.tempfile, "mkdtemp", side_effect=homes):
            h1 = runtime_mod._prepare_codex_home("http://s1/v1", "m")
            h2 = runtime_mod._prepare_codex_home("http://s2/v1", "m")
        assert h1 != h2
        runtime_mod._CODEX_HOMES.clear()


def _patch_codex(result):
    """Return a patcher for AsyncCodex whose thread.run resolves to ``result``."""
    thread = SimpleNamespace(run=AsyncMock(return_value=result))
    codex = MagicMock()
    codex.thread_start = AsyncMock(return_value=thread)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=codex)
    cm.__aexit__ = AsyncMock(return_value=False)
    return patch.object(runtime_mod, "AsyncCodex", MagicMock(return_value=cm)), codex


class TestRunAsync:
    @pytest.mark.asyncio
    async def test_missing_api_base_or_key_raises(self):
        agent = _agent(model_api_base="", model_api_key="")
        with patch.dict(os.environ, {}, clear=True):
            runtime = CodexRuntime()
            with pytest.raises(ValueError, match="model_api_base and model_api_key"):
                async for _ in runtime.run_async(agent, _ctx()):
                    pass

    @pytest.mark.asyncio
    async def test_run_async_streams_translated_events(self):
        agent = _agent(name="bot", instruction="Be nice.")
        result = SimpleNamespace(
            items=[{"type": "agentMessage", "text": "hello"}],
            final_response="hello",
        )
        codex_patch, codex = _patch_codex(result)
        with (
            patch.object(
                runtime_mod, "get_shim_url", AsyncMock(return_value="http://shim")
            ),
            patch.object(runtime_mod, "_prepare_codex_home", return_value="/tmp/home"),
            codex_patch,
        ):
            runtime = CodexRuntime()
            events = [e async for e in runtime.run_async(agent, _ctx("inv-9"))]

        assert len(events) == 1
        content = events[0].content
        assert content is not None and content.parts is not None
        assert content.parts[0].text == "hello"
        assert events[0].author == "bot"
        assert events[0].invocation_id == "inv-9"
        # thread_start receives the resolved model.
        codex.thread_start.assert_awaited_once_with(model="my-model")

    @pytest.mark.asyncio
    async def test_prompt_includes_system_append_block(self):
        agent = _agent(name="bot", description="A bot.", instruction="Be brief.")
        result = SimpleNamespace(items=[], final_response=None)
        codex_patch, codex = _patch_codex(result)
        ctx = _ctx()
        ctx.session.events = [
            SimpleNamespace(
                author="user",
                content=SimpleNamespace(
                    parts=[SimpleNamespace(text="hi", thought=False)]
                ),
            )
        ]
        with (
            patch.object(
                runtime_mod, "get_shim_url", AsyncMock(return_value="http://shim")
            ),
            patch.object(runtime_mod, "_prepare_codex_home", return_value="/tmp/home"),
            codex_patch,
        ):
            runtime = CodexRuntime()
            _ = [e async for e in runtime.run_async(agent, ctx)]

        prompt = codex.thread_start.return_value.run.call_args.args[0]
        assert "# System instructions" in prompt
        assert "Your name is bot." in prompt
        assert "A bot." in prompt
        assert "Be brief." in prompt
        assert "# Conversation" in prompt
        assert prompt.endswith("hi")

    @pytest.mark.asyncio
    async def test_env_isolation_restored_after_run(self):
        agent = _agent()
        result = SimpleNamespace(items=[], final_response=None)
        codex_patch, _ = _patch_codex(result)
        with patch.dict(
            os.environ,
            {"CODEX_HOME": "/orig/home", "VEADK_CODEX_API_KEY": "orig-key"},
        ):
            with (
                patch.object(
                    runtime_mod, "get_shim_url", AsyncMock(return_value="http://shim")
                ),
                patch.object(
                    runtime_mod, "_prepare_codex_home", return_value="/tmp/home"
                ),
                codex_patch,
            ):
                runtime = CodexRuntime()
                _ = [e async for e in runtime.run_async(agent, _ctx())]
            # Pre-existing env vars are restored to their original values.
            assert os.environ["CODEX_HOME"] == "/orig/home"
            assert os.environ["VEADK_CODEX_API_KEY"] == "orig-key"

    @pytest.mark.asyncio
    async def test_env_isolation_pops_vars_that_did_not_exist(self):
        agent = _agent()
        result = SimpleNamespace(items=[], final_response=None)
        codex_patch, _ = _patch_codex(result)
        with patch.dict(os.environ, {}, clear=True):
            os.environ["OPENAI_BASE_URL"] = "x"  # keep run_async happy via agent
            with (
                patch.object(
                    runtime_mod, "get_shim_url", AsyncMock(return_value="http://shim")
                ),
                patch.object(
                    runtime_mod, "_prepare_codex_home", return_value="/tmp/home"
                ),
                codex_patch,
            ):
                runtime = CodexRuntime()
                _ = [e async for e in runtime.run_async(agent, _ctx())]
            # They were absent before the run, so they must be removed after.
            assert "CODEX_HOME" not in os.environ
            assert "VEADK_CODEX_API_KEY" not in os.environ

    @pytest.mark.asyncio
    async def test_falls_back_to_env_base_and_key(self):
        agent = _agent(model_api_base="", model_api_key="")
        result = SimpleNamespace(items=[], final_response=None)
        codex_patch, _ = _patch_codex(result)
        shim = AsyncMock(return_value="http://shim")
        with patch.dict(
            os.environ,
            {"OPENAI_BASE_URL": "https://env-base/v1", "OPENAI_API_KEY": "env-key"},
        ):
            with (
                patch.object(runtime_mod, "get_shim_url", shim),
                patch.object(
                    runtime_mod, "_prepare_codex_home", return_value="/tmp/home"
                ),
                codex_patch,
            ):
                runtime = CodexRuntime()
                _ = [e async for e in runtime.run_async(agent, _ctx())]
        shim.assert_awaited_once_with("https://env-base/v1", "env-key")
