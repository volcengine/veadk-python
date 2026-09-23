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

"""Studio side of the judge channel: one app-server turn per Sandbox request.

The runner keeps owning batching, the thread record, the batch cache, and the report;
this driver only answers the request the runner writes.  It is driven by the evaluation
watcher, so every property that matters comes from being replayable:

* the request stays on disk until it has an answer, so a Studio restart re-runs the
  same turn instead of losing the batch;
* one turn per request id runs at a time, and the answer is written once, so a slow
  turn is never started twice;
* a turn that cannot deliver is answered with an error envelope, which sends the
  runner straight back to ``codex exec`` instead of leaving it waiting.

The request declares how long the runner will wait (``budget_seconds``); the turn is
sized to answer inside that window, so the runner always reads an answer - a verdict or
a reason - instead of timing out on work that was still running.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import json
import threading
import time

from veadk.utils.logger import get_logger

from ..gateway import (
    MigrationGateway,
    MigrationGatewayError,
    MigrationRemoteFileNotFound,
    MigrationSandboxSession,
)
from ..codex_tool_turn import (
    ToolTurnDeadlineExceeded,
    ToolTurnUnavailable,
)
from .judge_app_server import run_judge_turn
from .judge_channel import (
    JUDGE_CHANNEL_SCHEMA_VERSION,
    judge_app_server_enabled,
    judge_channel_paths,
)

logger = get_logger(__name__)

# 单条请求可能内嵌整批用例与 Runtime 观测，读取上限与评测报告保持一致。
JUDGE_REQUEST_MAX_BYTES = 16 * 1024 * 1024
# 单次回合的上限（不依赖 runner 给多少预算时的兜底值）。
# 实测一次成功判定约 130s，慢回合会超过 240s，因此这里留到 300s。
JUDGE_TURN_TIMEOUT_SECONDS = 300.0
# 续跑既有线程的预算；剩余预算留给「线程已失效，改用新线程」的第二次尝试。
JUDGE_RESUME_TIMEOUT_SECONDS = 90.0
# 从 runner 给的窗口里预留给「取件 + 落盘 + runner 轮询」的时间。
# runner 必须早于它自己的等待上限拿到信封，否则会先超时降级。
JUDGE_TURN_RESERVE_SECONDS = 30.0
_CASE_CONTEXT_FLAGS = ("criteria", "contract", "runtime_observation")

__all__ = [
    "JUDGE_REQUEST_MAX_BYTES",
    "JUDGE_RESUME_TIMEOUT_SECONDS",
    "JUDGE_TURN_RESERVE_SECONDS",
    "JUDGE_TURN_TIMEOUT_SECONDS",
    "JudgeRequest",
    "JudgeRequestError",
    "SandboxJudgeDriver",
    "answer_judge_request",
    "judge_turn_budget",
    "parse_judge_request",
]


class JudgeRequestError(RuntimeError):
    """One Sandbox judge request is not a valid channel message."""


@dataclass(frozen=True)
class JudgeRequest:
    """One batch the Sandbox is asking Studio to judge."""

    request_id: str
    prompt: str
    case_context: tuple[dict[str, object], ...]
    dimensions: tuple[str, ...]
    thread_id: str
    # runner 授予的应答窗口（秒）；0 表示请求方没有声明，用本地上限兜底。
    budget_seconds: float = 0.0

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(str(entry["case_id"]) for entry in self.case_context)


def parse_judge_request(value: object) -> JudgeRequest:
    """Parse and bound one ``request.json`` payload."""
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != JUDGE_CHANNEL_SCHEMA_VERSION
    ):
        raise JudgeRequestError("评测裁判请求的协议版本不匹配")
    request_id = value.get("request_id")
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise JudgeRequestError("评测裁判请求缺少有效的 request_id")
    prompt = value.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise JudgeRequestError("评测裁判请求缺少提示词")
    dimensions = value.get("dimensions")
    if (
        not isinstance(dimensions, list)
        or not dimensions
        or len(set(dimensions)) != len(dimensions)
        or any(not isinstance(item, str) or not item for item in dimensions)
    ):
        raise JudgeRequestError("评测裁判请求的维度无效")
    entries = value.get("case_context")
    if not isinstance(entries, list) or not entries or len(entries) > 64:
        raise JudgeRequestError("评测裁判请求的用例上下文无效")
    case_context: list[dict[str, object]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise JudgeRequestError(f"评测裁判请求的用例上下文 {index} 无效")
        case_id = entry.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise JudgeRequestError(f"评测裁判请求的用例上下文 {index} 缺少 case_id")
        state = entry.get("state")
        context: dict[str, object] = {
            "case_id": case_id,
            "state": state if isinstance(state, str) else "",
        }
        for flag in _CASE_CONTEXT_FLAGS:
            context[flag] = entry.get(flag) is True
        case_context.append(context)
    thread_id = value.get("thread_id")
    if thread_id is None:
        thread_id = ""
    if not isinstance(thread_id, str) or len(thread_id) > 256:
        raise JudgeRequestError("评测裁判请求的线程标识无效")
    budget = value.get("budget_seconds")
    if budget is None:
        budget_seconds = 0.0
    elif (
        isinstance(budget, bool)
        or not isinstance(budget, (int, float))
        or budget <= 0
        or budget > 24 * 3600
    ):
        raise JudgeRequestError("评测裁判请求的时间预算无效")
    else:
        budget_seconds = float(budget)
    return JudgeRequest(
        request_id=request_id,
        prompt=prompt,
        case_context=tuple(case_context),
        dimensions=tuple(dimensions),
        thread_id=thread_id,
        budget_seconds=budget_seconds,
    )


def judge_turn_budget(request: JudgeRequest) -> float:
    """How long this turn may run before it must answer the runner.

    The runner owns the deadline: it declares how long it will wait, and the turn has
    to finish early enough for its answer to reach the runner before that window
    closes.  Without a declared window the local ceiling applies.
    """
    if request.budget_seconds <= 0:
        return JUDGE_TURN_TIMEOUT_SECONDS
    return min(
        JUDGE_TURN_TIMEOUT_SECONDS,
        request.budget_seconds - JUDGE_TURN_RESERVE_SECONDS,
    )


def _judge_response(
    request: JudgeRequest,
    *,
    cases: dict[str, object] | None = None,
    thread_id: str = "",
    error: dict[str, str] | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": JUDGE_CHANNEL_SCHEMA_VERSION,
        "request_id": request.request_id,
        "ok": error is None,
        "thread_id": thread_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if error is None:
        value["cases"] = cases
    else:
        value["error"] = error
    return value


def answer_judge_request(
    request: JudgeRequest,
    *,
    endpoint: str,
    cwd: str,
    model: str = "",
    timeout_seconds: float | None = None,
) -> dict[str, object]:
    """Run the app-server turn for one batch and return the response envelope.

    A resumed thread that can no longer be attached is retried once on a fresh thread:
    losing the judge thread costs continuity, while failing the batch costs the report.
    Every step of that plan shares one deadline, so the envelope is written while the
    runner is still waiting for it.
    """
    if timeout_seconds is None:
        timeout_seconds = judge_turn_budget(request)
    started = time.monotonic()
    deadline = started + timeout_seconds
    plan: list[tuple[str, float]] = []
    if request.thread_id:
        plan.append((request.thread_id, JUDGE_RESUME_TIMEOUT_SECONDS))
    plan.append(("", 0.0))
    failure: Exception | None = None
    for thread_id, resume_budget in plan:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if resume_budget > 0:
            remaining = min(resume_budget, remaining)
        try:
            cases, used_thread = asyncio.run(
                run_judge_turn(
                    endpoint=endpoint,
                    prompt=request.prompt,
                    cwd=cwd,
                    case_context=[dict(entry) for entry in request.case_context],
                    dimensions=list(request.dimensions),
                    thread_id=thread_id,
                    model=model,
                    timeout_seconds=remaining,
                )
            )
        except ToolTurnUnavailable as error:
            failure = error
            continue
        except Exception as error:  # noqa: BLE001 - 任何回合故障都必须变成信封
            # 不认识的问题也必须有答案，否则 runner 会一直等到自己的窗口结束。
            logger.exception(
                "Studio judge turn raised request_id=%s error_type=%s",
                request.request_id,
                type(error).__name__,
            )
            failure = error
            continue
        logger.info(
            "Studio judge turn delivered request_id=%s elapsed=%.1fs thread_id=%s",
            request.request_id,
            time.monotonic() - started,
            used_thread,
        )
        return _judge_response(request, cases=cases, thread_id=used_thread)
    ran_out_of_time = failure is None or isinstance(failure, ToolTurnDeadlineExceeded)
    detail = str(failure) if failure is not None else "评测裁判回合超出时间预算"
    logger.warning(
        "Studio judge turn unavailable request_id=%s error_type=%s budget=%.0fs "
        "elapsed=%.1fs",
        request.request_id,
        type(failure).__name__ if failure is not None else "timeout",
        timeout_seconds,
        time.monotonic() - started,
    )
    return _judge_response(
        request,
        error={
            "code": (
                "judge_turn_timeout" if ran_out_of_time else "judge_turn_unavailable"
            ),
            "message": detail[:512],
        },
    )


class SandboxJudgeDriver:
    """Answer pending judge requests for the evaluation attempts of one Studio run."""

    def __init__(
        self,
        gateway: MigrationGateway,
        *,
        cwd: str,
        model: str = "",
        enabled: Callable[[], bool] = judge_app_server_enabled,
    ) -> None:
        self._gateway = gateway
        self._cwd = cwd
        self._model = model
        self._enabled = enabled
        self._turns: dict[tuple[str, int], threading.Thread] = {}
        self._answered: dict[tuple[str, int], set[str]] = {}

    def drive(
        self,
        session: MigrationSandboxSession,
        *,
        evaluation_root: str,
        attempt: int,
    ) -> None:
        """Answer the pending request of this attempt, if there is an unanswered one.

        Cheap to call on every watcher tick: it reads one small file and returns unless
        the runner is waiting for a batch Studio has not answered yet.
        """
        if attempt < 1 or not self._enabled():
            return
        key = (session.session_id, attempt)
        running = self._turns.get(key)
        if running is not None and running.is_alive():
            return
        request_path, _ = judge_channel_paths(evaluation_root, attempt)
        try:
            content = self._gateway.get_file(
                session,
                request_path,
                max_bytes=JUDGE_REQUEST_MAX_BYTES,
            )
        except MigrationRemoteFileNotFound:
            return
        except MigrationGatewayError as error:
            logger.warning(
                "Studio judge channel read failed task_id=%s attempt=%s code=%s",
                session.task_id,
                attempt,
                error.code,
            )
            return
        try:
            request = parse_judge_request(json.loads(content))
        except (UnicodeDecodeError, ValueError, JudgeRequestError) as error:
            logger.warning(
                "Studio judge channel request rejected task_id=%s attempt=%s "
                "error_type=%s",
                session.task_id,
                attempt,
                type(error).__name__,
            )
            return
        if request.request_id in self._answered.get(key, frozenset()):
            return
        logger.info(
            "Studio judge channel turn started task_id=%s attempt=%s request_id=%s "
            "budget=%.0fs thread=%s",
            session.task_id,
            attempt,
            request.request_id,
            judge_turn_budget(request),
            "resumed" if request.thread_id else "new",
        )
        worker = threading.Thread(
            target=self._answer,
            args=(session, attempt, evaluation_root, key, request),
            name=f"migration-judge-{attempt}",
            daemon=True,
        )
        self._turns[key] = worker
        try:
            worker.start()
        except Exception:  # noqa: BLE001 - a failed start must not break the tick
            self._turns.pop(key, None)
            logger.exception(
                "Studio judge worker could not start task_id=%s attempt=%s",
                session.task_id,
                attempt,
            )

    def _answer(
        self,
        session: MigrationSandboxSession,
        attempt: int,
        evaluation_root: str,
        key: tuple[str, int],
        request: JudgeRequest,
    ) -> None:
        try:
            response = answer_judge_request(
                request,
                endpoint=session.endpoint,
                cwd=self._cwd,
                model=self._model,
            )
            _, response_path = judge_channel_paths(evaluation_root, attempt)
            self._gateway.put_file(
                session,
                response_path,
                json.dumps(
                    response,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8"),
                media_type="application/json",
            )
            self._answered.setdefault(key, set()).add(request.request_id)
            logger.info(
                "Studio judge channel answered task_id=%s attempt=%s request_id=%s "
                "ok=%s",
                session.task_id,
                attempt,
                request.request_id,
                str(response.get("ok")).lower(),
            )
        except Exception:  # noqa: BLE001 - the watcher tick must survive this
            logger.exception(
                "Studio judge channel answer failed task_id=%s attempt=%s "
                "request_id=%s",
                session.task_id,
                attempt,
                request.request_id,
            )
        finally:
            if self._turns.get(key) is threading.current_thread():
                self._turns.pop(key, None)
