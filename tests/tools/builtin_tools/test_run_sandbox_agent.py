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
    wait_for_skill_api_health=lambda **_kwargs: None,
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
        if wait_for_skill_api_health is not None:
            module._wait_for_skill_api_health = wait_for_skill_api_health
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

    def test_execute_skills_posts_a2a_message_send_and_returns_artifact_text(self):
        captured_requests = []
        session_kwargs = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "req",
                        "result": {
                            "kind": "task",
                            "id": "task-1",
                            "status": {"state": "completed"},
                            "artifacts": [
                                {"parts": [{"kind": "text", "text": "a2a result"}]}
                            ],
                        },
                    }
                ).encode()

        def fake_urlopen(request, timeout=None):
            captured_requests.append((request, timeout))
            return FakeResponse()

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **kwargs: (
                session_kwargs.append(kwargs) or "https://sandbox.test"
            ),
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            result = module.execute_skills("do work", tool_context=self._tool_context())

        self.assertEqual(result, "a2a result")
        self.assertTrue(session_kwargs[0]["wait_until_ready"])
        self.assertEqual("test-tool", session_kwargs[0]["tool_id"])
        self.assertEqual(
            "agent_user_session-1", session_kwargs[0]["tool_user_session_id"]
        )
        self.assertEqual(1, len(captured_requests))
        request_obj, timeout = captured_requests[0]
        payload = json.loads(request_obj.data.decode())
        self.assertEqual("https://sandbox.test/a2a", request_obj.full_url)
        self.assertEqual(60, timeout)
        self.assertEqual("POST", request_obj.get_method())
        self.assertEqual("message/send", payload["method"])
        self.assertEqual("do work", payload["params"]["message"]["parts"][0]["text"])
        self.assertFalse(payload["params"]["configuration"]["blocking"])
        self.assertEqual("user", payload["params"]["metadata"]["user_id"])
        self.assertEqual("session-1", payload["params"]["metadata"]["session_id"])

    def test_a2a_retries_502_until_upstream_is_ready(self):
        attempts = []

        class HealthyResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "req",
                        "result": {
                            "kind": "task",
                            "id": "task-1",
                            "status": {"state": "completed"},
                            "artifacts": [
                                {"parts": [{"kind": "text", "text": "ready"}]}
                            ],
                        },
                    }
                ).encode()

        class ErrorResponse:
            def read(self):
                return b"bad gateway"

            def close(self):
                return None

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        def fake_urlopen(req, **_kwargs):
            attempts.append((req.full_url, req.get_method()))
            if len(attempts) == 1:
                raise module.error.HTTPError(
                    url=req.full_url,
                    code=502,
                    msg="Bad Gateway",
                    hdrs={},
                    fp=ErrorResponse(),
                )
            return HealthyResponse()

        with (
            patch.object(module.request, "urlopen", fake_urlopen),
            patch.object(module.time, "sleep") as sleep,
        ):
            result = module.execute_skills("do work", tool_context=self._tool_context())

        self.assertEqual(result, "ready")
        self.assertEqual(
            [
                ("https://sandbox.test/a2a", "POST"),
                ("https://sandbox.test/a2a", "POST"),
            ],
            attempts,
        )
        sleep.assert_called_once_with(2.0)

    def test_env_vars_are_rejected_for_a2a_execution(self):
        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: self.fail(
                "env_vars must be rejected before endpoint resolution"
            ),
        )

        with self.assertRaisesRegex(ValueError, "env_vars is not supported"):
            module.execute_skills(
                "do work",
                tool_context=self._tool_context(),
                env_vars={"CUSTOM_VALUE": "custom"},
            )

    def test_a2a_polls_task_until_completed_and_returns_status_message_text(self):
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
                    "status": {
                        "state": "completed",
                        "message": {"parts": [{"kind": "text", "text": "poll result"}]},
                    },
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

        def fake_urlopen(request, timeout=None):
            captured_requests.append((request, timeout))
            return FakeResponse()

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with (
            patch.object(module.request, "urlopen", fake_urlopen),
            patch.object(module.time, "sleep") as sleep,
        ):
            result = module.execute_skills("do work", tool_context=self._tool_context())

        self.assertEqual(result, "poll result")
        self.assertEqual(2, len(captured_requests))
        send_request, _send_timeout = captured_requests[0]
        get_request, _get_timeout = captured_requests[1]
        send_payload = json.loads(send_request.data.decode())
        get_payload = json.loads(get_request.data.decode())
        self.assertEqual("message/send", send_payload["method"])
        self.assertEqual("tasks/get", get_payload["method"])
        self.assertEqual("task-1", get_payload["params"]["id"])
        sleep.assert_called_once_with(2.0)

    def test_a2a_returns_history_text_when_artifacts_and_status_are_empty(self):
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
                        "id": "req",
                        "result": {
                            "kind": "task",
                            "id": "task-1",
                            "status": {"state": "completed"},
                            "history": [
                                {
                                    "role": "user",
                                    "parts": [{"kind": "text", "text": "do work"}],
                                },
                                {
                                    "role": "agent",
                                    "parts": [
                                        {"kind": "text", "text": "history result"}
                                    ],
                                },
                            ],
                        },
                    }
                ).encode()

        def fake_urlopen(request, timeout=None):
            captured_requests.append((request, timeout))
            return FakeResponse()

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            result = module.execute_skills("do work", tool_context=self._tool_context())

        self.assertEqual(result, "history result")
        request_obj, timeout = captured_requests[0]
        payload = json.loads(request_obj.data.decode())
        self.assertEqual("https://sandbox.test/a2a", request_obj.full_url)
        self.assertEqual(60, timeout)
        self.assertEqual("message/send", payload["method"])
        self.assertEqual("do work", payload["params"]["message"]["parts"][0]["text"])
        self.assertFalse(payload["params"]["configuration"]["blocking"])

    def test_a2a_rejects_non_task_message_send_response(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": "req",
                        "result": {
                            "kind": "message",
                            "role": "agent",
                            "parts": [{"kind": "text", "text": "a2a result"}],
                        },
                    }
                ).encode()

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(
            module.request, "urlopen", lambda *_args, **_kwargs: FakeResponse()
        ):
            with self.assertRaisesRegex(
                RuntimeError, "A2ASendMessage response result is not an A2A task"
            ):
                module.execute_skills("do work", tool_context=self._tool_context())

    def test_timeout_must_be_within_a2a_execution_limit(self):
        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: self.fail(
                "Invalid timeout must be rejected before endpoint resolution"
            ),
        )

        with self.assertRaisesRegex(ValueError, "between 1 and 1800 seconds"):
            module.execute_skills(
                "do work", tool_context=self._tool_context(), timeout=0
            )

    def test_skill_api_url_preserves_agentkit_endpoint_query_auth(self):
        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "",
        )

        self.assertEqual(
            "https://sandbox.test/v1/skills/execute?faasInstanceName=inst&Authorization=key",
            module._skill_api_url(
                "https://sandbox.test/?faasInstanceName=inst&Authorization=key",
                "/v1/skills/execute",
            ),
        )

    def test_a2a_http_404_is_not_swallowed(self):
        class NotFoundResponse:
            def read(self):
                return b"not found"

            def close(self):
                return None

        def fake_urlopen(_request, **_kwargs):
            raise module.error.HTTPError(
                url="https://sandbox.test/a2a",
                code=404,
                msg="Not Found",
                hdrs={},
                fp=NotFoundResponse(),
            )

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            with self.assertRaisesRegex(
                RuntimeError,
                r"AgentKit Skill /a2a request failed with HTTP 404: not found",
            ):
                module.execute_skills("do work", tool_context=self._tool_context())

    def test_a2a_http_405_is_not_swallowed(self):
        class MethodNotAllowedResponse:
            def read(self):
                return b"method not allowed"

            def close(self):
                return None

        def fake_urlopen(_request, **_kwargs):
            raise module.error.HTTPError(
                url="https://sandbox.test/a2a",
                code=405,
                msg="Method Not Allowed",
                hdrs={},
                fp=MethodNotAllowedResponse(),
            )

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            with self.assertRaisesRegex(
                RuntimeError,
                r"AgentKit Skill /a2a request failed with HTTP 405: method not allowed",
            ):
                module.execute_skills("do work", tool_context=self._tool_context())

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

    def test_a2a_http_500_is_not_swallowed(self):
        class ServerErrorResponse:
            def read(self):
                return b"internal error"

            def close(self):
                return None

        def fake_urlopen(_request, **_kwargs):
            raise module.error.HTTPError(
                url="https://sandbox.test/a2a",
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=ServerErrorResponse(),
            )

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            with self.assertRaisesRegex(RuntimeError, "HTTP 500: internal error"):
                module.execute_skills("do work", tool_context=self._tool_context())


if __name__ == "__main__":
    unittest.main()
