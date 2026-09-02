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
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from frontend.service.studio_release_server import publisher
from frontend.service.studio_release_server.publisher import (
    StudioPublisherError,
    validate_studio_agentkit_cli_archive,
    validate_studio_bundle_dependencies,
)

from veadk.cli.studio_dependencies import (
    STUDIO_AGENTKIT_CLI_ARTIFACT,
    STUDIO_DEPENDENCY_SOURCES,
    StudioDependencyWheel,
    stage_studio_dependency_wheels,
    write_studio_dependency_manifest,
)
from veadk.cli.studio_package import build_frontend_assets, studio_run_script
from veadk.cli.studio_release import (
    BYTEPLUS_STUDIO_RELEASE_REGION,
    StudioReleaseError,
    StudioReleaseManifest,
    StudioReleaseStore,
    build_studio_release,
    bundle_object_key,
    latest_manifest_object_key,
    manifest_object_key,
    release_catalog_object_key,
    studio_release_region,
)
from veadk.utils.cloud_provider import CloudProvider


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


@pytest.mark.parametrize(
    ("provider", "region", "expected_endpoint"),
    [
        ("volcengine", "cn-beijing", "tos-cn-beijing.volces.com"),
        ("byteplus", "ap-southeast-1", "tos-ap-southeast-1.bytepluses.com"),
    ],
)
def test_release_store_uses_provider_tos_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    provider: CloudProvider,
    region: str,
    expected_endpoint: str,
) -> None:
    captured: dict[str, Any] = {}

    def _client(*args: object, **kwargs: object) -> object:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setitem(sys.modules, "tos", SimpleNamespace(TosClientV2=_client))

    StudioReleaseStore(
        bucket="studio-releases",
        region=region,
        provider=provider,
        access_key="ak",
        secret_key="sk",
    )

    assert captured["kwargs"]["endpoint"] == expected_endpoint


def test_byteplus_release_region_is_provider_specific() -> None:
    assert studio_release_region("volcengine") == "cn-beijing"
    assert studio_release_region("byteplus") == BYTEPLUS_STUDIO_RELEASE_REGION


def test_manifest_round_trip_uses_public_field_names() -> None:
    manifest = _manifest()

    payload = json.loads(manifest.to_json())

    assert payload["version"] == "20260724153045"
    assert payload["gitSha"] == "a" * 40
    assert payload["changelog"] == ["新增版本选择", "修复自更新权限"]
    assert StudioReleaseManifest.from_json(manifest.to_json()) == manifest


def test_frontend_build_exposes_release_changelog_to_vite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "frontend-output"
    captured: list[str] = []

    monkeypatch.setattr(
        "veadk.cli.studio_package._validate_source_checkout", lambda _root: None
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.shutil.which", lambda _name: "/bin/npm"
    )

    def _run(command: list[str], **kwargs: object) -> None:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        captured.append(str(environment["VITE_STUDIO_RELEASE_CHANGELOG"]))
        if "build" in command:
            output_dir.mkdir()
            (output_dir / "index.html").write_text("studio", encoding="utf-8")

    monkeypatch.setattr("veadk.cli.studio_package.subprocess.run", _run)

    build_frontend_assets(
        tmp_path,
        output_dir,
        changelog=("新增能力;修复问题", "优化体验"),
    )

    assert captured == [
        '["新增能力;修复问题", "优化体验"]',
        '["新增能力;修复问题", "优化体验"]',
    ]


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


def test_publish_does_not_move_latest_pointer_to_an_older_release(
    tmp_path: Path,
) -> None:
    client = _FakeTosClient()
    store = _store(client)
    newer_content = b"newer"
    newer_bundle = tmp_path / "newer.zip"
    newer_bundle.write_bytes(newer_content)
    newer = StudioReleaseManifest(
        version="20260724163045",
        git_sha="b" * 40,
        sha256=hashlib.sha256(newer_content).hexdigest(),
        size=len(newer_content),
        created_at="2026-07-24T16:30:45+08:00",
    )
    store.publish(newer_bundle, newer)
    put_order = list(client.put_order)

    older_content = b"older"
    older_bundle = tmp_path / "older.zip"
    older_bundle.write_bytes(older_content)
    older = _manifest(older_content)

    with pytest.raises(StudioReleaseError, match="must be newer"):
        store.publish(older_bundle, older)

    assert client.put_order == put_order
    assert store.latest_manifest() == newer


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
        "veadk.cli.studio_dependencies.studio_dependency_wheels",
        lambda _provider, **_kwargs: (dependency,),
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


def test_stage_dependency_wheels_prefers_domestic_mirrors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"downloaded-wheel"
    dependency = StudioDependencyWheel(
        filename="downloaded.whl",
        url="https://files.pythonhosted.org/packages/example/downloaded.whl",
        sha256=hashlib.sha256(content).hexdigest(),
    )
    urls: list[str] = []

    def _urlopen(url: str, *, timeout: int) -> io.BytesIO:
        urls.append(url)
        assert timeout == 60
        if url.startswith("https://pypi.tuna.tsinghua.edu.cn/"):
            raise OSError("mirror unavailable")
        return io.BytesIO(content)

    monkeypatch.setattr(
        "veadk.cli.studio_dependencies.studio_dependency_wheels",
        lambda _provider, **_kwargs: (dependency,),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_dependencies.urllib.request.urlopen",
        _urlopen,
    )

    staged = stage_studio_dependency_wheels(tmp_path / "destination")

    assert staged[0].read_bytes() == content
    assert urls == [
        "https://pypi.tuna.tsinghua.edu.cn/packages/example/downloaded.whl",
        "https://mirrors.aliyun.com/pypi/packages/example/downloaded.whl",
    ]


def test_write_dependency_manifest_uses_pinned_wheel_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dependency = StudioDependencyWheel(
        filename="prepared.whl",
        url="https://example.com/prepared.whl",
        sha256="a" * 64,
    )
    byteplus_dependency = StudioDependencyWheel(
        filename="byteplus.whl",
        url="https://example.com/byteplus.whl",
        sha256="b" * 64,
    )
    monkeypatch.setattr(
        "veadk.cli.studio_dependencies.studio_dependency_wheels",
        lambda _provider: (dependency, byteplus_dependency),
    )
    manifest = tmp_path / "dependencies.json"

    write_studio_dependency_manifest(manifest)

    assert json.loads(manifest.read_text(encoding="utf-8")) == {
        "wheels": [
            {
                "filename": dependency.filename,
                "url": dependency.url,
                "sha256": dependency.sha256,
            },
            {
                "filename": byteplus_dependency.filename,
                "url": byteplus_dependency.url,
                "sha256": byteplus_dependency.sha256,
            },
        ],
        "sources": [
            {
                "filename": source.filename,
                "url": source.url,
                "sha256": source.sha256,
            }
            for source in STUDIO_DEPENDENCY_SOURCES
        ],
        "artifacts": [
            {
                "filename": STUDIO_AGENTKIT_CLI_ARTIFACT.filename,
                "url": STUDIO_AGENTKIT_CLI_ARTIFACT.url,
                "sha256": STUDIO_AGENTKIT_CLI_ARTIFACT.sha256,
            }
        ],
    }


def test_project_does_not_depend_on_unpublished_companion() -> None:
    pyproject = (Path(__file__).parents[2] / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    assert "volcengine-agentkit-cli-bin" not in pyproject


def _write_release_package(
    destination: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    destination.mkdir(parents=True, exist_ok=True)
    veadk_wheel = destination / "veadk_python-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(veadk_wheel, "w") as archive:
        archive.writestr(
            "veadk_python-1.2.3.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: veadk-python\nVersion: 1.2.3\n",
        )
    cli_archive = destination / STUDIO_AGENTKIT_CLI_ARTIFACT.filename
    cli_archive.write_bytes(b"pinned-cli")
    monkeypatch.setattr(
        publisher,
        "_AGENTKIT_CLI_ARCHIVE_SHA256",
        hashlib.sha256(cli_archive.read_bytes()).hexdigest(),
    )
    return veadk_wheel, cli_archive


def test_release_validation_accepts_pinned_native_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _veadk_wheel, cli_archive = _write_release_package(tmp_path, monkeypatch)

    assert validate_studio_agentkit_cli_archive([cli_archive]) == cli_archive


def test_release_validation_rejects_tampered_native_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _veadk_wheel, cli_archive = _write_release_package(tmp_path, monkeypatch)
    cli_archive.write_bytes(b"tampered")

    with pytest.raises(StudioPublisherError, match="checksum"):
        validate_studio_agentkit_cli_archive([cli_archive])


def test_extracted_bundle_requires_local_pinned_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "package"
    veadk_wheel, cli_archive = _write_release_package(package, monkeypatch)
    (package / "requirements.txt").write_text(
        f"./{veadk_wheel.name} --hash=sha256:{hashlib.sha256(veadk_wheel.read_bytes()).hexdigest()}\n",
        encoding="utf-8",
    )

    assert validate_studio_bundle_dependencies(package) == cli_archive


def test_release_entrypoint_reads_deployed_provider() -> None:
    run_script = studio_run_script(provider=None)

    assert (
        '--provider "${CLOUD_PROVIDER:-${AGENTKIT_CLOUD_PROVIDER:-volcengine}}"'
        in run_script
    )
    assert "python3 -m veadk.cli.studio_companion" in run_script


def test_release_entrypoint_prefers_bundled_dependencies(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    bundled = package / "site-packages"
    platform = tmp_path / "platform-site-packages"
    bundled.mkdir(parents=True)
    platform.mkdir()
    module = "studio_dependency_precedence_probe"
    (bundled / f"{module}.py").write_text('SOURCE = "bundled"\n', encoding="utf-8")
    (platform / f"{module}.py").write_text('SOURCE = "platform"\n', encoding="utf-8")

    lines = studio_run_script(provider=None).splitlines()
    companion_index = next(
        index
        for index, line in enumerate(lines)
        if "veadk.cli.studio_companion" in line
    )
    lines[companion_index:] = [
        f'exec python3 -c "import {module}; print({module}.SOURCE)"'
    ]
    entrypoint = package / "run.sh"
    entrypoint.write_text("\n".join(lines) + "\n", encoding="utf-8")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(platform)
    completed = subprocess.run(
        ["bash", str(entrypoint)],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "bundled"


def test_publish_workflow_sends_release_request_to_server() -> None:
    workflow = (
        Path(__file__).parents[2] / ".github/workflows/publish-studio-release.yaml"
    ).read_text(encoding="utf-8")

    assert "Upload staged release source" not in workflow
    assert "sourceKey" not in workflow
    assert '"Accept": "text/event-stream"' in workflow
    assert 'source_root = Path(os.environ["GITHUB_WORKSPACE"])' in workflow


def test_pypi_publish_workflow_rejects_embedded_native_cli() -> None:
    workflow = (
        Path(__file__).parents[2] / ".github/workflows/publish-tag-to-pypi.yaml"
    ).read_text(encoding="utf-8")

    assert "agentkit-cli-companion-release-gate:" not in workflow
    assert "must not embed an AgentKit CLI archive" in workflow
    assert "must not depend on an unpublished CLI companion" in workflow


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
    captured: dict[str, object] = {}

    def fail_frontend_build(*_args: object) -> None:
        raise AssertionError("Prepared frontend must skip npm build")

    def build_requirements(
        _source_root: Path,
        package_dir: Path,
        *,
        frontend_assets: Path | None = None,
        dependency_wheels: Path | None = None,
        provider: str = "volcengine",
    ) -> str:
        captured["frontend"] = frontend_assets
        captured["wheels"] = dependency_wheels
        captured["requirements_provider"] = provider
        package_dir.mkdir(parents=True)
        (package_dir / "veadk.whl").write_bytes(b"wheel")
        return "./veadk.whl\n"

    def write_package(
        package_dir: Path,
        *,
        requirements: str,
        site_logo: object,
        provider: str | None = "volcengine",
    ) -> None:
        del site_logo
        captured["package_provider"] = provider
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
        "requirements_provider": "byteplus",
        "package_provider": None,
    }
