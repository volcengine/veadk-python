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

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _tool_context():
    invocation_context = types.SimpleNamespace(
        session=types.SimpleNamespace(id="session-1"),
        agent=types.SimpleNamespace(name="agent"),
        user_id="user",
    )
    return types.SimpleNamespace(
        state={"state-key": "state-value"},
        _invocation_context=invocation_context,
    )


def _load_skill_task_module(
    module_name,
    *,
    ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
    post_a2a_jsonrpc=lambda **_kwargs: {
        "result": {"kind": "task", "id": "task-1", "status": {"state": "working"}}
    },
    inbound_auth_token=lambda _tool_context: "inbound-token",
):
    module_path = (
        Path(__file__).resolve().parents[3]
        / "veadk"
        / "tools"
        / "builtin_tools"
        / f"{module_name}.py"
    )

    fake_google = types.ModuleType("google")
    fake_google.__path__ = []  # type: ignore[attr-defined]
    fake_google_adk = types.ModuleType("google.adk")
    fake_google_adk.__path__ = []  # type: ignore[attr-defined]
    fake_google_adk_tools = types.ModuleType("google.adk.tools")
    fake_google_adk_tools.ToolContext = object

    fake_veadk = types.ModuleType("veadk")
    fake_veadk.__path__ = []  # type: ignore[attr-defined]
    fake_tools = types.ModuleType("veadk.tools")
    fake_tools.__path__ = []  # type: ignore[attr-defined]
    fake_builtin_tools = types.ModuleType("veadk.tools.builtin_tools")
    fake_builtin_tools.__path__ = []  # type: ignore[attr-defined]
    fake_agentkit = types.ModuleType("veadk.tools.builtin_tools._agentkit")
    fake_agentkit.resolve_agentkit_tool_id = lambda _name: "test-tool"
    fake_agentkit.ensure_agentkit_session_endpoint = ensure_agentkit_session_endpoint

    fake_execute_skills = types.ModuleType("veadk.tools.builtin_tools.execute_skills")
    fake_execute_skills._A2A_HISTORY_LENGTH = 20
    fake_execute_skills._a2a_request_timeout = lambda _deadline: 60
    fake_execute_skills._a2a_result_task = lambda _operation, response: response[
        "result"
    ]
    fake_execute_skills._inbound_auth_token = inbound_auth_token
    fake_execute_skills._post_a2a_jsonrpc = post_a2a_jsonrpc
    fake_execute_skills._tool_user_session_id = (
        lambda tool_context: "agent_user_session-1"
    )

    def fake_validate_timeout(timeout):
        if type(timeout) is not int or not 1 <= timeout <= 1800:
            raise ValueError("timeout must be an integer between 1 and 1800 seconds")

    fake_execute_skills._validate_timeout = fake_validate_timeout

    stub_modules = {
        "google": fake_google,
        "google.adk": fake_google_adk,
        "google.adk.tools": fake_google_adk_tools,
        "veadk": fake_veadk,
        "veadk.tools": fake_tools,
        "veadk.tools.builtin_tools": fake_builtin_tools,
        "veadk.tools.builtin_tools._agentkit": fake_agentkit,
        "veadk.tools.builtin_tools.execute_skills": fake_execute_skills,
    }

    with patch.dict(sys.modules, stub_modules):
        spec = importlib.util.spec_from_file_location(
            f"test_{module_name}_module", module_path
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class TestInvokeSkill(unittest.TestCase):
    def test_invoke_skill_posts_nonblocking_message_send_and_returns_task(self):
        session_kwargs = []
        jsonrpc_calls = []

        module = _load_skill_task_module(
            "invoke_skill",
            ensure_agentkit_session_endpoint=lambda **kwargs: (
                session_kwargs.append(kwargs) or "https://sandbox.test"
            ),
            post_a2a_jsonrpc=lambda **kwargs: (
                jsonrpc_calls.append(kwargs)
                or {
                    "result": {
                        "kind": "task",
                        "id": "task-1",
                        "status": {"state": "working"},
                    }
                }
            ),
        )

        task = module.invoke_skill("do work", tool_context=_tool_context(), timeout=30)

        self.assertEqual(
            {"kind": "task", "id": "task-1", "status": {"state": "working"}},
            task,
        )
        self.assertEqual(1, len(session_kwargs))
        self.assertEqual("test-tool", session_kwargs[0]["tool_id"])
        self.assertEqual(
            "agent_user_session-1", session_kwargs[0]["tool_user_session_id"]
        )
        self.assertEqual({"state-key": "state-value"}, session_kwargs[0]["tool_state"])
        self.assertEqual(1800, session_kwargs[0]["ttl"])
        self.assertTrue(session_kwargs[0]["wait_until_ready"])

        self.assertEqual(1, len(jsonrpc_calls))
        call = jsonrpc_calls[0]
        self.assertEqual("https://sandbox.test", call["endpoint"])
        self.assertEqual(60, call["timeout"])
        self.assertEqual("inbound-token", call["inbound_auth"])
        payload = call["payload"]
        self.assertEqual("2.0", payload["jsonrpc"])
        self.assertEqual("message/send", payload["method"])
        self.assertEqual("user", payload["params"]["metadata"]["user_id"])
        self.assertEqual("session-1", payload["params"]["metadata"]["session_id"])
        self.assertFalse(payload["params"]["configuration"]["blocking"])
        self.assertEqual(20, payload["params"]["configuration"]["historyLength"])
        self.assertEqual("do work", payload["params"]["message"]["parts"][0]["text"])

    def test_invoke_skill_requires_tool_context(self):
        module = _load_skill_task_module("invoke_skill")

        with self.assertRaisesRegex(ValueError, "tool_context is required"):
            module.invoke_skill("do work", tool_context=None)

    def test_invoke_skill_wraps_endpoint_resolution_error(self):
        module = _load_skill_task_module(
            "invoke_skill",
            ensure_agentkit_session_endpoint=lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("session failed")
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError, "AgentKit session endpoint is not available"
        ):
            module.invoke_skill("do work", tool_context=_tool_context())


class TestPollSkill(unittest.TestCase):
    def test_poll_skill_posts_one_tasks_get_request_and_returns_task(self):
        session_kwargs = []
        jsonrpc_calls = []

        module = _load_skill_task_module(
            "poll_skill",
            ensure_agentkit_session_endpoint=lambda **kwargs: (
                session_kwargs.append(kwargs) or "https://sandbox.test"
            ),
            post_a2a_jsonrpc=lambda **kwargs: (
                jsonrpc_calls.append(kwargs)
                or {
                    "result": {
                        "kind": "task",
                        "id": "task-1",
                        "status": {"state": "completed"},
                    }
                }
            ),
        )

        task = module.poll_skill("task-1", tool_context=_tool_context(), timeout=30)

        self.assertEqual(
            {"kind": "task", "id": "task-1", "status": {"state": "completed"}},
            task,
        )
        self.assertEqual(1, len(session_kwargs))
        self.assertEqual("test-tool", session_kwargs[0]["tool_id"])
        self.assertEqual(1, len(jsonrpc_calls))
        call = jsonrpc_calls[0]
        self.assertEqual("https://sandbox.test", call["endpoint"])
        self.assertEqual(60, call["timeout"])
        self.assertEqual("inbound-token", call["inbound_auth"])
        payload = call["payload"]
        self.assertEqual("tasks/get", payload["method"])
        self.assertEqual("task-1", payload["params"]["id"])
        self.assertEqual(20, payload["params"]["historyLength"])

    def test_poll_skill_rejects_empty_task_id_before_endpoint_resolution(self):
        module = _load_skill_task_module(
            "poll_skill",
            ensure_agentkit_session_endpoint=lambda **_kwargs: self.fail(
                "task_id must be rejected before endpoint resolution"
            ),
        )

        with self.assertRaisesRegex(ValueError, "task_id is required"):
            module.poll_skill("", tool_context=_tool_context())

    def test_poll_skill_requires_tool_context(self):
        module = _load_skill_task_module("poll_skill")

        with self.assertRaisesRegex(ValueError, "tool_context is required"):
            module.poll_skill("task-1", tool_context=None)


if __name__ == "__main__":
    unittest.main()
