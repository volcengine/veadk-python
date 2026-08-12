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
