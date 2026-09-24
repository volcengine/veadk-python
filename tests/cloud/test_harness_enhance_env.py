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

import json

from veadk.cloud.harness_app.env_mapping import to_runtime_env


def test_harness_enhance_config_flattens_to_runtime_env():
    env = to_runtime_env(
        {
            "harness_enhance": {
                "enabled": True,
                "components": ["invocation_context", "compactor"],
                "profile": "analysis",
                "compression_provider": "heuristic",
                "max_context_chars": 12000,
                "max_tool_result_chars": 3000,
                "verifier_mode": "observe",
            }
        }
    )

    assert env["HARNESS_ENHANCE_ENABLED"] == "true"
    assert env["HARNESS_ENHANCE_COMPONENTS"] == "invocation_context,compactor"
    assert env["HARNESS_ENHANCE_PROFILE"] == "analysis"
    assert env["HARNESS_ENHANCE_COMPRESSION_PROVIDER"] == "heuristic"
    assert env["HARNESS_ENHANCE_MAX_CONTEXT_CHARS"] == "12000"
    assert env["HARNESS_ENHANCE_MAX_TOOL_RESULT_CHARS"] == "3000"
    assert env["HARNESS_ENHANCE_VERIFIER_MODE"] == "observe"
    assert env["HARNESS_COMPONENTS"] == "invocation_context,compactor"
    assert env["HARNESS_PROFILE"] == "analysis"
    assert env["HARNESS_COMPRESSION_PROVIDER"] == "heuristic"
    assert env["HARNESS_MAX_CONTEXT_CHARS"] == "12000"
    assert env["HARNESS_MAX_TOOL_RESULT_CHARS"] == "3000"
    assert env["HARNESS_VERIFIER_MODE"] == "observe"


def test_structured_skills_and_mcp_map_to_json_runtime_env():
    env = to_runtime_env(
        {
            "selected_skills": [
                {"source": "skillhub", "slug": "team/reporting"},
            ],
            "mcp": [
                {
                    "name": "db",
                    "server_url": "http://db.test/mcp",
                    "bear_token": "secret",
                },
            ],
        }
    )

    assert json.loads(env["SELECTED_SKILLS_JSON"]) == [
        {"source": "skillhub", "slug": "team/reporting"}
    ]
    assert json.loads(env["MCP_SERVERS_JSON"]) == [
        {
            "name": "db",
            "server_url": "http://db.test/mcp",
            "bear_token": "secret",
        }
    ]


def test_judgement_thresholds_survive_the_deploy_path():
    """A threshold set in ``harness_enhance`` must reach the built plugins.

    ``to_runtime_env`` flattens the section into ``HARNESS_ENHANCE_*``, the same
    spelling the strategy settings use, so the runtime has to read it there.
    """
    from veadk.extensions.harness.env import build_harness_plugins_from_env

    env = to_runtime_env(
        {
            "harness_enhance": {
                "enabled": True,
                "components": "context_engine,compressor,long_run_control",
                "compaction_keep_threshold": 0.8,
                "long_run_ready_threshold": 0.25,
                "mode_decision_threshold": 0.9,
            }
        }
    )

    plugins = {plugin.name: plugin for plugin in build_harness_plugins_from_env(env)}

    assert (
        plugins["harness_compress_plugin"].compressor.config.decision_keep_threshold
        == 0.8
    )
    assert plugins["harness_long_run_control_plugin"].ready_threshold == 0.25
    assert (
        plugins[
            "harness_invocation_context_plugin"
        ].context_builder.config.mode_decision_threshold
        == 0.9
    )
