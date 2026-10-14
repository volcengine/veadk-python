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
"""Application identity must survive platform Sidecar environment cleanup."""

import json

import pytest

from veadk.cli.cli_frontend import _filter_harness_runtime_environment
from veadk.cli.legacy_runtime_recovery import _SITECUSTOMIZE


@pytest.mark.parametrize("sidecar_disabled", [False, True])
def test_source_preserving_filtered_environment_starts_matching_app(
    tmp_path, monkeypatch, sidecar_disabled
):
    from google.adk.agents import LlmAgent
    from google.adk.apps.app import App

    filtered = _filter_harness_runtime_environment(
        {
            "HARNESS_NAME": "fixture-app",
            "HARNESS_SIDECAR_ENABLED": str(not sidecar_disabled).lower(),
            "HARNESS_SIDECAR_EXPECTED_PLAN_HASH": "obsolete-plan",
            "HARNESS_SIDECAR_APIG_API_KEY": "synthetic-value",
            "MCP_SERVERS_JSON": "[]",
        },
        preserve_disabled_contract=sidecar_disabled,
        preserve_application_identity=True,
    )
    assert filtered["HARNESS_NAME"] == "fixture-app"
    assert "HARNESS_SIDECAR_EXPECTED_PLAN_HASH" not in filtered
    assert "HARNESS_SIDECAR_APIG_API_KEY" not in filtered
    assert "synthetic-value" not in json.dumps(filtered)
    for filename, content in {
        "managed.json": [],
        "selected.json": [],
        "final.json": [],
        "mcp.json": {"fixture_app": []},
        "mcp-bootstrap.json": {
            "schemaVersion": 1,
            "mode": "application-environment",
        },
    }.items():
        (tmp_path / filename).write_text(json.dumps(content))
    for key, value in filtered.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("VEADK_STUDIO_SKILL_OVERLAY", str(tmp_path))
    monkeypatch.setenv("VEADK_STUDIO_OVERLAY_READY_FILE", str(tmp_path / "ready"))
    monkeypatch.setattr(App, "__init__", App.__init__)
    exec(compile(_SITECUSTOMIZE, "studio-overlay-test", "exec"), {})
    # The historical SDK derives Agent identity from the application name.
    name = filtered.get("HARNESS_NAME", "harness_app").replace("-", "_")
    root = LlmAgent(name=name, tools=[])
    App(name=name, root_agent=root)
    assert (tmp_path / "ready").read_text() == "ready\n"


@pytest.mark.parametrize("preserve", [False, True])
def test_identity_retention_is_explicit_and_never_invents_a_name(preserve):
    filtered = _filter_harness_runtime_environment(
        {"HARNESS_NAME": "fixture-app", "OTHER_SETTING": "retained"},
        preserve_disabled_contract=False,
        preserve_application_identity=preserve,
    )
    assert ("HARNESS_NAME" in filtered) is preserve
    assert filtered["OTHER_SETTING"] == "retained"
    assert (
        _filter_harness_runtime_environment(
            {},
            preserve_disabled_contract=True,
            preserve_application_identity=preserve,
        )
        == {}
    )
