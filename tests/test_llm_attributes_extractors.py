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
from unittest.mock import Mock, call

from google.adk.models.llm_request import LlmRequest
from google.adk.tools.function_tool import FunctionTool
from opentelemetry.sdk.trace import TracerProvider

from veadk.tracing.telemetry.attributes.extractors.llm_attributes_extractors import (
    llm_gen_ai_request_functions,
    llm_gen_ai_usage_output_tokens,
)
from veadk.tracing.telemetry.attributes.extractors.types import ExtractorResponse


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


def test_missing_output_token_count_is_not_written_to_span():
    params = SimpleNamespace(
        llm_response=SimpleNamespace(
            usage_metadata=SimpleNamespace(candidates_token_count=None)
        )
    )
    response = llm_gen_ai_usage_output_tokens(params)
    span = Mock()

    ExtractorResponse.update_span(span, "gen_ai.usage.output_tokens", response)

    span.set_attribute.assert_not_called()


def test_falsy_attribute_values_are_written_to_span():
    span = Mock()

    ExtractorResponse.update_span(span, "zero", ExtractorResponse(content=0))
    ExtractorResponse.update_span(span, "false", ExtractorResponse(content=False))

    assert span.set_attribute.call_args_list == [call("zero", 0), call("false", False)]


def test_none_values_in_attribute_mappings_are_not_written_to_span():
    span = Mock()
    response = ExtractorResponse(
        content=[
            {
                "zero": 0,
                "false": False,
                "empty": "",
                "text": "present",
                "missing": None,
            }
        ]
    )

    ExtractorResponse.update_span(span, "unused", response)

    assert span.set_attribute.call_args_list == [
        call("zero", 0),
        call("false", False),
        call("empty", ""),
        call("text", "present"),
    ]


def test_none_values_in_event_mapping_are_not_written_to_span():
    span = Mock()
    response = ExtractorResponse(
        type="event",
        content={
            "zero": 0,
            "false": False,
            "empty": "",
            "text": "present",
            "missing": None,
        },
    )

    ExtractorResponse.update_span(span, "event.name", response)

    span.add_event.assert_called_once_with(
        "event.name",
        {"zero": 0, "false": False, "empty": "", "text": "present"},
    )


def test_none_values_in_event_mapping_list_are_not_written_to_span():
    span = Mock()
    response = ExtractorResponse(
        type="event",
        content=[
            {"zero": 0, "missing": None},
            {"false": False, "empty": "", "text": "present"},
        ],
    )

    ExtractorResponse.update_span(span, "event.name", response)

    assert span.add_event.call_args_list == [
        call("event.name", {"zero": 0}),
        call("event.name", {"false": False, "empty": "", "text": "present"}),
    ]


def test_none_values_in_event_list_mappings_are_not_written_to_span():
    span = Mock()
    response = ExtractorResponse(
        type="event_list",
        content=[
            {
                "event.one": {
                    "zero": 0,
                    "false": False,
                    "empty": "",
                    "missing": None,
                }
            },
            {"event.two": {"text": "present", "missing": None}},
        ],
    )

    ExtractorResponse.update_span(span, "unused", response)

    assert span.add_event.call_args_list == [
        call("event.one", {"zero": 0, "false": False, "empty": ""}),
        call("event.two", {"text": "present"}),
    ]


def test_none_values_are_filtered_before_reaching_real_otel_span():
    provider = TracerProvider()
    span = provider.get_tracer(__name__).start_span("extractor-response")

    ExtractorResponse.update_span(
        span,
        "event.one",
        ExtractorResponse(type="event", content={"zero": 0, "missing": None}),
    )
    ExtractorResponse.update_span(
        span,
        "unused",
        ExtractorResponse(
            type="event_list",
            content=[{"event.two": {"false": False, "missing": None}}],
        ),
    )

    assert [(event.name, dict(event.attributes)) for event in span.events] == [
        ("event.one", {"zero": 0}),
        ("event.two", {"false": False}),
    ]
    span.end()
    provider.shutdown()
