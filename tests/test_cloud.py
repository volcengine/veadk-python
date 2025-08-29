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

os.environ["VOLCENGINE_ACCESS_KEY"] = "test_access_key"
os.environ["VOLCENGINE_SECRET_KEY"] = "test_secret_key"

from veadk.cloud.cloud_agent_engine import CloudAgentEngine


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

                # Test CloudAgentEngine creation and deploy functionality
                engine = CloudAgentEngine()

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
                            cloud_app.delete_self()
                            mock_vefaas_client.delete.assert_called_with("app-123")

                # Verify all mocks were called as expected
                mock_vefaas_service.deploy.assert_called_once()
                mock_vefaas_service._update_function_code.assert_called_once()
