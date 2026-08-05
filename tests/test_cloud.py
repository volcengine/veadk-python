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

import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest
import requests

os.environ["VOLCENGINE_ACCESS_KEY"] = "test_access_key"
os.environ["VOLCENGINE_SECRET_KEY"] = "test_secret_key"

from veadk.cloud.cloud_agent_engine import CloudAgentEngine
from veadk.integrations.ve_apig.ve_apig import APIGateway
from veadk.integrations.ve_code_pipeline.ve_code_pipeline import VeCodePipeline
from veadk.integrations.ve_faas.ve_faas import VeFaaS
from veadk.utils.cloud_provider import cp_openapi_host


def test_vefaas_create_function_uses_configured_project() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        project_name="studio-project",
    )
    service.client = Mock()
    service.client.create_function.return_value = Mock(
        id="function-id", project_name="studio-project"
    )
    service._upload_and_mount_code = Mock()

    service._create_function("studio-function", ".")

    request = service.client.create_function.call_args.args[0]
    assert request.project_name == "studio-project"


def test_vefaas_deploy_cleans_created_resources_on_release_failure() -> None:
    service = object.__new__(VeFaaS)
    service._create_function = Mock(return_value=("studio-app-fn", "function-id"))
    service._create_application = Mock(return_value="application-id")
    service._release_application = Mock(side_effect=RuntimeError("release failed"))
    service.delete = Mock()
    service.delete_function = Mock()

    with pytest.raises(RuntimeError, match="release failed"):
        service.deploy(
            "studio-app",
            ".",
            gateway_name="gateway",
            gateway_service_name="service",
            gateway_upstream_name="upstream",
        )

    service.delete.assert_called_once_with("application-id")
    service.delete_function.assert_called_once_with("function-id")


def test_vefaas_deploy_can_keep_failed_resources_for_inspection() -> None:
    service = object.__new__(VeFaaS)
    service._create_function = Mock(return_value=("studio-app-fn", "function-id"))
    service._create_application = Mock(return_value="application-id")
    service._release_application = Mock(side_effect=RuntimeError("release failed"))
    service.delete = Mock()
    service.delete_function = Mock()

    with pytest.raises(RuntimeError, match="release failed"):
        service.deploy(
            "studio-app",
            ".",
            gateway_name="gateway",
            gateway_service_name="service",
            gateway_upstream_name="upstream",
            keep_failed_deploy=True,
        )

    service.delete.assert_not_called()
    service.delete_function.assert_not_called()


def test_apig_uses_session_token() -> None:
    gateway = APIGateway(
        access_key="test_access_key",
        secret_key="test_secret_key",
        session_token="test_session_token",
    )

    assert gateway.session_token == "test_session_token"
    assert gateway.api_client.configuration.session_token == "test_session_token"


def test_vefaas_passes_session_token_to_apig() -> None:
    with patch("veadk.integrations.ve_faas.ve_faas.APIGateway") as apig:
        VeFaaS(
            access_key="test_access_key",
            secret_key="test_secret_key",
            session_token="test_session_token",
            region="cn-shanghai",
        )

    apig.assert_called_once_with(
        "test_access_key",
        "test_secret_key",
        "cn-shanghai",
        session_token="test_session_token",
        provider="volcengine",
    )


def test_vefaas_code_upload_failure_logs_safe_diagnostics() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="cn-beijing",
    )
    service.client = Mock()
    service.client.get_code_upload_address.return_value = Mock(
        upload_address="https://uploads.example.com/path?signature=top-secret"
    )

    with (
        patch(
            "veadk.integrations.ve_faas.ve_faas.zip_and_encode_folder",
            return_value=(b"archive", 7, None),
        ),
        patch(
            "veadk.integrations.ve_faas.ve_faas.requests.put",
            side_effect=requests.ConnectionError("signed URL must stay private"),
        ),
        patch("veadk.integrations.ve_faas.ve_faas.logger.error") as log_error,
    ):
        with pytest.raises(ValueError, match="ConnectionError.*uploads.example.com"):
            service._upload_and_mount_code("function-id", ".")

    logged = " ".join(
        str(value) for call in log_error.call_args_list for value in call.args
    )
    assert "ConnectionError" in logged
    assert "uploads.example.com" in logged
    assert "top-secret" not in logged
    assert "signed URL must stay private" not in logged


def test_vefaas_code_upload_callback_uses_configured_region() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="cn-shanghai",
    )
    service.client = Mock()
    service.client.get_code_upload_address.return_value = Mock(
        upload_address="https://example.com/upload"
    )

    with (
        patch(
            "veadk.integrations.ve_faas.ve_faas.zip_and_encode_folder",
            return_value=(b"archive", 7, None),
        ),
        patch("veadk.integrations.ve_faas.ve_faas.requests.put") as upload,
        patch("veadk.integrations.ve_faas.ve_faas.signed_request") as callback,
    ):
        upload.return_value = Mock(status_code=200)
        service._upload_and_mount_code("function-id", ".")

    upload.assert_called_once_with(
        url="https://example.com/upload",
        data=b"archive",
        headers={"Content-Type": "application/zip"},
        timeout=(30, 300),
    )
    callback.assert_called_once_with(
        ak="test_access_key",
        sk="test_secret_key",
        target="CodeUploadCallback",
        body={"FunctionId": "function-id"},
        region="cn-shanghai",
        session_token="",
        host="open.volcengineapi.com",
    )


def test_vefaas_code_upload_callback_uses_byteplus_host() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="ap-southeast-1",
        provider="byteplus",
    )
    service.client = Mock()
    service.client.get_code_upload_address.return_value = Mock(
        upload_address="https://example.com/upload"
    )

    with (
        patch(
            "veadk.integrations.ve_faas.ve_faas.zip_and_encode_folder",
            return_value=(b"archive", 7, None),
        ),
        patch("veadk.integrations.ve_faas.ve_faas.requests.put") as upload,
        patch("veadk.integrations.ve_faas.ve_faas.signed_request") as callback,
    ):
        upload.return_value = Mock(status_code=200)
        service._upload_and_mount_code("function-id", ".")

    callback.assert_called_once_with(
        ak="test_access_key",
        sk="test_secret_key",
        target="CodeUploadCallback",
        body={"FunctionId": "function-id"},
        region="ap-southeast-1",
        session_token="",
        host="vefaas.ap-southeast-1.byteplusapi.com",
    )


def test_vefaas_byteplus_application_uses_configured_template() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="ap-southeast-1",
        provider="byteplus",
        application_template_id="byteplus-template-id",
    )

    with patch("veadk.integrations.ve_faas.ve_faas.ve_request") as request:
        request.return_value = {"Result": {"Status": "create_success", "Id": "app-id"}}

        app_id = service._create_application(
            "studio-app",
            "studio-function",
            "gateway",
            "upstream",
            "service",
        )

    assert app_id == "app-id"
    request_body = request.call_args.kwargs["request_body"]
    assert request_body["TemplateId"] == "byteplus-template-id"
    assert request_body["Config"]["Region"] == "ap-southeast-1"
    assert request_body["Config"]["EnableMcpSession"] is True


def test_vefaas_application_can_disable_mcp_session() -> None:
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="ap-southeast-1",
        provider="byteplus",
        application_template_id="byteplus-template-id",
    )

    with patch("veadk.integrations.ve_faas.ve_faas.ve_request") as request:
        request.return_value = {"Result": {"Status": "create_success", "Id": "app-id"}}

        service._create_application(
            "studio-app",
            "studio-function",
            "gateway",
            "upstream",
            "service",
            enable_mcp_session=False,
        )

    request_body = request.call_args.kwargs["request_body"]
    assert request_body["Config"]["EnableMcpSession"] is False


def test_vefaas_byteplus_application_uses_builtin_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VEFAAS_APPLICATION_TEMPLATE_ID", raising=False)
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="ap-southeast-1",
        provider="byteplus",
    )

    with patch("veadk.integrations.ve_faas.ve_faas.ve_request") as request:
        request.return_value = {"Result": {"Status": "create_success", "Id": "app-id"}}

        app_id = service._create_application(
            "studio-app",
            "studio-function",
            "gateway",
            "upstream",
            "service",
        )

    assert app_id == "app-id"
    request_body = request.call_args.kwargs["request_body"]
    assert request_body["TemplateId"] == "697a03b8adb54b0008fdebd0"


def test_vefaas_byteplus_application_requires_template_for_unknown_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VEFAAS_APPLICATION_TEMPLATE_ID", raising=False)
    service = VeFaaS(
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="ap-southeast-2",
        provider="byteplus",
    )

    with (
        patch("veadk.integrations.ve_faas.ve_faas.ve_request") as request,
        pytest.raises(ValueError, match="No built-in TemplateId"),
    ):
        service._create_application(
            "studio-app",
            "studio-function",
            "gateway",
            "upstream",
            "service",
        )

    request.assert_not_called()


def test_cloud_agent_engine_passes_application_template() -> None:
    with (
        patch("veadk.cloud.cloud_agent_engine.VeFaaS") as vefaas_class,
        patch("veadk.cloud.cloud_agent_engine.APIGateway"),
        patch("veadk.cloud.cloud_agent_engine.IdentityClient"),
    ):
        CloudAgentEngine(
            volcengine_access_key="test_access_key",
            volcengine_secret_key="test_secret_key",
            region="ap-southeast-1",
            provider="byteplus",
            vefaas_application_template_id="byteplus-template-id",
        )

    assert (
        vefaas_class.call_args.kwargs["application_template_id"]
        == "byteplus-template-id"
    )


def test_code_pipeline_uses_byteplus_region_host() -> None:
    service = VeCodePipeline(
        volcengine_access_key="test_access_key",
        volcengine_secret_key="test_secret_key",
        provider="byteplus",
    )

    assert service.region == "ap-southeast-1"
    assert service.host == "cp.ap-southeast-1.byteplusapi.com"
    assert cp_openapi_host("ap-southeast-1", "byteplus") == service.host


@pytest.mark.asyncio
async def test_cloud():
    app_name = "test-app"
    key = "CloudTestIdentifier123"
    test_endpoint = "https://test-endpoint.volcengine.com"
    test_message = "Hello cloud agent"

    # Create temporary directory with required agent.py file for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        with open(os.path.join(temp_dir, "agent.py"), "w") as f:
            f.write(f"# Test agent implementation with {key}")

        # Mock shutil.copy to avoid template file copying issues
        with patch("shutil.copy"):
            with patch("veadk.cloud.cloud_agent_engine.VeFaaS") as mock_vefaas_class:
                # Setup mock VeFaaS service for all operations
                mock_vefaas_service = Mock()
                mock_vefaas_class.return_value = mock_vefaas_service

                # Mock deploy operation
                mock_vefaas_service.deploy.return_value = (
                    test_endpoint,
                    "app-123",
                    "func-456",
                )

                # Mock update operation
                mock_vefaas_service._update_function_code.return_value = (
                    test_endpoint,
                    "app-123",
                    "func-456",
                )

                # Mock remove operation
                mock_vefaas_service.find_app_id_by_name.return_value = "app-123"
                mock_vefaas_service.delete.return_value = None

                mock_vefaas_service.get_application_route.return_value = (
                    "gw-123",
                    "svc-456",
                    "route-789",
                )

                # Test CloudAgentEngine creation and deploy functionality
                engine = CloudAgentEngine(
                    project="studio-project",
                    volcengine_access_key="test_access_key",
                    volcengine_secret_key="test_secret_key",
                    volcengine_session_token="test_session_token",
                )
                mock_vefaas_class.assert_called_once_with(
                    access_key="test_access_key",
                    secret_key="test_secret_key",
                    session_token="test_session_token",
                    region="cn-beijing",
                    project_name="studio-project",
                    provider="volcengine",
                    application_template_id="",
                )

                # Test deploy operation
                cloud_app = engine.deploy(application_name=app_name, path=temp_dir)

                # Verify deployment result contains expected values
                assert cloud_app.vefaas_application_name == app_name
                assert cloud_app.vefaas_endpoint == test_endpoint
                assert cloud_app.vefaas_application_id == "app-123"

                # Test update_function_code operation
                updated_app = engine.update_function_code(
                    application_name=app_name, path=temp_dir
                )

                # Verify update result maintains same endpoint
                assert updated_app.vefaas_endpoint == test_endpoint

                # Test remove operation with mocked user input
                with patch("builtins.input", return_value="y"):
                    engine.remove(app_name)
                    mock_vefaas_service.find_app_id_by_name.assert_called_with(app_name)
                    mock_vefaas_service.delete.assert_called_with("app-123")

                # Test CloudApp message_send functionality
                mock_response = Mock()
                mock_message = Mock()
                mock_response.root.result = mock_message

                with patch.object(cloud_app, "_get_a2a_client") as mock_get_client:
                    mock_client = AsyncMock()
                    mock_client.send_message = AsyncMock(return_value=mock_response)
                    mock_get_client.return_value = mock_client

                    # Test message sending to cloud agent
                    result = await cloud_app.message_send(
                        message=test_message,
                        session_id="session-123",
                        user_id="user-456",
                    )

                    # Verify message sending result
                    assert result == mock_message
                    mock_client.send_message.assert_called_once()

                # Test CloudApp delete_self functionality
                with patch("builtins.input", return_value="y"):
                    with patch(
                        "veadk.integrations.ve_faas.ve_faas.VeFaaS"
                    ) as mock_vefaas_in_app:
                        mock_vefaas_client = Mock()
                        mock_vefaas_in_app.return_value = mock_vefaas_client
                        mock_vefaas_client.delete.return_value = None
                        with patch.object(
                            cloud_app, "_get_vefaas_application_id_by_name"
                        ) as mock_get_id_by_name:
                            mock_get_id_by_name.return_value = None
                            cloud_app.delete_self(
                                volcengine_ak="test_access_key",
                                volcengine_sk="test_secret_key",
                            )
                            mock_vefaas_client.delete.assert_called_with("app-123")

                # Verify all mocks were called as expected
                mock_vefaas_service.deploy.assert_called_once()
                mock_vefaas_service._update_function_code.assert_called_once()
