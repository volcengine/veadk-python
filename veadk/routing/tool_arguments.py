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
"""Validate model-produced tool arguments against the advertised contract.

The guard runs after user callbacks and before execution, only in routed turns.
It never retries a tool that has already executed or changes the selected model.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from jsonschema import Draft202012Validator

from veadk.routing.context import get_turn_context

_BUDGET_KEY = "veadk:query_routing:tool_argument_errors"
_MAX_CORRECTIONS = 2


def _schema(value: Any) -> Any:
    """Translate GenAI schema types and nullable into JSON Schema."""
    if isinstance(value, list):
        return [_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = copy.deepcopy(value)
    # Only schema-bearing keywords are recursive. Defaults, const and enum
    # may contain arbitrary objects whose own 'type' keys are user data.
    for key in (
        "properties",
        "patternProperties",
        "$defs",
        "definitions",
        "dependentSchemas",
    ):
        if isinstance(result.get(key), dict):
            result[key] = {name: _schema(item) for name, item in result[key].items()}
    for key in (
        "items",
        "prefixItems",
        "additionalProperties",
        "unevaluatedProperties",
        "unevaluatedItems",
        "contains",
        "propertyNames",
        "not",
        "if",
        "then",
        "else",
        "anyOf",
        "allOf",
        "oneOf",
    ):
        if key in result:
            result[key] = _schema(result[key])
    for key in ("$ref", "$dynamicRef"):
        if key in result and not result[key].startswith("#"):
            raise ValueError("routing tool schemas must use local references")
    if isinstance(result.get("type"), str):
        result["type"] = result["type"].lower()
    if result.pop("nullable", False):
        return {"anyOf": [result, {"type": "null"}]}
    return result


async def validate_tool_arguments(tool, args, tool_context):
    turn = get_turn_context()
    if turn is None or turn.selection.shadow:
        return None
    declaration = tool._get_declaration()
    if declaration is None:
        return None
    schema = declaration.parameters_json_schema
    if schema is None and declaration.parameters is not None:
        schema = _schema(declaration.parameters.model_dump(exclude_none=True))
    if schema is None:
        return None
    # Check references in JSON schemas as well; validation must not perform IO.
    schema = _schema(schema)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    normalized = copy.deepcopy(args)
    for error in validator.iter_errors(normalized):
        # Only an unambiguous integer declaration permits normalization. In
        # particular, never truncate fractions or convert booleans to integers.
        if (
            error.validator == "type"
            and error.validator_value == "integer"
            and isinstance(error.instance, str)
            and re.fullmatch(r"-?(?:0|[1-9][0-9]{0,127})", error.instance)
            and error.absolute_path
        ):
            parent = normalized
            path = list(error.absolute_path)
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = int(error.instance)
    errors = list(validator.iter_errors(normalized))
    if not errors:
        args.clear()
        args.update(normalized)
        return None

    record = tool_context.state.get(_BUDGET_KEY, {})
    previous = (
        record.get("count", 0)
        if record.get("invocation_id") == turn.selection.invocation_id
        else 0
    )
    count = max(previous, turn.tool_argument_errors.get("count", 0)) + 1
    turn.tool_argument_errors["count"] = count
    tool_context.state[_BUDGET_KEY] = {
        "invocation_id": turn.selection.invocation_id,
        "count": count,
    }
    if count > _MAX_CORRECTIONS:
        raise ValueError("routing tool argument correction budget exhausted")
    return {
        "error": "invalid_tool_arguments",
        "retryable": True,
        "corrections_remaining": _MAX_CORRECTIONS - count,
        "instruction": "Correct the arguments using the tool schema before retrying.",
        # Error messages/instances can contain secrets. Only schema locations
        # and rule names are returned; argument values never enter this result.
        "issues": [
            {"schema_path": list(error.absolute_schema_path), "rule": error.validator}
            for error in errors[:8]
        ],
    }
