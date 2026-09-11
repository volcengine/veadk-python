# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

import click
import pytest
from click.testing import CliRunner

from veadk.cli.cli_frontend import studio


@pytest.fixture
def deployment_started(monkeypatch):
    monkeypatch.delenv("VEADK_STUDIO_SUPER_ADMIN", raising=False)
    calls = []

    def start(*args, **kwargs):
        calls.append(True)
        raise click.ClickException("deployment-started")

    # Stop at the first deployment setup step, before credentials or cloud calls
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._restore_process_env_on_click_close", start
    )
    return calls


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
@pytest.mark.parametrize("answer", ["", "\n", "n\n", "N\n"])
def test_deploy_without_super_admin_defaults_to_cancel(
    deployment_started, provider, answer
):
    result = CliRunner().invoke(
        studio,
        ["deploy", "--provider", provider, "--vefaas-app-name", "studio-test"],
        input=answer,
    )
    assert result.exit_code != 0
    assert "未指定 --super-admin" in result.output
    assert "[y/N]" in result.output
    assert deployment_started == []


@pytest.mark.parametrize("answer", ["y\n", "Y\n"])
def test_explicit_yes_continues_deployment(deployment_started, answer):
    result = CliRunner().invoke(
        studio, ["deploy", "--vefaas-app-name", "studio-test"], input=answer
    )
    assert "deployment-started" in result.output
    assert deployment_started == [True]


@pytest.mark.parametrize("mode", ["flag", "environment", "precheck"])
def test_configured_super_admin_and_read_only_precheck_do_not_prompt(
    deployment_started, monkeypatch, mode
):
    args = ["deploy", "--vefaas-app-name", "studio-test"]
    if mode == "flag":
        args.extend(["--super-admin", "owner@example.com"])
    elif mode == "environment":
        monkeypatch.setenv("VEADK_STUDIO_SUPER_ADMIN", "owner@example.com")
    else:
        args.append("--precheck-only")
    result = CliRunner().invoke(studio, args)
    assert "[y/N]" not in result.output
    assert "deployment-started" in result.output
    assert deployment_started == [True]
