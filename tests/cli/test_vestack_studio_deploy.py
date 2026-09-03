from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from veadk.cli import vestack_studio_deploy
from veadk.cli.cli_frontend import studio


@pytest.mark.parametrize(
    ("omitted_options", "expected_error"),
    [
        ({"--public-domain"}, "--public-domain is required"),
        ({"--vestack-openapi-url"}, "--vestack-openapi-url must include"),
        ({"--image"}, "--image is required"),
        ({"--vestack-agentkit-region"}, "--vestack-agentkit-region is required"),
        ({"--vestack-apig-cluster-id"}, "--vestack-apig-cluster-id is required"),
    ],
)
def test_vestack_cli_requires_custom_endpoint_options(
    omitted_options: set[str],
    expected_error: str,
) -> None:
    options = [
        ("--deploy-target", "vestack"),
        ("--provider", "volcengine"),
        ("--image", "registry.example.com/studio:v1"),
        ("--vefaas-app-name", "veadk-studio"),
        ("--public-domain", "studio.example.com"),
        ("--vestack-openapi-url", "https://openapi.example.com"),
        ("--vestack-agentkit-region", "region-a"),
        ("--vestack-apig-cluster-id", "cluster-1"),
        ("--volcengine-access-key", "ak"),
        ("--volcengine-secret-key", "sk"),
    ]
    arguments = [
        value
        for option, value in options
        if option not in omitted_options
        for value in (option, value)
    ]

    result = CliRunner().invoke(studio, ["deploy", *arguments])

    assert result.exit_code == 1
    assert expected_error in result.output


def test_vestack_deploy_requires_image_and_domain() -> None:
    common = {
        "access_key": "ak",
        "secret_key": "sk",
        "session_token": "",
        "region": "e70",
        "project": "default",
        "application_name": "veadk-studio",
        "role_trn": "trn:iam::1:role/studio",
        "public_domain": "studio.example.com",
    }

    with pytest.raises(ValueError, match="image"):
        vestack_studio_deploy.deploy_vestack_studio_image(image="", **common)
    with pytest.raises(ValueError, match="domain"):
        vestack_studio_deploy.deploy_vestack_studio_image(
            image="registry.example.com/studio:v1",
            **{**common, "public_domain": ""},
        )


def test_vestack_deploy_reuses_named_resources_and_does_not_inject_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setenv("IAM_ROLE", "original-role")
    function = SimpleNamespace(id="fn-1", name="veadk-studio-fn")
    function_service = MagicMock()
    function_service.client.list_functions.return_value = SimpleNamespace(
        items=[function]
    )
    function_service.client.get_function.return_value = SimpleNamespace(
        envs=[
            SimpleNamespace(key="OAUTH2_CLIENT_SECRET", value="existing-secret"),
            SimpleNamespace(key="VOLCENGINE_ACCESS_KEY", value="must-be-removed"),
        ]
    )
    monkeypatch.setattr(vestack_studio_deploy, "VeFaaS", lambda **_: function_service)
    monkeypatch.setattr(
        vestack_studio_deploy, "_wait_for_function_release", MagicMock()
    )

    apig = MagicMock()
    apig.list_gateways.return_value = SimpleNamespace(
        items=[SimpleNamespace(id="gw-1", name="veadk-studio-gateway")]
    )
    apig.find_gateway_service.return_value = SimpleNamespace(id="svc-1")
    apig.find_upstream.return_value = SimpleNamespace(id="up-1")
    apig.find_route.return_value = SimpleNamespace(id="route-1")
    apig.get_gateway_external_http_address.return_value = ("192.0.2.10", 32978)
    monkeypatch.setattr(vestack_studio_deploy, "APIGateway", lambda *_, **__: apig)

    environment = {
        "VOLCENGINE_AGENTKIT_HOST": "ops-top.ops-top.svc:8000",
        "VOLCENGINE_SECRET_KEY": "must-not-be-deployed",
    }
    result = vestack_studio_deploy.deploy_vestack_studio_image(
        access_key="deployer-ak",
        secret_key="deployer-sk",
        session_token="",
        region="e70",
        project="default",
        application_name="veadk-studio",
        image="registry.example.com/studio:v1",
        role_trn="trn:iam::1:role/studio",
        public_domain="studio.example.com",
        apig_cluster_id="cluster-1",
        apig_namespace="veadk-studio-apig",
        environment=environment,
    )

    assert result.endpoint == "http://studio.example.com:32978"
    assert result.function_id == "fn-1"
    function_service.update_function_envs_and_release.assert_called_once_with(
        "fn-1",
        {"OAUTH2_REDIRECT_URI": "http://studio.example.com:32978/oauth2/callback"},
    )
    update_request = function_service.client.update_function.call_args.args[0]
    deployed_env = {item.key: item.value for item in update_request.envs}
    assert deployed_env == {
        "OAUTH2_CLIENT_SECRET": "existing-secret",
        "VOLCENGINE_AGENTKIT_HOST": "ops-top.ops-top.svc:8000",
    }
    assert "VOLCENGINE_ACCESS_KEY" not in deployed_env
    assert "VOLCENGINE_SECRET_KEY" not in deployed_env
    assert vestack_studio_deploy.os.environ["IAM_ROLE"] == "original-role"
    apig.create_serverless_gateway.assert_not_called()
    apig.create_gateway_service.assert_not_called()
    apig.create_vefaas_upstream.assert_not_called()
    apig.create_gateway_service_routes.assert_not_called()


def test_wait_for_function_release_handles_success_failure_and_timeout(
    monkeypatch,
) -> None:
    service = SimpleNamespace(client=MagicMock())
    service.client.get_release_status.side_effect = [
        SimpleNamespace(status="Building"),
        SimpleNamespace(status="Succeeded"),
    ]
    monkeypatch.setattr(vestack_studio_deploy.time, "sleep", MagicMock())

    vestack_studio_deploy._wait_for_function_release(
        service,
        "fn-1",
        attempts=2,
        interval_seconds=0,
    )

    service.client.get_release_status.side_effect = None
    service.client.get_release_status.return_value = SimpleNamespace(status="Failed")
    with pytest.raises(RuntimeError, match="release failed"):
        vestack_studio_deploy._wait_for_function_release(
            service,
            "fn-1",
            attempts=1,
            interval_seconds=0,
        )

    service.client.get_release_status.return_value = SimpleNamespace(status="Building")
    with pytest.raises(TimeoutError, match="did not complete"):
        vestack_studio_deploy._wait_for_function_release(
            service,
            "fn-1",
            attempts=1,
            interval_seconds=0,
        )


@pytest.mark.parametrize(
    ("port_args", "expected_codex_port", "expected_hermes_port"),
    [
        ((), "8642", "4500"),
        (
            (
                "--vestack-codex-port",
                "18642",
                "--vestack-hermes-port",
                "14500",
                "--iam-role",
                "trn:iam::1:role/existing-studio",
                "--vestack-insecure-skip-tls-verify",
                "--client-secret",
                "test-client-secret",
                "--site-title",
                "Test Studio",
                "--admin",
                "admin@example.com",
                "--developer",
                "developer@example.com",
            ),
            "18642",
            "14500",
        ),
    ],
)
def test_vestack_cli_configures_independent_hermes_tools(
    monkeypatch,
    port_args: tuple[str, ...],
    expected_codex_port: str,
    expected_hermes_port: str,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "veadk.cli.cli_frontend._resolve_or_create_studio_identity_resources",
        lambda **_: ("pool-1", "auth.example.com", "client-1"),
    )

    def fake_deploy(**kwargs):
        captured.update(kwargs)
        return vestack_studio_deploy.VeStackStudioDeployment(
            endpoint="http://studio.example.com:32978",
            function_id="fn-1",
            gateway_id="gw-1",
            service_id="svc-1",
            upstream_id="up-1",
            route_id="route-1",
        )

    monkeypatch.setattr(
        "veadk.cli.vestack_studio_deploy.deploy_vestack_studio_image", fake_deploy
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_deploy_iam_vestack.ensure_frontend_role_vestack",
        lambda *_args, **_kwargs: "trn:iam::1:role/studio",
    )
    monkeypatch.setattr(
        "veadk.integrations.ve_identity.identity_client.IdentityClient.register_callback_for_user_pool_client",
        lambda *_args, **_kwargs: None,
    )

    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--deploy-target",
            "vestack",
            "--provider",
            "volcengine",
            "--image",
            "registry.example.com/studio:v1",
            "--vefaas-app-name",
            "veadk-studio",
            "--public-domain",
            "studio.example.com",
            "--vestack-openapi-url",
            "https://openapi.example.com",
            "--vestack-agentkit-region",
            "e70",
            "--vestack-apig-cluster-id",
            "cluster-1",
            "--user-pool-id",
            "pool-1",
            "--allowed-client-id",
            "client-1",
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
            "--vestack-hermes-model-agent-name",
            "ep-deepseek-test",
            "--vestack-hermes-model-api-base",
            "http://modelcenter.example:6789",
            "--vestack-hermes-model-api-key",
            "test-model-key",
            "--vestack-hermes-model-id",
            "ep-deepseek-test",
            *port_args,
        ],
    )

    assert result.exit_code == 0, result.output
    environment = captured["environment"]
    assert isinstance(environment, dict)
    assert environment["VOLCENGINE_REGION"] == "e70"
    assert environment["AGENTKIT_SANDBOX_REGION"] == "e70"
    assert environment["VEADK_STUDIO_DEPLOY_TARGET"] == "vestack"
    assert environment["VEADK_STUDIO_HERMES_TOOL_PER_AGENT"] == "true"
    assert environment["VEADK_STUDIO_HERMES_MODEL_AGENT_NAME"] == "ep-deepseek-test"
    assert environment["VEADK_STUDIO_HERMES_MODEL_API_BASE"] == (
        "http://modelcenter.example:6789"
    )
    assert environment["VEADK_STUDIO_HERMES_MODEL_API_KEY"] == "test-model-key"
    assert environment["VEADK_STUDIO_HERMES_MODEL_ID"] == "ep-deepseek-test"
    expected_role_name = "existing-studio" if "--iam-role" in port_args else "studio"
    assert environment["VEADK_STUDIO_HERMES_ROLE_NAME"] == expected_role_name
    assert environment["VEADK_STUDIO_CODEX_TOOL_PER_AGENT"] == "true"
    assert environment["VEADK_STUDIO_CODEX_ROLE_NAME"] == expected_role_name
    assert environment["VEADK_STUDIO_CODEX_PORT"] == expected_codex_port
    assert environment["VEADK_STUDIO_HERMES_PORT"] == expected_hermes_port
    assert environment["SANDBOX_CHAT_HERMES"] == ""
    assert environment["SANDBOX_CHAT_HERMES_SNAPSHOT"] == ""


def test_vestack_cli_rejects_byteplus_provider() -> None:
    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--deploy-target",
            "vestack",
            "--provider",
            "byteplus",
            "--image",
            "registry.example.com/studio:v1",
            "--vefaas-app-name",
            "veadk-studio",
            "--public-domain",
            "studio.example.com",
            "--vestack-openapi-url",
            "https://openapi.example.com",
            "--vestack-agentkit-region",
            "region-a",
            "--vestack-apig-cluster-id",
            "cluster-1",
            "--byteplus-access-key",
            "ak",
            "--byteplus-secret-key",
            "sk",
        ],
    )

    assert result.exit_code == 1
    assert "requires --provider volcengine" in result.output


def test_vestack_cli_validates_complete_hermes_model_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._resolve_or_create_studio_identity_resources",
        lambda **_: ("pool-1", "auth.example.com", "client-1"),
    )
    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--deploy-target",
            "vestack",
            "--provider",
            "volcengine",
            "--image",
            "registry.example.com/studio:v1",
            "--vefaas-app-name",
            "veadk-studio",
            "--public-domain",
            "studio.example.com",
            "--vestack-openapi-url",
            "https://openapi.example.com",
            "--vestack-agentkit-region",
            "region-a",
            "--vestack-apig-cluster-id",
            "cluster-1",
            "--user-pool-id",
            "pool-1",
            "--allowed-client-id",
            "client-1",
            "--iam-role",
            "trn:iam::1:role/studio",
            "--volcengine-access-key",
            "ak",
            "--volcengine-secret-key",
            "sk",
            "--vestack-hermes-model-agent-name",
            "model-agent",
        ],
    )

    assert result.exit_code == 1
    assert "require complete model environment" in result.output
