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

"""Unit tests for ``veadk.prompts.prompt_manager``.

``CozeloopPromptManager`` imports the optional ``cozeloop`` SDK inside its
constructor; we stub it in ``sys.modules`` and mock the client so no network
access occurs.
"""

import sys
from unittest.mock import MagicMock

import pytest

from veadk.prompts.prompt_manager import BasePromptManager, CozeloopPromptManager
from veadk.prompts.agent_default_prompt import DEFAULT_INSTRUCTION


@pytest.fixture
def fake_cozeloop(monkeypatch):
    """Install a stub ``cozeloop`` module and return its ``new_client`` mock."""
    module = MagicMock()
    client = MagicMock()
    module.new_client.return_value = client
    monkeypatch.setitem(sys.modules, "cozeloop", module)
    return module, client


def _make_context(agent_name: str = "agent-x") -> MagicMock:
    ctx = MagicMock()
    ctx.agent_name = agent_name
    return ctx


def test_base_prompt_manager_is_abstract():
    with pytest.raises(TypeError):
        BasePromptManager()  # type: ignore[abstract]


def test_init_creates_client_with_credentials(fake_cozeloop):
    module, client = fake_cozeloop
    manager = CozeloopPromptManager(
        cozeloop_workspace_id="ws",
        cozeloop_token="tok",
        prompt_key="key",
        version="v1",
        label="prod",
    )

    module.new_client.assert_called_once_with(workspace_id="ws", api_token="tok")
    assert manager.client is client
    assert manager.prompt_key == "key"
    assert manager.version == "v1"
    assert manager.label == "prod"


def test_get_prompt_returns_remote_content(fake_cozeloop):
    _, client = fake_cozeloop

    message = MagicMock()
    message.content = "REMOTE_PROMPT"
    prompt = MagicMock()
    prompt.prompt_template.messages = [message]
    client.get_prompt.return_value = prompt

    manager = CozeloopPromptManager(
        cozeloop_workspace_id="ws",
        cozeloop_token="tok",
        prompt_key="key",
    )

    result = manager.get_prompt(_make_context())

    assert result == "REMOTE_PROMPT"
    client.get_prompt.assert_called_once_with(prompt_key="key", version="", label="")


def test_get_prompt_falls_back_to_default_when_missing(fake_cozeloop):
    _, client = fake_cozeloop
    client.get_prompt.return_value = None

    manager = CozeloopPromptManager(
        cozeloop_workspace_id="ws",
        cozeloop_token="tok",
        prompt_key="key",
    )

    result = manager.get_prompt(_make_context())
    assert result == DEFAULT_INSTRUCTION


def test_get_prompt_falls_back_when_no_messages(fake_cozeloop):
    _, client = fake_cozeloop

    prompt = MagicMock()
    prompt.prompt_template.messages = []
    client.get_prompt.return_value = prompt

    manager = CozeloopPromptManager(
        cozeloop_workspace_id="ws",
        cozeloop_token="tok",
        prompt_key="key",
    )

    result = manager.get_prompt(_make_context())
    assert result == DEFAULT_INSTRUCTION
