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

"""SQLite acceptance, user isolation, fencing and replay for Studio tasks.

Every user-facing operation requires an owner. A short transaction owns each
mutation; neither remote calls nor event subscribers hold SQLite transactions.
Executor leases fence database writes, not remote RPCs: the runner must still
reconcile an ambiguous remote submission before retrying it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from .models import RUN_STATES, TERMINAL_STATES, Run


class RunNotFound(LookupError):
    pass


class RunConflict(ValueError):
    pass


class RunLeaseLost(RuntimeError):
    pass


class RunCapacity(RunConflict):
    pass


_T = TypeVar("_T")
_TERMINAL_SQL = "('succeeded', 'cancelled', 'failed')"
_INPUT_STATES = frozenset({"pending", "sending", "delivered", "withdrawn"})


class RunRepository:
    def __init__(
        self,
        path: str | Path,
        *,
        retention_seconds: float = 21_600,
        max_active_seconds: float = 28_800,
        max_event_bytes: int = 64 * 1024 * 1024,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if retention_seconds <= 0 or max_active_seconds <= 0 or max_event_bytes <= 0:
            raise ValueError("Task retention must be positive")
        self.path = Path(path).expanduser().absolute()
        self.retention_seconds = retention_seconds
        self.max_active_seconds = max_active_seconds
        self.max_event_bytes = max_event_bytes
        self.clock = clock
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Open with restrictive permissions even when the process umask is broad.
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        with self._connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(f"""
                CREATE TABLE IF NOT EXISTS runs (
                    owner_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    message TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'queued',
                    phase TEXT NOT NULL DEFAULT 'prepare',
                    thread_id TEXT NOT NULL DEFAULT '',
                    turn_id TEXT NOT NULL DEFAULT '',
                    input_revision INTEGER NOT NULL DEFAULT 1,
                    last_seq INTEGER NOT NULL DEFAULT 0,
                    stop_requested INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL,
                    lease_token TEXT NOT NULL DEFAULT '',
                    lease_until REAL NOT NULL DEFAULT 0,
                    checkpoint TEXT NOT NULL DEFAULT '{{}}',
                    state_message TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (owner_id, id),
                    UNIQUE (owner_id, session_id, request_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_run
                    ON runs(owner_id, session_id)
                    WHERE state NOT IN {_TERMINAL_SQL};
                CREATE INDEX IF NOT EXISTS run_expiry ON runs(expires_at);
                CREATE TABLE IF NOT EXISTS run_events (
                    owner_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (owner_id, run_id, seq),
                    FOREIGN KEY (owner_id, run_id) REFERENCES runs(owner_id, id)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS run_inputs (
                    owner_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    turn_id TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    PRIMARY KEY (owner_id, run_id, client_id),
                    UNIQUE (owner_id, run_id, revision),
                    FOREIGN KEY (owner_id, run_id) REFERENCES runs(owner_id, id)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS run_event_usage (
                    owner_id TEXT NOT NULL, run_id TEXT NOT NULL, bytes INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(owner_id,run_id),
                    FOREIGN KEY(owner_id,run_id) REFERENCES runs(owner_id,id) ON DELETE CASCADE
                );
                INSERT OR IGNORE INTO run_event_usage
                    SELECT owner_id,run_id,SUM(length(CAST(payload AS BLOB))) FROM run_events GROUP BY owner_id,run_id;
                CREATE TABLE IF NOT EXISTS run_turns (
                    owner_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    input_revision INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    PRIMARY KEY (owner_id, run_id, turn_id),
                    FOREIGN KEY (owner_id, run_id) REFERENCES runs(owner_id, id)
                        ON DELETE CASCADE
                );
                PRAGMA user_version=1;
            """)
            # Expand existing local databases without discarding retained runs.
            for table in ("runs", "run_inputs"):
                columns = {
                    row["name"] for row in db.execute(f"PRAGMA table_info({table})")
                }
                if "message_digest" not in columns:
                    db.execute(
                        f"ALTER TABLE {table} ADD COLUMN message_digest TEXT NOT NULL DEFAULT ''"
                    )

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        try:
            yield db
        finally:
            db.close()

    async def _read(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        def run() -> _T:
            with self._connection() as db:
                return operation(db)

        return await asyncio.to_thread(run)

    async def _write(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        def run() -> _T:
            with self._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    result = operation(db)
                    db.commit()
                    return result
                except BaseException:
                    db.rollback()
                    raise

        return await asyncio.to_thread(run)

    @staticmethod
    def _owned(db: sqlite3.Connection, owner: str, run_id: str) -> Run:
        row = db.execute(
            "SELECT * FROM runs WHERE owner_id=? AND id=?", (owner, run_id)
        ).fetchone()
        if row is None:
            raise RunNotFound("任务不存在或不属于当前用户。")
        value = dict(row)
        value["checkpoint"] = json.loads(value["checkpoint"])
        value["stop_requested"] = bool(value["stop_requested"])
        return Run(**value)

    def _leased(
        self, db: sqlite3.Connection, owner: str, run_id: str, token: str
    ) -> Run:
        run = self._owned(db, owner, run_id)
        if not token or run.lease_token != token or run.lease_until <= self.clock():
            raise RunLeaseLost("Task executor lease is no longer valid")
        return run

    def _event(
        self,
        db: sqlite3.Connection,
        owner: str,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if event_type == "run.status":
            payload = {
                **payload,
                "lastSeq": self._owned(db, owner, run_id).last_seq + 1,
            }
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        size = len(encoded.encode())
        if size > 2 * 1024 * 1024:
            raise ValueError("Task event exceeds the size limit")
        usage = db.execute(
            "SELECT bytes FROM run_event_usage WHERE owner_id=? AND run_id=?",
            (owner, run_id),
        ).fetchone()
        if (
            usage
            and usage["bytes"] + size > self.max_event_bytes
            and not event_type.startswith("run.")
        ):
            raise RunCapacity("任务输出已达到短期存储上限，已保留现有内容。")
        db.execute(
            "INSERT INTO run_event_usage VALUES(?,?,?) ON CONFLICT(owner_id,run_id) DO UPDATE SET bytes=bytes+excluded.bytes",
            (owner, run_id, size),
        )
        db.execute(
            "UPDATE runs SET last_seq=last_seq+1, updated_at=? WHERE owner_id=? AND id=?",
            (self.clock(), owner, run_id),
        )
        run = self._owned(db, owner, run_id)
        db.execute(
            "INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?)",
            (owner, run_id, run.last_seq, event_type, encoded, self.clock()),
        )
        return {"seq": run.last_seq, "type": event_type, "payload": payload}

    async def create(
        self,
        owner: str,
        session_id: str,
        request_id: str,
        message: str,
        *,
        thread_id: str = "",
        message_digest: str = "",
    ) -> Run:
        if not owner or not session_id or not request_id or not message.strip():
            raise ValueError("Task identity and message are required")
        if len(message) > 100_000 or len(request_id) > 128:
            raise ValueError("Task input exceeds the size limit")

        digest = message_digest or hashlib.sha256(message.encode()).hexdigest()

        def operation(db):
            existing = db.execute(
                "SELECT id FROM runs WHERE owner_id=? AND session_id=? AND request_id=?",
                (owner, session_id, request_id),
            ).fetchone()
            if existing:
                run = self._owned(db, owner, existing["id"])
                if (run.message_digest and run.message_digest != digest) or (
                    not run.message_digest and run.message != message
                ):
                    raise RunConflict("相同请求标识不能用于不同内容。")
                return run
            active = db.execute(
                f"SELECT owner_id FROM runs WHERE state NOT IN {_TERMINAL_SQL}"
            ).fetchall()
            if (
                len(active) >= 100
                or sum(row["owner_id"] == owner for row in active) >= 3
            ):
                raise RunCapacity("当前进行中的任务较多，请先完成或停止其他任务。")
            pages = db.execute("PRAGMA page_count").fetchone()[0]
            pages -= db.execute("PRAGMA freelist_count").fetchone()[0]
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            if pages * page_size >= 512 * 1024 * 1024:
                raise RunCapacity("本地任务存储暂时已满，请稍后重试。")
            run_id = uuid4().hex
            try:
                db.execute(
                    "INSERT INTO runs(owner_id,id,session_id,request_id,message,thread_id,created_at,updated_at,message_digest) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        owner,
                        run_id,
                        session_id,
                        request_id,
                        message,
                        thread_id,
                        self.clock(),
                        self.clock(),
                        digest,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise RunConflict(
                    "当前环境已有任务，请追加要求或先停止任务。"
                ) from error
            db.execute(
                "INSERT INTO run_inputs(owner_id,run_id,client_id,revision,message,created_at,message_digest) VALUES(?,?,?,?,?,?,?)",
                (owner, run_id, request_id, 1, message, self.clock(), digest),
            )
            self._event(
                db,
                owner,
                run_id,
                "run.input",
                {
                    "clientId": request_id,
                    "revision": 1,
                    "message": message,
                    "status": "pending",
                },
            )
            return self._owned(db, owner, run_id)

        return await self._write(operation)

    async def get(self, owner: str, run_id: str) -> Run:
        return await self._read(lambda db: self._owned(db, owner, run_id))

    async def session_runs(self, owner: str, session_id: str) -> list[Run]:
        def operation(db):
            return [
                self._owned(db, owner, row["id"])
                for row in db.execute(
                    "SELECT id FROM runs WHERE owner_id=? AND session_id=? ORDER BY created_at,id",
                    (owner, session_id),
                )
            ]

        return await self._read(operation)

    async def recoverable(self) -> list[Run]:
        """Internal scheduler scan; this method is never an HTTP list endpoint."""

        def operation(db):
            return [
                self._owned(db, row["owner_id"], row["id"])
                for row in db.execute(
                    f"SELECT owner_id,id FROM runs WHERE state NOT IN {_TERMINAL_SQL} "
                    "AND (state != 'waiting_user' OR created_at<=?) ORDER BY created_at",
                    (self.clock() - self.max_active_seconds,),
                )
            ]

        return await self._read(operation)

    async def active_for_owner(self, owner: str) -> list[Run]:
        return await self._read(
            lambda db: [
                self._owned(db, owner, row["id"])
                for row in db.execute(
                    f"SELECT id FROM runs WHERE owner_id=? AND state NOT IN {_TERMINAL_SQL} ORDER BY created_at",
                    (owner,),
                )
            ]
        )

    async def claim(
        self, owner: str, run_id: str, *, seconds: float = 30
    ) -> str | None:
        def operation(db):
            run = self._owned(db, owner, run_id)
            if run.terminal or (run.lease_token and run.lease_until > self.clock()):
                return None
            token = uuid4().hex
            db.execute(
                "UPDATE runs SET lease_token=?,lease_until=? WHERE owner_id=? AND id=?",
                (token, self.clock() + seconds, owner, run_id),
            )
            return token

        return await self._write(operation)

    async def heartbeat(
        self, owner: str, run_id: str, token: str, *, seconds: float = 30
    ) -> None:
        def operation(db):
            self._leased(db, owner, run_id, token)
            db.execute(
                "UPDATE runs SET lease_until=? WHERE owner_id=? AND id=?",
                (self.clock() + seconds, owner, run_id),
            )

        await self._write(operation)

    async def release(self, owner: str, run_id: str, token: str) -> None:
        await self._write(
            lambda db: db.execute(
                "UPDATE runs SET lease_token='',lease_until=0 WHERE owner_id=? AND id=? AND lease_token=?",
                (owner, run_id, token),
            ).rowcount
        )

    async def update(self, owner: str, run_id: str, token: str, **changes: Any) -> Run:
        allowed = {
            "state",
            "phase",
            "thread_id",
            "turn_id",
            "checkpoint",
            "state_message",
        }
        if not changes or set(changes) - allowed:
            raise ValueError("Unsupported task update")
        if "state" in changes and changes["state"] not in RUN_STATES:
            raise ValueError("Invalid task state")

        def operation(db):
            run = self._leased(db, owner, run_id, token)
            if run.terminal:
                raise RunConflict("任务已经结束。")
            state = changes.get("state", run.state)
            if run.stop_requested and state not in {"stopping", "cancelled", "failed"}:
                raise RunConflict("任务正在停止。")
            values = dict(changes)
            if "checkpoint" in values:
                values["checkpoint"] = json.dumps(
                    values["checkpoint"], ensure_ascii=False, allow_nan=False
                )
            values["updated_at"] = self.clock()
            if state in TERMINAL_STATES:
                values["expires_at"] = self.clock() + self.retention_seconds
            assignments = ",".join(f"{key}=?" for key in values)
            db.execute(
                f"UPDATE runs SET {assignments} WHERE owner_id=? AND id=?",
                (*values.values(), owner, run_id),
            )
            updated = self._owned(db, owner, run_id)
            if any(key in changes for key in ("state", "phase", "state_message")):
                self._event(db, owner, run_id, "run.status", updated.public())
            return self._owned(db, owner, run_id)

        return await self._write(operation)

    async def append_event(
        self,
        owner: str,
        run_id: str,
        token: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        def operation(db):
            self._leased(db, owner, run_id, token)
            return self._event(db, owner, run_id, event_type, payload)

        return await self._write(operation)

    async def events(
        self, owner: str, run_id: str, *, after: int = 0, limit: int = 500
    ) -> list[dict[str, Any]]:
        if after < 0 or not 1 <= limit <= 1000:
            raise ValueError("Invalid event cursor or limit")

        def operation(db):
            self._owned(db, owner, run_id)
            return [
                {
                    "seq": row["seq"],
                    "type": row["type"],
                    "payload": json.loads(row["payload"]),
                }
                for row in db.execute(
                    "SELECT seq,type,payload FROM run_events WHERE owner_id=? AND run_id=? AND seq>? ORDER BY seq LIMIT ?",
                    (owner, run_id, after, limit),
                )
            ]

        return await self._read(operation)

    async def request_stop(self, owner: str, run_id: str) -> Run:
        def operation(db):
            run = self._owned(db, owner, run_id)
            if run.terminal or run.stop_requested:
                return run
            db.execute(
                "UPDATE runs SET stop_requested=1,state='stopping',state_message=?,updated_at=? WHERE owner_id=? AND id=?",
                ("正在停止任务。", self.clock(), owner, run_id),
            )
            pending = db.execute(
                "SELECT client_id FROM run_inputs WHERE owner_id=? AND run_id=? AND status='pending' ORDER BY revision",
                (owner, run_id),
            ).fetchall()
            db.execute(
                "UPDATE run_inputs SET status='withdrawn' WHERE owner_id=? AND run_id=? AND status='pending'",
                (owner, run_id),
            )
            for item in pending:
                self._event(
                    db,
                    owner,
                    run_id,
                    "run.input_status",
                    {
                        "clientId": item["client_id"],
                        "status": "withdrawn",
                        "turnId": "",
                    },
                )
            self._event(
                db, owner, run_id, "run.status", self._owned(db, owner, run_id).public()
            )
            return self._owned(db, owner, run_id)

        return await self._write(operation)

    async def resume(self, owner: str, run_id: str) -> Run:
        """Explicitly resume a paused task; completed/cancelled tasks get a new run."""

        def operation(db):
            run = self._owned(db, owner, run_id)
            if run.state != "waiting_user" or run.stop_requested:
                raise RunConflict("只有等待处理的任务可以恢复。")
            db.execute(
                "UPDATE runs SET state='recovering',state_message='',checkpoint=?,updated_at=? WHERE owner_id=? AND id=?",
                (
                    json.dumps({**run.checkpoint, "manual_resume": True}),
                    self.clock(),
                    owner,
                    run_id,
                ),
            )
            self._event(
                db, owner, run_id, "run.status", self._owned(db, owner, run_id).public()
            )
            return self._owned(db, owner, run_id)

        return await self._write(operation)

    async def add_input(
        self,
        owner: str,
        run_id: str,
        client_id: str,
        message: str,
        *,
        message_digest: str = "",
    ) -> dict[str, Any]:
        if (
            not client_id
            or len(client_id) > 128
            or not message.strip()
            or len(message) > 100_000
        ):
            raise ValueError("Invalid additional input")
        digest = message_digest or hashlib.sha256(message.encode()).hexdigest()

        def operation(db):
            run = self._owned(db, owner, run_id)
            existing = db.execute(
                "SELECT * FROM run_inputs WHERE owner_id=? AND run_id=? AND client_id=?",
                (owner, run_id, client_id),
            ).fetchone()
            if existing:
                if (
                    existing["message_digest"] and existing["message_digest"] != digest
                ) or (
                    not existing["message_digest"] and existing["message"] != message
                ):
                    raise RunConflict("相同消息标识不能用于不同内容。")
                return dict(existing)
            if run.terminal or run.stop_requested:
                raise RunConflict("任务已结束或正在停止，请保留输入并稍后发送。")
            revision = run.input_revision + 1
            if revision > 256:
                raise RunCapacity("本次任务的追加消息已达上限，请完成后再发起新任务。")
            db.execute(
                "UPDATE runs SET input_revision=? WHERE owner_id=? AND id=?",
                (revision, owner, run_id),
            )
            db.execute(
                "INSERT INTO run_inputs(owner_id,run_id,client_id,revision,message,created_at,message_digest) VALUES(?,?,?,?,?,?,?)",
                (owner, run_id, client_id, revision, message, self.clock(), digest),
            )
            self._event(
                db,
                owner,
                run_id,
                "run.input",
                {
                    "clientId": client_id,
                    "revision": revision,
                    "message": message,
                    "status": "pending",
                },
            )
            if run.state == "waiting_user":
                db.execute(
                    "UPDATE runs SET state='recovering',checkpoint=? WHERE owner_id=? AND id=?",
                    (
                        json.dumps({**run.checkpoint, "manual_resume": True}),
                        owner,
                        run_id,
                    ),
                )
                self._event(
                    db,
                    owner,
                    run_id,
                    "run.status",
                    self._owned(db, owner, run_id).public(),
                )
            return dict(
                db.execute(
                    "SELECT * FROM run_inputs WHERE owner_id=? AND run_id=? AND client_id=?",
                    (owner, run_id, client_id),
                ).fetchone()
            )

        return await self._write(operation)

    async def inputs(
        self, owner: str, run_id: str, *, statuses: tuple[str, ...] = ()
    ) -> list[dict[str, Any]]:
        if set(statuses) - _INPUT_STATES:
            raise ValueError("Invalid input status")

        def operation(db):
            self._owned(db, owner, run_id)
            condition = (
                " AND status IN (" + ",".join("?" for _ in statuses) + ")"
                if statuses
                else ""
            )
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM run_inputs WHERE owner_id=? AND run_id=?"
                    + condition
                    + " ORDER BY revision",
                    (owner, run_id, *statuses),
                )
            ]

        return await self._read(operation)

    async def input_status(
        self,
        owner: str,
        run_id: str,
        token: str,
        client_id: str,
        status: str,
        *,
        turn_id: str = "",
    ) -> None:
        if status not in _INPUT_STATES:
            raise ValueError("Invalid input status")

        def operation(db):
            run = self._leased(db, owner, run_id, token)
            item = db.execute(
                "SELECT status,turn_id FROM run_inputs WHERE owner_id=? AND run_id=? AND client_id=?",
                (owner, run_id, client_id),
            ).fetchone()
            if item is None:
                raise RunNotFound("任务消息不存在。")
            if (run.stop_requested and status in {"pending", "sending"}) or item[
                "status"
            ] == "withdrawn":
                raise RunConflict("任务正在停止，不能继续发送。")
            if item["status"] == status and item["turn_id"] == turn_id:
                return
            if item["status"] == "delivered" and status != "delivered":
                raise RunConflict("已送达的消息不能重新发送。")
            changed = db.execute(
                "UPDATE run_inputs SET status=?,turn_id=? WHERE owner_id=? AND run_id=? AND client_id=?",
                (status, turn_id, owner, run_id, client_id),
            ).rowcount
            if not changed:
                raise RunNotFound("任务消息不存在。")
            self._event(
                db,
                owner,
                run_id,
                "run.input_status",
                {"clientId": client_id, "status": status, "turnId": turn_id},
            )

        await self._write(operation)

    async def record_turn(
        self,
        owner: str,
        run_id: str,
        token: str,
        *,
        thread_id: str,
        turn_id: str,
        revision: int,
        status: str,
    ) -> None:
        def operation(db):
            self._leased(db, owner, run_id, token)
            db.execute(
                "INSERT INTO run_turns VALUES(?,?,?,?,?,?) ON CONFLICT(owner_id,run_id,turn_id) "
                "DO UPDATE SET input_revision=excluded.input_revision,status=excluded.status",
                (owner, run_id, turn_id, thread_id, revision, status),
            )

        await self._write(operation)

    async def cleanup(self) -> int:
        return await self._write(
            lambda db: db.execute(
                f"DELETE FROM runs WHERE state IN {_TERMINAL_SQL} AND expires_at<=? AND lease_until<=?",
                (self.clock(), self.clock()),
            ).rowcount
        )

    async def finish(self, owner: str, run_id: str, token: str, revision: int) -> bool:
        """Atomically fence completion against a concurrent steer or stop."""

        def operation(db):
            run = self._leased(db, owner, run_id, token)
            if run.stop_requested or run.input_revision != revision:
                return False
            db.execute(
                "UPDATE runs SET state='succeeded',phase='complete',state_message='',expires_at=?,checkpoint=? WHERE owner_id=? AND id=?",
                (
                    self.clock() + self.retention_seconds,
                    json.dumps({**run.checkpoint, "issue": None}),
                    owner,
                    run_id,
                ),
            )
            self._event(
                db, owner, run_id, "run.status", self._owned(db, owner, run_id).public()
            )
            return True

        return await self._write(operation)

    async def delete(self, owner: str, run_id: str) -> None:
        def operation(db):
            run = self._owned(db, owner, run_id)
            if not run.terminal:
                raise RunConflict("请先停止任务。")
            db.execute("DELETE FROM runs WHERE owner_id=? AND id=?", (owner, run_id))

        await self._write(operation)

    async def checkpoint(
        self, owner: str, run_id: str, token: str, **values: Any
    ) -> Run:
        def operation(db):
            run = self._leased(db, owner, run_id, token)
            checkpoint = {**run.checkpoint, **values}
            if "accepted_revision" in values:
                checkpoint["accepted_revision"] = max(
                    int(run.checkpoint.get("accepted_revision", 0)),
                    int(values["accepted_revision"]),
                )
            db.execute(
                "UPDATE runs SET checkpoint=? WHERE owner_id=? AND id=?",
                (
                    json.dumps(checkpoint, ensure_ascii=False, allow_nan=False),
                    owner,
                    run_id,
                ),
            )
            return self._owned(db, owner, run_id)

        return await self._write(operation)
