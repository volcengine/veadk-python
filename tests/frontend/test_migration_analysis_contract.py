"""Acceptance of a Codex analysis judgement.

The contract exists to keep a shape drift from costing the analysis.  The regression
samples below are the exact payload shapes that a production migration turned into
"project is unsupported, no retry": the judgement was right and only its encoding was
off.  Acceptance has to land a usable result for those, and it must refuse a verdict
that cites nothing.
"""

from __future__ import annotations

import pytest

from frontend.server.migration.analysis_contract import (
    NEEDS_INPUT_KIND,
    RECOMMENDATION_KIND,
    UNSUPPORTED_KIND,
    AnalysisAcceptanceError,
    analysis_document_schema,
    analysis_tool_schema,
    build_analysis_result,
)
from frontend.server.migration.contracts import validate_analysis_result

_SHA = "d" * 64

_DETECTION: dict[str, object] = {
    "schema_version": 1,
    "files": {"count": 2, "listed": ["md5.txt", "template.yml"]},
    "documents": [
        {
            "path": "template.yml",
            "format": "yaml",
            "status": "parsed",
            "dsl": "dify",
            "signals": [],
        }
    ],
    "candidates": [
        {
            "id": "dify",
            "confidence": "high",
            "evidence": [
                {"path": "template.yml", "line": 5, "reason": "顶层 kind: app"},
                {
                    "path": "template.yml",
                    "line": 8,
                    "reason": "workflow.graph 含 3 个节点",
                },
            ],
        }
    ],
    "unreadable": [],
    "degraded": False,
    "degraded_reason": "",
}


def _degraded_detection() -> dict[str, object]:
    return {
        "schema_version": 1,
        "files": {"count": 0, "listed": []},
        "documents": [],
        "candidates": [],
        "unreadable": [],
        "degraded": True,
        "degraded_reason": "detection_missing",
    }


def _incident_recommendation(**overrides: object) -> dict[str, object]:
    """The judgement the production run produced, including its encoding drift."""
    payload: dict[str, object] = {
        "schema_version": "1",
        "status": "recommendation_ready",
        "attempt": 1,
        "input_sha256": _SHA,
        "summary": "ZIP 中只有一个 Dify 风格的工作流导出，按 Dify 方式迁移。",
        "frameworks": [
            {
                "id": "dify",
                "confidence": "high",
                "evidence": [
                    {"path": "template.yml", "line": "5", "reason": "kind: app"}
                ],
            }
        ],
        "recommended": {"framework": "dify", "entry": None, "reason": "无 Python 入口"},
        "entries": [],
        "boundary": {"include": ["template.yml"], "exclude": ["md5.txt"]},
        "assumptions": ["模型需在部署阶段配置"],
        "questions": [],
        "warnings": ["Start 节点无输入参数"],
    }
    payload.update(overrides)
    return payload


def test_the_production_judgement_lands_even_with_drifted_encoding() -> None:
    document, notes = build_analysis_result(
        RECOMMENDATION_KIND,
        _incident_recommendation(),
        attempt=1,
        input_sha256=_SHA,
        detection=_DETECTION,
    )

    assert validate_analysis_result(document) == document
    assert document["status"] == "recommendation_ready"
    assert document["recommended"]["framework"] == "dify"
    assert document["boundary"]["include"] == ["template.yml"]
    # A string line number is coerced rather than fatal.
    assert document["frameworks"][0]["evidence"][0]["line"] == 5
    # Studio owns the bookkeeping, so whatever the model echoed is replaced.
    assert document["input_sha256"] == _SHA
    assert notes


def test_a_bare_object_still_produces_a_usable_conclusion() -> None:
    document, notes = build_analysis_result(
        RECOMMENDATION_KIND,
        {"summary": "只有一个工作流导出文件。"},
        attempt=2,
        input_sha256=_SHA,
        detection=_DETECTION,
    )

    # The verified candidate is kept, and the missing recommendation is derived.
    assert [item["id"] for item in document["frameworks"]] == ["dify"]
    assert document["recommended"]["framework"] == "dify"
    assert document["boundary"]["include"] == ["项目内全部文件"]
    assert any("迁移范围" in note for note in notes)


def test_an_unusable_field_is_dropped_with_a_note_instead_of_failing() -> None:
    document, notes = build_analysis_result(
        RECOMMENDATION_KIND,
        {
            "summary": "摘要",
            "frameworks": "dify",
            "entries": [
                {"value": "agent.py:agent", "framework": "any", "evidence": "x"}
            ],
            "recommended": {"framework": "not-a-framework", "entry": "a.py:agent"},
        },
        attempt=1,
        input_sha256=_SHA,
        detection=_DETECTION,
    )

    assert any("frameworks" in note for note in notes)
    assert any("any" in note for note in notes)
    assert document["entries"] == []
    assert document["recommended"]["framework"] == "dify"
    # Dify never takes an entry, whatever the model sent.
    assert document["recommended"]["entry"] is None


def test_unknown_candidate_ids_are_dropped_and_evidence_without_a_path_too() -> None:
    document, notes = build_analysis_result(
        RECOMMENDATION_KIND,
        {
            "summary": "摘要",
            "frameworks": [
                {"id": "kubernetes", "confidence": "high", "evidence": []},
                {"id": "any", "confidence": "certain", "evidence": ["没有文件路径"]},
            ],
        },
        attempt=1,
        input_sha256=_SHA,
        detection=_degraded_detection(),
    )

    assert [item["id"] for item in document["frameworks"]] == ["any"]
    assert document["frameworks"][0]["confidence"] == "low"
    assert document["frameworks"][0]["evidence"] == []
    assert any("kubernetes" in note for note in notes)
    assert any("无法定位到文件" in note for note in notes)


def test_a_summary_is_the_one_thing_acceptance_insists_on() -> None:
    for payload in ({}, {"summary": "   "}, {"summary": 7}):
        with pytest.raises(AnalysisAcceptanceError) as error:
            build_analysis_result(
                RECOMMENDATION_KIND,
                payload,
                attempt=1,
                input_sha256=_SHA,
                detection=_DETECTION,
            )
        assert error.value.issues[0].path == "summary"


def test_needing_input_defaults_are_filled_but_questions_are_required() -> None:
    document, _ = build_analysis_result(
        NEEDS_INPUT_KIND,
        {"summary": "需要用户确认入口。", "questions": [{"prompt": "入口用哪个？"}]},
        attempt=1,
        input_sha256=_SHA,
        detection=_DETECTION,
    )

    assert document["status"] == "needs_input"
    assert document["questions"] == [
        {"id": "q1", "prompt": "入口用哪个？", "required": True}
    ]

    with pytest.raises(AnalysisAcceptanceError) as error:
        build_analysis_result(
            NEEDS_INPUT_KIND,
            {"summary": "需要用户确认入口。", "questions": []},
            attempt=1,
            input_sha256=_SHA,
            detection=_DETECTION,
        )
    assert error.value.issues[0].path == "questions"


def _unsupported(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "summary": (
            "ZIP 中只有一个工作流导出文件，没有可执行的 Agent 源码，无法恢复 Agent 行为，"
            "建议补充源码后重新发起迁移。"
        ),
        "evidence": [
            {"path": "template.yml", "line": 5, "reason": "只有一份 DSL 导出"},
            {"path": "md5.txt", "line": 1, "reason": "只有校验值"},
        ],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def test_an_unsupported_verdict_carries_its_evidence_to_the_page() -> None:
    document, _ = build_analysis_result(
        UNSUPPORTED_KIND,
        _unsupported(),
        attempt=1,
        input_sha256=_SHA,
        detection=_DETECTION,
    )

    assert document["status"] == "unsupported"
    assert document["recommended"] is None
    assert document["entries"] == []
    # 用户看不到工具参数，所以证据必须留在页面上。
    assert any("template.yml:5" in warning for warning in document["warnings"])


def test_a_probe_verdict_is_refused_without_an_evidence_trail() -> None:
    for payload in (
        {"summary": "结构测试。", "evidence": []},
        {
            "summary": "结构测试。",
            "evidence": [{"path": "template.yml", "reason": "x"}],
        },
        {"summary": "太短", "evidence": _unsupported()["evidence"]},
        {
            "summary": _unsupported()["summary"],
            "evidence": [
                {"path": "nope.py", "line": 1, "reason": "并不存在的文件"},
                {"path": "another.py", "line": 1, "reason": "也不存在"},
            ],
        },
    ):
        with pytest.raises(AnalysisAcceptanceError):
            build_analysis_result(
                UNSUPPORTED_KIND,
                payload,
                attempt=1,
                input_sha256=_SHA,
                detection=_DETECTION,
            )


def test_an_unknown_inventory_cannot_block_a_verdict() -> None:
    document, _ = build_analysis_result(
        UNSUPPORTED_KIND,
        _unsupported(
            evidence=[
                {"path": "somewhere/else.py", "line": 1, "reason": "检测器没有跑到"},
                {"path": "another.py", "line": 2, "reason": "同上"},
            ]
        ),
        attempt=1,
        input_sha256=_SHA,
        detection=_degraded_detection(),
    )

    assert document["status"] == "unsupported"


def test_the_documented_tool_schemas_only_ask_for_the_judgement() -> None:
    for kind in (RECOMMENDATION_KIND, NEEDS_INPUT_KIND, UNSUPPORTED_KIND):
        schema = analysis_tool_schema(kind)
        assert "schema_version" not in schema["properties"]
        assert "attempt" not in schema["properties"]
        assert "input_sha256" not in schema["properties"]
        assert schema["required"][0] == "summary"

    document_schema = analysis_document_schema()
    assert document_schema["required"] == ["status", "summary"]
    assert sorted(document_schema["properties"]) == [
        "assumptions",
        "boundary",
        "entries",
        "evidence",
        "frameworks",
        "questions",
        "recommended",
        "status",
        "summary",
        "warnings",
    ]
