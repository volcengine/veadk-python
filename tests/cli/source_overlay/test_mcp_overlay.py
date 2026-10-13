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
"""Custom applications keep ownership of their MCP policy wrappers."""

from types import SimpleNamespace
import json

import pytest

from veadk.cli.legacy_runtime_recovery import _SITECUSTOMIZE


def replace_mcp():
    namespace = {}
    # Exercise the actual generated functions without installing a process hook.
    source = _SITECUSTOMIZE.rsplit("\n_install()", 1)[0]
    exec(compile(source, "studio-overlay-test", "exec"), namespace)
    return namespace["_replace_mcp"]


def test_custom_handler_retains_wrappers_and_visits_children():
    wrapper = object()
    observed = []
    child = SimpleNamespace(
        name="child",
        tools=[wrapper],
        sub_agents=[],
        _veadk_studio_mcp_overlay_handler=observed.append,
    )
    root = SimpleNamespace(name="root", tools=[], sub_agents=[child])
    selection = [
        {
            "name": "fixture",
            "transport": "http",
            "url": "https://fixture.invalid/mcp",
            "authTokenEnv": "MISSING_FIXTURE_TOKEN",
        }
    ]
    replace_mcp()(root, {"child": selection})
    assert observed == [selection]
    assert child.tools == [wrapper]


def test_custom_handler_failure_does_not_fall_back_to_bare_mcp():
    wrapper = object()

    def refuse(entries):
        raise RuntimeError("domain policy refused")

    root = SimpleNamespace(
        name="root",
        tools=[wrapper],
        sub_agents=[],
        _veadk_studio_mcp_overlay_handler=refuse,
    )
    with pytest.raises(RuntimeError, match="domain policy refused"):
        replace_mcp()(root, {"root": []})
    assert root.tools == [wrapper]


def test_non_callable_handler_is_rejected():
    root = SimpleNamespace(
        name="root", tools=[], sub_agents=[], _veadk_studio_mcp_overlay_handler=True
    )
    with pytest.raises(RuntimeError, match="handler is invalid"):
        replace_mcp()(root, {"root": []})


@pytest.mark.parametrize("empty", [False, True])
def test_environment_bootstrap_preserves_application_wrapper(
    tmp_path, monkeypatch, empty
):
    monkeypatch.setenv("VEADK_STUDIO_SKILL_OVERLAY", str(tmp_path))
    (tmp_path / "mcp-bootstrap.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "mode": "application-environment",
            }
        )
    )
    entries = (
        []
        if empty
        else [
            {
                "name": "fixture",
                "transport": "http",
                "url": "https://fixture.invalid/mcp",
                "authTokenEnv": "FIXTURE_AUTH",
            }
        ]
    )
    servers = (
        []
        if empty
        else [
            {
                "name": "fixture",
                "url": "https://fixture.invalid/mcp",
                "headers": {"Authorization": "Bearer synthetic-value"},
            }
        ]
    )
    monkeypatch.setenv("FIXTURE_AUTH", "synthetic-value")
    monkeypatch.setenv("MCP_SERVERS_JSON", json.dumps(servers))
    wrapper = object()
    root = SimpleNamespace(name="root", tools=[wrapper], sub_agents=[])
    replace_mcp()(root, {"root": entries})
    assert root.tools == [wrapper]
    calls = []
    root._veadk_studio_mcp_overlay_handler = calls.append
    replace_mcp()(root, {"root": entries})
    assert calls == [entries]
    assert root.tools == [wrapper]


@pytest.mark.parametrize(
    "badcase", ["missing", "malformed", "mismatch", "credential", "topology", "mode"]
)
def test_environment_bootstrap_rejects_invalid_state_without_exposing_values(
    tmp_path, monkeypatch, badcase
):
    monkeypatch.setenv("VEADK_STUDIO_SKILL_OVERLAY", str(tmp_path))
    (tmp_path / "mcp-bootstrap.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "mode": "unknown" if badcase == "mode" else "application-environment",
            }
        )
    )
    selection = [
        {
            "name": "fixture",
            "transport": "http",
            "url": "https://fixture.invalid/mcp",
            "authTokenEnv": "FIXTURE_AUTH",
        }
    ]
    monkeypatch.setenv("FIXTURE_AUTH", "synthetic-value")
    monkeypatch.setenv(
        "MCP_SERVERS_JSON",
        json.dumps(
            [
                {
                    "name": "fixture",
                    "url": "https://fixture.invalid/mcp",
                    "headers": {"Authorization": "Bearer synthetic-value"},
                }
            ]
        ),
    )
    if badcase == "missing":
        monkeypatch.delenv("MCP_SERVERS_JSON")
    elif badcase == "malformed":
        monkeypatch.setenv("MCP_SERVERS_JSON", "synthetic-value")
    elif badcase == "mismatch":
        monkeypatch.setenv("MCP_SERVERS_JSON", "[]")
    elif badcase == "credential":
        monkeypatch.delenv("FIXTURE_AUTH")
    wrapper = object()
    root = SimpleNamespace(name="root", tools=[wrapper], sub_agents=[])
    configuration = {"root": selection}
    if badcase == "topology":
        root.sub_agents.append(SimpleNamespace(name="child", tools=[], sub_agents=[]))
        configuration["child"] = []
    with pytest.raises(RuntimeError, match="Studio MCP bootstrap") as error:
        replace_mcp()(root, configuration)
    assert "synthetic-value" not in str(error.value)
    assert "fixture.invalid" not in str(error.value)
    assert root.tools == [wrapper]


@pytest.mark.parametrize("invalid", [None, "child", "stdio", "owner"])
def test_bootstrap_build_rejects_ambiguous_ownership_and_topology(invalid):
    from veadk.cli.legacy_runtime_recovery import (
        LegacyRecoveryError,
        build_source_preserving_overlay,
    )

    draft = {"name": "root", "selectedSkills": [], "mcpTools": []}
    if invalid == "child":
        draft["subAgents"] = [{"name": "child", "mcpTools": []}]
    if invalid == "stdio":
        draft["mcpTools"] = [
            {"name": "local", "transport": "stdio", "command": "tool", "args": []}
        ]

    def build():
        return build_source_preserving_overlay(
            source_image="example-cn-shanghai.cr.volces.com/agentkit/fixture@sha256:"
            + "a" * 64,
            published_draft=draft,
            edited_draft=draft,
            canonical_skills=[],
            application_mcp=invalid != "owner",
            application_mcp_bootstrap=True,
        )

    if invalid is not None:
        with pytest.raises(LegacyRecoveryError, match="bootstrap_topology_unsupported"):
            build()
    else:
        files = {f["path"]: f["content"] for f in build()}
        assert json.loads(files[".veadk-studio-overlay/mcp.json"]) == {"root": []}
        assert json.loads(files[".veadk-studio-overlay/mcp-bootstrap.json"]) == {
            "schemaVersion": 1,
            "mode": "application-environment",
        }
