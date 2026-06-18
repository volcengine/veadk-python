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

"""Contract tests for the Harness server schemas (``veadk.cloud.harness_app``).

These pin the per-invocation override schema, the full creation-time config, and
the HTTP request/response models so that a change to a field name, default, or
the overridable/fixed split silently breaking the deployed server (or the
``veadk harness`` CLI, whose flags are generated from these fields) is caught
here rather than in production.

Only ``types`` and ``utils`` are imported: ``app.py`` builds the live agent at
import time, so it is intentionally left out to keep these tests offline.
"""

from veadk.cloud.harness_app.types import (
    HarnessCompactionMetric,
    HarnessConfig,
    HarnessEnhanceOverrides,
    HarnessOverrides,
    HarnessPluginMetrics,
    HarnessResponseMetrics,
    InvokeHarnessRequest,
    InvokeHarnessResponse,
    LlmUsageMetrics,
    RunAgentRequest,
)
from veadk.cloud.harness_app.utils import split_csv
from veadk.consts import DEFAULT_MODEL_AGENT_NAME
from veadk.prompts.agent_default_prompt import DEFAULT_INSTRUCTION


def _fields(model) -> dict:
    """Map of pydantic field name -> FieldInfo for ``model``."""
    return dict(model.model_fields)


class TestHarnessOverrides:
    def test_fields(self):
        assert set(_fields(HarnessOverrides)) == {
            "model_name",
            "tools",
            "skills",
            "system_prompt",
            "runtime",
        }

    def test_defaults(self):
        fields = _fields(HarnessOverrides)
        assert fields["model_name"].default == DEFAULT_MODEL_AGENT_NAME
        assert fields["tools"].default == ""
        assert fields["skills"].default == ""
        assert fields["system_prompt"].default == "You are a helpful assistant."
        assert fields["runtime"].default == "adk"

    def test_tools_and_skills_are_csv_strings(self):
        # The server splits these with split_csv(); they must stay plain strings,
        # not lists, to keep the CLI/curl pass-through contract.
        h = HarnessOverrides()
        assert isinstance(h.tools, str)
        assert isinstance(h.skills, str)

    def test_every_field_has_a_description(self):
        # Descriptions are the single source of truth for the generated
        # `veadk harness invoke` flags, so each field must carry one.
        for name, field in _fields(HarnessOverrides).items():
            assert field.description, f"{name} is missing a description"


class TestHarnessConfig:
    def test_extends_overrides(self):
        assert issubclass(HarnessConfig, HarnessOverrides)

    def test_adds_creation_time_fields(self):
        assert set(_fields(HarnessConfig)) == set(_fields(HarnessOverrides)) | {
            "app_name",
            "knowledgebase_type",
            "longterm_memory_type",
            "shortterm_memory_type",
            "max_llm_calls",
        }

    def test_component_defaults(self):
        fields = _fields(HarnessConfig)
        # Empty backend = component disabled; short-term memory defaults to local.
        assert fields["knowledgebase_type"].default == ""
        assert fields["longterm_memory_type"].default == ""
        assert fields["shortterm_memory_type"].default == "local"

    def test_system_prompt_default_is_veadk_instruction(self):
        # HarnessConfig overrides the override-layer default with VeADK's own.
        assert _fields(HarnessConfig)["system_prompt"].default == DEFAULT_INSTRUCTION

    def test_app_name_populated_via_name_alias(self):
        assert HarnessConfig(name="research-agent").app_name == "research-agent"
        assert HarnessConfig().app_name == "harness_app"


class TestRequestResponseSchemas:
    def test_run_agent_request_fields(self):
        assert set(_fields(RunAgentRequest)) == {
            "user_id",
            "session_id",
            "max_llm_calls",
        }

    def test_enhance_override_defaults(self):
        assert HarnessEnhanceOverrides().model_dump() == {
            "enabled": False,
            "components": "invocation_context,compactor,response_verification",
            "profile": "default",
            "compression_provider": None,
        }

    def test_invoke_request_fields(self):
        assert set(_fields(InvokeHarnessRequest)) == {
            "prompt",
            "harness_name",
            "harness",
            "harness_enhance",
            "run_agent_request",
        }

    def test_invoke_request_harness_is_optional_override(self):
        # A null `harness` means "use the served agent"; a non-null one is the
        # once-time override. The field must therefore allow None and default to it.
        field = _fields(InvokeHarnessRequest)["harness"]
        assert field.default is None
        assert field.annotation == (HarnessOverrides | None)

    def test_invoke_response_fields_and_defaults(self):
        fields = _fields(InvokeHarnessResponse)
        assert set(fields) == {
            "harness_name",
            "overwrite",
            "output",
            "metrics",
            "error",
        }
        assert fields["overwrite"].default is False
        assert fields["metrics"].default is None
        # `error` is unset on success and carries the message verbatim on failure.
        assert fields["error"].default is None

    def test_usage_metrics_accumulate(self):
        usage = LlmUsageMetrics(prompt_tokens=10, total_tokens=12, usage_event_count=1)
        usage.add(
            LlmUsageMetrics(
                prompt_tokens=20,
                completion_tokens=5,
                total_tokens=25,
                cached_tokens=3,
                usage_event_count=1,
            )
        )

        assert HarnessResponseMetrics(llm_usage=usage).model_dump() == {
            "llm_usage": {
                "prompt_tokens": 30,
                "completion_tokens": 5,
                "total_tokens": 37,
                "cached_tokens": 3,
                "usage_event_count": 2,
            },
            "harness_plugins": {
                "names": [],
                "compaction_reports": [],
            },
        }

    def test_harness_plugin_metrics_are_structured(self):
        metrics = HarnessResponseMetrics(
            harness_plugins=HarnessPluginMetrics(
                names=["harness_compress_plugin"],
                compaction_reports=[
                    HarnessCompactionMetric(
                        provider="builtin",
                        original_chars=8000,
                        compressed_chars=400,
                        changed=True,
                        tokens_before=2000,
                        tokens_after=100,
                        tokens_saved=1900,
                        compression_ratio=0.05,
                        transforms_applied=["builtin_tool_fact_compaction"],
                    )
                ],
            )
        )

        report = metrics.harness_plugins.compaction_reports[0]
        assert metrics.harness_plugins.names == ["harness_compress_plugin"]
        assert report.changed is True
        assert report.compressed_chars < report.original_chars


class TestSplitCsv:
    def test_splits_and_trims(self):
        assert split_csv("web_search, web_fetch") == ["web_search", "web_fetch"]

    def test_empty_string_is_empty_list(self):
        assert split_csv("") == []

    def test_drops_blank_segments(self):
        assert split_csv("a,,  ,b") == ["a", "b"]
