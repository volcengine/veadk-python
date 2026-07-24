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
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from veadk.cli.studio_release import StudioReleaseError, StudioReleaseManifest
from veadk.cli.studio_self_update import (
    StudioSelfUpdater,
    StudioUpdateSettings,
    extract_studio_bundle,
    mount_studio_update_routes,
)


def _manifest() -> StudioReleaseManifest:
    return StudioReleaseManifest(
        version="20260724153045",
        git_sha="a" * 40,
        sha256=hashlib.sha256(b"placeholder").hexdigest(),
        size=len(b"placeholder"),
        created_at="2026-07-24T15:30:45+08:00",
        changelog=("支持选择更新版本",),
    )


def _settings() -> StudioUpdateSettings:
    return StudioUpdateSettings(
        bucket="studio-releases",
        region="cn-beijing",
        prefix="veadk/studio/main",
        application_id="application-id",
        function_id="function-id",
        project="default",
    )


def _bundle(path: Path, *, unsafe_name: str | None = None) -> None:
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

        def submit_application_code_bundle_update(self, **kwargs: Any) -> None:
            package = Path(str(kwargs["path"]))
            assert (package / "run.sh").is_file()
            assert (package / "requirements.txt").is_file()
            captured["update"] = kwargs

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _VeFaaS)
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")

    assert updater.submit_latest() == manifest

    assert captured["credentials"] == {
        "access_key": "sts-ak",
        "secret_key": "sts-sk",
        "session_token": "sts-token",
        "region": "cn-beijing",
        "project_name": "default",
    }
    update = captured["update"]
    assert update["application_id"] == "application-id"
    assert update["function_id"] == "function-id"
    assert update["environment_overrides"] == {
        "VEADK_STUDIO_RELEASE_VERSION": manifest.version
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

        def download_bundle(
            self, release: StudioReleaseManifest, destination: Path
        ) -> None:
            assert release == manifest
            destination.write_bytes(content)

    class _VeFaaS:
        def __init__(self, **_kwargs: str) -> None:
            pass

        def submit_application_code_bundle_update(self, **_kwargs: Any) -> None:
            raise RuntimeError("AccessDenied: permission denied")

    updater = StudioSelfUpdater(
        settings=_settings(),
        credential_resolver=lambda: ("sts-ak", "sts-sk", "sts-token"),
        branding_logo=None,
    )
    monkeypatch.setattr(updater, "_store", lambda *_args: _Store())
    monkeypatch.setattr("veadk.integrations.ve_faas.ve_faas.VeFaaS", _VeFaaS)
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")

    with pytest.raises(StudioReleaseError, match="Studio 更新权限不足"):
        updater.submit_latest()


def test_update_routes_require_admin_and_custom_header() -> None:
    submitted: list[str | None] = []
    requested_targets: list[str | None] = []
    app = FastAPI()
    updater = SimpleNamespace(
        status=lambda *, target_version=None: (
            requested_targets.append(target_version)
            or {
                "enabled": True,
                "currentVersion": "bundled",
                "latestVersion": "20260724153045",
                "available": True,
            }
        ),
        submit_version=lambda version: submitted.append(version) or _manifest(),
    )

    def _admin(request: Request) -> None:
        if request.headers.get("X-Admin") != "1":
            raise HTTPException(status_code=403)

    mount_studio_update_routes(app, cast(Any, updater), _admin)
    client = TestClient(app)

    assert client.get("/web/studio-update").status_code == 403
    assert (
        client.get(
            "/web/studio-update?targetVersion=20260724153045",
            headers={"X-Admin": "1"},
        ).status_code
        == 200
    )
    assert requested_targets == ["20260724153045"]
    assert (
        client.get(
            "/web/studio-update?targetVersion=invalid",
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
    monkeypatch.setattr(updater, "_application_status", lambda: "deploy_success")
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
    monkeypatch.setattr(updater, "_application_status", lambda: application_status)
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "bundled")

    status = updater.status(target_version=manifest.version)

    assert status["state"] == expected_state
    assert status["progressStage"] == expected_stage
    assert status["targetVersion"] == manifest.version


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
    monkeypatch.setattr(updater, "_application_status", lambda: "deploying")
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
