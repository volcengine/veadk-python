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

"""Contract tests against the *real* ``openai-codex`` SDK types.

``translate.py`` dispatches on ``type(payload).__name__`` and ``_tool_call``
dispatches on a thread item's ``type`` string. Both are string-matched surfaces
against a third-party package, and the rest of the Codex tests hand-roll
same-named fakes -- so an SDK rename or a new notification type is invisible to
every one of them. These tests are the only place the real types are touched.

They require the ``openai-codex`` extra and therefore **skip on a developer
machine that has not installed it**; CI runs ``uv sync --all-extras``
(``.github/workflows/unit-tests.yaml``) so they execute there. See
``tests/runtime/codex/README.md``.
"""

from __future__ import annotations

import importlib.metadata
import typing

import pytest

pytest.importorskip("openai_codex")

from pydantic import BaseModel, ValidationError  # noqa: E402

from veadk.runtime.codex import translate  # noqa: E402

#: Pin from ``pyproject.toml``. Both string-matched surfaces below are only
#: meaningful against a known SDK version.
EXPECTED_SDK_VERSION = "0.1.0b3"


def _turn_notification_names() -> set[str]:
    """Every notification the SDK can deliver on a *turn* stream.

    Deliberately not "every class ending in ``Notification``": the SDK exports
    ~70, most of them thread- or account-scoped and never seen by a turn. The
    registry is the SDK's own answer to "what can arrive here".
    """
    from openai_codex.generated import notification_registry

    types_ = list(notification_registry.DIRECT_TURN_ID_NOTIFICATION_TYPES) + list(
        notification_registry.NESTED_TURN_NOTIFICATION_TYPES
    )
    return {t.__name__ for t in types_}


def test_dispatch_table_covers_every_sdk_notification() -> None:
    """Both directions: an unknown SDK type *and* a stale local entry must fail."""
    sdk_names = _turn_notification_names()
    local_names = set(translate._DISPATCH) | translate._EXPLICITLY_IGNORED

    unhandled = sdk_names - local_names
    stale = local_names - sdk_names

    assert not unhandled, (
        "openai-codex can deliver notifications this runtime neither handles "
        f"nor explicitly ignores: {sorted(unhandled)}. Add a handler to "
        "translate._DISPATCH, or record the decision in "
        "translate._EXPLICITLY_IGNORED."
    )
    assert not stale, (
        "translate.py names notifications the SDK no longer delivers on a turn "
        f"stream: {sorted(stale)}. They are dead dispatch entries -- the SDK "
        "renamed or removed them, so the real payloads now fall through."
    )
    assert not (
        set(translate._DISPATCH) & translate._EXPLICITLY_IGNORED
    ), "a notification is both handled and explicitly ignored"


def test_sdk_pin_matches_pyproject() -> None:
    """Both dispatch surfaces are string matches against one pinned version."""
    assert importlib.metadata.version("openai-codex") == EXPECTED_SDK_VERSION


def _model_by_name(name: str) -> type[BaseModel]:
    from openai_codex.generated import v2_all

    model = getattr(v2_all, name, None)
    assert model is not None, f"openai_codex.generated.v2_all has no {name}"
    return model


def _validate(name: str, payload: dict) -> BaseModel:
    """Real pydantic construction, with an actionable failure message."""
    model = _model_by_name(name)
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        required = sorted(
            field for field, info in model.model_fields.items() if info.is_required()
        )
        pytest.fail(
            f"{name}.model_validate rejected the payload this suite assumes.\n"
            f"required fields: {required}\n{error}"
        )


#: Minimal real payloads for the notifications ``translate.py`` reads fields
#: from. These are constructed with ``model_validate`` (never
#: ``model_construct``) so a schema drift fails here rather than silently
#: changing what the runtime observes.
_NOTIFICATION_PAYLOADS: dict[str, dict] = {
    "TurnStartedNotification": {"turn": {"id": "turn-1", "status": "inProgress"}},
    "TurnCompletedNotification": {"turn": {"id": "turn-1", "status": "completed"}},
    "AgentMessageDeltaNotification": {
        "turn_id": "turn-1",
        "item_id": "item-1",
        "delta": "hello",
    },
    "ReasoningSummaryTextDeltaNotification": {
        "turn_id": "turn-1",
        "item_id": "item-1",
        "summary_index": 0,
        "delta": "thinking",
    },
    "ThreadTokenUsageUpdatedNotification": {
        "turn_id": "turn-1",
        "model_context_window": 128000,
        "token_usage": {
            "last": {
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "output_tokens": 4,
                "reasoning_output_tokens": 0,
                "total_tokens": 14,
            },
            "total": {
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "output_tokens": 4,
                "reasoning_output_tokens": 0,
                "total_tokens": 14,
            },
        },
    },
}


@pytest.mark.parametrize("name", sorted(_NOTIFICATION_PAYLOADS))
def test_notification_to_events_accepts_real_sdk_instances(name: str) -> None:
    """A real SDK instance must reach a handler and translate cleanly.

    Every other Codex test builds a same-named fake with a hand-written
    ``model_dump``. If the SDK's real ``model_dump`` nests or renames a field
    the handler reads, only this test notices.
    """
    assert name in translate._DISPATCH, f"{name} is no longer dispatched"

    payload = _validate(name, _NOTIFICATION_PAYLOADS[name])
    events = translate.notification_to_events(payload, "agent", "inv")

    assert events, f"{name} produced no observable event"
    for event in events:
        assert event.author == "agent"
        assert event.invocation_id == "inv"
        assert (event.custom_metadata or {}).get("codex_event_type")


def test_turn_completed_payload_exposes_turn_id() -> None:
    """``runtime.py`` reads ``payload.turn.id`` directly, not through a dump."""
    payload = _validate(
        "TurnCompletedNotification", _NOTIFICATION_PAYLOADS["TurnCompletedNotification"]
    )

    assert payload.turn.id == "turn-1"
    event = translate.notification_to_events(payload, "agent", "inv")[0]
    assert event.custom_metadata["turn_id"] == "turn-1"


# ------------------------------------------------ thread item discriminators


def _item_model_for(discriminator: str) -> type[BaseModel]:
    """Find the SDK model whose ``type`` literal is ``discriminator``.

    Looked up by discriminator rather than by class name so an SDK *rename*
    still resolves; a removed or renamed *discriminator* -- which is what
    ``_tool_call`` actually matches on -- fails loudly.
    """
    from openai_codex.generated import v2_all

    matches: list[type[BaseModel]] = []
    for name in dir(v2_all):
        candidate = getattr(v2_all, name)
        if not isinstance(candidate, type) or not issubclass(candidate, BaseModel):
            continue
        field = candidate.model_fields.get("type")
        if field is None:
            continue
        literals = typing.get_args(field.annotation)
        if discriminator in literals or field.default == discriminator:
            matches.append(candidate)
    assert matches, (
        f"no openai-codex model carries type={discriminator!r}; "
        "translate._tool_call still matches that string and would now return "
        "None for every such item, silently dropping the tool call"
    )
    return matches[0]


@pytest.mark.parametrize(
    ("discriminator", "expected_tool_name", "payload"),
    [
        pytest.param(
            "commandExecution",
            "exec_command",
            {
                "id": "item-1",
                "type": "commandExecution",
                "command": "ls",
                "cwd": "/workspace",
                "aggregated_output": "a\nb\n",
                "exit_code": 0,
                "status": "completed",
            },
            id="commandExecution",
        ),
        pytest.param(
            "mcpToolCall",
            "srv.tool",
            {
                "id": "item-2",
                "type": "mcpToolCall",
                "server": "srv",
                "tool": "tool",
                "arguments": "{}",
                "status": "completed",
            },
            id="mcpToolCall",
        ),
        pytest.param(
            "dynamicToolCall",
            "ns.tool",
            {
                "id": "item-3",
                "type": "dynamicToolCall",
                "namespace": "ns",
                "tool": "tool",
                "arguments": "{}",
                "status": "completed",
            },
            id="dynamicToolCall",
        ),
        pytest.param(
            "fileChange",
            "apply_patch",
            {
                "id": "item-4",
                "type": "fileChange",
                "changes": [],
                "status": "completed",
            },
            id="fileChange",
        ),
        pytest.param(
            "webSearch",
            "web_search",
            {"id": "item-5", "type": "webSearch", "query": "veadk"},
            id="webSearch",
        ),
    ],
)
def test_thread_item_discriminators_match_sdk(
    discriminator: str, expected_tool_name: str, payload: dict
) -> None:
    """``_tool_call`` is a second string-matched surface, previously untested.

    It maps a thread item's ``type`` onto an ADK tool name. A discriminator
    rename makes it return ``None``, which drops the ``function_call`` /
    ``function_response`` pair for that tool entirely -- with no error.
    """
    model = _item_model_for(discriminator)
    try:
        instance = model.model_validate(payload)
    except ValidationError as error:
        pytest.fail(f"{model.__name__}.model_validate rejected {payload!r}:\n{error}")

    dumped = instance.model_dump()
    assert dumped.get("type") == discriminator, dumped

    call = translate._tool_call(dumped)
    assert call is not None, (
        f"_tool_call returned None for a real {discriminator} item; the tool "
        "call and its result would be silently dropped"
    )
    assert call[0] == expected_tool_name, call
