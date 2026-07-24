# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Dataset operations for the AgentKit evaluation OpenAPI."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Protocol


class AgentKitOpenApiPost(Protocol):
    """Callable transport used by the AgentKit evaluation client."""

    async def __call__(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...


class AgentKitOpenApiError(RuntimeError):
    """Structured AgentKit OpenAPI application error."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message
        detail = f"{code}: {message}" if message else code
        super().__init__(f"AgentKit OpenAPI returned error: {detail}")


@dataclass(frozen=True)
class EvaluationSetRef:
    """Stable identifiers required by evaluation-set item APIs."""

    id: str
    workspace_id: str
    name: str


@dataclass(frozen=True)
class EvaluationItemRef:
    """Result of an idempotent evaluation item write."""

    id: str
    item_key: str
    is_new: bool


_FEEDBACK_FIELD_KEYS = (
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
)

_DUPLICATE_DATASET_ERROR_CODE = "601104504"
_DUPLICATE_LOOKUP_DELAYS = (0.25, 0.5, 1.0, 2.0, 4.0)


def _feedback_field_schemas() -> list[dict[str, Any]]:
    return [
        {
            "Key": key,
            "Name": key,
            "ContentType": "Text",
            "TextSchema": '{"type":"string"}',
            "Status": 1,
            "DefaultDisplayFormat": 1,
            "IsRequired": key in {"input", "output", "session_id", "message_id"},
            "Hidden": False,
        }
        for key in _FEEDBACK_FIELD_KEYS
    ]


def feedback_set_name(agent_name: str, rating: str) -> str:
    """Return the stable good/bad dataset name for an Agent."""
    if rating not in {"good", "bad"}:
        raise ValueError(f"unsupported feedback rating: {rating}")
    normalized = re.sub(r"\s+", "_", agent_name.strip())[:80] or "agent"
    return f"{normalized}_{rating}_case"


class AgentKitEvaluationDatasetsClient:
    """Minimal AgentKit evaluation-set client used by Studio feedback."""

    def __init__(
        self,
        post: AgentKitOpenApiPost,
        *,
        project_name: str,
    ) -> None:
        self._post = post
        self._project_name = project_name.strip() or "default"
        self._workspace_id: str | None = None

    @property
    def _project_query(self) -> dict[str, str]:
        return {"ProjectName": self._project_name}

    async def ensure_feedback_set(
        self,
        agent_name: str,
        rating: str,
    ) -> EvaluationSetRef:
        """Return the feedback set, creating it when absent."""
        name = feedback_set_name(agent_name, rating)
        workspace_id = await self._resolve_workspace_id()
        existing = await self._find_set(name, workspace_id=workspace_id)
        if existing is not None:
            return existing

        try:
            created = await self._post(
                action="CreateEvaluationSet",
                query={**self._project_query, "WorkspaceId": workspace_id},
                payload={
                    "Name": name,
                    "Description": "VeADK Studio 对话反馈自动回流评测集",
                    "EvaluationSetSchema": {
                        "FieldSchemas": _feedback_field_schemas(),
                    },
                },
            )
        except AgentKitOpenApiError as error:
            if error.code != _DUPLICATE_DATASET_ERROR_CODE:
                raise
            existing = await self._wait_for_set(name, workspace_id=workspace_id)
            if existing is not None:
                return existing
            raise
        created_id = str((created.get("Result") or {}).get("EvaluationSetId") or "")
        if not created_id:
            raise RuntimeError("AgentKit did not return the created evaluation set ID")
        visible = await self._wait_for_set(name, workspace_id=workspace_id)
        if visible is None:
            raise RuntimeError(
                "AgentKit created evaluation set is not visible in ListEvaluationSets"
            )
        if visible.id != created_id:
            raise RuntimeError(
                "AgentKit returned inconsistent evaluation set identifiers"
            )
        return visible

    async def _resolve_workspace_id(self) -> str:
        """Resolve the account's evaluation workspace from visible datasets."""
        if self._workspace_id is not None:
            return self._workspace_id
        response = await self._post(
            action="ListEvaluationSets",
            query=self._project_query,
            payload={"PageNumber": 1, "PageSize": 1},
        )
        items = (response.get("Result") or {}).get("EvaluationSets") or []
        for item in items:
            version = item.get("EvaluationSetVersion") or {}
            workspace_id = str(
                item.get("WorkspaceId") or version.get("WorkspaceId") or ""
            )
            if workspace_id:
                self._workspace_id = workspace_id
                return workspace_id
        raise RuntimeError("AgentKit account does not expose an evaluation workspace")

    async def upsert_item(
        self,
        *,
        evaluation_set_id: str,
        workspace_id: str,
        item_key: str,
        fields: dict[str, str],
    ) -> EvaluationItemRef:
        """Idempotently create or replace one evaluation item."""
        field_data = [
            {
                "Key": key,
                "Name": key,
                "Content": {"ContentType": "Text", "Text": str(fields.get(key, ""))},
            }
            for key in _FEEDBACK_FIELD_KEYS
        ]
        response = await self._post(
            action="BatchCreateEvaluationSetItems",
            query={
                **self._project_query,
                "WorkspaceId": workspace_id,
                "EvaluationSetId": evaluation_set_id,
            },
            payload={
                "Items": [
                    {
                        "ItemKey": item_key,
                        "Turns": [{"Id": "0", "FieldDataList": field_data}],
                    }
                ],
                "SkipInvalidItems": False,
                "AllowPartialAdd": False,
            },
        )
        outputs = (response.get("Result") or {}).get("ItemOutputs") or []
        if not outputs:
            raise RuntimeError("AgentKit did not return the evaluation item result")
        output = outputs[0]
        item_id = str(output.get("ItemId") or "")
        if not item_id:
            raise RuntimeError("AgentKit did not return an evaluation item ID")
        return EvaluationItemRef(
            id=item_id,
            item_key=str(output.get("ItemKey") or item_key),
            is_new=bool(output.get("IsNewItem")),
        )

    async def delete_item(
        self,
        *,
        evaluation_set_id: str,
        workspace_id: str,
        item_id: str,
    ) -> None:
        """Delete one item when feedback is cancelled or changes polarity."""
        await self._post(
            action="BatchDeleteEvaluationSetItems",
            query={
                **self._project_query,
                "WorkspaceId": workspace_id,
                "EvaluationSetId": evaluation_set_id,
            },
            payload={"ItemIds": [item_id]},
        )

    async def _find_set(
        self,
        name: str,
        *,
        workspace_id: str,
    ) -> EvaluationSetRef | None:
        response = await self._post(
            action="ListEvaluationSets",
            query={**self._project_query, "WorkspaceId": workspace_id},
            payload={"Name": name, "PageNumber": 1, "PageSize": 100},
        )
        items = (response.get("Result") or {}).get("EvaluationSets") or []
        exact = [item for item in items if str(item.get("Name") or "") == name]
        if not exact:
            return None
        selected = exact[0]
        evaluation_set_id = str(selected.get("Id") or "")
        version = selected.get("EvaluationSetVersion") or {}
        resolved_workspace_id = str(
            selected.get("WorkspaceId") or version.get("WorkspaceId") or ""
        )
        if not evaluation_set_id or not resolved_workspace_id:
            raise RuntimeError("AgentKit evaluation set is missing stable identifiers")
        return EvaluationSetRef(
            id=evaluation_set_id,
            workspace_id=resolved_workspace_id,
            name=name,
        )

    async def _wait_for_set(
        self,
        name: str,
        *,
        workspace_id: str,
    ) -> EvaluationSetRef | None:
        """Wait until a newly created evaluation set is list-visible."""
        for delay in _DUPLICATE_LOOKUP_DELAYS:
            await asyncio.sleep(delay)
            existing = await self._find_set(name, workspace_id=workspace_id)
            if existing is not None:
                return existing
        return None
