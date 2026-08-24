# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the VeFaaS-hosted Studio self-update service."""

import hashlib
import json
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from veadk.cli.frontend_branding import SiteLogo
from veadk.cli.studio_release import (
    BYTEPLUS_STUDIO_RELEASE_REGION,
    STUDIO_RELEASE_REGION,
    StudioReleaseError,
    StudioReleaseManifest,
)
from veadk.cli.studio_self_update import (
    StudioSelfUpdater,
    StudioUpdateSettings,
    _parse_vefaas_time,
    _tail_log_lines,
    current_studio_display_version,
    current_studio_release_version,
    extract_studio_bundle,
    mount_studio_update_routes,
)
from veadk.utils.cloud_provider import CloudProvider


@pytest.fixture(autouse=True)
def _allow_studio_update_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        StudioSelfUpdater,
        "_permission_report",
        lambda _self, _credentials: SimpleNamespace(
            ready=True,
            missing_actions=(),
            to_payload=lambda: {
                "ready": True,
                "missingActions": [],
                "policyName": "",
                "authorizationUrl": "",
                "iamConsoleUrl": "https://console.volcengine.com/iam/policymanage",
                "principalName": "",
            },
        ),
    )


def test_studio_release_version_defaults_to_bundled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VEADK_STUDIO_RELEASE_VERSION", raising=False)

    assert current_studio_release_version() == "bundled"


def test_studio_display_version_selects_local_or_release_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("veadk.cli.studio_self_update.VERSION", "1.2.3")
    monkeypatch.delenv("VEADK_STUDIO_RELEASE_VERSION", raising=False)
    assert current_studio_display_version() == "1.2.3"

    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")
    assert current_studio_display_version() == "1.2.3"

    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "20260726123000")
    assert current_studio_display_version() == "20260726123000"


def test_parse_vefaas_time_supports_application_and_function_formats() -> None:
    assert _parse_vefaas_time(
        "2026-07-26 08:53:15.942 +0000 UTC"
    ) == _parse_vefaas_time("2026-07-26T08:53:15.942Z")


def test_update_log_lines_remove_terminal_noise_and_empty_rows() -> None:
    assert _tail_log_lines(
        [
            (
                "Start to install volcano-vefaas...\r"
                "% Total % Received % Xferd Average Speed Time Time Time Current\r"
                "Dload Upload Total Spent Left Speed\r"
                "100 2048 100 2048 0 0 1024 0 0:00:02 0:00:02 --:--:-- 1024"
            ),
            (
                "[WARNING] 执行日志内容较多，已自动加载尾部日志，"
                "更多日志通过日志下载链接查看。\n"
            ),
            "+ cat s.json",
            "+ node -p 'Output application s config json:'",
            'Output application s config json: {"edition":"3.0.0"}',
            "\x1b[2K\n--- End of CP Log ---\n",
        ]
    ) == [
        "Start to install volcano-vefaas...",
        "VeFaaS 日志内容较多，当前仅显示末尾内容。",
    ]
    assert _parse_vefaas_time(
        "2026-07-26 16:53:15.942 +0800 CST"
    ) == _parse_vefaas_time("2026-07-26T08:53:15.942Z")


def _manifest() -> StudioReleaseManifest:
    return StudioReleaseManifest(
        version="20260724153045",
        git_sha="a" * 40,
        sha256=hashlib.sha256(b"placeholder").hexdigest(),
        size=len(b"placeholder"),
        created_at="2026-07-24T15:30:45+08:00",
        changelog=("支持选择更新版本",),
    )


def _settings(
    *,
    deployment_region: str = "cn-beijing",
    provider: CloudProvider = "volcengine",
) -> StudioUpdateSettings:
    return StudioUpdateSettings(
        bucket="studio-releases",
        deployment_region=deployment_region,
        prefix="veadk/studio/main",
        application_id="application-id",
        function_id="function-id",
        project="default",
        provider=provider,
    )


def test_shanghai_studio_uses_beijing_release_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Store:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setenv("VEADK_STUDIO_DEPLOY_REGION", "cn-shanghai")
    monkeypatch.setenv("VEADK_STUDIO_UPDATE_REGION", "cn-shanghai")
    monkeypatch.setattr("veadk.cli.studio_self_update.StudioReleaseStore", _Store)
    updater = StudioSelfUpdater(
        settings=StudioUpdateSettings.from_env(),
        credential_resolver=lambda: ("ak", "sk", "token"),
        branding_logo=None,
    )

    updater._store("ak", "sk", "token")

    assert updater._settings.deployment_region == "cn-shanghai"
    assert captured["region"] == STUDIO_RELEASE_REGION


def test_studio_update_settings_keep_active_provider() -> None:
    settings = StudioUpdateSettings.from_env(provider="byteplus")

    assert settings.provider == "byteplus"


def test_byteplus_studio_uses_byteplus_release_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Store:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("veadk.cli.studio_self_update.StudioReleaseStore", _Store)
    updater = StudioSelfUpdater(
        settings=_settings(
            deployment_region="ap-southeast-1",
            provider="byteplus",
        ),
        credential_resolver=lambda: ("ak", "sk", "token"),
        branding_logo=None,
    )

    updater._store("ak", "sk", "token")

    assert captured["region"] == BYTEPLUS_STUDIO_RELEASE_REGION
    assert captured["provider"] == "byteplus"


def _bundle(
    path: Path,
    *,
    unsafe_name: str | None = None,
) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("run.sh", "#!/bin/bash\n")
        archive.writestr("requirements.txt", "veadk-python\n")
        if unsafe_name:
            archive.writestr(unsafe_name, "unsafe")


def test_extract_studio_bundle_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bundle.zip"
    _bundle(archive, unsafe_name="../outside.txt")

    with pytest.raises(StudioReleaseError, match="unsafe path"):
        extract_studio_bundle(archive, tmp_path / "package")


def test_self_update_preserves_deployed_branding_logo(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    updater = StudioSelfUpdater(
        settings=_settings(provider="byteplus"),
        credential_resolver=lambda: ("ak", "sk", "token"),
        branding_logo=SiteLogo(
            content=b"logo",
            media_type="image/png",
            extension="png",
        ),
    )

    updater._prepare_package(package)

    assert (package / "site-logo.png").read_bytes() == b"logo"
    run_script = (package / "run.sh").read_text(encoding="utf-8")
    assert '--site-logo "$ROOT_DIR/site-logo.png"' in run_script
    assert "--provider byteplus" in run_script


def test_submit_latest_uses_fixed_deployment_ids_and_sts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "source.zip"
    _bundle(archive)
    content = archive.read_bytes()
    manifest = StudioReleaseManifest(
        version="20260724153045",
        git_sha="a" * 40,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        created_at="2026-07-24T15:30:45+08:00",
    )
    captured: dict[str, Any] = {}

    class _Store:
        def latest_manifest(self) -> StudioReleaseManifest:
            return manifest

        def release_catalog(self) -> list[StudioReleaseManifest]:
            return [manifest]

        def download_bundle(
            self, release: StudioReleaseManifest, destination: Path
        ) -> None:
            assert release == manifest
            destination.write_bytes(content)

    class _VeFaaS:
        def __init__(self, **kwargs: str) -> None:
            captured["credentials"] = kwargs
            self.client = object()

        def submit_application_code_bundle_update(self, **kwargs: Any) -> None:
            package = Path(str(kwargs["path"]))
            assert "--provider byteplus" in (package / "run.sh").read_text(
                encoding="utf-8"
            )
            assert (package / "requirements.txt").is_file()
            captured["update"] = kwargs

    def _resources(**kwargs: Any) -> dict[str, str]:
        captured["resource_request"] = kwargs
        return {
            "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
            "VEADK_STUDIO_TOS_REGION": "ap-southeast-1",
            "SANDBOX_CHAT_CODEX_SNAPSHOT": "codex-snapshot-tool",
            "SANDBOX_CHAT_OPENCLAW_SNAPSHOT": "openclaw-snapshot-tool",
            "SANDBOX_CHAT_HERMES_SNAPSHOT": "hermes-snapshot-tool",
        }

    updater = StudioSelfUpdater(
        settings=_settings(
            deployment_region="ap-southeast-1",
            provider="byteplus",
        ),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _VeFaaS)
    monkeypatch.setattr(
        "frontend.server.studio_update_resources.reconcile_studio_update_resources",
        _resources,
    )

    def _deploy_scheduler_for_update(
        service: Any, **kwargs: Any
    ) -> tuple[str, str, str, str, str]:
        captured["scheduler_service"] = service
        captured["scheduler_update"] = kwargs
        return (
            "scheduler-function",
            "scheduler-timer",
            "worker-function",
            "worker-timer",
            "studio-app",
        )

    monkeypatch.setattr(
        "frontend.service.studio_scheduler.deploy.deploy_scheduler_for_studio_update",
        _deploy_scheduler_for_update,
    )
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")

    assert updater.submit_latest() == manifest

    assert captured["credentials"] == {
        "access_key": "sts-ak",
        "secret_key": "sts-sk",
        "session_token": "sts-token",
        "region": "ap-southeast-1",
        "project_name": "default",
        "provider": "byteplus",
    }
    update = captured["update"]
    assert update["application_id"] == "application-id"
    assert update["function_id"] == "function-id"
    assert update["environment_overrides"] == {
        "VEADK_STUDIO_RELEASE_VERSION": manifest.version,
        "CLOUD_PROVIDER": "byteplus",
        "AGENTKIT_CLOUD_PROVIDER": "byteplus",
        "BYTEPLUS_REGION": "ap-southeast-1",
        "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
        "VEADK_STUDIO_TOS_REGION": "ap-southeast-1",
        "VEADK_STUDIO_CRONJOB_SCHEDULER_BASE": "studio-app",
        "SANDBOX_CHAT_CODEX_SNAPSHOT": "codex-snapshot-tool",
        "SANDBOX_CHAT_OPENCLAW_SNAPSHOT": "openclaw-snapshot-tool",
        "SANDBOX_CHAT_HERMES_SNAPSHOT": "hermes-snapshot-tool",
    }
    resource_request = captured["resource_request"]
    assert resource_request["provider"] == "byteplus"
    assert resource_request["region"] == "ap-southeast-1"
    assert resource_request["application_id"] == "application-id"
    assert resource_request["function_id"] == "function-id"
    assert resource_request["function_client"] is not None
    scheduler_update = captured["scheduler_update"]
    assert scheduler_update["studio_function_id"] == "function-id"
    assert scheduler_update["package_root"].name == "package"
    assert scheduler_update["provider"] == "byteplus"
    assert scheduler_update["project"] == "default"
    assert scheduler_update["environment_overrides"] == {
        "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
        "VEADK_STUDIO_TOS_REGION": "ap-southeast-1",
        "SANDBOX_CHAT_CODEX_SNAPSHOT": "codex-snapshot-tool",
        "SANDBOX_CHAT_OPENCLAW_SNAPSHOT": "openclaw-snapshot-tool",
        "SANDBOX_CHAT_HERMES_SNAPSHOT": "hermes-snapshot-tool",
    }
    status = updater.status()
    assert status["state"] == "updating"
    assert status["progressStage"] == "publishing"
    assert status["progressMessage"] == "已提交，正在等待新 Revision 发布"
    assert status["targetVersion"] == manifest.version
    assert status["startedAt"] > 0


def test_submit_latest_reports_missing_vefaas_permissions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "source.zip"
    _bundle(archive)
    content = archive.read_bytes()
    manifest = StudioReleaseManifest(
        version="20260724153045",
        git_sha="a" * 40,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        created_at="2026-07-24T15:30:45+08:00",
    )

    class _Store:
        def latest_manifest(self) -> StudioReleaseManifest:
            return manifest

        def release_catalog(self) -> list[StudioReleaseManifest]:
            return [manifest]

        def download_bundle(
            self, release: StudioReleaseManifest, destination: Path
        ) -> None:
            assert release == manifest
            destination.write_bytes(content)

    class _VeFaaS:
        def __init__(self, **_kwargs: str) -> None:
            self.client = object()

        def submit_application_code_bundle_update(self, **_kwargs: Any) -> None:
            raise RuntimeError(
                "AccessDenied: permission denied for sts-ak/sts-sk "
                "at https://upload.example.com/object?token=sts-token"
            )

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _VeFaaS)
    monkeypatch.setattr(
        "frontend.server.studio_update_resources.reconcile_studio_update_resources",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        "frontend.service.studio_scheduler.deploy.deploy_scheduler_for_studio_update",
        lambda *_args, **_kwargs: (
            "scheduler-function",
            "scheduler-timer",
            "worker-function",
            "worker-timer",
            "studio",
        ),
    )
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")

    with pytest.raises(StudioReleaseError, match="Studio 更新权限不足"):
        updater.submit_latest()

    status = updater.status()
    assert status["state"] == "error"
    assert status["errorId"]
    assert status["errorStage"] == "submitting"
    assert "AccessDenied: permission denied" in status["errorLog"]
    assert "applicationId=application-id" in status["errorLog"]
    assert "functionId=function-id" in status["errorLog"]
    assert "sts-ak" not in status["errorLog"]
    assert "sts-sk" not in status["errorLog"]
    assert "sts-token" not in status["errorLog"]
    assert "?[REDACTED]" in status["errorLog"]
    assert status["consoleUrl"] == (
        "https://console.volcengine.com/vefaas/"
        "region:vefaas+cn-beijing/function/detail/function-id"
    )


def test_submit_latest_stops_before_bundle_reads_when_precheck_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(
        updater,
        "_permission_report",
        lambda _credentials: SimpleNamespace(
            ready=False,
            missing_actions=("vefaas:CreateDependencyInstallTask",),
        ),
    )
    monkeypatch.setattr(
        updater,
        "_store",
        lambda *_args: pytest.fail(
            "bundle store must not be read after failed precheck"
        ),
    )

    with pytest.raises(StudioReleaseError, match="请先完成授权"):
        updater.submit_latest()

    assert updater._last_error == "Studio 更新缺少 1 项 IAM 权限，请先完成授权"
    assert updater._error_stage == "permissions"


def test_submit_latest_stops_before_upload_when_resource_migration_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "source.zip"
    _bundle(archive)
    content = archive.read_bytes()
    manifest = StudioReleaseManifest(
        version="20260724153045",
        git_sha="a" * 40,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        created_at="2026-07-24T15:30:45+08:00",
    )
    submitted = False

    class _Store:
        def latest_manifest(self) -> StudioReleaseManifest:
            return manifest

        def download_bundle(
            self, release: StudioReleaseManifest, destination: Path
        ) -> None:
            assert release == manifest
            destination.write_bytes(content)

    class _VeFaaS:
        def __init__(self, **_kwargs: str) -> None:
            self.client = object()

        def submit_application_code_bundle_update(self, **_kwargs: Any) -> None:
            nonlocal submitted
            submitted = True

    def _fail_resource_migration(**_kwargs: Any) -> dict[str, str]:
        raise RuntimeError("snapshot tool provisioning failed")

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _VeFaaS)
    monkeypatch.setattr(
        "frontend.server.studio_update_resources.reconcile_studio_update_resources",
        _fail_resource_migration,
    )
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")

    with pytest.raises(StudioReleaseError, match="Studio 更新提交失败"):
        updater.submit_latest()

    status = updater.status()
    assert submitted is False
    assert status["errorStage"] == "provisioning"
    assert "snapshot tool provisioning failed" in status["errorLog"]


def test_byteplus_console_url_uses_byteplus_domain() -> None:
    updater = StudioSelfUpdater(
        settings=_settings(
            provider="byteplus",
            deployment_region="ap-southeast-1",
        ),
        credential_resolver=lambda: ("ak", "sk", ""),
        branding_logo=None,
    )

    assert updater._console_url() == (
        "https://console.byteplus.com/vefaas/"
        "region:vefaas+ap-southeast-1/function/detail/function-id"
    )
    assert updater._permission_console_url() == "https://console.byteplus.com/iam"


def test_volcengine_permission_console_url_uses_volcengine_domain() -> None:
    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("ak", "sk", ""),
        branding_logo=None,
    )

    assert updater._permission_console_url() == "https://console.volcengine.com/iam"


def test_application_status_uses_current_function_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Client:
        def get_function(self, request: Any) -> SimpleNamespace:
            captured["function_id"] = request.id
            return SimpleNamespace(
                envs=[
                    SimpleNamespace(
                        key="VEADK_STUDIO_RELEASE_VERSION",
                        value="20260810201000",
                    )
                ],
                last_update_time="2026-08-10 13:34:01.333 +0000 UTC",
            )

    class _VeFaaS:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)
            self.client = _Client()

        def _get_application_status(self, application_id: str) -> tuple[str, dict]:
            captured["application_id"] = application_id
            return (
                "deploy_success",
                {
                    "Result": {
                        "CloudResource": json.dumps(
                            {
                                "framework": {
                                    "function": {
                                        "Envs": [
                                            {
                                                "Key": "VEADK_STUDIO_RELEASE_VERSION",
                                                "Value": "bundled",
                                            }
                                        ],
                                        "LastUpdateTime": (
                                            "2026-08-10 13:30:00.000 +0000 UTC"
                                        ),
                                    }
                                }
                            }
                        ),
                        "StableRevisionNumber": 4,
                        "UpdateTime": "2026-08-10T13:34:50.417Z",
                    }
                },
            )

    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _VeFaaS)
    updater = StudioSelfUpdater(
        settings=_settings(
            provider="byteplus",
            deployment_region="ap-southeast-1",
        ),
        credential_resolver=lambda: ("ak", "sk", "token"),
        branding_logo=None,
    )

    assert updater._application_status() == (
        "deploy_success",
        "20260810201000",
        4,
        False,
    )
    assert captured["provider"] == "byteplus"
    assert captured["function_id"] == "function-id"
    assert captured["application_id"] == "application-id"


@pytest.mark.parametrize(
    ("provider", "deployment_region"),
    [
        ("volcengine", "cn-beijing"),
        ("byteplus", "ap-southeast-1"),
    ],
)
def test_vefaas_update_logs_use_provider_revision_cache_and_redaction(
    monkeypatch: pytest.MonkeyPatch,
    provider: CloudProvider,
    deployment_region: str,
) -> None:
    calls: list[dict[str, Any]] = []
    clients: list[dict[str, str]] = []

    class _VeFaaS:
        def __init__(self, **kwargs: str) -> None:
            clients.append(kwargs)

        def _get_application_logs(self, app_id: str, **kwargs: Any) -> list[str]:
            calls.append({"app_id": app_id, **kwargs})
            return [
                *(f"build line {index}" for index in range(220)),
                "access_key=sts-ak",
                "https://upload.example.com/object?token=sts-token",
            ]

    updater = StudioSelfUpdater(
        settings=_settings(
            deployment_region=deployment_region,
            provider=provider,
        ),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _VeFaaS)

    first = updater._load_vefaas_logs(7)
    second = updater._load_vefaas_logs(7)

    assert first == second
    assert len(calls) == 1
    assert clients[0]["provider"] == provider
    assert clients[0]["region"] == deployment_region
    assert calls[0] == {
        "app_id": "application-id",
        "revision_number": 7,
        "limit": 32 * 1024,
    }
    assert len(first) <= 200
    assert "sts-ak" not in "\n".join(first)
    assert "sts-token" not in "\n".join(first)
    assert "access_key=***" in first
    assert "https://upload.example.com/object?[REDACTED]" in first


@pytest.mark.parametrize(
    "error",
    [
        ValueError(
            "Get application log failed. Response: "
            "{'ResponseMetadata': {'Error': {'Code': 'AccessDenied'}}}"
        ),
        RuntimeError("Forbidden: no permission to GetApplicationRevisionLog"),
    ],
)
def test_vefaas_log_permission_denial_hides_log_region(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    class _VeFaaS:
        def __init__(self, **_kwargs: str) -> None:
            pass

        def _get_application_logs(self, *_args: Any, **_kwargs: Any) -> list[str]:
            raise error

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("ak", "sk", "token"),
        branding_logo=None,
    )
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _VeFaaS)

    assert updater._load_vefaas_logs(7) == []
    progress = updater._progress_payload()
    assert progress["updateLogsVisible"] is False
    assert progress["permissionConsoleUrl"] == "https://console.volcengine.com/iam"


def test_non_permission_log_error_keeps_log_region_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _VeFaaS:
        def __init__(self, **_kwargs: str) -> None:
            pass

        def _get_application_logs(self, *_args: Any, **_kwargs: Any) -> list[str]:
            raise TimeoutError("VeFaaS log request timed out")

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("ak", "sk", "token"),
        branding_logo=None,
    )
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _VeFaaS)

    assert updater._load_vefaas_logs(7) == []
    assert updater._progress_payload()["updateLogsVisible"] is True


def test_update_routes_require_admin_and_custom_header() -> None:
    submitted: list[str | None] = []
    requested_status: list[tuple[str | None, int | None]] = []
    app = FastAPI()
    updater = SimpleNamespace(
        status=lambda *, target_version=None, started_at=None: (
            requested_status.append((target_version, started_at))
            or {
                "enabled": True,
                "currentVersion": "bundled",
                "latestVersion": "20260724153045",
                "available": True,
            }
        ),
        permission_precheck=lambda: {
            "ready": False,
            "missingActions": ["vefaas:CreateTimer"],
            "policyName": "VeADKFrontendPolicy",
            "authorizationUrl": "https://api.volcengine.com/api-explorer/",
            "iamConsoleUrl": "https://console.volcengine.com/iam/policymanage",
            "principalName": "VeADKFrontendServiceRole",
        },
        submit_version=lambda version: submitted.append(version) or _manifest(),
    )

    def _admin(request: Request) -> None:
        if request.headers.get("X-Admin") != "1":
            raise HTTPException(status_code=403)

    mount_studio_update_routes(app, cast(Any, updater), _admin)
    client = TestClient(app)

    assert client.get("/web/studio-update").status_code == 403
    assert client.get("/web/studio-update/permissions").status_code == 403
    permission_response = client.get(
        "/web/studio-update/permissions", headers={"X-Admin": "1"}
    )
    assert permission_response.status_code == 200
    assert permission_response.json()["missingActions"] == ["vefaas:CreateTimer"]
    assert (
        client.get(
            "/web/studio-update?targetVersion=20260724153045&startedAt=123456",
            headers={"X-Admin": "1"},
        ).status_code
        == 200
    )
    assert requested_status == [("20260724153045", 123456)]
    assert (
        client.get(
            "/web/studio-update?targetVersion=invalid",
            headers={"X-Admin": "1"},
        ).status_code
        == 400
    )
    assert (
        client.get(
            "/web/studio-update?startedAt=invalid",
            headers={"X-Admin": "1"},
        ).status_code
        == 400
    )
    assert (
        client.post("/web/studio-update", headers={"X-Admin": "1"}).status_code == 403
    )
    response = client.post(
        "/web/studio-update",
        headers={"X-Admin": "1", "X-VeADK-Studio-Update": "1"},
        json={"version": "20260724153045"},
    )
    assert response.status_code == 202
    assert response.json()["version"] == "20260724153045"
    assert submitted == ["20260724153045"]


def test_status_lists_only_newer_releases_with_changelog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = StudioReleaseManifest(
        version="20260724143045",
        git_sha="b" * 40,
        sha256="c" * 64,
        size=1,
        created_at="2026-07-24T14:30:45+08:00",
    )
    latest = _manifest()

    class _Store:
        def latest_manifest(self) -> StudioReleaseManifest:
            return latest

        def release_catalog(self) -> list[StudioReleaseManifest]:
            return [latest, current]

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr(
        updater,
        "_application_status",
        lambda: ("deploy_success", current.version, 3, False),
    )
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", current.version)

    status = updater.status()

    assert status["available"] is True
    assert status["releases"] == [
        {
            "version": latest.version,
            "gitSha": latest.git_sha,
            "createdAt": latest.created_at,
            "changelog": ["支持选择更新版本"],
        }
    ]


@pytest.mark.parametrize(
    ("application_status", "expected_state", "expected_stage"),
    [
        ("deploying", "updating", "publishing"),
        ("deploy_success", "updating", "publishing"),
        ("deploy_fail", "error", "error"),
    ],
)
def test_status_recovers_update_from_vefaas_control_plane(
    monkeypatch: pytest.MonkeyPatch,
    application_status: str,
    expected_state: str,
    expected_stage: str,
) -> None:
    manifest = _manifest()

    class _Store:
        def latest_manifest(self) -> StudioReleaseManifest:
            return manifest

        def release_catalog(self) -> list[StudioReleaseManifest]:
            return [manifest]

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr(
        updater,
        "_application_status",
        lambda: (application_status, manifest.version, 4, False),
    )
    requested_revisions: list[int] = []
    monkeypatch.setattr(
        updater,
        "_load_vefaas_logs",
        lambda revision: requested_revisions.append(revision) or ["cloud build log"],
    )
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")

    status = updater.status(target_version=manifest.version)

    assert status["state"] == expected_state
    assert status["progressStage"] == expected_stage
    assert status["targetVersion"] == manifest.version
    assert status["updateLogs"][-1] == "cloud build log"
    assert requested_revisions == [4]
    if application_status == "deploy_fail":
        assert status["errorId"]
        assert status["errorStage"] == "publishing"
        assert "deploy_fail" in status["errorLog"]


def test_status_streams_vefaas_logs_during_local_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()

    class _Store:
        def latest_manifest(self) -> StudioReleaseManifest:
            return manifest

        def release_catalog(self) -> list[StudioReleaseManifest]:
            return [manifest]

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")
    updater._target_version = manifest.version
    updater._started_at = 123456
    updater._set_progress("publishing", "已提交，正在等待新 Revision 发布")
    monkeypatch.setattr(
        updater,
        "_load_vefaas_logs",
        lambda revision: [f"revision={revision}", "Function installing dependencies"],
    )

    status = updater.status(
        target_version=manifest.version,
        started_at=123456,
    )

    assert status["state"] == "updating"
    assert status["progressStage"] == "publishing"
    assert status["updateLogs"][-2:] == [
        "revision=0",
        "Function installing dependencies",
    ]


def test_status_rejects_stale_deploy_success_for_unsubmitted_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()

    class _Store:
        def latest_manifest(self) -> StudioReleaseManifest:
            return manifest

        def release_catalog(self) -> list[StudioReleaseManifest]:
            return [manifest]

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr(
        updater,
        "_application_status",
        lambda: ("deploy_success", "20260724143045", 3, False),
    )
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "20260724143045")

    status = updater.status(target_version=manifest.version)

    assert status["state"] == "error"
    assert status["errorStage"] == "submitting"
    assert status["targetVersion"] == manifest.version
    assert status["message"] == "目标版本未成功提交，请重新尝试更新"
    assert updater._last_error == ""
    assert updater.status()["state"] == "idle"


def test_status_waits_during_cross_instance_submission_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()

    class _Store:
        def latest_manifest(self) -> StudioReleaseManifest:
            return manifest

        def release_catalog(self) -> list[StudioReleaseManifest]:
            return [manifest]

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr(
        updater,
        "_application_status",
        lambda: ("deploy_success", "20260724143045", 3, False),
    )
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "20260724143045")

    started_at = int(time.time() * 1000) - 5 * 60 * 1000
    status = updater.status(
        target_version=manifest.version,
        started_at=started_at,
    )

    assert status["state"] == "updating"
    assert status["progressStage"] == "submitting"
    assert status["message"] == "正在等待 Function 更新提交"
    assert status["errorId"] == ""


def test_status_rejects_target_after_cross_instance_submission_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()

    class _Store:
        def latest_manifest(self) -> StudioReleaseManifest:
            return manifest

        def release_catalog(self) -> list[StudioReleaseManifest]:
            return [manifest]

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr(
        updater,
        "_application_status",
        lambda: ("deploy_success", "20260724143045", 3, False),
    )
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "20260724143045")

    status = updater.status(
        target_version=manifest.version,
        started_at=int(time.time() * 1000) - 11 * 60 * 1000,
    )

    assert status["state"] == "error"
    assert status["errorStage"] == "submitting"
    assert status["message"] == "目标版本未成功提交，请重新尝试更新"


def test_status_treats_newer_release_as_completed_stale_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()

    class _Store:
        def latest_manifest(self) -> StudioReleaseManifest:
            return manifest

        def release_catalog(self) -> list[StudioReleaseManifest]:
            return [manifest]

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr(
        updater,
        "_application_status",
        lambda: pytest.fail("completed stale targets must not query VeFaaS"),
    )
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "20260724163045")

    status = updater.status(target_version=manifest.version, started_at=123456)

    assert status["state"] == "idle"
    assert status["progressStage"] == "complete"
    assert status["targetVersion"] == manifest.version
    assert status["updateLogs"][-1] == "更新完成：新 Revision 已接管服务"


def test_status_reports_function_update_without_revision_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()

    class _Store:
        def latest_manifest(self) -> StudioReleaseManifest:
            return manifest

        def release_catalog(self) -> list[StudioReleaseManifest]:
            return [manifest]

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr(
        updater,
        "_application_status",
        lambda: ("deploy_success", manifest.version, 3, True),
    )
    monkeypatch.setattr(updater, "_load_vefaas_logs", lambda _revision: [])
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")

    status = updater.status(target_version=manifest.version)

    assert status["state"] == "error"
    assert status["errorStage"] == "publishing"
    assert status["message"] == "Function 已更新但 Revision 未发布，请重新尝试更新"


def test_status_infers_target_when_another_device_observes_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()

    class _Store:
        def latest_manifest(self) -> StudioReleaseManifest:
            return manifest

        def release_catalog(self) -> list[StudioReleaseManifest]:
            return [manifest]

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr(
        updater,
        "_application_status",
        lambda: ("deploying", manifest.version, 4, False),
    )
    monkeypatch.setattr(updater, "_load_vefaas_logs", lambda _revision: [])
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")

    status = updater.status()

    assert status["state"] == "updating"
    assert status["progressStage"] == "publishing"
    assert status["targetVersion"] == manifest.version


def test_submit_version_rejects_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    selected = _manifest()

    class _Store:
        def manifest(self, version: str) -> StudioReleaseManifest:
            assert version == selected.version
            return selected

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "20260724163045")

    with pytest.raises(StudioReleaseError, match="只能选择比当前版本新的"):
        updater.submit_version(selected.version)


def test_retry_clears_previous_failure_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "source.zip"
    _bundle(archive)
    content = archive.read_bytes()
    manifest = StudioReleaseManifest(
        version="20260724153045",
        git_sha="a" * 40,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        created_at="2026-07-24T15:30:45+08:00",
    )

    class _Store:
        def manifest(self, version: str) -> StudioReleaseManifest:
            assert version == manifest.version
            return manifest

        def latest_manifest(self) -> StudioReleaseManifest:
            return manifest

        def release_catalog(self) -> list[StudioReleaseManifest]:
            return [manifest]

        def download_bundle(
            self, release: StudioReleaseManifest, destination: Path
        ) -> None:
            assert release == manifest
            destination.write_bytes(content)

    attempts = 0

    class _VeFaaS:
        def __init__(self, **_kwargs: str) -> None:
            self.client = object()

        def submit_application_code_bundle_update(self, **_kwargs: Any) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("first attempt failed")

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _VeFaaS)
    monkeypatch.setattr(
        "frontend.server.studio_update_resources.reconcile_studio_update_resources",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr(
        "frontend.service.studio_scheduler.deploy.deploy_scheduler_for_studio_update",
        lambda *_args, **_kwargs: (
            "scheduler-function",
            "scheduler-timer",
            "worker-function",
            "worker-timer",
            "studio",
        ),
    )
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")

    with pytest.raises(StudioReleaseError, match="Studio 更新提交失败"):
        updater.submit_version(manifest.version)
    first_error_id = updater.status()["errorId"]

    assert updater.submit_version(manifest.version) == manifest
    status = updater.status()
    assert attempts == 2
    assert first_error_id
    assert status["errorId"] == ""
    assert status["errorStage"] == ""
    assert "first attempt failed" not in status["errorLog"]
    assert status["progressStage"] == "publishing"
