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

"""Tests for explicit Studio Environment build-resource deployment flags."""

import click
import pytest

from veadk.cli.cli_frontend import (
    STUDIO_ENVIRONMENT_CP_WORKSPACE_ENV,
    STUDIO_ENVIRONMENT_CR_REPOSITORY_ENV,
    _studio_environment_resource_environment,
    studio,
)


@pytest.mark.parametrize(
    ("cp_workspace", "cr_repository", "expected"),
    [
        (None, None, {}),
        (
            " cp-workspace-id ",
            None,
            {STUDIO_ENVIRONMENT_CP_WORKSPACE_ENV: "cp-workspace-id"},
        ),
        (
            None,
            " registry/namespace/repository ",
            {STUDIO_ENVIRONMENT_CR_REPOSITORY_ENV: ("registry/namespace/repository")},
        ),
        (
            "cp-workspace-name",
            "registry/namespace/repository",
            {
                STUDIO_ENVIRONMENT_CP_WORKSPACE_ENV: "cp-workspace-name",
                STUDIO_ENVIRONMENT_CR_REPOSITORY_ENV: ("registry/namespace/repository"),
            },
        ),
    ],
)
def test_environment_resource_flags_build_allow_listed_runtime_environment(
    cp_workspace: str | None,
    cr_repository: str | None,
    expected: dict[str, str],
) -> None:
    assert (
        _studio_environment_resource_environment(
            cp_workspace=cp_workspace,
            cr_repository=cr_repository,
        )
        == expected
    )


def test_environment_resource_flags_do_not_read_ambient_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(STUDIO_ENVIRONMENT_CP_WORKSPACE_ENV, "ambient-workspace")
    monkeypatch.setenv(
        STUDIO_ENVIRONMENT_CR_REPOSITORY_ENV,
        "ambient-registry/ambient-namespace/ambient-repository",
    )

    assert (
        _studio_environment_resource_environment(
            cp_workspace=None,
            cr_repository=None,
        )
        == {}
    )


def test_environment_resource_options_are_exposed_only_as_deploy_flags() -> None:
    deploy = studio.commands["deploy"]
    options = {
        option.name: option
        for option in deploy.params
        if isinstance(option, click.Option)
    }

    for name in ("environment_cp_workspace", "environment_cr_repository"):
        option = options[name]
        assert option.default is None
        assert option.envvar is None


@pytest.mark.parametrize(
    "value",
    [
        "registry/namespace",
        "registry//repository",
        "registry/../repository",
        "registry/name space/repository",
    ],
)
def test_environment_cr_repository_flag_requires_three_safe_segments(
    value: str,
) -> None:
    with pytest.raises(click.BadParameter, match="registry/namespace/repository"):
        _studio_environment_resource_environment(
            cp_workspace=None,
            cr_repository=value,
        )
