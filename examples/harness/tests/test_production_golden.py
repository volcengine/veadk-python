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

from harness_modules import (
    CapabilityReceipt,
    ContextEngine,
    HarnessContext,
    LocalHarnessStore,
    ResultVerifier,
    TaskContract,
)


URL_RE = re.compile(r"https?://[^\s)\],，。；;]+", re.IGNORECASE)
SUCCESS_STATUSES = {"success", "ok", "passed"}


def _cases_path() -> Path:
    return Path(__file__).resolve().parents[1] / "golden" / "production_scenarios.jsonl"


def _load_cases() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in _cases_path().read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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


def _build_receipts(
    *,
    store: LocalHarnessStore,
    case: dict[str, object],
) -> list[CapabilityReceipt]:
    receipts: list[CapabilityReceipt] = []
    tool_outputs = case.get("tool_outputs", [])
    if not isinstance(tool_outputs, list):
        return receipts

    for idx, raw_output in enumerate(tool_outputs, start=1):
        if not isinstance(raw_output, dict):
            continue
        output = {str(key): value for key, value in raw_output.items()}
        result = str(output.get("result", ""))
        status = str(output.get("status", "success"))
        evidence_refs = []
        sources = []
        if status in SUCCESS_STATUSES and result:
            evidence_refs.append(store.put_evidence(kind="tool-result", text=result))
            sources = [{"url": _clean_url(url)} for url in URL_RE.findall(result)]

        receipts.append(
            CapabilityReceipt(
                id=f"receipt-{idx}",
                run_id="r1",
                session_id="s1",
                tool_name=str(output.get("tool", "tool")),
                input_summary=str(case["prompt"]),
                result_summary=result,
                status=status,
                duration_ms=1.0,
                evidence_refs=evidence_refs,
                sources=sources,
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
    history = case.get("history", [])
    if not isinstance(history, list):
        return

    for idx, raw_item in enumerate(history):
        if not isinstance(raw_item, dict):
            continue
        item = {str(key): value for key, value in raw_item.items()}
        raw_metadata = item.get("metadata", {})
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        store.append_message(
            session_id=str(case["id"]),
            role=str(item.get("role", "")),
            content=str(item.get("content", "")),
            run_id=f"history-{idx}",
            metadata={str(key): value for key, value in metadata.items()},
        )


def _load_context_evidence(store: LocalHarnessStore, case: dict[str, object]) -> None:
    evidence_text = case.get("evidence")
    if not evidence_text:
        return

    evidence = store.put_evidence(kind="tool-result", text=str(evidence_text))
    store.append_receipt(
        CapabilityReceipt(
            id=f"receipt-{case['id']}",
            run_id=f"run-{case['id']}",
            session_id=str(case["id"]),
            tool_name="knowledge_lookup",
            input_summary=str(case["prompt"]),
            result_summary=str(evidence_text),
            status="success",
            duration_ms=1.0,
            evidence_refs=[evidence],
            sources=[
                {"url": _clean_url(url)} for url in URL_RE.findall(str(evidence_text))
            ],
        )
    )


def test_production_golden_collection_has_generic_scenarios():
    cases = _load_cases()
    raw_text = _cases_path().read_text(encoding="utf-8").lower()
    legacy_marker = "on" + "call"

    assert cases
    assert {case["kind"] for case in cases} == {"result_verifier", "context_engine"}
    assert f"task_{legacy_marker}" not in raw_text
    assert legacy_marker not in raw_text
    assert {case["scenario"] for case in cases} >= {
        "RAG memory freshness",
        "Tool failure claimed as success",
        "Runtime parameter drift",
        "Multi-turn context anchoring",
        "Current evidence beats stale memory",
    }


def test_production_golden_result_verifier_cases(tmp_path):
    for case in _load_cases():
        if case["kind"] != "result_verifier":
            continue

        store = LocalHarnessStore(tmp_path / str(case["id"]))
        verifier = ResultVerifier(store=store)
        report = verifier.verify(
            final_text=str(case["final_answer"]),
            context=_context(str(case["prompt"]), verifier),
            receipts=_build_receipts(store=store, case=case),
        )

        assert report.done is case["expected_done"], case["id"]
        expected_missing = case.get("expected_missing_contains")
        if expected_missing:
            assert any(
                str(expected_missing) in item for item in report.missing_requirements
            )


def test_production_golden_context_engine_cases(tmp_path):
    for case in _load_cases():
        if case["kind"] != "context_engine":
            continue

        store = LocalHarnessStore(tmp_path / str(case["id"]))
        _load_history(store, case)
        _load_context_evidence(store, case)

        engine = ContextEngine(
            store=store,
            max_context_chars=int(case.get("max_context_chars", 1600)),
        )
        context = engine.prepare_context(
            HarnessContext(
                user_id="u1",
                session_id=str(case["id"]),
                run_id=f"run-{case['id']}",
                original_prompt=str(case["prompt"]),
            )
        )
        header = engine.build_context_header(context=context)

        assert context.turn_type == case["expected_turn_type"], case["id"]
        assert context.task_contract is not None
        assert context.task_contract.original_prompt == case["expected_anchor"]
        if case.get("expected_excluded"):
            assert str(case["expected_excluded"]) not in header
        if case.get("expected_included"):
            assert str(case["expected_included"]) in header
        if case.get("expected_evidence_url"):
            assert str(case["expected_evidence_url"]) in header
            assert header.index("Evidence preview:") < header.index(
                "Recent session history:"
            )


def _clean_url(url: str) -> str:
    return url.strip().strip("\"'`<>()[]{}.,;:，。；：）】》").lower()
