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
import io
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_run_sandbox_agent_module():
    module_path = (
        Path(__file__).resolve().parents[3]
        / "veadk"
        / "tools"
        / "builtin_tools"
        / "run_sandbox_agent.py"
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
    fake_agentkit.invoke_agentkit_run_code = lambda **_kwargs: {}
    fake_utils = types.ModuleType("veadk.utils")
    fake_utils.__path__ = []  # type: ignore[attr-defined]
    fake_logger = types.ModuleType("veadk.utils.logger")
    fake_logger.get_logger = lambda _name: types.SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
    )

    stub_modules = {
        "google": fake_google,
        "google.adk": fake_google_adk,
        "google.adk.tools": fake_google_adk_tools,
        "veadk": fake_veadk,
        "veadk.tools": fake_tools,
        "veadk.tools.builtin_tools": fake_builtin_tools,
        "veadk.tools.builtin_tools._agentkit": fake_agentkit,
        "veadk.utils": fake_utils,
        "veadk.utils.logger": fake_logger,
    }

    with patch.dict(sys.modules, stub_modules):
        spec = importlib.util.spec_from_file_location(
            "test_run_sandbox_agent_module", module_path
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def _load_execute_skills_module(
    *,
    ensure_agentkit_session_endpoint=lambda **_kwargs: "",
    run_sandbox_agent=lambda **_kwargs: "",
):
    module_path = (
        Path(__file__).resolve().parents[3]
        / "veadk"
        / "tools"
        / "builtin_tools"
        / "execute_skills.py"
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
    fake_agentkit.get_agentkit_account_id = lambda _state: "test-account"
    fake_agentkit.resolve_agentkit_tool_id = lambda _name: "test-tool"
    fake_agentkit.ensure_agentkit_session_endpoint = ensure_agentkit_session_endpoint
    fake_runner = types.ModuleType("veadk.tools.builtin_tools.run_sandbox_agent")
    fake_runner.run_sandbox_agent = run_sandbox_agent
    fake_utils = types.ModuleType("veadk.utils")
    fake_utils.__path__ = []  # type: ignore[attr-defined]
    fake_logger = types.ModuleType("veadk.utils.logger")
    fake_logger.get_logger = lambda _name: types.SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
    )

    stub_modules = {
        "google": fake_google,
        "google.adk": fake_google_adk,
        "google.adk.tools": fake_google_adk_tools,
        "veadk": fake_veadk,
        "veadk.tools": fake_tools,
        "veadk.tools.builtin_tools": fake_builtin_tools,
        "veadk.tools.builtin_tools._agentkit": fake_agentkit,
        "veadk.tools.builtin_tools.run_sandbox_agent": fake_runner,
        "veadk.utils": fake_utils,
        "veadk.utils.logger": fake_logger,
    }

    with patch.dict(sys.modules, stub_modules):
        spec = importlib.util.spec_from_file_location(
            "test_execute_skills_module", module_path
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class TestMergeExecutionEnvVars(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_run_sandbox_agent_module()

    def test_custom_values_override_defaults_and_preserve_empty_values(self):
        base_env_vars = {"DEFAULT_VALUE": "default", "UNCHANGED": "value"}

        result = self.module._merge_execution_env_vars(
            base_env_vars,
            {"DEFAULT_VALUE": "custom", "EMPTY_VALUE": ""},
        )

        self.assertEqual(
            result,
            {
                "DEFAULT_VALUE": "custom",
                "UNCHANGED": "value",
                "EMPTY_VALUE": "",
            },
        )
        self.assertEqual(
            base_env_vars, {"DEFAULT_VALUE": "default", "UNCHANGED": "value"}
        )

    def test_rejects_framework_managed_values(self):
        for key in ["TOOL_USER_SESSION_ID", "USER_SESSION_ID"]:
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "managed by VeADK"):
                    self.module._merge_execution_env_vars({}, {key: "spoofed"})

    def test_rejects_invalid_names(self):
        for key in ["", "1INVALID", "INVALID-NAME", "INVALID=NAME"]:
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "Invalid environment"):
                    self.module._merge_execution_env_vars({}, {key: "value"})

    def test_rejects_non_string_and_null_byte_values(self):
        with self.assertRaisesRegex(TypeError, "must have a string value"):
            self.module._merge_execution_env_vars({}, {"COUNT": 1})

        with self.assertRaisesRegex(ValueError, "contains a null byte"):
            self.module._merge_execution_env_vars({}, {"VALUE": "before\x00after"})

    def test_runner_code_overrides_the_sandbox_process_environment(self):
        code = self.module._build_agent_runner_code(
            cmd=["python", "agent.py", "do work"],
            timeout=30,
            env_vars={"CUSTOM_VALUE": "custom"},
        )

        self.assertIn("env[key] = value", code)
        self.assertNotIn("if key not in env", code)
        self.assertIn('srv_pythonpath = env.get("SRV_PYTHONPATH")', code)


class TestExecuteSkillsSkillApi(unittest.TestCase):
    def _tool_context(self):
        invocation_context = types.SimpleNamespace(
            session=types.SimpleNamespace(id="session-1"),
            agent=types.SimpleNamespace(name="agent"),
            user_id="user",
        )
        return types.SimpleNamespace(
            state={"TIP_TOKEN_KEY": "tip-from-state"},
            _invocation_context=invocation_context,
        )

    def test_execute_skills_rejects_invalid_timeout(self):
        module = _load_execute_skills_module()

        for timeout in (0, -1, 1801, 1.5, True):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(
                    ValueError,
                    r"timeout must be an integer between 1 and 1800 seconds",
                ):
                    module.execute_skills(
                        "do work",
                        tool_context=self._tool_context(),
                        timeout=timeout,
                    )

    def test_env_vars_are_not_supported(self):
        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: self.fail(
                "env_vars must be rejected before endpoint resolution"
            )
        )

        with self.assertRaisesRegex(ValueError, "env_vars is not supported"):
            module.execute_skills(
                "do work",
                tool_context=self._tool_context(),
                env_vars={"CUSTOM_VALUE": "custom"},
            )

        with self.assertRaisesRegex(ValueError, "env_vars is not supported"):
            module.execute_skills(
                "do work",
                tool_context=self._tool_context(),
                env_vars={},
            )

    def test_execute_skills_does_not_accept_invocation_mode(self):
        module = _load_execute_skills_module()

        with self.assertRaises(TypeError):
            module.execute_skills(
                "do work",
                tool_context=self._tool_context(),
                invocation_mode="execute",
            )

    def test_default_a2a_mode_sends_nonblocking_message_and_polls_task(self):
        captured_requests = []
        responses = [
            {
                "jsonrpc": "2.0",
                "id": "send",
                "result": {
                    "kind": "task",
                    "id": "task-1",
                    "status": {"state": "working"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": "get",
                "result": {
                    "kind": "task",
                    "id": "task-1",
                    "status": {"state": "completed"},
                    "artifacts": [
                        {
                            "parts": [
                                {"kind": "text", "text": "a2a "},
                                {
                                    "kind": "text",
                                    "text": "thought",
                                    "metadata": {"adk_thought": True},
                                },
                            ]
                        },
                        {"parts": [{"kind": "text", "text": "result"}]},
                    ],
                },
            },
        ]

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(self.payload).encode()

        def fake_urlopen(request, timeout=None):
            captured_requests.append((request, timeout))
            return FakeResponse(responses.pop(0))

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **kwargs: (
                self.assertEqual(1800, kwargs["ttl"]) or "https://sandbox.test"
            ),
        )

        with (
            patch.object(module.request, "urlopen", fake_urlopen),
            patch.object(module.time, "sleep") as sleep,
        ):
            result = module.execute_skills(
                "do work",
                tool_context=self._tool_context(),
            )

        self.assertEqual(result, "a2a \nresult")
        self.assertEqual(2, len(captured_requests))
        send_request, send_timeout = captured_requests[0]
        send_payload = json.loads(send_request.data.decode())
        self.assertEqual("https://sandbox.test/a2a", send_request.full_url)
        self.assertEqual(60, send_timeout)
        self.assertEqual("message/send", send_payload["method"])
        self.assertEqual(
            "do work", send_payload["params"]["message"]["parts"][0]["text"]
        )
        self.assertFalse(send_payload["params"]["configuration"]["blocking"])
        self.assertEqual(20, send_payload["params"]["configuration"]["historyLength"])
        self.assertEqual("user", send_payload["params"]["metadata"]["user_id"])
        self.assertEqual("session-1", send_payload["params"]["metadata"]["session_id"])

        get_request, get_timeout = captured_requests[1]
        get_payload = json.loads(get_request.data.decode())
        self.assertEqual("https://sandbox.test/a2a", get_request.full_url)
        self.assertEqual(60, get_timeout)
        self.assertEqual("tasks/get", get_payload["method"])
        self.assertEqual("task-1", get_payload["params"]["id"])
        sleep.assert_called_once()

    def test_a2a_forwards_custom_timeout_to_requests(self):
        captured_timeouts = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "send",
                        "result": {
                            "kind": "task",
                            "id": "task-1",
                            "status": {
                                "state": "completed",
                                "message": {
                                    "parts": [
                                        {"kind": "text", "text": "custom timeout"}
                                    ]
                                },
                            },
                        },
                    }
                ).encode()

        def fake_urlopen(_request, timeout=None):
            captured_timeouts.append(timeout)
            return FakeResponse()

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **kwargs: (
                self.assertEqual(1800, kwargs["ttl"]) or "https://sandbox.test"
            ),
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            result = module.execute_skills(
                "do work",
                tool_context=self._tool_context(),
                timeout=120,
            )

        self.assertEqual("custom timeout", result)
        self.assertEqual([60], captured_timeouts)

    def test_a2a_posts_to_vefaas_a2a_endpoint_with_query_auth(self):
        captured_requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "test-1",
                        "result": {
                            "kind": "task",
                            "id": "task-1",
                            "status": {
                                "state": "completed",
                                "message": {
                                    "parts": [{"kind": "text", "text": "hello result"}]
                                },
                            },
                        },
                    }
                ).encode()

        def fake_urlopen(request, timeout=None):
            captured_requests.append((request, timeout))
            return FakeResponse()

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: (
                "https://sandbox.test/?faasInstanceName=inst&Authorization=key"
            ),
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            result = module.execute_skills("hello", tool_context=self._tool_context())

        self.assertEqual("hello result", result)
        self.assertEqual(1, len(captured_requests))
        send_request, send_timeout = captured_requests[0]
        send_payload = json.loads(send_request.data.decode())
        self.assertEqual(
            "https://sandbox.test/a2a?faasInstanceName=inst&Authorization=key",
            send_request.full_url,
        )
        self.assertEqual("application/json", send_request.get_header("Content-type"))
        self.assertIsNone(send_request.get_header("Accept"))
        self.assertEqual(60, send_timeout)
        self.assertEqual("2.0", send_payload["jsonrpc"])
        self.assertEqual("message/send", send_payload["method"])
        self.assertEqual("message", send_payload["params"]["message"]["kind"])
        self.assertEqual("user", send_payload["params"]["message"]["role"])
        self.assertEqual(
            [{"kind": "text", "text": "hello"}],
            send_payload["params"]["message"]["parts"],
        )
        self.assertFalse(send_payload["params"]["configuration"]["blocking"])
        self.assertEqual(20, send_payload["params"]["configuration"]["historyLength"])
        self.assertEqual("session-1", send_payload["params"]["metadata"]["session_id"])
        self.assertEqual("user", send_payload["params"]["metadata"]["user_id"])

    def test_retry_502(self):
        captured_timeouts = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "send",
                        "result": {
                            "kind": "task",
                            "id": "task-1",
                            "status": {
                                "state": "completed",
                                "message": {
                                    "parts": [{"kind": "text", "text": "retry ok"}]
                                },
                            },
                        },
                    }
                ).encode()

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        def fake_urlopen(request, timeout=None):
            captured_timeouts.append(timeout)
            if len(captured_timeouts) == 1:
                raise module.error.HTTPError(
                    request.full_url,
                    502,
                    "Bad Gateway",
                    hdrs=None,
                    fp=io.BytesIO(b"temporary gateway error"),
                )
            return FakeResponse()

        with (
            patch.object(module.request, "urlopen", fake_urlopen),
            patch.object(module.time, "sleep") as sleep,
        ):
            result = module.execute_skills("hello", tool_context=self._tool_context())

        self.assertEqual("retry ok", result)
        self.assertEqual([60, 60], captured_timeouts)
        sleep.assert_called_once_with(2.0)

    def test_a2a_mode_raises_when_task_fails(self):
        responses = [
            {
                "jsonrpc": "2.0",
                "id": "send",
                "result": {
                    "kind": "task",
                    "id": "task-1",
                    "status": {"state": "working"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": "get",
                "result": {
                    "kind": "task",
                    "id": "task-1",
                    "status": {"state": "failed"},
                },
            },
        ]

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(responses.pop(0)).encode()

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with (
            patch.object(
                module.request, "urlopen", lambda *_args, **_kwargs: FakeResponse()
            ),
            patch.object(module.time, "sleep"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                r"A2A task task-1 ended with state failed",
            ):
                module.execute_skills("do work", tool_context=self._tool_context())

    def test_skill_api_url_preserves_agentkit_endpoint_query_auth(self):
        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "",
        )

        self.assertEqual(
            "https://sandbox.test/a2a?faasInstanceName=inst&Authorization=key",
            module._skill_api_url(
                "https://sandbox.test/?faasInstanceName=inst&Authorization=key",
                "/a2a",
            ),
        )

    def test_a2a_jsonrpc_url_appends_a2a_before_vefaas_query(self):
        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "",
        )

        self.assertEqual(
            "https://sandbox.test/a2a?faasInstanceName=inst&Authorization=key",
            module._a2a_jsonrpc_url(
                "https://sandbox.test/?faasInstanceName=inst&Authorization=key"
            ),
        )
        self.assertEqual(
            "https://sc56tro0thc3nstnfkabv.apigateway-cn-beijing.volceapi.com/a2a"
            "?faasInstanceName=vefaas-example-sandbox&Authorization=test-token",
            module._a2a_jsonrpc_url(
                "https://sc56tro0thc3nstnfkabv.apigateway-cn-beijing.volceapi.com"
                "?faasInstanceName=vefaas-example-sandbox&Authorization=test-token"
            ),
        )

    def test_a2a_jsonrpc_url_keeps_explicit_a2a_endpoint(self):
        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "",
        )

        endpoint = "https://sandbox.test/a2a?faasInstanceName=inst&Authorization=key"
        self.assertEqual(endpoint, module._a2a_jsonrpc_url(endpoint))
        self.assertEqual(
            endpoint,
            module._a2a_jsonrpc_url(
                "https://sandbox.test/a2a/?faasInstanceName=inst&Authorization=key"
            ),
        )

    def test_a2a_jsonrpc_url_appends_a2a_for_plain_endpoint(self):
        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "",
        )

        self.assertEqual(
            "https://sandbox.test/a2a",
            module._a2a_jsonrpc_url("https://sandbox.test"),
        )

    def test_raises_runtime_error_when_session_endpoint_is_unavailable(self):
        def raise_endpoint_error(**_kwargs):
            raise RuntimeError("session unsupported")

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=raise_endpoint_error,
        )

        with self.assertRaisesRegex(
            RuntimeError, r"AgentKit session endpoint is not available"
        ):
            module.execute_skills("do work", tool_context=self._tool_context())

    def test_missing_tool_context_raises_value_error(self):
        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: self.fail(
                "Skill API requires a tool_context"
            ),
        )

        with self.assertRaisesRegex(ValueError, r"tool_context is required"):
            module.execute_skills("do work", tool_context=None)


if __name__ == "__main__":
    unittest.main()
