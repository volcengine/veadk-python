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

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from veadk.integrations.ve_identity.identity_client import IdentityClient


@pytest.mark.parametrize("pool_name", [None, "customer-pool"])
def test_api_key_request_preserves_optional_pool_scope(pool_name):
    client = IdentityClient(
        access_key="test-ak", secret_key="test-sk", enable_vefaas_iam_fallback=False
    )
    api = Mock()
    api.api_client.configuration = SimpleNamespace()
    api.get_resource_api_key.return_value = SimpleNamespace(api_key="test-key")
    client._api_client = api
    arguments = {
        "provider_name": "model-provider",
        "agent_identity_token": "test-token",
    }
    if pool_name is not None:
        arguments["pool_name"] = pool_name
    assert client.get_api_key(**arguments) == "test-key"
    request = api.get_resource_api_key.call_args.args[0]
    assert request.pool_name == pool_name
    assert request.provider_name == "model-provider"
    assert request.identity_token == "test-token"
