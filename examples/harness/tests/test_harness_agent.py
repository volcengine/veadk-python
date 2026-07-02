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

import asyncio
from types import SimpleNamespace

from harness_modules import (
    ContextEngine,
    HarnessRunProcessor,
    LocalHarnessStore,
    ResultVerifier,
)


class FakeRunner:
    user_id = "runner-user"


def _message(text: str) -> SimpleNamespace:
    return SimpleNamespace(parts=[SimpleNamespace(text=text)])


def _event(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=SimpleNamespace(parts=[SimpleNamespace(text=text, thought=False)])
    )


async def _collect(generator):
    texts = []
    async for event in generator:
        texts.append(event.content.parts[0].text)
    return texts


def test_baseline_without_verifier_returns_fake_answer(tmp_path):
    store = LocalHarnessStore(tmp_path)
    processor = HarnessRunProcessor(
        store=store,
        context_engine=ContextEngine(store=store),
        verifier=ResultVerifier(store=store),
        verify=False,
    )
    message = _message("请给出最新政策并附来源。")

    async def event_generator():
        yield _event("政策已发布，参考 https://fake.example/policy。")

    async def run():
        with processor.bind_run(
            user_id="u1",
            session_id="s1",
            original_prompt="请给出最新政策并附来源。",
            run_id="r1",
        ):
            wrapped = processor.process_run(FakeRunner(), message)(event_generator)
            return await _collect(wrapped())

    texts = asyncio.run(run())

    assert texts == ["政策已发布，参考 https://fake.example/policy。"]
    assert processor.last_report is None


def test_processor_injects_context_and_records_failed_verification(tmp_path):
    store = LocalHarnessStore(tmp_path)
    processor = HarnessRunProcessor(
        store=store,
        context_engine=ContextEngine(store=store),
        verifier=ResultVerifier(store=store),
    )
    message = _message("请给出最新政策并附来源。")

    async def event_generator():
        yield _event("政策已发布，参考 https://fake.example/policy。")

    async def run():
        with processor.bind_run(
            user_id="u1",
            session_id="s1",
            original_prompt="请给出最新政策并附来源。",
            run_id="r1",
        ):
            wrapped = processor.process_run(FakeRunner(), message)(event_generator)
            return await _collect(wrapped())

    asyncio.run(run())

    assert "[Harness Context]" in message.parts[0].text
    assert "AC-grounded-facts" in message.parts[0].text
    assert processor.last_report is not None
    assert processor.last_report.done is False
    assert any(
        "fake.example" in item for item in processor.last_report.missing_requirements
    )

    report = store.load_report(session_id="s1", run_id="r1")
    assert report["done"] is False


def test_second_turn_gets_history_projection(tmp_path):
    store = LocalHarnessStore(tmp_path)
    context_engine = ContextEngine(store=store)
    processor = HarnessRunProcessor(
        store=store,
        context_engine=context_engine,
        verifier=ResultVerifier(store=store),
    )

    async def first_event_generator():
        yield _event("1. 保留来源\n2. 保留收据")

    async def second_event_generator():
        yield _event("继续输出。")

    async def run_once(prompt: str, run_id: str, generator):
        message = _message(prompt)
        with processor.bind_run(
            user_id="u1",
            session_id="s1",
            original_prompt=prompt,
            run_id=run_id,
        ):
            wrapped = processor.process_run(FakeRunner(), message)(generator)
            await _collect(wrapped())
        return message

    asyncio.run(run_once("列出三条 Harness 验收要求。", "r1", first_event_generator))
    second_message = asyncio.run(
        run_once("继续按刚才的格式输出。", "r2", second_event_generator)
    )

    assert processor.last_context is not None
    assert processor.last_context.turn_type == "follow_up"
    assert any(
        item["role"] == "assistant" and "保留来源" in item["content"]
        for item in processor.last_context.history_projection
    )
    assert "Recent session history:" in second_message.parts[0].text
