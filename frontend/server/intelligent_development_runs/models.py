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

"""Persisted task state, independent of browser and Codex connections."""

from dataclasses import dataclass, field
from typing import Any

TERMINAL_STATES = frozenset({"succeeded", "cancelled", "failed"})
RUN_STATES = TERMINAL_STATES | {
    "queued",
    "running",
    "recovering",
    "waiting_user",
    "stopping",
}


@dataclass(frozen=True)
class Run:
    id: str
    owner_id: str
    session_id: str
    request_id: str
    message: str
    state: str
    phase: str
    thread_id: str
    turn_id: str
    input_revision: int
    last_seq: int
    stop_requested: bool
    created_at: float
    updated_at: float
    expires_at: float | None
    lease_token: str
    lease_until: float
    checkpoint: dict[str, Any] = field(default_factory=dict)
    state_message: str = ""
    message_digest: str = ""

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def public(self) -> dict[str, Any]:
        """Never expose executor leases, private paths or recovery checkpoints."""
        return {
            "runId": self.id,
            "sessionId": self.session_id,
            "requestId": self.request_id,
            "message": self.message,
            "state": self.state,
            "phase": self.phase,
            "threadId": self.thread_id,
            "turnId": self.turn_id,
            "inputRevision": self.input_revision,
            "lastSeq": self.last_seq,
            "stopRequested": self.stop_requested,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "expiresAt": self.expires_at,
            "statusMessage": self.state_message,
            "issue": self.checkpoint.get("issue"),
        }
