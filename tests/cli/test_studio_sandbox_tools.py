# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for deploy-time Studio Sandbox Tool provisioning."""

from types import SimpleNamespace

from veadk.cli.studio_sandbox_tools import ensure_studio_code_env_tool


def test_ensure_studio_code_env_tool_reuses_ready_exact_name() -> None:
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="veadk-studio-demo-chat-12345678",
                    project_name="default",
                    tool_type="CodeEnv",
                    tool_id="tool-existing",
                )
            ],
            next_token=None,
        ),
        get_tool=lambda _: SimpleNamespace(status="Ready"),
        create_tool=lambda _: (_ for _ in ()).throw(
            AssertionError("ready Tool must be reused")
        ),
    )

    assert (
        ensure_studio_code_env_tool(
            name="veadk-studio-demo-chat-12345678",
            client=client,
            timeout_seconds=0,
        )
        == "tool-existing"
    )


def test_ensure_studio_code_env_tool_creates_ready_code_env() -> None:
    requests: list[object] = []

    def _create(request: object) -> SimpleNamespace:
        requests.append(request)
        return SimpleNamespace(tool_id="tool-created")

    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=lambda _: SimpleNamespace(status="Ready"),
        create_tool=_create,
    )

    assert (
        ensure_studio_code_env_tool(
            name="veadk-studio-demo-skill-12345678",
            client=client,
            timeout_seconds=0,
        )
        == "tool-created"
    )
    request = requests[0]
    assert getattr(request, "name") == "veadk-studio-demo-skill-12345678"
    assert getattr(request, "tool_type") == "CodeEnv"
    assert getattr(request, "project_name") == "default"
    assert getattr(request, "cpu_milli") == 4000
    assert getattr(request, "memory_mb") == 8192
    assert getattr(request, "envs") is None
