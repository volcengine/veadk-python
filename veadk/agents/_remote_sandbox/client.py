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


"""Construct control-plane clients with VeADK endpoint overrides."""

import os

from veadk.tools.builtin_tools._agentkit import (
    get_agentkit_credentials,
    get_agentkit_endpoint_config,
)


def create_agentkit_client(state=None):
    """Explicit AGENTKIT_TOOL_* settings override SDK endpoint settings.

    Unset settings retain SDK defaults and VOLCENGINE_AGENTKIT_* overrides.
    A VeADK service override also selects its derived host unless HOST is set.
    Only this client instance is changed; process environment is never mutated.
    """
    from agentkit.sdk.tools.client import AgentkitToolsClient

    service, region, host, scheme = get_agentkit_endpoint_config()
    ak, sk, headers = get_agentkit_credentials(state)
    client = AgentkitToolsClient(
        access_key=ak,
        secret_key=sk,
        region=region,
        session_token=headers.get("X-Security-Token", ""),
    )
    if os.getenv("AGENTKIT_TOOL_SERVICE_CODE"):
        client.service = service
        client.service_info.credentials.service = service
    if os.getenv("AGENTKIT_TOOL_HOST") or os.getenv("AGENTKIT_TOOL_SERVICE_CODE"):
        client.host = host
        client.service_info.host = host
    if os.getenv("AGENTKIT_TOOL_SCHEME"):
        client.scheme = scheme
        client.service_info.scheme = scheme
    return client
