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

"""Checks for the turn that closes one migration delivery."""

from __future__ import annotations

import asyncio

import pytest

from frontend.server.migration import delivery_turn
from frontend.server.migration.delivery_turn import (
    ARTIFACT_PATH,
    ARTIFACT_TOOL_NAME,
    DELIVERY_APP_SERVER_ENV,
    DELIVERY_TOOL_NAME,
    DeliveryContractError,
    DeliveryRecorder,
    PublishedArtifact,
    artifact_schema,
    delivery_app_server_enabled,
    delivery_schema,
    run_delivery_turn,
)

RUN_ID = "migration-v1-" + "a" * 32
ARTIFACT = PublishedArtifact(path=ARTIFACT_PATH, sha256="b" * 64, size=2048)


def _recorder(*, state: str = "succeeded_with_warnings") -> DeliveryRecorder:
    return DeliveryRecorder(
        run_id=RUN_ID,
        expected_state=state,
        publisher=lambda path: PublishedArtifact(
            path=path,
            sha256=ARTIFACT.sha256,
            size=ARTIFACT.size,
        ),
    )


def test_publish_reads_the_artifact_through_the_caller() -> None:
    seen: list[str] = []

    def publisher(path: str) -> PublishedArtifact:
        seen.append(path)
        return ARTIFACT

    recorder = DeliveryRecorder(
        run_id=RUN_ID,
        expected_state="succeeded",
        publisher=publisher,
    )

    result = recorder.publish({"path": ARTIFACT_PATH})

    assert seen == [ARTIFACT_PATH]
    assert result.success is True
    assert ARTIFACT.sha256 in result.text
    assert recorder.artifact == ARTIFACT


def test_publish_rejects_a_path_the_contract_did_not_choose() -> None:
    recorder = _recorder()

    result = recorder.publish({"path": "delivery/migration-result.zip"})

    assert result.success is False
    assert recorder.artifact is None


def test_publish_reports_an_artifact_that_disagrees_with_the_manifest() -> None:
    def publisher(path: str) -> PublishedArtifact:
        del path
        raise DeliveryContractError("产物字节与迁移产物清单不一致")

    recorder = DeliveryRecorder(
        run_id=RUN_ID,
        expected_state="succeeded",
        publisher=publisher,
    )

    result = recorder.publish({"path": ARTIFACT_PATH})

    assert result.success is False
    assert "不一致" in result.text
    assert recorder.artifact is None


def test_a_successful_delivery_must_publish_its_artifact_first() -> None:
    recorder = _recorder()

    rejected = recorder.report(
        {"state": "succeeded_with_warnings", "message": "迁移已完成", "warnings": []}
    )
    assert rejected.success is False
    assert recorder.verdict is None

    recorder.publish({"path": ARTIFACT_PATH})
    accepted = recorder.report(
        {"state": "succeeded_with_warnings", "message": "迁移已完成", "warnings": []}
    )

    assert accepted.success is True
    assert recorder.ready is True
    assert recorder.verdict == {
        "state": "succeeded_with_warnings",
        "message": "迁移已完成",
        "warnings": [],
    }


def test_the_turn_cannot_change_the_state_the_sandbox_published() -> None:
    recorder = _recorder(state="failed")

    result = recorder.report(
        {"state": "succeeded", "message": "看起来没问题", "warnings": []}
    )

    assert result.success is False
    assert "已经确定为 failed" in result.text
    assert recorder.verdict is None


def test_a_failed_delivery_reports_its_reason_without_an_artifact() -> None:
    recorder = _recorder(state="failed")

    accepted = recorder.report(
        {
            "state": "failed",
            "message": "校验失败：assistant/agent.py 缺少 before_model_callback。",
            "warnings": [],
        }
    )

    assert accepted.success is True
    assert recorder.verdict["state"] == "failed"
    assert recorder.artifact is None


def test_a_failed_delivery_cannot_publish_an_artifact() -> None:
    recorder = _recorder(state="failed")
    recorder.publish({"path": ARTIFACT_PATH})

    result = recorder.report(
        {"state": "failed", "message": "迁移没有生成产物", "warnings": []}
    )

    assert result.success is False
    assert recorder.verdict is None


@pytest.mark.parametrize(
    "arguments",
    [
        {"state": "succeeded", "message": "好", "warnings": []},
        {"state": "succeeded", "message": None, "warnings": []},
        {"state": "succeeded", "message": "产物已经生成", "warnings": "无"},
        {"state": "succeeded", "message": "产物已经生成", "warnings": [1]},
        {"state": "succeeded", "message": "产物已经生成", "warnings": [], "score": 1},
    ],
)
def test_a_malformed_report_is_rejected(arguments: dict[str, object]) -> None:
    recorder = _recorder(state="succeeded")
    recorder.publish({"path": ARTIFACT_PATH})

    result = recorder.report(arguments)

    assert result.success is False
    assert recorder.verdict is None


def test_a_report_without_warnings_is_read_as_no_warnings() -> None:
    recorder = _recorder(state="succeeded")
    recorder.publish({"path": ARTIFACT_PATH})

    result = recorder.report({"state": "succeeded", "message": "迁移产物已生成"})

    assert result.success is True
    assert recorder.verdict["warnings"] == []


def test_publish_rejects_arguments_the_schema_does_not_describe() -> None:
    recorder = _recorder()

    result = recorder.publish({"path": ARTIFACT_PATH, "sha256": "b" * 64})

    assert result.success is False
    assert recorder.artifact is None


def test_warnings_are_trimmed_and_bounded() -> None:
    recorder = _recorder(state="succeeded")
    recorder.publish({"path": ARTIFACT_PATH})

    result = recorder.report(
        {
            "state": "succeeded",
            "message": "迁移产物已生成",
            "warnings": ["  APM 未配置  ", "", "x" * 900],
        }
    )

    assert result.success is True
    warnings = recorder.verdict["warnings"]
    assert warnings[0] == "APM 未配置"
    assert len(warnings) == 2
    assert len(warnings[1]) == 400


def test_the_delivery_switch_is_on_unless_it_is_switched_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DELIVERY_APP_SERVER_ENV, raising=False)
    assert delivery_app_server_enabled() is True

    monkeypatch.setenv(DELIVERY_APP_SERVER_ENV, "0")
    assert delivery_app_server_enabled() is False


def test_the_schemas_describe_what_the_handlers_accept() -> None:
    artifact = artifact_schema()
    assert artifact["required"] == ["path"]
    assert artifact["additionalProperties"] is False

    delivery = delivery_schema()
    assert delivery["required"] == ["state", "message", "warnings"]
    assert set(delivery["properties"]["state"]["enum"]) == {
        "succeeded",
        "succeeded_with_warnings",
        "partial",
        "failed",
    }


def test_the_verdict_schema_offers_only_the_settled_state() -> None:
    """只给一个选项：模型在 succeeded / succeeded_with_warnings 之间猜错就等于烧掉一次收尾回合。"""
    narrowed = delivery_schema("succeeded")
    state = narrowed["properties"]["state"]
    assert state["enum"] == ["succeeded"]
    assert "succeeded" in state["description"]

    unknown = delivery_schema("mystery")
    assert unknown["properties"]["state"]["enum"] == sorted(
        delivery_turn.DELIVERY_STATES
    )

    assert delivery_schema()["properties"]["state"]["enum"] == sorted(
        delivery_turn.DELIVERY_STATES
    )


def test_the_turn_registers_both_tools_and_returns_the_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    async def fake_run_tool_turn(**kwargs: object) -> None:
        calls.update(kwargs)
        handler = kwargs["handler"]
        extra_tools = kwargs["extra_tools"]
        artifact_tool = extra_tools[0]
        assert artifact_tool.name == ARTIFACT_TOOL_NAME
        artifact_tool.handler({"path": ARTIFACT_PATH})
        handler(
            {
                "state": "succeeded_with_warnings",
                "message": "迁移产物已生成，有 1 条提示。",
                "warnings": ["APM 未配置"],
            }
        )
        assert kwargs["has_result"]() is True

    monkeypatch.setattr(delivery_turn, "run_tool_turn", fake_run_tool_turn)

    report = asyncio.run(
        run_delivery_turn(
            endpoint="https://sandbox.invalid",
            prompt="prompt",
            cwd="/home/gem/.studio/migration/v1/work/delivery",
            run_id=RUN_ID,
            expected_state="succeeded_with_warnings",
            publisher=lambda path: ARTIFACT,
            timeout_seconds=30.0,
        )
    )

    assert calls["tool_name"] == DELIVERY_TOOL_NAME
    assert calls["cwd"] == "/home/gem/.studio/migration/v1/work/delivery"
    assert report == {
        "schema_version": 1,
        "run_id": RUN_ID,
        "driver": "app-server",
        "state": "succeeded_with_warnings",
        "message": "迁移产物已生成，有 1 条提示。",
        "warnings": ["APM 未配置"],
        "artifact": {
            "path": ARTIFACT_PATH,
            "sha256": ARTIFACT.sha256,
            "size": ARTIFACT.size,
        },
        "created_at": report["created_at"],
    }
    assert report["created_at"].endswith("Z")


def test_a_turn_without_a_verdict_returns_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_tool_turn(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(delivery_turn, "run_tool_turn", fake_run_tool_turn)

    report = asyncio.run(
        run_delivery_turn(
            endpoint="https://sandbox.invalid",
            prompt="prompt",
            cwd="/home/gem/.studio/migration/v1/work/delivery",
            run_id=RUN_ID,
            expected_state="failed",
            publisher=lambda path: ARTIFACT,
            timeout_seconds=30.0,
        )
    )

    assert report is None


def test_an_unavailable_app_server_becomes_a_delivery_turn_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_tool_turn(**_kwargs: object) -> None:
        raise delivery_turn.ToolTurnUnavailable("app-server 不可用")

    monkeypatch.setattr(delivery_turn, "run_tool_turn", fake_run_tool_turn)

    with pytest.raises(delivery_turn.DeliveryTurnUnavailable):
        asyncio.run(
            run_delivery_turn(
                endpoint="https://sandbox.invalid",
                prompt="prompt",
                cwd="/home/gem/.studio/migration/v1/work/delivery",
                run_id=RUN_ID,
                expected_state="failed",
                publisher=lambda path: ARTIFACT,
                timeout_seconds=30.0,
            )
        )
