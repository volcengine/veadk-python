"""Literal read remains exact; search and guidance share the original budget."""

import copy
import json

import pytest
from test_recoverable_context import mcp_source, read
from veadk.context.config import ContextCompressionConfig
from veadk.context.tool_results import READ_CONTEXT_TOOL, compact_tool_results


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", [None, "read"])
@pytest.mark.parametrize(
    "query", ["approval code", "AUTHORIZATION", "不存在的中文短语"]
)
async def test_missing_literal_never_falls_back_to_search(operation, query):
    text = "Authorization code: approved for 42 units.\n" * 1500
    request, scope = mcp_source(text)
    original = copy.deepcopy(scope.session.events)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    scope.retrieval_headroom = 1600
    options = {} if operation is None else {"operation": operation}
    value = await read(request, scope, next(iter(refs)), query=query, **options)
    assert value["found"] is False and value["complete"] is False
    assert "text" not in value and "matches" not in value
    assert "search" in value["guidance"]
    cost = (
        len(
            json.dumps(
                json.dumps(value, ensure_ascii=False), ensure_ascii=False
            ).encode()
        )
        + 128
    )
    assert cost <= 1600 and scope.retrieval_headroom == 1600 - cost
    assert scope.retrieval_calls == 1 and scope.session.events == original


@pytest.mark.asyncio
async def test_search_does_not_require_an_exact_phrase_and_keeps_offsets():
    text = "Distant routine facts.\n" * 1500
    text += '许可 code KQ-783: exactly 42 units; quote="confirmed".\n'
    text += "Distant routine facts.\n" * 1500
    query = "KQ-783 许可 units"
    assert query not in text
    request, scope = mcp_source(text)
    original = copy.deepcopy(scope.session.events)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    scope.retrieval_headroom = 2400
    scope.retrieval_page_bytes = 600
    value = await read(
        request, scope, next(iter(refs)), operation="search", query=query
    )
    assert value["found"] and value["matches"]
    assert any("42 units" in match["text"] for match in value["matches"])
    for match in value["matches"]:
        assert match["text"] == text[match["offset"] : match["end"]]
    cost = (
        len(
            json.dumps(
                json.dumps(value, ensure_ascii=False), ensure_ascii=False
            ).encode()
        )
        + 128
    )
    assert cost <= 2400 and 0 <= scope.retrieval_headroom <= 2400 - cost
    assert scope.session.events == original


def test_reader_redeclaration_keeps_operation_required_without_aliasing():
    request, scope = mcp_source("Record of source evidence.\n" * 2000)
    config = ContextCompressionConfig()
    compact_tool_results(request, scope, config)
    tool = request.tools_dict[READ_CONTEXT_TOOL]
    first = tool._get_declaration()
    if first.parameters is not None:
        first.parameters.properties["operation"].enum.append("invented")
    else:
        first.parameters_json_schema["properties"]["operation"]["enum"].append(
            "invented"
        )

    def schema(declaration):
        return (
            declaration.parameters.model_dump(exclude_none=True)
            if declaration.parameters is not None
            else declaration.parameters_json_schema
        )

    fresh = schema(tool._get_declaration())
    assert "invented" not in fresh["properties"]["operation"]["enum"]
    assert fresh["required"].count("operation") == 1
    compact_tool_results(request, scope, config)
    declarations = [
        d
        for t in request.config.tools
        for d in (t.function_declarations or [])
        if d.name == READ_CONTEXT_TOOL
    ]
    assert len(declarations) == 1
    assert schema(declarations[0])["required"].count("operation") == 1


@pytest.mark.parametrize("as_json", [False, True])
def test_reader_schema_supports_both_adk_representations(as_json, monkeypatch):
    from google.adk.tools.function_tool import FunctionTool
    from google.genai import types
    from veadk.context.tool_results import _ContextReader

    schema = {
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
        name="veadk_read_context",
        **(
            {"parameters_json_schema": schema}
            if as_json
            else {"parameters": types.Schema.model_validate(schema)}
        ),
    )
    before = declaration.model_dump()
    monkeypatch.setattr(FunctionTool, "_get_declaration", lambda _: declaration)
    tool = _ContextReader(lambda: None, ("a", "u", "s", "g", ""))
    actual = tool._get_declaration()
    result = (
        actual.parameters_json_schema
        if as_json
        else actual.parameters.model_dump(exclude_none=True)
    )
    assert result["required"] == ["reference", "operation"]
    assert "default" not in result["properties"]["operation"]
    assert {"read", "search"} <= set(result["properties"]["operation"]["enum"])
    assert "case-sensitive" in result["properties"]["query"]["description"]
    assert declaration.model_dump() == before
