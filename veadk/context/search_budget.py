"""Conservative credit for exact search copies already visible in this turn."""

import json
from collections import Counter

from .history import is_user_turn

SEARCH_FIELDS = {
    "found",
    "matches",
    "complete",
    "total_characters",
    "reference",
    "source_sha256",
    "remaining_calls",
    "repeated",
    "guidance",
}
ALIAS_GUIDANCE = "included_in_response identifies an exact copy in this input."


def contains_protected(value, protected):
    encoded = json.dumps(value, ensure_ascii=False)
    return any(
        json.dumps(text, ensure_ascii=False)[1:-1] in encoded for text in protected
    )


def reserve_parallel_exchanges(scope, call_id):
    """Reserve argument and refusal envelopes for an already emitted tool batch.

    The manager reserves one exchange. Extra calls in the same model message
    need their own space even if no further source evidence can be returned.
    This inspects only the current agent's latest persisted call event.
    """
    if (
        scope.retrieval_batch_reserved
        or scope.retrieval_headroom is None
        or not call_id
    ):
        return
    for event in reversed(scope.session.events):
        if (
            event.author != scope.agent_name
            or (event.branch or "") != scope.branch
            or not event.content
        ):
            continue
        calls = [p.function_call for p in event.content.parts or [] if p.function_call]
        if not calls:
            continue
        if not any(
            call.id == call_id and call.name == "veadk_read_context" for call in calls
        ):
            return
        scope.retrieval_batch_reserved = True
        additional = [
            call
            for call in calls
            if call.name == "veadk_read_context" and call.id != call_id
        ]
        reserve = sum(
            len(
                json.dumps(
                    call.model_dump(exclude_none=True), ensure_ascii=False
                ).encode()
            )
            + 512
            for call in additional
        )
        scope.retrieval_headroom = max(0, scope.retrieval_headroom - reserve)
        return


def _match_key(match):
    if (
        not isinstance(match, dict)
        or set(match) != {"offset", "end", "text"}
        or not isinstance(match["text"], str)
        or type(match["offset"]) is not int
        or type(match["end"]) is not int
        or match["offset"] < 0
        or match["end"] - match["offset"] != len(match["text"])
    ):
        return None
    return match["offset"], match["end"], match["text"]


def reuse_credit(contents, scope, value, call_id, config, original_response):
    """Credit only a verified literal copy that the existing compactor can alias.

    Already rewritten responses, other turns, protected text, unknown fields,
    and ambiguous IDs receive no credit. Each source response can be credited
    once per model step, so concurrent calls cannot spend its saving twice.
    """
    if not isinstance(call_id, str) or not call_id:
        return 0, set()
    all_responses, current = [], []
    for content in contents:
        if is_user_turn(content):
            current = []
        for part in content.parts or []:
            response = part.function_response
            if response and response.name == "veadk_read_context":
                all_responses.append(response)
                current.append(response)
    counts = Counter(response.id for response in all_responses)
    if counts[call_id]:
        return 0, set()
    keys = {_match_key(m) for m in value.get("matches", [])} - {None}
    claimed, credit = set(), 0
    for response in current:
        old = response.response
        if (
            not response.id
            or counts[response.id] != 1
            or response.id in scope.retrieval_reuse_claimed
            or not isinstance(old, dict)
            or not set(old) <= SEARCH_FIELDS
            or old.get("reference") != value.get("reference")
            or old.get("source_sha256") != value.get("source_sha256")
            or not isinstance(old.get("matches"), list)
            or not original_response(scope, response)
            or contains_protected(old, config.protected_context)
        ):
            continue
        matches, replaced = [], False
        for match in old["matches"]:
            alias = (
                {
                    "offset": match["offset"],
                    "end": match["end"],
                    "included_in_response": call_id,
                }
                if _match_key(match) in keys
                else None
            )
            if alias and _compact_size(alias) + len(ALIAS_GUIDANCE) < _compact_size(
                match
            ):
                matches.append(alias)
                replaced = True
            else:
                matches.append(match)
        if not replaced:
            continue
        projected = {
            "reference": old["reference"],
            "matches": matches,
            "complete": False,
            "archived": True,
            "guidance": ALIAS_GUIDANCE,
        }
        if _compact_size(projected) >= _compact_size(old):
            continue
        # Take the smaller saving across native JSON and provider-nested JSON.
        saving = min(
            _compact_size(old) - _compact_size(projected),
            _nested_size(old) - _nested_size(projected),
        )
        if saving > 0:
            credit += saving
            claimed.add(response.id)
    return credit, claimed


def _compact_size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def _nested_size(value):
    return len(
        json.dumps(json.dumps(value, ensure_ascii=False), ensure_ascii=False).encode()
    )


def tool_serialization_overhead(contents):
    """Reserve the extra JSON string layer used for tool args/results on wire.

    Native ADK structures count each value once. OpenAI-compatible adapters
    stringify tool values, so escaping already retained evidence costs more on
    each subsequent request. This reserve only lowers new retrieval allowance;
    the final adapter still validates the complete serialized request.
    """
    overhead = 0
    for content in contents:
        for part in content.parts or []:
            values = []
            if part.function_call:
                values.append(part.function_call.args)
            if part.function_response and not isinstance(
                part.function_response.response, str
            ):
                values.append(part.function_response.response)
            for value in values:
                try:
                    overhead += max(0, _nested_size(value) - _compact_size(value))
                except (TypeError, ValueError, OverflowError, RecursionError):
                    # ADK serializes other valid tool values as str(value).
                    # Reserve that entire string rather than underestimate the
                    # delta or introduce a new failure for existing tools.
                    overhead += len(json.dumps(str(value), ensure_ascii=False).encode())
    return overhead
