"""Durable, owner-scoped Studio tasks with cancellable child processes."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import uuid

from .diagnostics import classify_error, validate_diagnostic

logger = logging.getLogger(__name__)

STAGES = {
    "queued",
    "checking",
    "admin_workspace",
    "business_workspace",
    "admin_database",
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
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, owner TEXT NOT NULL, request TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL, stage TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '', supervisor INTEGER NOT NULL, updated REAL NOT NULL, UNIQUE(owner,request))"
            )
            if "images" not in {
                row[1] for row in db.execute("PRAGMA table_info(tasks)")
            }:
                db.execute(
                    "ALTER TABLE tasks ADD COLUMN images TEXT NOT NULL DEFAULT '{}'"
                )
            db.execute(
                "CREATE TABLE IF NOT EXISTS task_diagnostics (id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, stage TEXT NOT NULL, operation TEXT NOT NULL, category TEXT NOT NULL, attempt INTEGER NOT NULL, outcome TEXT NOT NULL, created REAL NOT NULL)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS task_diagnostics_task ON task_diagnostics(task_id,id)"
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

    def record_diagnostic(self, task_id, value):
        diagnostic = validate_diagnostic(value)
        if diagnostic is None:
            return
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT stage FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if row is None:
                return
            stage = row["stage"] if row["stage"] in STAGES else "queued"
            created = time.time()
            db.execute(
                "INSERT INTO task_diagnostics (task_id,stage,operation,category,attempt,outcome,created) VALUES (?,?,?,?,?,?,?)",
                (
                    task_id,
                    stage,
                    diagnostic["operation"],
                    diagnostic["category"],
                    diagnostic["attempt"],
                    diagnostic["outcome"],
                    created,
                ),
            )
            db.execute(
                "DELETE FROM task_diagnostics WHERE task_id=? AND id NOT IN (SELECT id FROM task_diagnostics WHERE task_id=? ORDER BY id DESC LIMIT 100)",
                (task_id, task_id),
            )
        logger.warning(
            "MPA creation diagnostic: %s",
            {"taskId": task_id, "stage": stage, "created": created, **diagnostic},
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
                self.record_diagnostic(
                    task_id,
                    dict(
                        operation="supervisor",
                        category="interrupted",
                        attempt=1,
                        outcome="failed",
                    ),
                )
                return self.get(owner, task_id)
        return {
            "taskId": task_id,
            "state": row["state"],
            "stage": row["stage"],
            "result": json.loads(row["result"]),
            "error": row["error"],
            "images": json.loads(row["images"]),
            **json.loads(row["payload"]),
        }

    async def start(
        self, owner, payload, *, config_path, timeout, images=None, secrets=None
    ):
        if "openvikingApiKey" in payload:
            raise TaskError("Secrets must not be included in stored task inputs")
        secrets = secrets or {}
        if set(secrets) - {"openvikingApiKey"}:
            raise TaskError("Unsupported creation secret")
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
            selected_images = json.loads(row["images"]) if row else dict(images or {})
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
                "INSERT INTO tasks (id,owner,request,payload,state,stage,supervisor,updated,images) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state='running', stage='queued', result='{}', error='', supervisor=excluded.supervisor, updated=excluded.updated",
                (
                    task_id,
                    owner,
                    payload["requestId"],
                    encoded,
                    "running",
                    "queued",
                    os.getpid(),
                    time.time(),
                    json.dumps(selected_images),
                ),
            )
        task = asyncio.create_task(
            self._run(task_id, owner, payload, config_path, timeout, secrets)
        )
        self.running[task_id] = task
        task.add_done_callback(lambda _: self.running.pop(task_id, None))
        return self.get(owner, task_id)

    async def _run(self, task_id, owner, payload, config_path, timeout, secrets):
        process = None
        succeeded = None
        terminal = {"state": "failed", "error": "creationFailed"}
        spawn = None
        failure_reported = False
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
                "config": None if config_path is None else str(config_path),
                "agentId": payload["agentId"],
                "description": payload["description"],
                "owner": owner,
                "region": payload["region"],
                "images": self.get(owner, task_id)["images"],
                "resources": {
                    key: payload[key]
                    for key in (
                        "pgHost",
                        "pgPort",
                        "openvikingUrl",
                        "openvikingResourceId",
                    )
                    if key in payload
                },
            }
            if secrets.get("openvikingApiKey"):
                data["resources"]["openvikingApiKey"] = secrets["openvikingApiKey"]
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
                if not isinstance(event, dict):
                    raise TaskError("Invalid event")
                diagnostic = validate_diagnostic(event.get("diagnostic"))
                if diagnostic is not None:
                    self.record_diagnostic(task_id, diagnostic)
                    failure_reported = (
                        failure_reported or diagnostic["outcome"] == "failed"
                    )
                if isinstance(event.get("stage"), str) and event["stage"] in STAGES:
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
                if not failure_reported:
                    self.record_diagnostic(
                        task_id,
                        dict(
                            operation="supervisor",
                            category="child_exit",
                            attempt=1,
                            outcome="failed",
                        ),
                    )
                    failure_reported = True
                raise TaskError("Creation failed")
            terminal = {
                "state": "succeeded",
                "result": json.dumps(succeeded),
                "error": "",
            }
        except asyncio.CancelledError:
            terminal = {"state": "cancelled", "error": "cancelled"}
            self.record_diagnostic(
                task_id,
                dict(
                    operation="supervisor",
                    category="cancelled",
                    attempt=1,
                    outcome="cancelled",
                ),
            )
        except asyncio.TimeoutError:
            terminal = {"state": "failed", "error": "timeout"}
            self.record_diagnostic(
                task_id,
                dict(
                    operation="supervisor",
                    category="timeout",
                    attempt=1,
                    outcome="failed",
                ),
            )
        except Exception as error:
            if not failure_reported:
                self.record_diagnostic(
                    task_id,
                    dict(
                        operation="supervisor",
                        category="protocol_error"
                        if isinstance(error, (TaskError, ValueError))
                        else classify_error(error),
                        attempt=1,
                        outcome="failed",
                    ),
                )
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
