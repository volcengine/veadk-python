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

import inspect
import json
from unittest.mock import Mock, patch

import pytest
import requests

from veadk.a2a.registry_client import (
    AgentKitA2ARegistryConfig,
    RegistryError,
    _OAUTH_TOKEN_CACHE,
    _agent_auth_headers,
    _volc_sign_v4,
    create_task,
    poll_task,
    registry_tip_token_from_headers,
    search_agent_cards,
    truncate_utf8_bytes,
)
from veadk.tools.builtin_tools.a2a_registry import (
    build_a2a_registry_tools,
    build_remote_a2a_agent_tools,
)
from veadk.utils.auth import VE_TIP_TOKEN_HEADER


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


def _oauth_agent_card() -> dict:
    token_url = (
        "https://userpool-61597ac7-4bcb-4acf-a1d8-fdbfb95333ad."
        "userpool.auth.id.cn-beijing.volces.com/oauth/token"
    )
    return {
        "name": "Finance Policy Remote Agent",
        "description": "Finance policy agent",
        "version": "1.0.0",
        "url": " https://oauth-agent.test/a2a/ ",
        "security": [{"oauth2": []}],
        "securitySchemes": {
            "oauth2": {
                "type": "oauth2",
                "description": "OAuth2 client credentials flow",
                "flows": {
                    "clientCredentials": {
                        "tokenUrl": f" `{token_url}` ",
                        "refreshUrl": f" `{token_url}` ",
                        "scopes": {},
                    }
                },
            }
        },
        "skills": [
            {
                "id": "finance-policy",
                "name": "Finance policy",
                "description": "Answer finance policy questions",
                "tags": ["finance", "policy"],
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
def test_search_agent_cards_truncates_prompt_to_2048_utf8_bytes(post: Mock):
    card = _agent_card()
    post.return_value = _mock_response(
        {
            "ResponseMetadata": {"RequestId": "req-1"},
            "Result": {"AgentCards": [json.dumps(card)], "TotalCount": 1},
        }
    )
    prompt = "番茄炒蛋" * 300

    search_agent_cards(
        prompt,
        3,
        AgentKitA2ARegistryConfig(space_id="space-test"),
    )

    request_body = json.loads(post.call_args.kwargs["data"].decode("utf-8"))
    request_prompt = request_body["Prompt"]
    assert len(request_prompt.encode("utf-8")) <= 2048
    assert request_prompt == truncate_utf8_bytes(prompt, 2048)


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
@patch("veadk.a2a.registry_client.requests.post")
def test_create_task_gets_oauth_agent_token_and_sends_message(post: Mock):
    _OAUTH_TOKEN_CACHE.clear()
    card = _oauth_agent_card()
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
                "ResponseMetadata": {"RequestId": "list-client-req"},
                "Result": {"Data": [{"Uid": "m2m-client-id"}]},
            }
        ),
        _mock_response(
            {
                "ResponseMetadata": {"RequestId": "get-client-req"},
                "Result": {"ClientSecret": "m2m-client-secret"},
            }
        ),
        _mock_response({"access_token": "oauth-access-token", "expires_in": 3600}),
        _mock_response(
            {
                "result": {
                    "kind": "message",
                    "parts": [{"kind": "text", "text": "需要财务审批。"}],
                }
            }
        ),
    ]

    result = create_task(
        "Finance Policy Remote Agent",
        "这笔支出是否需要审批？",
        config=AgentKitA2ARegistryConfig(
            space_id="space-test",
            endpoint="https://open.volcengineapi.com/",
        ),
    )

    assert result["outcome"] == "success"
    assert result["selected_agent"]["name"] == "Finance Policy Remote Agent"
    assert result["response"]["text"] == "需要财务审批。"

    assert post.call_args_list[0].kwargs["params"]["Action"] == "GetA2aAgent"
    assert post.call_args_list[1].kwargs["params"]["Action"] == "ListUserPoolClients"
    assert post.call_args_list[1].kwargs["params"]["Version"] == "2025-10-30"
    assert post.call_args_list[2].kwargs["params"]["Action"] == "GetUserPoolClient"
    assert post.call_args_list[2].kwargs["params"]["Version"] == "2025-10-30"
    assert post.call_args_list[3].args[0].endswith("/oauth/token")
    assert (
        post.call_args_list[3].kwargs["headers"]["Authorization"].startswith("Basic ")
    )
    assert post.call_args_list[4].args[0] == "https://oauth-agent.test/a2a/"
    assert post.call_args_list[4].kwargs["headers"]["Authorization"] == (
        "Bearer oauth-access-token"
    )

    serialized = json.dumps(result, ensure_ascii=False)
    assert "oauth-access-token" not in serialized
    assert "m2m-client-secret" not in serialized


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
                    "artifacts": [{"parts": [{"kind": "text", "text": "任务完成。"}]}],
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


@patch.dict(
    "os.environ",
    {
        "AGENTKIT_ACCESS_KEY": "ak-test",
        "AGENTKIT_SECRET_KEY": "sk-test",
    },
    clear=False,
)
@patch("veadk.a2a.registry_client.requests.post")
def test_registry_task_create_tool_forwards_tip_token(post: Mock):
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
    tools = build_a2a_registry_tools(
        AgentKitA2ARegistryConfig(
            space_id="space-test",
            upstream_tip_token="tip-from-config",
        )
    )

    result = tools[1]("Weather-A2A-Agent", "北京天气")

    assert result["outcome"] == "success"
    assert post.call_args_list[1].kwargs["headers"][VE_TIP_TOKEN_HEADER] == (
        "tip-from-config"
    )


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
def test_registry_task_poll_tool_forwards_tip_token(post: Mock, sleep: Mock):
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
                }
            }
        ),
    ]
    tools = build_a2a_registry_tools(
        AgentKitA2ARegistryConfig(
            space_id="space-test",
            upstream_tip_token="tip-from-config",
        )
    )

    result = tools[2]("Weather-A2A-Agent", "task-1")

    assert result["outcome"] == "success"
    assert post.call_args_list[1].kwargs["headers"][VE_TIP_TOKEN_HEADER] == (
        "tip-from-config"
    )
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
    assert "concise search prompt" in search_doc
    assert "must not exceed 2048 bytes" in search_doc
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


@patch.dict(
    "os.environ",
    {
        "AGENTKIT_ACCESS_KEY": "ak-test",
        "AGENTKIT_SECRET_KEY": "sk-test",
    },
    clear=False,
)
@patch("veadk.a2a.registry_client.requests.post")
def test_build_remote_a2a_agent_tools_searches_gets_and_sends(post: Mock):
    card = _agent_card()
    post.side_effect = [
        _mock_response(
            {
                "ResponseMetadata": {"RequestId": "search-req"},
                "Result": {"AgentCards": [json.dumps(card)], "TotalCount": 1},
            }
        ),
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
    config = AgentKitA2ARegistryConfig(space_id="space-test", top_k=7)

    tools = build_remote_a2a_agent_tools("北京天气", config)
    assert [tool.__name__ for tool in tools] == ["remote_a2a_weather_a2a_agent"]
    assert post.call_count == 1
    assert post.call_args_list[0].kwargs["params"]["Action"] == "SearchAgentCards"

    result = tools[0](input="北京天气")
    tool_doc = " ".join((tools[0].__doc__ or "").split())

    search_body = json.loads(post.call_args_list[0].kwargs["data"].decode("utf-8"))
    assert search_body["TopK"] == 7
    assert "Weather agent" in tool_doc
    assert "a2a_registry_task_poll" in tool_doc
    assert "Weather-A2A-Agent" in tool_doc
    assert result["outcome"] == "success"
    assert result["selected_agent"]["name"] == "Weather-A2A-Agent"
    assert result["response"]["text"] == "今天北京晴。"
    assert post.call_args_list[0].kwargs["params"]["Action"] == "SearchAgentCards"
    assert post.call_args_list[1].kwargs["params"]["Action"] == "GetA2aAgent"
    assert post.call_args_list[2].args[0] == "https://example.test/a2a"


@patch.dict(
    "os.environ",
    {
        "AGENTKIT_ACCESS_KEY": "ak-test",
        "AGENTKIT_SECRET_KEY": "sk-test",
    },
    clear=False,
)
@patch("veadk.a2a.registry_client.requests.post")
def test_dynamic_remote_a2a_tool_forwards_config_tip_token(post: Mock):
    card = _agent_card()
    post.side_effect = [
        _mock_response(
            {
                "ResponseMetadata": {"RequestId": "search-req"},
                "Result": {"AgentCards": [json.dumps(card)], "TotalCount": 1},
            }
        ),
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
    config = AgentKitA2ARegistryConfig(
        space_id="space-test",
        upstream_tip_token="tip-from-config",
    )

    tools = build_remote_a2a_agent_tools("北京天气", config)
    result = tools[0](input="北京天气")

    assert result["outcome"] == "success"
    assert post.call_args_list[2].kwargs["headers"][VE_TIP_TOKEN_HEADER] == (
        "tip-from-config"
    )


@patch("veadk.tools.builtin_tools.a2a_registry.search_agent_cards")
def test_build_remote_a2a_agent_tools_returns_empty_on_search_failure(search: Mock):
    search.side_effect = RegistryError("AGENT_NOT_FOUND", "no agents")

    tools = build_remote_a2a_agent_tools(
        "unknown task", AgentKitA2ARegistryConfig(space_id="space-test")
    )

    assert tools == []


@patch("veadk.tools.builtin_tools.a2a_registry.search_agent_cards")
def test_search_tool_accepts_prompt(search: Mock):
    config = AgentKitA2ARegistryConfig(space_id="space-test")
    search.return_value = {"outcome": "success", "agents": []}
    tool = build_a2a_registry_tools(config)[0]

    result = tool(prompt="三亚五日游")

    assert result["outcome"] == "success"
    search.assert_called_once_with("三亚五日游", None, config)


@patch("veadk.tools.builtin_tools.a2a_registry.search_agent_cards")
def test_search_tool_does_not_expose_top_k_to_model(search: Mock):
    config = AgentKitA2ARegistryConfig(space_id="space-test", top_k=7)
    search.return_value = {"outcome": "success", "agents": []}
    tool = build_a2a_registry_tools(config)[0]

    assert "top_k" not in inspect.signature(tool).parameters
    assert "query" not in inspect.signature(tool).parameters

    result = tool(prompt="财务报销")

    assert result["outcome"] == "success"
    search.assert_called_once_with("财务报销", None, config)


@patch.dict("os.environ", {}, clear=True)
def test_agent_auth_headers_extracts_api_key_header():
    assert _agent_auth_headers(_agent_card()) == {
        "Authorization": "Bearer secret-token"
    }


@patch.dict("os.environ", {}, clear=True)
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


def test_registry_tip_token_from_headers_is_case_insensitive():
    assert (
        registry_tip_token_from_headers({"x-ve-tip-token": " tip-from-header "})
        == "tip-from-header"
    )


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

    with (
        patch.dict(
            "os.environ",
            {"AGENTKIT_ACCESS_KEY": "ak-test", "AGENTKIT_SECRET_KEY": "sk-test"},
            clear=False,
        ),
        patch("veadk.a2a.registry_client.requests.post", return_value=response),
    ):
        with pytest.raises(RegistryError) as ctx:
            search_agent_cards(
                "weather",
                3,
                AgentKitA2ARegistryConfig(space_id="space-test"),
            )

    assert ctx.value.code == "AGENTKIT_OPENAPI_FAILED"
    assert ctx.value.diagnostics["status_code"] == 401
    assert ctx.value.diagnostics["request_id"] == "req-401"
    assert ctx.value.diagnostics["response_error"]["Code"] == ("SignatureDoesNotMatch")
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
