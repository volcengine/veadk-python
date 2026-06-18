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

from click.testing import CliRunner

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
            "paper-researcher",
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
    assert body["harness_name"] == "paper-researcher"
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
