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

"""Studio-owned AgentKit Runtime operations used by the independent verifier."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from collections.abc import Callable

from frontend.server.intelligent_development import CommandResult, StudioCredentials

RegionResolver = Callable[[], str]
CredentialResolver = Callable[[], StudioCredentials]


class IntelligentDevelopmentRuntimeOperations:
    """Resolve validation Runtime names server-side and operate by immutable IDs."""

    def __init__(self, region_resolver: RegionResolver) -> None:
        self._region_resolver = region_resolver

    async def cleanup_stale_validation_runtimes(
        self,
        resolve_credentials: CredentialResolver,
        *,
        older_than: timedelta = timedelta(hours=1),
    ) -> int:
        """Best-effort reconciliation after a process dies mid-validation."""
        return await asyncio.to_thread(
            self._cleanup_stale_validation_runtimes,
            resolve_credentials(),
            older_than,
        )

    def _cleanup_stale_validation_runtimes(
        self,
        credentials: StudioCredentials,
        older_than: timedelta,
    ) -> int:
        from agentkit.sdk.runtime import types as runtime_types

        if older_than <= timedelta(0):
            raise ValueError("cleanup age must be positive")
        client = self._client(credentials)
        cutoff = datetime.now(timezone.utc) - older_than
        removed = 0
        next_token: str | None = None
        while True:
            response = client.list_runtimes(
                runtime_types.ListRuntimesRequest(
                    MaxResults=100,
                    NextToken=next_token,
                    TagFilters=[
                        runtime_types.TagFiltersItemForListRuntimes(
                            Key="veadk:lifecycle",
                            Values=["validation"],
                        )
                    ],
                )
            )
            for runtime in response.agent_kit_runtimes or []:
                if not runtime.runtime_id or not runtime.created_at:
                    continue
                try:
                    created = datetime.fromisoformat(
                        runtime.created_at.replace("Z", "+00:00")
                    )
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                if created <= cutoff:
                    client.delete_runtime(
                        runtime_types.DeleteRuntimeRequest(RuntimeId=runtime.runtime_id)
                    )
                    removed += 1
            next_token = response.next_token
            if not next_token:
                return removed

    async def __call__(
        self,
        operation: str,
        runtime_name: str,
        credentials: StudioCredentials,
        arguments: tuple[str, ...],
    ) -> CommandResult:
        return await asyncio.to_thread(
            self._run,
            operation,
            runtime_name,
            credentials,
            arguments,
        )

    def _client(self, credentials: StudioCredentials):
        from agentkit.sdk.runtime.client import AgentkitRuntimeClient

        return AgentkitRuntimeClient(
            access_key=credentials.access_key_id,
            secret_key=credentials.secret_access_key,
            session_token=credentials.session_token or "",
            region=self._region_resolver(),
        )

    @staticmethod
    def _runtime(client, runtime_name: str):
        from agentkit.sdk.runtime import types as runtime_types

        request = runtime_types.ListRuntimesRequest(
            Filters=[
                runtime_types.FiltersItemForListRuntimes(
                    Name="Name",
                    Values=[runtime_name],
                )
            ],
            MaxResults=10,
        )
        response = client.list_runtimes(request)
        matches = [
            runtime
            for runtime in (response.agent_kit_runtimes or [])
            if runtime.name == runtime_name and runtime.runtime_id
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise RuntimeError("Validation Runtime identity is ambiguous")
        return matches[0]

    def _run(
        self,
        operation: str,
        runtime_name: str,
        credentials: StudioCredentials,
        arguments: tuple[str, ...],
    ) -> CommandResult:
        from agentkit.sdk.runtime import types as runtime_types

        client = self._client(credentials)
        runtime = self._runtime(client, runtime_name)
        if operation == "delete":
            if runtime is None:
                return CommandResult(0, '{"alreadyAbsent":true}')
            client.delete_runtime(
                runtime_types.DeleteRuntimeRequest(RuntimeId=runtime.runtime_id)
            )
            return CommandResult(0, json.dumps({"runtimeId": runtime.runtime_id}))
        if runtime is None:
            return CommandResult(1, stderr="Validation Runtime not found")
        if operation == "get":
            value = client.get_runtime(
                runtime_types.GetRuntimeRequest(RuntimeId=runtime.runtime_id)
            )
            return CommandResult(0, value.model_dump_json(by_alias=True))
        if operation == "tag":
            if len(arguments) != 1:
                raise ValueError("Validation Runtime tags are missing")
            raw_tags = json.loads(arguments[0])
            if not isinstance(raw_tags, list):
                raise ValueError("Validation Runtime tags are invalid")
            tags = [
                runtime_types.TagsItemForUpdateRuntime(
                    Key=item["Key"],
                    Value=item.get("Value"),
                )
                for item in raw_tags
                if isinstance(item, dict)
                and isinstance(item.get("Key"), str)
                and isinstance(item.get("Value"), str)
            ]
            if len(tags) != len(raw_tags):
                raise ValueError("Validation Runtime tags are invalid")
            client.update_runtime(
                runtime_types.UpdateRuntimeRequest(
                    RuntimeId=runtime.runtime_id,
                    Tags=tags,
                )
            )
            return CommandResult(0, json.dumps({"runtimeId": runtime.runtime_id}))
        if operation == "logs":
            instances = client.list_runtime_instances(
                runtime_types.ListRuntimeInstancesRequest(
                    RuntimeId=runtime.runtime_id
                )
            )
            logs: list[str] = []
            for instance in instances.instance_items or []:
                if not instance.instance_name:
                    continue
                response = client.get_runtime_instance_logs(
                    runtime_types.GetRuntimeInstanceLogsRequest(
                        RuntimeId=runtime.runtime_id,
                        InstanceName=instance.instance_name,
                        Limit=200,
                    )
                )
                if response.logs:
                    logs.append(response.logs)
            return CommandResult(0, "\n".join(logs))
        raise ValueError("Unsupported validation Runtime operation")


__all__ = ["IntelligentDevelopmentRuntimeOperations"]
