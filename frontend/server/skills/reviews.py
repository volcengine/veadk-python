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

"""Store submitted Skill versions as independent copies in the review space."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .archive import SkillArchive, validate_skill_archive
from .consts import (
    REVIEW_APPROVAL_STARTED_TAG,
    REVIEW_COMMENT_TAG,
    REVIEW_REASON_TAG,
    REVIEW_SHARED_SKILL_TAG,
    REVIEW_SHARED_SPACE_TAG,
    REVIEW_SHARED_VERSION_TAG,
    REVIEW_SOURCE_SKILL_TAG,
    REVIEW_SOURCE_SPACE_TAG,
    REVIEW_SOURCE_VERSION_TAG,
    REVIEW_SUBMITTED_AT_TAG,
    REVIEW_SUBMITTER_ID_TAG,
    REVIEW_SUBMITTER_OWNER_TAG,
    REVIEW_STATUS_TAG,
    REVIEWED_AT_TAG,
    REVIEWED_BY_TAG,
    REVIEWER_ID_TAG,
    REVIEWER_OWNER_TAG,
    SHARED_REVIEW_TAG,
    SHARED_SOURCE_VERSION_TAG,
    SCORE_STATUS_TAG,
    SCORE_TOTAL_TAG,
    SCORE_TIME_TAG,
    SCORE_MODEL_TAG,
    SCORE_RUBRIC_TAG,
    SCORE_BUCKET_TAG,
    SCORE_KEY_TAG,
)
from .models import SkillIdentity
from .reviewer_profiles import ReviewerProfileResolver
from .review_text import decode_review_text, encode_review_text
from .repository import SkillRepositoryError
from .system_spaces import is_review_space, is_shared_space
from .tags import update_skill_tags

if TYPE_CHECKING:
    from .repository import AgentKitSkillRepository


def skill_tags(skill: Any) -> dict[str, str]:
    return {str(tag.key): str(tag.value) for tag in getattr(skill, "tags", None) or []}


class SkillReviewRepository:
    def __init__(
        self,
        repository: AgentKitSkillRepository,
        client_factory: Callable[[str], Any],
        *,
        reviewer_profiles: ReviewerProfileResolver | None = None,
    ) -> None:
        self._repository = repository
        self._client_factory = client_factory
        self._submit_lock = Lock()
        self._reviewer_profiles = reviewer_profiles or ReviewerProfileResolver()

    def _with_reviewer(self, application: dict[str, Any]) -> dict[str, Any]:
        result = dict(application)
        uid = result.pop("reviewerId", "")
        owner = result.pop("reviewerOwner", "")
        if result.get("reviewedBy"):
            result["reviewer"] = self._reviewer_profiles.resolve(
                identity_uid=uid,
                owner_id=owner,
                fallback_name=result["reviewedBy"],
            )
        return result

    @staticmethod
    def require_admin(identity: SkillIdentity) -> None:
        if not identity.is_admin:
            raise SkillRepositoryError(
                "SKILL_REVIEW_FORBIDDEN", "仅管理员可以查看审核申请", status_code=403
            )

    @staticmethod
    def _relations(client: Any, space_id: str) -> list[Any]:
        from agentkit.sdk.skills import types as sdk

        result = []
        page = 1
        while True:
            response = client.list_skills_by_skill_space(
                sdk.ListSkillsBySkillSpaceRequest(
                    SkillSpaceId=space_id, PageNumber=page, PageSize=100
                )
            )
            items = response.items or []
            result.extend(items)
            if len(items) < 100 or (
                response.total_count is not None and len(result) >= response.total_count
            ):
                return result
            page += 1

    @staticmethod
    def _application(skill: Any, relation: Any, region: str) -> dict[str, Any]:
        tags = skill_tags(skill)
        status = tags.get(REVIEW_STATUS_TAG, "pending")
        if status not in {"approved", "returned"} and tags.get(
            REVIEW_APPROVAL_STARTED_TAG
        ):
            status = "approving"
        result = {
            "id": skill.id,
            "kind": "skill",
            "name": skill.name or relation.skill_name or "",
            "description": skill.description or "",
            "author": tags.get("author", ""),
            "submitterId": tags.get(REVIEW_SUBMITTER_ID_TAG, ""),
            "submitterOwner": tags.get(REVIEW_SUBMITTER_OWNER_TAG, ""),
            "version": tags.get(REVIEW_SOURCE_VERSION_TAG, relation.version),
            "submittedAt": tags.get(REVIEW_SUBMITTED_AT_TAG, ""),
            "status": status,
            "reviewedAt": tags.get(REVIEWED_AT_TAG, ""),
            "reviewedBy": decode_review_text(tags, REVIEWED_BY_TAG),
            "reason": decode_review_text(tags, REVIEW_REASON_TAG),
            "comment": decode_review_text(tags, REVIEW_COMMENT_TAG),
            "reviewerId": tags.get(REVIEWER_ID_TAG, ""),
            "reviewerOwner": tags.get(REVIEWER_OWNER_TAG, ""),
            "sharedSkillId": tags.get(REVIEW_SHARED_SKILL_TAG, ""),
            "sharedSpaceId": tags.get(REVIEW_SHARED_SPACE_TAG, ""),
            "sharedVersion": tags.get(REVIEW_SHARED_VERSION_TAG, ""),
            "region": region,
            "reviewSpaceId": relation.skill_space_id,
            "reviewVersion": relation.version,
            "sourceSpaceId": tags.get(REVIEW_SOURCE_SPACE_TAG, ""),
            "sourceSkillId": tags.get(REVIEW_SOURCE_SKILL_TAG, ""),
        }
        score_status = tags.get(SCORE_STATUS_TAG)
        if score_status in {"queued", "running", "completed", "failed"}:
            score: dict[str, Any] = {"status": score_status}
            if score_status == "completed":
                total = tags.get(SCORE_TOTAL_TAG, "")
                score.update(
                    overallScore=int(total)
                    if total.isdigit() and 0 <= int(total) <= 100
                    else None,
                    scoredAt=tags.get(SCORE_TIME_TAG, ""),
                    modelName=tags.get(SCORE_MODEL_TAG, ""),
                    rubricVersion=tags.get(SCORE_RUBRIC_TAG, ""),
                )
            result["aiReview"] = score
        if tags.get(SCORE_BUCKET_TAG) and tags.get(SCORE_KEY_TAG):
            result["scoreStorage"] = {
                "bucket": tags[SCORE_BUCKET_TAG],
                "key": tags[SCORE_KEY_TAG],
            }
        return result

    @staticmethod
    def _is_submitter(identity: SkillIdentity, application: dict[str, Any]) -> bool:
        if application.get("submitterId"):
            return identity.identity_uid == application["submitterId"]
        if application.get("submitterOwner"):
            return identity.owner_id == application["submitterOwner"]
        return bool(identity.author) and identity.author == application["author"]

    def get(
        self, identity: SkillIdentity, *, region: str, application_id: str
    ) -> dict[str, Any]:
        from agentkit.sdk.skills import types as sdk

        client = self._client_factory(region)
        space = self._repository.ensure_review_space(region=region)
        relation = self._review_relation(client, str(space["id"]), application_id)
        application = self._application(
            client.get_skill(sdk.GetSkillRequest(Id=application_id)), relation, region
        )
        if not identity.is_admin and not self._is_submitter(identity, application):
            raise SkillRepositoryError(
                "SKILL_REVIEW_FORBIDDEN", "只能查看自己的审核申请", status_code=403
            )
        return self._with_reviewer(application)

    def _applications(
        self, client: Any, space_id: str, region: str
    ) -> list[dict[str, Any]]:
        from agentkit.sdk.skills import types as sdk

        applications = []
        for relation in self._relations(client, space_id):
            skill = client.get_skill(sdk.GetSkillRequest(Id=relation.skill_id))
            applications.append(self._application(skill, relation, region))
        return applications

    def list(self, identity: SkillIdentity, *, region: str) -> dict[str, Any]:
        self.require_admin(identity)
        space = self._repository.ensure_review_space(region=region)
        items = self._applications(
            self._client_factory(region), str(space["id"]), region
        )
        items.sort(key=lambda item: item["submittedAt"], reverse=True)
        return {
            "items": [self._with_reviewer(item) for item in items],
            "totalCount": len(items),
        }

    def list_for_source(
        self, identity: SkillIdentity, *, region: str, space_id: str
    ) -> dict[str, Any]:
        space = self._repository.ensure_review_space(region=region)
        items = [
            item
            for item in self._applications(
                self._client_factory(region), str(space["id"]), region
            )
            if item["sourceSpaceId"] == space_id
            and (identity.is_admin or self._is_submitter(identity, item))
        ]
        items.sort(key=lambda item: item["submittedAt"], reverse=True)
        return {
            "items": [self._with_reviewer(item) for item in items],
            "totalCount": len(items),
        }

    def _review_relation(self, client: Any, space_id: str, application_id: str) -> Any:
        relation = next(
            (
                item
                for item in self._relations(client, space_id)
                if item.skill_id == application_id
            ),
            None,
        )
        if relation is None:
            raise SkillRepositoryError(
                "SKILL_REVIEW_NOT_FOUND", "审核申请不存在，请刷新列表", status_code=404
            )
        return relation

    def decide(
        self,
        identity: SkillIdentity,
        *,
        region: str,
        application_id: str,
        decision: str,
        reason: str = "",
        comment: str = "",
    ) -> dict[str, Any]:
        from agentkit.sdk.skills import types as sdk

        self.require_admin(identity)
        reason = reason.strip()
        comment = comment.strip()
        if (
            decision not in {"approved", "returned"}
            or len(reason) > 256
            or len(comment) > 256
            or (decision == "returned" and not reason)
            or (decision == "approved" and reason)
        ):
            raise SkillRepositoryError(
                "SKILL_REVIEW_DECISION_INVALID",
                "请检查审批操作和退回理由",
                status_code=422,
            )
        client = self._client_factory(region)
        review_space = self._repository.ensure_review_space(region=region)
        reviewer_tags = {
            **encode_review_text(REVIEWED_BY_TAG, identity.author),
            REVIEWER_ID_TAG: identity.identity_uid,
            REVIEWER_OWNER_TAG: identity.owner_id,
            **encode_review_text(REVIEW_COMMENT_TAG, comment),
        }
        with self._submit_lock:
            relation = self._review_relation(
                client, str(review_space["id"]), application_id
            )
            snapshot = client.get_skill(sdk.GetSkillRequest(Id=application_id))
            application = self._application(snapshot, relation, region)
            status = application["status"]
            if status in {"approved", "returned"}:
                if status == decision:
                    return self._with_reviewer(application)
                raise SkillRepositoryError(
                    "SKILL_REVIEW_ALREADY_DECIDED",
                    "该申请已处理，请刷新列表",
                    status_code=409,
                )
            if decision == "returned":
                if status != "pending":
                    raise SkillRepositoryError(
                        "SKILL_REVIEW_PUBLISHING",
                        "该申请正在发布，请继续完成发布",
                        status_code=409,
                    )
                update_skill_tags(
                    client,
                    application_id,
                    {
                        REVIEW_STATUS_TAG: "returned",
                        REVIEWED_AT_TAG: datetime.now(timezone.utc).isoformat(),
                        **reviewer_tags,
                        **encode_review_text(REVIEW_REASON_TAG, reason),
                    },
                )
            else:
                tags = skill_tags(snapshot)
                if status == "pending":
                    # Persist the approval intent before making any copy public
                    update_skill_tags(
                        client,
                        application_id,
                        {
                            REVIEW_APPROVAL_STARTED_TAG: datetime.now(
                                timezone.utc
                            ).isoformat(),
                            **reviewer_tags,
                        },
                    )
                    snapshot = client.get_skill(sdk.GetSkillRequest(Id=application_id))
                    tags = skill_tags(snapshot)
                elif status != "approving":
                    raise SkillRepositoryError(
                        "SKILL_REVIEW_STATE_INVALID",
                        "审核状态异常，请刷新列表",
                        status_code=409,
                    )
                shared_space = self._repository.ensure_shared_space(region=region)
                shared_space_id = str(shared_space["id"])
                shared = None
                for item in self._relations(client, shared_space_id):
                    candidate = client.get_skill(sdk.GetSkillRequest(Id=item.skill_id))
                    if skill_tags(candidate).get(SHARED_REVIEW_TAG) == application_id:
                        shared = item
                        break
                if shared is None:
                    content, _ = self._repository.skill_archive(
                        region=region,
                        space_id=str(review_space["id"]),
                        skill_id=application_id,
                        version=relation.version,
                    )
                    archive = validate_skill_archive(content)
                    if archive.name != snapshot.name:
                        raise SkillRepositoryError(
                            "SKILL_REVIEW_NAME_MISMATCH",
                            "审核文件中的名称与资源不一致",
                            status_code=409,
                        )
                    shared_tags = {
                        "author": application["author"],
                        SHARED_REVIEW_TAG: application_id,
                        SHARED_SOURCE_VERSION_TAG: application["version"],
                    }
                    shared_id, shared_version = self._copy_archive(
                        client,
                        archive,
                        region=region,
                        project=str(shared_space.get("projectName") or "default"),
                        tags=shared_tags,
                    )
                    try:
                        candidate = client.get_skill(sdk.GetSkillRequest(Id=shared_id))
                        if any(
                            skill_tags(candidate).get(key) != value
                            for key, value in shared_tags.items()
                        ):
                            raise SkillRepositoryError(
                                "SKILL_REVIEW_TAGS_UNAVAILABLE",
                                "无法读取共享副本标签，请重试",
                                status_code=502,
                            )
                        client.publish_skill_to_skill_space(
                            sdk.PublishSkillToSkillSpaceRequest(
                                SkillSpaces=[shared_space_id],
                                Skills=[
                                    sdk.SkillBasicInfo(
                                        SkillId=shared_id, Version=shared_version
                                    )
                                ],
                            )
                        )
                    except Exception:
                        client.delete_skill(sdk.DeleteSkillRequest(Id=shared_id))
                        raise
                    shared = sdk.Relation(
                        SkillSpaceId=shared_space_id,
                        SkillId=shared_id,
                        Version=shared_version,
                    )
                # A retry reuses the published copy if the final tag write failed
                shared_id = shared.skill_id
                shared_version = shared.version
                if not shared_id or not shared_version:
                    raise SkillRepositoryError(
                        "SKILL_REVIEW_SHARED_INVALID",
                        "共享副本信息不完整，请重试",
                        status_code=502,
                    )
                update_skill_tags(
                    client,
                    application_id,
                    {
                        REVIEW_STATUS_TAG: "approved",
                        REVIEWED_AT_TAG: tags[REVIEW_APPROVAL_STARTED_TAG],
                        REVIEW_SHARED_SPACE_TAG: shared_space_id,
                        REVIEW_SHARED_SKILL_TAG: shared_id,
                        REVIEW_SHARED_VERSION_TAG: shared_version,
                    },
                )
            snapshot = client.get_skill(sdk.GetSkillRequest(Id=application_id))
            return self._with_reviewer(self._application(snapshot, relation, region))

    def submit(
        self,
        identity: SkillIdentity,
        *,
        region: str,
        space_id: str,
        skill_id: str,
        version: str,
    ) -> dict[str, Any]:
        from agentkit.sdk.skills import types as sdk

        client = self._client_factory(region)
        source_space = client.get_skill_space(sdk.GetSkillSpaceRequest(Id=space_id))
        if is_review_space(source_space) or is_shared_space(source_space):
            raise SkillRepositoryError(
                "SKILL_REVIEW_SOURCE_INVALID",
                "请从个人技能空间申请公开",
                status_code=409,
            )
        if not any(
            item.skill_id == skill_id for item in self._relations(client, space_id)
        ):
            raise SkillRepositoryError(
                "SKILL_REVIEW_VERSION_NOT_FOUND",
                "该 Skill 已不在来源空间中，请刷新后重试",
                status_code=409,
            )
        source = client.get_skill(sdk.GetSkillRequest(Id=skill_id))
        author = skill_tags(source).get("author") or skill_tags(source_space).get(
            "author"
        )
        if not identity.is_admin and author != identity.author:
            raise SkillRepositoryError(
                "SKILL_REVIEW_NOT_OWNER", "只能提交自己创建的 Skill", status_code=403
            )
        current = client.get_skill_version(
            sdk.GetSkillVersionRequest(Id=skill_id, SkillVersion=version)
        )
        if str(current.status or "").lower() not in {"running", "ready"}:
            raise SkillRepositoryError(
                "SKILL_REVIEW_NOT_READY",
                "Skill 版本尚未就绪，请稍后重试",
                status_code=409,
            )
        review_space = self._repository.ensure_review_space(region=region)
        review_space_id = str(review_space["id"])
        with self._submit_lock:
            for application in self._applications(client, review_space_id, region):
                if (
                    application["sourceSkillId"] == skill_id
                    and application["version"] == version
                    and application["status"] != "returned"
                ):
                    raise SkillRepositoryError(
                        "SKILL_REVIEW_ALREADY_PENDING",
                        "该版本已提交或已公开，请勿重复提交",
                        status_code=409,
                    )
            content, _ = self._repository.skill_archive(
                region=region,
                space_id=space_id,
                skill_id=skill_id,
                version=version,
                skill_space_name=source_space.name,
                skill_name=source.name,
            )
            archive = validate_skill_archive(content)
            if archive.name != source.name:
                raise SkillRepositoryError(
                    "SKILL_REVIEW_NAME_MISMATCH",
                    "Skill 文件中的名称与当前资源不一致",
                    status_code=409,
                )
            tags = {
                "author": identity.author,
                REVIEW_SOURCE_SPACE_TAG: space_id,
                REVIEW_SOURCE_SKILL_TAG: skill_id,
                REVIEW_SOURCE_VERSION_TAG: version,
                REVIEW_SUBMITTED_AT_TAG: datetime.now(timezone.utc).isoformat(),
                SCORE_STATUS_TAG: "queued",
                **(
                    {REVIEW_SUBMITTER_ID_TAG: identity.identity_uid}
                    if identity.identity_uid
                    else {}
                ),
                **(
                    {REVIEW_SUBMITTER_OWNER_TAG: identity.owner_id}
                    if identity.owner_id
                    else {}
                ),
            }
            snapshot_id, snapshot_version = self._copy_archive(
                client,
                archive,
                region=region,
                project=str(review_space.get("projectName") or "default"),
                tags=tags,
            )
            try:
                snapshot = client.get_skill(sdk.GetSkillRequest(Id=snapshot_id))
                if any(
                    skill_tags(snapshot).get(key) != value
                    for key, value in tags.items()
                ):
                    raise SkillRepositoryError(
                        "SKILL_REVIEW_TAGS_UNAVAILABLE",
                        "当前区域无法读取 Skill 标签，暂不能提交审核",
                        status_code=502,
                    )
                client.publish_skill_to_skill_space(
                    sdk.PublishSkillToSkillSpaceRequest(
                        SkillSpaces=[review_space_id],
                        Skills=[
                            sdk.SkillBasicInfo(
                                SkillId=snapshot_id, Version=snapshot_version
                            )
                        ],
                    )
                )
            except Exception:
                client.delete_skill(sdk.DeleteSkillRequest(Id=snapshot_id))
                raise
            relation = sdk.Relation(
                SkillSpaceId=review_space_id,
                SkillId=snapshot_id,
                Version=snapshot_version,
            )
            return self._application(snapshot, relation, region)

    @staticmethod
    def _copy_archive(
        client: Any,
        archive: SkillArchive,
        *,
        region: str,
        project: str,
        tags: dict[str, str],
    ) -> tuple[str, str]:
        from agentkit.sdk.skills import types as sdk
        from agentkit.toolkit.cli.cli_skills_workflow import _wait_for_running_version
        from agentkit.toolkit.config import GlobalConfigManager

        from .storage import (
            ensure_skill_publish_bucket,
            resolve_skill_publish_credentials,
            resolve_skill_publish_storage,
            upload_skill_archive,
        )

        config = GlobalConfigManager().load()
        storage = resolve_skill_publish_storage(
            region=region,
            config_bucket=config.tos.bucket or "",
            config_prefix=config.tos.prefix or "",
        )
        credentials = resolve_skill_publish_credentials(provider=storage.provider)
        ensure_skill_publish_bucket(storage, credentials)
        with tempfile.TemporaryDirectory(prefix="studio-review-") as directory:
            path = Path(directory) / f"{archive.name}_{uuid4().hex}.zip"
            path.write_bytes(archive.content)
            url = upload_skill_archive(str(path), storage, credentials)
        created = client.create_skill(
            sdk.CreateSkillRequest(
                Name=archive.name,
                Description=archive.description,
                TosUrl=url,
                BucketName=storage.bucket,
                ProjectName=project,
                Tags=[
                    sdk.TagForSkill(Key=key, Value=value) for key, value in tags.items()
                ],
            )
        )
        if not created.id:
            raise SkillRepositoryError(
                "SKILL_REVIEW_COPY_FAILED",
                "未能创建待审核副本，请重试",
                status_code=502,
            )
        try:
            latest = _wait_for_running_version(
                client, created.id, timeout_seconds=90, poll_interval_seconds=2
            )
            return created.id, latest.version
        except Exception:
            client.delete_skill(sdk.DeleteSkillRequest(Id=created.id))
            raise

    def files(
        self, identity: SkillIdentity, *, region: str, application_id: str
    ) -> dict[str, object]:
        self.require_admin(identity)
        space = self._repository.ensure_review_space(region=region)
        space_id = str(space["id"])
        relation = next(
            (
                item
                for item in self._relations(self._client_factory(region), space_id)
                if item.skill_id == application_id
            ),
            None,
        )
        if relation is None:
            raise SkillRepositoryError(
                "SKILL_REVIEW_NOT_FOUND", "审核申请不存在，请刷新列表", status_code=404
            )
        return self._repository.skill_files(
            region=region,
            space_id=space_id,
            skill_id=application_id,
            version=relation.version,
        )
