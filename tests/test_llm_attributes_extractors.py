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
from types import SimpleNamespace
from unittest.mock import Mock

from google.adk.models.llm_request import LlmRequest
from google.adk.tools.function_tool import FunctionTool

from veadk.tracing.telemetry.attributes.extractors.llm_attributes_extractors import (
    llm_gen_ai_request_functions,
)


def test_request_functions_reuses_adk_request_declaration(monkeypatch):
    def search(query: str) -> str:
        """Search indexed documents."""
        return query

    tool = FunctionTool(search)
    request = LlmRequest()
    request.append_tools([tool])

    def fail_if_declaration_is_rebuilt():
        raise AssertionError("request declaration should be reused")

    monkeypatch.setattr(tool, "_get_declaration", fail_if_declaration_is_rebuilt)

    response = llm_gen_ai_request_functions(SimpleNamespace(llm_request=request))

    function = response.content[0]
    parameters = json.loads(function["gen_ai.request.functions.0.parameters"])
    assert function["gen_ai.request.functions.0.name"] == "search"
    assert function["gen_ai.request.functions.0.description"] == (
        "Search indexed documents."
    )
    assert parameters["type"] == "object"
    assert "query" in parameters["properties"]


def test_request_functions_supports_legacy_parameters_schema():
    parameters = Mock()
    parameters.model_dump_json.return_value = '{"type":"object"}'
    declaration = SimpleNamespace(name="search", parameters=parameters)
    tool = SimpleNamespace(
        name="search",
        description="Search documents.",
        _get_declaration=Mock(side_effect=AssertionError("unexpected rebuild")),
    )
    request = SimpleNamespace(
        config=SimpleNamespace(
            tools=[SimpleNamespace(function_declarations=[declaration])]
        ),
        tools_dict={"search": tool},
    )

    response = llm_gen_ai_request_functions(SimpleNamespace(llm_request=request))

    assert response.content[0]["gen_ai.request.functions.0.parameters"] == (
        '{"type":"object"}'
    )
    parameters.model_dump_json.assert_called_once_with(exclude_none=True)
    tool._get_declaration.assert_not_called()


def test_request_functions_builds_missing_declaration_once():
    declaration = SimpleNamespace(
        name="search",
        parameters=None,
        parameters_json_schema={"type": "object"},
    )
    get_declaration = Mock(return_value=declaration)
    tool = SimpleNamespace(
        name="search",
        description="Search documents.",
        _get_declaration=get_declaration,
    )
    request = SimpleNamespace(
        config=SimpleNamespace(tools=[]),
        tools_dict={"search": tool},
    )

    response = llm_gen_ai_request_functions(SimpleNamespace(llm_request=request))

    parameters = json.loads(
        response.content[0]["gen_ai.request.functions.0.parameters"]
    )
    assert parameters == {"type": "object"}
    get_declaration.assert_called_once_with()
