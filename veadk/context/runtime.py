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

"""Invocation-local state; immutable session records are only reusable caches."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


context_retriever: ContextVar[Any] = ContextVar("veadk_context_retriever", default=None)


@dataclass
class ContextScope:
    session: Any
    agent_name: str
    branch: str
    pending_state: dict = field(default_factory=dict)
    summary_calls: int = 0
    retrieval_calls: int = 0
    retrieval_results: int = 0
    retrieval_page_bytes: int = 8000
    retrieval_headroom: int | None = None
    retrieval_read_bytes: int | None = None
    retrieval_input_exhausted: bool = False
    projection_bytes: int | None = None
    lossless_projection_bytes: int | None = None
    retrieval_seen: set = field(default_factory=set)
    retrieval_reuse_claimed: set[str] = field(default_factory=set)
    retrieval_batch_reserved: bool = False
    restored_references: set = field(default_factory=set)
    lossy_references: set[str] = field(default_factory=set)
    source_verification_allowed: bool = False
    source_verification_attempted: bool = False
    lookup_previews: tuple = ()
    tool_lookup_previews: tuple = ()
    compression_owner: str | None = None
    evidence_retriever: Any = field(default_factory=context_retriever.get, repr=False)
    evidence_rankings: dict = field(default_factory=dict, repr=False)
    evidence_retrieval_status: str = "not_requested"
    evidence_retrieval_deadline: float | None = None


current_scope: ContextVar[ContextScope | None] = ContextVar(
    "veadk_context_scope", default=None
)
is_summary: ContextVar[bool] = ContextVar("veadk_context_summary", default=False)
