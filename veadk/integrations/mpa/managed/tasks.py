"""Durable, owner-scoped Studio tasks with cancellable child processes."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import uuid

STAGES = {
    "queued",
    "checking",
    "network",
    "gateway",
    "database",
    "skills",
    "worker",
    "deploying",
    "verifying",
}
ACTIVE = {"running", "cancelling"}


class TaskError(ValueError):
    pass


class CreationTasks:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        with self.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, owner TEXT NOT NULL, request TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL, stage TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '', supervisor INTEGER NOT NULL, updated REAL NOT NULL, UNIQUE(owner,request))"
            )
        os.chmod(path, 0o600)
        self.running: dict[str, asyncio.Task] = {}

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def command(self):
        return [sys.executable, "-m", "veadk.integrations.mpa.managed.runner"]

    def _update(self, task_id, **values):
        values["updated"] = time.time()
        with self.db() as db:
            db.execute(
                "UPDATE tasks SET "
                + ",".join(k + "=?" for k in values)
                + " WHERE id=?",
                (*values.values(), task_id),
            )

    def get(self, owner, task_id):
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM tasks WHERE id=? AND owner=?", (task_id, owner)
            ).fetchone()
        if row is None:
            raise TaskError("Task not found")
        if row["state"] in ACTIVE:
            try:
                os.kill(row["supervisor"], 0)
            except ProcessLookupError:
                self._update(task_id, state="failed", error="interrupted")
                return self.get(owner, task_id)
        return {
            "taskId": task_id,
            "state": row["state"],
            "stage": row["stage"],
            "result": json.loads(row["result"]),
            "error": row["error"],
            **json.loads(row["payload"]),
        }

    async def start(self, owner, payload, *, config_path, timeout):
        encoded = json.dumps(payload, sort_keys=True)
        # Reconcile stopped supervisors before acquiring the write transaction.
        # get() may write interrupted status and must not nest a SQLite writer.
        with self.db() as db:
            active = db.execute(
                "SELECT owner,id FROM tasks WHERE state IN ('running','cancelling')"
            ).fetchall()
        for item in active:
            self.get(item["owner"], item["id"])
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM tasks WHERE owner=? AND request=?",
                (owner, payload["requestId"]),
            ).fetchone()
            if row and row["payload"] != encoded:
                raise TaskError("Request identity already has different inputs")
            if row and row["state"] in ACTIVE | {"succeeded"}:
                return self.get(owner, row["id"])
            count = db.execute(
                "SELECT COUNT(*) FROM tasks WHERE state IN ('running','cancelling')"
            ).fetchone()[0]
            own = db.execute(
                "SELECT COUNT(*) FROM tasks WHERE owner=? AND state IN ('running','cancelling')",
                (owner,),
            ).fetchone()[0]
            if count >= 4 or own:
                raise TaskError("Another creation is running; wait or cancel it")
            task_id = row["id"] if row else str(uuid.uuid4())
            db.execute(
                "INSERT INTO tasks (id,owner,request,payload,state,stage,supervisor,updated) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state='running', stage='queued', result='{}', error='', supervisor=excluded.supervisor, updated=excluded.updated",
                (
                    task_id,
                    owner,
                    payload["requestId"],
                    encoded,
                    "running",
                    "queued",
                    os.getpid(),
                    time.time(),
                ),
            )
        task = asyncio.create_task(
            self._run(task_id, owner, payload, config_path, timeout)
        )
        self.running[task_id] = task
        task.add_done_callback(lambda _: self.running.pop(task_id, None))
        return self.get(owner, task_id)

    async def _run(self, task_id, owner, payload, config_path, timeout):
        process = None
        succeeded = None
        terminal = {"state": "failed", "error": "creationFailed"}
        spawn = None
        try:
            spawn = asyncio.create_task(
                asyncio.create_subprocess_exec(
                    *self.command(),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    limit=16384,
                )
            )
            process = await asyncio.shield(spawn)
            data = {
                "config": str(config_path),
                "agentId": payload["agentId"],
                "description": payload["description"],
                "owner": owner,
                "region": payload["region"],
            }
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(json.dumps(data).encode())
            await process.stdin.drain()
            process.stdin.close()
            deadline = time.monotonic() + timeout
            while True:
                if self.get(owner, task_id)["state"] == "cancelling":
                    raise asyncio.CancelledError()
                if time.monotonic() >= deadline:
                    raise asyncio.TimeoutError()
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), 1)
                except asyncio.TimeoutError:
                    continue
                if not line:
                    break
                if not line.startswith(b"MPA_EVENT "):
                    continue
                event = json.loads(line[10:])
                if event.get("stage") in STAGES:
                    self._update(task_id, stage=event["stage"])
                if event.get("result"):
                    result = event["result"]
                    keys = {
                        "runtime_id",
                        "skill_space_id",
                        "gateway_id",
                        "agent_id",
                        "region",
                        "state",
                    }
                    if set(result) != keys or not all(
                        isinstance(v, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", v)
                        for v in result.values()
                    ):
                        raise TaskError("Invalid result")
                    if (
                        result["agent_id"] != payload["agentId"]
                        or result["region"] != payload["region"]
                        or result["state"] != "ready"
                    ):
                        raise TaskError("Invalid result identity")
                    succeeded = result
            code = await asyncio.wait_for(
                process.wait(), max(0.1, deadline - time.monotonic())
            )
            if code != 0 or not succeeded:
                raise TaskError("Creation failed")
            terminal = {
                "state": "succeeded",
                "result": json.dumps(succeeded),
                "error": "",
            }
        except asyncio.CancelledError:
            terminal = {"state": "cancelled", "error": "cancelled"}
        except asyncio.TimeoutError:
            terminal = {"state": "failed", "error": "timeout"}
        except Exception:
            pass
        finally:

            async def finish():
                nonlocal process
                if process is None and spawn is not None:
                    try:
                        process = await spawn
                    except Exception:
                        pass
                if process is not None and process.returncode is None:
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
                    try:
                        await asyncio.wait_for(process.wait(), 3)
                    except asyncio.TimeoutError:
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass
                        await process.wait()
                self._update(task_id, **terminal)

            # A second cancellation must not interrupt termination or reaping.
            cleanup = asyncio.create_task(finish())
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            cleanup.result()

    async def cancel(self, owner, task_id):
        task = self.get(owner, task_id)
        if task["state"] == "running":
            self._update(task_id, state="cancelling")
            running = self.running.get(task_id)
            if running:
                # Let a just-scheduled coroutine enter its cleanup scope.
                await asyncio.sleep(0)
                running.cancel()
                await asyncio.gather(running, return_exceptions=True)
        return self.get(owner, task_id)

    async def close(self):
        tasks = list(self.running.values())
        await asyncio.sleep(0)
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def owner_key(identity: str) -> str:
    return hashlib.sha256(identity.encode()).hexdigest()
