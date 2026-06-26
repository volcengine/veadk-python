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

"""JSONL Harness store."""

from __future__ import annotations

import json
from pathlib import Path

from veadk.extensions.harness.schemas import (
    ToolReceipt,
    ConversationMessage,
    HarnessEvent,
)


class JsonlHarnessStore:
    """Append-only local JSONL store with lightweight reads."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def append_event(self, event: HarnessEvent) -> None:
        self._append("events.jsonl", event.model_dump(mode="json"))

    def append_receipt(self, receipt: ToolReceipt) -> None:
        self._append("receipts.jsonl", receipt.model_dump(mode="json"))

    def append_message(self, session_id: str, message: ConversationMessage) -> None:
        payload = message.model_dump(mode="json")
        payload["session_id"] = session_id
        self._append("messages.jsonl", payload)

    def load_messages(
        self, session_id: str, limit: int | None = None
    ) -> list[ConversationMessage]:
        messages = []
        for payload in self._read("messages.jsonl"):
            if payload.get("session_id") != session_id:
                continue
            payload.pop("session_id", None)
            messages.append(ConversationMessage.model_validate(payload))
        return messages[-limit:] if limit else messages

    def load_receipts(
        self,
        *,
        run_id: str = "",
        session_id: str = "",
        limit: int | None = None,
    ) -> list[ToolReceipt]:
        receipts = []
        for payload in self._read("receipts.jsonl"):
            receipt = ToolReceipt.model_validate(payload)
            if run_id and receipt.run_id != run_id:
                continue
            if session_id and receipt.session_id != session_id:
                continue
            receipts.append(receipt)
        return receipts[-limit:] if limit else receipts

    def _append(self, filename: str, payload: dict[str, object]) -> None:
        path = self.root / filename
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def _read(self, filename: str) -> list[dict[str, object]]:
        path = self.root / filename
        if not path.is_file():
            return []
        rows: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
        return rows
