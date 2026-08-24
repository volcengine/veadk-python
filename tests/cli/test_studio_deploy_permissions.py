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

from __future__ import annotations

import pytest
from click.testing import CliRunner

from veadk.cli import studio_deploy_permissions as permissions
from veadk.cli.cli_frontend import studio


def _default_specs() -> list[permissions.PermissionSpec]:
    return permissions.required_permission_specs(
        auto_identity_resources=True,
        auto_function_role=True,
        auto_storage=True,
        auto_sandbox_tools=True,
        auto_gateway=True,
        keep_failed_deploy=False,
    )


def test_default_studio_deploy_requires_all_reachable_actions() -> None:
    specs = _default_specs()
    actions = [spec.action for spec in specs]

    assert len(actions) == 44
    assert len(actions) == len(set(actions))
    assert "id:CreateUserPool" in actions
    assert "iam:UpdatePolicy" in actions
    assert "tos:CreateBucket" in actions
    assert "agentkit:CreateTool" in actions
    assert "apig:CreateGateway" in actions
    assert "apig:UpdateRoute" in actions
    assert "vefaas:CreateApplication" in actions
    assert "vefaas:CreateTimer" in actions
    assert "vefaas:ListTriggers" in actions
    assert "vefaas:UpdateTimer" in actions
    assert "vefaas:DeleteApplication" in actions


def test_existing_resources_remove_unreachable_create_and_cleanup_actions() -> None:
    actions = {
        spec.action
        for spec in permissions.required_permission_specs(
            auto_identity_resources=False,
            auto_function_role=False,
            auto_storage=False,
            auto_sandbox_tools=False,
            auto_gateway=False,
            keep_failed_deploy=True,
        )
    }

    assert "id:CreateUserPool" not in actions
    assert "iam:UpdatePolicy" not in actions
    assert "tos:CreateBucket" not in actions
    assert "agentkit:CreateTool" not in actions
    assert "apig:CreateGateway" not in actions
    assert "apig:UpdateRoute" in actions
    assert "vefaas:DeleteApplication" not in actions
    assert "id:UpdateUserPoolClient" in actions
    assert "agentkit:UpdateTool" in actions
    assert "vefaas:CreateApplication" in actions


def test_policy_evaluation_supports_wildcards_and_explicit_deny() -> None:
    documents = [
        {
            "Statement": [
                {"Effect": "Allow", "Action": "*", "Resource": "*"},
                {
                    "Effect": "Deny",
                    "Action": ["vefaas:Delete*", "agentkit:CreateTool"],
                    "Resource": "*",
                },
            ]
        }
    ]

    assert permissions.evaluate_actions(
        [
            "vefaas:CreateApplication",
            "vefaas:DeleteApplication",
            "agentkit:CreateTool",
        ],
        documents,
    ) == {
        "vefaas:CreateApplication": True,
        "vefaas:DeleteApplication": False,
        "agentkit:CreateTool": False,
    }


def test_conditional_or_resource_scoped_policy_fails_closed() -> None:
    documents = [
        {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "tos:CreateBucket",
                    "Resource": "trn:tos:::one-bucket",
                },
                {
                    "Effect": "Allow",
                    "Action": "vefaas:*",
                    "Resource": "*",
                    "Condition": {"StringEquals": {"iam:ProjectName": "default"}},
                },
            ]
        }
    ]

    assert permissions.evaluate_actions(
        ["tos:CreateBucket", "vefaas:CreateFunction"], documents
    ) == {"tos:CreateBucket": False, "vefaas:CreateFunction": False}


def test_renderer_localizes_volcengine_and_prints_every_status(capsys) -> None:
    specs = _default_specs()[:2]
    permissions.render_permission_results(
        "volcengine",
        [
            permissions.PermissionResult(spec=specs[0], satisfied=True),
            permissions.PermissionResult(spec=specs[1], satisfied=False),
        ],
    )

    output = capsys.readouterr().out
    assert "权限名称" in output
    assert specs[0].purpose_zh in output
    assert "✅" in output
    assert "❌" in output
    assert permissions.IAM_CONFIG_URLS["volcengine"] in output


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        (
            "volcengine",
            [
                "| 权限名称 | 作用 | 是否满足 |",
                "|----------|------|----------|",
                "| iam:X    | 中文 | ✅       |",
                "| iam:Long | A    | ❌       |",
            ],
        ),
        (
            "byteplus",
            [
                "| IAM Action | Purpose | Satisfied |",
                "|------------|---------|-----------|",
                "| iam:X      | A       | ✅        |",
                "| iam:Long   | Long    | ❌        |",
            ],
        ),
    ],
)
def test_renderer_aligns_wide_text_and_status_symbols(provider, expected) -> None:
    specs = [
        permissions.PermissionSpec("iam:X", "中文", "A"),
        permissions.PermissionSpec("iam:Long", "A", "Long"),
    ]

    assert (
        permissions._table_lines(
            provider,
            [
                permissions.PermissionResult(spec=specs[0], satisfied=True),
                permissions.PermissionResult(spec=specs[1], satisfied=False),
            ],
        )
        == expected
    )


def test_renderer_localizes_byteplus_purposes_and_summary(capsys) -> None:
    spec = _default_specs()[0]
    permissions.render_permission_results(
        "byteplus",
        [permissions.PermissionResult(spec=spec, satisfied=True)],
    )

    output = capsys.readouterr().out
    assert "IAM Action" in output
    assert spec.purpose_en in output
    assert spec.purpose_zh not in output
    assert "All 1 required IAM Actions are satisfied." in output
    assert permissions.IAM_CONFIG_URLS["byteplus"] in output


@pytest.mark.parametrize(
    ("provider_args", "expected_prompt", "expected_message"),
    [
        (
            [
                "--volcengine-access-key",
                "ak",
                "--volcengine-secret-key",
                "sk",
            ],
            "是否仍要继续部署？",
            "缺少 Studio 部署所需的 IAM 权限",
        ),
        (
            [
                "--provider",
                "byteplus",
                "--byteplus-access-key",
                "ak",
                "--byteplus-secret-key",
                "sk",
            ],
            "Continue deployment anyway?",
            "required IAM Actions are missing",
        ),
    ],
)
def test_cli_stops_before_cloud_writes_when_missing_permission_is_declined(
    monkeypatch, provider_args, expected_prompt, expected_message
) -> None:
    identity_called = False

    def _precheck(*, specs, **_kwargs):
        return [
            permissions.PermissionResult(spec=spec, satisfied=index != 0)
            for index, spec in enumerate(specs)
        ]

    def _identity(**_kwargs):
        nonlocal identity_called
        identity_called = True
        raise AssertionError("identity provisioning must not start")

    monkeypatch.setattr(
        permissions,
        "run_studio_deploy_permission_precheck",
        _precheck,
    )
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._resolve_or_create_studio_identity_resources",
        _identity,
    )

    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--vefaas-app-name",
            "studio-test",
            *provider_args,
        ],
        input="n\n",
    )

    assert result.exit_code != 0
    assert expected_prompt in result.output
    assert expected_message in result.output
    assert identity_called is False


def test_cli_continues_when_missing_permission_is_accepted(monkeypatch) -> None:
    identity_called = False

    def _precheck(*, specs, **_kwargs):
        return [
            permissions.PermissionResult(spec=spec, satisfied=index != 0)
            for index, spec in enumerate(specs)
        ]

    def _identity(**_kwargs):
        nonlocal identity_called
        identity_called = True
        raise RuntimeError("identity provisioning reached")

    monkeypatch.setattr(
        permissions,
        "run_studio_deploy_permission_precheck",
        _precheck,
    )
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._resolve_or_create_studio_identity_resources",
        _identity,
    )

    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--vefaas-app-name",
            "studio-test",
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
        ],
        input="y\n",
    )

    assert result.exit_code != 0
    assert "是否仍要继续部署？" in result.output
    assert "已确认忽略缺失的 IAM 权限，继续部署。" in result.output
    assert identity_called is True
    assert isinstance(result.exception, RuntimeError)
    assert str(result.exception) == "identity provisioning reached"


def test_cli_precheck_only_exits_before_cloud_writes(monkeypatch) -> None:
    required_count = 0

    def _precheck(*, specs, **_kwargs):
        nonlocal required_count
        required_count = len(specs)
        results = [
            permissions.PermissionResult(spec=spec, satisfied=True) for spec in specs
        ]
        permissions.render_permission_results("byteplus", results)
        return results

    monkeypatch.setattr(
        permissions,
        "run_studio_deploy_permission_precheck",
        _precheck,
    )

    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--vefaas-app-name",
            "studio-test",
            "--provider",
            "byteplus",
            "--byteplus-access-key",
            "ak",
            "--byteplus-secret-key",
            "sk",
            "--precheck-only",
        ],
    )

    assert result.exit_code == 0, result.output
    assert f"All {required_count} required IAM Actions are satisfied." in result.output
    assert "Pre-check only: no cloud resources were created." in result.output


def test_cli_precheck_only_rejects_overlong_site_title_before_iam(monkeypatch) -> None:
    precheck_called = False

    def _precheck(**_kwargs):
        nonlocal precheck_called
        precheck_called = True
        return []

    monkeypatch.setattr(
        permissions,
        "run_studio_deploy_permission_precheck",
        _precheck,
    )

    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--vefaas-app-name",
            "studio-test",
            "--provider",
            "byteplus",
            "--precheck-only",
            "--site-title",
            "ABCDEFGHIJKLMNOPQ",
        ],
    )

    assert result.exit_code == 1
    assert "at most 16 characters" in result.output
    assert precheck_called is False
