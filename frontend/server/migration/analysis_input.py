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

"""Questions a running analysis turn asks the user through Studio.

Codex' own ``request_user_input`` tool exists in Plan mode only, so the read-only
analysis cannot use it: switching collaboration mode would rewrite the agent's
instructions and disable tools the analysis relies on.  The analysis turn therefore
registers its own ``askUser`` dynamic tool.  Its handler publishes the questions,
waits for the browser to answer, and returns the answers as the tool result, so one
attempt finishes the whole analysis instead of re-running it from scratch.

The question and answer shapes mirror Codex' native protocol on purpose: questions are
``{id, header, question, options[]}`` and answers are ``{"<questionId>": {"answers":
[...]}}``.  Transport and protocol therefore stay interchangeable.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from collections.abc import Callable, Iterable
from concurrent.futures import Future, InvalidStateError
from dataclasses import dataclass

ASK_TOOL_NAME = "askUser"
ASK_TOOL_DESCRIPTION = (
    "在只读分析过程中向用户提出必须由用户决定的问题，并等待用户回答。"
    "一次提出 1-3 个问题，每个问题给出简短 header 和完整 question；"
    "有自然选择时给出 2-3 个 options（每个含 label 和 description，第一项为推荐项），"
    "没有自然选择时省略 options，用户会直接填写。"
    "只能提问项目内容无法回答、且答案会改变迁移方式或迁移范围的问题；"
    "能自己从项目里查到的事实必须自己查。"
)

# The native protocol asks for at most three questions; a longer list is a
# questionnaire, which is a different product decision.
MAX_QUESTIONS = 3
MAX_OPTIONS = 6
MAX_HEADER_LENGTH = 24
MAX_QUESTION_LENGTH = 1_000
MAX_OPTION_LABEL_LENGTH = 60
MAX_OPTION_DESCRIPTION_LENGTH = 200
MAX_ANSWER_LENGTH = 4_000
MAX_ANSWERS_PER_QUESTION = 8
# An entry nothing ever settles would keep a card on the page forever.
MAX_PENDING_SECONDS = 3_600.0

_QUESTION_ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")

Answers = dict[str, tuple[str, ...]]


class AnalysisAskError(ValueError):
    """The ``askUser`` call cannot be shown to the user as written."""


def _text(
    value: object,
    *,
    maximum: int,
    field: str,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise AnalysisAskError(f"{field} 必须是字符串")
    text = value.strip()
    if not text and not allow_empty:
        raise AnalysisAskError(f"{field} 不能为空")
    if len(text) > maximum:
        raise AnalysisAskError(f"{field} 不能超过 {maximum} 个字符")
    return text


def _options(value: object) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AnalysisAskError("options 必须是数组")
    if len(value) > MAX_OPTIONS:
        raise AnalysisAskError(f"options 不能超过 {MAX_OPTIONS} 项")
    options: list[dict[str, str]] = []
    labels: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise AnalysisAskError("options 的每一项都必须包含 label 和 description")
        label = _text(
            item.get("label"),
            maximum=MAX_OPTION_LABEL_LENGTH,
            field="options.label",
        )
        if label in labels:
            raise AnalysisAskError("options 的 label 不能重复")
        labels.add(label)
        options.append(
            {
                "label": label,
                "description": _text(
                    item.get("description"),
                    maximum=MAX_OPTION_DESCRIPTION_LENGTH,
                    field="options.description",
                ),
            }
        )
    return options


def normalize_questions(arguments: object) -> tuple[dict[str, object], ...]:
    """Validate one ``askUser`` call and return the questions the page renders."""
    if not isinstance(arguments, dict):
        raise AnalysisAskError("参数必须是对象")
    raw = arguments.get("questions")
    if not isinstance(raw, list) or not raw:
        raise AnalysisAskError("questions 必须是非空数组")
    if len(raw) > MAX_QUESTIONS:
        raise AnalysisAskError(f"questions 不能超过 {MAX_QUESTIONS} 个")
    questions: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise AnalysisAskError("questions 的每一项都必须是对象")
        question_id = _text(item.get("id"), maximum=64, field="questions.id")
        if not _QUESTION_ID_RE.match(question_id):
            raise AnalysisAskError(
                "questions.id 只能包含字母、数字、下划线、点或连字符，且不超过 64 个字符"
            )
        if question_id in seen:
            raise AnalysisAskError("questions.id 不能重复")
        seen.add(question_id)
        questions.append(
            {
                "id": question_id,
                "header": _text(
                    item.get("header"),
                    maximum=MAX_HEADER_LENGTH,
                    field="questions.header",
                ),
                "question": _text(
                    item.get("question"),
                    maximum=MAX_QUESTION_LENGTH,
                    field="questions.question",
                ),
                "options": _options(item.get("options")),
            }
        )
    return tuple(questions)


def _answers(value: object) -> Answers:
    """Validate the answers the browser submits for one question set."""
    if not isinstance(value, dict) or not value:
        raise AnalysisAskError("answers 必须是非空对象")
    answers: Answers = {}
    for raw_id, raw_answer in value.items():
        question_id = _text(raw_id, maximum=64, field="answers 的键")
        values = raw_answer if isinstance(raw_answer, list) else [raw_answer]
        if not values or len(values) > MAX_ANSWERS_PER_QUESTION:
            raise AnalysisAskError("answers 的每项必须包含 1-8 个回答")
        collected: list[str] = []
        for entry in values:
            text = _text(
                entry,
                maximum=MAX_ANSWER_LENGTH,
                field="answers 的值",
                allow_empty=True,
            )
            if text:
                collected.append(text)
        if not collected:
            raise AnalysisAskError("answers 的值不能为空")
        answers[question_id] = tuple(collected)
    return answers


def normalize_answers(value: object) -> Answers:
    """Public wrapper so routes and tests validate answers the same way."""
    return _answers(value)


ASK_TOOL_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["questions"],
    "properties": {
        "questions": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_QUESTIONS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "header", "question"],
                "properties": {
                    "id": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 64,
                        "pattern": "^[A-Za-z0-9_.-]+$",
                    },
                    "header": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_HEADER_LENGTH,
                    },
                    "question": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_QUESTION_LENGTH,
                    },
                    "options": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_OPTIONS,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["label", "description"],
                            "properties": {
                                "label": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": MAX_OPTION_LABEL_LENGTH,
                                },
                                "description": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": MAX_OPTION_DESCRIPTION_LENGTH,
                                },
                            },
                        },
                    },
                },
            },
        }
    },
}


@dataclass(frozen=True)
class PendingAnalysisInput:
    """One question set that an analysis turn is waiting on."""

    request_id: str
    attempt: int
    questions: tuple[dict[str, object], ...]
    created_at: float
    future: Future[Answers | None]


def ask_payload(pending: PendingAnalysisInput) -> dict[str, object]:
    """The question set as the page renders it."""
    return {
        "id": pending.request_id,
        "questions": [dict(question) for question in pending.questions],
    }


class AnalysisInputRegistry:
    """Track the questions each Sandbox session's analysis turn is waiting on.

    The analysis turn runs on its own event loop inside a Studio background worker,
    while the answer arrives on an HTTP request thread, so the hand-off is a
    ``concurrent.futures.Future``: it is settled from any thread and awaited from the
    worker's loop.  Settling with ``None`` is the "no answer" outcome, which the turn
    turns into the ``needs_input`` fallback instead of a hung tool call.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_pending_seconds: float = MAX_PENDING_SECONDS,
    ) -> None:
        self._clock = clock
        self._max_pending_seconds = max_pending_seconds
        self._lock = threading.Lock()
        self._pending: dict[str, PendingAnalysisInput] = {}

    def open(
        self,
        session_id: str,
        *,
        attempt: int,
        questions: Iterable[dict[str, object]],
    ) -> PendingAnalysisInput:
        """Publish one question set, releasing whatever was pending before."""
        pending = PendingAnalysisInput(
            request_id=uuid.uuid4().hex,
            attempt=attempt,
            questions=tuple(dict(question) for question in questions),
            created_at=self._clock(),
            future=Future(),
        )
        with self._lock:
            previous = self._pending.pop(session_id, None)
            self._pending[session_id] = pending
        if previous is not None:
            _settle(previous.future, None)
        return pending

    def pending(self, session_id: str) -> PendingAnalysisInput | None:
        """The live question set for one session, or ``None``."""
        with self._lock:
            pending = self._pending.get(session_id)
            if pending is None:
                return None
            if pending.future.done() or self._is_stale(pending):
                self._pending.pop(session_id, None)
                return None
            return pending

    def resolve(
        self,
        session_id: str,
        *,
        request_id: str,
        answers: Answers,
    ) -> bool:
        """Deliver answers to the waiting turn.  ``False`` means the ask is gone."""
        with self._lock:
            pending = self._pending.get(session_id)
            if (
                pending is None
                or pending.request_id != request_id
                or not _settle(pending.future, answers)
            ):
                return False
            self._pending.pop(session_id, None)
            return True

    def discard(self, session_id: str, *, request_id: str = "") -> None:
        """Withdraw one question set and release anyone still waiting on it."""
        with self._lock:
            pending = self._pending.get(session_id)
            if pending is None:
                return
            if request_id and pending.request_id != request_id:
                return
            self._pending.pop(session_id, None)
        _settle(pending.future, None)

    def _is_stale(self, pending: PendingAnalysisInput) -> bool:
        if self._max_pending_seconds <= 0:
            return False
        return self._clock() - pending.created_at > self._max_pending_seconds


def _settle(future: Future[Answers | None], value: Answers | None) -> bool:
    """Settle one pending hand-off, tolerating a waiter that already gave up."""
    if future.done():
        return False
    try:
        future.set_result(value)
    except InvalidStateError:
        return False
    return True


__all__ = [
    "ASK_TOOL_DESCRIPTION",
    "ASK_TOOL_NAME",
    "ASK_TOOL_SCHEMA",
    "MAX_PENDING_SECONDS",
    "AnalysisAskError",
    "AnalysisInputRegistry",
    "Answers",
    "PendingAnalysisInput",
    "ask_payload",
    "normalize_answers",
    "normalize_questions",
]
