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

import agentkit.toolkit.cli.cli as agentkit_cli
from click.testing import CliRunner

from veadk.cli import cli_agentkit
from veadk.cli.cli_agentkit import agentkit


class _FakeResponse:
    status_code = 200
    text = "{}"

    def json(self) -> dict[str, str]:
        return {"output": "ok"}


def test_agentkit_invoke_maps_harness_enhance_flags(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_post(
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> _FakeResponse:
        calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return _FakeResponse()

    monkeypatch.setattr("httpx.post", fake_post)

    result = CliRunner().invoke(
        agentkit,
        [
            "invoke",
            "--endpoint",
            "http://127.0.0.1:8000",
            "--apikey",
            "test-key",
            "--harness",
            "research-agent",
            "--user-id",
            "u1",
            "--session-id",
            "s1",
            "--model-id",
            "model-a",
            "--tools",
            "run_code",
            "--enable-harness-enhance",
            "--harness-components",
            "context_engine,compressor",
            "--harness-profile",
            "research",
            "--harness-compression-provider",
            "headroom",
            "find best model",
        ],
    )

    assert result.exit_code == 0
    assert result.output.strip() == "ok"
    assert calls[0]["url"] == "http://127.0.0.1:8000/harness/invoke"
    body = calls[0]["json"]
    headers = calls[0]["headers"]
    assert body["prompt"] == "find best model"
    assert body["harness_name"] == "research-agent"
    assert body["run_agent_request"] == {"user_id": "u1", "session_id": "s1"}
    assert body["harness"] == {"model_name": "model-a", "tools": "run_code"}
    assert body["harness_enhance"] == {
        "enabled": True,
        "components": "context_engine,compressor",
        "profile": "research",
        "compression_provider": "headroom",
    }
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["X-Harness-Enhance"] == "true"
    assert headers["X-Harness-Components"] == "context_engine,compressor"
    assert headers["X-Harness-Profile"] == "research"
    assert headers["X-Harness-Compression-Provider"] == "headroom"
    assert "X-Harness-Compression-Base-Url" not in headers
    assert "X-Harness-Max-Tool-Result-Chars" not in headers
    assert "X-Harness-Verifier-Mode" not in headers


def test_agentkit_invoke_falls_back_to_upstream_click_command(monkeypatch):
    calls: list[dict[str, object]] = []

    class FakeInvokeCommand:
        commands: dict[str, object] = {}

        def main(
            self,
            *,
            args: list[str],
            prog_name: str,
            standalone_mode: bool,
        ) -> None:
            calls.append(
                {
                    "args": args,
                    "prog_name": prog_name,
                    "standalone_mode": standalone_mode,
                }
            )

    monkeypatch.setattr(cli_agentkit, "_agentkit_invoke_command", None)
    monkeypatch.setattr(
        cli_agentkit,
        "_agentkit_invoke_click_command",
        FakeInvokeCommand(),
    )

    result = CliRunner().invoke(
        agentkit,
        [
            "invoke",
            "--endpoint",
            "http://127.0.0.1:8000",
            "--apikey",
            "test-key",
            "hello",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        {
            "args": [
                "--endpoint",
                "http://127.0.0.1:8000",
                "--apikey",
                "test-key",
                "hello",
            ],
            "prog_name": "invoke",
            "standalone_mode": False,
        }
    ]


def test_agentkit_invoke_lazy_loads_upstream_invoke_command(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_invoke_command(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(
        cli_agentkit,
        "_agentkit_invoke_command",
        cli_agentkit._AGENTKIT_INVOKE_COMMAND_NOT_LOADED,
    )
    monkeypatch.setattr(
        agentkit_cli, "invoke_command", fake_invoke_command, raising=False
    )

    cli_agentkit._delegate_agentkit_invoke(
        config_file=None,
        message="hello",
        payload=None,
        headers=None,
        runtime_id=None,
        endpoint="http://127.0.0.1:8000",
        region=None,
        a2a=False,
        show_reasoning=False,
        raw=False,
        apikey="test-key",
    )

    assert calls == [
        {
            "config_file": None,
            "message": "hello",
            "payload": None,
            "headers": None,
            "runtime_id": None,
            "endpoint": "http://127.0.0.1:8000",
            "region": None,
            "a2a": False,
            "show_reasoning": False,
            "raw": False,
            "apikey": "test-key",
        }
    ]


def test_is_harness_invoke_boolean_contract():
    assert cli_agentkit._is_harness_invoke(enable_harness_enhance=True) is True
    assert cli_agentkit._is_harness_invoke(enable_harness_enhance=False) is False
    assert cli_agentkit._is_harness_invoke(harness_components="compactor") is True


def test_json_object_value_returns_copy_for_harness_enhance_payload():
    payload_data: dict[str, object] = {"harness_enhance": {"enabled": False}}

    enhance = cli_agentkit._json_object_value(payload_data, "harness_enhance")
    enhance["enabled"] = True

    assert payload_data == {"harness_enhance": {"enabled": False}}


def test_build_harness_body_keeps_payload_enhance_explicitly_disabled():
    body = cli_agentkit._build_harness_body(
        message="hello",
        payload='{"harness_enhance": {"components": "compactor"}}',
        harness="test-harness",
        user_id="u1",
        session_id="s1",
        max_llm_calls=None,
        model_id=None,
        tools=None,
        skills=None,
        system_prompt=None,
        runtime=None,
        enable_harness_enhance=False,
        harness_components=None,
        harness_profile=None,
        harness_compression_provider=None,
    )

    assert body["harness_enhance"] == {
        "components": "compactor",
        "enabled": False,
    }


def test_build_harness_body_enable_flag_overrides_payload_disable():
    body = cli_agentkit._build_harness_body(
        message="hello",
        payload='{"harness_enhance": {"enabled": false, "components": "compactor"}}',
        harness="test-harness",
        user_id="u1",
        session_id="s1",
        max_llm_calls=None,
        model_id=None,
        tools=None,
        skills=None,
        system_prompt=None,
        runtime=None,
        enable_harness_enhance=True,
        harness_components=None,
        harness_profile=None,
        harness_compression_provider=None,
    )

    assert body["harness_enhance"] == {
        "enabled": True,
        "components": "compactor",
    }
