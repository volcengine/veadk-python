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
import json
import logging
import os
import re
import stat
import tempfile
import threading
import time
import traceback
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from veadk.cli.frontend_branding import SiteLogo
from veadk.cli.studio_package import studio_run_script
from veadk.cli.studio_release import (
    DEFAULT_RELEASE_PREFIX,
    STUDIO_RELEASE_REGION,
    StudioReleaseError,
    StudioReleaseManifest,
    StudioReleaseStore,
)
from veadk.utils.cloud_provider import DEFAULT_CLOUD_PROVIDER, CloudProvider
from veadk.version import VERSION

logger = logging.getLogger(__name__)

_MANIFEST_CACHE_SECONDS = 180
_MAX_EXTRACTED_BYTES = 600 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 10_000
_UPDATE_LOG_CACHE_SECONDS = 2
_UPDATE_LOG_MAX_BYTES = 32 * 1024
_UPDATE_LOG_MAX_LINES = 200
_STAGED_RELEASE_GRACE_SECONDS = 60
_SUBMIT_STATUS_GRACE_MILLISECONDS = 90 * 1000
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
    deployment_region: str
    prefix: str
    application_id: str
    function_id: str
    project: str
    provider: CloudProvider

    @classmethod
    def from_env(
        cls,
        provider: CloudProvider = DEFAULT_CLOUD_PROVIDER,
    ) -> StudioUpdateSettings:
        """Load self-update settings injected during Studio deployment."""
        return cls(
            bucket=os.getenv("VEADK_STUDIO_UPDATE_BUCKET", "").strip(),
            deployment_region=(
                os.getenv("VEADK_STUDIO_DEPLOY_REGION")
                or os.getenv("AGENTKIT_SANDBOX_REGION")
                or "cn-beijing"
            ).strip(),
            prefix=os.getenv(
                "VEADK_STUDIO_UPDATE_PREFIX", DEFAULT_RELEASE_PREFIX
            ).strip(),
            application_id=os.getenv("VEADK_STUDIO_APPLICATION_ID", "").strip(),
            function_id=os.getenv("VEADK_STUDIO_FUNCTION_ID", "").strip(),
            project=os.getenv("VEADK_STUDIO_PROJECT", "default").strip(),
            provider=provider,
        )

    @property
    def enabled(self) -> bool:
        """Whether this deployment has all required immutable identifiers."""
        return bool(
            self.bucket
            and self.deployment_region
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
        self._vefaas_log_lines: list[str] = []
        self._vefaas_log_revision = 0
        self._vefaas_logs_expires_at = 0.0
        self._vefaas_logs_visible = True

    def status(
        self,
        *,
        force: bool = False,
        target_version: str | None = None,
        started_at: int | None = None,
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
        revision_number = 0
        local_progress = self._progress_stage not in {"idle", "complete", "error"}
        local_state_applies = not target_version or target == self._target_version
        request_started_at = started_at or self._started_at
        if target and _release_reached(current, target):
            progress.update(
                {
                    "progressStage": "complete",
                    "progressMessage": "新 Revision 已接管服务",
                    "targetVersion": target,
                    "startedAt": request_started_at,
                }
            )
        elif self._last_error and local_state_applies:
            state = "error"
            message = self._last_error
        elif local_progress and local_state_applies:
            state = "updating"
            message = self._progress_message
        else:
            (
                application_status,
                deployed_version,
                revision_number,
                release_pending,
            ) = self._application_status()
            if not target and application_status != "deploy_success":
                target = deployed_version or manifest.version
            if application_status == "deploy_fail" and target:
                progress = self._status_failure_payload(
                    RuntimeError("VeFaaS control plane reported deploy_fail."),
                    "VeFaaS Revision 发布失败",
                    stage="publishing",
                    target_version=target,
                    started_at=request_started_at,
                )
                state = "error"
                message = "VeFaaS Revision 发布失败"
            elif (
                application_status == "deploy_success"
                and target
                and deployed_version == target
                and release_pending
            ):
                progress = self._status_failure_payload(
                    RuntimeError(
                        "Function update is newer than the latest Application release."
                    ),
                    "Function 已更新但 Revision 未发布，请重新尝试更新",
                    stage="publishing",
                    target_version=target,
                    started_at=request_started_at,
                )
                state = "error"
                message = "Function 已更新但 Revision 未发布，请重新尝试更新"
            elif (
                application_status == "deploy_success"
                and target
                and deployed_version
                and deployed_version != target
            ):
                elapsed = int(time.time() * 1000) - request_started_at
                if request_started_at and elapsed < _SUBMIT_STATUS_GRACE_MILLISECONDS:
                    state = "updating"
                    message = "正在等待 Function 更新提交"
                    progress.update(
                        {
                            "progressStage": "submitting",
                            "progressMessage": message,
                            "targetVersion": target,
                            "startedAt": request_started_at,
                        }
                    )
                else:
                    progress = self._status_failure_payload(
                        RuntimeError(
                            f"Target {target} was not submitted; deployed version is "
                            f"{deployed_version}."
                        ),
                        "目标版本未成功提交，请重新尝试更新",
                        stage="submitting",
                        target_version=target,
                        started_at=request_started_at,
                    )
                    state = "error"
                    message = "目标版本未成功提交，请重新尝试更新"
            elif application_status != "deploy_success":
                state = "updating"
                message = "VeFaaS 正在发布新 Revision"
                progress.update(
                    {
                        "progressStage": "publishing",
                        "progressMessage": message,
                        "targetVersion": target,
                        "startedAt": request_started_at,
                    }
                )
            elif target:
                state = "updating"
                message = "发布已完成，正在等待新 Revision 接管流量"
                progress.update(
                    {
                        "progressStage": "publishing",
                        "progressMessage": message,
                        "targetVersion": target,
                        "startedAt": request_started_at,
                    }
                )
        include_vefaas_logs = bool(target) and (
            progress["progressStage"] in {"publishing", "complete"}
            or progress["errorStage"] == "publishing"
        )
        progress["updateLogs"] = self._update_logs(
            include_vefaas=include_vefaas_logs,
            revision_number=revision_number,
            local_lines=str(progress["errorLog"]).splitlines(),
        )
        if progress["progressStage"] == "complete":
            progress["updateLogs"] = _tail_log_lines(
                [
                    *progress["updateLogs"],
                    "更新完成：新 Revision 已接管服务",
                ]
            )
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
        credentials: tuple[str, str, str] = ("", "", "")
        try:
            self._reset_diagnostics(version)
            self._set_progress("resolving", "正在读取目标版本信息")
            access_key, secret_key, session_token = self._credential_resolver()
            credentials = (access_key, secret_key, session_token or "")
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
                self._prepare_package(package_dir)
                from veadk.integrations.ve_faas.ve_faas import VeFaaS

                service = VeFaaS(
                    access_key=access_key,
                    secret_key=secret_key,
                    session_token=session_token or "",
                    region=self._settings.deployment_region,
                    project_name=self._settings.project,
                    provider=self._settings.provider,
                )
                from frontend.server.studio_update_resources import (
                    reconcile_studio_update_resources,
                )

                self._set_progress(
                    "provisioning",
                    "正在检查并补齐 Studio 云资源",
                )
                resource_environment = reconcile_studio_update_resources(
                    provider=self._settings.provider,
                    region=self._settings.deployment_region,
                    application_id=self._settings.application_id,
                    function_id=self._settings.function_id,
                    function_client=service.client,
                    access_key=access_key,
                    secret_key=secret_key,
                    session_token=session_token or "",
                )
                environment_overrides = {
                    "VEADK_STUDIO_RELEASE_VERSION": manifest.version,
                    **resource_environment,
                }
                if self._settings.provider == "byteplus":
                    environment_overrides.update(
                        {
                            "CLOUD_PROVIDER": "byteplus",
                            "AGENTKIT_CLOUD_PROVIDER": "byteplus",
                            "BYTEPLUS_REGION": self._settings.deployment_region,
                        }
                    )
                from frontend.service.studio_scheduler.deploy import (
                    deploy_scheduler_for_studio_update,
                )

                self._set_progress(
                    "scheduler",
                    "正在更新定时任务调度服务与分钟触发器",
                )
                _, _, _, _, scheduler_base = deploy_scheduler_for_studio_update(
                    service,
                    studio_function_id=self._settings.function_id,
                    package_root=package_dir,
                    provider=self._settings.provider,
                    project=self._settings.project,
                    environment_overrides=resource_environment,
                )
                environment_overrides["VEADK_STUDIO_CRONJOB_SCHEDULER_BASE"] = (
                    scheduler_base
                )
                self._set_progress("submitting", "正在提交 VeFaaS Function 更新")
                service.submit_application_code_bundle_update(
                    application_id=self._settings.application_id,
                    function_id=self._settings.function_id,
                    path=str(package_dir),
                    environment_overrides=environment_overrides,
                )
            self._submitted_version = manifest.version
            self._set_progress("publishing", "已提交，正在等待新 Revision 发布")
            return manifest
        except StudioUpdateConflict:
            raise
        except StudioReleaseError as error:
            self._record_failure(error, str(error), secrets=credentials)
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
            self._record_failure(error, self._last_error, secrets=credentials)
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
        self._vefaas_log_lines = []
        self._vefaas_log_revision = 0
        self._vefaas_logs_expires_at = 0.0
        self._vefaas_logs_visible = True

    def _record_failure(
        self,
        error: BaseException,
        message: str,
        *,
        stage: str | None = None,
        secrets: tuple[str, ...] = (),
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
                f"region={self._settings.deployment_region}",
                f"project={self._settings.project}",
                f"applicationId={self._settings.application_id}",
                f"functionId={self._settings.function_id}",
                "",
                _redact_diagnostic(
                    "".join(traceback.format_exception(error)).rstrip(),
                    secrets,
                ),
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
            "updateLogs": _tail_log_lines(self._diagnostic_lines),
            "updateLogsVisible": self._vefaas_logs_visible,
            "consoleUrl": self._console_url(),
            "permissionConsoleUrl": self._permission_console_url(),
        }

    def _status_failure_payload(
        self,
        error: BaseException,
        message: str,
        *,
        stage: str,
        target_version: str,
        started_at: int,
    ) -> dict[str, Any]:
        """Build one read-only control-plane failure response."""
        error_id = uuid.uuid4().hex[:12]
        lines = [
            *self._diagnostic_lines,
            f"errorId={error_id}",
            f"stage={stage}",
            f"region={self._settings.deployment_region}",
            f"project={self._settings.project}",
            f"applicationId={self._settings.application_id}",
            f"functionId={self._settings.function_id}",
            "",
            "".join(traceback.format_exception(error)).rstrip(),
        ]
        progress = self._progress_payload()
        progress.update(
            {
                "progressStage": "error",
                "progressMessage": message,
                "targetVersion": target_version,
                "startedAt": started_at,
                "errorId": error_id,
                "errorStage": stage,
                "errorLog": "\n".join(lines),
                "updateLogs": _tail_log_lines(lines),
            }
        )
        return progress

    def _update_logs(
        self,
        *,
        include_vefaas: bool,
        revision_number: int = 0,
        local_lines: list[str] | None = None,
    ) -> list[str]:
        """Return a bounded, redacted timeline for the update dialog."""
        lines = list(local_lines if local_lines is not None else self._diagnostic_lines)
        if include_vefaas:
            lines.extend(self._load_vefaas_logs(revision_number))
        return _tail_log_lines(lines)

    def _load_vefaas_logs(self, revision_number: int = 0) -> list[str]:
        """Read the active Revision log without delaying every status poll."""
        now = time.monotonic()
        if (
            (self._vefaas_log_lines or not self._vefaas_logs_visible)
            and revision_number == self._vefaas_log_revision
            and now < self._vefaas_logs_expires_at
        ):
            return self._vefaas_log_lines
        access_key, secret_key, session_token = self._credential_resolver()
        try:
            from veadk.integrations.ve_faas.ve_faas import VeFaaS

            service = VeFaaS(
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token or "",
                region=self._settings.deployment_region,
                project_name=self._settings.project,
                provider=self._settings.provider,
            )
            raw_lines = service._get_application_logs(
                self._settings.application_id,
                revision_number=revision_number or None,
                limit=_UPDATE_LOG_MAX_BYTES,
            )
            safe_lines = [
                _redact_diagnostic(
                    str(line),
                    (access_key, secret_key, session_token or ""),
                )
                for line in raw_lines
            ]
            self._vefaas_log_lines = _tail_log_lines(safe_lines)
            self._vefaas_log_revision = revision_number
            self._vefaas_logs_expires_at = now + _UPDATE_LOG_CACHE_SECONDS
            self._vefaas_logs_visible = True
        except Exception as error:
            if _is_log_query_permission_denied(error):
                self._vefaas_log_lines = []
                self._vefaas_log_revision = revision_number
                self._vefaas_logs_expires_at = now + _UPDATE_LOG_CACHE_SECONDS
                self._vefaas_logs_visible = False
            logger.debug("Failed to read VeFaaS update logs", exc_info=True)
        return self._vefaas_log_lines

    def _console_url(self) -> str:
        """Return the fixed VeFaaS Function console URL for this Studio."""
        if not self._settings.deployment_region or not self._settings.function_id:
            return ""
        console_host = (
            "console.byteplus.com"
            if self._settings.provider == "byteplus"
            else "console.volcengine.com"
        )
        return (
            f"https://{console_host}/vefaas/"
            f"region:vefaas+{self._settings.deployment_region}/function/detail/"
            f"{self._settings.function_id}"
        )

    def _permission_console_url(self) -> str:
        """Return the provider IAM console used to grant optional log access."""
        console_host = (
            "console.byteplus.com"
            if self._settings.provider == "byteplus"
            else "console.volcengine.com"
        )
        return f"https://{console_host}/iam"

    def _application_status(self) -> tuple[str, str, int, bool]:
        """Read the Application status and Function's configured release version."""
        access_key, secret_key, session_token = self._credential_resolver()
        from veadk.integrations.ve_faas.ve_faas import VeFaaS

        service = VeFaaS(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token or "",
            region=self._settings.deployment_region,
            project_name=self._settings.project,
            provider=self._settings.provider,
        )
        status, response = service._get_application_status(
            self._settings.application_id
        )
        result = response.get("Result", {})
        cloud_resource = result.get("CloudResource", "")
        if isinstance(cloud_resource, str):
            try:
                cloud_resource = json.loads(cloud_resource)
            except json.JSONDecodeError:
                cloud_resource = {}
        function_snapshot = (
            cloud_resource.get("framework", {}).get("function", {})
            if isinstance(cloud_resource, dict)
            else {}
        )
        try:
            from volcenginesdkvefaas import GetFunctionRequest

            current_function = service.client.get_function(
                GetFunctionRequest(id=self._settings.function_id)
            )
            environment = {
                str(item.key): str(item.value)
                for item in (getattr(current_function, "envs", None) or [])
            }
            function_updated_at = _parse_vefaas_time(
                getattr(current_function, "last_update_time", None)
            )
        except Exception:
            logger.debug(
                "Failed to read the current VeFaaS Function state",
                exc_info=True,
            )
            environment = {
                str(item.get("Key", "")): str(item.get("Value", ""))
                for item in function_snapshot.get("Envs", [])
                if isinstance(item, dict)
            }
            function_updated_at = _parse_vefaas_time(
                function_snapshot.get("LastUpdateTime")
            )
        revision_number = int(
            result.get("NewRevisionNumber") or result.get("StableRevisionNumber") or 0
        )
        application_updated_at = _parse_vefaas_time(result.get("UpdateTime"))
        release_pending = bool(
            function_updated_at
            and application_updated_at
            and function_updated_at > application_updated_at
            and (datetime.now(timezone.utc) - function_updated_at).total_seconds()
            >= _STAGED_RELEASE_GRACE_SECONDS
        )
        return (
            str(status),
            environment.get("VEADK_STUDIO_RELEASE_VERSION", ""),
            revision_number,
            release_pending,
        )

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
            region=STUDIO_RELEASE_REGION,
            prefix=self._settings.prefix,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token or "",
        )

    def _prepare_package(self, package_dir: Path) -> None:
        filename = None
        if self._branding_logo is not None:
            filename = f"site-logo.{self._branding_logo.extension}"
            (package_dir / filename).write_bytes(self._branding_logo.content)
        (package_dir / "run.sh").write_text(
            studio_run_script(filename, provider=self._settings.provider),
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


def _release_reached(current: str, target: str) -> bool:
    """Return whether the running release is the requested one or newer."""
    if current == target:
        return True
    return (
        _is_release_version(current)
        and _is_release_version(target)
        and current > target
    )


def _redact_diagnostic(text: str, secrets: tuple[str, ...]) -> str:
    """Remove credentials and signed query strings from administrator logs."""
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "***")
    redacted = re.sub(
        r"(?i)(\bbearer\s+)[a-z0-9._~+/=-]+",
        r"\1***",
        redacted,
    )
    redacted = re.sub(
        r"(?i)((?:api[_-]?key|access[_-]?key|secret[_-]?key|"
        r"session[_-]?token|security[_-]?token|token|password)\s*[:=]\s*)"
        r"(?:[\"'][^\"']*[\"']|[^\s,;]+)",
        r"\1***",
        redacted,
    )
    return re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[REDACTED]", redacted)


def _is_log_query_permission_denied(error: BaseException) -> bool:
    """Recognize explicit authorization failures without hiding other errors."""
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "accessdenied",
            "access denied",
            "permission denied",
            "forbidden",
            "unauthorizedoperation",
            "not authorized",
        )
    )


def _tail_log_lines(lines: list[str]) -> list[str]:
    """Keep the newest complete log lines inside the response budget."""
    flattened: list[str] = []
    for item in lines:
        for raw_line in str(item).splitlines():
            line = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", raw_line).strip()
            if not line or line == "--- End of CP Log ---":
                continue
            if re.match(r"^%\s+Total\s+%\s+Received\s+%\s+Xferd\b", line):
                continue
            if re.match(r"^Dload\s+Upload\s+Total\s+Spent\s+Left\s+Speed\b", line):
                continue
            if re.match(
                r"^\d{1,3}\s+\S+\s+\d{1,3}\s+\S+\s+\d+\s+\d+\s+\S+",
                line,
            ):
                continue
            if line == "+ cat s.json" or "Output application s config json:" in line:
                continue
            if line.startswith("{") and '"Envs":[' in line:
                continue
            if "执行日志内容较多" in line and "更多日志通过日志下载链接查看" in line:
                line = "VeFaaS 日志内容较多，当前仅显示末尾内容。"
            if not flattened or flattened[-1] != line:
                flattened.append(line)
    flattened = flattened[-_UPDATE_LOG_MAX_LINES:]
    selected: list[str] = []
    size = 0
    for line in reversed(flattened):
        encoded = line.encode("utf-8")
        if size + len(encoded) + 1 > _UPDATE_LOG_MAX_BYTES:
            break
        selected.append(line)
        size += len(encoded) + 1
    return list(reversed(selected))


def _parse_vefaas_time(value: Any) -> datetime | None:
    """Parse the two timestamp formats returned by the VeFaaS control plane."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = re.sub(r"\s+[A-Za-z]{2,5}$", "", value.strip())
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    normalized = re.sub(r"\s*([+-]\d{2})(\d{2})$", r"\1:\2", normalized)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
        raw_started_at = request.query_params.get("startedAt")
        try:
            started_at = int(raw_started_at) if raw_started_at else None
        except ValueError as error:
            raise HTTPException(status_code=400, detail="更新时间格式无效") from error
        if started_at is not None and started_at <= 0:
            raise HTTPException(status_code=400, detail="更新时间格式无效")
        return await asyncio.to_thread(
            updater.status,
            target_version=target_version,
            started_at=started_at,
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
