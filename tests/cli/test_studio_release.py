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

"""Tests for immutable Studio release artifacts."""

import hashlib
import json
from pathlib import Path

import pytest

from veadk.cli.studio_release import (
    StudioReleaseError,
    StudioReleaseManifest,
    StudioReleaseStore,
    build_studio_release,
    bundle_object_key,
    latest_manifest_object_key,
    manifest_object_key,
    release_catalog_object_key,
)
from veadk.cli.studio_dependencies import (
    StudioDependencyWheel,
    stage_studio_dependency_wheels,
)


def _manifest(content: bytes = b"bundle") -> StudioReleaseManifest:
    return StudioReleaseManifest(
        version="20260724153045",
        git_sha="a" * 40,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        created_at="2026-07-24T15:30:45+08:00",
        changelog=("新增版本选择", "修复自更新权限"),
    )


class _FakeTosClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_order: list[str] = []

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        content: bytes,
        content_type: str,
        forbid_overwrite: bool = False,
    ) -> None:
        del content_type
        if forbid_overwrite and (bucket, key) in self.objects:
            raise FileExistsError(key)
        self.objects[(bucket, key)] = content
        self.put_order.append(key)

    def get_object(self, *, bucket: str, key: str) -> list[bytes]:
        return [self.objects[(bucket, key)]]


def _store(client: _FakeTosClient) -> StudioReleaseStore:
    return StudioReleaseStore(
        bucket="studio-releases",
        region="cn-beijing",
        prefix="veadk/studio/main",
        access_key="ak",
        secret_key="sk",
        client=client,
    )


def test_manifest_round_trip_uses_public_field_names() -> None:
    manifest = _manifest()

    payload = json.loads(manifest.to_json())

    assert payload["version"] == "20260724153045"
    assert payload["gitSha"] == "a" * 40
    assert payload["changelog"] == ["新增版本选择", "修复自更新权限"]
    assert StudioReleaseManifest.from_json(manifest.to_json()) == manifest


@pytest.mark.parametrize("version", ["20260724", "20261324153045", "latest"])
def test_manifest_rejects_invalid_beijing_version(version: str) -> None:
    with pytest.raises(StudioReleaseError, match="YYYYMMDDHHMMSS"):
        StudioReleaseManifest(
            version=version,
            git_sha="a" * 40,
            sha256="b" * 64,
            size=1,
            created_at="2026-07-24T15:30:45+08:00",
        )


def test_publish_moves_latest_pointer_after_immutable_objects(tmp_path: Path) -> None:
    content = b"complete-studio-bundle"
    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(content)
    manifest = _manifest(content)
    client = _FakeTosClient()
    store = _store(client)

    store.publish(bundle, manifest)

    assert client.put_order == [
        bundle_object_key(store.prefix, manifest.version),
        manifest_object_key(store.prefix, manifest.version),
        release_catalog_object_key(store.prefix),
        latest_manifest_object_key(store.prefix),
    ]
    assert store.latest_manifest() == manifest
    assert store.release_catalog() == [manifest]


def test_publish_catalog_keeps_newest_release_first(tmp_path: Path) -> None:
    client = _FakeTosClient()
    store = _store(client)
    older_content = b"older"
    older_bundle = tmp_path / "older.zip"
    older_bundle.write_bytes(older_content)
    older = _manifest(older_content)
    store.publish(older_bundle, older)

    newer_content = b"newer"
    newer_bundle = tmp_path / "newer.zip"
    newer_bundle.write_bytes(newer_content)
    newer = StudioReleaseManifest(
        version="20260724163045",
        git_sha="b" * 40,
        sha256=hashlib.sha256(newer_content).hexdigest(),
        size=len(newer_content),
        created_at="2026-07-24T16:30:45+08:00",
        changelog=("修复更新流程",),
    )

    store.publish(newer_bundle, newer)

    assert store.release_catalog() == [newer, older]
    assert store.manifest(older.version) == older


def test_publish_does_not_replace_an_immutable_release(tmp_path: Path) -> None:
    content = b"complete-studio-bundle"
    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(content)
    manifest = _manifest(content)
    client = _FakeTosClient()
    store = _store(client)

    store.publish(bundle, manifest)

    with pytest.raises(FileExistsError):
        store.publish(bundle, manifest)


def test_download_rejects_content_with_wrong_digest(tmp_path: Path) -> None:
    manifest = _manifest(b"expected")
    client = _FakeTosClient()
    store = _store(client)
    client.objects[
        (store.bucket, bundle_object_key(store.prefix, manifest.version))
    ] = b"tampered"

    with pytest.raises(StudioReleaseError, match="checksum"):
        store.download_bundle(manifest, tmp_path / "bundle.zip")


def test_download_rejects_content_larger_than_manifest(tmp_path: Path) -> None:
    manifest = _manifest(b"small")
    client = _FakeTosClient()
    store = _store(client)
    client.objects[
        (store.bucket, bundle_object_key(store.prefix, manifest.version))
    ] = b"larger"

    with pytest.raises(StudioReleaseError, match="exceeds"):
        store.download_bundle(manifest, tmp_path / "bundle.zip")


def test_stage_dependency_wheels_copies_only_verified_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"prepared-wheel"
    dependency = StudioDependencyWheel(
        filename="prepared.whl",
        url="https://example.com/prepared.whl",
        sha256=hashlib.sha256(content).hexdigest(),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_dependencies.STUDIO_DEPENDENCY_WHEELS",
        (dependency,),
    )
    source = tmp_path / "source"
    source.mkdir()
    (source / dependency.filename).write_bytes(content)

    staged = stage_studio_dependency_wheels(
        tmp_path / "destination",
        source_dir=source,
    )

    assert [path.name for path in staged] == [dependency.filename]
    assert staged[0].read_bytes() == content


def test_build_release_uses_prepared_frontend_and_wheels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    frontend_assets = tmp_path / "prepared-frontend"
    frontend_assets.mkdir()
    (frontend_assets / "index.html").write_text("studio", encoding="utf-8")
    dependency_wheels = tmp_path / "prepared-wheels"
    dependency_wheels.mkdir()
    captured: dict[str, Path | None] = {}

    def fail_frontend_build(*_args: object) -> None:
        raise AssertionError("Prepared frontend must skip npm build")

    def build_requirements(
        _source_root: Path,
        package_dir: Path,
        *,
        frontend_assets: Path | None = None,
        dependency_wheels: Path | None = None,
    ) -> str:
        captured["frontend"] = frontend_assets
        captured["wheels"] = dependency_wheels
        package_dir.mkdir(parents=True)
        (package_dir / "veadk.whl").write_bytes(b"wheel")
        return "./veadk.whl\n"

    def write_package(
        package_dir: Path,
        *,
        requirements: str,
        site_logo: object,
    ) -> None:
        del site_logo
        (package_dir / "requirements.txt").write_text(
            requirements,
            encoding="utf-8",
        )

    monkeypatch.setattr(
        "veadk.cli.studio_package.build_frontend_assets",
        fail_frontend_build,
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_local_studio_requirements",
        build_requirements,
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.write_studio_package",
        write_package,
    )

    bundle, manifest = build_studio_release(
        source_root=source_root,
        output_dir=tmp_path / "output",
        version="20260725020000",
        git_sha="c" * 40,
        frontend_assets=frontend_assets,
        dependency_wheels=dependency_wheels,
    )

    assert bundle.is_file()
    assert manifest.git_sha == "c" * 40
    assert captured == {
        "frontend": frontend_assets,
        "wheels": dependency_wheels,
    }
