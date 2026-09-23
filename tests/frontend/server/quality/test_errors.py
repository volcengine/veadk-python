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
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import APIStatusError

from frontend.server.quality.models import QualityRequest
from frontend.server.quality.routes import mount_quality_routes


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_provider_diagnostics_reach_response_in_full_without_credentials(
    monkeypatch, provider
):
    api_key = "test-provider-key-that-is-not-in-environment"
    message = "cloud log line\n" * 10000 + "LAST CLOUD LOG LINE"
    body = {
        "error": {"code": "InvalidParameter", "message": message},
        "api_key": api_key,
    }
    response = httpx.Response(
        400,
        json=body,
        headers={
            "x-request-id": "request-123",
            "x-tt-logid": "log-456",
            "set-cookie": "private-session",
        },
        request=httpx.Request("POST", "https://provider.invalid/api/v3/responses"),
    )
    error = APIStatusError(
        f"Model request rejected: {api_key}", response=response, body=body
    )
    monkeypatch.setattr("veadk.Agent", Mock())
    monkeypatch.setattr(
        "veadk.Runner",
        Mock(return_value=SimpleNamespace(run=AsyncMock(side_effect=error))),
    )
    app = FastAPI()
    mount_quality_routes(
        app,
        provider=provider,
        resolve_api_key=lambda: api_key,
        authorize=Mock(),
        authorize_runtime=Mock(),
    )
    result = TestClient(app).post(
        "/web/quality/evaluators", json={"agent": {"name": "assistant"}}
    )
    assert result.status_code == 502
    detail = result.json()["detail"]
    assert detail["code"] == "quality_generation_failed"
    diagnostics = detail["diagnostics"]
    assert "HTTP status: 400" in diagnostics
    assert "request-123" in diagnostics and "log-456" in diagnostics
    assert "InvalidParameter" in diagnostics
    assert "LAST CLOUD LOG LINE" in diagnostics and len(diagnostics) > 100000
    assert "Exception trace:" in diagnostics
    assert api_key not in diagnostics and "private-session" not in diagnostics
    assert "[REDACTED]" in diagnostics


def test_complete_topology_contract_keeps_resource_ownership_and_edge_names():
    context = QualityRequest.model_validate(
        {
            "agent": {
                "id": "root",
                "name": "review",
                "type": "sequential",
                "children": ["root/0", "root/1"],
                "configuredWorkflow": {
                    "type": "custom",
                    "edges": [{"from": "root/0", "to": "root/1"}],
                },
                "subAgentDetails": [
                    {
                        "id": "root/0",
                        "parentId": "root",
                        "name": "lookup",
                        "path": ["review", "lookup"],
                        "instruction": "Retrieve the current refund policy",
                        "components": [
                            {
                                "name": "refund-policy",
                                "kind": "knowledgebase",
                                "provenance": "runtime",
                            }
                        ],
                        "skillDetails": [
                            {
                                "name": "lookup-policy",
                                "instructions": "Cite the retrieved policy clause",
                            }
                        ],
                    }
                ],
                "contextNotes": [
                    "No documents have been retrieved from the knowledge base"
                ],
            }
        }
    )
    payload = context.model_dump(by_alias=True)["agent"]
    assert payload["configuredWorkflow"]["edges"] == [
        {"from": "root/0", "to": "root/1"}
    ]
    assert payload["subAgentDetails"][0]["components"][0]["name"] == "refund-policy"
    assert (
        payload["subAgentDetails"][0]["skillDetails"][0]["instructions"]
        == "Cite the retrieved policy clause"
    )
