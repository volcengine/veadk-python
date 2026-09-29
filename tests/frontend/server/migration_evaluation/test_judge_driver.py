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

from __future__ import annotations

import json
from datetime import datetime, timezone
import threading
import time
from typing import Any

import pytest

from frontend.server.migration.evaluation import judge_driver as judge_driver_module
from frontend.server.migration.codex_tool_turn import (
    ToolTurnDeadlineExceeded,
    ToolTurnUnavailable,
)
from frontend.server.migration.evaluation.judge_app_server import (
    JudgeTurnUnavailable,
)
from frontend.server.migration.evaluation.judge_channel import (
    JUDGE_APP_SERVER_ENV,
    JUDGE_CHANNEL_SCHEMA_VERSION,
    judge_app_server_enabled,
    judge_channel_paths,
)
from frontend.server.migration.evaluation.judge_driver import (
    JUDGE_TURN_RESERVE_SECONDS,
    JUDGE_TURN_TIMEOUT_SECONDS,
    JudgeRequestError,
    SandboxJudgeDriver,
    answer_judge_request,
    judge_turn_budget,
    parse_judge_request,
)
from frontend.server.migration.gateway import (
    MigrationRemoteFileNotFound,
    MigrationSandboxSession,
)

TASK_ID = "migration-v1-" + "1" * 32
EVALUATION_ROOT = "/migration/evaluation/v1"


class FakeGateway:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.puts: list[str] = []

    def put_file(
        self,
        _session: MigrationSandboxSession,
        path: str,
        content: bytes,
        *,
        media_type: str,
    ) -> None:
        assert media_type
        self.puts.append(path)
        self.files[path] = content

    def get_file(
        self,
        _session: MigrationSandboxSession,
        path: str,
        *,
        max_bytes: int,
    ) -> bytes:
        if path not in self.files:
            raise MigrationRemoteFileNotFound(path)
        content = self.files[path]
        assert len(content) <= max_bytes
        return content


def _session() -> MigrationSandboxSession:
    return MigrationSandboxSession(
        tool_id="tool",
        session_id="session",
        task_id=TASK_ID,
        endpoint="https://sandbox.invalid",
        region="cn-beijing",
        status="Ready",
        created_at="2026-09-07T09:00:00Z",
        expire_at=datetime.fromtimestamp(
            datetime(2026, 9, 7, 11, tzinfo=timezone.utc).timestamp() + 7200,
            timezone.utc,
        )
        .isoformat()
        .replace("+00:00", "Z"),
        owner_id="owner",
    )


def _request_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": JUDGE_CHANNEL_SCHEMA_VERSION,
        "request_id": "batch-001-002-attempt-1",
        "batch_start": 0,
        "batch_end": 2,
        "case_ids": ["case-1", "case-2"],
        "dimensions": ["semantic_fidelity", "output_contract"],
        "prompt_version": 4,
        "thread_id": "",
        "prompt": "judge this batch",
        "created_at": "2026-09-07T10:00:00Z",
        "case_context": [
            {
                "case_id": "case-1",
                "state": "succeeded",
                "criteria": True,
                "contract": False,
                "runtime_observation": True,
            },
            {
                "case_id": "case-2",
                "state": "failed",
                "criteria": False,
                "contract": False,
                "runtime_observation": False,
            },
        ],
    }
    payload.update(overrides)
    return payload


_JUDGED_CASES: list[dict[str, Any]] = [
    {
        "case_id": "case-1",
        "dimensions": [
            {
                "id": "semantic_fidelity",
                "score": 0.8,
                "reason": "一致",
                "evidence": ["输出证据"],
                "evidence_sources": ["observed_output"],
                "severity": "low",
            }
        ],
    }
]


def _wait_for(predicate: Any, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.mark.parametrize("value", ["0", "false", "no", "off", " OFF "])
def test_judge_channel_switch_can_pin_the_scripted_judge(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv(JUDGE_APP_SERVER_ENV, value)

    assert judge_app_server_enabled() is False


@pytest.mark.parametrize("value", ["", "1", "true", "yes"])
def test_judge_channel_is_on_by_default(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    if value:
        monkeypatch.setenv(JUDGE_APP_SERVER_ENV, value)
    else:
        monkeypatch.delenv(JUDGE_APP_SERVER_ENV, raising=False)

    assert judge_app_server_enabled() is True


def test_judge_channel_paths_are_attempt_scoped() -> None:
    request, response = judge_channel_paths(EVALUATION_ROOT, 2)

    assert request == f"{EVALUATION_ROOT}/results/attempt-2/judge/request.json"
    assert response == f"{EVALUATION_ROOT}/results/attempt-2/judge/response.json"


def test_parse_judge_request_normalizes_the_batch_contract() -> None:
    request = parse_judge_request(_request_payload())

    assert request.request_id == "batch-001-002-attempt-1"
    assert request.case_ids == ("case-1", "case-2")
    assert request.dimensions == ("semantic_fidelity", "output_contract")
    assert request.thread_id == ""
    assert request.budget_seconds == 0.0
    assert parse_judge_request(_request_payload(budget_seconds=360)).budget_seconds == (
        360.0
    )
    assert request.case_context[1] == {
        "case_id": "case-2",
        "state": "failed",
        "criteria": False,
        "contract": False,
        "runtime_observation": False,
    }


@pytest.mark.parametrize(
    "payload",
    [
        _request_payload(schema_version=JUDGE_CHANNEL_SCHEMA_VERSION + 1),
        _request_payload(request_id=""),
        _request_payload(request_id="x" * 129),
        _request_payload(prompt="   "),
        _request_payload(dimensions=[]),
        _request_payload(dimensions=["semantic_fidelity", "semantic_fidelity"]),
        _request_payload(dimensions=[1]),
        _request_payload(case_context=[]),
        _request_payload(case_context=[{"state": "succeeded"}]),
        _request_payload(case_context=[{"case_id": ""}]),
        _request_payload(case_context=[{"case_id": "case-1"}] * 65),
        _request_payload(thread_id="x" * 257),
        _request_payload(budget_seconds=0),
        _request_payload(budget_seconds=-1),
        _request_payload(budget_seconds=True),
        _request_payload(budget_seconds="360"),
        _request_payload(budget_seconds=24 * 3600 + 1),
        "not-an-object",
    ],
)
def test_parse_judge_request_rejects_invalid_messages(payload: object) -> None:
    with pytest.raises(JudgeRequestError):
        parse_judge_request(payload)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        # 没有声明窗口：用 Studio 本地上限。
        (_request_payload(), JUDGE_TURN_TIMEOUT_SECONDS),
        # 窗口刚好等于上限 + 预留：仍然被上限压住。
        (
            _request_payload(
                budget_seconds=JUDGE_TURN_TIMEOUT_SECONDS + JUDGE_TURN_RESERVE_SECONDS
            ),
            JUDGE_TURN_TIMEOUT_SECONDS,
        ),
        # 更宽的窗口不会让回合跑得更久。
        (_request_payload(budget_seconds=1000.0), JUDGE_TURN_TIMEOUT_SECONDS),
        # 更窄的窗口按比例缩短，先把预留让出来。
        (
            _request_payload(budget_seconds=120.0),
            120.0 - JUDGE_TURN_RESERVE_SECONDS,
        ),
        (
            _request_payload(budget_seconds=40.0),
            40.0 - JUDGE_TURN_RESERVE_SECONDS,
        ),
    ],
)
def test_judge_turn_budget_fits_inside_the_declared_window(
    payload: dict[str, Any],
    expected: float,
) -> None:
    assert judge_turn_budget(parse_judge_request(payload)) == pytest.approx(expected)


def test_answer_judge_request_defaults_to_the_declared_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[float] = []

    async def fake_run_judge_turn(**kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        calls.append(float(kwargs["timeout_seconds"]))
        return _JUDGED_CASES, "thread-new"

    monkeypatch.setattr(judge_driver_module, "run_judge_turn", fake_run_judge_turn)

    answer_judge_request(
        parse_judge_request(_request_payload(budget_seconds=120)),
        endpoint="https://sandbox.invalid",
        cwd="/migration/output/veadk",
    )

    # 窗口 120s、预留 30s：回合最多只能跑 90s。
    assert calls[0] == pytest.approx(120.0 - JUDGE_TURN_RESERVE_SECONDS, abs=1.0)


def test_answer_judge_request_reports_a_slow_turn_as_a_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_judge_turn(**_kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        raise ToolTurnDeadlineExceeded("Codex 回合超出时间预算。")

    monkeypatch.setattr(judge_driver_module, "run_judge_turn", fake_run_judge_turn)

    response = answer_judge_request(
        parse_judge_request(_request_payload(thread_id="thread-old")),
        endpoint="https://sandbox.invalid",
        cwd="/migration/output/veadk",
    )

    assert response["ok"] is False
    # 慢回合与「app-server 用不了」必须给出不同的错误码。
    assert response["error"]["code"] == "judge_turn_timeout"  # type: ignore[index]


def test_answer_judge_request_returns_the_verdict_and_its_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_run_judge_turn(**kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        calls.append(kwargs)
        return _JUDGED_CASES, "thread-new"

    monkeypatch.setattr(judge_driver_module, "run_judge_turn", fake_run_judge_turn)

    response = answer_judge_request(
        parse_judge_request(_request_payload(thread_id="thread-old")),
        endpoint="https://sandbox.invalid",
        cwd="/migration/output/veadk",
        model="dola-seed",
        timeout_seconds=5,
    )

    assert response["ok"] is True
    assert response["cases"] == _JUDGED_CASES
    assert isinstance(response["cases"], list)
    assert response["thread_id"] == "thread-new"
    assert response["request_id"] == "batch-001-002-attempt-1"
    assert [call["thread_id"] for call in calls] == ["thread-old"]
    assert calls[0]["model"] == "dola-seed"
    assert calls[0]["cwd"] == "/migration/output/veadk"
    assert calls[0]["dimensions"] == ["semantic_fidelity", "output_contract"]
    assert calls[0]["case_context"][0]["case_id"] == "case-1"
    assert calls[0]["case_context"][1]["state"] == "failed"
    assert response["created_at"].endswith("Z")


def test_answer_judge_request_retries_a_dead_thread_on_a_fresh_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_run_judge_turn(**kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        calls.append(kwargs["thread_id"])
        if kwargs["thread_id"]:
            raise JudgeTurnUnavailable("thread is gone")
        return [], "thread-fresh"

    monkeypatch.setattr(judge_driver_module, "run_judge_turn", fake_run_judge_turn)

    response = answer_judge_request(
        parse_judge_request(_request_payload(thread_id="thread-old")),
        endpoint="https://sandbox.invalid",
        cwd="/migration/output/veadk",
        timeout_seconds=5,
    )

    assert calls == ["thread-old", ""]
    assert response["ok"] is True
    assert response["thread_id"] == "thread-fresh"


def test_answer_judge_request_starts_one_thread_when_none_is_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_run_judge_turn(**kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        calls.append(kwargs["thread_id"])
        return [], "thread-first"

    monkeypatch.setattr(judge_driver_module, "run_judge_turn", fake_run_judge_turn)

    response = answer_judge_request(
        parse_judge_request(_request_payload()),
        endpoint="https://sandbox.invalid",
        cwd="/migration/output/veadk",
        timeout_seconds=5,
    )

    assert calls == [""]
    assert response["thread_id"] == "thread-first"


def test_answer_judge_request_answers_a_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """回合自己抛出的传输错误也必须变成信封。

    否则 runner 收不到任何回应，只能一直等到自己的窗口结束再降级。
    """

    async def fake_run_judge_turn(**_kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        raise ToolTurnUnavailable("app-server websocket closed")

    monkeypatch.setattr(judge_driver_module, "run_judge_turn", fake_run_judge_turn)

    response = answer_judge_request(
        parse_judge_request(_request_payload()),
        endpoint="https://sandbox.invalid",
        cwd="/migration/output/veadk",
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "judge_turn_unavailable"  # type: ignore[index]


def test_answer_judge_request_answers_an_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_judge_turn(**_kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        raise ValueError("client bug")

    monkeypatch.setattr(judge_driver_module, "run_judge_turn", fake_run_judge_turn)

    response = answer_judge_request(
        parse_judge_request(_request_payload()),
        endpoint="https://sandbox.invalid",
        cwd="/migration/output/veadk",
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "judge_turn_unavailable"  # type: ignore[index]
    assert "client bug" in response["error"]["message"]  # type: ignore[index]


def test_answer_judge_request_returns_an_error_envelope_when_no_turn_delivers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_judge_turn(**_kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        raise JudgeTurnUnavailable("app-server refused the turn")

    monkeypatch.setattr(judge_driver_module, "run_judge_turn", fake_run_judge_turn)

    response = answer_judge_request(
        parse_judge_request(_request_payload(thread_id="thread-old")),
        endpoint="https://sandbox.invalid",
        cwd="/migration/output/veadk",
        timeout_seconds=5,
    )

    assert response["ok"] is False
    assert "cases" not in response
    assert response["error"]["code"] == "judge_turn_unavailable"  # type: ignore[index]
    assert "refused" in response["error"]["message"]  # type: ignore[index]
    assert response["thread_id"] == ""


def test_answer_judge_request_returns_an_error_envelope_without_a_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_judge_turn(**_kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        raise AssertionError("an exhausted budget must not start a turn")

    monkeypatch.setattr(judge_driver_module, "run_judge_turn", fake_run_judge_turn)

    response = answer_judge_request(
        parse_judge_request(_request_payload()),
        endpoint="https://sandbox.invalid",
        cwd="/migration/output/veadk",
        timeout_seconds=0,
    )

    assert response["ok"] is False
    # 预算已经用尽：这不是协议故障，而是这个回合没能在窗口内交付。
    assert response["error"]["code"] == "judge_turn_timeout"  # type: ignore[index]


def _driver(
    gateway: FakeGateway,
    monkeypatch: pytest.MonkeyPatch,
    handler: Any,
    *,
    enabled: bool = True,
) -> SandboxJudgeDriver:
    monkeypatch.setattr(judge_driver_module, "run_judge_turn", handler)
    return SandboxJudgeDriver(
        gateway,  # type: ignore[arg-type]
        cwd="/migration/output/veadk",
        enabled=lambda: enabled,
    )


def _write_request(gateway: FakeGateway, attempt: int = 1) -> str:
    request_path, _ = judge_channel_paths(EVALUATION_ROOT, attempt)
    gateway.files[request_path] = json.dumps(_request_payload()).encode("utf-8")
    return request_path


def test_drive_answers_one_request_once(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = FakeGateway()
    calls: list[Any] = []

    async def handler(**kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        calls.append(kwargs["thread_id"])
        return _JUDGED_CASES, "thread-1"

    driver = _driver(gateway, monkeypatch, handler)
    _write_request(gateway)
    _, response_path = judge_channel_paths(EVALUATION_ROOT, 1)

    driver.drive(_session(), evaluation_root=EVALUATION_ROOT, attempt=1)
    assert _wait_for(lambda: response_path in gateway.files)
    driver.drive(_session(), evaluation_root=EVALUATION_ROOT, attempt=1)
    time.sleep(0.05)

    assert calls == [""]
    response = json.loads(gateway.files[response_path])
    assert response["ok"] is True
    assert response["cases"] == _JUDGED_CASES
    assert gateway.puts == [response_path]


def test_drive_does_nothing_without_a_request(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = FakeGateway()

    async def handler(**_kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        raise AssertionError("no turn without a request")

    driver = _driver(gateway, monkeypatch, handler)

    driver.drive(_session(), evaluation_root=EVALUATION_ROOT, attempt=1)

    assert gateway.files == {}
    assert gateway.puts == []


def test_drive_ignores_a_malformed_request(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = FakeGateway()

    async def handler(**_kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        raise AssertionError("no turn for a malformed request")

    driver = _driver(gateway, monkeypatch, handler)
    request_path, _ = judge_channel_paths(EVALUATION_ROOT, 1)
    gateway.files[request_path] = b'{"schema_version": 99}'

    driver.drive(_session(), evaluation_root=EVALUATION_ROOT, attempt=1)

    assert gateway.puts == []


def test_drive_respects_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = FakeGateway()

    async def handler(**_kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        raise AssertionError("no turn while the channel is off")

    driver = _driver(gateway, monkeypatch, handler, enabled=False)
    _write_request(gateway)

    driver.drive(_session(), evaluation_root=EVALUATION_ROOT, attempt=1)

    assert gateway.puts == []


def test_drive_keeps_one_turn_in_flight_per_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeGateway()
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    async def handler(**kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        calls.append(kwargs["thread_id"])
        started.set()
        release.wait(5)
        return _JUDGED_CASES, "thread-1"

    driver = _driver(gateway, monkeypatch, handler)
    _write_request(gateway)

    driver.drive(_session(), evaluation_root=EVALUATION_ROOT, attempt=1)
    assert started.wait(5)
    driver.drive(_session(), evaluation_root=EVALUATION_ROOT, attempt=1)
    release.set()
    _, response_path = judge_channel_paths(EVALUATION_ROOT, 1)

    assert _wait_for(lambda: response_path in gateway.files)
    assert calls == [""]


def test_drive_replays_a_request_after_a_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeGateway()
    calls: list[str] = []

    async def handler(**kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        calls.append(kwargs["thread_id"])
        return _JUDGED_CASES, "thread-2"

    _write_request(gateway)
    first = _driver(gateway, monkeypatch, handler)
    first.drive(_session(), evaluation_root=EVALUATION_ROOT, attempt=1)
    _, response_path = judge_channel_paths(EVALUATION_ROOT, 1)
    assert _wait_for(lambda: response_path in gateway.files)
    gateway.files.pop(response_path)

    # 新的 Studio 进程没有任何内存状态：同一个请求会重放，而不是被丢弃。
    second = _driver(gateway, monkeypatch, handler)
    second.drive(_session(), evaluation_root=EVALUATION_ROOT, attempt=1)

    assert _wait_for(lambda: response_path in gateway.files)
    assert calls == ["", ""]


def test_drive_reports_a_failed_turn_as_an_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeGateway()

    async def handler(**_kwargs: Any) -> tuple[list[dict[str, Any]], str]:
        raise JudgeTurnUnavailable("app-server is down")

    driver = _driver(gateway, monkeypatch, handler)
    _write_request(gateway)

    driver.drive(_session(), evaluation_root=EVALUATION_ROOT, attempt=1)
    _, response_path = judge_channel_paths(EVALUATION_ROOT, 1)

    assert _wait_for(lambda: response_path in gateway.files)
    response = json.loads(gateway.files[response_path])
    assert response["ok"] is False
    assert response["error"]["code"] == "judge_turn_unavailable"
