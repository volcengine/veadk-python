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

from unittest.mock import patch

from veadk import Agent


def test_explicit_key_beats_name(monkeypatch):
    """A key value passed explicitly wins over a key name (no lookup happens)."""
    monkeypatch.delenv("MODEL_AGENT_API_KEY", raising=False)
    with patch("veadk.auth.veauth.ark_veauth.get_ark_token") as g:
        agent = Agent(
            name="a", model_api_key="sk-EXPLICIT", model_api_key_name="some-name"
        )
        assert agent.model_api_key == "sk-EXPLICIT"
        g.assert_not_called()


def test_env_key_beats_name(monkeypatch):
    """MODEL_AGENT_API_KEY wins over a key name (no lookup happens)."""
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "sk-ENV")
    with patch("veadk.auth.veauth.ark_veauth.get_ark_token") as g:
        agent = Agent(name="b", model_api_key_name="some-name")
        assert agent.model_api_key == "sk-ENV"
        g.assert_not_called()


def test_name_resolves_when_no_key(monkeypatch):
    """With no key set, the value is resolved from the name."""
    monkeypatch.delenv("MODEL_AGENT_API_KEY", raising=False)
    with patch(
        "veadk.auth.veauth.ark_veauth.get_ark_token", return_value="sk-BY-NAME"
    ) as g:
        agent = Agent(name="c", model_api_key_name="my-key")
        assert agent.model_api_key == "sk-BY-NAME"
        g.assert_called_once_with(api_key_name="my-key")
