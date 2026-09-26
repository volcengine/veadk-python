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

"""Preview explicitly eligible text fields, retrieving originals from Session.

No new raw-content store, file path or URL is introduced. References are scoped
to the current request and resolve only to its session's original tool events.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections import Counter
from typing import Any

from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .budget import ContextBudgetError
from .evidence import current_question, repeated_projection
from .history import is_user_turn
from .operations import count_unique, search
from .read_projection import compact_pages
from .references import register, resolve, saved_references
from .runtime import current_scope
from .retrieval import prepared_preview, search_original
from .search_budget import (
    ALIAS_GUIDANCE,
    SEARCH_FIELDS,
    contains_protected,
    reserve_parallel_exchanges,
    reuse_credit,
)
from .vector_queries import overview, statistic

READ_CONTEXT_TOOL = "veadk_read_context"


class _ContextReader(FunctionTool):
    def __init__(self, function, identity, references=None):
        super().__init__(function)
        self.context_identity = identity
        # Freeze capabilities, not original content, into the declaration.
        operations = ["read", "search"]
        sources = None if references is None else tuple(references.values())
        if sources is None or any(
            isinstance(s, dict)
            and isinstance(s.get("record_format"), str)
            and s["record_format"] in {"numbered_paragraphs", "json_array_strings"}
            for s in sources
        ):
            operations.append("count_unique")
        if sources is None or any(
            isinstance(s, dict) and s.get("prometheus_vector") is True for s in sources
        ):
            operations.extend(["count", "tail", "max", "sum"])
        self.context_operations = tuple(operations)

    def _get_declaration(self):
        # The model must choose an operation. Keep the Python callable's default
        # for direct callers and previously saved calls; never reinterpret read.
        declaration = super()._get_declaration()
        if declaration is None:
            return declaration
        declaration = declaration.model_copy(deep=True)
        operations = list(self.context_operations)
        declaration.description = (
            "Retrieve omitted original evidence when retained excerpts are insufficient. "
            "Observe remaining_calls; never infer missing facts."
        )
        if "count_unique" in operations:
            declaration.description += (
                " count_unique requires a source with declared records."
            )
        if "count" in operations:
            declaration.description += (
                " count/tail/max/sum require a source with declared vectors."
            )
        descriptions = {
            "operation": "Choose explicitly: read exact text or search passages.",
            "reference": "Reference from the compressed preview.",
            "query": "search: words or a short question; read: exact case-sensitive text, or empty to page from offset. Max 256 characters.",
        }
        if declaration.parameters is not None:
            parameters = declaration.parameters
            if parameters.properties is None:
                raise ValueError("context_reader_schema_missing_properties")
            for name, description in descriptions.items():
                parameters.properties[name].description = description
            operation = parameters.properties["operation"]
            operation.default = None
            operation.enum = operations
            parameters.required = list(
                dict.fromkeys([*(parameters.required or []), "operation"])
            )
        elif isinstance(declaration.parameters_json_schema, dict):
            parameters = declaration.parameters_json_schema
            for name, description in descriptions.items():
                parameters["properties"][name]["description"] = description
            operation = parameters["properties"]["operation"]
            operation.pop("default", None)
            operation["enum"] = operations
            parameters["required"] = list(
                dict.fromkeys([*parameters.get("required", []), "operation"])
            )
        return declaration


def _eligible_fields(tool) -> tuple[str, ...]:
    metadata = getattr(tool, "custom_metadata", None) or {}
    fields = metadata.get("context_compression_text_fields")
    if isinstance(fields, (list, tuple)) and all(
        isinstance(field, str) for field in fields
    ):
        return tuple(fields)
    function = getattr(tool, "func", None)
    if function is not None and inspect.signature(function).return_annotation in (
        str,
        "str",
    ):
        return ("result",)
    return ()


def _record_overview(text, source, remaining_bytes):
    """Add exact declared statistics only in unused projection space."""
    record_format = source.get("record_format")
    if not record_format or remaining_bytes <= 0:
        return ""
    try:
        result = count_unique(text, record_format)
    except (ValueError, TypeError, RecursionError):
        return ""
    addition = "\nEXACT_RECORD_OVERVIEW=" + json.dumps(
        {
            "record_format": record_format,
            "record_count": result["record_count"],
            "unique_record_count": result["value"],
            "complete": result["complete"],
            "equality": result["equality"],
            "source_sha256": source["text_hash"],
        },
        separators=(",", ":"),
    )
    return addition if len(addition.encode()) <= remaining_bytes else ""


def _compression_candidates(request, scope, config):
    """One eligibility path for async retrieval and synchronous projection."""
    if scope is None:
        return
    sources = max(
        1,
        sum(
            bool(p.function_response and p.function_response.name != READ_CONTEXT_TOOL)
            for c in request.contents
            for p in c.parts or []
        ),
    )
    maximum = min(
        config.tool_result_max_bytes,
        (scope.projection_bytes or config.tool_result_max_bytes) // sources,
    )
    if config.tool_result_max_bytes < 16000:
        maximum = min(maximum, config.tool_result_max_bytes // 4)
    for content in request.contents:
        for part in content.parts or []:
            response = part.function_response
            if response is None or getattr(response, "will_continue", False):
                continue
            if response.name == READ_CONTEXT_TOOL or not isinstance(
                response.response, dict
            ):
                continue
            tool = request.tools_dict.get(response.name)
            metadata = getattr(tool, "custom_metadata", None) or {}
            fields: list[tuple[str | int, ...]] = [
                (field,) for field in _eligible_fields(tool)
            ]
            is_mcp = metadata.get("mcp_text_preview") is True or any(
                cls.__module__ == "google.adk.tools.mcp_tool.mcp_tool"
                and cls.__name__ in {"McpTool", "MCPTool"}
                for cls in type(tool).__mro__
            )
            payload = response.response
            if (
                is_mcp
                and set(payload) <= {"content", "isError"}
                and payload.get("isError", False) is False
                and isinstance(payload.get("content"), list)
            ):
                fields.extend(
                    ("content", i, "text")
                    for i, block in enumerate(payload["content"])
                    if isinstance(block, dict)
                    and set(block) == {"type", "text"}
                    and block["type"] == "text"
                )
            for path in fields:
                parent = response.response
                for key in path[:-1]:
                    parent = parent[key]
                field = path[-1]
                text = parent.get(field)
                if (
                    not isinstance(text, str)
                    # A configured cap must not exempt a source that exceeds
                    # its share of the active request's projection budget.
                    or len(text.encode("utf-8")) <= maximum
                ):
                    continue
                if any(required in text for required in config.protected_context):
                    continue
                source = _find_original(scope, response, path, text)
                if source is None:
                    continue
                yield parent, field, text, source, metadata, maximum, sources


def compact_tool_results(
    request, scope, config, *, references=None, attach_reader=True, compact_reads=True
):
    refs = saved_references(scope)
    refs.update(references or {})
    if scope is None:
        return refs
    scope.restored_references.clear()
    question = current_question(request.contents)
    for (
        parent,
        field,
        text,
        source,
        metadata,
        maximum,
        sources,
    ) in _compression_candidates(request, scope, config):
        record_format = metadata.get("context_compression_record_format")
        if isinstance(record_format, str) and record_format in {
            "numbered_paragraphs",
            "json_array_strings",
        }:
            source["record_format"] = record_format
        exact_overview = None
        if metadata.get("prometheus_vector_queries") is True:
            try:
                exact_overview = overview(text)
                source["prometheus_vector"] = True
            except (ValueError, TypeError, KeyError, RecursionError):
                pass
        handle = register(scope, refs, source)
        lossless = (
            repeated_projection(text) if config.tool_result_max_bytes >= 16000 else None
        )
        if (
            lossless
            and scope.lossless_projection_bytes
            and len(lossless["text"].encode())
            > scope.lossless_projection_bytes // sources
        ):
            lossless = None
        preview = (
            lossless["text"]
            if lossless
            else prepared_preview(
                scope, source, text, question, min(maximum, len(text.encode()) // 2)
            )
        )
        operations = "read, search" + (
            ", count_unique (exact full-data count)"
            if source.get("record_format")
            else ""
        )
        if exact_overview is not None:
            operations += ", count, tail, max, sum (complete vector)"
            preview += "\nEXACT_VECTOR_OVERVIEW=" + json.dumps(
                exact_overview, separators=(",", ":")
            )
        preview_limit = (
            (scope.lossless_projection_bytes or config.tool_result_max_bytes) // sources
            if lossless
            else min(maximum, len(text.encode()) // 2)
        )
        # Do not shorten evidence or downgrade a lossless representation
        # to make room for optional deterministic statistics.
        preview += _record_overview(text, source, preview_limit - len(preview.encode()))
        if scope.retrieval_calls >= config.max_retrieval_calls:
            guidance = (
                f"Source reference {handle!r}; retrieval budget exhausted for this invocation. "
                "Use retained evidence, or state that evidence is insufficient."
            )
        elif lossless:
            guidance = (
                f"Original reference {handle!r}. All text is represented above, "
                "with exact duplicates referring to their first occurrence. "
                "Answer using this complete representation; retrieve the original "
                "only if you need to verify a repeated range. "
                f"Available source operations: {operations}. "
                + (
                    "For exact whole-source counts, use the declared count_unique operation. "
                    if source.get("record_format")
                    else ""
                )
            )
        else:
            guidance = (
                f"Use {READ_CONTEXT_TOOL}(reference={handle!r}, operation='search', query='keywords') to locate evidence. "
                "Use operation='read' for exact case-sensitive text or a character offset. "
                f"Operations: {operations}. Verify omitted details in the original."
            )
        parent[field] = (
            preview
            + f"\n[{'Lossless projection' if lossless else 'Preview only'}; original text has {len(text)} characters. "
            + guidance
            + "]"
        )
        if not lossless:
            scope.lossy_references.add(handle)
    if compact_reads:
        compact_read_results(request.contents, scope, refs, config)
    if refs and attach_reader:
        _attach_reader(request, scope, config, refs)
    from .tool_lookup_preview import build_tool_lookup_previews

    scope.tool_lookup_previews = build_tool_lookup_previews(
        scope, request.contents, refs, config
    )
    return refs


def _find_original(scope, response, path, text):
    for event in reversed(scope.session.events):
        if (
            event.author != scope.agent_name
            or (getattr(event, "branch", None) or "") != scope.branch
        ):
            continue
        parts = (event.content.parts or []) if event.content else []
        for index, part in enumerate(parts):
            original = part.function_response
            if (
                original
                and original.name == response.name
                and original.id == response.id
                and isinstance(original.response, dict)
            ):
                candidate = original.response
                try:
                    for key in path:
                        candidate = candidate[key]
                except (TypeError, KeyError, IndexError):
                    continue
                if candidate != text:
                    continue
                return {
                    "event_id": event.id,
                    "part": index,
                    "path": list(path),
                    "tool": original.name,
                    "call_id": original.id,
                    "text_hash": hashlib.sha256(text.encode()).hexdigest(),
                }
    return None


def _attach_reader(request, scope, config, references):
    identity = (
        scope.session.app_name,
        scope.session.user_id,
        scope.session.id,
        scope.agent_name,
        scope.branch,
    )
    existing = request.tools_dict.get(READ_CONTEXT_TOOL)
    if existing is not None:
        if (
            not isinstance(existing, _ContextReader)
            or existing.context_identity != identity
        ):
            raise ContextBudgetError("reserved_retrieval_tool_conflict")
        retained_tools = []
        for tool_config in request.config.tools or []:
            if (
                isinstance(tool_config, types.Tool)
                and tool_config.function_declarations
            ):
                declarations = [
                    declaration
                    for declaration in tool_config.function_declarations
                    if declaration.name != READ_CONTEXT_TOOL
                ]
                if len(declarations) != len(tool_config.function_declarations):
                    tool_config = tool_config.model_copy(
                        deep=True, update={"function_declarations": declarations}
                    )
                    # ADK's LiteLLM adapter serializes only the first tool
                    # group. Removing its sole reader and appending a new
                    # group would silently hide the reader on the next turn.
                    # Drop only the function-only group emptied here; keep
                    # any other tool capability and every business function.
                    if not declarations and set(
                        tool_config.model_dump(exclude_none=True)
                    ) == {"function_declarations"}:
                        continue
            retained_tools.append(tool_config)
        request.config.tools = retained_tools

    async def veadk_read_context(
        reference: str,
        tool_context: ToolContext,
        offset: int = 0,
        query: str = "",
        operation: str = "read",
    ) -> dict:
        """Read Session originals. Observe remaining_calls; never infer omitted facts. count_unique requires declared records; count/tail/max/sum require declared vectors."""
        current = tool_context.session
        active = current_scope.get()
        if (
            active is None
            or (
                current.app_name,
                current.user_id,
                current.id,
                tool_context.agent_name,
                active.branch,
            )
            != identity
        ):
            return {"error": "context_reference_not_available"}
        if (
            isinstance(reference, str)
            and reference in active.restored_references
            and isinstance(operation, str)
            and operation in {"read", "search"}
        ):
            return {
                "reference": reference,
                "original_included": True,
                "complete": False,
                "guidance": "The entire original is already present in the source tool result. Use it to answer; do not request it again.",
            }
        if (
            active.retrieval_calls >= config.max_retrieval_calls
            or active.retrieval_input_exhausted
        ):
            return {
                "error": (
                    "context_retrieval_input_budget_exhausted"
                    if active.retrieval_input_exhausted
                    else "context_retrieval_budget_exhausted"
                ),
                "complete": False,
                "remaining_calls": 0,
                "guidance": (
                    "The reader budget is exhausted. Do not call it again. "
                    "Answer from retained evidence, or state that evidence is insufficient."
                ),
            }
        # Every authenticated invocation of this reader uses its call budget,
        # including invalid arguments. Otherwise rejected model tool calls can
        # consume the Runner limit while the reader stays advertised forever.
        active.retrieval_calls += 1
        reserve_parallel_exchanges(
            active, getattr(tool_context, "function_call_id", None)
        )
        # Some providers emit JSON integer arguments as decimal strings. Accept
        # this bounded, unambiguous representation only; never coerce floats,
        # bools, expressions, signs or arbitrarily long input.
        if isinstance(offset, str) and re.fullmatch(r"[0-9]{1,10}", offset):
            offset = int(offset)
        if (
            not isinstance(reference, str)
            or type(offset) is not int
            or not isinstance(query, str)
        ):
            return {
                "error": "context_reference_not_available",
                "complete": False,
                "remaining_calls": config.max_retrieval_calls - active.retrieval_calls,
            }
        source = references.get(reference)
        if (
            not isinstance(source, dict)
            or offset < 0
            or len(query) > 256
            or not isinstance(operation, str)
            or operation
            not in {"read", "search", "count_unique", "count", "tail", "max", "sum"}
        ):
            return {"error": "context_reference_not_available"}
        maximum = min(config.retrieval_max_bytes, active.retrieval_page_bytes)
        if operation == "read" and active.retrieval_read_bytes is not None:
            maximum = min(maximum, active.retrieval_read_bytes)
        if active.retrieval_headroom is not None and operation == "read":
            maximum = min(maximum, max(0, active.retrieval_headroom // 2))
            if maximum < 128:
                active.retrieval_input_exhausted = True
                return {
                    "error": "context_retrieval_input_budget_exhausted",
                    "complete": False,
                    "remaining_calls": 0,
                    "guidance": "No room for further evidence. Answer from retained evidence or state that it is insufficient.",
                }
        text = resolve(active, source)
        if text is not None:
            result: dict[str, Any]
            if operation == "count_unique":
                if offset or query:
                    return {"error": "unsupported_operation", "complete": False}
                try:
                    result = count_unique(text, source.get("record_format"))
                except (ValueError, TypeError, RecursionError):
                    return {"error": "unsupported_operation", "complete": False}
            elif operation in {"count", "tail", "max", "sum"}:
                if not source.get("prometheus_vector") or offset or query:
                    return {"error": "unsupported_operation", "complete": False}
                try:
                    result = statistic(text, operation)
                except (ValueError, TypeError, KeyError, RecursionError):
                    return {"error": "unsupported_operation", "complete": False}
            elif operation == "search":
                if not query or len(text.encode()) > 2_000_000:
                    return {"error": "invalid_search", "complete": False}
                retrieved = await search_original(active, source, text, query, maximum)
                # Retrieval awaits external work. The Session remains authoritative.
                if resolve(active, source) != text:
                    return {"error": "context_reference_expired"}
                result = (
                    search(text, query, maximum) if retrieved is None else retrieved
                )
            else:
                result = _read_page(text, offset, query, maximum)
            signature = (reference, operation, offset, query)
            repeated = signature in active.retrieval_seen
            active.retrieval_seen.add(signature)
            result.update(
                reference=reference,
                source_sha256=source["text_hash"],
                remaining_calls=config.max_retrieval_calls - active.retrieval_calls,
                repeated=repeated,
            )
            if repeated:
                result["guidance"] = (
                    "This range/query was already read. Use its evidence, change the query/offset, or answer; do not loop."
                )
            if active.retrieval_calls >= config.max_retrieval_calls:
                result["guidance"] = (
                    "Reader budget exhausted. Answer using retained evidence or state it is insufficient; "
                    "do not infer omitted facts."
                )
            if active.retrieval_headroom is not None and operation in {
                "read",
                "search",
            }:

                def search_charge(value):
                    credit, claimed = reuse_credit(
                        request.contents,
                        active,
                        value,
                        getattr(tool_context, "function_call_id", None),
                        config,
                        _original_reader_response,
                    )
                    return max(128, _reader_result_size(value) - credit), claimed

                fitted = (
                    _fit_search_result(result, active.retrieval_headroom, search_charge)
                    if operation == "search"
                    else _fit_reader_result(result, active.retrieval_headroom, query)
                )
                if fitted is None:
                    active.retrieval_input_exhausted = True
                    return {
                        "error": "context_retrieval_input_budget_exhausted",
                        "complete": False,
                        "remaining_calls": 0,
                        "guidance": "No room for further evidence. Answer from retained evidence or state that it is insufficient.",
                    }
                result = fitted
                # Share the allowance between calls in a parallel tool group.
                charge = _reader_result_size(result)
                if operation == "search":
                    charge, claimed = search_charge(result)
                    active.retrieval_reuse_claimed.update(claimed)
                active.retrieval_headroom = max(0, active.retrieval_headroom - charge)
            active.retrieval_results += 1
            return result
        return {"error": "context_reference_expired"}

    tool = _ContextReader(veadk_read_context, identity, references)
    if (
        scope.retrieval_calls >= config.max_retrieval_calls
        or scope.retrieval_input_exhausted
    ):
        # Keep a non-advertised handler for stale calls emitted by the model.
        # It returns a bounded refusal without resolving or reading any source.
        request.tools_dict[READ_CONTEXT_TOOL] = tool
    else:
        request.append_tools([tool])


def _read_page(text, offset, query, maximum):
    if offset > len(text):
        return {"error": "invalid_offset", "complete": False}
    if query:
        found = text.find(query, offset)
        if found < 0:
            return {
                "found": False,
                "total_characters": len(text),
                "complete": False,
                "guidance": (
                    "No exact case-sensitive match at or after this offset. "
                    "This does not establish that the source lacks relevant evidence. "
                    "Use operation='search' with keywords to locate it, or read a known character offset."
                ),
            }
        before = text[max(offset, found - 256) : found].encode()
        prefix_bytes = min(256, max(0, maximum - len(query.encode())))
        prefix = before[-prefix_bytes:].decode(errors="ignore") if prefix_bytes else ""
        offset = found - len(prefix)
    chunk = text[offset:].encode("utf-8")[:maximum].decode("utf-8", errors="ignore")
    end = offset + len(chunk)
    return {
        "text": chunk,
        "offset": offset,
        "end": end,
        "next_offset": end if end < len(text) else None,
        "total_characters": len(text),
        "complete": offset == 0 and end == len(text),
    }


def _reader_result_size(value):
    # Tool responses become JSON text nested in a provider JSON request.
    return (
        len(
            json.dumps(
                json.dumps(value, ensure_ascii=False), ensure_ascii=False
            ).encode()
        )
        + 128
    )


def _fit_reader_result(value, maximum, query):
    """Bound newly retrieved text before persistence, including JSON escaping."""
    if _reader_result_size(value) <= maximum:
        return value
    if not isinstance(value.get("text"), str) or not value["text"]:
        return None
    text = value["text"]
    start = value["offset"]
    # A short query result must include its match, not just preceding context.
    if query and query in text:
        prefix = text.index(query)
        text, start = text[prefix:], start + prefix

    def candidate(length):
        end = start + length
        return {
            **value,
            "text": text[:length],
            "offset": start,
            "end": end,
            "next_offset": end if end < value["total_characters"] else None,
            "complete": start == 0 and end == value["total_characters"],
        }

    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if _reader_result_size(candidate(middle)) <= maximum:
            low = middle
        else:
            high = middle - 1
    if not low or (query and query not in text[:low]):
        return None
    return candidate(low)


def _fit_search_result(value, maximum, charge):
    """Admit complete new search excerpts within the serialized allowance."""
    if charge(value)[0] <= maximum:
        return value
    retained = []
    for match in value.get("matches", []):
        candidate = {**value, "matches": [*retained, match]}
        if charge(candidate)[0] <= maximum:
            retained.append(match)
    if not retained:
        return None
    return {**value, "matches": retained, "complete": False}


def compact_read_results(contents, scope, references, config):
    """Keep retrieved evidence once per turn without changing Session events.

    Identical older search excerpts may refer to a full copy in the same user
    turn, including the newest response group (which remains unchanged).
    Turn-local references cannot outlive their target when history is removed.
    """
    if scope is None:
        return
    groups = []
    turn = 0
    for content in contents:
        if is_user_turn(content):
            turn += 1
        results = [
            p.function_response
            for p in content.parts or []
            if p.function_response and p.function_response.name == READ_CONTEXT_TOOL
        ]
        if results:
            groups.append((turn, results))
    if not groups:
        return
    identifiers = Counter(response.id for _, group in groups for response in group)
    alias_guidance = ALIAS_GUIDANCE

    def encoded_size(value):
        return len(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        )

    known_search_fields = SEARCH_FIELDS

    def verified(response):
        value = response.response
        source = (
            references.get(value.get("reference")) if isinstance(value, dict) else None
        )
        return (
            source
            and value.get("source_sha256") == source.get("text_hash")
            and _original_reader_response(scope, response)
            and not contains_protected(value, config.protected_context)
        )

    def match_key(turn, response, match):
        if (
            not isinstance(match, dict)
            or set(match) != {"offset", "end", "text"}
            or not isinstance(match["text"], str)
            or type(match["offset"]) is not int
            or type(match["end"]) is not int
            or match["offset"] < 0
            or match["end"] - match["offset"] != len(match["text"])
            or not response.id
            or identifiers[response.id] != 1
        ):
            return None
        value = response.response
        return (
            turn,
            value["reference"],
            value["source_sha256"],
            match["offset"],
            match["end"],
            match["text"],
        )

    # Pages are validated against Session and original source before any rewrite.
    compact_pages(
        contents, groups, scope, references, config, _original_reader_response
    )

    # The unchanged newest response can supply evidence for earlier duplicates.
    # Every alias points directly to full text, never to another alias.
    included = {}
    latest_turn, latest_group = groups[-1]
    for response in latest_group:
        if not verified(response):
            continue
        matches = response.response.get("matches")
        if not isinstance(matches, list):
            continue
        for match in matches:
            key = match_key(latest_turn, response, match)
            if key is not None:
                included[key] = response.id
    for turn, group in groups[:-1]:
        for response in group:
            if not verified(response):
                continue
            value = response.response
            if (
                isinstance(value.get("matches"), list)
                and set(value) <= known_search_fields
            ):
                retained = []
                has_alias = False
                for match in value["matches"]:
                    key = match_key(turn, response, match)
                    previous = included.get(key) if key is not None else None
                    alias = (
                        {
                            "offset": match["offset"],
                            "end": match["end"],
                            "included_in_response": previous,
                        }
                        if previous and previous != response.id
                        else None
                    )
                    if alias and encoded_size(alias) + len(
                        alias_guidance
                    ) < encoded_size(match):
                        retained.append(alias)
                        has_alias = True
                    else:
                        retained.append(match)
                        if key is not None:
                            included[key] = response.id
                # Prior quota, found and total-length metadata are redundant.
                # Unknown fields were excluded above; source evidence stays exact.
                compacted = {
                    "reference": value["reference"],
                    # This scoped handle already binds the source hash. Keep
                    # the hash in the original event and newest response; do
                    # not repeat it in each verified consumed response.
                    "matches": retained,
                    "complete": False,
                    "archived": True,
                }
                if has_alias:
                    compacted["guidance"] = alias_guidance
                if encoded_size(compacted) < encoded_size(value):
                    response.response = compacted
                else:
                    # Preserve the existing consumed-result protocol flag even
                    # when the evidence is too short to benefit from an alias.
                    value["archived"] = True
                    value["complete"] = False


def _original_reader_response(scope, response):
    return any(
        e.author == scope.agent_name
        and (e.branch or "") == scope.branch
        and any(p.function_response == response for p in e.content.parts or [])
        for e in scope.session.events
        if e.content
    )


def restore_fitting_originals(request, scope, config, available):
    """After repeated retrieval, prefer a fitting full source over more paging.

    Keep call envelopes and replace redundant reader copies only when that
    exact source is restored elsewhere in the same request.
    """
    if scope is None or scope.retrieval_calls < 2:
        return
    import copy

    from .budget import count_input, request_payload

    refs = saved_references(scope)
    candidate = request.model_copy(update={"contents": copy.deepcopy(request.contents)})
    used = {
        p.function_response.response.get("reference")
        for c in candidate.contents
        for p in c.parts or []
        if p.function_response
        and p.function_response.name == READ_CONTEXT_TOOL
        and isinstance(p.function_response.response, dict)
    }
    restored = set()
    for ref in used:
        source = refs.get(ref)
        if not source or source.get("kind") == "history":
            continue
        text = resolve(scope, source)
        if text is None:
            continue
        for content in candidate.contents:
            for part in content.parts or []:
                response = part.function_response
                if (
                    response
                    and response.name == source.get("tool")
                    and response.id == source.get("call_id")
                ):
                    try:
                        parent = response.response
                        for key in source["path"][:-1]:
                            parent = parent[key]
                        parent[source["path"][-1]] = text
                        restored.add(ref)
                    except (KeyError, IndexError, TypeError):
                        continue
    if not restored:
        return
    for content in candidate.contents:
        for part in content.parts or []:
            response = part.function_response
            if (
                response
                and response.name == READ_CONTEXT_TOOL
                and isinstance(response.response, dict)
                and response.response.get("reference") in restored
                and _original_reader_response(scope, response)
                and not any(
                    required in json.dumps(response.response, ensure_ascii=False)
                    for required in config.protected_context
                )
            ):
                value = response.response
                value.pop("matches", None)
                value["text"] = (
                    "The complete original is included in the preceding source tool result; use that text."
                )
                value["complete"] = False
                value["original_included"] = True
    # If every reference is now included, its reader is unnecessary in this
    # model request. Keep the local handler for a stale model tool call.
    if set(refs) <= restored and not any(
        source.get("record_format") or source.get("prometheus_vector")
        for source in refs.values()
    ):
        candidate.config = copy.deepcopy(request.config)
        for tool_config in candidate.config.tools or []:
            if (
                isinstance(tool_config, types.Tool)
                and tool_config.function_declarations
            ):
                tool_config.function_declarations = [
                    declaration
                    for declaration in tool_config.function_declarations
                    if declaration.name != READ_CONTEXT_TOOL
                ]
    if count_input(request_payload(candidate), config) <= available:
        request.contents = candidate.contents
        request.config = candidate.config
        scope.restored_references = restored
