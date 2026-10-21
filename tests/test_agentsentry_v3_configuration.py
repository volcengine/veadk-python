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

import pytest


@pytest.fixture
def independent(monkeypatch):
    for key in (
        "TOOL_LLM_SHIELD_URL",
        "TOOL_LLM_SHIELD_APP_ID",
        "TOOL_LLM_SHIELD_API_KEY",
        "TOOL_LLM_SHIELD_REGION",
        "TOOL_LLM_SHIELD_ACCOUNT_ID",
        "ENABLE_LLM_SHIELD",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in {
        "AGENTSENTRY_URL": "http://sentry/OpenTOP/V3/Lumen/Moderate",
        "AGENTSENTRY_ACCOUNT_ID": "account",
        "AGENTSENTRY_INSTANCE_ID": "instance",
        "AGENTSENTRY_AK": "ak",
        "AGENTSENTRY_SK": "sk",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("AGENTSENTRY_REGION", raising=False)


@pytest.mark.parametrize("polluted", [False, True])
def test_independent_configuration(independent, monkeypatch, polluted):
    if polluted:
        for key, value in {
            "TOOL_LLM_SHIELD_URL": "https://public.example",
            "TOOL_LLM_SHIELD_APP_ID": "cloud-app",
            "TOOL_LLM_SHIELD_API_KEY": "cloud-secret",
            "TOOL_LLM_SHIELD_REGION": "cloud-region",
            "ENABLE_LLM_SHIELD": "false",
        }.items():
            monkeypatch.setenv(key, value)
    from veadk.tools.builtin_tools.llm_shield import LLMShieldPlugin

    plugin = LLMShieldPlugin()
    assert plugin._sentry_v3 is not None
    assert plugin._sentry_v3.account_id == "account"
    assert plugin._sentry_v3.access_key == "ak"
    assert plugin.region == "cn-private"
    assert plugin.api_key == ""


def test_invalid_private_url_never_falls_back(independent, monkeypatch):
    from veadk.tools.builtin_tools.llm_shield import LLMShieldPlugin

    monkeypatch.setenv("AGENTSENTRY_URL", "http://sentry/wrong-path")

    factory = LLMShieldPlugin
    with pytest.raises(ValueError, match="V3 Moderate URL"):
        factory()
