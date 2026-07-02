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

"""Deterministic result verification and hallucination suppression."""

from __future__ import annotations

import json
import re
from typing import Callable, Protocol, TypedDict

from .context_engine import has_external_fact_markers, has_output_format_markers
from .core import (
    AcceptanceCheck,
    AcceptanceCriterion,
    CapabilityReceipt,
    HarnessContext,
    VerificationReport,
)


class EvidenceReadStoreProtocol(Protocol):
    def read_evidence(self, ref_id: str) -> str: ...


class EvidenceBundle(TypedDict):
    corpus: str
    refs: list[str]
    urls: set[str]


URL_RE = re.compile(r"https?://[^\s)\],，。；;]+", re.IGNORECASE)
KEY_FACT_RE = re.compile(
    r"(?:[$¥￥]\s?\d+(?:\.\d+)?|\d+(?:\.\d+)?%|\d{4}[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?|\d{4}年|\d{4,})"
)
SUCCESS_RECEIPT_STATUSES = {"success", "ok", "passed", "completed"}
SUCCESS_DECLARATION_RE = re.compile(
    r'(?:"?operation_completed"?\s*[:=]\s*true|'
    r'"?problem_observed"?\s*[:=]\s*false|'
    r'"?status"?\s*[:=]\s*"?(?:passed|success|ok)"?)',
    re.IGNORECASE,
)
COMPLETION_CLAIM_RE = re.compile(
    r"(已完成|已经完成|完成了|操作完成|已成功|成功完成|已更新|已经更新|"
    r"已写入|done|successfully completed|completed successfully|updated successfully)",
    re.IGNORECASE,
)
NEGATED_COMPLETION_RE = re.compile(
    r"(未完成|没有完成|无法完成|不能完成|不能视为已完成|未能完成|"
    r"not\s+completed|failed\s+to\s+complete|could\s+not\s+complete|"
    r"unable\s+to\s+complete|cannot\s+complete)",
    re.IGNORECASE,
)


class ResultVerifier:
    """Small deterministic verifier for external-fact answers."""

    def __init__(
        self,
        *,
        store: EvidenceReadStoreProtocol | None = None,
        repair_callback: Callable[[str, VerificationReport], str] | None = None,
    ) -> None:
        self.store = store
        self.repair_callback = repair_callback

    def build_acceptance(self, prompt: str) -> list[AcceptanceCriterion]:
        criteria = [
            AcceptanceCriterion(
                id="AC-final-answer",
                description="Return a non-empty final answer that addresses the user request.",
            )
        ]
        if has_external_fact_markers(prompt):
            criteria.append(
                AcceptanceCriterion(
                    id="AC-grounded-facts",
                    description="External or current factual claims must be grounded in tool evidence or cited sources.",
                )
            )
        if has_output_format_markers(prompt):
            criteria.append(
                AcceptanceCriterion(
                    id="AC-output-format",
                    description="Respect the requested output format.",
                )
            )
        return criteria

    def verify(
        self,
        *,
        final_text: str,
        context: HarnessContext,
        receipts: list[CapabilityReceipt] | None = None,
    ) -> VerificationReport:
        receipts = receipts if receipts is not None else context.receipts
        prompt = self._contract_prompt(context)
        criteria = (
            context.task_contract.acceptance
            if context.task_contract is not None
            else self.build_acceptance(prompt)
        )
        evidence = self._collect_evidence(receipts)
        evidence_corpus = evidence["corpus"]
        evidence_refs = evidence["refs"]
        allowed_urls = evidence["urls"]

        checks: list[AcceptanceCheck] = []
        checks.append(self._check_final_answer(final_text))
        receipt_check = self._check_failed_receipt_completion(
            final_text=final_text,
            receipts=receipts,
        )
        if receipt_check is not None:
            checks.append(receipt_check)

        if any(item.id == "AC-grounded-facts" for item in criteria):
            checks.append(
                self._check_grounded_facts(
                    final_text=final_text,
                    evidence_refs=evidence_refs,
                    allowed_urls=allowed_urls,
                )
            )
            checks.extend(
                self._build_evidence_checks(
                    final_text=final_text,
                    evidence_corpus=evidence_corpus,
                    allowed_urls=allowed_urls,
                    evidence_refs=evidence_refs,
                )
            )

        if any(item.id == "AC-output-format" for item in criteria):
            checks.append(
                self._check_output_format(prompt=prompt, final_text=final_text)
            )

        missing = [
            check.message
            for check in checks
            if not check.passed and check.severity == "error"
        ]
        done = not missing
        guidance = ""
        if missing:
            guidance = (
                "Answer is not ready to trust. Add tool evidence, cite only observed sources, "
                "or explicitly state which facts could not be verified."
            )

        return VerificationReport(
            run_id=context.run_id,
            session_id=context.session_id,
            done=done,
            checks=checks,
            missing_requirements=missing,
            evidence_refs=evidence_refs,
            follow_up_guidance=guidance,
        )

    def repair(self, final_text: str, report: VerificationReport) -> str:
        """Return a conservative repaired answer or delegate to a callback."""

        if report.done:
            return final_text
        if self.repair_callback is not None:
            return self.repair_callback(final_text, report)

        missing = "; ".join(report.missing_requirements)
        return (
            "I cannot verify the answer with the available evidence. "
            f"Missing requirements: {missing}. "
            "Please run the required lookup/search tools or provide source material before treating this as final."
        )

    def _contract_prompt(self, context: HarnessContext) -> str:
        if context.task_contract is None:
            return context.original_prompt
        current_prompt = context.task_contract.metadata.get("current_prompt", "")
        return f"{context.task_contract.original_prompt}\n{current_prompt}".strip()

    def _check_final_answer(self, final_text: str) -> AcceptanceCheck:
        passed = bool(final_text and final_text.strip())
        return AcceptanceCheck(
            id="AC-final-answer",
            passed=passed,
            message="Final answer is present." if passed else "Final answer is empty.",
        )

    def _check_grounded_facts(
        self,
        *,
        final_text: str,
        evidence_refs: list[str],
        allowed_urls: set[str],
    ) -> AcceptanceCheck:
        has_evidence = bool(evidence_refs or allowed_urls)
        if has_evidence:
            return AcceptanceCheck(
                id="AC-grounded-facts",
                passed=True,
                message="External facts have evidence candidates.",
                evidence_refs=list(evidence_refs),
            )
        return AcceptanceCheck(
            id="AC-grounded-facts",
            passed=False,
            message="External/current factual task has no tool evidence or source receipt.",
        )

    def _build_evidence_checks(
        self,
        *,
        final_text: str,
        evidence_corpus: str,
        allowed_urls: set[str],
        evidence_refs: list[str],
    ) -> list[AcceptanceCheck]:
        checks: list[AcceptanceCheck] = []

        answer_urls = {self._clean_url(url) for url in URL_RE.findall(final_text)}
        fabricated_urls = sorted(url for url in answer_urls if url not in allowed_urls)
        checks.append(
            AcceptanceCheck(
                id="EG-source-refs",
                passed=not fabricated_urls,
                message=(
                    "All cited URLs are present in tool evidence."
                    if not fabricated_urls
                    else f"Answer cites URL(s) not present in evidence/source: {', '.join(fabricated_urls)}"
                ),
                evidence_refs=evidence_refs,
            )
        )

        key_facts = sorted(set(KEY_FACT_RE.findall(final_text)))
        missing_facts = [
            fact
            for fact in key_facts
            if self._normalize(fact) not in self._normalize(evidence_corpus)
        ]
        checks.append(
            AcceptanceCheck(
                id="EG-key-facts",
                passed=not missing_facts,
                message=(
                    "Numeric/date/price facts are covered by evidence."
                    if not missing_facts
                    else f"Key fact(s) not found in evidence text: {', '.join(missing_facts)}"
                ),
                evidence_refs=evidence_refs,
            )
        )
        return checks

    def _check_failed_receipt_completion(
        self,
        *,
        final_text: str,
        receipts: list[CapabilityReceipt],
    ) -> AcceptanceCheck | None:
        failed_receipts = [
            receipt
            for receipt in receipts
            if receipt.status.strip().lower() not in SUCCESS_RECEIPT_STATUSES
        ]
        if not failed_receipts:
            return None

        failure_summary = ", ".join(
            self._format_receipt_failure(receipt) for receipt in failed_receipts
        )
        completion_claimed = self._claims_completion(final_text)
        return AcceptanceCheck(
            id="EG-tool-receipts",
            passed=not completion_claimed,
            message=(
                "Final answer does not claim completion after failed tool receipt(s)."
                if not completion_claimed
                else (
                    "Answer claims the operation completed despite failed tool "
                    f"receipt(s): {failure_summary}"
                )
            ),
            evidence_refs=[
                ref.ref_id
                for receipt in failed_receipts
                for ref in receipt.evidence_refs
            ],
        )

    def _check_output_format(self, *, prompt: str, final_text: str) -> AcceptanceCheck:
        lowered = prompt.lower()
        text = final_text.strip()
        passed = True
        expected = "requested format"

        if "json" in lowered:
            expected = "JSON"
            try:
                json.loads(text)
            except Exception:
                passed = False
        elif "表格" in lowered or "table" in lowered:
            expected = "table"
            passed = "|" in text or "\t" in text
        elif any(
            marker in lowered for marker in ("清单", "列表", "要点", "list", "bullet")
        ):
            expected = "list"
            passed = bool(
                re.search(r"(^|\n)\s*(?:[-*]|\*{0,2}\d+[.)、]\*{0,2})\s+", text)
            )

        return AcceptanceCheck(
            id="AC-output-format",
            passed=passed,
            message=(
                f"Answer satisfies {expected} output format."
                if passed
                else f"Answer does not satisfy requested {expected} output format."
            ),
        )

    def _collect_evidence(self, receipts: list[CapabilityReceipt]) -> EvidenceBundle:
        corpus_parts: list[str] = []
        refs: list[str] = []
        urls: set[str] = set()

        for receipt in receipts:
            corpus_parts.append(receipt.result_summary)
            for source in receipt.sources:
                source_text = json.dumps(source, ensure_ascii=False, sort_keys=True)
                corpus_parts.append(source_text)
                for url in URL_RE.findall(source_text):
                    urls.add(self._clean_url(url))
            for ref in receipt.evidence_refs:
                refs.append(ref.ref_id)
                corpus_parts.append(ref.preview)
                if self.store is not None:
                    corpus_parts.append(self.store.read_evidence(ref.ref_id))
                for url in URL_RE.findall(ref.preview):
                    urls.add(self._clean_url(url))
            for url in URL_RE.findall(receipt.result_summary):
                urls.add(self._clean_url(url))

        return {
            "corpus": "\n".join(corpus_parts),
            "refs": refs,
            "urls": urls,
        }

    def _clean_url(self, url: str) -> str:
        return url.strip().strip("\"'`<>()[]{}.,;:，。；：）】》").lower()

    def _normalize(self, value: str) -> str:
        return re.sub(r"\s+", "", value).lower()

    def _claims_completion(self, final_text: str) -> bool:
        if SUCCESS_DECLARATION_RE.search(final_text):
            return True
        if NEGATED_COMPLETION_RE.search(final_text):
            return False
        return bool(COMPLETION_CLAIM_RE.search(final_text))

    def _format_receipt_failure(self, receipt: CapabilityReceipt) -> str:
        detail = receipt.error_type or receipt.error_message or receipt.status
        return f"{receipt.tool_name}({detail})"
