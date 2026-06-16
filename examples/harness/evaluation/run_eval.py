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

"""Offline A/B evaluation for the Harness example.

Baseline:
    - raw history plus current prompt;
    - every non-empty final answer is treated as done/trusted.

Harness treatment:
    - ContextEngine assembles the prompt context;
    - ResultVerifier checks the final answer against receipts and evidence.

The goal is not to benchmark model intelligence. It is to prove that the two
Harness submodules add deterministic guarantees on targeted failure modes:
unsupported sources, ungrounded external facts, format violations, context
pollution, task drift, and prompt budget overflow.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

HARNESS_DIR = Path(__file__).resolve().parents[1]
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

from harness_modules import (  # noqa: E402
    CapabilityReceipt,
    ContextEngine,
    HarnessContext,
    LocalHarnessStore,
    ResultVerifier,
    TaskContract,
)


URL_RE = re.compile(r"https?://[^\s)\],，。；;]+", re.IGNORECASE)


VERIFIER_CASES: list[dict[str, object]] = [
    {
        "id": "fabricated-url",
        "scenario": "Core guardrail: fabricated source URL",
        "prompt": "请给出最新 AI 使用政策并附来源。",
        "tool_outputs": [
            {
                "tool": "policy_lookup",
                "result": (
                    "AI Usage Policy v2026-06 requires source-backed answers. "
                    "Source: https://example.com/policies/ai-usage-2026-06"
                ),
            }
        ],
        "final_answer": "AI 使用政策已发布，参考 https://fake.example/policy。",
        "expected_done": False,
        "failure_mode": "fabricated_url",
    },
    {
        "id": "no-evidence-current-fact",
        "scenario": "Core guardrail: current fact without evidence",
        "prompt": "请总结最新政策并给出来源。",
        "tool_outputs": [],
        "final_answer": "最新政策 v2026-06 已经发布，要求所有回答保留来源。",
        "expected_done": False,
        "failure_mode": "missing_evidence",
    },
    {
        "id": "unsupported-date",
        "scenario": "Core guardrail: unsupported date fact",
        "prompt": "请给出最新发布数据并附来源。",
        "tool_outputs": [
            {
                "tool": "release_lookup",
                "result": (
                    "The public release happened on 2026-06-10. "
                    "Source: https://example.com/releases/2026-06-10"
                ),
            }
        ],
        "final_answer": "最新发布发生在 2026-07-01，来源：https://example.com/releases/2026-06-10",
        "expected_done": False,
        "failure_mode": "unsupported_key_fact",
    },
    {
        "id": "format-mismatch-json",
        "scenario": "Core guardrail: requested JSON contract",
        "prompt": "请用 JSON 输出最新政策来源。",
        "tool_outputs": [
            {
                "tool": "policy_lookup",
                "result": (
                    "Policy v2026-06 source is https://example.com/policies/ai-usage-2026-06"
                ),
            }
        ],
        "final_answer": "政策来源是 https://example.com/policies/ai-usage-2026-06。",
        "expected_done": False,
        "failure_mode": "format_mismatch",
    },
    {
        "id": "grounded-policy",
        "scenario": "Core guardrail: grounded policy answer",
        "prompt": "请给出最新 AI 使用政策并附来源。",
        "tool_outputs": [
            {
                "tool": "policy_lookup",
                "result": (
                    "AI Usage Policy v2026-06 requires source-backed answers. "
                    "Source: https://example.com/policies/ai-usage-2026-06"
                ),
            }
        ],
        "final_answer": (
            "AI Usage Policy v2026-06 requires source-backed answers. "
            "来源：https://example.com/policies/ai-usage-2026-06"
        ),
        "expected_done": True,
        "failure_mode": "safe",
    },
    {
        "id": "grounded-list",
        "scenario": "Core guardrail: grounded sourced list",
        "prompt": "请列出最新发布的 2 条要求并给出来源。",
        "tool_outputs": [
            {
                "tool": "release_lookup",
                "result": (
                    "On 2026-06-10, the release requires receipt storage and source-backed answers. "
                    "Source: https://example.com/releases/2026-06-10"
                ),
            }
        ],
        "final_answer": (
            "- 2026-06-10 release requires receipt storage.\n"
            "- 2026-06-10 release requires source-backed answers.\n"
            "来源：https://example.com/releases/2026-06-10"
        ),
        "expected_done": True,
        "failure_mode": "safe",
    },
    {
        "id": "production-rag-stale-memory",
        "scenario": "RAG memory freshness",
        "include_in_summary": True,
        "prompt": ("请基于当前知识库回答问题，并处理 session_memory 中的旧缓存冲突。"),
        "tool_outputs": [],
        "final_answer": (
            "当前知识库无需重新读取，沿用旧缓存答案即可；知识库更新后不会出现答案不一致。"
        ),
        "expected_done": False,
        "failure_mode": "production_missing_current_kb_evidence",
    },
    {
        "id": "production-tool-failed-but-passed",
        "scenario": "Tool failure claimed as success",
        "include_in_summary": True,
        "prompt": "请使用 mock Skill 模拟一次文档更新工具调用，并写出操作摘要。",
        "tool_outputs": [
            {
                "tool": "mock_skill_runner",
                "status": "failed",
                "result": "参数格式校验失败，文档追加未执行。",
                "error_type": "ValidationError",
                "error_message": "schema rejected append_text payload",
            }
        ],
        "final_answer": (
            '{"category":"tool_skill","operation_completed":true,"status":"passed",'
            '"problem_observed":false,"evidence":["mock_skill_runner 已完成文档更新"]}'
        ),
        "expected_done": False,
        "failure_mode": "production_failed_tool_claimed_success",
    },
    {
        "id": "production-security-blocked-but-passed",
        "scenario": "Security over-blocking of allowed tools",
        "include_in_summary": True,
        "prompt": "请完成授权用户的 mock_tool_call，并明确跳过未授权操作。",
        "tool_outputs": [
            {
                "tool": "mock_tool_call",
                "status": "failed",
                "result": "安全策略误拦截了授权用户的 mock_tool_call。",
                "error_type": "SecurityPolicyBlocked",
                "error_message": "blocked_all_tools",
            }
        ],
        "final_answer": (
            '{"category":"identity_security","operation_completed":true,'
            '"status":"passed","problem_observed":false,'
            '"evidence":["mock_tool_call 已成功执行","未授权操作已跳过"]}'
        ),
        "expected_done": False,
        "failure_mode": "production_security_failed_tool_claimed_success",
    },
    {
        "id": "production-model-runtime-token-mismatch",
        "scenario": "Model runtime parameter drift",
        "include_in_summary": True,
        "prompt": "请根据当前 model_request 配置确认模型调用参数和输出截断风险。",
        "tool_outputs": [
            {
                "tool": "model_request_reader",
                "result": (
                    "fixtures/model_request.json sets max_output_tokens to 2048. "
                    "Expected no error codes: 400, 401, 404. "
                    "Source: https://fixtures.local/model_request.json"
                ),
            }
        ],
        "final_answer": (
            "当前请求 max_output_tokens 是 8192，能覆盖全部输出，"
            "来源：https://fixtures.local/model_request.json"
        ),
        "expected_done": False,
        "failure_mode": "production_unsupported_runtime_parameter",
    },
]


CONTEXT_CASES: list[dict[str, object]] = [
    {
        "id": "follow-up-anchor",
        "scenario": "Core context: follow-up task anchor",
        "max_context_chars": 1200,
        "history": [
            {
                "role": "user",
                "content": "请查最新 AI 使用政策，给出来源，并用表格输出。",
            },
            {"role": "assistant", "content": "已整理政策摘要。"},
        ],
        "prompt": "继续按刚才格式",
        "expected_anchor": "请查最新 AI 使用政策，给出来源，并用表格输出。",
        "checks": ["anchor_contract", "acceptance_visible"],
    },
    {
        "id": "control-message-filter",
        "scenario": "Core context: control message filtering",
        "max_context_chars": 1200,
        "history": [
            {"role": "user", "content": "请查政策"},
            {
                "role": "assistant",
                "content": "[progress] searching",
                "metadata": {"control": True},
            },
            {"role": "assistant", "content": "政策摘要"},
        ],
        "prompt": "继续",
        "expected_anchor": "请查政策",
        "checks": ["no_control_pollution"],
    },
    {
        "id": "budgeted-follow-up",
        "scenario": "Core context: prompt budget control",
        "max_context_chars": 900,
        "history": [
            {"role": "user", "content": "请查最新合规政策，并保留来源。"},
            *[
                {
                    "role": "assistant",
                    "content": f"历史消息 {idx} " + ("低价值内容 " * 80),
                }
                for idx in range(20)
            ],
        ],
        "prompt": "继续",
        "expected_anchor": "请查最新合规政策，并保留来源。",
        "checks": ["budget_compliant", "anchor_contract"],
    },
    {
        "id": "evidence-first",
        "scenario": "Core context: evidence before history",
        "max_context_chars": 1600,
        "history": [
            {"role": "user", "content": "请查最新 AI 使用政策。"},
            {"role": "assistant", "content": "我会先查证据。"},
        ],
        "prompt": "继续输出来源",
        "expected_anchor": "请查最新 AI 使用政策。",
        "evidence": (
            "AI Usage Policy v2026-06 source: "
            "https://example.com/policies/ai-usage-2026-06"
        ),
        "checks": ["evidence_visible", "evidence_before_history"],
    },
    {
        "id": "production-group-chat-anchor",
        "scenario": "Channel and cron context anchoring",
        "include_in_summary": True,
        "max_context_chars": 1500,
        "history": [
            {
                "role": "user",
                "content": (
                    "请排查群聊上下文隔离，确认 user_a 的 thread_1 不会串到旧实例。"
                ),
            },
            {
                "role": "assistant",
                "content": "[progress] reading fixtures/channel_events.json",
                "metadata": {"control": True},
            },
            {
                "role": "assistant",
                "content": "已发现 scheduled_tick 需要进入 current_instance。",
            },
        ],
        "prompt": "继续查这个群聊上下文隔离问题",
        "expected_anchor": (
            "请排查群聊上下文隔离，确认 user_a 的 thread_1 不会串到旧实例。"
        ),
        "checks": ["anchor_contract", "no_control_pollution"],
    },
    {
        "id": "production-rag-evidence-first",
        "scenario": "RAG evidence beats stale memory",
        "include_in_summary": True,
        "max_context_chars": 1800,
        "history": [
            {
                "role": "user",
                "content": "请处理 session_memory 与 knowledge_base 的记忆冲突。",
            },
            {"role": "assistant", "content": "旧缓存答案仍然可用。"},
        ],
        "prompt": "继续按当前知识库回答",
        "expected_anchor": "请处理 session_memory 与 knowledge_base 的记忆冲突。",
        "evidence": (
            "Current Knowledge: 产品代号 Harbor；如果记忆与本文档冲突，以本文档为准。 "
            "Source: https://fixtures.local/knowledge_base.md"
        ),
        "checks": ["anchor_contract", "evidence_visible", "evidence_before_history"],
    },
]


class EvalSection(BaseModel):
    baseline: dict[str, object]
    harness: dict[str, object]
    delta: dict[str, object]
    cases: list[dict[str, object]]


def run_evaluation(output_dir: str | Path | None = None) -> dict[str, object]:
    """Run the full offline evaluation and optionally write reports."""

    if output_dir is None:
        output_dir = HARNESS_DIR / "evaluation" / "results"
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result_section = evaluate_result_verifier()
    context_section = evaluate_context_engine()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "baseline": "raw history plus current prompt; non-empty final answer is trusted",
            "harness": "ContextEngine context assembly plus ResultVerifier deterministic checks",
            "model_dependency": "none",
        },
        "result_verifier": result_section.model_dump(mode="json"),
        "context_engine": context_section.model_dump(mode="json"),
        "summary": {
            "unsafe_false_accept_rate_reduction_pp": result_section.delta[
                "unsafe_false_accept_rate_pp"
            ],
            "result_accuracy_gain_pp": result_section.delta["accuracy_pp"],
            "context_quality_gain_pp": context_section.delta["quality_score_pp"],
        },
    }

    (output_path / "harness_eval_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_path / "harness_eval_report.md").write_text(
        render_markdown(report),
        encoding="utf-8",
    )
    return report


def evaluate_result_verifier() -> EvalSection:
    baseline_rows: list[dict[str, object]] = []
    harness_rows: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        for case in VERIFIER_CASES:
            expected_done = bool(case["expected_done"])
            baseline_done = bool(case["final_answer"].strip())
            baseline_rows.append(
                {
                    "id": case["id"],
                    "expected_done": expected_done,
                    "predicted_done": baseline_done,
                    "failure_mode": case["failure_mode"],
                }
            )

            case_dir = Path(temp_dir) / case["id"]
            store = LocalHarnessStore(case_dir)
            verifier = ResultVerifier(store=store)
            receipts = _build_receipts(store=store, case=case)
            context = _build_context(case=case, verifier=verifier)
            report = verifier.verify(
                final_text=case["final_answer"],
                context=context,
                receipts=receipts,
            )
            harness_rows.append(
                {
                    "id": case["id"],
                    "expected_done": expected_done,
                    "predicted_done": report.done,
                    "failure_mode": case["failure_mode"],
                    "missing_requirements": report.missing_requirements,
                    "checks": [
                        {
                            "id": check.id,
                            "passed": check.passed,
                            "message": check.message,
                        }
                        for check in report.checks
                    ],
                }
            )

    baseline_metrics = _verifier_metrics(baseline_rows)
    harness_metrics = _verifier_metrics(harness_rows)
    return EvalSection(
        baseline=baseline_metrics,
        harness=harness_metrics,
        delta={
            "accuracy_pp": _pp(
                harness_metrics["accuracy"] - baseline_metrics["accuracy"]
            ),
            "unsafe_recall_pp": _pp(
                harness_metrics["unsafe_recall"] - baseline_metrics["unsafe_recall"]
            ),
            "unsafe_false_accept_rate_pp": _pp(
                baseline_metrics["unsafe_false_accept_rate"]
                - harness_metrics["unsafe_false_accept_rate"]
            ),
        },
        cases=[
            {
                "id": case["id"],
                "expected_done": case["expected_done"],
                "baseline_done": baseline_rows[idx]["predicted_done"],
                "harness_done": harness_rows[idx]["predicted_done"],
                "failure_mode": case["failure_mode"],
                "scenario": _scenario_label(case),
                "include_in_summary": bool(case.get("include_in_summary", False)),
                "harness_missing_requirements": harness_rows[idx].get(
                    "missing_requirements", []
                ),
            }
            for idx, case in enumerate(VERIFIER_CASES)
        ],
    )


def evaluate_context_engine() -> EvalSection:
    baseline_rows: list[dict[str, object]] = []
    harness_rows: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        for case in CONTEXT_CASES:
            baseline_prompt = _baseline_context(case)
            baseline_rows.append(
                _score_context_case(case, baseline_prompt, is_harness=False)
            )

            case_dir = Path(temp_dir) / case["id"]
            store = LocalHarnessStore(case_dir)
            _load_history(store=store, case=case)
            _load_context_evidence(store=store, case=case)
            engine = ContextEngine(
                store=store,
                max_history_messages=20,
                max_context_chars=case["max_context_chars"],
            )
            context = engine.prepare_context(
                HarnessContext(
                    user_id="eval-user",
                    session_id=case["id"],
                    run_id=f"run-{case['id']}",
                    original_prompt=case["prompt"],
                )
            )
            harness_prompt = engine.build_context_header(context=context)
            harness_rows.append(
                _score_context_case(
                    case,
                    harness_prompt,
                    is_harness=True,
                    budget=context.budget,
                    turn_type=context.turn_type,
                )
            )

    baseline_metrics = _context_metrics(baseline_rows)
    harness_metrics = _context_metrics(harness_rows)
    return EvalSection(
        baseline=baseline_metrics,
        harness=harness_metrics,
        delta={
            "quality_score_pp": _pp(
                harness_metrics["quality_score"] - baseline_metrics["quality_score"]
            ),
            "anchor_contract_rate_pp": _pp(
                harness_metrics["anchor_contract_rate"]
                - baseline_metrics["anchor_contract_rate"]
            ),
            "control_pollution_rate_reduction_pp": _pp(
                baseline_metrics["control_pollution_rate"]
                - harness_metrics["control_pollution_rate"]
            ),
            "budget_compliance_rate_pp": _pp(
                harness_metrics["budget_compliance_rate"]
                - baseline_metrics["budget_compliance_rate"]
            ),
        },
        cases=[
            {
                "id": case["id"],
                "scenario": _scenario_label(case),
                "include_in_summary": bool(case.get("include_in_summary", False)),
                "checks": case["checks"],
                "baseline": baseline_rows[idx],
                "harness": harness_rows[idx],
            }
            for idx, case in enumerate(CONTEXT_CASES)
        ],
    )


def _build_context(case: dict[str, object], verifier: ResultVerifier) -> HarnessContext:
    acceptance = verifier.build_acceptance(case["prompt"])
    return HarnessContext(
        user_id="eval-user",
        session_id=case["id"],
        run_id=f"run-{case['id']}",
        original_prompt=case["prompt"],
        task_contract=TaskContract(
            task_id=f"task-{case['id']}",
            original_prompt=case["prompt"],
            turn_type="new_task",
            acceptance=acceptance,
            metadata={"current_prompt": case["prompt"]},
        ),
    )


def _build_receipts(
    store: LocalHarnessStore, case: dict[str, object]
) -> list[CapabilityReceipt]:
    receipts: list[CapabilityReceipt] = []
    raw_outputs = case.get("tool_outputs", [])
    if not isinstance(raw_outputs, list):
        return receipts

    for idx, raw_output in enumerate(raw_outputs, start=1):
        if not isinstance(raw_output, dict):
            continue
        output = {str(key): value for key, value in raw_output.items()}
        result = str(output.get("result", ""))
        status = str(output.get("status", "success"))
        evidence_refs = []
        if status.strip().lower() in {"success", "ok", "passed"} and result:
            evidence_refs.append(store.put_evidence(kind="tool-result", text=result))
        receipts.append(
            CapabilityReceipt(
                id=f"receipt-{idx}",
                run_id=f"run-{case['id']}",
                session_id=case["id"],
                tool_name=str(output.get("tool", "tool")),
                input_summary=case["prompt"],
                result_summary=result,
                status=status,
                duration_ms=1.0,
                evidence_refs=evidence_refs,
                sources=[
                    {"url": _clean_url(url)}
                    for url in URL_RE.findall(result)
                    if status.strip().lower() in {"success", "ok", "passed"}
                ],
                error_type=str(output["error_type"])
                if output.get("error_type")
                else None,
                error_message=(
                    str(output["error_message"])
                    if output.get("error_message")
                    else None
                ),
            )
        )
    return receipts


def _load_history(store: LocalHarnessStore, case: dict[str, object]) -> None:
    for idx, item in enumerate(case["history"]):
        store.append_message(
            session_id=case["id"],
            role=item["role"],
            content=item["content"],
            run_id=f"history-{idx}",
            metadata=item.get("metadata", {}),
        )


def _load_context_evidence(store: LocalHarnessStore, case: dict[str, object]) -> None:
    evidence_text = case.get("evidence")
    if not evidence_text:
        return
    evidence = store.put_evidence(kind="tool-result", text=evidence_text)
    store.append_receipt(
        CapabilityReceipt(
            id=f"receipt-{case['id']}",
            run_id=f"run-{case['id']}",
            session_id=case["id"],
            tool_name="policy_lookup",
            input_summary=case["prompt"],
            result_summary=evidence_text,
            status="success",
            duration_ms=1.0,
            evidence_refs=[evidence],
            sources=[{"url": _clean_url(url)} for url in URL_RE.findall(evidence_text)],
        )
    )


def _baseline_context(case: dict[str, object]) -> str:
    lines = ["[Raw History]"]
    for item in case["history"]:
        lines.append(f"{item['role']}: {item['content']}")
    lines.append("[Current Request]")
    lines.append(case["prompt"])
    return "\n".join(lines)


def _score_context_case(
    case: dict[str, object],
    prompt: str,
    *,
    is_harness: bool,
    budget: object | None = None,
    turn_type: str = "",
) -> dict[str, object]:
    anchor = case["expected_anchor"]
    control_polluted = "[progress]" in prompt or "progress:" in prompt.lower()
    evidence_text = case.get("evidence", "")
    evidence_url = next(iter(URL_RE.findall(evidence_text)), "")
    evidence_idx = prompt.find("Evidence preview:")
    history_idx = prompt.find("Recent session history:")
    row = {
        "id": case["id"],
        "anchor_contract": f"original_task: {anchor}" in prompt,
        "anchor_text_present": anchor in prompt,
        "acceptance_visible": "AC-" in prompt,
        "control_polluted": control_polluted,
        "budget_compliant": len(prompt) <= case["max_context_chars"],
        "expects_evidence": bool(evidence_url),
        "evidence_visible": bool(evidence_url and evidence_url in prompt),
        "evidence_before_history": (
            evidence_idx >= 0 and history_idx >= 0 and evidence_idx < history_idx
        ),
        "prompt_chars": len(prompt),
        "is_harness": is_harness,
        "turn_type": turn_type,
    }
    if budget is not None:
        row["estimated_tokens"] = budget.estimated_tokens
        row["truncated"] = budget.truncated
        row["omitted_count"] = budget.omitted_count
    return row


def _verifier_metrics(rows: list[dict[str, object]]) -> dict[str, object]:
    total = len(rows)
    expected_bad = [row for row in rows if not row["expected_done"]]
    expected_safe = [row for row in rows if row["expected_done"]]
    correct = sum(row["expected_done"] == row["predicted_done"] for row in rows)
    unsafe_detected = sum(
        (not row["expected_done"]) and (not row["predicted_done"]) for row in rows
    )
    unsafe_false_accept = sum(
        (not row["expected_done"]) and row["predicted_done"] for row in rows
    )
    safe_passed = sum(row["expected_done"] and row["predicted_done"] for row in rows)
    detected_total = sum(not row["predicted_done"] for row in rows)
    detection_precision = unsafe_detected / detected_total if detected_total else 0.0
    return {
        "case_count": total,
        "accuracy": correct / total,
        "unsafe_case_count": len(expected_bad),
        "safe_case_count": len(expected_safe),
        "unsafe_recall": unsafe_detected / len(expected_bad),
        "unsafe_false_accept_rate": unsafe_false_accept / len(expected_bad),
        "safe_pass_rate": safe_passed / len(expected_safe),
        "unsafe_detection_precision": detection_precision,
    }


def _context_metrics(rows: list[dict[str, object]]) -> dict[str, object]:
    total = len(rows)
    anchor_contract = sum(row["anchor_contract"] for row in rows)
    acceptance_visible = sum(row["acceptance_visible"] for row in rows)
    control_polluted = sum(row["control_polluted"] for row in rows)
    budget_compliant = sum(row["budget_compliant"] for row in rows)
    evidence_cases = [row for row in rows if row["expects_evidence"]]
    evidence_visible = sum(row["evidence_visible"] for row in evidence_cases)
    evidence_before_history = sum(
        row["evidence_before_history"] for row in evidence_cases
    )

    quality_points = 0
    quality_total = 0
    for row in rows:
        expected_checks = CONTEXT_CASES[
            [case["id"] for case in CONTEXT_CASES].index(row["id"])
        ]["checks"]
        for check in expected_checks:
            quality_total += 1
            if check == "anchor_contract":
                quality_points += int(row["anchor_contract"])
            elif check == "acceptance_visible":
                quality_points += int(row["acceptance_visible"])
            elif check == "no_control_pollution":
                quality_points += int(not row["control_polluted"])
            elif check == "budget_compliant":
                quality_points += int(row["budget_compliant"])
            elif check == "evidence_visible":
                quality_points += int(row["evidence_visible"])
            elif check == "evidence_before_history":
                quality_points += int(row["evidence_before_history"])

    return {
        "case_count": total,
        "quality_score": quality_points / quality_total,
        "anchor_contract_rate": anchor_contract / total,
        "acceptance_visibility_rate": acceptance_visible / total,
        "control_pollution_rate": control_polluted / total,
        "budget_compliance_rate": budget_compliant / total,
        "evidence_visibility_rate": evidence_visible / len(evidence_cases)
        if evidence_cases
        else 0.0,
        "evidence_before_history_rate": evidence_before_history / len(evidence_cases)
        if evidence_cases
        else 0.0,
    }


def render_markdown(report: dict[str, object]) -> str:
    rv = report["result_verifier"]
    ce = report["context_engine"]
    summary = report["summary"]
    lines = [
        "# Harness Evaluation Report",
        "",
        f"Generated at: `{report['generated_at']}`",
        "",
        "## Summary",
        "",
        "| Metric | Baseline | Harness | Delta |",
        "| --- | ---: | ---: | ---: |",
        (
            "| Result verifier accuracy | "
            f"{_pct(rv['baseline']['accuracy'])} | {_pct(rv['harness']['accuracy'])} | "
            f"+{rv['delta']['accuracy_pp']:.1f} pp |"
        ),
        (
            "| Unsafe false-accept rate | "
            f"{_pct(rv['baseline']['unsafe_false_accept_rate'])} | "
            f"{_pct(rv['harness']['unsafe_false_accept_rate'])} | "
            f"-{summary['unsafe_false_accept_rate_reduction_pp']:.1f} pp |"
        ),
        (
            "| Unsafe detection recall | "
            f"{_pct(rv['baseline']['unsafe_recall'])} | {_pct(rv['harness']['unsafe_recall'])} | "
            f"+{rv['delta']['unsafe_recall_pp']:.1f} pp |"
        ),
        (
            "| Context quality score | "
            f"{_pct(ce['baseline']['quality_score'])} | {_pct(ce['harness']['quality_score'])} | "
            f"+{ce['delta']['quality_score_pp']:.1f} pp |"
        ),
        "",
        "## Scenario Lift",
        "",
        "| Scenario | Harness module | Baseline behavior | Harness behavior | Lift shown |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(_scenario_rows(rv, ce))

    lines.extend(
        [
            "",
            "## ResultVerifier Cases",
            "",
            "| Scenario | Case | Expected done | Baseline done | Harness done | Failure mode |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for case in rv["cases"]:
        scenario = str(case.get("scenario") or case["id"])
        lines.append(
            f"| {scenario} | {case['id']} | {case['expected_done']} | "
            f"{case['baseline_done']} | {case['harness_done']} | "
            f"{case['failure_mode']} |"
        )

    lines.extend(
        [
            "",
            "## ContextEngine Cases",
            "",
            "| Scenario | Case | Checks | Baseline pass details | Harness pass details |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for case in ce["cases"]:
        baseline = _context_detail(case["baseline"])
        harness = _context_detail(case["harness"])
        lines.append(
            f"| {case.get('scenario') or case['id']} | "
            f"{case['id']} | {', '.join(case['checks'])} | {baseline} | {harness} |"
        )

    lines.extend(
        [
            "",
            "## Method",
            "",
            "- Baseline trusts every non-empty final answer and uses raw history as context.",
            "- Harness treatment uses the example ContextEngine and ResultVerifier modules.",
            "- No LLM call is made; the benchmark isolates deterministic Harness guarantees.",
            "",
        ]
    )
    return "\n".join(lines)


def _scenario_rows(rv: dict[str, object], ce: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for case in rv["cases"]:
        if not case.get("include_in_summary"):
            continue
        lines.append(
            "| {scenario} | ResultVerifier | {baseline} | {harness} | {lift} |".format(
                scenario=case.get("scenario") or case["id"],
                baseline=_done_label(bool(case["baseline_done"])),
                harness=_done_label(bool(case["harness_done"])),
                lift=_verifier_lift(case),
            )
        )
    for case in ce["cases"]:
        if not case.get("include_in_summary"):
            continue
        baseline = case["baseline"]
        harness = case["harness"]
        lines.append(
            "| {scenario} | ContextEngine | {baseline} | {harness} | {lift} |".format(
                scenario=case.get("scenario") or case["id"],
                baseline=_context_lift_detail(baseline),
                harness=_context_lift_detail(harness),
                lift=", ".join(case["checks"]),
            )
        )
    return lines


def _scenario_label(case: dict[str, object]) -> str:
    scenario = case.get("scenario")
    return str(scenario) if scenario else str(case["id"])


def _verifier_lift(case: dict[str, object]) -> str:
    expected_done = bool(case["expected_done"])
    baseline_done = bool(case["baseline_done"])
    harness_done = bool(case["harness_done"])
    if not expected_done and baseline_done and not harness_done:
        return "unsafe answer blocked"
    if expected_done and baseline_done and harness_done:
        return "safe answer preserved"
    return (
        "trust decision corrected" if harness_done == expected_done else "needs review"
    )


def _done_label(done: bool) -> str:
    return "trusted" if done else "blocked"


def _context_lift_detail(row: dict[str, object]) -> str:
    return (
        f"anchor={row['anchor_contract']}; "
        f"control_noise={row['control_polluted']}; "
        f"evidence={row['evidence_visible']}"
    )


def _context_detail(row: dict[str, object]) -> str:
    return (
        f"anchor_contract={row['anchor_contract']}; "
        f"control_polluted={row['control_polluted']}; "
        f"budget={row['budget_compliant']}; "
        f"evidence={row['evidence_visible']}"
    )


def _clean_url(url: str) -> str:
    return url.strip().strip("\"'`<>()[]{}.,;:，。；：）】》").lower()


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _pp(value: float) -> float:
    return round(value * 100, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline Harness A/B evaluation.")
    parser.add_argument(
        "--output-dir",
        default=str(HARNESS_DIR / "evaluation" / "results"),
        help="Directory for JSON and Markdown reports.",
    )
    args = parser.parse_args()
    report = run_evaluation(args.output_dir)

    rv = report["result_verifier"]
    ce = report["context_engine"]
    print("Harness offline evaluation")
    print(
        f"- Result accuracy: baseline {_pct(rv['baseline']['accuracy'])} -> harness {_pct(rv['harness']['accuracy'])}"
    )
    print(
        "- Unsafe false-accept rate: "
        f"baseline {_pct(rv['baseline']['unsafe_false_accept_rate'])} -> "
        f"harness {_pct(rv['harness']['unsafe_false_accept_rate'])}"
    )
    print(
        f"- Context quality: baseline {_pct(ce['baseline']['quality_score'])} -> "
        f"harness {_pct(ce['harness']['quality_score'])}"
    )
    print(f"Report written to: {Path(args.output_dir).resolve()}")


if __name__ == "__main__":
    main()
