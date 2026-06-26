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
