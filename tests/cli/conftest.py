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
