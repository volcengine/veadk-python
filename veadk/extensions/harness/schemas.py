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

"""Public Pydantic models shared by Harness modules and plugins."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list[object] | dict[str, object]
JsonObject: TypeAlias = dict[str, JsonValue]


class HarnessBaseModel(BaseModel):
    """Strict base model for public SDK schemas."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )


class TaskContract(HarnessBaseModel):
    """Stable task target used to keep multi-turn runs anchored."""

    goal: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    metadata: JsonObject = Field(default_factory=dict)


class HarnessInvocationRef(HarnessBaseModel):
    """Run identity and profile propagated through Harness modules."""

    app_name: str = ""
    user_id: str = ""
    session_id: str
    invocation_id: str
    profile: str = "default"
    task: TaskContract | None = None
    metadata: JsonObject = Field(default_factory=dict)


class ConversationMessage(HarnessBaseModel):
    """Protocol-neutral message projection used by atomic modules."""

    role: str
    content: str
    name: str = ""
    metadata: JsonObject = Field(default_factory=dict)


class InvocationContextBlock(HarnessBaseModel):
    """Context header and accounting generated before a model call."""

    header: str
    messages: list[ConversationMessage] = Field(default_factory=list)
    original_chars: int = 0
    context_chars: int = 0
    injected: bool = False
    warnings: list[str] = Field(default_factory=list)


class CompressionDecision(HarnessBaseModel):
    """Policy decision for one message."""

    index: int
    action: Literal["protect", "skip", "compress"]
    reason: str
    role: str
    chars: int


class CompressionPlan(HarnessBaseModel):
    """Role and recency aware compression plan."""

    decisions: list[CompressionDecision] = Field(default_factory=list)
    candidate_indexes: list[int] = Field(default_factory=list)
    summary: JsonObject = Field(default_factory=dict)


class CompressionRequest(HarnessBaseModel):
    """Messages and limits passed to a compressor."""

    messages: list[ConversationMessage]
    max_context_chars: int = 24000
    protected_message_count: int = 2
    metadata: JsonObject = Field(default_factory=dict)


class CompactionReport(HarnessBaseModel):
    """Compaction accounting and policy trace."""

    provider: str
    original_chars: int
    compressed_chars: int
    changed: bool = False
    omitted_messages: int = 0
    protected_messages: int = 0
    tokens_before: int = 0
    tokens_after: int = 0
    tokens_saved: int = 0
    compression_ratio: float = 0.0
    transforms_applied: list[str] = Field(default_factory=list)
    policy: JsonObject = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class CompactionResult(HarnessBaseModel):
    """Compacted messages and report."""

    messages: list[ConversationMessage]
    report: CompactionReport


class EvidenceRef(HarnessBaseModel):
    """Evidence extracted from tool outputs or other trusted context."""

    source: str
    content: str
    score: float = 1.0
    metadata: JsonObject = Field(default_factory=dict)


class ToolReceipt(HarnessBaseModel):
    """Structured record of a tool or capability result."""

    name: str
    status: Literal["success", "error", "unknown"] = "unknown"
    summary: str = ""
    run_id: str = ""
    session_id: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)
    metadata: JsonObject = Field(default_factory=dict)


class VerificationReport(HarnessBaseModel):
    """Answer grounding result."""

    status: Literal["pass", "warn", "fail"] = "pass"
    reasons: list[str] = Field(default_factory=list)
    supported_claims: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    repaired: bool = False


class VerificationDecision(HarnessBaseModel):
    """Action a plugin can take after validation."""

    action: Literal["allow", "observe", "repair", "block"] = "allow"
    reason: str = ""
    instruction: str = ""
    report: VerificationReport | None = None


class HarnessEvent(HarnessBaseModel):
    """Generic event stored for receipts, reports, and diagnostics."""

    event_type: str
    run_context: HarnessInvocationRef | None = None
    payload: JsonObject = Field(default_factory=dict)


HarnessRunContext = HarnessInvocationRef
ContextBundle = InvocationContextBlock
CompressionReport = CompactionReport
CompressionResult = CompactionResult
CapabilityReceipt = ToolReceipt
HarnessIntervention = VerificationDecision

__all__ = [
    "CapabilityReceipt",
    "CompactionReport",
    "CompactionResult",
    "CompressionDecision",
    "CompressionPlan",
    "CompressionReport",
    "CompressionRequest",
    "CompressionResult",
    "ContextBundle",
    "ConversationMessage",
    "EvidenceRef",
    "HarnessBaseModel",
    "HarnessEvent",
    "HarnessIntervention",
    "HarnessInvocationRef",
    "HarnessRunContext",
    "InvocationContextBlock",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "TaskContract",
    "ToolReceipt",
    "VerificationDecision",
    "VerificationReport",
]
