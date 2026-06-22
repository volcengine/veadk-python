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

import pytest

from veadk.cloud.harness_app.types import (
    HarnessConfig,
    HarnessOverrides,
    InvokeHarnessRequest,
    InvokeHarnessResponse,
    RunAgentRequest,
)
from veadk.cloud.harness_app.utils import (
    _download_and_extract_skill,
    _resolve_skill_slug,
    split_csv,
)
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

    def test_invoke_request_fields(self):
        assert set(_fields(InvokeHarnessRequest)) == {
            "prompt",
            "harness_name",
            "harness",
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
        assert set(fields) == {"harness_name", "overwrite", "output", "error"}
        assert fields["overwrite"].default is False
        # `error` is unset on success and carries the message verbatim on failure.
        assert fields["error"].default is None


class TestSplitCsv:
    def test_splits_and_trims(self):
        assert split_csv("web_search, web_fetch") == ["web_search", "web_fetch"]

    def test_empty_string_is_empty_list(self):
        assert split_csv("") == []

    def test_drops_blank_segments(self):
        assert split_csv("a,,  ,b") == ["a", "b"]


class _FakeResp:
    """Minimal stand-in for an ``httpx.Response``."""

    def __init__(self, *, status_code=200, json_data=None, content=b"", headers=None):
        self.status_code = status_code
        self._json = json_data
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self._json


class TestResolveSkillSlug:
    def test_exact_name_match_wins_even_when_not_first(self, monkeypatch):
        # The hub ranks "smart-web-scraper" above the exact "web-scraper"; the
        # exact Name match must still win (we scan the whole page, not just [0]).
        def fake_get(url, params=None, **kwargs):
            assert params["query"] == "web-scraper"
            return _FakeResp(
                json_data={
                    "Skills": [
                        {
                            "Name": "smart-web-scraper",
                            "Slug": "clawhub/m/smart-web-scraper",
                        },
                        {"Name": "web-scraper", "Slug": "clawhub/y/web-scraper"},
                    ]
                }
            )

        monkeypatch.setattr("veadk.cloud.harness_app.utils.httpx.get", fake_get)
        assert _resolve_skill_slug("web-scraper") == "clawhub/y/web-scraper"

    def test_value_with_slash_is_treated_as_explicit_slug(self, monkeypatch):
        def boom(*args, **kwargs):
            raise AssertionError("must not search when given an explicit slug")

        monkeypatch.setattr("veadk.cloud.harness_app.utils.httpx.get", boom)
        assert _resolve_skill_slug("clawhub/org/my-skill") == "clawhub/org/my-skill"

    def test_no_exact_match_raises(self, monkeypatch):
        monkeypatch.setattr(
            "veadk.cloud.harness_app.utils.httpx.get",
            lambda *a, **k: _FakeResp(
                json_data={"Skills": [{"Name": "other", "Slug": "clawhub/o/other"}]}
            ),
        )
        with pytest.raises(RuntimeError, match="not found in the skill hub"):
            _resolve_skill_slug("nonexistent-skill")

    def test_search_http_error_raises(self, monkeypatch):
        monkeypatch.setattr(
            "veadk.cloud.harness_app.utils.httpx.get",
            lambda *a, **k: _FakeResp(status_code=500, json_data={}),
        )
        with pytest.raises(RuntimeError, match="failed: HTTP 500"):
            _resolve_skill_slug("whatever")


class TestDownloadNonZip:
    def test_non_zip_200_gives_clear_error(self, monkeypatch, tmp_path):
        # An explicit slug skips the search; a 200 JSON error body (not a zip)
        # must surface clearly rather than as a BadZipFile.
        monkeypatch.setattr(
            "veadk.cloud.harness_app.utils.httpx.get",
            lambda *a, **k: _FakeResp(
                status_code=200,
                content=b'{"Error":{"Code":"InternalError"}}',
                headers={"content-type": "application/json"},
            ),
        )
        with pytest.raises(RuntimeError, match="did not return a zip"):
            _download_and_extract_skill("clawhub/org/my-skill", tmp_path)
