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

from __future__ import annotations

from pathlib import Path

import pytest

from veadk.cli.studio_package import (
    build_local_studio_requirements,
    write_studio_package,
)
from veadk.cli.studio_sidecar_prerequisites import (
    DEFAULT_SIDECAR_BASE_IMAGE,
    SIDECAR_BASE_IMAGE_ENV,
    SIDECAR_REGIONS_ENV,
    StudioSidecarConfigurationError,
    managed_studio_sidecar_base_image,
    normalize_studio_sidecar_environment,
    resolve_studio_sidecar_environment,
)


def test_write_studio_package_bootstraps_the_preloaded_cli_archive(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"

    write_studio_package(
        package,
        requirements="veadk-python\n",
        site_logo=None,
        provider="volcengine",
    )

    run_script = (package / "run.sh").read_text(encoding="utf-8")
    assert "export VEADK_AGENTKIT_CLI=" not in run_script
    assert (
        'export VEADK_STUDIO_AGENTKIT_CLI_ARCHIVE="$ROOT_DIR/'
        'agentkit-linux-x64.tar.gz"' in run_script
    )
    assert "VEADK_STUDIO_AGENTKIT_CLI_RUNTIME_MANIFEST" in run_script
    assert '--archive "$ROOT_DIR/agentkit-linux-x64.tar.gz"' in run_script


def test_write_studio_update_package_bootstraps_cli_from_remote_artifact(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"

    write_studio_package(
        package,
        requirements="veadk-python\n",
        site_logo=None,
        provider="byteplus",
        bundle_agentkit_cli=False,
    )

    run_script = (package / "run.sh").read_text(encoding="utf-8")
    assert "studio_companion --provider byteplus" in run_script
    assert "--archive" not in run_script
    assert "--runtime-manifest" not in run_script
    assert "export VEADK_STUDIO_AGENTKIT_CLI_ARCHIVE=" not in run_script
    assert "export VEADK_STUDIO_AGENTKIT_CLI_RUNTIME_MANIFEST=" not in run_script


def test_local_studio_update_skips_full_offline_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    package = tmp_path / "package"
    source_root.mkdir()
    (source_root / "pyproject.toml").write_text("", encoding="utf-8")
    (source_root / "uv.lock").write_text("", encoding="utf-8")
    (source_root / "README.md").write_text("", encoding="utf-8")
    (source_root / "LICENSE").write_text("", encoding="utf-8")
    (source_root / "frontend").mkdir()
    (source_root / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (source_root / "frontend" / "package-lock.json").write_text("{}", encoding="utf-8")
    (source_root / "veadk").mkdir()

    monkeypatch.setattr(
        "veadk.cli.studio_package._stage_wheel_source",
        lambda _source, _assets, wheel_source: wheel_source.mkdir(parents=True),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.shutil.which", lambda _: "/usr/bin/uv"
    )

    def _build(command: list[str], *, check: bool) -> None:
        assert check is True
        output_dir = Path(command[-1])
        (output_dir / "veadk_python-test-py3-none-any.whl").write_bytes(b"wheel")

    monkeypatch.setattr("veadk.cli.studio_package.subprocess.run", _build)
    monkeypatch.setattr(
        "veadk.cli.studio_package.validate_studio_wheel", lambda *_args: None
    )

    def _stage_dependencies(destination: Path, **_: object) -> tuple[Path, ...]:
        dependency = destination / "dependency-test-py3-none-any.whl"
        dependency.write_bytes(b"dependency")
        return (dependency,)

    monkeypatch.setattr(
        "veadk.cli.studio_package.stage_studio_dependency_wheels",
        _stage_dependencies,
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.stage_studio_dependency_sources",
        lambda *_args, **_kwargs: pytest.fail("thin update staged source archives"),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.stage_studio_agentkit_cli_archive",
        lambda *_args, **_kwargs: pytest.fail("thin update staged the CLI archive"),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_package.build_studio_offline_runtime",
        lambda *_args, **_kwargs: pytest.fail("thin update built an offline runtime"),
    )

    requirements = build_local_studio_requirements(
        source_root,
        package,
        provider="byteplus",
        offline_runtime=False,
    )

    assert requirements == (
        "./dependency-test-py3-none-any.whl\n./veadk_python-test-py3-none-any.whl\n"
    )
    assert sorted(path.name for path in package.iterdir()) == [
        "dependency-test-py3-none-any.whl",
        "veadk_python-test-py3-none-any.whl",
    ]


def test_project_keeps_native_cli_outside_python_distributions() -> None:
    root = Path(__file__).resolve().parents[2]
    project = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert "volcengine-agentkit-cli-bin" not in project
    assert not (root / "veadk" / "cli" / "assets" / "agentkit-cli").exists()


def test_sidecar_environment_accepts_public_image_without_region_configuration() -> (
    None
):
    image = "registry.example.com/agentkit/base@sha256:" + "a" * 64

    assert normalize_studio_sidecar_environment(
        provider="volcengine",
        base_image=image,
        regions=None,
    ) == {SIDECAR_BASE_IMAGE_ENV: image}
    assert (
        normalize_studio_sidecar_environment(
            provider="volcengine",
            base_image=None,
            regions=None,
        )
        == {}
    )


def test_sidecar_environment_requires_immutable_operator_override() -> None:
    with pytest.raises(StudioSidecarConfigurationError, match="immutable OCI"):
        normalize_studio_sidecar_environment(
            provider="volcengine",
            base_image="registry.example.com/agentkit/base:latest",
            regions="cn-shanghai",
        )


def test_sidecar_environment_ignores_legacy_region_allowlist() -> None:
    environment = normalize_studio_sidecar_environment(
        provider="volcengine",
        base_image="registry.example.com/agentkit/base@sha256:" + "b" * 64,
        regions=" cn-shanghai,cn-beijing,cn-shanghai ",
    )

    assert environment == {
        SIDECAR_BASE_IMAGE_ENV: (
            "registry.example.com/agentkit/base@sha256:" + "b" * 64
        ),
    }


def test_sidecar_release_default_is_public_immutable_artifact() -> None:
    assert managed_studio_sidecar_base_image() == DEFAULT_SIDECAR_BASE_IMAGE
    assert "@sha256:" in DEFAULT_SIDECAR_BASE_IMAGE


def test_sidecar_environment_rejects_byteplus() -> None:
    with pytest.raises(StudioSidecarConfigurationError, match="only on Volcengine"):
        normalize_studio_sidecar_environment(
            provider="byteplus",
            base_image="registry.example.com/agentkit/base@sha256:" + "c" * 64,
            regions="cn-shanghai",
        )


def test_update_inherits_complete_sidecar_environment() -> None:
    environment = resolve_studio_sidecar_environment(
        provider="volcengine",
        base_image=None,
        regions=None,
        current_environment={
            SIDECAR_BASE_IMAGE_ENV: (
                "registry.example.com/agentkit/base@sha256:" + "d" * 64
            ),
            SIDECAR_REGIONS_ENV: "cn-shanghai",
        },
    )

    assert environment == {
        SIDECAR_BASE_IMAGE_ENV: (
            "registry.example.com/agentkit/base@sha256:" + "d" * 64
        ),
    }


def test_update_explicit_image_does_not_require_inherited_region() -> None:
    image = "registry.example.com/agentkit/base@sha256:" + "e" * 64

    assert resolve_studio_sidecar_environment(
        provider="volcengine",
        base_image=image,
        regions=None,
        current_environment={SIDECAR_REGIONS_ENV: "cn-shanghai"},
    ) == {SIDECAR_BASE_IMAGE_ENV: image}


def test_update_ignores_obsolete_inherited_region_without_image_override() -> None:
    assert (
        resolve_studio_sidecar_environment(
            provider="volcengine",
            base_image=None,
            regions=None,
            current_environment={SIDECAR_REGIONS_ENV: "cn-shanghai"},
        )
        == {}
    )
