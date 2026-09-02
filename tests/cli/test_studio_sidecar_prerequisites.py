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

from veadk.cli.studio_package import write_studio_package
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
    assert "VEADK_AGENTKIT_CLI" not in run_script
    assert '--archive "$ROOT_DIR/agentkit-linux-x64.tar.gz"' in run_script


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
