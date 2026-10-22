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

"""Conservative, resumable cleanup of an MPA's exclusive managed resources."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from typing import Any

from .database import AgentDeploymentRegistry, DeploymentError, agent_suffix
from .diagnostics import classify_error
from .runtime import env_map
from .worker import WorkerCloud


class ResourceDeletionError(DeploymentError):
    def __init__(self, stage: str, reason: str):
        self.stage, self.reason = stage, reason
        super().__init__(
            f"MPA cleanup failed ({stage}): {reason}. Check resources and permissions, then retry."
        )


class OwnedResourceCleanup:
    def __init__(
        self,
        *,
        entry,
        cloud,
        account: str,
        region: str,
        agent_id: str,
        runtime: dict,
        worker=None,
    ):
        self.entry, self.cloud = entry, cloud
        self.worker = worker if worker is not None else WorkerCloud(cloud)
        self.account, self.region, self.agent_id, self.runtime = (
            account,
            region,
            agent_id,
            runtime,
        )

    async def _plan(self):
        logging.getLogger(__name__).info(
            "MPA delete check stage=registry runtime_id=%s",
            self.runtime.get("RuntimeId", ""),
        )
        record = await self.entry.read() if self.entry is not None else {}
        if record and record.get("runtime_id") != self.runtime.get("RuntimeId"):
            raise ResourceDeletionError("ownership", "runtime_binding_conflict")
        from .database import has_active_image_update

        if has_active_image_update(record):
            raise ResourceDeletionError("ownership", "active_image_update")
        if record.get("pending"):
            raise ResourceDeletionError("ownership", "active_deployment")
        env = env_map(self.runtime)
        if env.get("MPA_AGENT_ID") and env["MPA_AGENT_ID"] != self.agent_id:
            raise ResourceDeletionError("ownership", "agent_binding_conflict")
        if (
            self.runtime.get("ToolId")
            and env.get("AGENTKIT_TOOL_ID")
            and self.runtime["ToolId"] != env["AGENTKIT_TOOL_ID"]
        ):
            raise ResourceDeletionError("worker_template", "resource_binding_conflict")
        resources = [
            (
                "worker_template",
                "worker_id",
                "worker_managed",
                self.runtime.get("ToolId") or env.get("AGENTKIT_TOOL_ID", ""),
            ),
            (
                "skill_space",
                "skill_space_id",
                "skill_space_managed",
                env.get("SKILL_SPACE_ID", ""),
            ),
        ]
        plan, retained = [], []
        candidates = []
        progress = record.get("deletion") or {}
        for stage, field, flag, bound in resources:
            resource_id = record.get(field) or bound
            if not resource_id:
                continue
            if bound and record.get(field) and bound != record[field]:
                raise ResourceDeletionError(stage, "resource_binding_conflict")
            if record.get(flag) is not True or not record.get(field):
                retained.append(
                    {"stage": stage, "resourceId": resource_id, "reason": "unproven"}
                )
            elif progress.get(stage) != "deleted":
                candidates.append((stage, field, resource_id))
        if candidates:
            assert self.entry is not None
            try:
                others = await self.entry.other_records()
                logging.getLogger(__name__).info(
                    "MPA delete check stage=runtime_references runtime_id=%s",
                    self.runtime.get("RuntimeId", ""),
                )
                runtimes = await self.cloud.list_runtimes()
            except Exception as exc:
                raise ResourceDeletionError("references", classify_error(exc)) from None
            suffix = agent_suffix(self.account, self.region, self.agent_id)
            for stage, field, resource_id in candidates:
                shared = any(
                    other.get(field) == resource_id and other.get("state") != "deleted"
                    for other in others
                )
                for runtime in runtimes:
                    values = env_map(runtime)
                    if runtime.get("RuntimeId") == self.runtime.get("RuntimeId"):
                        current_refs = (
                            {
                                value
                                for value in (
                                    runtime.get("ToolId"),
                                    values.get("AGENTKIT_TOOL_ID"),
                                )
                                if value
                            }
                            if stage == "worker_template"
                            else {values["SKILL_SPACE_ID"]}
                            if values.get("SKILL_SPACE_ID")
                            else set()
                        )
                        if current_refs and current_refs != {resource_id}:
                            raise ResourceDeletionError(
                                stage, "resource_binding_conflict"
                            )
                        continue
                    references = (
                        {runtime.get("ToolId"), values.get("AGENTKIT_TOOL_ID")}
                        if stage == "worker_template"
                        else {values.get("SKILL_SPACE_ID")}
                    )
                    shared |= resource_id in references
                if shared:
                    retained.append(
                        {"stage": stage, "resourceId": resource_id, "reason": "shared"}
                    )
                    continue
                try:
                    resource = (
                        await self.worker.get(resource_id)
                        if stage == "worker_template"
                        else await self.cloud.get_skill_space(resource_id)
                    )
                except Exception as exc:
                    if classify_error(exc) == "not_found":
                        plan.append(
                            {
                                "stage": stage,
                                "resourceId": resource_id,
                                "description": stage,
                                "count": 1,
                                "missing": True,
                            }
                        )
                        continue
                    raise ResourceDeletionError(stage, classify_error(exc)) from None
                tags = {
                    item["Key"]: item.get("Value")
                    for item in resource.get("Tags") or []
                }
                identity_key = "ToolId" if stage == "worker_template" else "Id"
                if (
                    resource.get(identity_key) != resource_id
                    or tags.get("managed_by") != "mpa-deployment"
                    or tags.get("mpa_agent_key") != suffix
                    or resource.get("ProjectName")
                    != (self.runtime.get("ProjectName") or "default")
                ):
                    raise ResourceDeletionError(stage, "ownership_conflict")
                if stage == "worker_template" and env_map(resource).get(
                    "MPA_AGENT_ID"
                ) not in (None, "", self.agent_id):
                    raise ResourceDeletionError(stage, "agent_binding_conflict")
                plan.append(
                    {
                        "stage": stage,
                        "resourceId": resource_id,
                        "description": stage,
                        "count": 1,
                    }
                )
        return record, plan, retained

    async def preview(self) -> dict[str, Any]:
        _, plan, retained = await self._plan()
        return {
            "cleanupPlan": [
                {k: v for k, v in item.items() if k != "missing"} for item in plan
            ],
            "retainedResources": retained,
        }

    async def delete_resources(self):
        # Revalidate both resources before the first destructive call.
        record, plan, _ = await self._plan()
        if self.entry is None or not record:
            return
        record["state"] = "deleting"
        await self.entry.save(record)
        for item in plan:
            stage, resource_id = item["stage"], item["resourceId"]
            record.setdefault("deletion", {})[stage] = "deleting"
            await self.entry.save(record)
            try:
                if not item.get("missing"):
                    if stage == "worker_template":
                        await self.worker.delete(resource_id)
                    else:
                        await self.cloud.delete_skill_space(resource_id)
            except Exception as exc:
                if classify_error(exc) != "not_found":
                    raise ResourceDeletionError(stage, classify_error(exc)) from None
            record["deletion"][stage] = "deleted"
            await self.entry.save(record)

    async def mark_runtime_deleted(self):
        if self.entry is not None:
            record = await self.entry.read()
            if record:
                record.update(state="deleted", pending=False)
                record.setdefault("deletion", {})["agentkit_runtime"] = "deleted"
                await self.entry.save(record)


@asynccontextmanager
async def owned_resource_cleanup(*, runtime: dict, agent_id: str, region: str, cloud):
    url = env_map(runtime).get("SHARED_APIG_DATABASE_URL", "")
    if not url:
        yield OwnedResourceCleanup(
            entry=None,
            cloud=cloud,
            account="",
            region=region,
            agent_id=agent_id,
            runtime=runtime,
        )
        return
    registry = None
    try:
        account = await cloud.account_id()
        registry = AgentDeploymentRegistry(url)
        async with registry.lock(account, region, agent_id) as entry:
            yield OwnedResourceCleanup(
                entry=entry,
                cloud=cloud,
                account=account,
                region=region,
                agent_id=agent_id,
                runtime=runtime,
            )
    finally:
        if registry is not None:
            await registry.close()
