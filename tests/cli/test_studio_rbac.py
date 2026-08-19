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
import itertools
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
    _adapt_migration_model_envs,
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
    oauth2_provider_label: str | None = None,
    provider: str = "volcengine",
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
        oauth2_provider_label=oauth2_provider_label,
        auth_mode=auth_mode,
        generated_agent_test_run_ttl=60,
        studio_admins=admins,
        studio_developers=developers,
        open_browser=False,
        provider=provider,  # type: ignore[arg-type]
        studio=True,
    )
    return captured["app"]


@pytest.mark.parametrize(
    (
        "provider",
        "inherited_name",
        "inherited_base",
        "expected_name",
        "expected_base",
    ),
    [
        (
            "volcengine",
            "seed-2-0-lite-260228",
            "https://ark.ap-southeast.bytepluses.com/api/v3",
            "doubao-seed-2-1-pro-260628",
            "https://ark.cn-beijing.volces.com/api/v3",
        ),
        (
            "byteplus",
            "doubao-seed-2-1-pro-260628",
            "https://ark.cn-beijing.volces.com/api/v3/",
            "dola-seed-2-1-turbo-260628",
            "https://ark.ap-southeast.bytepluses.com/api/v3",
        ),
        (
            "volcengine",
            "seed-2-0-lite-260228",
            "https://ark.cn-beijing.volces.com/api/v3",
            "doubao-seed-2-1-pro-260628",
            "https://ark.cn-beijing.volces.com/api/v3",
        ),
        (
            "byteplus",
            "doubao-seed-2-1-pro-260628",
            "https://ark.ap-southeast.bytepluses.com/api/v3",
            "dola-seed-2-1-turbo-260628",
            "https://ark.ap-southeast.bytepluses.com/api/v3",
        ),
    ],
)
def test_migration_model_defaults_follow_studio_provider(
    provider: str,
    inherited_name: str,
    inherited_base: str,
    expected_name: str,
    expected_base: str,
) -> None:
    runtime_envs = {
        "MODEL_AGENT_NAME": inherited_name,
        "MODEL_AGENT_API_BASE": inherited_base,
    }

    _adapt_migration_model_envs(runtime_envs, provider)

    assert runtime_envs == {
        "MODEL_AGENT_NAME": expected_name,
        "MODEL_AGENT_API_BASE": expected_base,
        "MODEL_NAME": expected_name,
    }


def test_migration_model_defaults_preserve_custom_endpoint() -> None:
    runtime_envs = {
        "MODEL_AGENT_NAME": "private-model",
        "MODEL_AGENT_API_BASE": "https://models.example.com/v1",
    }

    _adapt_migration_model_envs(runtime_envs, "volcengine")

    assert runtime_envs == {
        "MODEL_AGENT_NAME": "private-model",
        "MODEL_AGENT_API_BASE": "https://models.example.com/v1",
        "MODEL_NAME": "private-model",
    }


@pytest.mark.parametrize(
    ("provider", "provider_label", "expected_label"),
    [
        ("volcengine", None, "火山引擎 Identity"),
        ("byteplus", None, "BytePlus Identity"),
        ("byteplus", "Enterprise SSO", "Enterprise SSO"),
    ],
)
def test_auth_config_uses_cloud_specific_identity_label(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    provider_label: str | None,
    expected_label: str,
) -> None:
    from veadk.auth.middleware.oauth2_auth import OAuth2Config

    monkeypatch.setattr(
        OAuth2Config,
        "from_veidentity",
        lambda **_: SimpleNamespace(
            cookie_secure=True,
            logout_redirect_url="/",
            end_session_url="https://identity.example.com/logout",
        ),
    )
    monkeypatch.setattr(
        "veadk.auth.middleware.oauth2_auth.setup_oauth2",
        lambda *_, **__: None,
    )
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        oauth2_user_pool_uid="pool-current",
        oauth2_user_pool_client_uid="studio-client",
        oauth2_provider_label=provider_label,
        provider=provider,
    )

    with TestClient(app) as client:
        response = client.get("/web/auth-config")

    assert response.status_code == 200
    assert response.json()["providers"] == [
        {
            "id": "veidentity",
            "label": expected_label,
            "loginUrl": "/oauth2/login",
        }
    ]


def test_project_handoff_pairing_authorizes_only_terminal_session_routes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from veadk.auth.middleware.oauth2_auth import OAuth2Config

    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        OAuth2Config,
        "from_veidentity",
        lambda **_: SimpleNamespace(
            cookie_secure=True,
            logout_redirect_url="/",
            end_session_url="https://identity.example.com/logout",
        ),
    )

    def _capture_oauth2(*_: Any, **kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(
        "veadk.auth.middleware.oauth2_auth.setup_oauth2",
        _capture_oauth2,
    )

    _create_studio_app(
        monkeypatch,
        tmp_path,
        oauth2_user_pool_uid="pool-current",
        oauth2_user_pool_client_uid="studio-client",
    )

    assert "/web/sandbox/codex-project-handoff/sessions" in captured["exempt_paths"]
    assert "/web/sandbox/codex-project-handoff/sessions/" in captured["exempt_prefixes"]
    assert "/web/sandbox/codex-project-handoff/pairings" not in captured["exempt_paths"]


def test_no_sso_identity_endpoint_selects_local_username_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path)

    with TestClient(app) as client:
        identity = client.get("/oauth2/userinfo")
        auth_config = client.get("/web/auth-config")

    assert identity.status_code == 404
    assert identity.json() == {"status": "unauthenticated"}
    assert auth_config.status_code == 200
    assert auth_config.json() == {"providers": []}


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


def test_identity_user_pools_use_byteplus_default_region(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    clients: list[dict[str, Any]] = []

    class _FakeIdentityClient:
        def __init__(self, **kwargs: Any) -> None:
            clients.append(kwargs)

        def list_user_pools(self) -> list[dict[str, str]]:
            return [
                {
                    "uid": "pool-byteplus",
                    "name": "BytePlus Studio",
                    "domain": "studio.byteplus.example.com",
                }
            ]

    monkeypatch.delenv("VEIDENTITY_REGION", raising=False)
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "test-byteplus-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "test-byteplus-sk")
    monkeypatch.setattr(
        "veadk.integrations.ve_identity.identity_client.IdentityClient",
        _FakeIdentityClient,
    )
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        auth_mode="gateway",
        developers="developer",
        provider="byteplus",
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/identity/user-pools",
            headers={"Authorization": f"Bearer {_unsigned_jwt({'sub': 'developer'})}"},
        )

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "uid": "pool-byteplus",
            "name": "BytePlus Studio",
            "domain": "studio.byteplus.example.com",
            "region": "ap-southeast-1",
            "isCurrent": False,
        }
    ]
    assert clients == [
        {
            "access_key": "test-byteplus-ak",
            "secret_key": "test-byteplus-sk",
            "session_token": "",
            "region": "ap-southeast-1",
            "provider": "byteplus",
        }
    ]


def test_system_info_lists_configured_sandbox_tool_ids(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SANDBOX_CHAT_CODEX", "tool-codex")
    monkeypatch.setenv("SANDBOX_CHAT_OPENCLAW", "tool-openclaw")
    monkeypatch.setenv("SANDBOX_CHAT_HERMES", "tool-hermes")
    monkeypatch.setenv("SANDBOX_CHAT_CODEX_SNAPSHOT", "tool-codex-snapshot")
    monkeypatch.setenv("SANDBOX_CHAT_OPENCLAW_SNAPSHOT", "tool-openclaw-snapshot")
    monkeypatch.setenv("SANDBOX_CHAT_HERMES_SNAPSHOT", "tool-hermes-snapshot")
    monkeypatch.setenv("SANDBOX_DEV", "tool-dev")
    monkeypatch.setenv("VEADK_STUDIO_TOS_BUCKET", "teststudio")
    monkeypatch.setenv("VEADK_STUDIO_TOS_REGION", "cn-beijing")
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        auth_mode="gateway",
        admins="admin",
        developers="developer",
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/system-info",
            headers={"Authorization": f"Bearer {_unsigned_jwt({'sub': 'admin'})}"},
        )
        developer_denied = client.get(
            "/web/system-info",
            headers={"Authorization": f"Bearer {_unsigned_jwt({'sub': 'developer'})}"},
        )
        user_denied = client.get(
            "/web/system-info",
            headers={"Authorization": f"Bearer {_unsigned_jwt({'sub': 'viewer'})}"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "storage": {
            "tosAddress": "teststudio.tos-cn-beijing.volces.com",
        },
        "sandboxTools": [
            {
                "kind": "codex",
                "label": "Codex Sandbox",
                "toolId": "tool-codex",
                "snapshot": False,
            },
            {
                "kind": "codex_snapshot",
                "label": "Codex Sandbox",
                "toolId": "tool-codex-snapshot",
                "snapshot": True,
            },
            {
                "kind": "deepseek_harness",
                "label": "DeepSeek Harness Sandbox",
                "toolId": "tool-codex",
                "snapshot": False,
            },
            {
                "kind": "deepseek_harness_snapshot",
                "label": "DeepSeek Harness Sandbox",
                "toolId": "tool-codex-snapshot",
                "snapshot": True,
            },
            {
                "kind": "openclaw",
                "label": "OpenClaw Sandbox",
                "toolId": "tool-openclaw",
                "snapshot": False,
            },
            {
                "kind": "openclaw_snapshot",
                "label": "OpenClaw Sandbox",
                "toolId": "tool-openclaw-snapshot",
                "snapshot": True,
            },
            {
                "kind": "hermes",
                "label": "Hermes Sandbox",
                "toolId": "tool-hermes",
                "snapshot": False,
            },
            {
                "kind": "hermes_snapshot",
                "label": "Hermes Sandbox",
                "toolId": "tool-hermes-snapshot",
                "snapshot": True,
            },
            {
                "kind": "dev",
                "label": "Dev Sandbox",
                "toolId": "tool-dev",
                "snapshot": False,
            },
        ],
    }
    assert developer_denied.status_code == 403
    assert user_denied.status_code == 403


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


def test_byteplus_deploy_agentkit_uses_iam_file_for_sdk_templates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("BYTEPLUS_ACCESS_KEY", raising=False)
    monkeypatch.delenv("BYTEPLUS_SECRET_KEY", raising=False)
    monkeypatch.delenv("BYTEPLUS_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("BYTEPLUS_REGION", "ap-southeast-1")
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("DATABASE_VIKING_REGION", "cn-beijing")
    captured_config: dict[str, Any] = {}
    captured_env: dict[str, str | None] = {}

    import builtins
    import os

    real_open = builtins.open

    def _fake_open(path: object, *args: object, **kwargs: object):
        if path == "/var/run/secrets/iam/credential":
            return real_open(tmp_path / "iam-credential.json", *args, **kwargs)
        return real_open(path, *args, **kwargs)

    (tmp_path / "iam-credential.json").write_text(
        json.dumps(
            {
                "access_key_id": "iam-ak",
                "secret_access_key": "iam-sk",
                "session_token": "iam-token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(builtins, "open", _fake_open)
    monkeypatch.setattr(
        "agentkit.utils.template_utils.render_template",
        lambda template: template.replace("{{account_id}}", "3001037806"),
    )

    def launch(*, config_file: str, **_kwargs: Any) -> SimpleNamespace:
        captured_config.update(yaml.safe_load(Path(config_file).read_text()))
        captured_env.update(
            {
                "BYTEPLUS_ACCESS_KEY": os.environ.get("BYTEPLUS_ACCESS_KEY"),
                "BYTEPLUS_SECRET_KEY": os.environ.get("BYTEPLUS_SECRET_KEY"),
                "BYTEPLUS_SESSION_TOKEN": os.environ.get("BYTEPLUS_SESSION_TOKEN"),
            }
        )
        return SimpleNamespace(
            success=True,
            error=None,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.com",
                metadata={
                    "runtime_id": "runtime-bp",
                    "runtime_name": "byteplus-agent",
                    "runtime_endpoint": "https://runtime.example.com",
                    "runtime_apikey": "secret",
                },
            ),
        )

    async def initialize_evaluation_sets(**_kwargs: Any) -> list[str]:
        raise AssertionError("BytePlus deploy should not create evaluation sets")

    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    monkeypatch.setattr(
        "frontend.server.evaluation_automation.datasets.ensure_feedback_sets",
        initialize_evaluation_sets,
    )
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        developers="developer",
        provider="byteplus",
    )

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/web/deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "name": "byteplus-agent",
                "files": [{"path": "app.py", "content": "app = object()\n"}],
                "config": {"region": "ap-southeast-1", "projectName": "default"},
            },
        ) as response:
            frames = [
                json.loads(line.removeprefix("data: "))
                for line in response.iter_lines()
                if line.startswith("data: ")
            ]

    assert response.status_code == 200
    assert frames[-1]["success"] is True
    assert not [frame for frame in frames if frame.get("phase") == "evaluation"]
    assert captured_env == {
        "BYTEPLUS_ACCESS_KEY": "iam-ak",
        "BYTEPLUS_SECRET_KEY": "iam-sk",
        "BYTEPLUS_SESSION_TOKEN": "iam-token",
    }
    cloud = captured_config["launch_types"]["cloud"]
    assert cloud["region"] == "ap-southeast-1"
    assert cloud["tos_bucket"] == "agentkit-platform-3001037806-ap-southeast-1"
    assert cloud["cr_instance_name"] == "agentkit-platform-3001037806"
    runtime_envs = cloud["runtime_envs"]
    assert runtime_envs["CLOUD_PROVIDER"] == "byteplus"
    assert runtime_envs["AGENTKIT_CLOUD_PROVIDER"] == "byteplus"
    assert runtime_envs["DATABASE_VIKING_REGION"] == "cn-hongkong"
    assert "BYTEPLUS_ACCESS_KEY" not in runtime_envs
    assert "BYTEPLUS_SECRET_KEY" not in runtime_envs
    assert "BYTEPLUS_SESSION_TOKEN" not in runtime_envs
    assert os.environ.get("BYTEPLUS_ACCESS_KEY") is None


def test_migration_routes_require_agent_management_role(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SANDBOX_DEV", raising=False)
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    with TestClient(app) as client:
        viewer = client.get(
            "/web/agent-migrations/capabilities",
            headers={"X-VeADK-Local-User": "viewer"},
        )
        developer = client.get(
            "/web/agent-migrations/capabilities",
            headers={"X-VeADK-Local-User": "developer"},
        )
        create = client.post(
            "/web/agent-migrations/tasks",
            headers={"X-VeADK-Local-User": "developer"},
            json={"sourceFileName": "source.zip"},
        )
        invalid_cancel = client.post(
            "/web/cancel-deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={},
        )

    assert viewer.status_code == 403
    assert developer.status_code == 200
    assert create.status_code == 503
    assert invalid_cancel.status_code == 400


def test_migration_capabilities_reuse_the_shared_devenv_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.tools.client import AgentkitToolsClient

    from veadk.cli.frontend_skill_creator import _sandbox_model_config

    _, base_url = _sandbox_model_config("volcengine")
    monkeypatch.setenv("SANDBOX_DEV", "tool-dev")
    monkeypatch.setattr(
        AgentkitToolsClient,
        "get_tool",
        lambda _self, _request: SimpleNamespace(
            tool_type="DevEnv",
            status="Ready",
            image_url="",
            envs=[
                SimpleNamespace(key="CODEX_MODEL", value="model"),
                SimpleNamespace(key="CODEX_API_KEY", value="secret"),
                SimpleNamespace(key="CODEX_BASE_URL", value=base_url),
            ],
        ),
    )
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    with TestClient(app) as client:
        configured = client.get(
            "/web/agent-migrations/capabilities",
            headers={"X-VeADK-Local-User": "developer"},
        )

    assert configured.status_code == 200
    assert configured.json()["enabled"] is True

    missing_credentials_app = _create_studio_app(
        monkeypatch,
        tmp_path,
        developers="developer",
    )
    monkeypatch.delenv("VOLCENGINE_ACCESS_KEY")
    monkeypatch.delenv("VOLCENGINE_SECRET_KEY")

    with TestClient(missing_credentials_app) as client:
        unavailable = client.get(
            "/web/agent-migrations/capabilities",
            headers={"X-VeADK-Local-User": "developer"},
        )

    assert unavailable.status_code == 200
    assert unavailable.json()["enabled"] is False


def test_invalid_code_package_deploy_removes_temporary_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")
    temporary_source = tmp_path / "invalid-code-package"

    def make_temporary_source(*, prefix: str) -> str:
        assert prefix.startswith("agentkit_deploy_")
        temporary_source.mkdir()
        return str(temporary_source)

    monkeypatch.setattr("tempfile.mkdtemp", make_temporary_source)
    with TestClient(app) as client:
        response = client.post(
            "/web/deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "name": "invalid-package",
                "files": [
                    {
                        "path": "agentkit.yaml",
                        "content": "common:\n  entry_point: missing.py\n",
                    }
                ],
                "config": {"region": "cn-beijing", "projectName": "default"},
                "createEvaluationSets": False,
            },
        )

    assert response.status_code == 400
    assert not temporary_source.exists()


def test_code_package_manifest_entry_point_reaches_agentkit_sdk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured_config: dict[str, Any] = {}

    def launch(*, config_file: str, **_kwargs: Any) -> SimpleNamespace:
        config_path = Path(config_file)
        captured_config.update(yaml.safe_load(config_path.read_text()))
        assert (config_path.parent / "runtime" / "main.py").read_text() == (
            "app = object()\n"
        )
        return SimpleNamespace(
            success=True,
            error=None,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.com",
                metadata={
                    "runtime_id": "runtime-manifest-entry",
                    "runtime_name": "manifest-agent",
                    "runtime_endpoint": "https://runtime.example.com",
                    "runtime_apikey": "secret",
                },
            ),
        )

    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    with (
        TestClient(app) as client,
        client.stream(
            "POST",
            "/web/deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "name": "manifest-agent",
                "files": [
                    {
                        "path": "agentkit.yaml",
                        "content": (
                            "common:\n"
                            "  agent_name: ignored\n"
                            "  entry_point: runtime/main.py\n"
                        ),
                    },
                    {
                        "path": "runtime/main.py",
                        "content": "app = object()\n",
                    },
                ],
                "config": {"region": "cn-beijing", "projectName": "default"},
                "createEvaluationSets": False,
            },
        ) as response,
    ):
        frames = [
            json.loads(line.removeprefix("data: "))
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]

    assert response.status_code == 200
    assert frames[-1]["success"] is True
    assert captured_config["common"]["entry_point"] == "runtime/main.py"


def test_migration_deployment_materializes_owned_session_source_server_side(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from frontend.server.migration.service import MigrationService
    from veadk.config import veadk_environments

    captured_config: dict[str, Any] = {}
    materialized: dict[str, str] = {}

    def materialize(
        _self: MigrationService,
        task_id: str,
        owner_id: str,
        target: Path,
    ) -> str:
        materialized.update(task_id=task_id, owner_id=owner_id)
        entry = target / "runtime" / "migrated.py"
        entry.parent.mkdir(parents=True)
        entry.write_text("app = object()\n", encoding="utf-8")
        return "runtime/migrated.py"

    def launch(*, config_file: str, **_kwargs: Any) -> SimpleNamespace:
        config_path = Path(config_file)
        captured_config.update(yaml.safe_load(config_path.read_text()))
        assert (config_path.parent / "runtime" / "migrated.py").is_file()
        assert not (config_path.parent / "browser.py").exists()
        return SimpleNamespace(
            success=True,
            error=None,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.com",
                metadata={
                    "runtime_id": "runtime-migrated",
                    "runtime_name": "migrated-agent",
                    "runtime_endpoint": "https://runtime.example.com",
                    "runtime_apikey": "secret",
                },
            ),
        )

    monkeypatch.setattr(MigrationService, "materialize_deployment", materialize)
    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    monkeypatch.setitem(
        veadk_environments,
        "MODEL_AGENT_NAME",
        "seed-2-0-lite-260228",
    )
    monkeypatch.setitem(
        veadk_environments,
        "MODEL_AGENT_API_BASE",
        "https://ark.ap-southeast.bytepluses.com/api/v3",
    )
    monkeypatch.setitem(veadk_environments, "MODEL_AGENT_API_KEY", "test-model-key")
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    with (
        TestClient(app) as client,
        client.stream(
            "POST",
            "/web/deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "name": "migrated-agent",
                "migrationTaskId": "migration-v1-" + "1" * 32,
                "envs": [
                    {"key": "MODEL_AGENT_NAME", "value": "seed-2-0-lite-260228"},
                    {
                        "key": "MODEL_AGENT_API_BASE",
                        "value": "https://ark.ap-southeast.bytepluses.com/api/v3",
                    },
                    {"key": "MODEL_NAME", "value": "seed-2-0-lite-260228"},
                ],
                "files": [
                    {
                        "path": "browser.py",
                        "content": "raise RuntimeError('untrusted')\n",
                    }
                ],
                "config": {"region": "cn-beijing", "projectName": "default"},
                "createEvaluationSets": False,
            },
        ) as response,
    ):
        frames = [
            json.loads(line.removeprefix("data: "))
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]

    assert response.status_code == 200
    assert frames[-1]["success"] is True
    assert materialized == {
        "task_id": "migration-v1-" + "1" * 32,
        "owner_id": "developer",
    }
    assert captured_config["common"]["entry_point"] == "runtime/migrated.py"
    runtime_envs = captured_config["launch_types"]["cloud"]["runtime_envs"]
    assert runtime_envs["MODEL_AGENT_NAME"] == "doubao-seed-2-1-pro-260628"
    assert runtime_envs["MODEL_NAME"] == "doubao-seed-2-1-pro-260628"
    assert runtime_envs["MODEL_AGENT_API_BASE"] == (
        "https://ark.cn-beijing.volces.com/api/v3"
    )


def test_migration_deployment_rejection_removes_temporary_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from frontend.server.migration.service import MigrationError, MigrationService

    temporary_source = tmp_path / "rejected-migration"

    def make_temporary_source(*, prefix: str) -> str:
        assert prefix.startswith("agentkit_deploy_")
        temporary_source.mkdir()
        return str(temporary_source)

    def reject(*_args: object, **_kwargs: object) -> str:
        raise MigrationError(
            "MIGRATION_ARTIFACT_NOT_READY",
            "artifact not ready",
            status_code=409,
        )

    monkeypatch.setattr("tempfile.mkdtemp", make_temporary_source)
    monkeypatch.setattr(MigrationService, "materialize_deployment", reject)
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    with TestClient(app) as client:
        response = client.post(
            "/web/deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "name": "migrated-agent",
                "migrationTaskId": "migration-v1-" + "1" * 32,
                "files": [],
                "config": {"region": "cn-beijing", "projectName": "default"},
                "createEvaluationSets": False,
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "artifact not ready"
    assert not temporary_source.exists()


@pytest.mark.parametrize(
    ("provider", "region"),
    [
        ("volcengine", "cn-beijing"),
        ("byteplus", "ap-southeast-1"),
    ],
)
def test_deployment_resource_mode_matrix_reaches_agentkit_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    region: str,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    from frontend.server.deployment_resources import DeploymentResourceService
    from veadk.config import veadk_environments

    captured_configs: list[dict[str, Any]] = []

    def existing_resource(
        _self: DeploymentResourceService,
        kind: str,
        **parents: str,
    ) -> dict[str, str]:
        resource_id = parents["resource_id"]
        return {
            "id": resource_id,
            "name": ("pipeline-existing" if kind == "cp-pipeline" else resource_id),
        }

    def launch(*, config_file: str, **_kwargs: Any) -> SimpleNamespace:
        captured_configs.append(yaml.safe_load(Path(config_file).read_text()))
        runtime_id = f"runtime-{len(captured_configs)}"
        return SimpleNamespace(
            success=True,
            error=None,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.com",
                metadata={
                    "runtime_id": runtime_id,
                    "runtime_name": "matrix-agent",
                    "runtime_endpoint": "https://runtime.example.com",
                    "runtime_apikey": "secret",
                },
            ),
        )

    monkeypatch.setattr(
        DeploymentResourceService,
        "_require_existing_resource",
        existing_resource,
    )
    monkeypatch.setattr(
        "agentkit.utils.template_utils.render_template",
        lambda _template: "agentkit-platform-test-account",
    )
    monkeypatch.setattr(
        AgentkitRuntimeClient,
        "get_runtime",
        lambda _self, _request: SimpleNamespace(current_version_number=1),
    )
    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    monkeypatch.setitem(
        veadk_environments,
        "MODEL_AGENT_API_KEY",
        "test-model-key",
    )
    if provider == "byteplus":
        monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "test-ak")
        monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "test-sk")
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        developers="developer",
        provider=provider,
    )

    modes = ("auto", "create", "existing")
    with TestClient(app) as client:
        for tos_mode, cr_mode, cp_mode in itertools.product(modes, repeat=3):
            tos = {"mode": tos_mode}
            cr = {"mode": cr_mode}
            code_pipeline = {"mode": cp_mode}
            if tos_mode != "auto":
                tos["bucket"] = f"tos-{tos_mode}"
            if cr_mode != "auto":
                cr.update(
                    {
                        "instance": f"cr-{cr_mode}",
                        "namespace": f"namespace-{cr_mode}",
                        "repository": f"repository-{cr_mode}",
                    }
                )
            if cp_mode != "auto":
                code_pipeline.update(
                    {
                        "workspaceName": f"workspace-{cp_mode}",
                        "pipelineName": f"pipeline-{cp_mode}",
                    }
                )
            if cp_mode == "existing":
                code_pipeline.update(
                    {
                        "workspaceId": "workspace-existing",
                        "pipelineId": "pipeline-existing-id",
                    }
                )

            with client.stream(
                "POST",
                "/web/deploy-agentkit",
                headers={"X-VeADK-Local-User": "developer"},
                json={
                    "name": "matrix-agent",
                    "files": [{"path": "app.py", "content": "app = object()\n"}],
                    "config": {"region": region, "projectName": "default"},
                    "createEvaluationSets": False,
                    "resources": {
                        "tos": tos,
                        "cr": cr,
                        "codePipeline": code_pipeline,
                    },
                },
            ) as response:
                frames = [
                    json.loads(line.removeprefix("data: "))
                    for line in response.iter_lines()
                    if line.startswith("data: ")
                ]

            assert response.status_code == 200
            assert frames[-1]["success"] is True
            cloud = captured_configs[-1]["launch_types"]["cloud"]

            if tos_mode == "auto":
                if provider == "byteplus":
                    assert cloud["tos_bucket"] == (
                        "agentkit-platform-test-account-ap-southeast-1"
                    )
                else:
                    assert "tos_bucket" not in cloud
            else:
                assert cloud["tos_bucket"] == f"tos-{tos_mode}"

            if cr_mode == "auto":
                if provider == "byteplus":
                    assert cloud["cr_instance_name"] == (
                        "agentkit-platform-test-account"
                    )
                else:
                    assert "cr_instance_name" not in cloud
                assert "cr_namespace_name" not in cloud
                assert "cr_repo_name" not in cloud
            else:
                assert cloud["cr_instance_name"] == f"cr-{cr_mode}"
                assert cloud["cr_namespace_name"] == f"namespace-{cr_mode}"
                assert cloud["cr_repo_name"] == f"repository-{cr_mode}"

            if cp_mode == "auto":
                assert "cp_workspace_name" not in cloud
                assert "cp_pipeline_name" not in cloud
                assert "cp_pipeline_id" not in cloud
            else:
                assert cloud["cp_workspace_name"] == f"workspace-{cp_mode}"
                assert cloud["cp_pipeline_name"] == f"pipeline-{cp_mode}"
                if cp_mode == "existing":
                    assert cloud["cp_pipeline_id"] == "pipeline-existing-id"
                else:
                    assert "cp_pipeline_id" not in cloud

    assert len(captured_configs) == 27


@pytest.mark.parametrize(
    ("cp_mode", "workspace_id", "pipeline_id"),
    [
        ("create", "workspace-created-id", "pipeline-created-id"),
        ("existing", "workspace-existing", "pipeline-existing-id"),
    ],
)
@pytest.mark.parametrize(
    ("provider", "region"),
    [
        ("volcengine", "cn-beijing"),
        ("byteplus", "ap-southeast-1"),
    ],
)
def test_code_pipeline_build_logs_use_configured_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cp_mode: str,
    workspace_id: str,
    pipeline_id: str,
    provider: str,
    region: str,
) -> None:
    import threading

    import agentkit.toolkit.volcengine.code_pipeline as code_pipeline_mod

    from frontend.server.deployment_resources import DeploymentResourceService

    log_requested = threading.Event()
    stage_calls: list[tuple[str, str, str]] = []
    client_configs: list[dict[str, Any]] = []

    def existing_resource(
        _self: DeploymentResourceService,
        kind: str,
        **parents: str,
    ) -> dict[str, str]:
        resource_id = parents["resource_id"]
        return {
            "id": resource_id,
            "name": f"pipeline-{cp_mode}" if kind == "cp-pipeline" else resource_id,
        }

    class FakeCodePipeline:
        def __init__(self, **kwargs: Any) -> None:
            client_configs.append(kwargs)

        def get_workspaces_by_name(
            self, name: str, page_size: int
        ) -> dict[str, list[dict[str, str]]]:
            assert name == f"workspace-{cp_mode}"
            assert page_size == 5
            return {"Items": [{"Id": workspace_id, "Name": name}]}

        def list_pipeline_run_stages_inner(
            self,
            workspace_id: str,
            pipeline_id: str,
            pipeline_run_id: str,
        ) -> dict[str, list[Any]]:
            stage_calls.append((workspace_id, pipeline_id, pipeline_run_id))
            log_requested.set()
            return {"Items": []}

    def launch(*, reporter: Any, **_kwargs: Any) -> SimpleNamespace:
        if cp_mode == "existing":
            reporter.info("Reusing pipeline by name: pipeline-existing")
        else:
            reporter.info(
                "Pipeline created successfully: pipeline-create "
                "(ID: pipeline-created-id)"
            )
        reporter.info("Pipeline triggered successfully, run ID: run-existing")
        assert log_requested.wait(timeout=2)
        return SimpleNamespace(
            success=True,
            error=None,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.com",
                metadata={
                    "runtime_id": "runtime-existing",
                    "runtime_name": "matrix-agent",
                    "runtime_endpoint": "https://runtime.example.com",
                    "runtime_apikey": "secret",
                },
            ),
        )

    monkeypatch.setattr(
        DeploymentResourceService,
        "_require_existing_resource",
        existing_resource,
    )
    monkeypatch.setattr(code_pipeline_mod, "VeCodePipeline", FakeCodePipeline)
    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    if provider == "byteplus":
        monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "test-ak")
        monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "test-sk")
    else:
        monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "test-ak")
        monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "test-sk")
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        developers="developer",
        provider=provider,
    )
    code_pipeline = {
        "mode": cp_mode,
        "workspaceName": f"workspace-{cp_mode}",
        "pipelineName": f"pipeline-{cp_mode}",
    }
    if cp_mode == "existing":
        code_pipeline.update(
            {
                "workspaceId": workspace_id,
                "pipelineId": pipeline_id,
            }
        )

    with (
        TestClient(app) as client,
        client.stream(
            "POST",
            "/web/deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "name": "matrix-agent",
                "files": [{"path": "app.py", "content": "app = object()\n"}],
                "config": {"region": region, "projectName": "default"},
                "createEvaluationSets": False,
                "resources": {
                    "tos": {"mode": "auto"},
                    "cr": {"mode": "auto"},
                    "codePipeline": code_pipeline,
                },
            },
        ) as response,
    ):
        frames = [
            json.loads(line.removeprefix("data: "))
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]

    assert response.status_code == 200
    assert frames[-1]["success"] is True
    assert client_configs[-1]["provider"] == provider
    assert client_configs[-1]["region"] == region
    assert stage_calls == [(workspace_id, pipeline_id, "run-existing")]


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


def test_runtime_duplicate_name_error_has_actionable_message() -> None:
    from veadk.cli.cli_frontend import _runtime_deploy_error_detail

    detail = _runtime_deploy_error_detail(
        "CreateRuntime failed: InvalidParameter.DuplicateName",
        "travel-agent-a1b2c3",
    )

    assert detail == ("Runtime 名称“travel-agent-a1b2c3”已存在，请修改名称后重新部署。")
    assert _runtime_deploy_error_detail("AccessDenied", "unused") == "AccessDenied"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("", "Runtime 名称为必填项"),
        ("abc", "Runtime 名称长度须为 4-64 个字符"),
        ("a" * 65, "Runtime 名称长度须为 4-64 个字符"),
        ("valid-runtime", None),
    ],
)
def test_runtime_name_validation_covers_length_boundaries(
    name: str,
    expected: str | None,
) -> None:
    from veadk.cli.cli_frontend import _runtime_name_validation_error

    assert _runtime_name_validation_error(name) == expected


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
    assert "--skill-creator-tool-id" not in result.output


def test_access_endpoint_resolves_local_roles_and_blocks_user_management(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VEADK_STUDIO_ACCOUNT_ID", "2100123456")
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
        legacy_skill_creator = client.post(
            "/web/skill-creator/jobs",
            headers={"X-VeADK-Local-User": "reader"},
            json={"prompt": "Create a release notes Skill"},
        )

    assert admin.json()["role"] == "admin"
    assert developer.json()["role"] == "developer"
    assert developer.json()["telemetry"] == {
        "userId": "developer",
        "accountId": "2100123456",
    }
    assert user.json()["role"] == "user"
    assert user.json()["telemetry"]["userId"] == "reader"
    assert user.json()["telemetry"]["accountId"] == "2100123456"
    assert forbidden.status_code == 403
    assert legacy_skill_creator.status_code == 404


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_model_api_key_value_requires_agent_management_role(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
) -> None:
    resolved_ids: list[str] = []
    list_key_calls: list[bool] = []
    list_option_calls: list[tuple[str | None, bool]] = []

    async def resolve_raw_key(_self: object, key_id: str) -> str:
        resolved_ids.append(key_id)
        return "raw-secret-value"

    async def list_api_keys(
        _self: object,
        *,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        list_key_calls.append(force_refresh)
        return {
            "provider": "volcengine",
            "keys": [{"id": "key-1", "name": "first-key"}],
            "defaultKeyId": "key-1",
        }

    async def list_options(
        _self: object,
        *,
        api_key_id: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        list_option_calls.append((api_key_id, force_refresh))
        return {
            "provider": "volcengine",
            "selectedApiKeyId": "key-1",
            "models": [],
        }

    monkeypatch.setattr(
        "frontend.server.model_catalog.service.ModelCatalogService.resolve_raw_key",
        resolve_raw_key,
    )
    monkeypatch.setattr(
        "frontend.server.model_catalog.service.ModelCatalogService.list_api_keys",
        list_api_keys,
    )
    monkeypatch.setattr(
        "frontend.server.model_catalog.service.ModelCatalogService.list_options",
        list_options,
    )
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        admins="admin",
        developers="developer",
        provider=provider,
    )

    with TestClient(app) as client:
        unauthenticated = client.post("/web/model-api-keys/key-1/value")
        user = client.post(
            "/web/model-api-keys/key-1/value",
            headers={"X-VeADK-Local-User": "reader"},
        )
        developer = client.post(
            "/web/model-api-keys/key-1/value",
            headers={"X-VeADK-Local-User": "developer"},
        )
        admin = client.post(
            "/web/model-api-keys/key-1/value",
            headers={"X-VeADK-Local-User": "admin"},
        )
        unauthenticated_keys = client.get("/web/model-api-keys")
        user_keys = client.get(
            "/web/model-api-keys",
            headers={"X-VeADK-Local-User": "reader"},
        )
        developer_keys = client.get(
            "/web/model-api-keys",
            headers={"X-VeADK-Local-User": "developer"},
        )
        unauthenticated_models = client.get("/web/model-options")
        user_models = client.get(
            "/web/model-options",
            headers={"X-VeADK-Local-User": "reader"},
        )
        developer_models = client.get(
            "/web/model-options",
            headers={"X-VeADK-Local-User": "developer"},
        )

    assert unauthenticated.status_code == 401
    assert user.status_code == 403
    assert developer.status_code == 200
    assert admin.status_code == 200
    assert resolved_ids == ["key-1", "key-1"]
    for response in (unauthenticated, user, developer, admin):
        assert response.headers["cache-control"] == "no-store"
    for response in (unauthenticated, user):
        assert "raw-secret-value" not in response.text
    assert unauthenticated_keys.status_code == 401
    assert user_keys.status_code == 403
    assert developer_keys.status_code == 200
    assert unauthenticated_models.status_code == 401
    assert user_models.status_code == 403
    assert developer_models.status_code == 200
    assert list_key_calls == [False]
    assert list_option_calls == [(None, False)]


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


def test_runtime_name_availability_uses_an_exact_cloud_filter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    requests: list[Any] = []

    def list_runtimes(_self: Any, request: Any) -> SimpleNamespace:
        requests.append(request)
        requested_name = request.filters[0].values[0]
        runtimes = (
            [SimpleNamespace(name=requested_name)]
            if requested_name == "existing-runtime"
            else []
        )
        return SimpleNamespace(agent_kit_runtimes=runtimes, next_token="")

    monkeypatch.setattr(AgentkitRuntimeClient, "list_runtimes", list_runtimes)
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        developers="developer",
    )

    with TestClient(app) as client:
        existing = client.get(
            "/web/runtime-name-availability",
            params={"name": "existing-runtime", "region": "cn-beijing"},
            headers={"X-VeADK-Local-User": "developer"},
        )
        available = client.get(
            "/web/runtime-name-availability",
            params={"name": "new-runtime", "region": "cn-beijing"},
            headers={"X-VeADK-Local-User": "developer"},
        )

    assert existing.status_code == 200
    assert existing.json() == {"available": False}
    assert available.status_code == 200
    assert available.json() == {"available": True}
    assert [request.max_results for request in requests] == [1, 1]
    assert [request.filters[0].name for request in requests] == ["Name", "Name"]
    assert [request.filters[0].values for request in requests] == [
        ["existing-runtime"],
        ["new-runtime"],
    ]


def test_runtime_name_availability_rejects_invalid_names_before_cloud_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    monkeypatch.setattr(
        AgentkitRuntimeClient,
        "list_runtimes",
        lambda *_args, **_kwargs: pytest.fail("cloud API should not be called"),
    )
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        developers="developer",
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-name-availability",
            params={"name": "bad runtime", "region": "cn-beijing"},
            headers={"X-VeADK-Local-User": "developer"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Runtime 名称只能包含英文字母、数字、下划线和连字符"
    )


def test_runtime_name_availability_hides_cloud_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    def fail_list(_self: Any, _request: Any) -> None:
        raise RuntimeError("credential=test-secret")

    monkeypatch.setattr(AgentkitRuntimeClient, "list_runtimes", fail_list)
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        developers="developer",
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-name-availability",
            params={"name": "new-runtime", "region": "cn-beijing"},
            headers={"X-VeADK-Local-User": "developer"},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "暂时无法检查 Runtime 名称，请稍后重试。"
    assert "test-secret" not in response.text


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


def test_agent_usage_requires_management_role_and_runtime_ownership(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    runtimes = {
        "runtime-developer": _runtime("runtime-developer", "developer"),
        "runtime-viewer": _runtime("runtime-viewer", "viewer"),
        "runtime-other": _runtime("runtime-other", "someone-else"),
    }
    monkeypatch.setattr(
        AgentkitRuntimeClient,
        "get_runtime",
        lambda _self, request: runtimes[request.runtime_id],
    )

    class _UsageSummary:
        def model_dump(self, **_: Any) -> dict[str, Any]:
            return {
                "totalInvocations": 2,
                "totalUsers": 1,
                "users": [],
                "page": 1,
                "pageSize": 20,
            }

    class _UsageService:
        def __init__(self) -> None:
            self.queries: list[tuple[str, str]] = []

        async def get_summary(self, **kwargs: Any) -> _UsageSummary:
            self.queries.append((kwargs["runtime_id"], kwargs["app_name"]))
            return _UsageSummary()

        async def close(self) -> None:
            pass

    usage = _UsageService()
    monkeypatch.setattr(
        "frontend.server.agent_usage.create_service",
        lambda **_: usage,
    )
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        admins="admin",
        developers="developer",
    )
    params = {"region": "cn-beijing", "appName": "agent"}

    with TestClient(app) as client:
        developer_own = client.get(
            "/web/agent-usage",
            params={**params, "runtimeId": "runtime-developer"},
            headers={"X-VeADK-Local-User": "developer"},
        )
        viewer_own = client.get(
            "/web/agent-usage",
            params={**params, "runtimeId": "runtime-viewer"},
            headers={"X-VeADK-Local-User": "viewer"},
        )
        developer_other = client.get(
            "/web/agent-usage",
            params={**params, "runtimeId": "runtime-other"},
            headers={"X-VeADK-Local-User": "developer"},
        )
        admin_other = client.get(
            "/web/agent-usage",
            params={**params, "runtimeId": "runtime-other"},
            headers={"X-VeADK-Local-User": "admin"},
        )

    assert developer_own.status_code == 200
    assert viewer_own.status_code == 403
    assert developer_other.status_code == 404
    assert developer_other.json()["detail"] == "runtime_access_denied"
    assert admin_other.status_code == 200
    assert usage.queries == [
        ("runtime-developer", "agent"),
        ("runtime-other", "agent"),
    ]


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
    runtime.envs = [
        SimpleNamespace(key="MODEL_AGENT_API_KEY", value="must-not-reach-browser"),
        SimpleNamespace(key="MODEL_AGENT_API_KEY_ID", value="ark-key-id"),
        SimpleNamespace(key="MODEL_AGENT_API_KEY_NAME", value="ark-key-name"),
    ]
    legacy_runtime = _runtime_with_public_endpoint(
        _runtime("runtime-legacy", "developer", managed=False)
    )
    legacy_runtime.envs = [
        SimpleNamespace(key="MODEL_AGENT_API_KEY", value="legacy-secret"),
        SimpleNamespace(key="MODEL_AGENT_NAME", value="legacy-model"),
        SimpleNamespace(key="MODEL_AGENT_PROVIDER", value="openai"),
        SimpleNamespace(
            key="MODEL_AGENT_API_BASE",
            value="https://legacy-model.example.com/v1",
        ),
    ]
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
        if request.runtime_id == legacy_runtime.runtime_id:
            return legacy_runtime
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
        legacy = client.get(
            "/web/runtime-update-capability",
            params={
                "runtimeId": legacy_runtime.runtime_id,
                "region": "cn-beijing",
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
            "envs": [
                {"key": "MODEL_AGENT_API_KEY_ID", "value": "ark-key-id"},
                {"key": "MODEL_AGENT_API_KEY_NAME", "value": "ark-key-name"},
            ],
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
    assert legacy.status_code == 200
    legacy_envs = legacy.json()["runtime"]["envs"]
    assert legacy_envs == [
        {"key": "MODEL_AGENT_NAME", "value": "legacy-model"},
        {"key": "MODEL_AGENT_PROVIDER", "value": "openai"},
        {
            "key": "MODEL_AGENT_API_BASE",
            "value": "https://legacy-model.example.com/v1",
        },
    ]
    assert not any(
        item["key"] in {"MODEL_AGENT_API_KEY_ID", "MODEL_AGENT_API_KEY_NAME"}
        for item in legacy_envs
    )
    assert "legacy-secret" not in legacy.text
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
                if mode == "forbidden":
                    return _RuntimeJsonResponse(
                        {},
                        status_code=403,
                        text='{"detail":"Forbidden"}',
                    )
                if mode == "server-error":
                    return _RuntimeJsonResponse(
                        {},
                        status_code=500,
                        text='{"error_code":"internal_server_error"}',
                    )
                if mode == "empty":
                    return _RuntimeJsonResponse([])
                if mode == "multiple":
                    return _RuntimeJsonResponse(["selected-agent", "other-agent"])
                return _RuntimeJsonResponse(["selected-agent"])
            assert url.endswith("/web/agent-info/selected-agent")
            if mode == "agent-unsupported":
                return _RuntimeJsonResponse({}, status_code=404, text="Not Found")
            assert mode == "agent-server-error"
            return _RuntimeJsonResponse(
                {},
                status_code=500,
                text='{"error_code":"internal_server_error"}',
            )

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
        network_without_app = client.get(
            "/web/runtime-update-capability",
            params={
                "runtimeId": runtime.runtime_id,
                "region": "cn-beijing",
            },
            headers={"X-VeADK-Local-User": "developer"},
        )
        mode = "server-error"
        server_error = client.get(
            "/web/runtime-update-capability",
            params=params,
            headers={"X-VeADK-Local-User": "developer"},
        )
        server_error_without_app = client.get(
            "/web/runtime-update-capability",
            params={
                "runtimeId": runtime.runtime_id,
                "region": "cn-beijing",
            },
            headers={"X-VeADK-Local-User": "developer"},
        )
        mode = "agent-server-error"
        agent_server_error = client.get(
            "/web/runtime-update-capability",
            params=params,
            headers={"X-VeADK-Local-User": "developer"},
        )
        mode = "forbidden"
        forbidden = client.get(
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
    assert network_error.status_code == 200
    assert network_error.json()["canUpdate"] is False
    assert network_error.json()["reasonCode"] == "runtime_list_apps_unavailable"
    assert network_error.json()["agent"] == {"appName": "selected-agent"}
    assert network_without_app.status_code == 200
    assert network_without_app.json()["canUpdate"] is False
    assert network_without_app.json()["reasonCode"] == "runtime_list_apps_unavailable"
    assert network_without_app.json()["reason"] == (
        "暂时无法读取该 Runtime 的 Agent 信息，请稍后重试。"
    )
    assert "connect" not in network_without_app.json()["reason"].lower()
    assert server_error.status_code == 200
    assert server_error.json()["canUpdate"] is False
    assert server_error.json()["reasonCode"] == "runtime_list_apps_unavailable"
    assert server_error.json()["agent"] == {"appName": "selected-agent"}
    assert server_error_without_app.status_code == 200
    assert server_error_without_app.json()["canUpdate"] is False
    assert server_error_without_app.json()["reasonCode"] == (
        "runtime_list_apps_unavailable"
    )
    assert "internal_server_error" not in server_error_without_app.json()["reason"]
    assert agent_server_error.status_code == 200
    assert agent_server_error.json()["canUpdate"] is False
    assert agent_server_error.json()["reasonCode"] == "runtime_agent_info_unavailable"
    assert agent_server_error.json()["reason"] == (
        "暂时无法读取该 Runtime 的 Agent 配置，请稍后重试。"
    )
    assert agent_server_error.json()["agent"] == {"appName": "selected-agent"}
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "runtime_update_capability_failed"
    assert "Forbidden" not in forbidden.text


@pytest.mark.parametrize(
    "evaluation_error",
    [None, "evaluation workspace unavailable"],
)
@pytest.mark.parametrize("has_resource_tags", [False, True])
@pytest.mark.parametrize(
    ("provider", "region"),
    [("volcengine", "cn-beijing"), ("byteplus", "ap-southeast-1")],
)
def test_update_deployment_reuses_owned_runtime_and_returns_new_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    evaluation_error: str | None,
    has_resource_tags: bool,
    provider: str,
    region: str,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    from frontend.server.deployment_resources import deployment_resource_tags

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
    tagged_resources = {
        "tos": {"mode": "create", "bucket": "tagged-bucket"},
        "cr": {
            "mode": "create",
            "instance": "tagged-registry",
            "namespace": "tagged-namespace",
            "repository": "tagged-repository",
        },
        "codePipeline": {
            "mode": "create",
            "workspaceName": "tagged-workspace",
            "pipelineName": "tagged-pipeline",
        },
    }
    if has_resource_tags:
        runtime.tags.extend(
            SimpleNamespace(key=key, value=value)
            for key, value in deployment_resource_tags(tagged_resources).items()
        )
    runtime.envs = [
        SimpleNamespace(
            key="MCP_UPDATED_AGENT_ORDERS_AUTH_TOKEN",
            value="preserved-secret",
        ),
        SimpleNamespace(key="REPLACED_ENV", value="old-value"),
        SimpleNamespace(key="MODEL_AGENT_API_KEY", value="old-raw-model-key"),
        SimpleNamespace(key="MODEL_AGENT_API_KEY_ID", value="old-key-id"),
        SimpleNamespace(key="MODEL_AGENT_API_KEY_NAME", value="old-key-name"),
        SimpleNamespace(key="VEADK_DISABLE_EXPIRE_AT", value="true"),
    ]
    captured_config: dict[str, Any] = {}
    get_calls = 0
    evaluation_set_calls: list[dict[str, Any]] = []
    resolved_model_keys: list[dict[str, Any]] = []

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
                    "runtime_name": "sdk-renamed-runtime",
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

    def resolve_model_key(**kwargs: Any) -> str:
        resolved_model_keys.append(kwargs)
        return "new-raw-model-key"

    monkeypatch.setattr(
        "veadk.auth.veauth.ark_veauth.get_ark_token",
        resolve_model_key,
    )

    async def initialize_evaluation_sets(**kwargs: Any) -> list[str]:
        evaluation_set_calls.append(kwargs)
        if evaluation_error:
            raise RuntimeError(evaluation_error)
        return ["updated-agent_good_case", "updated-agent_bad_case"]

    monkeypatch.setattr(
        "frontend.server.evaluation_automation.datasets.ensure_feedback_sets",
        initialize_evaluation_sets,
    )
    if provider == "byteplus":
        monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "test-ak")
        monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "test-sk")
        monkeypatch.setenv("MODEL_AGENT_API_KEY", "test-model-key")
        monkeypatch.setattr(
            "agentkit.utils.template_utils.render_template",
            lambda _template: "agentkit-platform-account",
        )
    app = _create_studio_app(
        monkeypatch,
        tmp_path,
        admins="admin",
        developers="developer",
        provider=provider,
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
                "config": {"region": region, "projectName": "default"},
                "authentication": {"type": "api_key"},
                "envs": [
                    {"key": "REPLACED_ENV", "value": "new-value"},
                    {"key": "MODEL_AGENT_API_KEY_ID", "value": "new-key-id"},
                    {
                        "key": "MODEL_AGENT_API_KEY_NAME",
                        "value": "new-key-name",
                    },
                ],
                "resources": {
                    "tos": {"mode": "create", "bucket": "request-bucket"},
                    "cr": {
                        "mode": "create",
                        "instance": "request-registry",
                        "namespace": "request-namespace",
                        "repository": "request-repository",
                    },
                    "codePipeline": {
                        "mode": "create",
                        "workspaceName": "request-workspace",
                        "pipelineName": "request-pipeline",
                    },
                },
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
    assert frames[-1]["agentName"] == "updated-agent"
    assert frames[-1]["runtimeName"] == runtime.name
    assert frames[-1]["version"] == 4
    evaluation_frames = [
        frame for frame in frames if frame.get("phase") == "evaluation"
    ]
    if provider == "byteplus":
        assert evaluation_frames == []
        assert "warnings" not in frames[-1]
        assert evaluation_set_calls == []
    else:
        assert evaluation_frames[0]["message"] == (
            "正在创建 Good Case 和 Bad Case 评测集"
        )
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
            "region": region,
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
    assert cloud["runtime_envs"]["MODEL_AGENT_API_KEY_ID"] == "new-key-id"
    assert cloud["runtime_envs"]["MODEL_AGENT_API_KEY_NAME"] == "new-key-name"
    assert cloud["runtime_envs"]["MODEL_AGENT_API_KEY"] == "new-raw-model-key"
    assert "old-key-name" not in cloud["runtime_envs"].values()
    assert "old-key-id" not in cloud["runtime_envs"].values()
    assert "old-raw-model-key" not in cloud["runtime_envs"].values()
    assert len(resolved_model_keys) == 1
    assert resolved_model_keys[0]["api_key_id"] == "new-key-id"
    assert resolved_model_keys[0]["api_key_name"] == "new-key-name"
    assert resolved_model_keys[0]["cloud_provider"] == provider
    assert "VEADK_DISABLE_EXPIRE_AT" not in cloud["runtime_envs"]
    assert "runtime_network" not in cloud
    if has_resource_tags:
        assert cloud["tos_bucket"] == "tagged-bucket"
        assert cloud["cr_instance_name"] == "tagged-registry"
        assert cloud["cr_namespace_name"] == "tagged-namespace"
        assert cloud["cr_repo_name"] == "tagged-repository"
        assert cloud["cp_workspace_name"] == "tagged-workspace"
        assert cloud["cp_pipeline_name"] == "tagged-pipeline"
    else:
        if provider == "byteplus":
            assert cloud["tos_bucket"] == ("agentkit-platform-account-ap-southeast-1")
            assert cloud["cr_instance_name"] == "agentkit-platform-account"
        else:
            assert "tos_bucket" not in cloud
            assert "cr_instance_name" not in cloud
        assert "cr_namespace_name" not in cloud
        assert "cr_repo_name" not in cloud
        assert "cp_workspace_name" not in cloud
        assert "cp_pipeline_name" not in cloud
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
                    "runtime_name": "generated-runtime-name",
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
                "runtimeName": "stable-runtime-name",
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
    assert frames[-1]["agentName"] == "demo-agent"
    assert frames[-1]["runtimeName"] == "generated-runtime-name"
    assert captured_config["launch_types"]["cloud"]["runtime_name"] == (
        "stable-runtime-name"
    )
    assert create_requests[0].apmplus_enable is True
    assert {
        item.key: item.value
        for item in create_requests[0].tags
        if item.key.startswith("veadk:build-resource:")
    } == {
        "veadk:build-resource:tos-mode": "auto",
        "veadk:build-resource:cr-mode": "auto",
        "veadk:build-resource:cp-mode": "auto",
    }
    assert captured_config["launch_types"]["cloud"]["runtime_auth_type"] == ("key_auth")
    runtime_envs = captured_config["launch_types"]["cloud"]["runtime_envs"]
    assert "VEADK_DISABLE_EXPIRE_AT" not in runtime_envs
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


def test_deployment_rejects_internal_runtime_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_studio_app(monkeypatch, tmp_path, developers="developer")

    with TestClient(app) as client:
        response = client.post(
            "/web/deploy-agentkit",
            headers={"X-VeADK-Local-User": "developer"},
            json={
                "name": "demo-agent",
                "files": [{"path": "app.py", "content": "app = object()\n"}],
                "config": {"region": "cn-beijing", "projectName": "default"},
                "envs": [
                    {"key": "VEADK_DISABLE_EXPIRE_AT", "value": "true"},
                ],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Reserved runtime environment variable: VEADK_DISABLE_EXPIRE_AT"
    )


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


def test_deployment_maps_create_runtime_duplicate_name_to_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def launch(**_kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            success=False,
            error=(
                "Failed to CreateRuntime: "
                "InvalidParameter.DuplicateName: name already exists"
            ),
            deploy_result=None,
            build_result=None,
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
                "runtimeName": "demo-agent-a1b2c3",
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
    assert frames[-1]["error"] == (
        "Runtime 名称“demo-agent-a1b2c3”已存在，请修改名称后重新部署。"
    )


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
