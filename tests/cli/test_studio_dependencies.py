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

"""Check bundled OpenViking artifacts against the SDK dependency contract."""

import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, parse_wheel_filename

from veadk.cli.studio_dependencies import studio_dependency_wheels
from veadk.utils.cloud_provider import CloudProvider

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_openviking_wheel_satisfies_sdk_requirement(provider: CloudProvider) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = [Requirement(value) for value in project["project"]["dependencies"]]
    requirement = next(
        item
        for item in requirements
        if canonicalize_name(item.name) == "openviking-sdk"
    )
    wheels = [
        wheel
        for wheel in studio_dependency_wheels(provider)
        if parse_wheel_filename(wheel.filename)[0] == "openviking-sdk"
    ]

    assert len(wheels) == 1
    version = parse_wheel_filename(wheels[0].filename)[1]
    assert version in requirement.specifier, (
        f"{provider}: {version} violates {requirement}"
    )


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_openviking_wheel_matches_locked_artifact(provider: CloudProvider) -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    package = next(item for item in lock["package"] if item["name"] == "openviking-sdk")
    wheel = next(
        item
        for item in studio_dependency_wheels(provider)
        if parse_wheel_filename(item.filename)[0] == "openviking-sdk"
    )

    assert str(parse_wheel_filename(wheel.filename)[1]) == package["version"]
    assert any(
        artifact["url"] == wheel.url
        and Path(urlparse(artifact["url"]).path).name == wheel.filename
        and artifact["hash"] == f"sha256:{wheel.sha256}"
        for artifact in package["wheels"]
    ), f"{provider}: OpenViking wheel URL, filename or hash differs from uv.lock"
