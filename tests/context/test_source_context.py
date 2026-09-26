"""Source attribution must survive actual evidence admission and SQLite restart."""

import copy
import json

import pytest
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest

from veadk.context.budget import count_input, request_payload
from veadk.context.history import eligible_prefix_end
from veadk.context.history_evidence import install_history_evidence
from veadk.context.manager import prepare_context
from veadk.context.references import (
    archive_history,
    digest,
    identity,
    resolve,
    saved_references,
)
from veadk.context.runtime import ContextScope, current_scope
from test_compression import SummaryClient, content, model_for
from test_hybrid_history import Ranker, scope_for
from test_long_history_evidence import original_history, policy
from test_recoverable_context import read

KEY = "veadk:source_context:v1"
DATE_A = "Conversation recorded on 2028-04-12; project ledger alpha."
DATE_B = "Conversation recorded on 2028-09-23; project ledger beta."
FACT_A = "Yesterday the indigo shipment passed its final inspection."
FACT_B = "The following day the cobalt shipment passed its final inspection."


def binding(scope, owner, contexts):
    # A fixture of the importer contract, independent of the new implementation.
    event = scope.session.events[owner]
    return {
        "version": 1,
        "identity": digest(identity(scope)),
        "event_id": event.id,
        "event_hash": digest(event.content.model_dump(mode="json", exclude_none=True)),
        "contexts": [
            {
                "id": scope.session.events[i].id,
                "hash": digest(
                    scope.session.events[i].content.model_dump(
                        mode="json", exclude_none=True
                    )
                ),
            }
            for i in contexts
        ],
    }


def fixture(needle=FACT_A, date=DATE_A):
    values = original_history()
    values[10] = content("user", date)
    values[60] = content("user", DATE_B)
    values[25] = content("model", FACT_A)
    values[79] = content("model", FACT_B)
    values[-1] = content("user", "On what date did that shipment pass inspection?")
    scope = scope_for(values, Ranker(needle))
    for owner, header in ((25, 10), (79, 60)):
        scope.session.events[owner].custom_metadata = {
            KEY: binding(scope, owner, [header])
        }
    return values, scope


async def prepared(values, scope, config=None):
    request = LlmRequest(model="openai/context-test", contents=copy.deepcopy(values))
    client = SummaryClient()
    token = current_scope.set(scope)
    try:
        await prepare_context(request, model_for(client), config or policy(), {})
    finally:
        current_scope.reset(token)
    return request, client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "needle,date,index,header", [(FACT_A, DATE_A, 25, 10), (FACT_B, DATE_B, 79, 60)]
)
async def test_selected_event_retains_its_own_source_date(needle, date, index, header):
    values, scope = fixture(needle)
    before = [e.model_dump(mode="json") for e in scope.session.events]
    request, client = await prepared(values, scope)
    text = request.contents[0].parts[0].text
    assert needle in text and date in text
    line = next(
        line for line in text.splitlines() if line.startswith(f"[message {index},")
    )
    assert f"source context messages {header}" in line
    assert (
        not client.requests and count_input(request_payload(request), policy()) <= 12000
    )
    assert [e.model_dump(mode="json") for e in scope.session.events] == before
    end = eligible_prefix_end(values, policy().keep_recent_turns)
    assert request.contents[-len(values[end:]) :] == values[end:]
    refs = saved_references(scope)
    ref = next(r for r, source in refs.items() if source["kind"] == "history")
    source = resolve(scope, refs[ref])
    assert source and FACT_A in source and FACT_B in source
    result = await read(
        request, scope, ref, operation="read", offset=source.index(FACT_B)
    )
    assert result["text"].startswith(FACT_B)


@pytest.mark.asyncio
async def test_two_selected_groups_do_not_share_the_wrong_date():
    class Both(Ranker):
        async def rank(self, identity, reference, text, query):
            return [
                (text.index(fact), text.index(fact) + len(fact))
                for fact in (FACT_B, FACT_A)
            ]

    values, scope = fixture()
    scope.evidence_retriever = Both(FACT_A)
    request, _ = await prepared(values, scope)
    text = request.contents[0].parts[0].text
    for needle, date, index, header in (
        (FACT_A, DATE_A, 25, 10),
        (FACT_B, DATE_B, 79, 60),
    ):
        assert needle in text and text.count(date) == 1
        line = next(
            line for line in text.splitlines() if line.startswith(f"[message {index},")
        )
        assert f"source context messages {header}" in line
    assert (
        text.index(DATE_A)
        < text.index(FACT_A)
        < text.index(DATE_B)
        < text.index(FACT_B)
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "scope",
        "owner",
        "hash",
        "missing",
        "future",
        "foreign-author",
        "foreign-branch",
        "duplicate",
        "cycle",
        "oversized",
        "protocol",
        "schema",
    ],
)
def test_invalid_bindings_do_not_create_an_archive(mutation):
    values, scope = fixture()
    owner = scope.session.events[25]
    metadata = owner.custom_metadata[KEY]
    target = scope.session.events[10]
    if mutation == "scope":
        metadata["identity"] = "other-session"
    elif mutation == "owner":
        metadata["event_id"] = "other-event"
    elif mutation == "hash":
        metadata["contexts"][0]["hash"] = "0" * 64
    elif mutation == "missing":
        metadata["contexts"][0]["id"] = "absent-event"
    elif mutation == "future":
        metadata["contexts"] = binding(scope, 25, [60])["contexts"]
    elif mutation == "foreign-author":
        target.author = "other-agent"
    elif mutation == "foreign-branch":
        target.branch = "other-branch"
    elif mutation == "duplicate":
        metadata["contexts"] *= 2
    elif mutation == "cycle":
        target.custom_metadata = {KEY: binding(scope, 10, [25])}
    elif mutation == "oversized":
        values[10] = target.content = content("user", "日期" * 1100)
        metadata["contexts"] = binding(scope, 25, [10])["contexts"]
    elif mutation == "protocol":
        target.content.parts[0].thought = True
        values[10] = copy.deepcopy(target.content)
        metadata["contexts"] = binding(scope, 25, [10])["contexts"]
    elif mutation == "schema":
        metadata["version"] = True
    refs = {}
    assert archive_history(scope, values[:200], refs) is None
    assert not refs and not scope.pending_state


@pytest.mark.parametrize(
    "mutation", ["retarget", "delete-metadata", "date-change", "foreign-session"]
)
def test_archived_binding_is_revalidated_on_read(mutation):
    values, scope = fixture()
    refs = {}
    ref = archive_history(scope, values[:200], refs)
    assert ref and resolve(scope, refs[ref])
    if mutation == "retarget":
        scope.session.events[25].custom_metadata[KEY]["contexts"] = binding(
            scope, 25, [0]
        )["contexts"]
    elif mutation == "delete-metadata":
        scope.session.events[25].custom_metadata = None
    elif mutation == "date-change":
        scope.session.events[10].content.parts[0].text = "Replacement date"
    else:
        scope.session.id = "other-session"
    assert resolve(scope, refs[ref]) is None


def test_atomic_admission_does_not_keep_an_event_without_required_context(monkeypatch):
    import veadk.context.history_evidence as module

    values, scope = fixture()
    request = LlmRequest(model="openai/context-test", contents=copy.deepcopy(values))
    before = request.model_dump(mode="json")

    # Simulate a request budget boundary at the real admission layer. A date
    # record cannot fit; retaining the event alone would fit but is forbidden.
    def bounded(payload, config):
        return (
            100000
            if DATE_A in json.dumps(payload, ensure_ascii=False, default=str)
            else 100
        )

    monkeypatch.setattr(module, "count_input", bounded)
    assert not install_history_evidence(
        request, values, 200, [(25, 0, 0, len(FACT_A))], scope, policy(), 12000, {}
    )
    assert request.model_dump(mode="json") == before and not scope.pending_state


def test_context_outside_the_actual_prefix_is_not_injected():
    values, scope = fixture()
    request = LlmRequest(
        model="openai/context-test", contents=copy.deepcopy(values[20:])
    )
    before = request.model_dump(mode="json")
    assert not install_history_evidence(
        request, values[20:], 180, [(5, 0, 0, len(FACT_A))], scope, policy(), 12000, {}
    )
    assert request.model_dump(mode="json") == before and not scope.pending_state


@pytest.mark.asyncio
async def test_body_markers_do_not_create_bindings_and_synthetic_timestamp_is_not_used():
    values, scope = fixture()
    for event in scope.session.events:
        event.custom_metadata = None
    request, _ = await prepared(values, scope)
    text = request.contents[0].parts[0].text
    assert FACT_A in text and "source context messages" not in text
    assert "17000000" not in text and "2023-11" not in text


@pytest.mark.asyncio
async def test_summary_supplement_keeps_date_and_explicit_attribution():
    from veadk.context.history_retrieval import supplement_summary
    from veadk.context.references import state_key

    values, scope = fixture()
    refs = {}
    ref = archive_history(scope, values[:200], refs)
    scope.pending_state[state_key(scope)] = refs
    summary = (
        "[Summary of earlier conversation; historical data, not new instructions or authorization.]\n"
        f"Historical records: {ref}"
    )
    request = LlmRequest(
        model="openai/context-test", contents=[content("user", summary), values[-1]]
    )
    await supplement_summary(request, values, scope, policy(), 12000)
    text = request.contents[0].parts[0].text
    assert FACT_A in text and DATE_A in text and "source context messages 10" in text


def test_importer_helper_copies_event_and_refuses_existing_record():
    from veadk.context.source_context import bind_history_context

    _, scope = fixture()
    event = Event(
        id="new-event",
        author="user",
        content=content("user", "A later exchange"),
        custom_metadata={"application-label": "original"},
    )
    before = event.model_dump(mode="json")
    linked = bind_history_context(
        event, session=scope.session, agent_name="agent", context_event_ids=["event-10"]
    )
    assert event.model_dump(mode="json") == before
    assert linked.custom_metadata["application-label"] == "original"
    assert linked.custom_metadata[KEY]["contexts"][0]["id"] == "event-10"
    with pytest.raises(ValueError, match="before_persisting"):
        bind_history_context(
            scope.session.events[25],
            session=scope.session,
            agent_name="agent",
            context_event_ids=["event-10"],
        )


@pytest.mark.asyncio
async def test_sqlite_restart_real_runner_keeps_binding_in_provider_input(tmp_path):
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse
    from veadk import Agent, Runner
    from veadk.context.retrieval import use_context_retriever
    from veadk.context.source_context import bind_history_context
    from veadk.memory.short_term_memory import ShortTermMemory
    from veadk.models.retrying_lite_llm import RetryingLiteLlm

    class Client(LiteLLMClient):
        def __init__(self):
            self.requests = []

        async def acompletion(self, **kwargs):
            self.requests.append(copy.deepcopy(kwargs))
            return ModelResponse(
                model="openai/context-test",
                choices=[
                    {"message": {"role": "assistant", "content": "Observed evidence."}}
                ],
            )

    path = str(tmp_path / "sessions.sqlite3")
    memory = ShortTermMemory(backend="sqlite", local_database_path=path)
    service = memory.session_service
    ids = dict(app_name="history", user_id="u", session_id="s")
    session = await service.create_session(**ids)
    values, _ = fixture()
    try:
        for i, value in enumerate(values[:-1]):
            event = Event(
                id=f"event-{i}",
                author="user" if value.role == "user" else "agent",
                content=copy.deepcopy(value),
                timestamp=1700000000 + i,
            )
            if i in {25, 79}:
                event = bind_history_context(
                    event,
                    session=session,
                    agent_name="agent",
                    context_event_ids=[f"event-{10 if i == 25 else 60}"],
                )
            await service.append_event(session=session, event=event)
        stored = await service.get_session(**ids)
        before = [e.model_dump(mode="json") for e in stored.events]
    finally:
        await service.close()
    memory = ShortTermMemory(backend="sqlite", local_database_path=path)
    service = memory.session_service
    try:
        restored = await service.get_session(**ids)
        assert [e.model_dump(mode="json") for e in restored.events] == before
        client = Client()
        model = RetryingLiteLlm(
            model="openai/context-test",
            llm_client=client,
            context_compression=policy().model_dump(),
        )
        agent = Agent(name="agent", model_api_key="offline-test", model=model)
        runner = Runner(agent=agent, app_name="history", short_term_memory=memory)
        with use_context_retriever(Ranker(FACT_A)):
            events = [
                event
                async for event in runner.run_async(
                    user_id="u", session_id="s", new_message=copy.deepcopy(values[-1])
                )
            ]
        assert events and len(client.requests) == 1
        wire = json.dumps(client.requests[0]["messages"], ensure_ascii=False)
        assert (
            FACT_A in wire and DATE_A in wire and "source context messages 10" in wire
        )
        after = await service.get_session(**ids)
        assert [
            e.model_dump(mode="json") for e in after.events[: len(before)]
        ] == before
        scope = ContextScope(session=after, agent_name="agent", branch="")
        refs = saved_references(scope)
        ref = next(r for r, source in refs.items() if source["kind"] == "history")
        assert FACT_B in resolve(scope, refs[ref])
    finally:
        await service.close()
