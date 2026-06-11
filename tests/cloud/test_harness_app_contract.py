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

"""Contract tests for the Harness server (``veadk.cloud.harness_app``).

These pin the HTTP request/response *schemas* and the ``HarnessApp`` surface so
that a change to a model field name, default, or route silently breaking the
deployed server (or the ``veadk agentkit harness`` CLI client) is caught here
rather than in production. No network or model access is required.
"""

import inspect

from veadk.cloud import harness_app
from veadk.cloud.harness_app import (
    AddHarnessRequest,
    AddHarnessResponse,
    Harness,
    HarnessApp,
    InvokeHarnessRequest,
    InvokeHarnessResponse,
    RunAgentRequest,
)
from veadk.consts import DEFAULT_MODEL_AGENT_NAME


def _fields(model) -> dict:
    """Map of pydantic field name -> FieldInfo for ``model``."""
    return dict(model.model_fields)


class TestHarnessModel:
    def test_fields(self):
        assert set(_fields(Harness)) == {
            "model_name",
            "tools",
            "skills",
            "system_prompt",
        }

    def test_defaults(self):
        fields = _fields(Harness)
        assert fields["model_name"].default == DEFAULT_MODEL_AGENT_NAME
        assert fields["tools"].default == ""
        assert fields["skills"].default == ""
        assert fields["system_prompt"].default == "You are a helpful assistant."

    def test_tools_and_skills_are_csv_strings(self):
        # The server splits these with _split_csv(); they must stay plain
        # strings, not lists, to keep the CLI/curl pass-through contract.
        h = Harness()
        assert isinstance(h.tools, str)
        assert isinstance(h.skills, str)


class TestRequestResponseSchemas:
    def test_add_request_fields(self):
        assert set(_fields(AddHarnessRequest)) == {"harness_name", "harness"}

    def test_add_response_fields_and_defaults(self):
        fields = _fields(AddHarnessResponse)
        assert set(fields) == {"code", "msg", "harness_name"}
        assert fields["code"].default == 200

    def test_run_agent_request_fields(self):
        assert set(_fields(RunAgentRequest)) == {"user_id", "session_id"}

    def test_invoke_request_fields(self):
        assert set(_fields(InvokeHarnessRequest)) == {
            "prompt",
            "harness_name",
            "harness",
            "run_agent_request",
        }

    def test_invoke_request_harness_is_optional(self):
        # A null `harness` means "use the stored one"; a non-null one is the
        # once-time override. The field must therefore allow None.
        assert _fields(InvokeHarnessRequest)["harness"].default is None

    def test_invoke_response_fields_and_defaults(self):
        fields = _fields(InvokeHarnessResponse)
        assert set(fields) == {"harness_name", "overwrite", "output"}
        assert fields["overwrite"].default is False


class TestHarnessApp:
    def test_public_methods_exist(self):
        for name in ("mount", "serve"):
            assert callable(getattr(HarnessApp, name))

    def test_serve_signature_defaults(self):
        sig = inspect.signature(HarnessApp.serve)
        assert sig.parameters["host"].default == "0.0.0.0"
        assert sig.parameters["port"].default == 8000

    def test_routes_registered(self):
        app = HarnessApp()
        paths = {getattr(route, "path", None) for route in app.app.routes}
        assert {"/harness/add", "/harness/invoke"} <= paths


class TestSplitCsv:
    def test_splits_and_trims(self):
        assert harness_app._split_csv("web_search, web_fetch") == [
            "web_search",
            "web_fetch",
        ]

    def test_empty_string_is_empty_list(self):
        assert harness_app._split_csv("") == []

    def test_drops_blank_segments(self):
        assert harness_app._split_csv("a,,  ,b") == ["a", "b"]
