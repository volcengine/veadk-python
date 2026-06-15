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

import json
from unittest.mock import Mock, patch

import pytest
import requests

from veadk.a2a.registry_client import (
    AgentKitA2ARegistryConfig,
    RegistryError,
    _agent_auth_headers,
    _volc_sign_v4,
    create_task,
    poll_task,
    search_agent_cards,
)
from veadk.tools.builtin_tools.a2a_registry import build_a2a_registry_tools


def _mock_response(payload: dict, status_code: int = 200) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def _agent_card() -> dict:
    return {
        "name": "Weather-A2A-Agent",
        "description": "Weather agent",
        "version": "1.0.0",
        "url": "https://example.test/a2a",
        "security": [{"bearer": ["Bearer secret-token"]}],
        "securitySchemes": {
            "bearer": {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
            }
        },
        "skills": [
            {
                "id": "weather",
                "name": "Weather",
                "description": "Query weather",
                "tags": ["weather"],
            }
        ],
    }


@patch.dict(
    "os.environ",
    {
        "AGENTKIT_ACCESS_KEY": "ak-test",
        "AGENTKIT_SECRET_KEY": "sk-test",
    },
    clear=False,
)
@patch("veadk.a2a.registry_client.requests.post")
def test_search_agent_cards_sanitizes_and_signs_request(post: Mock):
    card = _agent_card()
    post.return_value = _mock_response(
        {
            "ResponseMetadata": {"RequestId": "req-1"},
            "Result": {"AgentCards": [json.dumps(card)], "TotalCount": 1},
        }
    )

    result = search_agent_cards(
        "北京天气",
        3,
        AgentKitA2ARegistryConfig(space_id="space-test"),
    )

    assert result["outcome"] == "success"
    assert result["agents"][0]["name"] == "Weather-A2A-Agent"

    request_headers = post.call_args.kwargs["headers"]
    assert "X-Content-Sha256" in request_headers
    assert (
        "SignedHeaders=content-type;host;x-content-sha256;x-date"
        in request_headers["Authorization"]
    )
    assert isinstance(post.call_args.kwargs["data"], bytes)
    assert "北京天气" in post.call_args.kwargs["data"].decode("utf-8")

    serialized = json.dumps(result, ensure_ascii=False)
    assert "secret-token" not in serialized
    assert "Authorization" not in serialized
    assert "https://example.test/a2a" not in serialized


@patch.dict(
    "os.environ",
    {
        "AGENTKIT_ACCESS_KEY": "ak-test",
        "AGENTKIT_SECRET_KEY": "sk-test",
    },
    clear=False,
)
@patch("veadk.a2a.registry_client.requests.post")
def test_create_task_gets_agent_and_sends_message(post: Mock):
    card = _agent_card()
    post.side_effect = [
        _mock_response(
            {
                "ResponseMetadata": {"RequestId": "get-req"},
                "Result": {
                    "Id": "agent-id",
                    "Status": "running",
                    "AgentCard": json.dumps(card),
                },
            }
        ),
        _mock_response(
            {
                "result": {
                    "kind": "message",
                    "parts": [{"kind": "text", "text": "今天北京晴。"}],
                }
            }
        ),
    ]

    result = create_task(
        "Weather-A2A-Agent",
        "北京天气",
        config=AgentKitA2ARegistryConfig(space_id="space-test"),
    )

    assert result["outcome"] == "success"
    assert result["selected_agent"]["name"] == "Weather-A2A-Agent"
    assert result["response"]["text"] == "今天北京晴。"
    assert post.call_args_list[0].kwargs["params"]["Action"] == "GetA2aAgent"
    assert post.call_args_list[1].args[0] == "https://example.test/a2a"

    serialized = json.dumps(result, ensure_ascii=False)
    assert "secret-token" not in serialized
    assert "Authorization" not in serialized


@patch.dict(
    "os.environ",
    {
        "AGENTKIT_ACCESS_KEY": "ak-test",
        "AGENTKIT_SECRET_KEY": "sk-test",
    },
    clear=False,
)
@patch("veadk.a2a.registry_client.time.sleep")
@patch("veadk.a2a.registry_client.requests.post")
def test_poll_task_sleeps_5_seconds_when_not_terminal(post: Mock, sleep: Mock):
    card = _agent_card()
    post.side_effect = [
        _mock_response(
            {
                "ResponseMetadata": {"RequestId": "get-req"},
                "Result": {
                    "Id": "agent-id",
                    "Status": "running",
                    "AgentCard": json.dumps(card),
                },
            }
        ),
        _mock_response(
            {
                "result": {
                    "id": "task-1",
                    "status": {"state": "working"},
                }
            }
        ),
    ]

    result = poll_task(
        "Weather-A2A-Agent",
        "task-1",
        config=AgentKitA2ARegistryConfig(space_id="space-test"),
    )

    assert result["outcome"] == "success"
    assert result["task"]["status"] == "working"
    assert result["is_terminal"] is False
    assert result["diagnostics"]["sleep_seconds"] == 5
    assert result["diagnostics"]["next_action"]
    sleep.assert_called_once_with(5)
    assert post.call_args_list[0].kwargs["params"]["Action"] == "GetA2aAgent"
    assert post.call_args_list[1].args[0] == "https://example.test/a2a"

    serialized = json.dumps(result, ensure_ascii=False)
    assert "secret-token" not in serialized
    assert "Authorization" not in serialized


@patch.dict(
    "os.environ",
    {
        "AGENTKIT_ACCESS_KEY": "ak-test",
        "AGENTKIT_SECRET_KEY": "sk-test",
    },
    clear=False,
)
@patch("veadk.a2a.registry_client.time.sleep")
@patch("veadk.a2a.registry_client.requests.post")
def test_poll_task_returns_terminal_without_sleep(post: Mock, sleep: Mock):
    card = _agent_card()
    post.side_effect = [
        _mock_response(
            {
                "ResponseMetadata": {"RequestId": "get-req"},
                "Result": {
                    "Id": "agent-id",
                    "Status": "running",
                    "AgentCard": json.dumps(card),
                },
            }
        ),
        _mock_response(
            {
                "result": {
                    "id": "task-1",
                    "status": {"state": "completed"},
                    "artifacts": [
                        {"parts": [{"kind": "text", "text": "任务完成。"}]}
                    ],
                }
            }
        ),
    ]

    result = poll_task(
        "Weather-A2A-Agent",
        "task-1",
        config=AgentKitA2ARegistryConfig(space_id="space-test"),
    )

    assert result["outcome"] == "success"
    assert result["task"]["status"] == "completed"
    assert result["is_terminal"] is True
    assert result["response"]["text"] == "任务完成。"
    sleep.assert_not_called()


def test_build_a2a_registry_tools_exposes_mcp_compatible_names():
    tools = build_a2a_registry_tools(AgentKitA2ARegistryConfig(space_id="space-test"))

    assert [tool.__name__ for tool in tools] == [
        "a2a_registry_search_agent_cards",
        "a2a_registry_task_create",
        "a2a_registry_task_poll",
    ]


def test_a2a_registry_tool_descriptions_guide_model_flow():
    search_tool, create_tool, poll_tool = build_a2a_registry_tools(
        AgentKitA2ARegistryConfig(space_id="space-test")
    )

    search_doc = " ".join((search_tool.__doc__ or "").split())
    assert "Use this first" in search_doc
    assert "agents" in search_doc
    assert "a2a_registry_task_create" in search_doc

    create_doc = " ".join((create_tool.__doc__ or "").split())
    assert "selected `agents[].name`" in create_doc
    assert "message/send" in create_doc
    assert "a2a_registry_task_poll" in create_doc

    poll_doc = " ".join((poll_tool.__doc__ or "").split())
    assert "tasks/get" in poll_doc
    assert "do not create a new task" in poll_doc
    assert "completed" in poll_doc
    assert "rejected" in poll_doc


@patch("veadk.tools.builtin_tools.a2a_registry.search_agent_cards")
def test_search_tool_accepts_query_alias(search: Mock):
    config = AgentKitA2ARegistryConfig(space_id="space-test")
    search.return_value = {"outcome": "success", "agents": []}
    tool = build_a2a_registry_tools(config)[0]

    result = tool(query="三亚五日游")

    assert result["outcome"] == "success"
    search.assert_called_once_with("三亚五日游", 3, config)


def test_agent_auth_headers_extracts_api_key_header():
    assert _agent_auth_headers(_agent_card()) == {
        "Authorization": "Bearer secret-token"
    }


def test_agent_auth_headers_rejects_unusable_security():
    with pytest.raises(RegistryError) as ctx:
        _agent_auth_headers(
            {
                "security": [{"bearer": []}],
                "securitySchemes": {
                    "bearer": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "Authorization",
                    }
                },
            }
        )
    assert ctx.value.code == "AGENT_AUTH_MISSING"


def test_agentkit_http_error_uses_safe_diagnostics():
    response = _mock_response(
        {
            "ResponseMetadata": {
                "RequestId": "req-401",
                "Action": "SearchAgentCards",
                "Version": "2025-10-30",
                "Service": "agentkit",
                "Region": "cn-beijing",
                "Error": {
                    "Code": "SignatureDoesNotMatch",
                    "CodeN": 100010,
                    "Message": "signature mismatch",
                },
            }
        },
        status_code=401,
    )
    response.raise_for_status.side_effect = requests.HTTPError(
        "401 Client Error", response=response
    )

    with patch.dict(
        "os.environ",
        {"AGENTKIT_ACCESS_KEY": "ak-test", "AGENTKIT_SECRET_KEY": "sk-test"},
        clear=False,
    ), patch("veadk.a2a.registry_client.requests.post", return_value=response):
        with pytest.raises(RegistryError) as ctx:
            search_agent_cards(
                "weather",
                3,
                AgentKitA2ARegistryConfig(space_id="space-test"),
            )

    assert ctx.value.code == "AGENTKIT_OPENAPI_FAILED"
    assert ctx.value.diagnostics["status_code"] == 401
    assert ctx.value.diagnostics["request_id"] == "req-401"
    assert ctx.value.diagnostics["response_error"]["Code"] == (
        "SignatureDoesNotMatch"
    )
    serialized = json.dumps(ctx.value.diagnostics, ensure_ascii=False)
    assert "Authorization" not in serialized
    assert "ak-test" not in serialized
    assert "sk-test" not in serialized


def test_volc_sign_v4_signs_openapi_headers():
    headers = _volc_sign_v4(
        access_key="ak-test",
        secret_key="sk-test",
        service="agentkit",
        region="cn-beijing",
        method="POST",
        path="/",
        query={"Action": "SearchAgentCards", "Version": "2025-10-30"},
        headers={
            "Host": "open.volcengineapi.com",
            "Content-Type": "application/json",
        },
        body='{"SpaceId":"space-test"}',
    )

    assert "X-Date" in headers
    assert "X-Content-Sha256" in headers
    assert (
        "SignedHeaders=content-type;host;x-content-sha256;x-date"
        in headers["Authorization"]
    )
