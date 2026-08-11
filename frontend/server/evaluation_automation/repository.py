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

"""Persistence adapters for automatic evaluations and optimization snapshots."""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

from veadk.integrations.agentkit.evaluation import AgentKitOpenApiError

from .models import AutoEvaluationCase, OptimizationSnapshot

AUTO_FIELD_KEYS = (
    "input",
    "reference_output",
    "output",
    "feedback_comment",
    "agent_name",
    "session_id",
    "message_id",
    "runtime_id",
    "invocation_id",
    "user_id",
    "created_at",
    "source",
    "score",
    "reason",
    "evaluator_version",
)
_MAX_DATASET_NAME_LENGTH = 50
_DUPLICATE_DATASET_ERROR_CODE = "601104504"
_LOOKUP_DELAYS = (0.25, 0.5, 1.0, 2.0, 4.0)
_OPTIMIZATION_KEY_PREFIX = "veadk-studio/v1/evaluation-optimizations"
_MAX_OPTIMIZATION_BYTES = 8 * 1024 * 1024


class AgentKitPost(Protocol):
    async def __call__(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class _SetRef:
    id: str
    workspace_id: str
    name: str


def auto_set_name(agent_name: str, kind: str) -> str:
    if kind not in {"good", "bad"}:
        raise ValueError(f"unsupported automatic evaluation kind: {kind}")
    suffix = f"_auto_{kind}_case"
    normalized = re.sub(r"\s+", "_", agent_name.strip()) or "agent"
    return f"{normalized[: _MAX_DATASET_NAME_LENGTH - len(suffix)]}{suffix}"


def auto_item_key(
    *,
    project_name: str,
    runtime_id: str,
    session_id: str,
    message_id: str,
    evaluator_version: str,
) -> str:
    value = (
        f"auto\0{project_name}\0{runtime_id}\0{session_id}\0{message_id}\0"
        f"{evaluator_version}"
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AgentKitAutoEvaluationRepository:
    """Store automatic cases in AgentKit datasets separate from user feedback."""

    def __init__(self, post: AgentKitPost, *, project_name: str) -> None:
        self._post = post
        self._project_name = project_name.strip() or "default"
        self._workspace_id: str | None = None

    @property
    def _project_query(self) -> dict[str, str]:
        return {"ProjectName": self._project_name}

    async def upsert(self, case: AutoEvaluationCase) -> AutoEvaluationCase:
        evaluation_set = await self._ensure_set(case.agent_name, case.kind)
        fields = case.field_values()
        response = await self._post(
            action="BatchCreateEvaluationSetItems",
            query={
                **self._project_query,
                "WorkspaceId": evaluation_set.workspace_id,
                "EvaluationSetId": evaluation_set.id,
            },
            payload={
                "Items": [
                    {
                        "ItemKey": case.item_key,
                        "Turns": [
                            {
                                "Id": "0",
                                "FieldDataList": [
                                    {
                                        "Key": key,
                                        "Name": key,
                                        "Content": {
                                            "ContentType": "Text",
                                            "Text": fields.get(key, ""),
                                        },
                                    }
                                    for key in AUTO_FIELD_KEYS
                                ],
                            }
                        ],
                    }
                ],
                "SkipInvalidItems": False,
                "AllowPartialAdd": False,
            },
        )
        outputs = (response.get("Result") or {}).get("ItemOutputs") or []
        if not outputs or not outputs[0].get("ItemId"):
            raise RuntimeError("AgentKit did not return the automatic evaluation item")
        return case.model_copy(
            update={
                "id": str(outputs[0]["ItemId"]),
                "evaluation_set_id": evaluation_set.id,
                "evaluation_set_name": evaluation_set.name,
                "workspace_id": evaluation_set.workspace_id,
            }
        )

    async def list_cases(
        self,
        *,
        agent_name: str,
        page_size: int = 100,
    ) -> list[AutoEvaluationCase]:
        workspace_id = await self._resolve_workspace_id()
        result: list[AutoEvaluationCase] = []
        for kind in ("good", "bad"):
            name = auto_set_name(agent_name, kind)
            evaluation_set = await self._find_set(name, workspace_id=workspace_id)
            if evaluation_set is None:
                evaluation_set = await self._find_set(
                    self._fallback_name(name, workspace_id),
                    workspace_id=workspace_id,
                )
            if evaluation_set is None:
                continue
            response = await self._post(
                action="ListEvaluationSetItems",
                query={
                    **self._project_query,
                    "WorkspaceId": workspace_id,
                    "EvaluationSetId": evaluation_set.id,
                },
                payload={"PageNumber": 1, "PageSize": max(1, min(page_size, 200))},
            )
            for item in _extract_items(response):
                fields = _extract_fields(item)
                try:
                    score = float(fields.get("score", ""))
                except ValueError:
                    continue
                result.append(
                    AutoEvaluationCase(
                        id=str(item.get("ItemId") or item.get("Id") or ""),
                        itemKey=str(item.get("ItemKey") or ""),
                        kind=kind,
                        input=fields.get("input", ""),
                        output=fields.get("output", ""),
                        referenceOutput=fields.get("reference_output", ""),
                        comment=fields.get("feedback_comment", ""),
                        agentName=fields.get("agent_name", agent_name),
                        sessionId=fields.get("session_id", ""),
                        messageId=fields.get("message_id", ""),
                        runtimeId=fields.get("runtime_id", ""),
                        invocationId=fields.get("invocation_id", ""),
                        userId=fields.get("user_id", ""),
                        createdAt=fields.get("created_at", ""),
                        evaluationSetId=evaluation_set.id,
                        evaluationSetName=evaluation_set.name,
                        workspaceId=evaluation_set.workspace_id,
                        score=score,
                        reason=fields.get("reason", ""),
                        evaluatorVersion=fields.get("evaluator_version", "v1"),
                    )
                )
        return result

    async def _ensure_set(self, agent_name: str, kind: str) -> _SetRef:
        workspace_id = await self._resolve_workspace_id()
        name = auto_set_name(agent_name, kind)
        fallback = self._fallback_name(name, workspace_id)
        for candidate in (name, fallback):
            existing = await self._find_set(candidate, workspace_id=workspace_id)
            if existing is not None:
                return existing
        try:
            return await self._create_set(name, workspace_id=workspace_id)
        except AgentKitOpenApiError as error:
            if error.code != _DUPLICATE_DATASET_ERROR_CODE:
                raise
            existing = await self._wait_for_set(name, workspace_id=workspace_id)
            if existing is not None:
                return existing
        return await self._create_set(fallback, workspace_id=workspace_id)

    async def _create_set(self, name: str, *, workspace_id: str) -> _SetRef:
        response = await self._post(
            action="CreateEvaluationSet",
            query={**self._project_query, "WorkspaceId": workspace_id},
            payload={
                "Name": name,
                "Description": "AgentKit Studio 会话静默自动评测集",
                "EvaluationSetSchema": {
                    "FieldSchemas": [
                        {
                            "Key": key,
                            "Name": key,
                            "ContentType": "Text",
                            "TextSchema": '{"type":"string"}',
                            "Status": 1,
                            "DefaultDisplayFormat": 1,
                            "IsRequired": key
                            in {"input", "output", "session_id", "message_id"},
                            "Hidden": False,
                        }
                        for key in AUTO_FIELD_KEYS
                    ]
                },
            },
        )
        created_id = str((response.get("Result") or {}).get("EvaluationSetId") or "")
        if not created_id:
            raise RuntimeError("AgentKit did not return an automatic evaluation set ID")
        visible = await self._wait_for_set(name, workspace_id=workspace_id)
        if visible is None or visible.id != created_id:
            raise RuntimeError("AgentKit automatic evaluation set is not visible")
        return visible

    async def _resolve_workspace_id(self) -> str:
        if self._workspace_id:
            return self._workspace_id
        response = await self._post(
            action="ListEvaluationSets",
            query=self._project_query,
            payload={"PageNumber": 1, "PageSize": 1},
        )
        for item in (response.get("Result") or {}).get("EvaluationSets") or []:
            version = item.get("EvaluationSetVersion") or {}
            workspace_id = str(
                item.get("WorkspaceId") or version.get("WorkspaceId") or ""
            )
            if workspace_id:
                self._workspace_id = workspace_id
                return workspace_id
        raise RuntimeError("AgentKit account does not expose an evaluation workspace")

    async def _find_set(self, name: str, *, workspace_id: str) -> _SetRef | None:
        response = await self._post(
            action="ListEvaluationSets",
            query={**self._project_query, "WorkspaceId": workspace_id},
            payload={"Name": name, "PageNumber": 1, "PageSize": 100},
        )
        for item in (response.get("Result") or {}).get("EvaluationSets") or []:
            if str(item.get("Name") or "") != name:
                continue
            version = item.get("EvaluationSetVersion") or {}
            resolved_workspace_id = str(
                item.get("WorkspaceId") or version.get("WorkspaceId") or ""
            )
            item_id = str(item.get("Id") or "")
            if not item_id or not resolved_workspace_id:
                raise RuntimeError("AgentKit evaluation set has invalid identifiers")
            return _SetRef(item_id, resolved_workspace_id, name)
        return None

    async def _wait_for_set(self, name: str, *, workspace_id: str) -> _SetRef | None:
        for delay in _LOOKUP_DELAYS:
            await asyncio.sleep(delay)
            existing = await self._find_set(name, workspace_id=workspace_id)
            if existing is not None:
                return existing
        return None

    @staticmethod
    def _fallback_name(name: str, workspace_id: str) -> str:
        digest = hashlib.sha256(f"{workspace_id}\0{name}".encode()).hexdigest()
        suffix = f"_{digest[:8]}"
        return f"{name[: _MAX_DATASET_NAME_LENGTH - len(suffix)]}{suffix}"


class InMemoryOptimizationRepository:
    """Process-local fallback used when Studio storage is not configured."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], OptimizationSnapshot] = {}

    async def put(self, snapshot: OptimizationSnapshot) -> None:
        self._items[(snapshot.runtime_id, snapshot.app_name)] = snapshot

    async def get(
        self,
        runtime_id: str,
        app_name: str,
    ) -> OptimizationSnapshot | None:
        return self._items.get((runtime_id, app_name))


class TosOptimizationRepository:
    """Persist the latest optimization snapshot for each Runtime application."""

    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
    ) -> None:
        if not bucket.strip():
            raise ValueError("TOS optimization storage requires a bucket.")
        self._bucket = bucket
        self._client_factory = client_factory

    async def put(self, snapshot: OptimizationSnapshot) -> None:
        await asyncio.to_thread(self._put, snapshot)

    def _put(self, snapshot: OptimizationSnapshot) -> None:
        content = snapshot.model_dump_json(by_alias=True).encode("utf-8")
        self._client_factory().put_object(
            bucket=self._bucket,
            key=self._key(snapshot.runtime_id, snapshot.app_name),
            content=content,
            content_type="application/json",
        )

    async def get(
        self,
        runtime_id: str,
        app_name: str,
    ) -> OptimizationSnapshot | None:
        return await asyncio.to_thread(self._get, runtime_id, app_name)

    def _get(
        self,
        runtime_id: str,
        app_name: str,
    ) -> OptimizationSnapshot | None:
        import tos

        try:
            response = self._client_factory().get_object(
                bucket=self._bucket,
                key=self._key(runtime_id, app_name),
            )
        except tos.exceptions.TosServerError as error:
            if error.status_code == 404:
                return None
            raise
        content = b"".join(response)
        if len(content) > _MAX_OPTIMIZATION_BYTES:
            raise ValueError("Studio optimization snapshot is too large.")
        return OptimizationSnapshot.model_validate_json(content)

    @staticmethod
    def _key(runtime_id: str, app_name: str) -> str:
        runtime_segment = quote(runtime_id, safe="")
        app_segment = quote(app_name, safe="")
        return f"{_OPTIMIZATION_KEY_PREFIX}/{runtime_segment}/{app_segment}.json"


def _extract_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    result = response.get("Result") or {}
    for key in ("Items", "EvaluationSetItems", "ItemDetails", "EvaluationItems"):
        value = result.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _extract_fields(item: dict[str, Any]) -> dict[str, str]:
    turns = item.get("Turns")
    turn = turns[0] if isinstance(turns, list) and turns else {}
    if not isinstance(turn, dict):
        turn = {}
    field_data = (
        turn.get("FieldDataList")
        or turn.get("FieldData")
        or item.get("FieldDataList")
        or item.get("FieldData")
        or []
    )
    result: dict[str, str] = {}
    if not isinstance(field_data, list):
        return result
    for field in field_data:
        if not isinstance(field, dict):
            continue
        key = str(field.get("Key") or field.get("Name") or "")
        content = field.get("Content")
        if not key:
            continue
        if isinstance(content, dict):
            result[key] = str(content.get("Text") or content.get("Value") or "")
        elif content is not None:
            result[key] = str(content)
    return result
