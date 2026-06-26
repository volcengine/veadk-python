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

"""In-memory Harness store for tests and local development."""

from __future__ import annotations

from collections import defaultdict

from veadk.extensions.harness.schemas import (
    ToolReceipt,
    ConversationMessage,
    HarnessEvent,
)


class InMemoryHarnessStore:
    """Simple process-local store."""

    def __init__(self) -> None:
        self.events: list[HarnessEvent] = []
        self.receipts: list[ToolReceipt] = []
        self.messages: dict[str, list[ConversationMessage]] = defaultdict(list)

    def append_event(self, event: HarnessEvent) -> None:
        self.events.append(event)

    def append_receipt(self, receipt: ToolReceipt) -> None:
        self.receipts.append(receipt)

    def append_message(self, session_id: str, message: ConversationMessage) -> None:
        self.messages[session_id].append(message)

    def load_messages(
        self, session_id: str, limit: int | None = None
    ) -> list[ConversationMessage]:
        messages = list(self.messages.get(session_id, []))
        return messages[-limit:] if limit else messages

    def load_receipts(
        self,
        *,
        run_id: str = "",
        session_id: str = "",
        limit: int | None = None,
    ) -> list[ToolReceipt]:
        receipts = [
            receipt
            for receipt in self.receipts
            if (not run_id or receipt.run_id == run_id)
            and (not session_id or receipt.session_id == session_id)
        ]
        return receipts[-limit:] if limit else receipts
