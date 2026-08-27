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

"""HTTP routes for durable intelligent-development projects."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import re
import shutil
import tempfile

from fastapi import FastAPI, HTTPException, Request, Response

from frontend.server.deployment_source import DeploymentSourceError
from frontend.server.intelligent_development_source import (
    IntelligentDevelopmentSourceIntegrityError,
    IntelligentDevelopmentSourceNotFound,
    IntelligentDevelopmentSourceStale,
    TrustedDeploymentSource,
    load_intelligent_development_artifact,
    materialize_intelligent_development_preview,
)

from .repository import (
    IntelligentDevelopmentProjectConflict,
    IntelligentDevelopmentProjectNotFound,
    IntelligentDevelopmentProjectStorageUnavailable,
    IntelligentDevelopmentVersionIntegrityError,
    IntelligentDevelopmentVersionNotFound,
)
from .service import IntelligentDevelopmentProjectService

PROJECT_EXCEPTIONS = (
    IntelligentDevelopmentProjectConflict,
    IntelligentDevelopmentProjectNotFound,
    IntelligentDevelopmentProjectStorageUnavailable,
    IntelligentDevelopmentVersionIntegrityError,
    IntelligentDevelopmentVersionNotFound,
)
PROJECT_MATERIALIZATION_EXCEPTIONS = PROJECT_EXCEPTIONS + (DeploymentSourceError,)


def project_error_detail(error: Exception) -> tuple[int, dict[str, object]]:
    """Map known project failures without disguising unexpected exceptions."""
    if isinstance(error, IntelligentDevelopmentProjectNotFound):
        status = 404
        code = "INTELLIGENT_DEVELOPMENT_PROJECT_NOT_FOUND"
        retryable = False
    elif isinstance(error, IntelligentDevelopmentVersionNotFound):
        status = 404
        code = "INTELLIGENT_DEVELOPMENT_VERSION_NOT_FOUND"
        retryable = False
    elif isinstance(error, IntelligentDevelopmentProjectConflict):
        status = 409
        code = "INTELLIGENT_DEVELOPMENT_VERSION_CONFLICT"
        retryable = False
    elif isinstance(error, IntelligentDevelopmentVersionIntegrityError):
        status = 502
        code = "INTELLIGENT_DEVELOPMENT_VERSION_INVALID"
        retryable = False
    elif isinstance(error, IntelligentDevelopmentProjectStorageUnavailable):
        status = 503
        code = "INTELLIGENT_DEVELOPMENT_STORAGE_UNAVAILABLE"
        retryable = True
    else:
        raise TypeError("Unsupported intelligent-development project error") from error
    return status, {"code": code, "message": str(error), "retryable": retryable}


def project_http_error(error: Exception) -> HTTPException:
    status, detail = project_error_detail(error)
    return HTTPException(
        status_code=status,
        detail=detail,
    )


def _release_payload(
    session_id: str,
    trusted: TrustedDeploymentSource,
    parent_version_id: str | None,
) -> dict[str, object]:
    return {
        "sessionId": session_id,
        "projectId": trusted.project_id,
        "versionId": trusted.version_id,
        "parentVersionId": parent_version_id,
        "artifactSha256": trusted.artifact_sha256,
        "validationReportSha256": trusted.validation_report_sha256,
        "agentName": trusted.agent_name,
        "entryPoint": trusted.entry_point,
        "fileCount": trusted.file_count,
        "artifactSize": trusted.artifact_size,
        "validatedAt": trusted.validated_at,
        "gateSummary": list(trusted.gate_summary),
        "deployable": True,
        "verified": trusted.verified,
        "validationSummary": trusted.validation_summary,
        "files": [
            {"path": item.path, "content": item.content} for item in trusted.files
        ],
    }


def _stored_source(
    *,
    session_id: str,
    project_id: str,
    version_id: str,
    artifact_sha256: str,
    validation_report_sha256: str,
) -> dict[str, object]:
    return {
        "kind": "intelligentDevelopment",
        "sessionId": session_id,
        "projectId": project_id,
        "versionId": version_id,
        "artifactSha256": artifact_sha256,
        "validationReportSha256": validation_report_sha256,
    }


def _materialization_http_error(error: Exception) -> HTTPException:
    if isinstance(error, PROJECT_EXCEPTIONS):
        return project_http_error(error)
    if isinstance(error, IntelligentDevelopmentSourceNotFound):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, IntelligentDevelopmentSourceStale):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, IntelligentDevelopmentSourceIntegrityError):
        return HTTPException(status_code=502, detail=str(error))
    if isinstance(error, DeploymentSourceError):
        return HTTPException(status_code=409, detail=str(error))
    raise TypeError("Unsupported intelligent-development source error") from error


def mount_intelligent_development_project_routes(
    app: FastAPI,
    *,
    prefix: str,
    owner_resolver: Callable[[Request], str],
    project_service: IntelligentDevelopmentProjectService | None,
) -> None:
    """Mount the owner-scoped project and immutable-version API."""

    def configured_service() -> IntelligentDevelopmentProjectService:
        if project_service is None:
            raise project_http_error(
                IntelligentDevelopmentProjectStorageUnavailable("项目存储尚未配置。")
            )
        return project_service

    @app.get(f"{prefix}/projects")
    async def _projects(request: Request) -> dict[str, object]:
        owner = owner_resolver(request)
        service = configured_service()
        try:
            projects = await service.list_projects(owner)
        except PROJECT_EXCEPTIONS as error:
            raise project_http_error(error) from error
        return {
            "projects": [
                project.model_dump(
                    by_alias=True,
                    mode="json",
                    exclude={"owner_id"},
                )
                for project in projects
            ]
        }

    @app.get(f"{prefix}/projects/{{project_id}}/versions")
    async def _project_versions(
        project_id: str,
        request: Request,
    ) -> dict[str, object]:
        owner = owner_resolver(request)
        service = configured_service()
        try:
            versions = await service.list_versions(owner, project_id)
        except PROJECT_EXCEPTIONS as error:
            raise project_http_error(error) from error
        return {
            "versions": [
                version.model_dump(by_alias=True, mode="json") for version in versions
            ]
        }

    @app.delete(f"{prefix}/projects/{{project_id}}/versions/{{version_id}}")
    async def _delete_project_version(
        project_id: str,
        version_id: str,
        request: Request,
    ) -> dict[str, object]:
        owner = owner_resolver(request)
        service = configured_service()
        try:
            project = await service.delete_version(owner, project_id, version_id)
        except PROJECT_EXCEPTIONS as error:
            raise project_http_error(error) from error
        return {
            "deleted": True,
            "projectDeleted": project is None,
            **(
                {
                    "project": project.model_dump(
                        by_alias=True,
                        mode="json",
                        exclude={"owner_id"},
                    )
                }
                if project is not None
                else {}
            ),
        }

    @app.get(f"{prefix}/projects/{{project_id}}/versions/{{version_id}}/source")
    async def _project_version_source(
        project_id: str,
        version_id: str,
        request: Request,
    ) -> dict[str, object]:
        owner = owner_resolver(request)
        service = configured_service()
        destination = Path(tempfile.mkdtemp(prefix="intelligent-project-source-"))
        try:
            metadata = await service.get_version(owner, project_id, version_id)
            trusted = await materialize_intelligent_development_preview(
                destination,
                _stored_source(
                    session_id=metadata.source_session_id,
                    project_id=project_id,
                    version_id=version_id,
                    artifact_sha256=metadata.artifact_sha256,
                    validation_report_sha256=metadata.validation_report_sha256,
                ),
                owner_id=owner,
                service=None,
                project_service=service,
            )
            return _release_payload(
                metadata.source_session_id,
                trusted,
                metadata.parent_version_id,
            )
        except PROJECT_MATERIALIZATION_EXCEPTIONS as error:
            raise _materialization_http_error(error) from error
        finally:
            shutil.rmtree(destination, ignore_errors=True)

    @app.get(f"{prefix}/projects/{{project_id}}/versions/{{version_id}}/download")
    async def _project_version_download(
        project_id: str,
        version_id: str,
        request: Request,
    ) -> Response:
        owner = owner_resolver(request)
        service = configured_service()
        destination = Path(tempfile.mkdtemp(prefix="intelligent-project-download-"))
        try:
            metadata = await service.get_version(owner, project_id, version_id)
            trusted = await load_intelligent_development_artifact(
                destination,
                _stored_source(
                    session_id=metadata.source_session_id,
                    project_id=project_id,
                    version_id=version_id,
                    artifact_sha256=metadata.artifact_sha256,
                    validation_report_sha256=metadata.validation_report_sha256,
                ),
                owner_id=owner,
                service=None,
                project_service=service,
            )
        except PROJECT_MATERIALIZATION_EXCEPTIONS as error:
            raise _materialization_http_error(error) from error
        finally:
            shutil.rmtree(destination, ignore_errors=True)

        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", trusted.agent_name)
        safe_name = safe_name.strip(".-_")[:64] or "agent"
        filename = f"{safe_name}-source-{trusted.artifact_sha256[:12]}.zip"
        return Response(
            content=trusted.content,
            media_type="application/zip",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Content-Type-Options": "nosniff",
            },
        )


__all__ = [
    "PROJECT_EXCEPTIONS",
    "mount_intelligent_development_project_routes",
    "project_error_detail",
    "project_http_error",
]
