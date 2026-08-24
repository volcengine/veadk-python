# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

import json
from copy import deepcopy
from urllib.parse import parse_qs, urlparse

import pytest

from veadk.cli.frontend_deploy_policy import FRONTEND_DEPLOY_POLICY
from veadk.cli.studio_deploy_permissions import (
    AttachedPolicyDocument,
    PrincipalPolicySet,
    evaluate_actions,
)
from veadk.cli.studio_update_permissions import (
    STUDIO_UPDATE_PERMISSION_SPECS,
    StudioUpdatePermissionService,
    build_update_policy_url,
    merge_policy_actions,
)

_NEW_SCHEDULER_ACTIONS = {
    "tos:ListBucket",
    "tos:ListObjects",
    "vefaas:CreateDependencyInstallTask",
    "vefaas:GetDependencyInstallTaskStatus",
    "vefaas:GetDependencyInstallTaskLogDownloadURI",
    "vefaas:ListTriggers",
    "vefaas:CreateTimer",
    "vefaas:UpdateTimer",
}


class _Inspector:
    def __init__(self, principal: PrincipalPolicySet) -> None:
        self.principal = principal

    def principal_policies(self) -> PrincipalPolicySet:
        return self.principal


def _policy_without_scheduler_actions() -> dict:
    document = deepcopy(FRONTEND_DEPLOY_POLICY)
    actions = document["Statement"][0]["Action"]
    document["Statement"][0]["Action"] = [
        action for action in actions if action not in _NEW_SCHEDULER_ACTIONS
    ]
    document["Statement"].append(
        {"Effect": "Allow", "Action": ["custom:KeepMe"], "Resource": ["*"]}
    )
    return document


@pytest.mark.parametrize(
    ("provider", "expected_host"),
    [
        ("volcengine", "api.volcengine.com"),
        ("byteplus", "api.byteplus.com"),
    ],
)
def test_precheck_builds_prefilled_update_policy_link(provider, expected_host) -> None:
    current = _policy_without_scheduler_actions()
    principal = PrincipalPolicySet(
        kind="role",
        name="VeADKFrontendServiceRoleOtaTest",
        policies=(
            AttachedPolicyDocument(
                name="VeADKFrontendPolicyOtaTest",
                policy_type="Custom",
                document=current,
            ),
        ),
    )

    report = StudioUpdatePermissionService(
        provider=provider,
        access_key="ak",
        secret_key="sk",
        inspector=_Inspector(principal),
    ).check()

    assert report.ready is False
    assert set(report.missing_actions) == _NEW_SCHEDULER_ACTIONS
    assert report.policy_name == "VeADKFrontendPolicyOtaTest"
    parsed = urlparse(report.authorization_url)
    assert parsed.netloc == expected_host
    query = parse_qs(parsed.query)
    assert query["action"] == ["UpdatePolicy"]
    prefilled = json.loads(query["query"][0])
    assert prefilled["PolicyName"] == "VeADKFrontendPolicyOtaTest"
    merged = json.loads(prefilled["NewPolicyDocument"])
    evaluated = evaluate_actions(_NEW_SCHEDULER_ACTIONS, [merged])
    assert all(evaluated.values())
    assert evaluate_actions(["custom:KeepMe"], [merged])["custom:KeepMe"]


def test_precheck_does_not_offer_link_that_cannot_override_explicit_deny() -> None:
    current = _policy_without_scheduler_actions()
    current["Statement"].append(
        {
            "Effect": "Deny",
            "Action": ["vefaas:CreateTimer"],
            "Resource": ["*"],
        }
    )
    principal = PrincipalPolicySet(
        kind="role",
        name="CustomerRole",
        policies=(
            AttachedPolicyDocument(
                name="CustomerPolicy", policy_type="Custom", document=current
            ),
        ),
    )

    report = StudioUpdatePermissionService(
        provider="volcengine",
        access_key="ak",
        secret_key="sk",
        inspector=_Inspector(principal),
    ).check()

    assert "vefaas:CreateTimer" in report.missing_actions
    assert report.authorization_url == ""


def test_precheck_honors_explicit_deny_from_another_attached_policy() -> None:
    current = _policy_without_scheduler_actions()
    principal = PrincipalPolicySet(
        kind="role",
        name="CustomerRole",
        policies=(
            AttachedPolicyDocument(
                name="CustomerPolicy",
                policy_type="Custom",
                document=current,
            ),
            AttachedPolicyDocument(
                name="GuardrailPolicy",
                policy_type="System",
                document={
                    "Statement": [
                        {
                            "Effect": "Deny",
                            "Action": ["vefaas:CreateTimer"],
                            "Resource": ["*"],
                        }
                    ]
                },
            ),
        ),
    )

    report = StudioUpdatePermissionService(
        provider="byteplus",
        access_key="ak",
        secret_key="sk",
        inspector=_Inspector(principal),
    ).check()

    assert "vefaas:CreateTimer" in report.missing_actions
    assert report.authorization_url == ""


def test_default_frontend_policy_satisfies_every_ota_permission() -> None:
    evaluated = evaluate_actions(
        (spec.action for spec in STUDIO_UPDATE_PERMISSION_SPECS),
        [FRONTEND_DEPLOY_POLICY],
    )

    assert all(evaluated.values())


def test_merge_policy_actions_preserves_unrelated_statements() -> None:
    original = {
        "Statement": [
            {"Effect": "Allow", "Action": "tos:GetObject", "Resource": "*"},
            {"Effect": "Deny", "Action": "iam:DeleteRole", "Resource": "*"},
        ]
    }

    merged = merge_policy_actions(original, ["vefaas:CreateTimer"])

    assert original["Statement"][0]["Action"] == "tos:GetObject"
    assert evaluate_actions(["vefaas:CreateTimer"], [merged])["vefaas:CreateTimer"]
    assert merged["Statement"][1] == original["Statement"][1]


def test_build_update_policy_url_contains_complete_document() -> None:
    document = {"Statement": [{"Effect": "Allow", "Action": ["x:y"]}]}

    url = build_update_policy_url(
        provider="volcengine",
        policy_name="PolicyName",
        policy_document=document,
    )

    query = parse_qs(urlparse(url).query)
    payload = json.loads(query["query"][0])
    assert json.loads(payload["NewPolicyDocument"]) == document
