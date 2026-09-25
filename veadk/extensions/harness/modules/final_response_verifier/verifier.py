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

"""Final-response verification: builtin rules, optionally judged.

The builtin rules are deterministic and stay the default. The ``decision``
strategy adds a judgement that rates the answer against the run's receipts and
picks the repair the answer needs; see ``support_judge``.
"""

from __future__ import annotations

import ast
import json
import re
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from veadk.extensions.decisions import DEFAULT_JUDGEMENT_THRESHOLD
from veadk.extensions.harness.schemas import (
    ToolReceipt,
    EvidenceRef,
    HarnessBaseModel,
    VerificationDecision,
    VerificationReport,
)

if TYPE_CHECKING:
    from veadk.extensions.harness.modules.final_response_verifier.support_judge import (
        SupportJudgement,
    )

_ASCII_MARKER_RE = re.compile(r"^[a-z0-9_ -]+$")
_HTML_TAG_RE = re.compile(
    r"</?(?:html|head|body|main|section|article|div|p|span|script|style|ul|ol|li|"
    r"table|tr|td|th|form|input|button|a|h[1-6])\b",
    re.IGNORECASE,
)
_HTML_DOCUMENT_RE = re.compile(
    r"<!doctype html|<html\b|<body\b|<main\b|<section\b|<article\b",
    re.IGNORECASE,
)
_HTML_BLOCK_TAG_RE = re.compile(
    r"</?(?:html|body|main|section|article|p|ul|ol|li|table|form|h[1-6])\b",
    re.IGNORECASE,
)
_FENCED_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_CODE_SPAN_RE = re.compile(r"`[^`\n]+`")
_NEGATED_CJK_MARKER_PREFIXES = ("尚未", "没有", "沒有", "未", "没", "不", "无", "非")


class FinalResponseVerifierConfig(HarnessBaseModel):
    """Settings for final-response verification."""

    mode: Literal["observe", "block"] = "observe"
    strategy: Literal["deterministic", "decision"] = "deterministic"
    support_threshold: float = Field(
        default=DEFAULT_JUDGEMENT_THRESHOLD, ge=0.0, le=1.0
    )
    # 判定说「回答超出回执范围」到这个概率就直接算失败：正交检查是用来兜住
    # 一个过于宽松的 supported 结论的。
    overclaim_threshold: float = Field(
        default=DEFAULT_JUDGEMENT_THRESHOLD, ge=0.0, le=1.0
    )
    # 判定自己没把握（低于该置信度）时不做硬判，回落到内置规则；0 表示关闭。
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    require_receipt_for_completion_claims: bool = True
    max_repair_candidates: int = Field(default=8, ge=1)
    completion_markers: list[str] = Field(
        default_factory=lambda: [
            "created",
            "saved",
            "uploaded",
            "deployed",
            "verified",
            "completed",
            "done",
            "生成",
            "保存",
            "部署",
            "完成",
        ]
    )


class FinalResponseVerifier:
    """Checks whether final answers are grounded in available receipts."""

    def __init__(self, config: FinalResponseVerifierConfig | None = None) -> None:
        self.config = config or FinalResponseVerifierConfig()

    def verify_text(
        self,
        text: str,
        *,
        receipts: list[ToolReceipt] | None = None,
        evidence: list[EvidenceRef] | None = None,
    ) -> VerificationReport:
        """Verify answer text against tool receipts and evidence."""

        receipts = receipts or []
        evidence = evidence or self._evidence_from_receipts(receipts)
        reasons = []
        unsupported_claims = []
        supported_claims = []
        has_success_receipt = any(receipt.status == "success" for receipt in receipts)
        if (
            self.config.require_receipt_for_completion_claims
            and self._has_completion_claim(text)
            and not has_success_receipt
        ):
            reasons.append("completion claim has no successful capability receipt")
            unsupported_claims.append(self._completion_sentence(text))

        if self._looks_like_truncated_html(text):
            reasons.append("response looks like truncated html")
            unsupported_claims.append("html artifact is incomplete")

        if evidence and not unsupported_claims:
            supported_claims.append("answer has tool evidence")

        status: Literal["pass", "warn", "fail"] = "pass"
        if unsupported_claims:
            status = "fail"
        elif reasons:
            status = "warn"
        return VerificationReport(
            status=status,
            reasons=reasons,
            supported_claims=supported_claims,
            unsupported_claims=[claim for claim in unsupported_claims if claim],
            evidence=evidence,
        )

    def apply_judgement(
        self,
        report: VerificationReport,
        judgement: SupportJudgement | None,
    ) -> VerificationReport:
        """Return the report with a decision-model verdict applied.

        The builtin rules only read completion markers and receipt statuses, so
        a judgement replaces the status they produced: the judgement reads the
        answer together with the receipts. What the rules found stays in the
        report, so both verdicts remain visible in the event payload.

        The check that reads the answer from the other side runs first: an
        answer that claims more than the receipts show fails even when the
        verdict itself was ``supported``. A judgement with too little
        confidence never reaches here, because the judge refuses to give one.
        """
        if judgement is None:
            return report
        if judgement.overclaim >= self.config.overclaim_threshold:
            return self._fail(
                report,
                "the decision model judged the answer to claim more than the "
                f"receipts show (overclaim={judgement.overclaim:.2f} >= "
                f"{self.config.overclaim_threshold})",
            )
        if judgement.support >= self.config.support_threshold:
            return report.model_copy(update={"status": "pass"})
        return self._fail(
            report,
            "the decision model judged the answer unsupported "
            f"(support={judgement.support:.2f} < "
            f"{self.config.support_threshold})",
        )

    @staticmethod
    def _fail(report: VerificationReport, reason: str) -> VerificationReport:
        """Return the report failed with one judged reason in front."""
        return report.model_copy(
            update={"status": "fail", "reasons": [reason, *report.reasons]}
        )

    def decide(
        self,
        report: VerificationReport,
        *,
        judgement: SupportJudgement | None = None,
    ) -> VerificationDecision:
        """Map a verification report to a plugin intervention.

        Without a judgement this is the builtin behaviour. With one, the judged
        status decides the intervention and the judged repair action shapes the
        instruction, while ``mode`` still decides whether a failure blocks.
        """
        report = self.apply_judgement(report, judgement)
        action_guidance = judgement.guidance if judgement is not None else ""
        if report.status == "pass":
            return VerificationDecision(action="allow", report=report)
        if self.config.mode == "block" and report.status == "fail":
            return VerificationDecision(
                action="block",
                reason="; ".join(report.reasons),
                instruction=self.build_repair_instruction(
                    report, action_guidance=action_guidance
                ),
                report=report,
            )
        return VerificationDecision(
            action="observe",
            reason="; ".join(report.reasons),
            instruction=self.build_repair_instruction(
                report, action_guidance=action_guidance
            ),
            report=report,
        )

    def build_repair_instruction(
        self,
        report: VerificationReport,
        *,
        goal: str = "",
        action_guidance: str = "",
    ) -> str:
        """Create a compact repair instruction for callers that support retry."""

        reason_text = "; ".join(report.reasons or ["unsupported answer"])
        parts = [
            "[Harness Repair]",
            "The previous answer failed verification.",
            f"Problems: {reason_text}.",
            action_guidance or "Retry the same task with evidence-backed claims only.",
            "Do not claim that files, deployments, or artifacts exist unless a tool receipt proves it.",
        ]
        if goal:
            parts.append(f"Original goal: {goal}")
        parts.append("[/Harness Repair]")
        return "\n".join(parts)

    def try_repair_json_text(self, value: str) -> str:
        """Repair common JSON-like tool argument text."""

        candidate = self._strip_fences(value.strip())
        if not candidate:
            return value
        for repaired in self._repair_candidates(candidate):
            parsed = self._loads_json_or_python(repaired)
            if parsed is not None:
                return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        return value

    def _evidence_from_receipts(self, receipts: list[ToolReceipt]) -> list[EvidenceRef]:
        evidence: list[EvidenceRef] = []
        for receipt in receipts:
            evidence.extend(receipt.evidence)
            if receipt.summary:
                evidence.append(
                    EvidenceRef(
                        source=receipt.name,
                        content=receipt.summary,
                        score=1.0 if receipt.status == "success" else 0.3,
                    )
                )
        return evidence

    def _has_completion_claim(self, text: str) -> bool:
        lowered = text.lower()
        return any(
            self._marker_matches(lowered, marker)
            for marker in self.config.completion_markers
        )

    def _marker_matches(self, lowered_text: str, marker: str) -> bool:
        normalized = marker.strip().lower()
        if not normalized:
            return False
        if _ASCII_MARKER_RE.fullmatch(normalized):
            pattern = rf"(?<![A-Za-z0-9_]){re.escape(normalized)}(?![A-Za-z0-9_])"
            return re.search(pattern, lowered_text) is not None

        start = 0
        while True:
            index = lowered_text.find(normalized, start)
            if index < 0:
                return False
            prefix = lowered_text[max(0, index - 2) : index]
            if not prefix.endswith(_NEGATED_CJK_MARKER_PREFIXES):
                return True
            start = index + len(normalized)

    def _completion_sentence(self, text: str) -> str:
        sentences = re.split(r"(?<=[.!?。！？])\s+", text.strip())
        for sentence in sentences:
            if self._has_completion_claim(sentence):
                return sentence
        return sentences[0] if sentences else ""

    def _looks_like_truncated_html(self, text: str) -> bool:
        html_text = _CODE_SPAN_RE.sub("", _FENCED_CODE_BLOCK_RE.sub("", text))
        if not self._looks_like_html_content(html_text):
            return False
        lowered = html_text.lower()
        if ("<html" in lowered or "<!doctype html" in lowered) and (
            "</html>" not in lowered
        ):
            return True
        if "<script" in lowered and "</script>" not in lowered:
            return True
        return (
            self._looks_like_html_document(html_text)
            and self._has_unclosed_tag(html_text, "div")
            and len(html_text) > 1000
        )

    def _looks_like_html_content(self, text: str) -> bool:
        lowered = text.lower()
        return (
            "<!doctype html" in lowered
            or "<html" in lowered
            or len(_HTML_TAG_RE.findall(text)) >= 3
        )

    def _looks_like_html_document(self, text: str) -> bool:
        return bool(_HTML_DOCUMENT_RE.search(text)) or (
            len(_HTML_BLOCK_TAG_RE.findall(text)) >= 3
        )

    def _has_unclosed_tag(self, text: str, tag: str) -> bool:
        open_count = len(re.findall(rf"<{re.escape(tag)}\b", text, re.IGNORECASE))
        close_count = len(re.findall(rf"</{re.escape(tag)}\s*>", text, re.IGNORECASE))
        return open_count > close_count

    def _strip_fences(self, value: str) -> str:
        stripped = value.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        return stripped.strip()

    def _repair_candidates(self, candidate: str) -> list[str]:
        values = [candidate]
        extracted = self._extract_outer_json_text(candidate)
        if extracted and extracted not in values:
            values.append(extracted)
        repaired = []
        for value in values:
            balanced = self._balance_brackets(value)
            self._append_repair_candidate(repaired, balanced)
            if len(repaired) >= self.config.max_repair_candidates:
                break
            normalized = self._normalize_json_like_text(balanced)
            if normalized != balanced:
                self._append_repair_candidate(repaired, normalized)
                if len(repaired) >= self.config.max_repair_candidates:
                    break
        return repaired

    def _append_repair_candidate(self, values: list[str], candidate: str) -> None:
        if candidate not in values:
            values.append(candidate)

    def _loads_json_or_python(
        self, value: str
    ) -> dict[str, object] | list[object] | None:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except json.JSONDecodeError:
            pass
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, (dict, list)):
                return parsed
        except (SyntaxError, ValueError):
            pass
        return None

    def _extract_outer_json_text(self, value: str) -> str:
        candidates = []
        for start_char, end_char in (("{", "}"), ("[", "]")):
            start = value.find(start_char)
            end = value.rfind(end_char)
            if start >= 0 and end > start:
                candidates.append(value[start : end + 1])
        return max(candidates, key=len) if candidates else ""

    def _balance_brackets(self, value: str) -> str:
        repaired = value.strip()
        if repaired.count("{") > repaired.count("}"):
            repaired += "}" * (repaired.count("{") - repaired.count("}"))
        if repaired.count("[") > repaired.count("]"):
            repaired += "]" * (repaired.count("[") - repaired.count("]"))
        return repaired

    def _normalize_json_like_text(self, value: str) -> str:
        repaired = value.strip()
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
        repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")
        return repaired


ResultVerifierConfig = FinalResponseVerifierConfig
ResultVerifier = FinalResponseVerifier

__all__ = [
    "FinalResponseVerifier",
    "FinalResponseVerifierConfig",
    "ResultVerifier",
    "ResultVerifierConfig",
]
