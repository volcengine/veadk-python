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

"""Checks for the questions an analysis turn asks the user through Studio."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from frontend.server.migration.analysis_input import (
    ASK_TOOL_NAME,
    AnalysisAskError,
    AnalysisInputRegistry,
    ask_payload,
    normalize_answers,
    normalize_questions,
)
from frontend.server.migration.app_server import ask_tool_handler

from frontend.server.migration.models import SubmitAnalysisInputBody
from frontend.server.migration.service import (
    MigrationError,
    MigrationService,
)
from tests.frontend.test_migration_server import (
    FakeMigrationGateway,
    agentic_delivery_task,
    create_uploaded_task,
)


def _ask(**overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "questions": [
            {
                "id": "framework",
                "header": "目标框架",
                "question": "迁移到 langchain 还是 dify？",
                "options": [
                    {"label": "langchain", "description": "保留 LangChain 结构。"},
                    {"label": "dify", "description": "输出 Dify 应用。"},
                ],
            }
        ]
    }
    arguments.update(overrides)
    return arguments


def test_ask_questions_are_normalized_and_bounded() -> None:
    questions = normalize_questions(_ask())
    assert questions == (
        {
            "id": "framework",
            "header": "目标框架",
            "question": "迁移到 langchain 还是 dify？",
            "options": [
                {"label": "langchain", "description": "保留 LangChain 结构。"},
                {"label": "dify", "description": "输出 Dify 应用。"},
            ],
        },
    )

    # 没有自然选项的问题也允许：页面直接让用户填写。
    assert normalize_questions(
        {
            "questions": [
                {"id": "app_name", "header": "应用名", "question": "新应用叫什么？"}
            ]
        }
    ) == (
        {
            "id": "app_name",
            "header": "应用名",
            "question": "新应用叫什么？",
            "options": [],
        },
    )

    for broken in (
        "not-an-object",
        {},
        {"questions": []},
        {"questions": [{"id": "a", "header": "h"}]},
        {"questions": [{"id": "has space", "header": "h", "question": "q"}]},
        {"questions": [{"id": "a", "header": "", "question": "q"}]},
        {"questions": [{"id": "a", "header": "h", "question": "q"}] * 4},
        {
            "questions": [
                {"id": "a", "header": "h", "question": "q"},
                {"id": "a", "header": "h", "question": "q"},
            ]
        },
        {"questions": [{"id": "a", "header": "h", "question": "q", "options": [{}]}]},
    ):
        with pytest.raises(AnalysisAskError):
            normalize_questions(broken)


def test_answers_are_trimmed_and_must_not_be_empty() -> None:
    assert normalize_answers({"framework": " dify "}) == {"framework": ("dify",)}
    assert normalize_answers({"framework": ["a", "b"]}) == {"framework": ("a", "b")}
    for broken in ({}, {"framework": "   "}, {"framework": []}, {"": "x"}):
        with pytest.raises(AnalysisAskError):
            normalize_answers(broken)


def test_registry_hands_answers_from_another_thread_to_the_waiting_turn() -> None:
    registry = AnalysisInputRegistry()
    pending = registry.open(
        "session-1",
        attempt=1,
        questions=normalize_questions(_ask()),
    )
    assert registry.pending("session-1") is pending
    assert ask_payload(pending) == {
        "id": pending.request_id,
        "questions": list(pending.questions),
    }

    assert (
        registry.resolve(
            "session-1",
            request_id="other-request",
            answers={"framework": ("dify",)},
        )
        is False
    )
    assert (
        registry.resolve(
            "session-1",
            request_id=pending.request_id,
            answers={"framework": ("dify",)},
        )
        is True
    )
    assert pending.future.result(timeout=1) == {"framework": ("dify",)}
    # 结算过的提问不能再次展示或结算。
    assert registry.pending("session-1") is None
    assert (
        registry.resolve(
            "session-1",
            request_id=pending.request_id,
            answers={"framework": ("dify",)},
        )
        is False
    )


def test_registry_replaces_and_discards_pending_questions() -> None:
    registry = AnalysisInputRegistry()
    first = registry.open("session-1", attempt=1, questions=normalize_questions(_ask()))
    second = registry.open(
        "session-1", attempt=2, questions=normalize_questions(_ask())
    )
    # 同一会话只保留一次提问：被替换的等待者拿到「没有回答」而不是一直挂着。
    assert first.future.result(timeout=1) is None
    assert registry.pending("session-1") is second

    registry.discard("session-1", request_id="other-request")
    assert registry.pending("session-1") is second
    registry.discard("session-1", request_id=second.request_id)
    assert second.future.result(timeout=1) is None
    assert registry.pending("session-1") is None


def test_registry_stops_showing_a_question_nobody_settles() -> None:
    now = [1_000.0]
    registry = AnalysisInputRegistry(clock=lambda: now[0], max_pending_seconds=10.0)
    pending = registry.open(
        "session-1", attempt=1, questions=normalize_questions(_ask())
    )
    now[0] += 11.0
    assert registry.pending("session-1") is None
    # 过期后迟到的回答不能再生效。
    assert (
        registry.resolve(
            "session-1",
            request_id=pending.request_id,
            answers={"framework": ("dify",)},
        )
        is False
    )


def test_ask_tool_returns_the_native_answer_shape() -> None:
    seen: list[object] = []

    async def questioner(questions: object) -> dict[str, tuple[str, ...]]:
        seen.append(questions)
        return {"framework": ("dify",)}

    handler = ask_tool_handler(questioner)  # type: ignore[arg-type]
    result = asyncio.run(handler(_ask()))
    assert result.success is True
    assert json.loads(result.text) == {"answers": {"framework": {"answers": ["dify"]}}}
    assert seen and isinstance(seen[0], tuple)


def test_ask_tool_reports_a_bad_question_instead_of_asking() -> None:
    async def questioner(questions: object) -> None:
        raise AssertionError("an invalid ask must never reach the user")

    handler = ask_tool_handler(questioner)  # type: ignore[arg-type]
    result = asyncio.run(handler({"questions": []}))
    assert result.success is False
    assert ASK_TOOL_NAME in result.text


def test_ask_tool_falls_back_when_nobody_answers() -> None:
    async def questioner(questions: object) -> None:
        return None

    handler = ask_tool_handler(questioner)  # type: ignore[arg-type]
    result = asyncio.run(handler(_ask()))
    assert result.success is True
    payload = json.loads(result.text)
    assert payload["answers"] == {}
    assert payload["unanswered"] is True
    assert "needs_input" in payload["hint"]


def test_ask_tool_survives_a_broken_channel() -> None:
    async def questioner(questions: object) -> None:
        raise RuntimeError("channel down")

    handler = ask_tool_handler(questioner)  # type: ignore[arg-type]
    result = asyncio.run(handler(_ask()))
    assert result.success is True
    assert json.loads(result.text)["unanswered"] is True


def test_pending_questions_are_exposed_until_they_are_answered() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    session_id = service._session(task_id, "owner-1").session_id

    assert "pendingInput" not in service.get_task(task_id, "owner-1")
    pending = service._analysis_input.open(
        session_id,
        attempt=1,
        questions=normalize_questions(_ask()),
    )
    task = service.get_task(task_id, "owner-1")
    # 等待回答时任务仍然处于分析中，SSE 不会提前收尾。
    assert task["state"] == "analyzing"
    assert task["pendingInput"] == ask_payload(pending)
    assert task["message"] == "分析正在等待你的回答"

    service._analysis_input.resolve(
        session_id,
        request_id=pending.request_id,
        answers={"framework": ("dify",)},
    )
    assert "pendingInput" not in service.get_task(task_id, "owner-1")


def test_a_settled_delivery_still_shows_the_questions_it_asks() -> None:
    """交付收尾回合提问时任务已经落定，卡片同样要出现。"""
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _, _ = agentic_delivery_task(service, gateway)
    session_id = service._session(task_id, "owner-1").session_id
    settled = service.get_task(task_id, "owner-1")
    assert settled["state"] == "succeeded_with_warnings"

    pending = service._analysis_input.open(
        session_id,
        attempt=1,
        questions=normalize_questions(_ask()),
    )
    task = service.get_task(task_id, "owner-1")

    # 提问不改状态：交付已经落定，回合要的是用户才知道的答案。
    assert task["state"] == "succeeded_with_warnings"
    assert task["pendingInput"] == ask_payload(pending)
    assert task["message"] == "交付说明正在等待你的回答"

    service._analysis_input.resolve(
        session_id,
        request_id=pending.request_id,
        answers={"framework": ("dify",)},
    )
    assert "pendingInput" not in service.get_task(task_id, "owner-1")


def test_submit_analysis_input_unblocks_the_waiting_turn() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    session_id = service._session(task_id, "owner-1").session_id
    pending = service._analysis_input.open(
        session_id,
        attempt=1,
        questions=normalize_questions(_ask()),
    )

    task = service.submit_analysis_input(
        task_id,
        "owner-1",
        SubmitAnalysisInputBody(
            requestId=pending.request_id,
            answers={"framework": " dify "},
        ),
    )
    assert task["state"] == "analyzing"
    assert pending.future.result(timeout=1) == {"framework": ("dify",)}


def test_submit_analysis_input_rejects_stale_and_incomplete_answers() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    session_id = service._session(task_id, "owner-1").session_id
    pending = service._analysis_input.open(
        session_id,
        attempt=1,
        questions=normalize_questions(_ask()),
    )

    with pytest.raises(MigrationError) as gone:
        service.submit_analysis_input(
            task_id,
            "owner-1",
            SubmitAnalysisInputBody(
                requestId="stale-request",
                answers={"framework": "dify"},
            ),
        )
    assert gone.value.code == "MIGRATION_ANALYSIS_INPUT_GONE"

    with pytest.raises(MigrationError) as unknown:
        service.submit_analysis_input(
            task_id,
            "owner-1",
            SubmitAnalysisInputBody(
                requestId=pending.request_id,
                answers={"other": "dify"},
            ),
        )
    assert unknown.value.code == "MIGRATION_ANALYSIS_INPUT_INVALID"

    # 未回答全部问题时保持挂起，等待页面补齐。
    assert pending.future.done() is False
    assert service._analysis_input.pending(session_id) is pending


def test_submit_analysis_input_is_gone_without_a_waiting_turn() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)

    with pytest.raises(MigrationError) as gone:
        service.submit_analysis_input(
            task_id,
            "owner-1",
            SubmitAnalysisInputBody(requestId="whatever", answers={"a": "b"}),
        )
    assert gone.value.code == "MIGRATION_ANALYSIS_INPUT_GONE"
    assert time.monotonic() > 0
