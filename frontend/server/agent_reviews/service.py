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

"""First-publication review; no public-version upgrade or automatic decisions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from .tags import (
    APPLICATION_MESSAGE_LIMIT,
    REVIEW_TEXT_LIMIT,
    STATUS_TAG,
    decode_record,
    encode_record,
    enterprise_visible,
    runtime_tags,
    validate_text,
)


@dataclass(frozen=True)
class ReviewActor:
    owner_id: str
    name: str
    role: str
    identity_uid: str = ""
    identifiers: frozenset[str] = frozenset()

    @property
    def is_admin(self) -> bool:
        return self.role in {"admin", "super_admin"}

    def person(self) -> dict[str, str]:
        return {
            "id": self.owner_id,
            "identityUid": self.identity_uid,
            "name": self.name,
            "avatarUrl": "",
            "email": "",
        }


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint(runtime: Any) -> str:
    def primitive(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if hasattr(value, "__dict__"):
            return vars(value)
        raise TypeError(f"Unsupported runtime configuration: {type(value).__name__}")

    values = {
        key: getattr(runtime, key, None)
        for key in (
            "name",
            "description",
            "current_version_number",
            "agent_runtime_artifact",
            "envs",
            "authorizer_configuration",
            "cpu_milli",
            "memory_mb",
            "network_configuration",
            "role_name",
        )
    }
    return hashlib.sha256(
        json.dumps(
            values, sort_keys=True, default=primitive, ensure_ascii=False
        ).encode()
    ).hexdigest()


def summary(runtime: Any) -> dict[str, Any]:
    envs = {
        str(item.key): str(item.value or "")
        for item in getattr(runtime, "envs", None) or []
    }
    return {
        "name": str(getattr(runtime, "name", "") or ""),
        "description": str(getattr(runtime, "description", "") or ""),
        "version": getattr(runtime, "current_version_number", None),
        "model": envs.get("MODEL_AGENT_NAME", ""),
        "environmentKeys": sorted(envs),
        "cpuMilli": getattr(runtime, "cpu_milli", None),
        "memoryMb": getattr(runtime, "memory_mb", None),
    }


class AgentReviewService:
    def __init__(
        self,
        repository: Any,
        profiles: Callable[[dict[str, str]], dict[str, str]] | None = None,
    ):
        self.repository = repository
        self.profiles = profiles or (lambda person: person)
        self._lock = RLock()

    def _authorize(self, actor: ReviewActor, runtime: Any) -> None:
        if not actor.owner_id:
            raise HTTPException(401, "Studio identity is required")
        if not actor.is_admin and runtime_tags(runtime).get(
            "veadk:owner", ""
        ).casefold() not in (actor.identifiers | {actor.owner_id.casefold()}):
            raise HTTPException(404, "Runtime not found")

    @staticmethod
    def _manager(actor: ReviewActor, *, admin: bool = False) -> None:
        if not actor.owner_id:
            raise HTTPException(401, "Studio identity is required")
        if (admin and not actor.is_admin) or actor.role == "user":
            raise HTTPException(403, "Agent review operation is not allowed")

    @staticmethod
    def require_editable(runtime: Any) -> None:
        tags = runtime_tags(runtime)
        if enterprise_visible(tags):
            raise HTTPException(409, "请先取消公开，再修改或删除 Agent")
        if tags.get(STATUS_TAG) == "pending":
            raise HTTPException(409, "请先撤回审核申请，再修改或删除 Agent")

    def _save(
        self, region: str, runtime: Any, record: dict[str, Any]
    ) -> dict[str, Any]:
        values = encode_record(record)
        if len(set(runtime_tags(runtime)) | set(values)) > 50:
            raise HTTPException(422, "Runtime 标签数量已达上限，请先清理无关标签")
        runtime_id = runtime.runtime_id
        self.repository.write(region, runtime_id, values)
        actual = runtime_tags(self.repository.get(region, runtime_id))
        if any(actual.get(key) != value for key, value in values.items()):
            raise HTTPException(502, "审批标签尚未保存成功，请刷新后重试")
        return self._present(record, runtime, region)

    def _present(
        self, record: dict[str, Any], runtime: Any, region: str
    ) -> dict[str, Any]:
        result = {
            key: value
            for key, value in record.items()
            if key not in {"fingerprint", "snapshot", "submitter"}
        }
        tags = runtime_tags(runtime)
        owner = tags.get("veadk:owner", "")
        result.update(
            runtimeId=runtime.runtime_id, region=region, agent=summary(runtime)
        )
        result["submitter"] = self.profiles(
            {
                "id": owner,
                "name": tags.get("veadk:author") or owner,
                "identityUid": "",
                "avatarUrl": "",
                "email": "",
            }
        )
        if record.get("reviewer"):
            result["reviewer"] = self.profiles(record["reviewer"])
        return result

    def read(
        self, actor: ReviewActor, region: str, runtime_id: str
    ) -> dict[str, Any] | None:
        runtime = self.repository.get(region, runtime_id)
        self._authorize(actor, runtime)
        record = decode_record(runtime_tags(runtime))
        if not record:
            return None
        result = self._present(record, runtime, region)
        result["contentChanged"] = record["fingerprint"] != fingerprint(runtime)
        return result

    def list(self, actor: ReviewActor, region: str) -> list[dict[str, Any]]:
        self._manager(actor, admin=True)
        results = []
        for runtime in self.repository.list(region):
            record = decode_record(runtime_tags(runtime))
            if record:
                results.append(self._present(record, runtime, region))
        return sorted(results, key=lambda record: record["submittedAt"], reverse=True)

    def _new(
        self, actor: ReviewActor, region: str, runtime: Any, message: str
    ) -> dict[str, Any]:
        if str(getattr(runtime, "status", "")).lower() not in {"running", "ready"}:
            raise HTTPException(409, "Agent 尚未运行就绪，请部署完成后再申请公开")
        if runtime_tags(runtime).get("veadk:managed") != "true":
            raise HTTPException(409, "请先通过 Studio 部署 Agent，再申请公开")
        return {
            "id": uuid4().hex,
            "runtimeId": runtime.runtime_id,
            "region": region,
            "status": "pending",
            "fingerprint": fingerprint(runtime),
            "submittedAt": now(),
            "message": message.strip(),
            "reviewer": None,
            "reviewedAt": "",
            "reason": "",
            "comment": "",
            "published": False,
        }

    def submit(
        self, actor: ReviewActor, region: str, runtime_id: str, message: str = ""
    ) -> dict[str, Any]:
        self._manager(actor)
        message = validate_text(message, APPLICATION_MESSAGE_LIMIT, "申请理由")
        with self._lock:
            runtime = self.repository.get(region, runtime_id)
            self._authorize(actor, runtime)
            tags = runtime_tags(runtime)
            previous = decode_record(tags)
            if enterprise_visible(tags):
                raise HTTPException(409, "Agent 已公开")
            if previous and previous["status"] == "pending":
                return self._present(previous, runtime, region)
            record = self._new(actor, region, runtime, message)
            return self._save(region, runtime, record)

    def decide(
        self,
        actor: ReviewActor,
        region: str,
        runtime_id: str,
        application_id: str,
        decision: str,
        reason: str = "",
        comment: str = "",
    ) -> dict[str, Any]:
        self._manager(actor, admin=True)
        reason = validate_text(reason, REVIEW_TEXT_LIMIT, "退回理由")
        comment = validate_text(comment, REVIEW_TEXT_LIMIT, "审批意见")
        if decision not in {"approved", "returned"}:
            raise HTTPException(422, "Invalid review decision")
        if decision == "returned" and not reason.strip():
            raise HTTPException(422, "请填写退回理由")
        with self._lock:
            runtime = self.repository.get(region, runtime_id)
            record = decode_record(runtime_tags(runtime))
            if not record or record["id"] != application_id:
                raise HTTPException(409, "申请已变化，请刷新后重试")
            if record["status"] == decision:
                return self._present(record, runtime, region)
            if record["status"] != "pending":
                raise HTTPException(409, "申请已处理")
            if decision == "approved" and record["fingerprint"] != fingerprint(runtime):
                raise HTTPException(409, "Agent 内容已变化，请退回后重新申请")
            record.update(
                status=decision,
                reviewer=actor.person(),
                reviewedAt=now(),
                reason=reason.strip(),
                comment=comment.strip(),
                published=decision == "approved",
            )
            return self._save(region, runtime, record)

    def publish(
        self, actor: ReviewActor, region: str, runtime_id: str, comment: str = ""
    ) -> dict[str, Any]:
        self._manager(actor, admin=True)
        comment = validate_text(comment, REVIEW_TEXT_LIMIT, "审批意见")
        with self._lock:
            runtime = self.repository.get(region, runtime_id)
            record = decode_record(runtime_tags(runtime))
            if enterprise_visible(runtime_tags(runtime)) and record:
                return self._present(record, runtime, region)
            if record and record["status"] == "pending":
                return self.decide(
                    actor, region, runtime_id, record["id"], "approved", "", comment
                )
            record = self._new(actor, region, runtime, "")
            record.update(
                status="approved",
                reviewer=actor.person(),
                reviewedAt=now(),
                comment=comment.strip(),
                published=True,
                direct=True,
            )
            return self._save(region, runtime, record)

    def withdraw(
        self, actor: ReviewActor, region: str, runtime_id: str
    ) -> dict[str, Any]:
        self._manager(actor)
        with self._lock:
            runtime = self.repository.get(region, runtime_id)
            self._authorize(actor, runtime)
            record = decode_record(runtime_tags(runtime))
            if not record or record["status"] != "pending":
                raise HTTPException(409, "没有待审核的申请")
            record.update(
                status="withdrawn", withdrawnBy=actor.person(), withdrawnAt=now()
            )
            return self._save(region, runtime, record)

    def unpublish(
        self, actor: ReviewActor, region: str, runtime_id: str
    ) -> dict[str, Any]:
        self._manager(actor)
        with self._lock:
            runtime = self.repository.get(region, runtime_id)
            self._authorize(actor, runtime)
            record = decode_record(runtime_tags(runtime))
            if not record or record["status"] != "approved":
                raise HTTPException(409, "Agent 尚未公开")
            record.update(
                published=False, unpublishedBy=actor.person(), unpublishedAt=now()
            )
            return self._save(region, runtime, record)
