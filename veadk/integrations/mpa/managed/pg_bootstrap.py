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

"""Durable two-Workspace bootstrap before the shared registry is available."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from dataclasses import replace
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from sqlalchemy.engine import make_url

from .admin_database import initialize_admin_database
from .config import ADMIN_DATABASE_NAME, validate_postgres_layout
from .database import DeploymentError
from .pg_cloud import PGCloudError, PGNotReady, check_ready


class BootstrapStore:
    """Nonsecret creation intents; a shared local state path is required."""

    def __init__(self, path):
        self.path = Path(path).expanduser().absolute()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        with self.connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS workspaces (scope TEXT, purpose TEXT, config TEXT NOT NULL, workspace_id TEXT NOT NULL, intent INTEGER NOT NULL, PRIMARY KEY(scope,purpose))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS failed_workspaces (scope TEXT, purpose TEXT, workspace_id TEXT NOT NULL, PRIMARY KEY(scope,purpose,workspace_id))"
            )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    @asynccontextmanager
    async def lock(self, scope):
        fd = os.open(
            str(self.path) + "." + scope + ".lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
        )
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.1)
            yield
        finally:
            os.close(fd)

    def read(self, scope, purpose):
        with self.connection() as db:
            row = db.execute(
                "SELECT config,workspace_id,intent FROM workspaces WHERE scope=? AND purpose=?",
                (scope, purpose),
            ).fetchone()
        return row

    def save(self, scope, purpose, config, ident, intent):
        with self.connection() as db:
            db.execute(
                "INSERT INTO workspaces VALUES (?,?,?,?,?) ON CONFLICT(scope,purpose) DO UPDATE SET workspace_id=excluded.workspace_id,intent=excluded.intent",
                (scope, purpose, config, ident, int(intent)),
            )

    def rejected(self, scope, purpose):
        with self.connection() as db:
            db.execute(
                "DELETE FROM workspaces WHERE scope=? AND purpose=? AND workspace_id=''",
                (scope, purpose),
            )

    def failed_ids(self, scope, purpose):
        with self.connection() as db:
            return {
                row[0]
                for row in db.execute(
                    "SELECT workspace_id FROM failed_workspaces WHERE scope=? AND purpose=?",
                    (scope, purpose),
                )
            }

    def retire_failed(self, scope, purpose, ident, *, clear_intent):
        """Retain a failed cloud identity without attributing it to later requests."""
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO failed_workspaces VALUES (?,?,?)",
                (scope, purpose, ident),
            )
            if clear_intent:
                db.execute(
                    "DELETE FROM workspaces WHERE scope=? AND purpose=? AND workspace_id IN ('',?)",
                    (scope, purpose, ident),
                )


def validate_workspace(row, *, account, region, project, name, tags, owned):
    expected = {
        "account_id": account,
        "region_id": region,
        "project_name": project,
        "workspace_name": name,
        "engine_version": "PostgreSQL_17",
    }
    missing_metadata = False
    for key, value in expected.items():
        actual = str(row.get(key) or "")
        if actual != value:
            if owned and not actual:
                missing_metadata = True
                continue
            raise DeploymentError(
                "PostgreSQL Workspace identity, scope or engine differs from configuration"
            )
    if not row.get("workspace_id") and not owned:
        raise DeploymentError(
            "PostgreSQL Workspace identity, scope or engine differs from configuration"
        )
    actual = {t.get("key"): t.get("value") for t in row.get("workspace_tags") or []}
    for key, value in tags.items():
        if key in actual and actual.get(key) != value:
            raise DeploymentError(
                "PostgreSQL Workspace ownership tags differ from bootstrap state"
            )
    if missing_metadata or not row.get("workspace_id"):
        raise PGNotReady("PostgreSQL Workspace metadata is not ready yet")
    if owned and any(key not in actual for key in tags):
        raise PGNotReady("PostgreSQL Workspace ownership tags are not ready yet")


async def ensure_workspace(store, cloud, settings, scope, account, region, purpose):
    name = (
        settings.admin_workspace_name
        if purpose == "admin"
        else settings.business_workspace_name
    )
    explicit = (
        settings.admin_workspace_id
        if purpose == "admin"
        else settings.business_workspace_id
    )
    tags = {"veadk-pg-scope": scope, "veadk-pg-purpose": purpose}
    config = json.dumps([name, "PostgreSQL_17"])
    record = store.read(scope, purpose)
    if record and record[0] != config:
        raise DeploymentError(
            "PostgreSQL bootstrap configuration changed; migrate explicitly before retrying"
        )
    ident = record[1] if record else ""
    owned = bool(record and record[2])
    if explicit and ident and explicit != ident:
        raise DeploymentError(
            "Configured Workspace ID differs from recorded bootstrap identity"
        )
    ident = ident or explicit
    dispatched = False
    validation = dict(
        account=account,
        region=region,
        project=settings.project_name,
        name=name,
        tags=tags,
    )
    while True:
        if not ident:
            retired = store.failed_ids(scope, purpose)
            candidates, failed = [], []
            for row in await cloud.find(settings.project_name, name):
                candidate_id = row.get("workspace_id")
                if candidate_id in retired:
                    if row.get("workspace_status") != "CreateFailed":
                        raise DeploymentError(
                            "Retired PostgreSQL Workspace state changed; inspect AIDAP before retrying"
                        )
                    continue
                if row.get("workspace_status") == "CreateFailed":
                    # Confirm terminal creation failure before changing local state.
                    validate_workspace(row, **validation, owned=False)
                    row = await cloud.detail(candidate_id)
                if row.get("workspace_status") == "CreateFailed":
                    validate_workspace(row, **validation, owned=False)
                    failed.append(row["workspace_id"])
                else:
                    candidates.append(row)
            if len(candidates) > 1 or record and not candidates and len(failed) > 1:
                raise DeploymentError(
                    "Multiple PostgreSQL Workspaces match; configure an explicit Workspace ID"
                )
            for failed_id in failed:
                clear_intent = bool(owned and record and not candidates)
                store.retire_failed(
                    scope, purpose, failed_id, clear_intent=clear_intent
                )
                if clear_intent:
                    record, owned = None, False
            if candidates:
                row = candidates[0]
                try:
                    validate_workspace(row, **validation, owned=owned)
                except PGNotReady:
                    # Owned discovery metadata is subject to the same readiness wait.
                    if not row.get("workspace_id"):
                        raise
                ident = row["workspace_id"]
            elif record:
                raise DeploymentError(
                    "Previous Workspace creation outcome is uncertain; inspect AIDAP and recover by Workspace ID"
                )
            else:
                store.save(scope, purpose, config, "", True)
                owned, dispatched = True, True
                try:
                    ident = await cloud.create(name, settings.project_name, tags)
                except asyncio.CancelledError:
                    raise
                except PGCloudError as exc:
                    if exc.code.split(".")[0] in {
                        "AccessDenied",
                        "Forbidden",
                        "Unauthorized",
                        "InvalidAccessKeyId",
                        "SignatureDoesNotMatch",
                        "InvalidToken",
                        "ExpiredToken",
                        "InvalidParameter",
                        "InvalidParameterValue",
                        "MissingParameter",
                    }:
                        store.rejected(scope, purpose)
                    raise
                except Exception:
                    raise DeploymentError(
                        "Workspace creation outcome is uncertain; inspect AIDAP before retrying"
                    ) from None
        if explicit and not (record and record[1]):
            # Validate adoption before pinning an operator-supplied identity.
            row = await cloud.detail(ident)
            validate_workspace(row, **validation, owned=owned)
        store.save(scope, purpose, config, ident, owned)
        try:
            try:
                row = await cloud.detail(ident)
            except PGCloudError as exc:
                if owned and exc.code.split(".")[0] in {
                    "ResourceNotFound",
                    "NotFound",
                }:
                    raise PGNotReady(
                        "PostgreSQL Workspace detail is not visible yet"
                    ) from None
                raise
            if row.get("workspace_status") == "CreateFailed" and owned and not explicit:
                validate_workspace(row, **validation, owned=False)
                store.retire_failed(scope, purpose, ident, clear_intent=True)
                if dispatched:
                    raise DeploymentError(
                        "PostgreSQL Workspace creation failed; correct AIDAP permissions or configuration before retrying"
                    )
                ident, record, owned = "", None, False
                continue
            try:
                validate_workspace(row, **validation, owned=owned)
            except PGNotReady:
                # Terminal/unknown states cannot masquerade as delayed metadata.
                check_ready(row.get("workspace_status"))
                raise
            check_ready(row.get("workspace_status"))
            connection = await cloud.connection(ident)
            return ident, connection
        except PGNotReady:
            await asyncio.sleep(3)


async def prepare_postgres(
    profile, cloud, account, *, progress=lambda stage: None, source_url=""
):
    settings = profile.managed.postgres
    if settings is None or settings.mode != "auto":
        return profile
    if profile.shared_url and not source_url:
        raise DeploymentError(
            "Legacy registry connection is configured; migrate with init-admin-db and remove the legacy registry URL before automatic provisioning"
        )
    if profile.admin_url and not settings.business_workspace_id:
        raise DeploymentError(
            "Adopting existing business databases requires an explicit business Workspace ID"
        )
    scope = hashlib.sha256(
        json.dumps([account, profile.region, settings.project_name]).encode()
    ).hexdigest()[:32]

    async def prepare():
        store = BootstrapStore(settings.bootstrap_path)
        async with store.lock(scope):
            progress("admin_workspace")
            admin_id, admin_connection = await ensure_workspace(
                store, cloud, settings, scope, account, profile.region, "admin"
            )
            progress("business_workspace")
            business_id, business_connection = await ensure_workspace(
                store, cloud, settings, scope, account, profile.region, "business"
            )
            admin, business = make_url(admin_connection), make_url(business_connection)
            if profile.admin_url:
                old = make_url(profile.admin_url)
                if ((old.host or "").lower(), old.port or 5432) != (
                    (business.host or "").lower(),
                    business.port or 5432,
                ):
                    raise DeploymentError(
                        "Existing business PostgreSQL endpoint changed; explicitly adopt or migrate before provisioning"
                    )
            managed = profile.managed.model_copy(deep=True)
            managed.postgres = settings.model_copy(
                update={
                    "mode": "manual",
                    "admin_workspace_id": admin_id,
                    "business_workspace_id": business_id,
                }
            )
            env = {
                "PGHOST": business.host or "",
                "PGPORT": str(business.port or 5432),
                "PGUSER": business.username or "",
                "PGPASSWORD": business.password or "",
                "PGSSLMODE": str(business.query.get("sslmode", "require")),
            }
            managed.runtime.env = {**managed.runtime.env, **env}
            values = {
                **profile.values,
                **{k.lower().replace("pg", "pg_", 1): v for k, v in env.items()},
            }
            values["pg_database"] = business.database
            resolved = replace(
                profile,
                managed=managed,
                values=values,
                admin_url=business_connection,
                shared_url=admin.set(database=ADMIN_DATABASE_NAME).render_as_string(
                    hide_password=False
                ),
            )
            validate_postgres_layout(resolved)
            progress("admin_database")
            await initialize_admin_database(
                resolved, source_url=source_url, maintenance_url=admin_connection
            )
            return resolved

    try:
        return await asyncio.wait_for(prepare(), timeout=settings.timeout_seconds)
    except asyncio.TimeoutError:
        raise DeploymentError(
            "PostgreSQL preparation timed out; retry with the same agent ID and bootstrap state"
        ) from None
    except DeploymentError:
        raise
    except Exception:
        raise DeploymentError(
            "PostgreSQL preparation failed; check bootstrap state, IAM permissions and connectivity"
        ) from None
