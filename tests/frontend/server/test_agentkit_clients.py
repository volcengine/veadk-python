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

from agentkit.sdk.tools.client import AgentkitToolsClient

from frontend.server.agentkit_clients import create_agentkit_client


def test_tools_client_preserves_vestack_endpoint_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("VOLCENGINE_AGENTKIT_HOST", "agentkit.e70.inspirecloud.io")
    monkeypatch.setenv("VOLCENGINE_AGENTKIT_SCHEME", "http")

    client = create_agentkit_client(
        AgentkitToolsClient,
        provider="volcengine",
        access_key="temporary-ak",
        secret_key="temporary-sk",
        session_token="temporary-token",
        region="e70",
    )

    assert client.host == "agentkit.e70.inspirecloud.io"
    assert client.scheme == "http"
    assert client.region == "e70"
