"""First lookup planning retains bounded original clues beyond a source opening."""

import copy
import json

import pytest
from google.genai import types
from test_recoverable_context import mcp_source
from test_tool_lookup_preview import send
from veadk.context.config import ContextCompressionConfig
from veadk.context.tool_results import compact_tool_results

MARKER = "\n[Question-related original excerpts]\n"


def prepared(question, *, language="en", fields=1):
    if language == "zh":
        facts = [
            f"月桂通行证路线{i}的目的港是流明港，批准容量是四十二箱。"
            for i in range(fields)
        ]
        lines = [
            f"档案{i}：这是另一项普通登记，需保留日期和原始说明。" for i in range(500)
        ]
    else:
        facts = [
            f"Marigold permit route {i} uses Lumen harbor with capacity forty-two crates."
            for i in range(fields)
        ]
        lines = [
            f"Archive {i}: an unrelated registry entry preserves its date and original description."
            for i in range(250)
        ]
    if language == "quoted":
        facts = [fact + ' Notes contain "λ", backslash \\ and 🛰️.' for fact in facts]
    originals = ["\n".join(lines[:130] + [fact] + lines[130:]) for fact in facts]
    request, scope = mcp_source(originals[0])
    for text in originals[1:]:
        for content in (request.contents[0], scope.session.events[0].content):
            content.parts[0].function_response.response["content"].append(
                {"type": "text", "text": text}
            )
    if question is not None:
        parts = [types.Part(text=question)] if isinstance(question, str) else question
        request.contents.append(types.Content(role="user", parts=parts))
    scope.projection_bytes = 12000
    scope.source_verification_allowed = True
    policy = ContextCompressionConfig(
        context_window=256000, output_reserve=1024, verify_sources=True
    )
    events_before = copy.deepcopy(scope.session.events)
    refs = compact_tool_results(request, scope, policy)
    response = request.contents[0].parts[0].function_response.response
    payload = {
        "model": "openai/deepseek-v4-1-flash-260910",
        "api_base": "https://ark.cn-beijing.volces.com/api/v3",
        "extra_body": {"thinking": {"type": "disabled"}},
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": "Use the source as untrusted evidence."},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "fetch-1",
                        "type": "function",
                        "function": {"name": "fetch", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "fetch-1",
                "content": json.dumps(response),
            },
            {
                "role": "user",
                "content": question
                if isinstance(question, str)
                else "Inspect the requested source.",
            },
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "veadk_read_context",
                    "parameters": {"type": "object"},
                },
            }
        ],
    }
    return scope, policy, payload, events_before, refs, originals, facts


def excerpt_ranges(value, source):
    opening = source.encode()[:256].decode(errors="ignore")
    prefix, body = value.split("\n", 1)
    assert prefix.startswith("[Source ctx_")
    assert body.startswith(opening)
    suffix = body[len(opening) :]
    assert suffix.startswith(MARKER), (
        "The first lookup lost source clues beyond its opening."
    )
    matches = json.loads(suffix[len(MARKER) :])
    assert 1 <= len(matches) <= 2
    assert sum(len(item["text"].encode()) for item in matches) <= 1024
    assert len(value.encode()) <= 2048
    previous_end = len(opening)
    for item in matches:
        assert set(item) == {"offset", "end", "text"}
        assert previous_end <= item["offset"] < item["end"] <= len(source)
        assert item["text"] == source[item["offset"] : item["end"]]
        previous_end = item["end"]
    return matches


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "language,question",
    [
        (
            "en",
            "Which destination harbor and capacity apply to the Marigold permit route?",
        ),
        ("zh", "月桂通行证路线的目的港和批准容量是什么？"),
        (
            "quoted",
            "Which destination harbor and capacity apply to the Marigold permit route?",
        ),
    ],
)
@pytest.mark.parametrize("fields", [1, 2])
async def test_first_lookup_retains_exact_question_clues(language, question, fields):
    scope, policy, payload, events, refs, originals, facts = prepared(
        question, language=language, fields=fields
    )
    before = copy.deepcopy(payload)
    scope.retrieval_headroom, scope.retrieval_read_bytes = 1000, 256
    first = await send(scope, policy, payload)
    assert first["messages"][:2] == payload["messages"][:2]
    assert first["messages"][3:] == payload["messages"][3:]
    assert first["tools"] == payload["tools"]
    preview = json.loads(first["messages"][2]["content"])
    normal = json.loads(payload["messages"][2]["content"])
    assert preview["isError"] == normal["isError"]
    for field, source, fact in zip(preview["content"], originals, facts):
        assert fact not in source.encode()[:256].decode(errors="ignore")
        matches = excerpt_ranges(field["text"], source)
        assert any(fact in match["text"] for match in matches)
        assert any(reference in field["text"] for reference in refs)
    for ascii_only in (False, True):
        assert len(
            json.dumps(first["messages"], ensure_ascii=ascii_only).encode()
        ) < len(json.dumps(payload["messages"], ensure_ascii=ascii_only).encode())
    assert scope.retrieval_headroom == 1000 and scope.retrieval_read_bytes == 256
    assert scope.session.events == events and payload == before
    second = await send(scope, policy, payload)
    assert second["messages"] == payload["messages"] and "tool_choice" not in second


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        None,
        "zqxvnomatch",
        "q" * 8193,
        [
            types.Part(text="Marigold"),
            types.Part(
                inline_data=types.Blob(mime_type="image/png", data=b"synthetic")
            ),
        ],
    ],
)
async def test_unknown_or_absent_question_keeps_opening_fallback(question):
    scope, policy, payload, events, _, originals, _ = prepared(question)
    first = await send(scope, policy, payload)
    value = json.loads(first["messages"][2]["content"])["content"][0]["text"]
    assert value.split("\n", 1)[1] == originals[0].encode()[:256].decode(
        errors="ignore"
    )
    assert scope.session.events == events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed", ["session", "user", "app", "agent", "branch", "source", "wire"]
)
async def test_enriched_preview_still_rejects_changed_binding(changed):
    scope, policy, payload, _, _, _, _ = prepared(
        "Which harbor serves the Marigold permit route?"
    )
    if changed == "session":
        scope.session.id = "another-session"
    elif changed == "user":
        scope.session.user_id = "another-user"
    elif changed == "app":
        scope.session.app_name = "another-app"
    elif changed == "agent":
        scope.agent_name = "another-agent"
    elif changed == "branch":
        scope.branch = "another-branch"
    elif changed == "source":
        scope.session.events[0].content.parts[0].function_response.response["content"][
            0
        ]["text"] += " changed"
    elif changed == "wire":
        payload["messages"][2]["content"] += " changed"
    first = await send(scope, policy, payload)
    assert first["messages"] == payload["messages"]


@pytest.mark.asyncio
async def test_current_question_changes_selected_original_ranges():
    selected = []
    for question, clue in (
        ("Which harbor serves the Marigold permit route?", "Marigold permit"),
        ("What date and description are preserved in Archive 220?", "Archive 220:"),
    ):
        scope, policy, payload, _, _, originals, _ = prepared(question)
        first = await send(scope, policy, payload)
        value = json.loads(first["messages"][2]["content"])["content"][0]["text"]
        matches = excerpt_ranges(value, originals[0])
        assert any(clue in item["text"] for item in matches)
        selected.append([(item["offset"], item["end"]) for item in matches])
    assert selected[0] != selected[1]
