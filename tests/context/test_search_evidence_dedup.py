"""Repeated exact retrieved evidence must not exhaust the model-input budget."""

import copy

from google.adk.events import Event
from google.genai import types
from test_evidence_quality import fixture

from veadk.context.budget import count_input, request_payload
from veadk.context.config import ContextCompressionConfig
from veadk.context.tool_results import (
    READ_CONTEXT_TOOL,
    compact_read_results,
    compact_tool_results,
)


def scenario():
    text = "".join(
        f"Archival item {i}: approval pending; amount {i}.\n" for i in range(500)
    )
    request, scope = fixture(text, "Verify the approvals and exact amounts.")
    config = ContextCompressionConfig()
    refs = compact_tool_results(request, scope, config)
    ref = next(iter(refs))
    request.contents = [
        types.Content(
            role="user", parts=[types.Part(text="Recent task constraints. " * 350)]
        )
    ]
    ranges = [
        [(100, 1800), (4000, 5600)],
        [(5600, 7300), (12000, 13700)],
        [(100, 1800), (4000, 5600)],
        [(5600, 7300), (13700, 15400)],
        [(9000, 10700), (13700, 15400)],
    ]
    for i, segments in enumerate(ranges):
        result = {
            "reference": ref,
            "source_sha256": refs[ref]["text_hash"],
            "matches": [
                {"offset": a, "end": b, "text": text[a:b]} for a, b in segments
            ],
            "complete": False,
        }
        event = Event(
            id=f"search-{i}",
            author="agent",
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=f"read-{i}", name=READ_CONTEXT_TOOL, response=result
                        ),
                    )
                ],
            ),
        )
        scope.session.events.append(event)
        request.contents.append(copy.deepcopy(event.content))
    return request, scope, refs, config


def test_duplicate_searches_fit_budget_without_losing_any_retrieved_evidence():
    request, scope, refs, config = scenario()
    originals = copy.deepcopy(scope.session.events)
    before = count_input(request_payload(request), config)
    budget = before - 4000
    newest = copy.deepcopy(request.contents[-1])
    compact_read_results(request.contents, scope, refs, config)
    assert count_input(request_payload(request), config) <= budget
    included = {
        (response.id, match["offset"], match["end"]): match["text"]
        for content in request.contents[1:]
        for response in [content.parts[0].function_response]
        for match in response.response["matches"]
        if "text" in match
    }
    alias_count = 0
    for content in request.contents[1:]:
        response = content.parts[0].function_response
        for match in response.response["matches"]:
            key = (response.id, match["offset"], match["end"])
            if "included_in_response" in match:
                source_key = (
                    match["included_in_response"],
                    match["offset"],
                    match["end"],
                )
                assert source_key in included
                alias_count += 1
                included[key] = included[source_key]
            else:
                included[key] = match["text"]
    assert alias_count >= 4
    for event in originals[1:]:
        response = event.content.parts[0].function_response
        for match in response.response["matches"]:
            assert (
                included[(response.id, match["offset"], match["end"])] == match["text"]
            )
    assert request.contents[-1] == newest
    assert scope.session.events == originals


def test_equal_ranges_with_different_text_are_never_aliased():
    request, scope, refs, config = scenario()
    changed = (
        scope.session.events[3]
        .content.parts[0]
        .function_response.response["matches"][0]
    )
    changed["text"] = "Z" * (changed["end"] - changed["offset"])
    request.contents[3] = copy.deepcopy(scope.session.events[3].content)
    compact_read_results(request.contents, scope, refs, config)
    match = request.contents[3].parts[0].function_response.response["matches"][0]
    assert match["text"] == changed["text"] and "included_in_response" not in match


def test_identical_text_from_different_references_is_not_aliased():
    request, scope, refs, config = scenario()
    original_ref = next(iter(refs))
    other_ref = "other-source-reference"
    refs[other_ref] = dict(refs[original_ref])
    value = scope.session.events[3].content.parts[0].function_response.response
    value["reference"] = other_ref
    request.contents[3] = copy.deepcopy(scope.session.events[3].content)
    before = copy.deepcopy(value["matches"])
    compact_read_results(request.contents, scope, refs, config)
    assert request.contents[3].parts[0].function_response.response["matches"] == before


def test_ambiguous_response_ids_cannot_become_alias_targets():
    request, scope, refs, config = scenario()
    for index in (1, 3):
        scope.session.events[index].content.parts[0].function_response.id = "same-id"
        request.contents[index] = copy.deepcopy(scope.session.events[index].content)
    originals = copy.deepcopy(scope.session.events)
    compact_read_results(request.contents, scope, refs, config)
    for index in (1, 3):
        assert (
            request.contents[index].parts[0].function_response.response["matches"]
            == (originals[index].content.parts[0].function_response.response["matches"])
        )


def test_latest_response_can_supply_exact_evidence_to_older_copies():
    request, scope, refs, config = scenario()
    newest = copy.deepcopy(request.contents[-1])
    compact_read_results(request.contents, scope, refs, config)
    earlier = request.contents[-2].parts[0].function_response.response
    repeated = earlier["matches"][-1]
    assert repeated.get("included_in_response") == newest.parts[0].function_response.id
    assert "text" not in repeated
    assert request.contents[-1] == newest
    # Only current quota and completeness metadata live in the unchanged latest
    # response; original metadata remains in the Session event.
    assert set(earlier) <= {
        "reference",
        "source_sha256",
        "matches",
        "archived",
        "complete",
        "guidance",
    }


def test_alias_never_crosses_a_user_turn_that_history_summary_can_remove():
    request, scope, refs, config = scenario()
    request.contents.insert(
        3,
        types.Content(role="user", parts=[types.Part(text="New task: verify again.")]),
    )
    compact_read_results(request.contents, scope, refs, config)
    new_turn_first = request.contents[4].parts[0].function_response.response
    assert all("text" in match for match in new_turn_first["matches"])
    old_turn_second = request.contents[2].parts[0].function_response.response
    assert all("text" in match for match in old_turn_second["matches"])


def test_unknown_reader_response_fields_are_preserved_without_compaction():
    request, scope, refs, config = scenario()
    value = scope.session.events[3].content.parts[0].function_response.response
    value["new_protocol_evidence"] = "Approval is pending, not complete."
    request.contents[3] = copy.deepcopy(scope.session.events[3].content)
    compact_read_results(request.contents, scope, refs, config)
    assert request.contents[3].parts[0].function_response.response == value


def test_mismatched_source_hash_is_never_compacted_or_used_as_evidence():
    request, scope, refs, config = scenario()
    value = scope.session.events[3].content.parts[0].function_response.response
    value["source_sha256"] = "0" * 64
    request.contents[3] = copy.deepcopy(scope.session.events[3].content)
    latest = copy.deepcopy(request.contents[-1])
    originals = copy.deepcopy(scope.session.events)
    compact_read_results(request.contents, scope, refs, config)
    assert request.contents[3].parts[0].function_response.response == value
    assert request.contents[-1] == latest and scope.session.events == originals
