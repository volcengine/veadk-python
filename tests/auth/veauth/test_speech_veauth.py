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

import pytest
from unittest.mock import patch, MagicMock
from veadk.auth.veauth.speech_veauth import get_speech_token


# Test cases


def test_get_speech_token_with_env_vars(monkeypatch):
    """Test when credentials are available in environment variables"""
    # Setup
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "test_access_key")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "test_secret_key")

    mock_response = {"Result": {"APIKeys": [{"APIKey": "test_api_key"}]}}

    with patch("veadk.auth.veauth.speech_veauth.ve_request") as mock_ve_request:
        mock_ve_request.return_value = mock_response

        # Execute
        result = get_speech_token()

        # Verify
        assert result == "test_api_key"
        mock_ve_request.assert_called_once_with(
            request_body={
                "ProjectName": "default",
                "OnlyAvailable": True,
                "Filter": {},
            },
            header={"X-Security-Token": ""},
            action="ListApiKeys",
            ak="test_access_key",
            sk="test_secret_key",
            service="speech_saas_prod",
            version="2025-05-20",
            region="cn-beijing",
            host="open.volcengineapi.com",
        )


def test_get_speech_token_with_vefaas_iam(monkeypatch):
    """Test when credentials are obtained from vefaas iam"""
    # Setup
    monkeypatch.delenv("VOLCENGINE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_SECRET_KEY", raising=False)

    mock_cred = MagicMock()
    mock_cred.access_key_id = "vefaas_access_key"
    mock_cred.secret_access_key = "vefaas_secret_key"
    mock_cred.session_token = "vefaas_session_token"

    mock_response = {"Result": {"APIKeys": [{"APIKey": "vefaas_api_key"}]}}

    with (
        patch(
            "veadk.auth.veauth.speech_veauth.get_credential_from_vefaas_iam"
        ) as mock_get_cred,
        patch("veadk.auth.veauth.speech_veauth.ve_request") as mock_ve_request,
    ):
        mock_get_cred.return_value = mock_cred
        mock_ve_request.return_value = mock_response

        # Execute
        result = get_speech_token(region="cn-shanghai")

        # Verify
        assert result == "vefaas_api_key"
        mock_get_cred.assert_called_once()
        mock_ve_request.assert_called_once_with(
            request_body={
                "ProjectName": "default",
                "OnlyAvailable": True,
                "Filter": {},
            },
            header={"X-Security-Token": "vefaas_session_token"},
            action="ListApiKeys",
            ak="vefaas_access_key",
            sk="vefaas_secret_key",
            service="speech_saas_prod",
            version="2025-05-20",
            region="cn-shanghai",
            host="open.volcengineapi.com",
        )


def test_get_speech_token_invalid_response():
    """Test when API response is invalid"""
    # Setup
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "test_access_key")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "test_secret_key")

    mock_response = {"Error": {"Message": "Invalid request"}}

    with patch("veadk.auth.veauth.speech_veauth.ve_request") as mock_ve_request:
        mock_ve_request.return_value = mock_response

        # Execute & Verify
        with pytest.raises(ValueError, match="Failed to get speech api key list"):
            get_speech_token()
