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

from veadk.integrations.mpa import session_client as MODULE

SelfHostSandboxClient = MODULE.SelfHostSandboxClient


def _client():
    return SelfHostSandboxClient(
        base_url="https://sandbox.example.com",
        environment_id="env-123",
        agent_id="agent-123",
        session_id="session-123",
        bearer_token="token",
        remote_bash_tool_name="bash",
    )


def test_injected_anthropic_session_id_takes_precedence(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_SESSION_ID", "session-from-work-item")
    monkeypatch.setenv("SANDBOX_SESSION_ID", "legacy-session")

    client = SelfHostSandboxClient(
        base_url="https://sandbox.example.com",
        environment_id="env-123",
        agent_id="agent-123",
        bearer_token="token",
    )

    assert client.session_id == "session-from-work-item"


def test_execute_command_posts_agent_tool_use_and_correlates_worker_result(
    monkeypatch,
):
    client = _client()
    posted_events = []
    event_batches = iter(
        [
            [{"_seq": 10, "type": "session.status_idle"}],
            [
                {
                    "_seq": 11,
                    "type": "agent.tool_use",
                    "id": "call-123",
                    "name": "bash",
                    "input": {"command": "echo hello", "timeout": 5000},
                },
                {
                    "_seq": 12,
                    "type": "user.tool_result",
                    "tool_use_id": "call-123",
                    "content": "exit=0\nhello\n",
                    "is_error": False,
                },
            ],
        ]
    )

    monkeypatch.setattr(client, "list_events", lambda **kwargs: next(event_batches))
    monkeypatch.setattr(
        client,
        "post_events",
        lambda events: posted_events.extend(events) or {"status": "accepted"},
    )

    result = client.execute_command(
        "echo hello",
        timeout=5,
        dispatch_id="call-123",
    )

    assert posted_events == [
        {
            "type": "agent.tool_use",
            "id": "call-123",
            "name": "bash",
            "input": {
                "command": "echo hello",
                "timeout_ms": 5000,
            },
        },
        {
            "type": "agent.tool_result",
            "tool_use_id": "call-123",
            "content": "exit=0\nhello\n",
            "is_error": False,
        },
    ]
    assert result == {
        "dispatch_id": "call-123",
        "tool_use_id": "call-123",
        "environment_id": "env-123",
        "session_id": "session-123",
        "status": "completed",
        "exit_code": 0,
        "stdout": "hello\n",
        "stderr": "",
        "content": "exit=0\nhello\n",
        "is_error": False,
    }


def test_send_tool_result_uses_payload_shape(monkeypatch):
    client = _client()
    posted_events = []
    monkeypatch.setattr(
        client,
        "post_events",
        lambda events: posted_events.extend(events) or {"status": "accepted"},
    )

    client.send_tool_result("tool-123", "done")

    assert posted_events == [
        {
            "type": "user.tool_result",
            "tool_use_id": "tool-123",
            "content": [{"type": "text", "text": "done"}],
            "is_error": False,
        }
    ]


@pytest.mark.parametrize(
    "name,input",
    [
        ("read", {"file_path": "a 'quoted' $file.txt", "view_range": [1, -1]}),
        (
            "write",
            {
                "file_path": "notes.txt",
                "content": "' \" `$HOME` $(touch nope) &amp;\n中文",
            },
        ),
        (
            "edit",
            {
                "file_path": "notes.txt",
                "old_string": "old",
                "new_string": "new",
                "replace_all": True,
            },
        ),
        ("glob", {"pattern": "**/*.py"}),
        ("grep", {"pattern": "a.*b", "path": "."}),
        ("bash", {"restart": True, "timeout_ms": 5000}),
        ("search_internal_db", {"query": "select 'special'"}),
    ],
)
def test_dispatch_preserves_registered_name_and_json(monkeypatch, name, input):
    client = _client()
    posted = []
    result_content = [{"type": "text", "text": "done"}]
    monkeypatch.setattr(client, "post_events", lambda events: posted.extend(events))
    monkeypatch.setattr(
        client,
        "list_events",
        lambda **kw: [
            {
                "type": "user.tool_result",
                "tool_use_id": "native-1",
                "content": result_content,
                "is_error": False,
            }
        ],
    )
    result = client.dispatch_tool(name, input, dispatch_id="native-1")
    assert posted[0] == {
        "type": "agent.tool_use",
        "id": "native-1",
        "name": name,
        "input": input,
    }
    assert result["content"] == result_content
    assert posted[1]["content"] == result_content
    assert not hasattr(client, "tool_to_bash")


def test_bash_command_is_not_html_decoded(monkeypatch):
    client = _client()
    posted = []
    monkeypatch.setattr(client, "post_events", lambda events: posted.extend(events))
    monkeypatch.setattr(client, "_wait_for_tool_result", lambda **kw: {})
    client.execute_command("printf '%s' '&amp;'", timeout=2)
    assert posted[0]["input"] == {"command": "printf '%s' '&amp;'", "timeout_ms": 2000}
