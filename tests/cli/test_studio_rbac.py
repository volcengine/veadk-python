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

"""Tests for Studio role and Runtime ownership policy."""

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veadk.cli.cli_frontend import _run_frontend_server, studio
from veadk.cli.studio_rbac import (
    StudioAccessPolicy,
    StudioPrincipal,
    StudioRole,
    parse_role_members,
    runtime_belongs_to,
)


def _create_studio_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    auth_mode: str = "frontend",
    admins: str | None = None,
    developers: str | None = None,
) -> FastAPI:
    captured: dict[str, Any] = {}
    monkeypatch.setattr("dotenv.find_dotenv", lambda: "")
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "test-sk")
    monkeypatch.setattr(
        "uvicorn.run",
        lambda app, **kwargs: captured.setdefault("app", app),
    )
    _run_frontend_server(
        agents_dir=str(tmp_path),
        frontend_dir=None,
        site_logo=None,
        site_title=None,
        host="127.0.0.1",
        port=8765,
        dev=True,
        vite=True,
        oauth2_user_pool=None,
        oauth2_user_pool_client=None,
        oauth2_user_pool_uid=None,
        oauth2_user_pool_client_uid=None,
        oauth2_redirect_uri=None,
        oauth2_provider=None,
        oauth2_provider_label=None,
        auth_mode=auth_mode,
        generated_agent_test_run_ttl=60,
        studio_admins=admins,
        studio_developers=developers,
        open_browser=False,
        studio=True,
    )
    return captured["app"]


def _unsigned_jwt(claims: dict[str, str]) -> str:
    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    return f"{encode(b'{}')}.{encode(json.dumps(claims).encode())}.signature"


def _runtime(
    runtime_id: str,
    owner: str,
    *,
    managed: bool = True,
) -> SimpleNamespace:
    tags = [SimpleNamespace(key="veadk:owner", value=owner)]
    if managed:
        tags.append(SimpleNamespace(key="veadk:managed", value="true"))
    return SimpleNamespace(
        runtime_id=runtime_id,
        name=runtime_id,
        status="Running",
        created_at="2026-07-21T00:00:00Z",
        tags=tags,
        network_configurations=[],
        authorizer_configuration=None,
    )


def test_parse_role_members_normalizes_csv() -> None:
    assert parse_role_members(" Admin@Example.com, alice, ALICE, ") == {
        "admin@example.com",
        "alice",
    }


def test_studio_role_behaves_as_a_python_310_string_enum() -> None:
    assert isinstance(StudioRole.ADMIN, str)
    assert str(StudioRole.ADMIN) == "admin"
    assert json.dumps({"role": StudioRole.ADMIN}) == '{"role": "admin"}'


def test_role_matching_uses_all_trusted_identifiers_and_admin_wins() -> None:
    principal = StudioPrincipal.from_claims(
        {
            "sub": "stable-user-id",
            "email": "Owner@Example.com",
            "preferred_username": "owner",
        }
    )
    assert principal is not None
    policy = StudioAccessPolicy.from_csv(
        "owner@example.com",
        "stable-user-id,owner",
    )

    assert policy.role_for(principal) == StudioRole.ADMIN
    assert policy.access_payload(principal)["capabilities"] == {
        "createAgents": True,
        "manageAgents": True,
        "runtimeScope": "all",
    }


def test_unconfigured_policy_preserves_legacy_full_access() -> None:
    policy = StudioAccessPolicy.from_csv(None, "")
    principal = StudioPrincipal.local("any-user")

    assert not policy.enabled
    assert policy.role_for(principal) == StudioRole.ADMIN
    assert policy.access_payload(principal) == {
        "role": "admin",
        "username": "any-user",
        "rbacEnabled": False,
        "capabilities": {
            "createAgents": True,
            "manageAgents": True,
            "runtimeScope": "all",
        },
    }


@pytest.mark.parametrize(
    ("admins", "developers", "listed_user", "listed_role"),
    [
        ("admin", None, "admin", StudioRole.ADMIN),
        (None, "developer", "developer", StudioRole.DEVELOPER),
    ],
)
def test_either_role_list_enables_rbac(
    admins: str | None,
    developers: str | None,
    listed_user: str,
    listed_role: StudioRole,
) -> None:
    policy = StudioAccessPolicy.from_csv(admins, developers)

    assert policy.enabled
    assert policy.role_for(StudioPrincipal.local(listed_user)) == listed_role
    assert policy.role_for(StudioPrincipal.local("unlisted")) == StudioRole.USER


def test_unlisted_identity_is_a_regular_user() -> None:
    policy = StudioAccessPolicy.from_csv("admin", "developer")
    principal = StudioPrincipal.local("reader")

    assert policy.role_for(principal) == StudioRole.USER
    assert policy.access_payload(principal)["capabilities"] == {
        "createAgents": False,
        "manageAgents": False,
        "runtimeScope": "mine",
    }


def test_display_name_cannot_grant_a_role() -> None:
    policy = StudioAccessPolicy.from_csv("Shared Display Name", None)
    principal = StudioPrincipal.from_claims(
        {"sub": "stable-id", "name": "Shared Display Name"}
    )

    assert principal is not None
    assert principal.display_name == "Shared Display Name"
    assert policy.role_for(principal) == StudioRole.USER


def test_runtime_owner_tag_takes_precedence_with_author_fallback() -> None:
    principal = StudioPrincipal.from_claims(
        {"sub": "stable-id", "email": "owner@example.com"}
    )
    assert principal is not None

    assert runtime_belongs_to(
        {"veadk:owner": "stable-id", "veadk:author": "other@example.com"},
        principal,
    )
    assert not runtime_belongs_to(
        {"veadk:owner": "other", "veadk:author": "owner@example.com"},
        principal,
    )
    assert runtime_belongs_to(
        {"veadk:author": "OWNER@EXAMPLE.COM"},
        principal,
    )


def test_studio_deploy_exposes_role_options() -> None:
    result = CliRunner().invoke(studio, ["deploy", "--help"])

    assert result.exit_code == 0
    assert "--admin" in result.output
    assert "--developer" in result.output
    assert "Omit both role options to grant every user admin access" in " ".join(
        result.output.split()
    )
    assert "--skill-creator-tool-id" in result.output


def test_access_endpoint_resolves_local_roles_and_blocks_user_management(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        admins="admin",
        developers="developer",
    )

    with TestClient(app) as client:
        admin = client.get("/web/access", headers={"X-VeADK-Local-User": "ADMIN"})
        developer = client.get(
            "/web/access", headers={"X-VeADK-Local-User": "developer"}
        )
        user = client.get("/web/access", headers={"X-VeADK-Local-User": "reader"})
        forbidden = client.post(
            "/web/generated-agent-projects",
            headers={"X-VeADK-Local-User": "reader"},
            json={},
        )
        skill_creator_forbidden = client.post(
            "/web/skill-creator/jobs",
            headers={"X-VeADK-Local-User": "reader"},
            json={"prompt": "Create a release notes Skill"},
        )

    assert admin.json()["role"] == "admin"
    assert developer.json()["role"] == "developer"
    assert user.json()["role"] == "user"
    assert forbidden.status_code == 403
    assert skill_creator_forbidden.status_code == 403


def test_gateway_role_uses_jwt_and_ignores_local_identity_header(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        auth_mode="gateway",
        admins="admin@example.com",
        developers="local-developer",
    )
    token = _unsigned_jwt({"sub": "user-1", "email": "admin@example.com"})

    with TestClient(app) as client:
        response = client.get(
            "/web/access",
            headers={
                "Authorization": f"Bearer {token}",
                "X-VeADK-Local-User": "local-developer",
            },
        )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_non_admin_runtime_list_scans_pages_and_ignores_all_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    other = _runtime("runtime-other", "someone-else")
    own = _runtime("runtime-own", "developer")

    def list_runtimes(_self: Any, request: Any) -> SimpleNamespace:
        if getattr(request, "next_token", None) == "page-2":
            return SimpleNamespace(agent_kit_runtimes=[own], next_token="")
        return SimpleNamespace(agent_kit_runtimes=[other], next_token="page-2")

    monkeypatch.setattr(AgentkitRuntimeClient, "list_runtimes", list_runtimes)
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        admins="admin",
        developers="developer",
    )

    with TestClient(app) as client:
        developer = client.get(
            "/web/runtimes?scope=all&page_size=1&region=cn-beijing",
            headers={"X-VeADK-Local-User": "developer"},
        )
        admin = client.get(
            "/web/runtimes?scope=all&page_size=10&region=cn-beijing",
            headers={"X-VeADK-Local-User": "admin"},
        )

    assert developer.status_code == 200
    assert [item["runtimeId"] for item in developer.json()["runtimes"]] == [
        "runtime-own"
    ]
    assert admin.status_code == 200
    assert [item["runtimeId"] for item in admin.json()["runtimes"]] == [
        "runtime-other",
        "runtime-own",
    ]


def test_runtime_detail_proxy_and_delete_enforce_role_and_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    runtimes = {
        "runtime-developer": _runtime("runtime-developer", "developer"),
        "runtime-viewer": _runtime("runtime-viewer", "viewer"),
        "runtime-other": _runtime("runtime-other", "someone-else"),
        "runtime-unmanaged": _runtime(
            "runtime-unmanaged",
            "admin",
            managed=False,
        ),
    }
    deleted: list[str] = []

    def get_runtime(_self: Any, request: Any) -> SimpleNamespace:
        return runtimes[request.runtime_id]

    def delete_runtime(_self: Any, request: Any) -> None:
        deleted.append(request.runtime_id)

    monkeypatch.setattr(AgentkitRuntimeClient, "get_runtime", get_runtime)
    monkeypatch.setattr(AgentkitRuntimeClient, "delete_runtime", delete_runtime)
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        admins="admin",
        developers="developer",
    )

    with TestClient(app) as client:
        developer_headers = {"X-VeADK-Local-User": "developer"}
        viewer_headers = {"X-VeADK-Local-User": "viewer"}
        admin_headers = {"X-VeADK-Local-User": "admin"}

        assert (
            client.get(
                "/web/runtime-detail?runtimeId=runtime-developer&region=cn-beijing",
                headers=developer_headers,
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/web/runtime-detail?runtimeId=runtime-other&region=cn-beijing",
                headers=developer_headers,
            ).status_code
            == 404
        )
        proxy_forbidden = client.get(
            "/web/runtime-proxy/runtime-other/list-apps?region=cn-beijing",
            headers=developer_headers,
        )
        assert proxy_forbidden.status_code == 404
        assert proxy_forbidden.json()["detail"] == "runtime_access_denied"
        assert (
            client.post(
                "/web/delete-runtime",
                headers=viewer_headers,
                json={"runtimeId": "runtime-viewer", "region": "cn-beijing"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/web/delete-runtime",
                headers=developer_headers,
                json={"runtimeId": "runtime-developer", "region": "cn-beijing"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/web/delete-runtime",
                headers=admin_headers,
                json={"runtimeId": "runtime-other", "region": "cn-beijing"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/web/delete-runtime",
                headers=admin_headers,
                json={"runtimeId": "runtime-unmanaged", "region": "cn-beijing"},
            ).status_code
            == 404
        )
        assert (
            client.get(
                "/agentkit-proxy/list-apps",
                headers=viewer_headers,
            ).status_code
            == 403
        )

    assert deleted == ["runtime-developer", "runtime-other"]
