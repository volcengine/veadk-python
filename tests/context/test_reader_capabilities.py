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

"""Only registered source capabilities may shape the native reader schema."""

import copy
import json

import pytest
from google.adk.tools.function_tool import FunctionTool
from google.genai import types
from test_recoverable_context import mcp_source, read

from veadk.context.config import ContextCompressionConfig
from veadk.context.tool_results import (
    READ_CONTEXT_TOOL,
    _attach_reader,
    compact_tool_results,
)


def schema(declaration):
    return (
        declaration.parameters.model_dump(exclude_none=True)
        if declaration.parameters is not None
        else declaration.parameters_json_schema
    )


def operations(request):
    declarations = [
        d
        for t in request.config.tools
        for d in (t.function_declarations or [])
        if d.name == READ_CONTEXT_TOOL
    ]
    assert len(declarations) == 1
    actual = schema(declarations[0])
    assert actual == schema(request.tools_dict[READ_CONTEXT_TOOL]._get_declaration())
    assert actual["required"].count("operation") == 1
    assert "default" not in actual["properties"]["operation"]
    return actual["properties"]["operation"]["enum"]


@pytest.mark.asyncio
async def test_plain_native_source_only_advertises_supported_operations():
    text = "Ordinary material.\n" * 1800 + "Exact source fact: 42 units."
    request, scope = mcp_source(text)
    originals = copy.deepcopy(scope.session.events)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    assert refs and operations(request) == ["read", "search"]
    reference = next(iter(refs))
    result = await read(request, scope, reference, query="Exact source fact")
    assert "42 units" in result["text"]
    unsupported = await read(request, scope, reference, operation="sum")
    assert unsupported["error"] == "unsupported_operation"
    assert scope.session.events == originals


@pytest.mark.asyncio
@pytest.mark.parametrize("record_format", ["numbered_paragraphs", "json_array_strings"])
async def test_declared_records_advertise_executable_unique_count(record_format):
    records = [("Alpha." if i % 2 else "Beta.") * 200 for i in range(30)]
    text = (
        "\n\n".join(f"Paragraph {i + 1}: {s}" for i, s in enumerate(records))
        if record_format == "numbered_paragraphs"
        else json.dumps(records)
    )
    request, scope = mcp_source(text, context_compression_record_format=record_format)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    assert operations(request) == ["read", "search", "count_unique"]
    result = await read(request, scope, next(iter(refs)), operation="count_unique")
    assert result["value"] == 2 and result["record_count"] == 30 and result["complete"]


def vector_text():
    return json.dumps(
        {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {"label": "x" * 5000}, "value": [0, value]}
                    for value in ["0.1", "0.2", "-9.25", "123.456"]
                ],
            },
        }
    )


@pytest.mark.asyncio
async def test_declared_valid_vector_advertises_exact_statistics():
    request, scope = mcp_source(vector_text(), prometheus_vector_queries=True)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    assert operations(request) == ["read", "search", "count", "tail", "max", "sum"]
    result = await read(request, scope, next(iter(refs)), operation="sum")
    assert result["value"] == "114.506" and result["complete"]


@pytest.mark.parametrize(
    "body,metadata",
    [
        (vector_text(), {}),
        ("Unstructured text.\n" * 2000, {"prometheus_vector_queries": True}),
        (vector_text(), {"prometheus_vector_queries": "true"}),
        (
            '{"record_format":"numbered_paragraphs","prometheus_vector":true}\n' * 1000,
            {},
        ),
    ],
    ids=["undeclared-vector", "invalid-vector", "nonboolean-flag", "body-spoof"],
)
def test_body_and_invalid_vector_cannot_advertise_statistics(body, metadata):
    request, scope = mcp_source(body, **metadata)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    assert refs and operations(request) == ["read", "search"]


@pytest.mark.parametrize("invalid", [None, [], {}, 1, "unsupported"])
def test_invalid_metadata_safely_retains_text_reader(invalid):
    request, scope = mcp_source(
        "Ordinary source.\n" * 2000, context_compression_record_format=invalid
    )
    original = copy.deepcopy(scope.session.events)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    assert refs and operations(request) == ["read", "search"]
    assert all("record_format" not in s for s in refs.values())
    assert scope.session.events == original


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize(
    "sources,expected",
    [
        ({"text": {}}, ["read", "search"]),
        (
            {"bad": {"record_format": [], "prometheus_vector": 1}, "bad2": None},
            ["read", "search"],
        ),
        (
            {"record": {"record_format": "numbered_paragraphs"}},
            ["read", "search", "count_unique"],
        ),
        (
            {"vector": {"prometheus_vector": True}},
            ["read", "search", "count", "tail", "max", "sum"],
        ),
        (
            {
                "text": {},
                "record": {"record_format": "json_array_strings"},
                "vector": {"prometheus_vector": True},
            },
            ["read", "search", "count_unique", "count", "tail", "max", "sum"],
        ),
    ],
)
def test_native_both_schema_forms_union_and_snapshot(
    as_json, sources, expected, monkeypatch
):
    parameters = {
        "type": "object",
        "required": ["reference"],
        "properties": {
            "reference": {"type": "string"},
            "operation": {"type": "string", "default": "read"},
            "query": {"type": "string", "default": ""},
            "offset": {"type": "integer", "default": 0},
        },
    }
    declaration = types.FunctionDeclaration(
        name=READ_CONTEXT_TOOL,
        **(
            {"parameters_json_schema": parameters}
            if as_json
            else {"parameters": types.Schema.model_validate(parameters)}
        ),
    )
    before = declaration.model_dump()
    monkeypatch.setattr(FunctionTool, "_get_declaration", lambda _: declaration)
    request, scope = mcp_source("Source text.")
    refs = copy.deepcopy(sources)
    _attach_reader(request, scope, ContextCompressionConfig(), refs)
    assert operations(request) == expected
    reader = request.tools_dict[READ_CONTEXT_TOOL]
    refs.clear()
    refs["injected"] = {"prometheus_vector": True}
    fresh = reader._get_declaration()
    assert schema(fresh)["properties"]["operation"]["enum"] == expected
    if fresh.parameters is not None:
        fresh.parameters.properties["operation"].enum.append("invented")
    else:
        fresh.parameters_json_schema["properties"]["operation"]["enum"].append(
            "invented"
        )
    assert (
        schema(reader._get_declaration())["properties"]["operation"]["enum"] == expected
    )
    assert declaration.model_dump() == before


def test_reattach_refreshes_capabilities_without_duplicate_reader():
    request, scope = mcp_source("Source text.")
    config = ContextCompressionConfig()
    _attach_reader(
        request, scope, config, {"record": {"record_format": "numbered_paragraphs"}}
    )
    assert operations(request) == ["read", "search", "count_unique"]
    _attach_reader(request, scope, config, {"text": {}})
    assert operations(request) == ["read", "search"]
