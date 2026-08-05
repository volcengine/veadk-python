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

import httpx
import pytest
import yaml
from click.testing import CliRunner
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from veadk.cli.cli_frontend import (
    _create_runtime_with_description_fallback,
    _is_malformed_runtime_description_error,
    _normalize_runtime_description,
    _run_frontend_server,
    studio,
)
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
    oauth2_user_pool_uid: str | None = None,
    oauth2_user_pool_client_uid: str | None = None,
) -> FastAPI:
    captured: dict[str, Any] = {}
    monkeypatch.setattr("dotenv.find_dotenv", lambda *args, **kwargs: "")
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
        oauth2_user_pool_uid=oauth2_user_pool_uid,
        oauth2_user_pool_client_uid=oauth2_user_pool_client_uid,
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


def test_identity_user_pools_marks_the_current_studio_pool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    regions: list[str] = []

    class _FakeIdentityClient:
        def __init__(self, **kwargs: Any) -> None:
            regions.append(kwargs["region"])

        def list_user_pools(self) -> list[dict[str, str]]:
            return [
                {
                    "uid": "pool-current",
                    "name": "Studio",
                    "domain": "studio.example.com",
                },
                {
                    "uid": "pool-other",
                    "name": "Customers",
                    "domain": "users.example.com",
                },
            ]

    monkeypatch.setenv("VEIDENTITY_REGION", "cn-shanghai")
    monkeypatch.setattr(
        "veadk.integrations.ve_identity.identity_client.IdentityClient",
        _FakeIdentityClient,
    )
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        auth_mode="gateway",
        developers="developer",
        oauth2_user_pool_uid="pool-current",
        oauth2_user_pool_client_uid="studio-client",
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/identity/user-pools",
            headers={"Authorization": f"Bearer {_unsigned_jwt({'sub': 'developer'})}"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "uid": "pool-current",
                "name": "Studio",
                "domain": "studio.example.com",
                "region": "cn-shanghai",
                "isCurrent": True,
            },
            {
                "uid": "pool-other",
                "name": "Customers",
                "domain": "users.example.com",
                "region": "cn-shanghai",
                "isCurrent": False,
            },
        ]
    }
    assert regions == ["cn-shanghai"]


def test_current_user_pool_deployment_forwards_studio_jwt_to_run_sse(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    captured_config: dict[str, Any] = {}
    runtime_id = "runtime-custom-jwt"
    runtime = _runtime_with_public_endpoint(_runtime(runtime_id, "developer"))
    runtime.current_version_number = 1
    runtime.authorizer_configuration = SimpleNamespace(
        key_auth=None,
        custom_jwt_authorizer=SimpleNamespace(
            discovery_url=(
                "https://studio.example.com/.well-known/openid-configuration"
            ),
            allowed_clients=["studio-client"],
        ),
    )

    class _FakeIdentityClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def get_user_pool(
            self,
            *,
            uid: str,
            name: str | None = None,
        ) -> tuple[str, str] | None:
            assert uid == "pool-current"
            assert name is None
            return uid, "studio.example.com"

    def launch(*, config_file: str, **_kwargs: Any) -> SimpleNamespace:
        captured_config.update(yaml.safe_load(Path(config_file).read_text()))
        return SimpleNamespace(
            success=True,
            error=None,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.com",
                metadata={
                    "runtime_id": runtime_id,
                    "runtime_name": "demo-agent",
                    "runtime_endpoint": "https://runtime.example.com",
                    "runtime_apikey": "",
                },
            ),
        )

    monkeypatch.setattr(
        "veadk.integrations.ve_identity.identity_client.IdentityClient",
        _FakeIdentityClient,
    )
    monkeypatch.setattr(
        AgentkitRuntimeClient,
        "get_runtime",
        lambda _self, _request: runtime,
    )
    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        auth_mode="gateway",
        developers="developer",
        oauth2_user_pool_uid="pool-current",
        oauth2_user_pool_client_uid="studio-client",
    )

    upstream_headers: dict[str, str] = {}

    class _FakeUpstreamResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        async def aiter_raw(self):
            yield b'data: {"author":"runtime"}\n\n'

        async def aclose(self) -> None:
            pass

    class _FakeAsyncClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def build_request(
            self,
            _method: str,
            _url: str,
            *,
            params: dict[str, str],
            headers: dict[str, str],
            content: bytes,
        ) -> object:
            assert params == {}
            assert json.loads(content) == {
                "app_name": "demo-agent",
                "user_id": "developer",
                "session_id": "session-1",
                "new_message": {"role": "user", "parts": [{"text": "hello"}]},
                "streaming": True,
            }
            upstream_headers.update(headers)
            return object()

        async def send(
            self,
            _request: object,
            *,
            stream: bool,
        ) -> _FakeUpstreamResponse:
            assert stream is True
            return _FakeUpstreamResponse()

        async def aclose(self) -> None:
            pass

    token = _unsigned_jwt({"sub": "developer"})
    authorization = f"Bearer {token}"
    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/web/deploy-agentkit",
            headers={"Authorization": authorization},
            json={
                "name": "demo-agent",
                "files": [{"path": "app.py", "content": "app = object()\n"}],
                "config": {"region": "cn-beijing", "projectName": "default"},
                "authentication": {
                    "type": "user_pool",
                    "userPoolUid": "pool-current",
                    "discoveryUrl": "https://untrusted.example.com/openid",
                },
            },
        ) as response:
            frames = [
                json.loads(line.removeprefix("data: "))
                for line in response.iter_lines()
                if line.startswith("data: ")
            ]

        monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
        run_response = client.post(
            f"/web/runtime-proxy/{runtime_id}/run_sse?region=cn-beijing",
            headers={"Authorization": authorization},
            json={
                "app_name": "demo-agent",
                "user_id": "developer",
                "session_id": "session-1",
                "new_message": {"role": "user", "parts": [{"text": "hello"}]},
                "streaming": True,
            },
        )
        unauthenticated_response = client.post(
            f"/web/runtime-proxy/{runtime_id}/run_sse?region=cn-beijing",
            json={},
        )

    assert response.status_code == 200
    assert frames[-1]["success"] is True
    cloud = captured_config["launch_types"]["cloud"]
    assert cloud["runtime_auth_type"] == "custom_jwt"
    assert cloud["runtime_jwt_discovery_url"] == (
        "https://studio.example.com/.well-known/openid-configuration"
    )
    assert cloud["runtime_jwt_allowed_clients"] == ["studio-client"]
    assert run_response.status_code == 200
    assert run_response.text == 'data: {"author":"runtime"}\n\n'
    assert upstream_headers["Authorization"] == authorization
    assert unauthenticated_response.status_code == 401


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


class _RuntimeJsonResponse:
    def __init__(
        self,
        data: Any,
        *,
        status_code: int = 200,
        text: str = "",
    ) -> None:
        self._data = data
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": "application/json"}

    def json(self) -> Any:
        return self._data


def _runtime_with_public_endpoint(runtime: SimpleNamespace) -> SimpleNamespace:
    runtime.network_configurations = [
        SimpleNamespace(
            endpoint="https://runtime.example.com",
            network_type="public",
        )
    ]
    runtime.authorizer_configuration = SimpleNamespace(
        key_auth=SimpleNamespace(api_key="runtime-key"),
        custom_jwt_authorizer=None,
    )
    return runtime


def test_runtime_description_is_safe_and_bounded() -> None:
    normalized = _normalize_runtime_description(
        "  数据\n分析\u0000 Agent 🤖 " + "数" * 100
    )

    assert normalized.startswith("数据 分析 Agent 数")
    assert "\n" not in normalized
    assert "\u0000" not in normalized
    assert "🤖" not in normalized
    assert len(normalized.encode("utf-8")) <= 255


def test_runtime_description_error_detection_is_specific() -> None:
    assert _is_malformed_runtime_description_error(
        "CreateRuntime failed: InvalidDescription.Malformed"
    )
    assert not _is_malformed_runtime_description_error(
        "CreateRuntime failed: AccessDenied"
    )


def test_runtime_creation_retries_without_a_rejected_description() -> None:
    attempts: list[str | None] = []
    request = SimpleNamespace(description="bad description")

    def create_runtime(_client: object, current_request: SimpleNamespace):
        attempts.append(current_request.description)
        if len(attempts) == 1:
            raise RuntimeError("InvalidDescription.Malformed")
        return SimpleNamespace(runtime_id="runtime-1")

    result = _create_runtime_with_description_fallback(
        create_runtime, object(), request
    )

    assert result.runtime_id == "runtime-1"
    assert attempts == ["bad description", None]


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


def test_runtime_ownership_requires_current_owner_tag() -> None:
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
    assert not runtime_belongs_to({"veadk:author": "OWNER@EXAMPLE.COM"}, principal)


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
    assert developer.json()["telemetry"] == {"userId": "developer"}
    assert user.json()["role"] == "user"
    assert user.json()["telemetry"]["userId"] == "reader"
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


def test_non_admin_runtime_list_uses_one_owner_filtered_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    other = _runtime("runtime-other", "someone-else")
    own = _runtime("runtime-own", "developer")
    reader_own = _runtime("runtime-reader", "reader")
    developer_tag_filters: list[tuple[str, list[str]]] = []

    runtime_calls = 0

    def list_runtimes(_self: Any, request: Any) -> SimpleNamespace:
        nonlocal runtime_calls
        runtime_calls += 1
        tag_filters = getattr(request, "tag_filters", None) or []
        for item in tag_filters:
            developer_tag_filters.append((item.key, item.values))
        if tag_filters:
            owner = tag_filters[0].values[0]
            owned = reader_own if owner == "reader" else own
            return SimpleNamespace(agent_kit_runtimes=[owned], next_token="")
        return SimpleNamespace(agent_kit_runtimes=[other, own], next_token="")

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
        developer_call_count = runtime_calls
        reader = client.get(
            "/web/runtimes?scope=all&page_size=10&region=cn-beijing",
            headers={"X-VeADK-Local-User": "reader"},
        )
        admin = client.get(
            "/web/runtimes?scope=all&page_size=10&region=cn-beijing",
            headers={"X-VeADK-Local-User": "admin"},
        )

    assert developer.status_code == 200
    assert [item["runtimeId"] for item in developer.json()["runtimes"]] == [
        "runtime-own"
    ]
    assert developer.json()["runtimes"][0]["canDelete"] is True
    assert ("veadk:owner", ["developer"]) in developer_tag_filters
    assert developer_call_count == 1
    assert reader.status_code == 200
    assert [item["runtimeId"] for item in reader.json()["runtimes"]] == [
        "runtime-reader"
    ]
    assert runtime_calls == 3
    assert admin.status_code == 200
    assert [item["runtimeId"] for item in admin.json()["runtimes"]] == [
        "runtime-other",
        "runtime-own",
    ]
    assert all(item["canDelete"] is True for item in admin.json()["runtimes"])


def test_runtime_detail_proxy_and_delete_enforce_role_and_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    runtimes = {
        "runtime-developer": _runtime_with_public_endpoint(
            _runtime("runtime-developer", "developer")
        ),
        "runtime-viewer": _runtime("runtime-viewer", "viewer"),
        "runtime-other": _runtime("runtime-other", "someone-else"),
        "runtime-unmanaged": _runtime(
            "runtime-unmanaged",
            "admin",
            managed=False,
        ),
    }
    runtimes["runtime-developer"].envs = [
        SimpleNamespace(key="MCP_VISIBLE_AUTH_TOKEN", value="visible-secret")
    ]
    runtimes["runtime-viewer"].envs = [
        SimpleNamespace(key="VIEWER_VISIBLE_TOKEN", value="viewer-secret")
    ]
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

        runtime_detail = client.get(
            "/web/runtime-detail?runtimeId=runtime-developer&region=cn-beijing",
            headers=developer_headers,
        )
        assert runtime_detail.status_code == 200
        assert runtime_detail.json()["endpoint"] == "https://runtime.example.com"
        assert runtime_detail.json()["authType"] == "key_auth"
        assert runtime_detail.json()["envs"] == [
            {"key": "MCP_VISIBLE_AUTH_TOKEN", "value": "visible-secret"}
        ]
        viewer_runtime_detail = client.get(
            "/web/runtime-detail?runtimeId=runtime-viewer&region=cn-beijing",
            headers=viewer_headers,
        )
        assert viewer_runtime_detail.status_code == 200
        assert viewer_runtime_detail.json()["envs"] == [
            {"key": "VIEWER_VISIBLE_TOKEN", "value": "viewer-secret"}
        ]
        assert "runtime-key" not in runtime_detail.text
        revealed_key = client.post(
            "/web/runtime-api-key/reveal?runtimeId=runtime-developer&region=cn-beijing",
            headers=developer_headers,
        )
        assert revealed_key.status_code == 200
        assert revealed_key.json() == {"apiKey": "runtime-key"}
        assert revealed_key.headers["cache-control"] == "no-store"
        assert revealed_key.headers["pragma"] == "no-cache"
        assert (
            client.post(
                "/web/runtime-api-key/reveal?runtimeId=runtime-other&region=cn-beijing",
                headers=developer_headers,
            ).status_code
            == 404
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


def test_runtime_trace_reads_apmplus_and_explains_missing_observability(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    runtime = _runtime("runtime-developer", "developer")
    runtime.project_name = "default"
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        AgentkitRuntimeClient,
        "get_runtime",
        lambda _self, _request: runtime,
    )

    def load_trace(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(kwargs)
        if kwargs["session_id"] == "session-without-trace":
            return []
        return [
            {
                "operation_name": "invocation",
                "span_id": "span-1",
                "trace_id": "trace-1",
                "parent_span_id": "",
                "start_time_microsecond": 1_000,
                "duration_microseconds": 250,
                "tags": {"gen_ai.session.id": kwargs["session_id"]},
            }
        ]

    monkeypatch.setattr(
        "veadk.cli.frontend_apmplus_trace.load_apmplus_trace",
        load_trace,
    )
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        developers="developer",
    )
    headers = {"X-VeADK-Local-User": "developer"}

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-trace",
            params={
                "runtimeId": "runtime-developer",
                "sessionId": "session-1",
                "region": "cn-beijing",
                "endTimeMs": 1_800_000_000_000,
            },
            headers=headers,
        )
        missing = client.get(
            "/web/runtime-trace",
            params={
                "runtimeId": "runtime-developer",
                "sessionId": "session-without-trace",
                "region": "cn-beijing",
            },
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()[0]["name"] == "invocation"
    assert response.json()[0]["start_time"] == 1_000_000
    assert calls[0]["runtime_id"] == "runtime-developer"
    assert calls[0]["session_id"] == "session-1"
    assert calls[0]["project_name"] == "default"
    assert calls[0]["now_ms"] == 1_800_000_000_000
    assert missing.status_code == 404
    assert missing.json()["detail"] == (
        "该 Agent 暂未开启链路观测，请到控制台打开后使用。"
    )


def test_runtime_update_capability_supports_owned_unmanaged_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    runtime = _runtime_with_public_endpoint(
        _runtime("runtime-unmanaged", "developer", managed=False)
    )
    runtime.current_version_number = 7
    runtime.network_configurations.append(
        SimpleNamespace(
            endpoint="https://runtime.internal.example.com",
            network_type="private",
            vpc_configuration=SimpleNamespace(
                vpc_id="vpc-existing",
                subnet_ids=["subnet-a", "subnet-b"],
                enable_shared_internet_access=True,
            ),
        )
    )
    requested_paths: list[str] = []

    def get_runtime(_self: Any, request: Any) -> SimpleNamespace:
        if request.runtime_id == "runtime-missing":
            raise RuntimeError("InvalidResource.NotFound")
        return runtime

    class RuntimeAsyncClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "RuntimeAsyncClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def request(
            self,
            _method: str,
            url: str,
            **_kwargs: Any,
        ) -> _RuntimeJsonResponse:
            requested_paths.append(url)
            if url.endswith("/list-apps"):
                return _RuntimeJsonResponse(["selected-agent"])
            assert url.endswith("/web/agent-info/selected-agent")
            return _RuntimeJsonResponse(
                {
                    "name": "selected-agent",
                    "description": "Existing Agent",
                }
            )

    monkeypatch.setattr(AgentkitRuntimeClient, "get_runtime", get_runtime)
    monkeypatch.setattr("httpx.AsyncClient", RuntimeAsyncClient)
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        admins="admin",
        developers="developer,other-developer",
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-update-capability",
            params={
                "runtimeId": runtime.runtime_id,
                "region": "cn-beijing",
            },
            headers={"X-VeADK-Local-User": "developer"},
        )
        missing_app = client.get(
            "/web/runtime-update-capability",
            params={
                "runtimeId": runtime.runtime_id,
                "region": "cn-beijing",
                "appName": "missing-agent",
            },
            headers={"X-VeADK-Local-User": "developer"},
        )
        forbidden = client.get(
            "/web/runtime-update-capability",
            params={
                "runtimeId": runtime.runtime_id,
                "region": "cn-beijing",
                "appName": "selected-agent",
            },
            headers={"X-VeADK-Local-User": "other-developer"},
        )
        no_permission = client.get(
            "/web/runtime-update-capability",
            params={
                "runtimeId": runtime.runtime_id,
                "region": "cn-beijing",
                "appName": "selected-agent",
            },
            headers={"X-VeADK-Local-User": "viewer"},
        )
        missing_runtime = client.get(
            "/web/runtime-update-capability",
            params={
                "runtimeId": "runtime-missing",
                "region": "cn-beijing",
                "appName": "selected-agent",
            },
            headers={"X-VeADK-Local-User": "developer"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "canUpdate": True,
        "reason": "",
        "reasonCode": "",
        "runtime": {
            "runtimeId": runtime.runtime_id,
            "name": runtime.name,
            "status": "Running",
            "region": "cn-beijing",
            "currentVersion": 7,
            "managed": False,
            "envs": [],
            "network": {
                "mode": "both",
                "vpcId": "vpc-existing",
                "subnetIds": "subnet-a,subnet-b",
                "enableSharedInternetAccess": True,
            },
        },
        "agent": {
            "appName": "selected-agent",
            "name": "selected-agent",
            "description": "Existing Agent",
        },
    }
    assert requested_paths[:2] == [
        "https://runtime.example.com/list-apps",
        "https://runtime.example.com/web/agent-info/selected-agent",
    ]
    assert missing_app.status_code == 200
    assert missing_app.json()["canUpdate"] is False
    assert missing_app.json()["reasonCode"] == "runtime_app_not_found"
    assert missing_app.json()["reason"] == "该 Runtime 中不存在当前 Agent，无法更新。"
    assert missing_app.json()["agent"] == {"appName": "missing-agent"}
    assert forbidden.status_code == 404
    assert forbidden.json()["detail"] == "runtime_access_denied"
    assert no_permission.status_code == 403
    assert missing_runtime.status_code == 404
    assert missing_runtime.json()["detail"] == "runtime_not_found"


def test_runtime_update_capability_distinguishes_incompatible_and_network_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    runtime = _runtime_with_public_endpoint(_runtime("runtime-1", "developer"))
    mode = "unsupported"

    monkeypatch.setattr(
        AgentkitRuntimeClient,
        "get_runtime",
        lambda _self, _request: runtime,
    )

    class RuntimeAsyncClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "RuntimeAsyncClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def request(
            self,
            _method: str,
            url: str,
            **_kwargs: Any,
        ) -> _RuntimeJsonResponse:
            if mode == "network":
                raise httpx.ConnectError("connect failed")
            if url.endswith("/list-apps"):
                if mode == "unsupported":
                    return _RuntimeJsonResponse(
                        {},
                        status_code=404,
                        text="Not Found",
                    )
                if mode == "empty":
                    return _RuntimeJsonResponse([])
                if mode == "multiple":
                    return _RuntimeJsonResponse(["selected-agent", "other-agent"])
                return _RuntimeJsonResponse(["selected-agent"])
            assert url.endswith("/web/agent-info/selected-agent")
            assert mode == "agent-unsupported"
            return _RuntimeJsonResponse({}, status_code=404, text="Not Found")

    monkeypatch.setattr("httpx.AsyncClient", RuntimeAsyncClient)
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        developers="developer",
    )
    params = {
        "runtimeId": runtime.runtime_id,
        "region": "cn-beijing",
        "appName": "selected-agent",
    }

    with TestClient(app) as client:
        incompatible = client.get(
            "/web/runtime-update-capability",
            params=params,
            headers={"X-VeADK-Local-User": "developer"},
        )
        mode = "agent-unsupported"
        agent_unsupported = client.get(
            "/web/runtime-update-capability",
            params=params,
            headers={"X-VeADK-Local-User": "developer"},
        )
        mode = "empty"
        no_apps = client.get(
            "/web/runtime-update-capability",
            params=params,
            headers={"X-VeADK-Local-User": "developer"},
        )
        mode = "multiple"
        multiple_apps = client.get(
            "/web/runtime-update-capability",
            params=params,
            headers={"X-VeADK-Local-User": "developer"},
        )
        mode = "network"
        network_error = client.get(
            "/web/runtime-update-capability",
            params=params,
            headers={"X-VeADK-Local-User": "developer"},
        )

    assert incompatible.status_code == 200
    assert incompatible.json()["canUpdate"] is False
    assert incompatible.json()["reasonCode"] == "runtime_list_apps_unsupported"
    assert incompatible.json()["reason"] == (
        "该 Runtime 不支持 list-apps 接口，无法更新。"
    )
    assert agent_unsupported.status_code == 200
    assert agent_unsupported.json()["canUpdate"] is False
    assert agent_unsupported.json()["reasonCode"] == ("runtime_agent_info_unsupported")
    assert agent_unsupported.json()["agent"] == {"appName": "selected-agent"}
    assert no_apps.status_code == 200
    assert no_apps.json()["canUpdate"] is False
    assert no_apps.json()["reasonCode"] == "runtime_no_apps"
    assert no_apps.json()["reason"] == "该 Runtime 未提供可更新 Agent。"
    assert multiple_apps.status_code == 200
    assert multiple_apps.json()["canUpdate"] is False
    assert multiple_apps.json()["reasonCode"] == "runtime_multiple_apps"
    assert multiple_apps.json()["reason"] == (
        "该 Runtime 包含多个 Agent，暂不支持原地更新。"
    )
    assert network_error.status_code == 502
    assert network_error.json()["detail"] == "runtime_json_connect_error"


@pytest.mark.parametrize(
    "evaluation_error",
    [None, "evaluation workspace unavailable"],
)
def test_update_deployment_reuses_owned_runtime_and_returns_new_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    evaluation_error: str | None,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    runtime = _runtime_with_public_endpoint(
        _runtime("runtime-developer", "developer", managed=False)
    )
    runtime.authorizer_configuration = SimpleNamespace(
        key_auth=None,
        custom_jwt_authorizer=SimpleNamespace(
            discovery_url=(
                "https://studio.example.com/.well-known/openid-configuration"
            ),
            allowed_clients=["studio-client"],
        ),
    )
    runtime.role_name = "runtime-role"
    runtime.current_version_number = 3
    runtime.envs = [
        SimpleNamespace(
            key="MCP_UPDATED_AGENT_ORDERS_AUTH_TOKEN",
            value="preserved-secret",
        ),
        SimpleNamespace(key="REPLACED_ENV", value="old-value"),
    ]
    captured_config: dict[str, Any] = {}
    get_calls = 0
    evaluation_set_calls: list[dict[str, Any]] = []

    def get_runtime(_self: Any, _request: Any) -> SimpleNamespace:
        nonlocal get_calls
        get_calls += 1
        runtime.current_version_number = 4 if get_calls > 1 else 3
        return runtime

    def launch(*, config_file: str, **_kwargs: Any) -> SimpleNamespace:
        captured_config.update(yaml.safe_load(Path(config_file).read_text()))
        return SimpleNamespace(
            success=True,
            error=None,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.com",
                metadata={
                    "runtime_id": runtime.runtime_id,
                    "runtime_name": runtime.name,
                    "runtime_endpoint": "https://runtime.example.com",
                    "runtime_apikey": "secret",
                },
            ),
        )

    monkeypatch.setattr(AgentkitRuntimeClient, "get_runtime", get_runtime)

    class RuntimeAsyncClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "RuntimeAsyncClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def request(
            self,
            _method: str,
            url: str,
            **_kwargs: Any,
        ) -> _RuntimeJsonResponse:
            if url.endswith("/list-apps"):
                return _RuntimeJsonResponse(["updated-agent"])
            assert url.endswith("/web/agent-info/updated-agent")
            return _RuntimeJsonResponse({"name": "updated-agent"})

    monkeypatch.setattr("httpx.AsyncClient", RuntimeAsyncClient)
    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)

    async def initialize_evaluation_sets(**kwargs: Any) -> list[str]:
        evaluation_set_calls.append(kwargs)
        if evaluation_error:
            raise RuntimeError(evaluation_error)
        return ["updated-agent_good_case", "updated-agent_bad_case"]

    monkeypatch.setattr(
        "frontend.server.evaluation_automation.datasets.ensure_feedback_sets",
        initialize_evaluation_sets,
    )
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        admins="admin",
        developers="developer",
    )

    @app.middleware("http")
    async def _mark_validated_oauth_token(request: Request, call_next):
        request.state.oauth2_access_token_validated = True
        request.state.oauth2_access_token = "validated.jwt.token"
        return await call_next(request)

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/web/deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "name": "updated-agent",
                "description": "Updated\n description 🤖",
                "runtimeId": runtime.runtime_id,
                "appName": "updated-agent",
                "files": [{"path": "app.py", "content": "app = object()\n"}],
                "config": {"region": "cn-beijing", "projectName": "default"},
                "authentication": {"type": "api_key"},
                "envs": [{"key": "REPLACED_ENV", "value": "new-value"}],
            },
        ) as response:
            frames = [
                json.loads(line.removeprefix("data: "))
                for line in response.iter_lines()
                if line.startswith("data: ")
            ]

    assert response.status_code == 200
    assert frames[-1]["success"] is True
    assert frames[-1]["runtimeId"] == runtime.runtime_id
    assert frames[-1]["version"] == 4
    evaluation_frames = [
        frame for frame in frames if frame.get("phase") == "evaluation"
    ]
    assert evaluation_frames[0]["message"] == ("正在创建 Good Case 和 Bad Case 评测集")
    if evaluation_error:
        assert evaluation_frames[-1]["level"] == "warning"
        assert evaluation_frames[-1]["message"] == (
            "Good Case 和 Bad Case 评测集创建失败"
        )
        assert frames[-1]["warnings"] == [
            "Runtime 已部署，但评测集创建失败：evaluation workspace unavailable"
        ]
    else:
        assert evaluation_frames[-1]["level"] == "success"
        assert evaluation_frames[-1]["message"] == (
            "Good Case 和 Bad Case 评测集已创建"
        )
        assert "warnings" not in frames[-1]
    assert len(evaluation_set_calls) == 1
    assert callable(evaluation_set_calls[0]["openapi_post"])
    assert evaluation_set_calls[0] | {"openapi_post": None} == {
        "openapi_post": None,
        "region": "cn-beijing",
        "project_name": "default",
        "agent_name": "updated-agent",
    }
    cloud = captured_config["launch_types"]["cloud"]
    assert cloud["runtime_id"] == runtime.runtime_id
    assert cloud["runtime_name"] == runtime.name
    assert cloud["runtime_role_name"] == "runtime-role"
    assert cloud["image_tag"] == "veadk-v4"
    assert cloud["runtime_auth_type"] == "custom_jwt"
    assert cloud["runtime_jwt_discovery_url"] == (
        "https://studio.example.com/.well-known/openid-configuration"
    )
    assert cloud["runtime_jwt_allowed_clients"] == ["studio-client"]
    assert cloud["runtime_envs"]["MCP_UPDATED_AGENT_ORDERS_AUTH_TOKEN"] == (
        "preserved-secret"
    )
    assert cloud["runtime_envs"]["REPLACED_ENV"] == "new-value"
    assert "runtime_network" not in cloud
    assert captured_config["common"]["description"] == "Updated description"


@pytest.mark.parametrize(
    ("session_storage", "min_instance", "max_instance", "expects_update"),
    [
        ("in-memory", 1, 1, True),
        ("persistent", 1, 5, False),
        ("persistent", 2, 4, True),
    ],
)
def test_new_deployment_only_updates_non_default_instance_range(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    session_storage: str,
    min_instance: int,
    max_instance: int,
    expects_update: bool,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    runtime_id = "r-new-runtime"
    update_requests: list[Any] = []
    create_requests: list[Any] = []
    captured_config: dict[str, Any] = {}

    def create_runtime(_self: Any, request: Any) -> SimpleNamespace:
        create_requests.append(request)
        return SimpleNamespace(runtime_id=runtime_id)

    def update_runtime(_self: Any, request: Any) -> SimpleNamespace:
        update_requests.append(request)
        return SimpleNamespace(runtime_id=runtime_id)

    def get_runtime(_self: Any, _request: Any) -> SimpleNamespace:
        return SimpleNamespace(current_version_number=2)

    def launch(*, config_file: str, **_kwargs: Any) -> SimpleNamespace:
        captured_config.update(yaml.safe_load(Path(config_file).read_text()))
        request = SimpleNamespace(tags=[], apmplus_enable=True, description="demo")
        created = AgentkitRuntimeClient.create_runtime(object(), request)
        return SimpleNamespace(
            success=True,
            error=None,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.com",
                metadata={
                    "runtime_id": created.runtime_id,
                    "runtime_name": "demo-agent",
                    "runtime_endpoint": "https://runtime.example.com",
                    "runtime_apikey": "secret",
                },
            ),
        )

    monkeypatch.setattr(AgentkitRuntimeClient, "create_runtime", create_runtime)
    monkeypatch.setattr(AgentkitRuntimeClient, "update_runtime", update_runtime)
    monkeypatch.setattr(AgentkitRuntimeClient, "get_runtime", get_runtime)
    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/web/deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "name": "demo-agent",
                "sessionStorage": session_storage,
                "minInstance": min_instance,
                "maxInstance": max_instance,
                "createEvaluationSets": False,
                "files": [{"path": "app.py", "content": "app = object()\n"}],
                "config": {"region": "cn-beijing", "projectName": "default"},
            },
        ) as response:
            frames = [
                json.loads(line.removeprefix("data: "))
                for line in response.iter_lines()
                if line.startswith("data: ")
            ]

    assert response.status_code == 200
    assert frames[-1]["success"] is True
    assert create_requests[0].apmplus_enable is True
    assert captured_config["launch_types"]["cloud"]["runtime_auth_type"] == ("key_auth")
    runtime_envs = captured_config["launch_types"]["cloud"]["runtime_envs"]
    assert "OTEL_SDK_DISABLED" not in runtime_envs
    assert "ENABLE_APMPLUS" not in runtime_envs
    assert "OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY" not in runtime_envs
    assert not any(frame.get("phase") == "evaluation" for frame in frames)
    assert bool(update_requests) is expects_update
    assert all(request.apmplus_enable is True for request in update_requests)
    assert any(frame.get("phase") == "update" for frame in frames) is expects_update
    if expects_update:
        request = update_requests[0]
        assert request.runtime_id == runtime_id
        assert request.min_instance == min_instance
        assert request.max_instance == max_instance
        assert request.release_enable is True


@pytest.mark.parametrize(
    ("min_instance", "max_instance", "detail"),
    [
        (0, 1, "Runtime instance range must use positive integers"),
        ("1", 5, "Runtime instance range must use positive integers"),
        (2, 1, "Runtime minInstance cannot exceed maxInstance"),
    ],
)
def test_new_deployment_rejects_invalid_instance_range(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    min_instance: object,
    max_instance: object,
    detail: str,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    with TestClient(app) as client:
        response = client.post(
            "/web/deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "name": "demo-agent",
                "minInstance": min_instance,
                "maxInstance": max_instance,
                "files": [{"path": "app.py", "content": "app = object()\n"}],
                "config": {"region": "cn-beijing", "projectName": "default"},
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == detail


def test_single_instance_update_failure_fails_the_deployment_at_update_phase(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    runtime_id = "r-update-failure"

    monkeypatch.setattr(
        AgentkitRuntimeClient,
        "create_runtime",
        lambda _self, _request: SimpleNamespace(runtime_id=runtime_id),
    )

    def fail_update(_self: Any, _request: Any) -> None:
        raise RuntimeError("instance update failed")

    monkeypatch.setattr(
        AgentkitRuntimeClient,
        "update_runtime",
        fail_update,
    )

    def launch(**_kwargs: Any) -> SimpleNamespace:
        request = SimpleNamespace(tags=[], apmplus_enable=True, description="demo")
        created = AgentkitRuntimeClient.create_runtime(object(), request)
        return SimpleNamespace(
            success=True,
            error=None,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.com",
                metadata={"runtime_id": created.runtime_id},
            ),
        )

    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/web/deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "name": "demo-agent",
                "sessionStorage": "in-memory",
                "minInstance": 1,
                "maxInstance": 1,
                "files": [{"path": "app.py", "content": "app = object()\n"}],
                "config": {"region": "cn-beijing", "projectName": "default"},
            },
        ) as response:
            frames = [
                json.loads(line.removeprefix("data: "))
                for line in response.iter_lines()
                if line.startswith("data: ")
            ]

    assert response.status_code == 200
    assert frames[-1]["success"] is False
    assert frames[-1]["phase"] == "update"
    assert "instance update failed" in frames[-1]["error"]


def test_update_deployment_rejects_incompatible_runtime_before_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    runtime = _runtime_with_public_endpoint(
        _runtime("runtime-developer", "developer", managed=False)
    )
    launched = False

    monkeypatch.setattr(
        AgentkitRuntimeClient,
        "get_runtime",
        lambda _self, _request: runtime,
    )

    class RuntimeAsyncClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "RuntimeAsyncClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

        async def request(
            self,
            _method: str,
            url: str,
            **_kwargs: Any,
        ) -> _RuntimeJsonResponse:
            assert url.endswith("/list-apps")
            return _RuntimeJsonResponse(["updated-agent", "different-agent"])

    def launch(**_kwargs: Any) -> None:
        nonlocal launched
        launched = True

    monkeypatch.setattr("httpx.AsyncClient", RuntimeAsyncClient)
    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        developers="developer",
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "name": "updated-agent",
                "runtimeId": runtime.runtime_id,
                "appName": "updated-agent",
                "files": [{"path": "app.py", "content": "app = object()\n"}],
                "config": {"region": "cn-beijing", "projectName": "default"},
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "该 Runtime 包含多个 Agent，暂不支持原地更新。"
    )
    assert launched is False
