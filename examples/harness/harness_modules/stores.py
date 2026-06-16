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

"""Local JSONL/file store for the Harness example.

The store is intentionally small and dependency-free. Production deployments
should replace it with a durable shared store, but the interfaces here are
enough to demonstrate context projection, tool receipts, evidence, and reports.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from pathlib import Path

from pydantic import BaseModel

from .core import (
    CapabilityReceipt,
    EvidenceRef,
    HarnessEvent,
    JSONDict,
    JSONValue,
    VerificationReport,
    summarize_text,
    utc_now,
)


def _to_jsonable(value: object) -> JSONValue:
    if isinstance(value, BaseModel):
        return _to_jsonable(value.model_dump(mode="json"))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _json_object(text: str) -> JSONDict:
    value = json.loads(text)
    return dict(value) if isinstance(value, dict) else {}


def _read_jsonl(path: Path) -> list[JSONDict]:
    if not path.exists():
        return []
    records: list[JSONDict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = _json_object(line)
        if record:
            records.append(record)
    return records


class LocalHarnessStore:
    """Simple local store used by the example and tests."""

    def __init__(self, root_dir: str | Path = ".harness_runs") -> None:
        self.root_dir = Path(root_dir)
        self.evidence_dir = self.root_dir / "evidence"
        self.reports_dir = self.root_dir / "reports"
        self.events_path = self.root_dir / "events.jsonl"
        self.receipts_path = self.root_dir / "receipts.jsonl"
        self.messages_path = self.root_dir / "messages.jsonl"
        self._lock = threading.Lock()
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def _append_jsonl(self, path: Path, record: JSONDict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(_to_jsonable(record), ensure_ascii=False, sort_keys=True)
                )
                f.write("\n")

    def append_event(self, event: HarnessEvent) -> None:
        self._append_jsonl(self.events_path, event.model_dump(mode="json"))

    def load_events(
        self, *, run_id: str | None = None, session_id: str | None = None
    ) -> list[JSONDict]:
        records = _read_jsonl(self.events_path)
        return [
            record
            for record in records
            if (run_id is None or record.get("run_id") == run_id)
            and (session_id is None or record.get("session_id") == session_id)
        ]

    def append_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        run_id: str = "",
        metadata: JSONDict | None = None,
    ) -> None:
        self._append_jsonl(
            self.messages_path,
            {
                "session_id": session_id,
                "run_id": run_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "created_at": utc_now(),
            },
        )

    def load_messages(
        self, session_id: str, *, limit: int | None = None
    ) -> list[JSONDict]:
        records = [
            record
            for record in _read_jsonl(self.messages_path)
            if record.get("session_id") == session_id
        ]
        if limit is None:
            return records
        return records[-limit:]

    def put_evidence(
        self,
        *,
        kind: str,
        text: str,
        metadata: JSONDict | None = None,
        ref_id: str | None = None,
    ) -> EvidenceRef:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        ref_id = ref_id or f"ev-{digest[:12]}-{uuid.uuid4().hex[:6]}"
        path = self.evidence_dir / f"{ref_id}.txt"
        path.write_text(text, encoding="utf-8")
        return EvidenceRef(
            ref_id=ref_id,
            kind=kind,
            uri=str(path),
            digest=digest,
            preview=summarize_text(text, max_chars=700),
            metadata=metadata or {},
        )

    def read_evidence(self, ref_id: str) -> str:
        path = self.evidence_dir / f"{ref_id}.txt"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def append_receipt(self, receipt: CapabilityReceipt) -> None:
        self._append_jsonl(self.receipts_path, receipt.model_dump(mode="json"))

    def load_receipts(
        self,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> list[CapabilityReceipt]:
        receipts: list[CapabilityReceipt] = []
        for record in _read_jsonl(self.receipts_path):
            if run_id is not None and record.get("run_id") != run_id:
                continue
            if session_id is not None and record.get("session_id") != session_id:
                continue
            receipt = CapabilityReceipt(
                id=str(record["id"]),
                run_id=str(record.get("run_id", "")),
                session_id=str(record.get("session_id", "")),
                tool_name=str(record.get("tool_name", "")),
                input_summary=str(record.get("input_summary", "")),
                result_summary=str(record.get("result_summary", "")),
                status=str(record.get("status", "unknown")),
                duration_ms=float(record.get("duration_ms", 0)),
                evidence_refs=[
                    EvidenceRef(**ref)
                    for ref in record.get("evidence_refs", [])
                    if isinstance(ref, dict)
                ],
                sources=[
                    dict(source)
                    for source in record.get("sources", [])
                    if isinstance(source, dict)
                ],
                artifacts=[
                    dict(artifact)
                    for artifact in record.get("artifacts", [])
                    if isinstance(artifact, dict)
                ],
                error_type=str(record["error_type"])
                if record.get("error_type")
                else None,
                error_message=str(record["error_message"])
                if record.get("error_message")
                else None,
                created_at=str(record.get("created_at", utc_now())),
                metadata=(
                    dict(record["metadata"])
                    if isinstance(record.get("metadata"), dict)
                    else {}
                ),
            )
            receipts.append(receipt)
        return receipts

    def save_report(self, report: VerificationReport) -> None:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.reports_dir / f"{report.session_id}-{report.run_id}.json"
        report_path.write_text(
            json.dumps(
                _to_jsonable(report), ensure_ascii=False, indent=2, sort_keys=True
            ),
            encoding="utf-8",
        )

    def load_report(self, *, session_id: str, run_id: str) -> JSONDict:
        report_path = self.reports_dir / f"{session_id}-{run_id}.json"
        return _json_object(report_path.read_text(encoding="utf-8"))

    def latest_report(self, *, session_id: str) -> JSONDict | None:
        reports = sorted(self.reports_dir.glob(f"{session_id}-*.json"))
        if not reports:
            return None
        return _json_object(reports[-1].read_text(encoding="utf-8"))
