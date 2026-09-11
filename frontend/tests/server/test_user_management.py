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

"""Identity-backed role changes must preserve authorization boundaries."""

from dataclasses import replace

import pytest

from frontend.server.user_management.directory import IdentityGroup, PoolUser
from frontend.server.user_management.policy import (
    StudioAccessPolicy,
    StudioPrincipal,
    StudioRole,
)
from frontend.server.user_management.service import (
    UserManagementError,
    UserManagementService,
)


class Directory:
    def __init__(self):
        self.records = {
            "owner": PoolUser(
                "owner", "oidc|owner", "owner@example.com", "Owner", "EXTERNAL_PROVIDER"
            ),
            "member": PoolUser(
                "member",
                "oidc|member",
                "member@example.com",
                "Member",
                "EXTERNAL_PROVIDER",
            ),
        }
        self.group_records = {}
        self.fail_remove = False

    def users(self):
        return list(self.records.values())

    def user(self, uid):
        return self.records[uid]

    def groups(self):
        return list(self.group_records.values())

    def create_group(self, name, description):
        group = IdentityGroup(f"g{len(self.group_records)}", name, description)
        self.group_records[group.uid] = group
        return group

    def describe_group(self, uid, description):
        self.group_records[uid] = replace(
            self.group_records[uid], description=description
        )

    def add(self, group_uid, user_uid):
        user = self.records[user_uid]
        self.records[user_uid] = replace(
            user, groups=tuple(set(user.groups) | {group_uid})
        )

    def remove(self, group_uid, user_uid):
        if self.fail_remove:
            raise RuntimeError("Identity unavailable")
        user = self.records[user_uid]
        self.records[user_uid] = replace(
            user, groups=tuple(set(user.groups) - {group_uid})
        )


@pytest.fixture
def setup_service():
    directory = Directory()
    service = UserManagementService(directory, "pool", "client", "volcengine")
    service.initialize("owner@example.com")
    owner = StudioPrincipal.from_claims({"sub": "oidc|owner"})
    member = StudioPrincipal.from_claims({"sub": "oidc|member"})
    return directory, service, owner, member


def test_bootstrap_is_persisted_and_does_not_regrant_on_restart(setup_service):
    directory, service, owner, _ = setup_service
    assert service.principal_for(owner).role == StudioRole.SUPER_ADMIN
    assert service.list_users(owner)["total"] == 2
    restarted = UserManagementService(directory, "pool", "client", "volcengine")
    restarted.initialize("member@example.com")
    assert restarted.protected_user_uid == "owner"
    assert restarted.principal_for(owner).role == StudioRole.SUPER_ADMIN


def test_subject_mapping_and_refresh_read_live_membership(setup_service):
    directory, service, owner, member = setup_service
    assert service.principal_for(member).role == StudioRole.USER
    service.change_role(owner, "member", StudioRole.DEVELOPER, StudioRole.USER)
    assert service.principal_for(member).role == StudioRole.DEVELOPER
    service.change_role(owner, "member", StudioRole.ADMIN, StudioRole.DEVELOPER)
    assert service.principal_for(member).role == StudioRole.ADMIN
    assert directory.records["member"].subject != directory.records["member"].uid


def test_regular_user_cannot_list_or_assign_roles(setup_service):
    _, service, _, member = setup_service
    with pytest.raises(UserManagementError) as error:
        service.list_users(member)
    assert error.value.status == 403
    with pytest.raises(UserManagementError):
        service.change_role(member, "member", StudioRole.SUPER_ADMIN, StudioRole.USER)


def test_protected_administrator_cannot_be_demoted(setup_service):
    _, service, owner, _ = setup_service
    with pytest.raises(UserManagementError) as error:
        service.change_role(owner, "owner", StudioRole.USER, StudioRole.SUPER_ADMIN)
    assert error.value.code == "protected_administrator"


def test_role_change_preserves_unrelated_groups_and_rejects_stale_form(setup_service):
    directory, service, owner, _ = setup_service
    directory.add("unrelated-department", "member")
    service.change_role(owner, "member", StudioRole.ADMIN, StudioRole.USER)
    assert "unrelated-department" in directory.records["member"].groups
    with pytest.raises(UserManagementError) as error:
        service.change_role(owner, "member", StudioRole.DEVELOPER, StudioRole.USER)
    assert error.value.status == 409


def test_partial_membership_change_fails_closed(setup_service):
    directory, service, owner, member = setup_service
    service.change_role(owner, "member", StudioRole.ADMIN, StudioRole.USER)
    directory.fail_remove = True
    with pytest.raises(RuntimeError):
        service.change_role(owner, "member", StudioRole.DEVELOPER, StudioRole.ADMIN)
    assert service.principal_for(member).role == StudioRole.USER


def test_identity_subject_cannot_be_replaced_with_matching_email(setup_service):
    _, service, _, _ = setup_service
    impostor = StudioPrincipal.from_claims(
        {"sub": "other-subject", "email": "owner@example.com"}
    )
    with pytest.raises(UserManagementError):
        service.principal_for(impostor)


def test_super_admin_inherits_existing_admin_capabilities(setup_service):
    _, service, owner, _ = setup_service
    policy = StudioAccessPolicy.from_csv(None, None, identity_roles=True)
    capabilities = policy.access_payload(service.principal_for(owner))["capabilities"]
    assert capabilities["manageUsers"] is True
    assert capabilities["manageAgents"] is True
    assert capabilities["runtimeScope"] == "all"
    assert policy.role_for(None) == StudioRole.USER


@pytest.mark.parametrize("identifier", ["missing@example.com", "duplicate@example.com"])
def test_unmatched_legacy_roles_stop_before_any_identity_writes(identifier):
    directory = Directory()
    for uid, user in directory.records.items():
        directory.records[uid] = replace(user, username="duplicate@example.com")
    service = UserManagementService(directory, "pool", "client", "volcengine")
    with pytest.raises(UserManagementError, match="legacy_role_member_not_unique"):
        service.initialize("owner@example.com", admins=identifier)
    assert directory.group_records == {}
    assert all(not user.groups for user in directory.records.values())


@pytest.mark.parametrize(
    "provider,region",
    [
        ("volcengine", "cn-beijing"),
        ("volcengine", "cn-shanghai"),
        ("byteplus", "ap-southeast-1"),
    ],
)
def test_deployment_migrates_legacy_roles_once_then_clears_static_lists(
    monkeypatch, provider, region
):
    from frontend.server.user_management import deployment

    directory = Directory()
    calls = []

    def make_directory(pool, selected_provider, selected_region, credentials):
        calls.append((pool, selected_provider, selected_region, credentials()))
        return directory

    monkeypatch.setattr(deployment, "IdentityDirectory", make_directory)
    options = dict(
        pool_uid="pool",
        client_uid="client",
        provider=provider,
        region=region,
        access_key="ak",
        secret_key="sk",
        session_token="token",
    )
    environment = deployment.prepare_identity_roles(
        **options,
        super_admin="owner@example.com",
        legacy_environment={"VEADK_STUDIO_ADMINS": "member@example.com"},
    )
    assert environment == {
        "VEADK_STUDIO_IDENTITY_ROLES": "1",
        "VEADK_STUDIO_SUPER_ADMIN": "",
        "VEADK_STUDIO_ADMINS": "",
        "VEADK_STUDIO_DEVELOPERS": "",
    }
    assert calls == [("pool", provider, region, ("ak", "sk", "token"))]
    service = UserManagementService(directory, "pool", "client", provider)
    service.initialize()
    owner = StudioPrincipal.from_claims({"sub": "oidc|owner"})
    member = StudioPrincipal.from_claims({"sub": "oidc|member"})
    assert service.principal_for(member).role == StudioRole.ADMIN
    service.change_role(owner, "member", StudioRole.DEVELOPER, StudioRole.ADMIN)
    deployment.prepare_identity_roles(
        **options, legacy_environment={"VEADK_STUDIO_ADMINS": "member@example.com"}
    )
    assert service.principal_for(member).role == StudioRole.DEVELOPER


def test_first_deployment_defaults_to_admin_and_requires_valid_explicit_owner(
    monkeypatch,
):
    import click
    from frontend.server.user_management import deployment

    directory = Directory()
    monkeypatch.setattr(deployment, "IdentityDirectory", lambda *args: directory)
    options = dict(
        pool_uid="pool",
        client_uid="client",
        provider="volcengine",
        region="cn-beijing",
        access_key="ak",
        secret_key="sk",
    )
    with pytest.raises(click.ClickException, match="exactly one existing"):
        deployment.prepare_identity_roles(**options, super_admin="missing@example.com")
    assert directory.group_records == {}
    deployment.prepare_identity_roles(**options)
    service = UserManagementService(directory, "pool", "client", "volcengine")
    service.initialize()
    policy = StudioAccessPolicy.from_csv(None, None, identity_roles=True)
    for uid in directory.records:
        principal = StudioPrincipal.from_claims({"sub": f"oidc|{uid}"})
        access = policy.access_payload(service.principal_for(principal))
        assert access["role"] == "admin"
        assert access["capabilities"]["manageUsers"] is False
        with pytest.raises(UserManagementError, match="super_administrator_required"):
            service.list_users(principal)
    directory.records["new"] = PoolUser(
        "new", "oidc|new", "new@example.com", "New", "ENABLED"
    )
    assert (
        service.principal_for(StudioPrincipal.from_claims({"sub": "oidc|new"})).role
        == StudioRole.ADMIN
    )


def test_existing_role_lists_migrate_without_promoting_anyone_to_super_admin():
    directory = Directory()
    service = UserManagementService(directory, "pool", "client", "volcengine")
    service.initialize(
        admins="owner@example.com",
        developers="member@example.com",
        allow_initialize=True,
    )
    assert service.default_role == StudioRole.USER
    assert service.protected_user_uid == ""
    assert (
        service.principal_for(StudioPrincipal.from_claims({"sub": "oidc|owner"})).role
        == StudioRole.ADMIN
    )
    assert (
        service.principal_for(StudioPrincipal.from_claims({"sub": "oidc|member"})).role
        == StudioRole.DEVELOPER
    )
    restarted = UserManagementService(directory, "pool", "client", "volcengine")
    restarted.initialize(admins="member@example.com", allow_initialize=True)
    assert (
        restarted.principal_for(
            StudioPrincipal.from_claims({"sub": "oidc|member"})
        ).role
        == StudioRole.DEVELOPER
    )


def test_dynamic_runtime_does_not_reinitialize_missing_metadata_as_all_admin():
    directory = Directory()
    service = UserManagementService(directory, "pool", "client", "volcengine")
    with pytest.raises(UserManagementError, match="roles_not_initialized"):
        service.initialize()
    assert not directory.group_records


def test_first_super_admin_can_be_added_later_without_resetting_member_roles():
    directory = Directory()
    service = UserManagementService(directory, "pool", "client", "volcengine")
    service.initialize(allow_initialize=True)
    service.initialize("owner@example.com")
    assert service.protected_user_uid == "owner"
    assert (
        service.principal_for(StudioPrincipal.from_claims({"sub": "oidc|owner"})).role
        == StudioRole.SUPER_ADMIN
    )
    assert (
        service.principal_for(StudioPrincipal.from_claims({"sub": "oidc|member"})).role
        == StudioRole.ADMIN
    )


def test_conflicting_memberships_fail_closed_with_default_admin():
    directory = Directory()
    service = UserManagementService(directory, "pool", "client", "volcengine")
    service.initialize(allow_initialize=True)
    directory.add(service.role_groups[StudioRole.ADMIN].uid, "member")
    directory.add(service.role_groups[StudioRole.DEVELOPER].uid, "member")
    assert (
        service.principal_for(StudioPrincipal.from_claims({"sub": "oidc|member"})).role
        == StudioRole.USER
    )


def test_update_bundle_must_contain_role_management_code(tmp_path):
    from zipfile import ZipFile
    from frontend.server.user_management.deployment import (
        package_supports_identity_roles,
    )

    assert not package_supports_identity_roles(tmp_path)
    with ZipFile(tmp_path / "veadk_old.whl", "w") as wheel:
        wheel.writestr("veadk/cli/cli.py", "")
    assert not package_supports_identity_roles(tmp_path)
    with ZipFile(tmp_path / "veadk_new.whl", "w") as wheel:
        wheel.writestr("frontend/server/user_management/service.py", "")
    assert package_supports_identity_roles(tmp_path)


def test_http_permissions_refresh_and_cross_origin_mutations_are_blocked(setup_service):
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from frontend.server.user_management.routes import mount_user_management

    _, service, owner, member = setup_service
    app = FastAPI()

    def principal(request):
        return getattr(request.state, "studio_identity_principal", None) or getattr(
            request.state, "authenticated_principal", None
        )

    mount_user_management(app, service, principal)

    @app.middleware("http")
    async def trusted_auth(request, call_next):
        # Simulate identities that have already passed the outer OAuth middleware
        request.state.authenticated_principal = (
            owner if request.cookies.get("session") == "owner" else member
        )
        return await call_next(request)

    @app.get("/web/access")
    def access(request: Request):
        return StudioAccessPolicy.from_csv(
            None, None, identity_roles=True
        ).access_payload(principal(request))

    with TestClient(app) as client:
        client.cookies.set("session", "owner")
        assert client.get("/web/users").status_code == 200
        denied = client.patch(
            "/web/users/member/role",
            json={"role": "admin", "expectedRole": "user"},
            headers={"Origin": "https://other.example"},
        )
        assert denied.status_code == 403
        assert (
            client.patch(
                "/web/users/member/role",
                json={"role": "developer", "expectedRole": "user"},
                headers={"Origin": "http://testserver"},
            ).status_code
            == 200
        )
        assert (
            client.patch(
                "/web/users/member/role",
                json={"role": "owner", "expectedRole": "developer"},
            ).status_code
            == 422
        )
        client.cookies.set("session", "member")
        first = client.get("/web/access")
        assert first.json()["role"] == "developer"
        assert first.headers["cache-control"] == "no-store"
        assert client.get("/web/users").status_code == 403
        service.change_role(owner, "member", StudioRole.USER, StudioRole.DEVELOPER)
        assert client.get("/web/access").json()["role"] == "user"


@pytest.mark.parametrize(
    "provider,region,host",
    [
        ("volcengine", "cn-beijing", "https://open.volcengineapi.com"),
        ("volcengine", "cn-shanghai", "https://open.volcengineapi.com"),
        ("byteplus", "ap-southeast-1", "https://id.ap-southeast-1.byteplusapi.com"),
    ],
)
def test_directory_uses_provider_host_and_fetches_all_pages(
    monkeypatch, provider, region, host
):
    from types import SimpleNamespace
    from frontend.server.user_management import directory as module

    configurations = []
    requests = []

    def api_client(config):
        configurations.append(config)
        return config

    class Api:
        def __init__(self, config):
            pass

        def list_users(self, body, **kwargs):
            requests.append(body)
            value = SimpleNamespace(
                uid=f"u{body.page_number}",
                sub=f"s{body.page_number}",
                preferred_username="",
                email="",
                name="Member",
                user_state="CONFIRMED",
                group_uids=[],
                latest_login="",
            )
            return SimpleNamespace(data=[value], total_count=2)

    monkeypatch.setattr(module.volcenginesdkcore, "ApiClient", api_client)
    monkeypatch.setattr(module.sdk, "IDApi", Api)
    monkeypatch.delenv("IDENTITY_OPENAPI_HOST", raising=False)
    directory = module.IdentityDirectory(
        "pool", provider, region, lambda: ("test-ak", "test-sk", None)
    )
    assert len(directory.users()) == 2
    assert [request.page_number for request in requests] == [1, 2]
    assert all(
        config.host == host and config.region == region for config in configurations
    )


@pytest.mark.parametrize(
    "provider,region",
    [
        ("volcengine", "cn-beijing"),
        ("volcengine", "cn-shanghai"),
        ("byteplus", "ap-southeast-1"),
    ],
)
@pytest.mark.parametrize(
    "admins,developers,expected",
    [
        ("", "", (StudioRole.ADMIN, StudioRole.ADMIN)),
        (
            "owner@example.com",
            "member@example.com",
            (StudioRole.ADMIN, StudioRole.DEVELOPER),
        ),
    ],
)
def test_old_updater_runtime_migrates_then_cleans_cloud_environment(
    monkeypatch, provider, region, admins, developers, expected
):
    from types import SimpleNamespace
    from frontend.server.user_management import deployment

    directory = Directory()
    monkeypatch.setattr(deployment, "IdentityDirectory", lambda *args: directory)
    environment = {
        "OAUTH2_USER_POOL_ID": "pool",
        "OAUTH2_USER_POOL_CLIENT_ID": "client",
        "VEADK_STUDIO_FUNCTION_ID": "function",
        "VEADK_STUDIO_DEPLOY_REGION": region,
        "VEADK_STUDIO_ADMINS": admins,
        "VEADK_STUDIO_DEVELOPERS": developers,
        "UNRELATED": "preserve",
    }
    updates = []
    connections = []

    def update(request):
        assert any(
            '"initialized": true' in group.description for group in directory.groups()
        )
        updates.append(request)
        environment.update({item.key: item.value for item in request.envs})

    client = SimpleNamespace(
        get_function=lambda request: SimpleNamespace(
            envs=[SimpleNamespace(key=k, value=v) for k, v in environment.items()]
        ),
        update_function=update,
    )
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.ve_faas.VeFaaS",
        lambda **kwargs: connections.append(kwargs) or SimpleNamespace(client=client),
    )
    options = dict(
        pool_uid="pool",
        client_uid="client",
        provider=provider,
        identity_region=region,
        credentials=lambda: ("ak", "sk", "token"),
        admins=admins,
        developers=developers,
    )
    stale_instance_environment = dict(environment)
    service = deployment.initialize_runtime_roles(
        **options, environment=stale_instance_environment
    )
    assert len(updates) == 1
    assert (
        environment["VEADK_STUDIO_ADMINS"]
        == environment["VEADK_STUDIO_DEVELOPERS"]
        == ""
    )
    assert environment["VEADK_STUDIO_IDENTITY_ROLES"] == "1"
    assert environment["UNRELATED"] == "preserve"
    assert connections[0]["provider"] == provider
    assert connections[0]["region"] == region
    for uid, role in zip(("owner", "member"), expected):
        assert (
            service.principal_for(
                StudioPrincipal.from_claims({"sub": f"oidc|{uid}"})
            ).role
            == role
        )
    # Another instance of the same immutable revision still has old env values
    service._set_role(directory.user("member"), StudioRole.USER)
    restarted = deployment.initialize_runtime_roles(
        **options, environment=stale_instance_environment
    )
    assert len(updates) == 1
    assert (
        restarted.principal_for(
            StudioPrincipal.from_claims({"sub": "oidc|member"})
        ).role
        == StudioRole.USER
    )


def test_failed_runtime_migration_never_clears_old_environment(monkeypatch):
    import click
    from frontend.server.user_management import deployment

    directory = Directory()
    monkeypatch.setattr(deployment, "IdentityDirectory", lambda *args: directory)
    monkeypatch.setattr(
        deployment,
        "clear_legacy_role_environment",
        lambda **kwargs: pytest.fail("must not clear before successful migration"),
    )
    with pytest.raises(click.ClickException, match="legacy_role_member_not_unique"):
        deployment.initialize_runtime_roles(
            pool_uid="pool",
            client_uid="client",
            provider="volcengine",
            identity_region="cn-beijing",
            credentials=lambda: ("ak", "sk", ""),
            environment={"VEADK_STUDIO_FUNCTION_ID": "function"},
            admins="missing@example.com",
        )
    assert not directory.group_records
