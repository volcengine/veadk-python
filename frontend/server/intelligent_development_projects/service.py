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

"""Application service for durable intelligent-development projects."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import shlex
from uuid import uuid4

from frontend.server.intelligent_development import DeliveryReference, release_path
from frontend.server.intelligent_development_task import IntentDecision
from frontend.server.sandbox_remote import SandboxRemoteTransport
from veadk.cli.frontend_sandbox import SandboxSessionUnavailableError

from .models import (
    IntelligentDevelopmentProject,
    IntelligentDevelopmentSessionBinding,
    IntelligentDevelopmentVersion,
    StoredDevelopmentVersion,
)
from .repository import (
    IntelligentDevelopmentProjectNotFound,
    IntelligentDevelopmentProjectStorageUnavailable,
    TosIntelligentDevelopmentProjectRepository,
)

_MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
_MAX_REPORT_BYTES = 2 * 1024 * 1024
logger = logging.getLogger(__name__)


class IntelligentDevelopmentProjectService:
    """Coordinate Session bindings, immutable versions, and TOS bytes."""

    def __init__(self, repository: TosIntelligentDevelopmentProjectRepository) -> None:
        self.repository = repository

    async def list_projects(self, owner_id: str) -> list[IntelligentDevelopmentProject]:
        return await self.repository.list_projects(owner_id)

    async def list_versions(
        self, owner_id: str, project_id: str
    ) -> list[IntelligentDevelopmentVersion]:
        return await self.repository.list_versions(owner_id, project_id)

    async def get_version(
        self, owner_id: str, project_id: str, version_id: str
    ) -> IntelligentDevelopmentVersion:
        return await self.repository.get_version(owner_id, project_id, version_id)

    async def load_version(
        self, owner_id: str, project_id: str, version_id: str
    ) -> StoredDevelopmentVersion:
        return await self.repository.load_version(owner_id, project_id, version_id)

    async def delete_version(
        self, owner_id: str, project_id: str, version_id: str
    ) -> IntelligentDevelopmentProject | None:
        return await self.repository.delete_version(owner_id, project_id, version_id)

    async def create_binding(
        self,
        *,
        owner_id: str,
        session_id: str,
        display_name: str,
        project_id: str | None = None,
        base_version_id: str | None = None,
    ) -> IntelligentDevelopmentSessionBinding:
        now = datetime.now(timezone.utc)
        resolved_project_id = project_id or uuid4().hex
        project_name = display_name.strip()[:128] or "未命名 Agent"
        if project_id is not None:
            project = await self.repository.get_project(owner_id, project_id)
            project_name = project.name
            if base_version_id is None:
                base_version_id = project.latest_version_id
        if base_version_id is not None:
            version = await self.repository.get_version(
                owner_id, resolved_project_id, base_version_id
            )
            if version.project_id != resolved_project_id:
                raise ValueError("Selected version does not belong to the project.")
        binding = IntelligentDevelopmentSessionBinding(
            ownerId=owner_id,
            sessionId=session_id,
            projectId=resolved_project_id,
            projectName=project_name,
            baseVersionId=base_version_id,
            createdAt=now,
            updatedAt=now,
        )
        await self.repository.put_binding(binding)
        return binding

    async def get_binding(
        self, owner_id: str, session_id: str
    ) -> IntelligentDevelopmentSessionBinding:
        return await self.repository.get_binding(owner_id, session_id)

    async def delete_binding(self, owner_id: str, session_id: str) -> None:
        await self.repository.delete_binding(owner_id, session_id)

    async def base_version(
        self, owner_id: str, session_id: str
    ) -> StoredDevelopmentVersion | None:
        binding = await self._resolved_binding(owner_id, session_id)
        if binding.base_version_id is None:
            return None
        return await self.load_version(
            owner_id, binding.project_id, binding.base_version_id
        )

    async def base_metadata(
        self, owner_id: str, session_id: str
    ) -> IntelligentDevelopmentVersion | None:
        binding = await self._resolved_binding(owner_id, session_id)
        if binding.base_version_id is None:
            return None
        return await self.repository.get_version(
            owner_id, binding.project_id, binding.base_version_id
        )

    async def restore_base_version(
        self,
        *,
        owner_id: str,
        session_id: str,
        endpoint: str,
        workspace: str,
    ) -> bool:
        """Validate and atomically restore the selected version to an empty Sandbox."""
        import shutil
        import tempfile
        from pathlib import Path

        from frontend.server.deployment_source import DeploymentSourceError
        from frontend.server.intelligent_development_source import (
            load_intelligent_development_artifact,
        )

        from .repository import IntelligentDevelopmentVersionIntegrityError

        metadata = await self.base_metadata(owner_id, session_id)
        if metadata is None:
            return False
        destination = Path(tempfile.mkdtemp(prefix="intelligent-restore-check-"))
        try:
            trusted = await load_intelligent_development_artifact(
                destination,
                {
                    "kind": "intelligentDevelopment",
                    "sessionId": metadata.source_session_id,
                    "projectId": metadata.project_id,
                    "versionId": metadata.version_id,
                    "artifactSha256": metadata.artifact_sha256,
                    "validationReportSha256": metadata.validation_report_sha256,
                },
                owner_id=owner_id,
                service=None,
                project_service=self,
            )
        except DeploymentSourceError as error:
            raise IntelligentDevelopmentVersionIntegrityError(str(error)) from error
        finally:
            shutil.rmtree(destination, ignore_errors=True)

        token = uuid4().hex
        archive_path = f"/tmp/.intelligent-development-restore-{token}.zip"
        staging_path = f"{workspace}.restore-{token}"
        transport = SandboxRemoteTransport(endpoint)
        source = (
            "import os,shutil,stat,zipfile\n"
            "from pathlib import PurePosixPath\n"
            f"archive={archive_path!r}; root={workspace!r}; staging={staging_path!r}\n"
            f"expected_count={metadata.file_count}; expected_size={metadata.artifact_size}\n"
            "try:\n"
            " if os.path.getsize(archive)!=expected_size: raise ValueError('archive size mismatch')\n"
            " if os.path.lexists(staging): shutil.rmtree(staging)\n"
            " os.makedirs(staging,mode=0o700)\n"
            " with zipfile.ZipFile(archive) as package:\n"
            "  files=[item for item in package.infolist() if not item.is_dir()]\n"
            "  if len(files)!=expected_count: raise ValueError('file count mismatch')\n"
            "  if sum(item.file_size for item in files)>20*1024*1024: raise ValueError('archive too large')\n"
            "  for item in files:\n"
            "   path=PurePosixPath(item.filename)\n"
            "   if path.is_absolute() or not path.parts or '..' in path.parts: raise ValueError('unsafe path')\n"
            "   if stat.S_ISLNK((item.external_attr>>16)&0xffff): raise ValueError('symlink')\n"
            "   target=os.path.join(staging,*path.parts)\n"
            "   if os.path.commonpath((staging,target))!=staging: raise ValueError('unsafe target')\n"
            "   os.makedirs(os.path.dirname(target),mode=0o700,exist_ok=True)\n"
            "   with package.open(item) as src, open(target,'wb') as dst: shutil.copyfileobj(src,dst)\n"
            " if os.listdir(root): raise ValueError('workspace is not empty')\n"
            " os.rmdir(root)\n"
            " os.replace(staging,root)\n"
            " os.chmod(root,0o700)\n"
            "finally:\n"
            " if os.path.lexists(archive): os.unlink(archive)\n"
            " if os.path.lexists(staging): shutil.rmtree(staging)\n"
        )
        try:
            await transport.upload(
                archive_path,
                trusted.content,
                media_type="application/zip",
                mode=0o600,
            )
            await transport.exec_text(
                f"python3 -c {shlex.quote(source)}",
                timeout=60,
            )
        except Exception as error:
            raise SandboxSessionUnavailableError(
                "项目版本恢复失败，请重新进入后重试。"
            ) from error
        return True

    async def persist_delivery(
        self,
        *,
        owner_id: str,
        session_id: str,
        transport: SandboxRemoteTransport,
        delivery: DeliveryReference,
        decision: IntentDecision,
    ) -> tuple[IntelligentDevelopmentProject, IntelligentDevelopmentVersion]:
        binding = await self._resolved_binding(owner_id, session_id)
        release = release_path(
            delivery.artifact_sha256, delivery.validation_report_sha256
        )
        artifact = await transport.download(
            f"{release}/artifact.zip", max_bytes=_MAX_ARTIFACT_BYTES
        )
        report = await transport.download(
            f"{release}/validation/{delivery.validation_report_sha256}.json",
            max_bytes=_MAX_REPORT_BYTES,
        )
        try:
            report_value = json.loads(report)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(
                "Intelligent-development validation report is invalid."
            ) from error
        criteria = (
            report_value.get("acceptanceCriteria")
            if isinstance(report_value, dict)
            else None
        )
        acceptance_criteria = (
            [str(item) for item in criteria if isinstance(item, str) and item.strip()]
            if isinstance(criteria, list)
            else list(decision.acceptance_criteria)
        )
        now = datetime.now(timezone.utc)
        version = IntelligentDevelopmentVersion(
            projectId=binding.project_id,
            versionId=uuid4().hex,
            parentVersionId=binding.base_version_id,
            sourceSessionId=session_id,
            createdAt=now,
            intentSummary=decision.intent_summary,
            acceptanceCriteria=acceptance_criteria,
            artifactSha256=delivery.artifact_sha256,
            validationReportSha256=delivery.validation_report_sha256,
            artifactSize=delivery.artifact_size,
            fileCount=delivery.file_count,
            agentName=delivery.agent_name,
            entryPoint=delivery.entry_point,
            verified=delivery.verified,
            validationSummary=delivery.validation_summary,
            gateSummary=list(delivery.gate_summary),
            validatedAt=delivery.validated_at,
        )
        project = await self.repository.commit_version(
            owner_id,
            binding.project_name,
            version,
            artifact,
            report,
        )
        advanced = binding.model_copy(
            update={"base_version_id": version.version_id, "updated_at": now}
        )
        try:
            await self.repository.put_binding(advanced)
        except IntelligentDevelopmentProjectStorageUnavailable:
            logger.warning(
                "Stored intelligent-development version %s but could not advance Session binding %s",
                version.version_id,
                session_id,
            )
        return project, version

    async def _resolved_binding(
        self,
        owner_id: str,
        session_id: str,
    ) -> IntelligentDevelopmentSessionBinding:
        """Recover a binding when its post-commit update was interrupted."""
        binding = await self.get_binding(owner_id, session_id)
        try:
            versions = await self.repository.list_versions(
                owner_id,
                binding.project_id,
            )
        except IntelligentDevelopmentProjectNotFound:
            if binding.base_version_id is None:
                return binding
            raise
        candidates = [
            version for version in versions if version.source_session_id == session_id
        ]
        if not candidates:
            return binding
        latest = max(
            candidates,
            key=lambda item: (item.created_at, item.version_id),
        )
        current = next(
            (
                version
                for version in versions
                if version.version_id == binding.base_version_id
            ),
            None,
        )
        if current is not None and (
            current.created_at,
            current.version_id,
        ) >= (latest.created_at, latest.version_id):
            return binding
        repaired = binding.model_copy(
            update={
                "base_version_id": latest.version_id,
                "updated_at": latest.created_at,
            }
        )
        try:
            await self.repository.put_binding(repaired)
        except IntelligentDevelopmentProjectStorageUnavailable:
            logger.warning(
                "Resolved but could not repair intelligent-development Session binding %s",
                session_id,
            )
        return repaired


__all__ = ["IntelligentDevelopmentProjectService"]
