"""AIDAP SDK adapter using refreshed, account-verified deployment credentials."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from sqlalchemy.engine import URL

from .database import DeploymentError


def _debug_event(hypothesis: str, location: str, message: str, data: dict) -> None:
    url = os.getenv("DEBUG_SERVER_URL", "").strip()
    session_id = os.getenv("DEBUG_SESSION_ID", "").strip()
    if not url or not session_id:
        return
    try:
        import urllib.request

        payload = {
            "sessionId": session_id,
            "runId": "pre-fix",
            "hypothesisId": hypothesis,
            "location": location,
            "msg": message,
            "data": data,
        }
        urllib.request.urlopen(
            urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=1,
        ).read()
    except Exception:  # noqa: BLE001, S110
        pass


class PGCloudError(DeploymentError):
    def __init__(self, method, code):
        self.code = code
        super().__init__(
            f"AIDAP {method} failed ({code}); check deployment permissions and connectivity"
        )


class PGNotReady(DeploymentError):
    """A discovered resource is still being prepared by AIDAP."""


def check_ready(status):
    value = str(status or "").strip().lower()
    if value in {"running", "ready", "available", "active", "normal"}:
        return
    if value in {
        "creating",
        "updating",
        "modifying",
        "pending",
        "initializing",
        "init",
        "syncing",
        "starting",
    }:
        raise PGNotReady("PostgreSQL resource is not ready yet")
    raise DeploymentError(
        "PostgreSQL resource has an unsupported or failed state; check AIDAP console"
    )


def one(rows, key, preferred=None):
    candidates = [r for r in rows if r.get(key)]
    if preferred is not None:
        selected = [r for r in candidates if r.get(key) == preferred]
        if selected:
            candidates = selected
    if not candidates:
        raise PGNotReady("PostgreSQL connection resources are not ready yet")
    if len(candidates) != 1:
        raise DeploymentError(
            "Ambiguous PostgreSQL connection resources; check AIDAP configuration"
        )
    return candidates[0]


def parse_connection(result):
    """Parse provider parameters without logging or shell evaluation."""
    examples = [
        e
        for e in result.get("connection_examples") or []
        if str(e.get("connection_type", "")).lower() == "parameters"
    ]
    if len(examples) != 1:
        raise DeploymentError(
            "AIDAP did not return unique PostgreSQL connection parameters"
        )
    values = {}
    for line in str(examples[0].get("connection_example") or "").splitlines():
        key, separator, value = line.strip().partition("=")
        if not separator:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        if key in values:
            raise DeploymentError(
                "AIDAP returned duplicate PostgreSQL connection parameters"
            )
        values[key] = value
    try:
        if not all(
            values.get(k) for k in ("PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE")
        ):
            raise ValueError
        port = int(values.get("PGPORT", "5432"))
        sslmode = values.get("PGSSLMODE", "require")
        if not 1 <= port <= 65535 or sslmode not in {
            "require",
            "verify-ca",
            "verify-full",
        }:
            raise ValueError
        return URL.create(
            "postgresql",
            username=values["PGUSER"],
            password=values["PGPASSWORD"],
            host=values["PGHOST"],
            port=port,
            database=values["PGDATABASE"],
            query={"sslmode": sslmode},
        ).render_as_string(hide_password=False)
    except Exception:  # noqa: BLE001
        raise DeploymentError(
            "AIDAP returned invalid or insecure PostgreSQL connection parameters"
        ) from None


class PGCloud:
    def __init__(self, *, region, credentials):
        self.region, self.credentials = region, credentials

    async def call(self, method, request_type, **params):
        def run():
            import volcenginesdkaidap
            import volcenginesdkcore

            credential = self.credentials()
            _debug_event(
                "A-B",
                "pg_cloud.py:call:start",
                "[DEBUG] Starting AIDAP request",
                {
                    "method": method,
                    "requestType": request_type,
                    "region": self.region,
                    "parameterNames": sorted(params),
                    "hasSessionToken": bool(credential.session_token),
                },
            )
            config: Any = volcenginesdkcore.Configuration()
            config.ak, config.sk = (
                credential.access_key_id,
                credential.secret_access_key,
            )
            config.session_token, config.region = credential.session_token, self.region
            config.host = "open.volcengineapi.com"
            config.auto_retry = (
                False  # CreateWorkspace has no client idempotency token.
            )
            client = volcenginesdkcore.ApiClient(config)
            try:
                api = volcenginesdkaidap.AIDAPApi(client)
                request = getattr(volcenginesdkaidap, request_type)(**params)
                result = getattr(api, method)(request, _request_timeout=30).to_dict()
                _debug_event(
                    "B-D",
                    "pg_cloud.py:call:success",
                    "[DEBUG] AIDAP request succeeded",
                    {"method": method, "resultKeys": sorted(result)},
                )
                return result
            finally:
                client.rest_client.pool_manager.clear()

        try:
            return await asyncio.to_thread(run)
        except DeploymentError:
            raise
        except Exception as exc:  # noqa: BLE001
            try:
                code = json.loads(getattr(exc, "body", "") or "{}")["ResponseMetadata"][
                    "Error"
                ]["Code"]
                if not isinstance(code, str) or not code.replace(".", "").isalnum():
                    raise ValueError
            except (ValueError, TypeError, KeyError):
                code = "CloudRequestFailed"
            _debug_event(
                "B-C",
                "pg_cloud.py:call:error",
                "[DEBUG] AIDAP request failed",
                {"method": method, "code": code, "errorType": type(exc).__name__},
            )
            raise PGCloudError(method, code) from None

    async def listing(self, method, request, collection, **params):
        rows = []
        for offset in range(0, 100000, 100):
            result = await self.call(
                method, request, limit=100, offset=offset, **params
            )
            batch = result.get(collection)
            if not isinstance(batch, list):
                raise DeploymentError("Invalid AIDAP discovery response")
            if batch and any(row in rows for row in batch):
                raise DeploymentError("AIDAP discovery repeated a page")
            rows.extend(batch)
            if len(batch) < 100:
                return rows
        raise DeploymentError("AIDAP discovery exceeded pagination limit")

    async def find(self, project, name):
        rows = await self.listing(
            "describe_workspaces",
            "DescribeWorkspacesRequest",
            "workspaces",
            project_name=project,
            search=name,
        )
        matches = [r for r in rows if r.get("workspace_name") == name]
        _debug_event(
            "C-D",
            "pg_cloud.py:find",
            "[DEBUG] Completed Workspace discovery",
            {
                "project": project,
                "name": name,
                "matchCount": len(matches),
                "matches": [
                    {
                        key: row.get(key)
                        for key in (
                            "workspace_id",
                            "account_id",
                            "region_id",
                            "project_name",
                            "workspace_name",
                            "workspace_status",
                        )
                    }
                    for row in matches
                ],
            },
        )
        return matches

    async def detail(self, ident):
        result = await self.call(
            "describe_workspace_detail",
            "DescribeWorkspaceDetailRequest",
            workspace_id=ident,
        )
        row = result.get("workspace")
        if not isinstance(row, dict) or row.get("workspace_id") != ident:
            raise DeploymentError(
                "Recorded PostgreSQL Workspace is missing; restore it or explicitly migrate"
            )
        return row

    async def create(self, name, project, tags):
        import volcenginesdkaidap as sdk

        result = await self.call(
            "create_workspace",
            "CreateWorkspaceRequest",
            workspace_name=name,
            project_name=project,
            engine_version="PostgreSQL_17",
            workspace_tags=[
                sdk.WorkspaceTagForCreateWorkspaceInput(key=k, value=v)
                for k, v in tags.items()
            ],
        )
        ident = result.get("workspace_id") or (result.get("workspace") or {}).get(
            "workspace_id"
        )
        if not ident:
            raise DeploymentError(
                "AIDAP creation outcome is uncertain; discover the Workspace before retrying"
            )
        return ident

    async def connection(self, ident):
        params = {"workspace_id": ident}
        branches = await self.listing(
            "describe_branches", "DescribeBranchesRequest", "branches", **params
        )
        branch = one(branches, "branch_name", "main")
        check_ready(branch.get("branch_status"))
        if not branch.get("branch_id"):
            raise DeploymentError("AIDAP returned an invalid main branch")
        params["branch_id"] = branch["branch_id"]
        result = await self.call(
            "describe_computes",
            "DescribeComputesRequest",
            service_type="Database",
            **params,
        )
        computes = [c for c in result.get("computes") or [] if not c.get("disabled")]
        primary = [
            c
            for c in computes
            if str(c.get("compute_role", "")).lower()
            in {"primary", "readwrite", "read_write"}
        ]
        compute = one(primary or computes, "compute_id")
        check_ready(compute.get("compute_status"))
        connection = {**params, "compute_id": compute["compute_id"]}
        endpoints = await self.call(
            "describe_workspace_endpoint",
            "DescribeWorkspaceEndpointRequest",
            **connection,
        )
        addresses = [
            a
            for e in endpoints.get("endpoints") or []
            for a in e.get("addresses") or []
            if str(a.get("address_type", "")).lower() == "public"
        ]
        connection["address_id"] = one(addresses, "address_id")["address_id"]
        accounts = await self.listing(
            "describe_db_accounts", "DescribeDBAccountsRequest", "accounts", **params
        )
        databases = await self.listing(
            "describe_databases", "DescribeDatabasesRequest", "databases", **params
        )
        connection["account_name"] = one(accounts, "account_name", "user_admin")[
            "account_name"
        ]
        connection["database_name"] = one(databases, "database_name", "aidb")[
            "database_name"
        ]
        result = await self.call(
            "describe_db_account_connection",
            "DescribeDBAccountConnectionRequest",
            **connection,
        )
        return parse_connection(result)
