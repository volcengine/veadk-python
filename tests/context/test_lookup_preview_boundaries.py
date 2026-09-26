"""Origin, caller ownership, retry and wire-format boundaries of lookup previews."""

import asyncio
import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions import Session
from google.genai import types
from veadk.context.client import BudgetedLiteLLMClient
from veadk.context.config import ContextCompressionConfig
from veadk.context.manager import prepare_context
from veadk.context.references import archive_history, state_key
from veadk.context.runtime import ContextScope, current_scope
from veadk.context.verification_preview import (
    apply_lookup_previews,
    build_lookup_previews,
)


@pytest.fixture
def prepared():
    policy = ContextCompressionConfig(
        context_window=32000, output_reserve=1024, verify_sources=True
    )
    original = [
        types.Content(role="user", parts=[types.Part(text='档案 "evidence"\n' * 240)]),
        types.Content(role="model", parts=[types.Part(text="Saved.")]),
        types.Content(role="user", parts=[types.Part(text="Current question?")]),
    ]
    scope = ContextScope(
        session=Session(id="s", app_name="a", user_id="u"),
        agent_name="agent",
        branch="",
        source_verification_allowed=True,
    )
    scope.session.events = [
        Event(
            id=f"event-{i}", author="user" if c.role == "user" else "agent", content=c
        )
        for i, c in enumerate(original)
    ]
    projected = copy.deepcopy(original)
    projected[0].parts[0].text = "[User excerpts]\n" + original[0].parts[0].text[:1300]
    refs = {}
    reference = archive_history(scope, original[:2], refs)
    scope.pending_state[state_key(scope)] = refs
    scope.lossy_references.add(reference)
    scope.lookup_previews = build_lookup_previews(
        scope,
        original,
        projected,
        2,
        reference,
        refs,
        policy,
    )
    assert len(scope.lookup_previews) == 1
    payload = {
        "model": "openai/deepseek-v4-1-flash-260910",
        "api_base": "https://ark.cn-beijing.volces.com/api/v3",
        "extra_body": {"thinking": {"type": "disabled"}},
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": "Check the source."},
            {"role": "user", "content": projected[0].parts[0].text},
            {"role": "assistant", "content": "Saved."},
            {"role": "user", "content": "Current question?"},
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
    token = current_scope.set(scope)
    yield scope, original, projected, refs, reference, policy, payload
    current_scope.reset(token)


@pytest.mark.parametrize("shape", ["string", "text_part"])
def test_preview_is_verbatim_bounded_and_input_immutable(prepared, shape):
    scope, original, _, _, reference, _, payload = prepared
    if shape == "text_part":
        payload["messages"][1]["content"] = [
            {
                "type": "text",
                "text": payload["messages"][1]["content"],
            }
        ]
    before = copy.deepcopy(payload)
    result = apply_lookup_previews(payload)
    assert result != before and payload == before
    assert result["messages"][:1] == before["messages"][:1]
    assert result["messages"][2:] == before["messages"][2:]
    preview = scope.lookup_previews[0].preview
    opening = preview.split("\n", 1)[1]
    assert len(opening.encode()) <= 256
    assert original[0].parts[0].text.startswith(opening)
    assert reference in preview and "history record 0, part 0" in preview


@pytest.mark.parametrize(
    "case",
    [
        "unarchived",
        "tampered_source",
        "tampered_history",
        "protected",
        "short",
        "assistant",
        "unchanged",
        "multipart",
        "default",
        "attempted",
        "already_read",
    ],
)
def test_only_verified_projected_long_user_text_can_create_preview(prepared, case):
    scope, original, projected, refs, reference, policy, _ = prepared
    if case == "unarchived":
        reference = "ctx_" + "a" * 24
    elif case == "tampered_source":
        refs[reference]["text_hash"] = "invalid"
    elif case == "tampered_history":
        original = copy.deepcopy(original)
        original[0].parts[0].text += "different"
    elif case == "protected":
        policy = policy.model_copy(update={"protected_context": ("evidence",)})
    elif case in {"short", "assistant", "multipart"}:
        if case == "short":
            original[0].parts[0].text = "short"
        elif case == "assistant":
            original[0].role = projected[0].role = "model"
            scope.session.events[0].author = "agent"
        else:
            original[0].parts.append(types.Part(text="second part"))
        reference = archive_history(scope, original[:2], refs)
    elif case == "unchanged":
        projected = copy.deepcopy(original)
    elif case == "default":
        policy = policy.model_copy(update={"verify_sources": False})
    elif case == "attempted":
        scope.source_verification_attempted = True
    elif case == "already_read":
        scope.retrieval_calls = 1
    assert not build_lookup_previews(
        scope, original, projected, 2, reference, refs, policy
    )


@pytest.mark.parametrize(
    "case",
    [
        "duplicate_user",
        "duplicate_system",
        "same_current",
        "last_user",
        "multimodal",
        "unknown_part",
        "multipart",
        "tool_protocol",
        "missing_ref",
        "other_session",
        "other_agent",
        "duplicate_binding",
        "larger",
        "changed_text",
        "no_scope",
    ],
)
def test_ambiguous_or_unknown_wire_content_is_not_shortened(prepared, case):
    scope, _, _, _, _, _, payload = prepared
    text = payload["messages"][1]["content"]
    if case.startswith("duplicate_") and case != "duplicate_binding":
        payload["messages"].insert(1, {"role": case.split("_")[1], "content": text})
    elif case == "same_current":
        payload["messages"][-1]["content"] = text
    elif case == "last_user":
        payload["messages"] = payload["messages"][:2]
    elif case in {"multimodal", "unknown_part", "multipart"}:
        payload["messages"][1]["content"] = [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": "fake"},
        ]
        if case == "unknown_part":
            payload["messages"][1]["content"] = [
                {"type": "text", "text": text, "unknown": True}
            ]
        elif case == "multipart":
            payload["messages"][1]["content"][1] = {"type": "text", "text": "extra"}
    elif case == "tool_protocol":
        payload["messages"][1]["tool_call_id"] = "call-1"
    elif case == "missing_ref":
        scope.pending_state.clear()
    elif case == "other_session":
        scope.session.id = "other"
    elif case == "other_agent":
        scope.agent_name = "other"
    elif case == "duplicate_binding":
        scope.lookup_previews *= 2
    elif case == "larger":
        scope.lookup_previews = (replace(scope.lookup_previews[0], preview=text * 2),)
    elif case == "changed_text":
        payload["messages"][1]["content"] += " changed"
    elif case == "no_scope":
        current_scope.set(None)
    before = copy.deepcopy(payload)
    assert apply_lookup_previews(payload) == before and payload == before


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exception", "cancel", "fallback"])
async def test_failed_transport_restores_normal_context_on_next_attempt(
    prepared, failure
):
    scope, _, _, _, _, policy, payload = prepared
    calls = []

    class Delegate:
        async def acompletion(self, **kwargs):
            calls.append(copy.deepcopy(kwargs))
            if len(calls) == 1:
                if failure == "cancel":
                    raise asyncio.CancelledError()
                raise RuntimeError("synthetic failure")
            return "done"

    client = BudgetedLiteLLMClient(Delegate(), policy)
    before = copy.deepcopy(payload)
    if failure == "fallback":
        await client.acompletion(
            **payload,
            fallbacks=[
                {
                    "model": payload["model"],
                    "context_compression": {"context_window": 32000},
                }
            ],
        )
    else:
        with pytest.raises(
            asyncio.CancelledError if failure == "cancel" else RuntimeError
        ):
            await client.acompletion(**payload)
        await client.acompletion(**payload)
    assert len(calls) == 2 and scope.source_verification_attempted
    assert calls[0]["messages"] != before["messages"]
    assert calls[1]["messages"] == before["messages"]
    assert "tool_choice" not in calls[1]
    assert payload == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setting", ["tool_choice", "response_format", "stream", "default"]
)
async def test_ineligible_client_call_keeps_normal_context(prepared, setting):
    _, _, _, _, _, policy, payload = prepared
    if setting == "default":
        policy = policy.model_copy(update={"verify_sources": False})
    else:
        payload[setting] = {
            "tool_choice": "auto",
            "response_format": {"type": "json_object"},
            "stream": True,
        }[setting]
    calls = []

    class Delegate:
        async def acompletion(self, **kwargs):
            calls.append(kwargs)
            return "done"

    await BudgetedLiteLLMClient(Delegate(), policy).acompletion(**payload)
    assert calls[0]["messages"] == payload["messages"]


@pytest.mark.asyncio
async def test_preparation_clears_preview_before_early_return(prepared):
    scope, _, _, _, _, policy, _ = prepared
    request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="New question")])]
    )
    await prepare_context(
        request, SimpleNamespace(model="openai/deepseek-v4-1-flash-260910"), policy, {}
    )
    assert not scope.lookup_previews
