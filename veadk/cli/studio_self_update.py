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

"""Admin-only self-update support for a VeFaaS-hosted Studio."""

from __future__ import annotations

import asyncio
import logging
import os
import stat
import tempfile
import threading
import time
import traceback
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException, Request

from veadk.cli.frontend_branding import SiteLogo
from veadk.cli.studio_package import studio_run_script
from veadk.cli.studio_release import (
    DEFAULT_RELEASE_PREFIX,
    StudioReleaseError,
    StudioReleaseManifest,
    StudioReleaseStore,
)
from veadk.version import VERSION

logger = logging.getLogger(__name__)

_MANIFEST_CACHE_SECONDS = 180
_MAX_EXTRACTED_BYTES = 600 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 10_000
_UPDATE_HEADER = "X-VeADK-Studio-Update"

Credentials = tuple[str, str, str | None]
CredentialResolver = Callable[[], Credentials]
AdminGuard = Callable[[Request], None]


def current_studio_release_version() -> str:
    """Return the deployed Studio release id, or its pre-release sentinel."""
    return os.getenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")


def current_studio_display_version() -> str:
    """Prefer a cloud Frontend release id, otherwise show the VeADK version."""
    release_version = current_studio_release_version()
    return VERSION if release_version == "bundled" else release_version


class StudioUpdateConflict(StudioReleaseError):
    """Raised when an update is already being prepared by this instance."""


@dataclass(frozen=True)
class StudioUpdateSettings:
    """Immutable identifiers required to update the current Studio."""

    bucket: str
    region: str
    prefix: str
    application_id: str
    function_id: str
    project: str

    @classmethod
    def from_env(cls) -> StudioUpdateSettings:
        """Load self-update settings injected during Studio deployment."""
        return cls(
            bucket=os.getenv("VEADK_STUDIO_UPDATE_BUCKET", "").strip(),
            region=os.getenv("VEADK_STUDIO_UPDATE_REGION", "cn-beijing").strip(),
            prefix=os.getenv(
                "VEADK_STUDIO_UPDATE_PREFIX", DEFAULT_RELEASE_PREFIX
            ).strip(),
            application_id=os.getenv("VEADK_STUDIO_APPLICATION_ID", "").strip(),
            function_id=os.getenv("VEADK_STUDIO_FUNCTION_ID", "").strip(),
            project=os.getenv("VEADK_STUDIO_PROJECT", "default").strip(),
        )

    @property
    def enabled(self) -> bool:
        """Whether this deployment has all required immutable identifiers."""
        return bool(
            self.bucket
            and self.region
            and self.prefix
            and self.application_id
            and self.function_id
            and self.project
        )


class StudioSelfUpdater:
    """Check, stage, and submit full Studio Function bundle updates."""

    def __init__(
        self,
        *,
        settings: StudioUpdateSettings,
        credential_resolver: CredentialResolver,
        branding_logo: SiteLogo | None,
    ) -> None:
        self._settings = settings
        self._credential_resolver = credential_resolver
        self._branding_logo = branding_logo
        self._manifest: StudioReleaseManifest | None = None
        self._manifest_expires_at = 0.0
        self._lock = threading.Lock()
        self._submitted_version = ""
        self._last_error = ""
        self._error_id = ""
        self._error_stage = ""
        self._diagnostic_lines: list[str] = []
        self._progress_stage = "idle"
        self._progress_message = ""
        self._target_version = ""
        self._started_at = 0

    def status(
        self,
        *,
        force: bool = False,
        target_version: str | None = None,
    ) -> dict[str, Any]:
        """Return current and latest versions for the administrator UI."""
        current = current_studio_release_version()
        if not self._settings.enabled:
            return {
                "enabled": False,
                "currentVersion": current,
                "latestVersion": "",
                "latestGitSha": "",
                "releases": [],
                "available": False,
                "state": "disabled",
                "message": "管理员未配置 Studio 更新源",
                **self._progress_payload(),
            }
        try:
            manifest = self._latest_manifest(force=force)
            releases = self._available_releases(current)
        except Exception:
            logger.exception("Failed to check the latest Studio release")
            return {
                "enabled": True,
                "currentVersion": current,
                "latestVersion": "",
                "latestGitSha": "",
                "releases": [],
                "available": False,
                "state": "error",
                "message": "检查 Studio 更新失败，请稍后重试",
                **self._progress_payload(),
            }
        available = bool(releases)
        state = "idle"
        message = ""
        progress = self._progress_payload()
        target = target_version or self._target_version
        local_progress = self._progress_stage not in {"idle", "complete", "error"}
        local_state_applies = not target_version or target == self._target_version
        if target and current == target:
            progress = {
                "progressStage": "complete",
                "progressMessage": "新 Revision 已接管服务",
                "targetVersion": target,
                "startedAt": self._started_at,
            }
        elif self._last_error and local_state_applies:
            state = "error"
            message = self._last_error
        elif local_progress and local_state_applies:
            state = "updating"
            message = self._progress_message
        else:
            application_status = self._application_status()
            if application_status == "deploy_fail" and target:
                self._target_version = target
                self._record_failure(
                    RuntimeError("VeFaaS control plane reported deploy_fail."),
                    "VeFaaS Revision 发布失败",
                    stage="publishing",
                )
                state = "error"
                message = self._last_error
                progress = self._progress_payload()
            elif application_status != "deploy_success":
                target = target or manifest.version
                state = "updating"
                message = "VeFaaS 正在发布新 Revision"
                progress = {
                    "progressStage": "publishing",
                    "progressMessage": message,
                    "targetVersion": target,
                    "startedAt": self._started_at,
                }
            elif target:
                state = "updating"
                message = "发布已完成，正在等待新 Revision 接管流量"
                progress = {
                    "progressStage": "publishing",
                    "progressMessage": message,
                    "targetVersion": target,
                    "startedAt": self._started_at,
                }
        return {
            "enabled": True,
            "currentVersion": current,
            "latestVersion": manifest.version,
            "latestGitSha": manifest.git_sha,
            "releases": [_release_payload(item) for item in releases],
            "available": available,
            "state": state,
            "message": message,
            **progress,
        }

    def submit_latest(self) -> StudioReleaseManifest:
        """Stage the latest bundle and submit a release for this Function."""
        return self.submit_version(None)

    def submit_version(self, version: str | None) -> StudioReleaseManifest:
        """Stage one selectable bundle and submit a release for this Function."""
        if not self._settings.enabled:
            raise StudioReleaseError("Studio self-update is not configured.")
        if not self._lock.acquire(blocking=False):
            raise StudioUpdateConflict("A Studio update is already in progress.")
        try:
            self._reset_diagnostics(version)
            self._set_progress("resolving", "正在读取目标版本信息")
            access_key, secret_key, session_token = self._credential_resolver()
            store = self._store(access_key, secret_key, session_token)
            manifest = store.manifest(version) if version else store.latest_manifest()
            self._target_version = manifest.version
            current = current_studio_release_version()
            if current == manifest.version:
                self._set_progress("complete", "当前已是所选版本")
                return manifest
            if _is_release_version(current) and manifest.version <= current:
                raise StudioReleaseError("只能选择比当前版本新的 Studio 版本。")
            with tempfile.TemporaryDirectory(prefix="veadk_studio_self_update_") as tmp:
                workspace = Path(tmp)
                archive = workspace / "studio-bundle.zip"
                package_dir = workspace / "package"
                self._set_progress("downloading", "正在下载并校验完整更新包")
                store.download_bundle(manifest, archive)
                self._set_progress("preparing", "正在准备 VeFaaS Function 代码")
                extract_studio_bundle(archive, package_dir)
                self._preserve_branding(package_dir)
                from veadk.integrations.ve_faas.ve_faas import VeFaaS

                service = VeFaaS(
                    access_key=access_key,
                    secret_key=secret_key,
                    session_token=session_token or "",
                    region=self._settings.region,
                    project_name=self._settings.project,
                )
                self._set_progress("submitting", "正在提交 VeFaaS Function 更新")
                service.submit_application_code_bundle_update(
                    application_id=self._settings.application_id,
                    function_id=self._settings.function_id,
                    path=str(package_dir),
                    environment_overrides={
                        "VEADK_STUDIO_RELEASE_VERSION": manifest.version,
                    },
                )
            self._submitted_version = manifest.version
            self._set_progress("publishing", "已提交，正在等待新 Revision 发布")
            return manifest
        except StudioUpdateConflict:
            raise
        except StudioReleaseError as error:
            self._record_failure(error, str(error))
            raise
        except Exception as error:
            logger.exception("Failed to submit the Studio self-update")
            error_text = str(error).lower()
            if any(
                marker in error_text
                for marker in (
                    "accessdenied",
                    "access denied",
                    "forbidden",
                    "permission",
                    "unauthorized",
                )
            ):
                self._last_error = (
                    "Studio 更新权限不足，请管理员刷新 VeFaaS IAM 策略后重试"
                )
            else:
                self._last_error = "Studio 更新提交失败"
            self._record_failure(error, self._last_error)
            raise StudioReleaseError(self._last_error) from error
        finally:
            self._lock.release()

    def _set_progress(self, stage: str, message: str) -> None:
        """Expose the current update stage to the administrator status route."""
        self._progress_stage = stage
        self._progress_message = message
        self._diagnostic_lines.append(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {stage}: {message}"
        )

    def _reset_diagnostics(self, version: str | None) -> None:
        """Start a fresh diagnostic timeline for one update attempt."""
        self._last_error = ""
        self._error_id = ""
        self._error_stage = ""
        self._diagnostic_lines = []
        self._started_at = int(time.time() * 1000)
        self._target_version = version or ""

    def _record_failure(
        self,
        error: BaseException,
        message: str,
        *,
        stage: str | None = None,
    ) -> None:
        """Record a complete, administrator-visible failure diagnostic."""
        failure_stage = stage or self._progress_stage or "unknown"
        self._last_error = message
        self._error_id = uuid.uuid4().hex[:12]
        self._error_stage = failure_stage
        self._diagnostic_lines.extend(
            (
                f"errorId={self._error_id}",
                f"stage={failure_stage}",
                f"region={self._settings.region}",
                f"project={self._settings.project}",
                f"applicationId={self._settings.application_id}",
                f"functionId={self._settings.function_id}",
                "",
                "".join(traceback.format_exception(error)).rstrip(),
            )
        )
        self._set_progress("error", message)

    def _progress_payload(self) -> dict[str, Any]:
        """Return stable progress fields for every status response."""
        return {
            "progressStage": self._progress_stage,
            "progressMessage": self._progress_message,
            "targetVersion": self._target_version,
            "startedAt": self._started_at,
            "errorId": self._error_id,
            "errorStage": self._error_stage,
            "errorLog": "\n".join(self._diagnostic_lines),
            "consoleUrl": self._console_url(),
        }

    def _console_url(self) -> str:
        """Return the fixed VeFaaS Function console URL for this Studio."""
        if not self._settings.region or not self._settings.function_id:
            return ""
        return (
            "https://console.volcengine.com/vefaas/"
            f"region:vefaas+{self._settings.region}/function/detail/"
            f"{self._settings.function_id}"
        )

    def _application_status(self) -> str:
        """Read the current Application release status from VeFaaS."""
        access_key, secret_key, session_token = self._credential_resolver()
        from veadk.integrations.ve_faas.ve_faas import VeFaaS

        service = VeFaaS(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token or "",
            region=self._settings.region,
            project_name=self._settings.project,
        )
        status, _ = service._get_application_status(self._settings.application_id)
        return str(status)

    def _latest_manifest(self, *, force: bool) -> StudioReleaseManifest:
        now = time.monotonic()
        if not force and self._manifest and now < self._manifest_expires_at:
            return self._manifest
        access_key, secret_key, session_token = self._credential_resolver()
        manifest = self._store(
            access_key,
            secret_key,
            session_token,
        ).latest_manifest()
        self._manifest = manifest
        self._manifest_expires_at = now + _MANIFEST_CACHE_SECONDS
        return manifest

    def _available_releases(self, current: str) -> list[StudioReleaseManifest]:
        """Return selectable releases, newest first, without allowing downgrade."""
        access_key, secret_key, session_token = self._credential_resolver()
        store = self._store(access_key, secret_key, session_token)
        try:
            releases = store.release_catalog()
        except Exception as error:
            if (
                not isinstance(error, KeyError)
                and getattr(error, "status_code", None) != 404
            ):
                raise
            releases = [store.latest_manifest()]
        return [
            release
            for release in releases
            if release.version != current
            and (not _is_release_version(current) or release.version > current)
        ]

    def _store(
        self,
        access_key: str,
        secret_key: str,
        session_token: str | None,
    ) -> StudioReleaseStore:
        return StudioReleaseStore(
            bucket=self._settings.bucket,
            region=self._settings.region,
            prefix=self._settings.prefix,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token or "",
        )

    def _preserve_branding(self, package_dir: Path) -> None:
        if self._branding_logo is None:
            return
        filename = f"site-logo.{self._branding_logo.extension}"
        (package_dir / filename).write_bytes(self._branding_logo.content)
        (package_dir / "run.sh").write_text(
            studio_run_script(filename),
            encoding="utf-8",
        )
        (package_dir / "run.sh").chmod(0o755)


def extract_studio_bundle(archive: Path, destination: Path) -> None:
    """Safely extract a bounded Studio bundle and validate its entrypoint."""
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if not members or len(members) > _MAX_ARCHIVE_MEMBERS:
            raise StudioReleaseError("Studio release archive member count is invalid.")
        total_size = 0
        for member in members:
            total_size += member.file_size
            if total_size > _MAX_EXTRACTED_BYTES:
                raise StudioReleaseError("Studio release archive is too large.")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise StudioReleaseError("Studio release archive contains a symlink.")
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(root):
                raise StudioReleaseError(
                    "Studio release archive contains an unsafe path."
                )
        bundle.extractall(destination)
    required = (destination / "run.sh", destination / "requirements.txt")
    if not all(path.is_file() for path in required):
        raise StudioReleaseError("Studio release bundle is missing its entrypoint.")
    (destination / "run.sh").chmod(0o755)


def _is_release_version(value: str) -> bool:
    return len(value) == 14 and value.isdigit()


def _release_payload(manifest: StudioReleaseManifest) -> dict[str, Any]:
    return {
        "version": manifest.version,
        "gitSha": manifest.git_sha,
        "createdAt": manifest.created_at,
        "changelog": list(manifest.changelog),
    }


def mount_studio_update_routes(
    app: Any,
    updater: StudioSelfUpdater,
    require_admin: AdminGuard,
) -> None:
    """Mount administrator-only status and update routes."""

    @app.get("/web/studio-update")
    async def _studio_update_status(request: Request) -> dict[str, Any]:
        require_admin(request)
        target_version = request.query_params.get("targetVersion")
        if target_version and not _is_release_version(target_version):
            raise HTTPException(status_code=400, detail="版本号格式无效")
        return await asyncio.to_thread(
            updater.status,
            target_version=target_version,
        )

    @app.post("/web/studio-update", status_code=202)
    async def _studio_update_start(request: Request) -> dict[str, Any]:
        require_admin(request)
        if request.headers.get(_UPDATE_HEADER) != "1":
            raise HTTPException(
                status_code=403, detail="Studio update header is required"
            )
        try:
            version = None
            if request.headers.get("content-type", "").startswith("application/json"):
                payload = await request.json()
                if not isinstance(payload, dict):
                    raise HTTPException(status_code=400, detail="请求格式无效")
                raw_version = payload.get("version")
                if raw_version is not None and not isinstance(raw_version, str):
                    raise HTTPException(status_code=400, detail="版本号格式无效")
                version = raw_version
            manifest = await asyncio.to_thread(updater.submit_version, version)
        except StudioUpdateConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except StudioReleaseError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return {
            "accepted": True,
            "version": manifest.version,
            "gitSha": manifest.git_sha,
        }
