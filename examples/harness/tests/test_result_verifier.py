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

import json
import re
from pathlib import Path

import pytest

from harness_modules import (
    CapabilityReceipt,
    HarnessContext,
    LocalHarnessStore,
    ResultVerifier,
    TaskContract,
    wrap_tool,
)


def _context(prompt: str, verifier: ResultVerifier) -> HarnessContext:
    return HarnessContext(
        user_id="u1",
        session_id="s1",
        run_id="r1",
        original_prompt=prompt,
        task_contract=TaskContract(
            task_id="task-1",
            original_prompt=prompt,
            turn_type="new_task",
            acceptance=verifier.build_acceptance(prompt),
        ),
    )


def test_passes_when_fact_is_in_evidence(tmp_path):
    store = LocalHarnessStore(tmp_path)
    verifier = ResultVerifier(store=store)
    evidence = store.put_evidence(
        kind="tool-result",
        text=(
            "AI Usage Policy v2026-06 requires source-backed answers. "
            "Source URL: https://example.com/policies/ai-usage-2026-06"
        ),
    )
    receipt = CapabilityReceipt(
        id="receipt-1",
        run_id="r1",
        session_id="s1",
        tool_name="policy_lookup",
        input_summary="policy",
        result_summary=evidence.preview,
        status="success",
        duration_ms=1.0,
        evidence_refs=[evidence],
        sources=[{"url": "https://example.com/policies/ai-usage-2026-06"}],
    )
    context = _context("请给出最新 AI 使用政策并附来源。", verifier)

    report = verifier.verify(
        final_text=(
            "AI Usage Policy v2026-06 requires source-backed answers. "
            "来源：https://example.com/policies/ai-usage-2026-06"
        ),
        context=context,
        receipts=[receipt],
    )

    assert report.done is True
    assert all(check.passed for check in report.checks)


def test_fails_for_fabricated_url(tmp_path):
    store = LocalHarnessStore(tmp_path)
    verifier = ResultVerifier(store=store)
    evidence = store.put_evidence(
        kind="tool-result",
        text="Policy source: https://example.com/policies/ai-usage-2026-06",
    )
    receipt = CapabilityReceipt(
        id="receipt-1",
        run_id="r1",
        session_id="s1",
        tool_name="policy_lookup",
        input_summary="policy",
        result_summary=evidence.preview,
        status="success",
        duration_ms=1.0,
        evidence_refs=[evidence],
        sources=[{"url": "https://example.com/policies/ai-usage-2026-06"}],
    )
    context = _context("请给出最新政策并附来源。", verifier)

    report = verifier.verify(
        final_text="政策已经发布，参考 https://fake.example/policy。",
        context=context,
        receipts=[receipt],
    )

    assert report.done is False
    assert any(
        "not present in evidence" in item for item in report.missing_requirements
    )


def test_passes_when_url_is_only_in_source_receipt(tmp_path):
    store = LocalHarnessStore(tmp_path)
    verifier = ResultVerifier(store=store)
    receipt = CapabilityReceipt(
        id="receipt-1",
        run_id="r1",
        session_id="s1",
        tool_name="policy_lookup",
        input_summary="policy",
        result_summary="AI Usage Policy v2026-06 requires source-backed answers.",
        status="success",
        duration_ms=1.0,
        sources=[
            {"title": "policy", "url": "https://example.com/policies/ai-usage-2026-06"}
        ],
    )
    context = _context("请给出最新 AI 使用政策并附来源。", verifier)

    report = verifier.verify(
        final_text=(
            "AI Usage Policy v2026-06 requires source-backed answers. "
            "来源：https://example.com/policies/ai-usage-2026-06"
        ),
        context=context,
        receipts=[receipt],
    )

    assert report.done is True


def test_accepts_markdown_bold_numbered_list_format(tmp_path):
    verifier = ResultVerifier(store=LocalHarnessStore(tmp_path))
    receipt = CapabilityReceipt(
        id="receipt-1",
        run_id="r1",
        session_id="s1",
        tool_name="public_web_lookup",
        input_summary="harness capabilities",
        result_summary=(
            "ContextEngine anchors tasks. ResultVerifier checks evidence. "
            "Source: https://example.com/veadk/harness-demo"
        ),
        status="success",
        duration_ms=1.0,
        sources=[{"url": "https://example.com/veadk/harness-demo"}],
    )
    context = _context("请用 2 条要点回答，并给出来源。", verifier)

    report = verifier.verify(
        final_text=(
            "**1. ContextEngine** anchors tasks.\n"
            "**2. ResultVerifier** checks evidence.\n"
            "来源：https://example.com/veadk/harness-demo"
        ),
        context=context,
        receipts=[receipt],
    )

    assert report.done is True


def test_fails_when_external_fact_has_no_evidence(tmp_path):
    verifier = ResultVerifier(store=LocalHarnessStore(tmp_path))
    context = _context("请总结最新政策并给出来源。", verifier)

    report = verifier.verify(
        final_text="最新政策已经发布。",
        context=context,
        receipts=[],
    )

    assert report.done is False
    assert any("no tool evidence" in item for item in report.missing_requirements)


def test_tool_wrapper_records_failed_receipt(tmp_path):
    store = LocalHarnessStore(tmp_path)

    def broken_lookup(topic: str) -> dict[str, str]:
        """Broken lookup used by the test."""

        raise RuntimeError(f"missing index for {topic}")

    wrapped = wrap_tool(broken_lookup, store=store)

    with pytest.raises(RuntimeError):
        wrapped("policy")

    receipts = store.load_receipts()
    assert len(receipts) == 1
    assert receipts[0].status == "failed"
    assert receipts[0].tool_name == "broken_lookup"
    assert receipts[0].error_type == "RuntimeError"


def test_fails_when_failed_receipt_is_claimed_successful(tmp_path):
    verifier = ResultVerifier(store=LocalHarnessStore(tmp_path))
    receipt = CapabilityReceipt(
        id="receipt-1",
        run_id="r1",
        session_id="s1",
        tool_name="mock_skill_runner",
        input_summary="append text",
        result_summary="参数格式校验失败，文档追加未执行。",
        status="failed",
        duration_ms=1.0,
        error_type="ValidationError",
        error_message="schema rejected append_text payload",
    )
    context = _context("请使用 mock Skill 模拟一次文档更新工具调用。", verifier)

    report = verifier.verify(
        final_text=(
            '{"category":"tool_skill","operation_completed":true,'
            '"status":"passed","problem_observed":false}'
        ),
        context=context,
        receipts=[receipt],
    )

    assert report.done is False
    assert any(
        "despite failed tool receipt" in item for item in report.missing_requirements
    )


def test_allows_failed_receipt_when_answer_reports_failure(tmp_path):
    verifier = ResultVerifier(store=LocalHarnessStore(tmp_path))
    receipt = CapabilityReceipt(
        id="receipt-1",
        run_id="r1",
        session_id="s1",
        tool_name="mock_tool_call",
        input_summary="authorized call",
        result_summary="安全策略误拦截了授权调用。",
        status="failed",
        duration_ms=1.0,
        error_type="SecurityPolicyBlocked",
    )
    context = _context("请完成授权用户的 mock_tool_call。", verifier)

    report = verifier.verify(
        final_text="mock_tool_call 未完成：授权调用被安全策略拦截，需要修复策略后重试。",
        context=context,
        receipts=[receipt],
    )

    assert report.done is True


def test_large_tool_result_externalized(tmp_path):
    store = LocalHarnessStore(tmp_path)

    def large_lookup() -> dict[str, str]:
        """Return a large result."""

        return {"result": "large evidence " * 100}

    wrapped = wrap_tool(large_lookup, store=store, externalize_threshold=100)
    wrapped()

    receipts = store.load_receipts()
    assert len(receipts) == 1
    assert receipts[0].status == "success"
    assert receipts[0].evidence_refs
    assert "large evidence" in store.read_evidence(receipts[0].evidence_refs[0].ref_id)


def test_golden_verifier_cases(tmp_path):
    cases_path = Path(__file__).resolve().parents[1] / "golden" / "verifier_cases.jsonl"
    for line in cases_path.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        store = LocalHarnessStore(tmp_path / case["id"])
        verifier = ResultVerifier(store=store)
        receipts = []
        for idx, output in enumerate(case.get("tool_outputs", []), start=1):
            result = output["result"]
            status = output.get("status", "success")
            evidence_refs = []
            sources = []
            if status == "success":
                evidence_refs.append(
                    store.put_evidence(kind="tool-result", text=result)
                )
                sources = [
                    {"url": url.rstrip(".,;:，。；：)")}
                    for url in re.findall(r"https?://[^\s)\],，。；;]+", result)
                ]
            receipts.append(
                CapabilityReceipt(
                    id=f"receipt-{idx}",
                    run_id="r1",
                    session_id="s1",
                    tool_name=output["tool"],
                    input_summary="golden",
                    result_summary=result,
                    status=status,
                    duration_ms=1.0,
                    evidence_refs=evidence_refs,
                    sources=sources,
                    error_type=output.get("error_type"),
                    error_message=output.get("error_message"),
                )
            )

        report = verifier.verify(
            final_text=case["final_answer"],
            context=_context(case["prompt"], verifier),
            receipts=receipts,
        )

        assert report.done is case["expected_done"], case["id"]
        expected_missing = case.get("expected_missing_contains")
        if expected_missing:
            assert any(expected_missing in item for item in report.missing_requirements)
