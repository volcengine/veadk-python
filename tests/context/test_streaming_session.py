"""Native streaming parser + SDK compression + SQLite, with no network."""

import asyncio
import copy
import hashlib
import json
import re
from contextlib import aclosing

import pytest
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.runners import Runner
from google.genai import types
from litellm import ModelResponse, ModelResponseStream

from veadk import Agent
from veadk.context.attempts import current_attempts
from veadk.context.budget import check_payload
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import current_scope, is_summary
from veadk.context.summary import HistorySummary
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.models.retrying_lite_llm import RetryingLiteLlm

MODEL = "deepseek-v4-1-flash-260910"
POLICY = ContextCompressionConfig(
    context_window=256000,
    input_limit=24000,
    tool_result_max_bytes=4000,
    retrieval_max_bytes=1800,
    max_model_attempts=1,
)
RUN = RunConfig(streaming_mode=StreamingMode.SSE, max_llm_calls=5)
IDENTITY = {"app_name": "stream_contract", "user_id": "synthetic", "session_id": "one"}


def message(text):
    return types.Content(role="user", parts=[types.Part(text=text)])


def validate_history_read(session, expected_source):
    """Rebuild the documented history representation from original events."""

    def digest(value):
        if not isinstance(value, str):
            value = json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        return hashlib.sha256(value.encode()).hexdigest()

    identity = [session.app_name, session.user_id, session.id, "archive_agent", ""]
    key = "veadk:references:" + digest(identity)[:24]
    references = {}
    for event in session.events:
        references.update(event.actions.state_delta.get(key, {}))
    references.update(session.state.get(key, {}))
    page = [
        p.function_response.response
        for e in session.events
        if e.content
        for p in e.content.parts or []
        if p.function_response and p.function_response.name == "veadk_read_context"
    ][-1]
    descriptor = references[page["reference"]]
    assert page["reference"] == "ctx_" + digest([identity, descriptor])[:24]
    assert descriptor["kind"] == "history"
    by_id = {event.id: event for event in session.events}
    records = []
    for item in descriptor["events"]:
        record = by_id[item["id"]].content.model_dump(mode="json", exclude_none=True)
        assert digest(record) == item["hash"]
        records.append(record)
    originals = [
        part["function_response"]["response"]["result"]
        for record in records
        for part in record.get("parts", [])
        if part.get("function_response", {}).get("name") == "fetch_archive"
    ]
    assert originals == [expected_source]
    canonical = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    assert digest(canonical) == descriptor["text_hash"] == page["source_sha256"]
    assert page["text"] == canonical[page["offset"] : page["end"]]
    return page


def chunk(delta, finish=None):
    return ModelResponseStream(
        model=MODEL, choices=[{"index": 0, "delta": delta, "finish_reason": finish}]
    )


class Stream:
    def __init__(self, values, hold=False, fail=False):
        self.values = iter(values)
        self.hold = hold
        self.fail = fail
        self.closed = False
        self.blocked = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.values)
        except StopIteration:
            if self.hold:
                self.blocked.set()
                await asyncio.Event().wait()
            if self.fail:
                raise RuntimeError("synthetic_stream_failed")
            raise StopAsyncIteration

    async def aclose(self):
        self.closed = True


def streamed_call(name, args, call_id):
    encoded = json.dumps(args)
    split = max(1, len(encoded) // 2)
    return [
        chunk(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": encoded[:split]},
                    }
                ],
            }
        ),
        chunk(
            {"tool_calls": [{"index": 0, "function": {"arguments": encoded[split:]}}]}
        ),
        chunk({}, "tool_calls"),
    ]


class Client(LiteLLMClient):
    def __init__(self, mode="load"):
        self.mode = mode
        self.requests = []
        self.streams = []
        self.summary_requests = []

    async def acompletion(self, **kwargs):
        if is_summary.get():
            assert not kwargs.get("stream") and not kwargs.get("tools")
            check_payload(kwargs, POLICY)
            self.summary_requests.append(copy.deepcopy(kwargs))
            summary = HistorySummary(
                goal="Continue the archive task",
                active_constraints=[],
                decisions=[],
                completed_work=[],
                pending_work=[],
                evidence=["Archive stored."],
                uncertainties=["Consult original records for exact facts."],
            )
            return ModelResponse(
                model=MODEL,
                choices=[
                    {
                        "message": {
                            "role": "assistant",
                            "content": summary.model_dump_json(),
                        }
                    }
                ],
            )
        assert kwargs["stream"] and kwargs["stream_options"]["include_usage"]
        check_payload(kwargs, POLICY)
        self.requests.append(copy.deepcopy(kwargs))
        index = len(self.requests)
        hold = fail = False
        if self.mode == "load" and index == 1:
            values = streamed_call("fetch_archive", {}, "business-" + str(index))
        elif self.mode == "read" and index == 1:
            reference = re.search(r"ctx_[a-f0-9]{24}", json.dumps(kwargs["messages"]))[
                0
            ]
            values = streamed_call(
                "veadk_read_context",
                {
                    "reference": reference,
                    "query": "KEEP-STREAM-FACT",
                    "operation": "read",
                },
                "reader-" + str(index),
            )
        elif self.mode in {"hold", "fail"}:
            values = [
                chunk({"role": "assistant", "content": "Incomplete visible answer"})
            ]
            hold, fail = self.mode == "hold", self.mode == "fail"
        else:
            if self.mode == "read":
                result = json.loads(
                    next(
                        m["content"]
                        for m in reversed(kwargs["messages"])
                        if m.get("tool_call_id") == "reader-1"
                    )
                )
                assert "error" not in result
                answer = result["text"]
            else:
                answer = "Archive stored."
            split = len(answer) // 2
            values = [
                chunk({"role": "assistant", "content": answer[:split]}),
                chunk({"content": answer[split:]}),
                chunk({}, "stop"),
            ]
        stream = Stream(values, hold=hold, fail=fail)
        self.streams.append(stream)
        return stream


def runner(service, client, fetch):
    model = RetryingLiteLlm(
        model="openai/" + MODEL,
        api_key="synthetic-offline-test",
        llm_client=client,
        context_compression=POLICY,
        max_tokens=1024,
        extra_body={"thinking": {"type": "disabled"}},
    )
    agent = Agent(
        name="archive_agent",
        model=model,
        tools=[fetch],
        instruction="Use archive evidence only. Do not repeat completed source acquisition.",
    )
    return Runner(agent=agent, app_name=IDENTITY["app_name"], session_service=service)


async def collect(agent_runner, text):
    async with aclosing(
        agent_runner.run_async(
            user_id=IDENTITY["user_id"],
            session_id=IDENTITY["session_id"],
            new_message=message(text),
            run_config=RUN,
        )
    ) as events:
        return [event async for event in events]


async def setup(tmp_path):
    source = "".join(
        f"Archive item {i}: ordinary source information to preserve.\n"
        for i in range(1600)
    )
    source += "KEEP-STREAM-FACT amount=371.29 CNY; approval remains pending.\n"
    source += "".join(
        f"Archive item {i}: other original source information.\n"
        for i in range(1600, 2400)
    )
    count = [0]

    def fetch_archive() -> str:
        """Read an immutable source once."""
        count[0] += 1
        return source

    path = str(tmp_path / "session.sqlite3")
    service = ShortTermMemory(
        backend="sqlite", local_database_path=path
    ).session_service
    await service.create_session(**IDENTITY)
    client = Client()
    events = await collect(
        runner(service, client, fetch_archive), "Store the archive for later use."
    )
    assert count[0] == 1 and len(client.requests) == 2
    assert any(e.partial for e in events)
    session = await service.get_session(**IDENTITY)
    assert not any(e.partial for e in session.events)
    responses = [
        p.function_response
        for e in session.events
        if e.content
        for p in e.content.parts or []
        if p.function_response
    ]
    assert len(responses) == 1 and responses[0].response["result"] == source
    assert "ctx_" in json.dumps(client.requests[1]["messages"])
    originals = [e.model_dump(mode="json") for e in session.events]
    await service.close()
    service = ShortTermMemory(
        backend="sqlite", local_database_path=path
    ).session_service
    assert [
        e.model_dump(mode="json")
        for e in (await service.get_session(**IDENTITY)).events
    ] == originals
    return service, fetch_archive, source, count, originals


@pytest.mark.asyncio
async def test_streamed_tool_fragments_then_restart_exact_source_read(tmp_path):
    service, fetch, source, count, original = await setup(tmp_path)
    try:
        client = Client("read")
        events = await collect(
            runner(service, client, fetch),
            "Read KEEP-STREAM-FACT from the stored original.",
        )
        assert count[0] == 1 and len(client.requests) == 2
        final = [e for e in events if e.is_final_response() and not e.partial][-1]
        text = "".join(p.text or "" for p in final.content.parts)
        assert "amount=371.29 CNY" in text and text in source
        session = await service.get_session(**IDENTITY)
        assert [
            e.model_dump(mode="json") for e in session.events[: len(original)]
        ] == original
        readers = [
            p.function_response.response
            for e in session.events
            if e.content
            for p in e.content.parts or []
            if p.function_response and p.function_response.name == "veadk_read_context"
        ]
        assert len(readers) == 1
        page = readers[0]
        assert page["text"] == source[page["offset"] : page["end"]]
        assert not any(e.partial for e in session.events)
    finally:
        await service.close()
    assert current_scope.get() is None and current_attempts.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["hold", "fail"])
async def test_interrupted_stream_does_not_commit_final_or_replay_business(
    tmp_path, failure
):
    service, fetch, _source, count, original = await setup(tmp_path)
    try:
        client = Client(failure)
        task = asyncio.create_task(
            collect(runner(service, client, fetch), "Continue checking the source.")
        )
        if failure == "hold":
            async with asyncio.timeout(2):
                while not client.streams:
                    await asyncio.sleep(0)
                await client.streams[0].blocked.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            try:
                await task
            except RuntimeError:
                pass
        assert len(client.requests) == 1 and client.streams[0].closed
        session = await service.get_session(**IDENTITY)
        assert [
            e.model_dump(mode="json") for e in session.events[: len(original)]
        ] == original
        assert not any(
            e.content
            and any(
                "Incomplete visible answer" in (p.text or "")
                for p in e.content.parts or []
            )
            for e in session.events[len(original) :]
        )
        assert count[0] == 1
        recovered = await collect(
            runner(service, Client("read"), fetch),
            "Read KEEP-STREAM-FACT from the original after interruption.",
        )
        final = [e for e in recovered if e.is_final_response() and not e.partial][-1]
        assert "371.29" in "".join(p.text or "" for p in final.content.parts)
        assert count[0] == 1
    finally:
        await service.close()
    assert current_scope.get() is None and current_attempts.get() is None


@pytest.mark.asyncio
async def test_streaming_many_turns_summary_then_restart_and_read_original(tmp_path):
    service, fetch, source, count, original = await setup(tmp_path)
    summaries = 0
    try:
        for turn in range(36):
            client = Client("chatter")
            events = await collect(
                runner(service, client, fetch),
                f"Progress note {turn}: "
                + ("Temporary background; preserve archived source. " * 22),
            )
            assert any(e.is_final_response() and not e.partial for e in events)
            summaries += len(client.summary_requests)
            assert len(client.requests) == 1
        assert summaries > 0
        saved = await service.get_session(**IDENTITY)
        full_history = [e.model_dump(mode="json") for e in saved.events]
        assert full_history[: len(original)] == original
        assert not any(e.partial for e in saved.events)
        await service.close()
        service = ShortTermMemory(
            backend="sqlite", local_database_path=str(tmp_path / "session.sqlite3")
        ).session_service
        assert [
            e.model_dump(mode="json")
            for e in (await service.get_session(**IDENTITY)).events
        ] == full_history
        client = Client("read")
        events = await collect(
            runner(service, client, fetch),
            "Read KEEP-STREAM-FACT from the stored original.",
        )
        final = [e for e in events if e.is_final_response() and not e.partial][-1]
        text = "".join(p.text or "" for p in final.content.parts)
        assert "amount=371.29 CNY" in text
        saved = await service.get_session(**IDENTITY)
        page = validate_history_read(saved, source)
        assert text == page["text"]
        assert [
            e.model_dump(mode="json") for e in saved.events[: len(full_history)]
        ] == full_history
        assert count[0] == 1
    finally:
        await service.close()
    assert current_scope.get() is None and current_attempts.get() is None
