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

"""Read-only, bounded MPA name checks before cloud prerequisites are purchased."""

from __future__ import annotations

import asyncio

from .config import ConfigurationError, validate_runtime_name
from .database import DeploymentError, agent_suffix
from .pg_bootstrap import (
    agent_business_scope,
    named_business_workspace,
    validate_workspace,
)
from .pg_cloud import PGCloud
from .runtime import env_map
from .worker import WorkerCloud

ERROR_KEYS = {"runtimeNameTaken", "runtimeNameCheckFailed"}


class NameCheckError(DeploymentError):
    def __init__(self, key="runtimeNameCheckFailed"):
        self.key = key
        super().__init__(key)


def tags(values):
    return {
        item.get("Key", item.get("key")): item.get("Value", item.get("value"))
        for item in values or []
    }


async def check_creation_name(
    profile, cloud, *, agent_id, name, owner="", verified_creation_account=""
):
    """Return only verified account identity; never return matching resource details."""
    name = validate_runtime_name(name)

    async def check():
        account = await cloud.account_id()
        expected = profile.values.get("account_id", "")
        if expected and expected != account:
            raise NameCheckError()
        if verified_creation_account and verified_creation_account != account:
            raise NameCheckError()
        worker = WorkerCloud(cloud)
        runtimes, workers = await asyncio.gather(
            cloud.find_runtimes(name), worker.find(name)
        )
        if len(runtimes) > 1 or len(workers) > 1:
            raise NameCheckError("runtimeNameTaken")
        for item in runtimes:
            current = await cloud.get(item["RuntimeId"])
            listed = tags(item.get("Tags"))
            detailed = tags(current.get("Tags"))
            if any(
                key in listed and key in detailed and listed[key] != detailed[key]
                for key in ("veadk:owner", "veadk:mpa-instance-id")
            ):
                raise NameCheckError("runtimeNameTaken")
            # GetRuntime's SDK shape omits Tags; matching list metadata owns them.
            provenance = {**listed, **detailed}
            if (
                env_map(current).get("MPA_AGENT_ID") != agent_id
                or provenance.get("veadk:mpa-instance-id", agent_id) != agent_id
                or owner
                and provenance.get("veadk:owner") != owner
                and not (
                    bool(verified_creation_account)
                    and verified_creation_account == account
                    and not provenance.get("veadk:owner")
                )
            ):
                raise NameCheckError("runtimeNameTaken")
        worker_owned = {
            "managed_by": "mpa-deployment",
            "mpa_agent_key": agent_suffix(account, profile.region, agent_id),
        }
        for item in workers:
            current = await worker.get(item["ToolId"])
            provenance = tags(current.get("Tags"))
            if env_map(current).get("MPA_AGENT_ID") != agent_id or any(
                provenance.get(key) != value for key, value in worker_owned.items()
            ):
                raise NameCheckError("runtimeNameTaken")
        settings = profile.managed.postgres
        if settings and settings.business_database_name == "aidb":
            pg = PGCloud(
                region=profile.region,
                credentials=cloud._credentials,
                provider=profile.provider,
            )
            workspaces = await pg.find(
                settings.project_name, named_business_workspace(name)
            )
            expected_tags = {
                "veadk-pg-scope": agent_business_scope(
                    account, profile.region, settings.project_name, agent_id
                ),
                "veadk-pg-purpose": "business",
                "veadk-pg-database": "aidb",
            }
            if len(workspaces) > 1:
                raise NameCheckError("runtimeNameTaken")
            for current in workspaces:
                actual = tags(current.get("workspace_tags"))
                if any(
                    actual.get(key) != value for key, value in expected_tags.items()
                ):
                    raise NameCheckError("runtimeNameTaken")
                validate_workspace(
                    current,
                    account=account,
                    region=profile.region,
                    project=settings.project_name,
                    name=named_business_workspace(name),
                    tags=expected_tags,
                    owned=True,
                )
        return account

    try:
        return await asyncio.wait_for(check(), timeout=30)
    except (NameCheckError, ConfigurationError):
        raise
    except asyncio.CancelledError:
        raise
    except Exception:
        raise NameCheckError() from None
