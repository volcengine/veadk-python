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
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture(autouse=True)
def _stub_studio_local_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI tests independent of live Cronjob and TOS polling."""

    async def _offline_local_scheduler(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "frontend.service.studio_scheduler.run_local_scheduler",
        _offline_local_scheduler,
    )


@pytest.fixture(autouse=True)
def _stub_skill_score_background_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI route tests independent of live Skill recovery scans"""
    monkeypatch.setattr(
        "frontend.server.skills.auto_scoring.SkillAutoScoring.start", AsyncMock()
    )


@pytest.fixture(autouse=True)
def _stub_studio_deploy_role_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """Provisioning tests continue past the separately tested interactive warning"""
    if request.path.name == "test_studio_deploy_role_confirmation.py":
        return
    monkeypatch.setattr(
        "frontend.server.user_management.deployment.confirm_super_admin_for_deploy",
        lambda super_admin: None,
    )


@pytest.fixture(autouse=True)
def _stub_studio_runtime_role(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Keep deployment tests isolated from live Runtime IAM operations"""
    resolver = MagicMock(return_value="shared-runtime-role")
    monkeypatch.setattr("frontend.server.runtime_iam.ensure_runtime_role", resolver)
    return resolver


@pytest.fixture(autouse=True)
def _stub_studio_deploy_permission_precheck(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """Keep existing Studio deploy tests isolated from live IAM reads."""
    if request.path.name == "test_studio_deploy_permissions.py":
        return

    from veadk.cli import studio_deploy_permissions

    def _allow_all(*, specs, **_kwargs):
        return [
            studio_deploy_permissions.PermissionResult(spec=spec, satisfied=True)
            for spec in specs
        ]

    monkeypatch.setattr(
        studio_deploy_permissions,
        "run_studio_deploy_permission_precheck",
        _allow_all,
    )
