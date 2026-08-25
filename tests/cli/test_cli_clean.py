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

from __future__ import annotations

from typing import Any

from click.testing import CliRunner

from veadk.cli.cli_clean import clean


class _FakeVeFaaS:
    calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.calls.append({"init": kwargs, "deleted": []})

    def find_app_id_by_name(self, name: str) -> str | None:
        self.calls[-1].setdefault("lookups", []).append(name)
        if len(self.calls[-1]["lookups"]) == 1:
            return "app-123"
        return None

    def delete(self, app_id: str | None) -> None:
        self.calls[-1]["deleted"].append(app_id)


def test_clean_defaults_to_volcengine_environment(
    monkeypatch,
) -> None:
    monkeypatch.delenv("AGENTKIT_CLOUD_PROVIDER", raising=False)
    monkeypatch.delenv("CLOUD_PROVIDER", raising=False)
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "volc-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "volc-sk")
    monkeypatch.setenv("VOLCENGINE_SESSION_TOKEN", "volc-token")
    monkeypatch.setenv("REGION", "cn-shanghai")
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _FakeVeFaaS)
    _FakeVeFaaS.calls.clear()

    result = CliRunner().invoke(
        clean,
        ["--vefaas-app-name", "studio-app"],
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    assert _FakeVeFaaS.calls == [
        {
            "init": {
                "access_key": "volc-ak",
                "secret_key": "volc-sk",
                "session_token": "volc-token",
                "region": "cn-shanghai",
                "provider": "volcengine",
            },
            "deleted": ["app-123"],
            "lookups": ["studio-app", "studio-app"],
        }
    ]


def test_clean_uses_byteplus_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.delenv("AGENTKIT_CLOUD_PROVIDER", raising=False)
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "byteplus-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "byteplus-sk")
    monkeypatch.setenv("BYTEPLUS_SESSION_TOKEN", "byteplus-token")
    monkeypatch.setenv("BYTEPLUS_REGION", "ap-southeast-1")
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "volc-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "volc-sk")
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _FakeVeFaaS)
    _FakeVeFaaS.calls.clear()

    result = CliRunner().invoke(
        clean,
        ["--vefaas-app-name", "studio-app"],
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    assert _FakeVeFaaS.calls[0]["init"] == {
        "access_key": "byteplus-ak",
        "secret_key": "byteplus-sk",
        "session_token": "byteplus-token",
        "region": "ap-southeast-1",
        "provider": "byteplus",
    }
    assert _FakeVeFaaS.calls[0]["deleted"] == ["app-123"]


def test_clean_explicit_byteplus_options_override_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "env-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "env-sk")
    monkeypatch.setenv("BYTEPLUS_SESSION_TOKEN", "env-token")
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _FakeVeFaaS)
    _FakeVeFaaS.calls.clear()

    result = CliRunner().invoke(
        clean,
        [
            "--provider",
            "byteplus",
            "--region",
            "ap-southeast-1",
            "--byteplus-access-key",
            "cli-ak",
            "--byteplus-secret-key",
            "cli-sk",
            "--byteplus-session-token",
            "cli-token",
            "--vefaas-app-name",
            "studio-app",
        ],
        input="y\n",
    )

    assert result.exit_code == 0, result.output
    assert _FakeVeFaaS.calls[0]["init"] == {
        "access_key": "cli-ak",
        "secret_key": "cli-sk",
        "session_token": "cli-token",
        "region": "ap-southeast-1",
        "provider": "byteplus",
    }
