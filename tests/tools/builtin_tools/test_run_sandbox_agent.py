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
    run_sandbox_agent,
    ensure_agentkit_session_endpoint=lambda **_kwargs: "",
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


class TestExecuteSkillsEnvVars(unittest.TestCase):
    def test_passes_custom_env_vars_to_each_sandbox_execution(self):
        captured_kwargs = {}

        def fake_run_sandbox_agent(**kwargs):
            captured_kwargs.update(kwargs)
            return "done"

        module = _load_execute_skills_module(fake_run_sandbox_agent)
        tool_context = types.SimpleNamespace(state={})

        result = module.execute_skills(
            "do work",
            tool_context=tool_context,
            env_vars={"CUSTOM_VALUE": "custom", "TOS_SKILLS_DIR": ""},
        )

        self.assertEqual(result, "done")
        self.assertEqual(
            captured_kwargs["extra_env_vars"],
            {"CUSTOM_VALUE": "custom", "TOS_SKILLS_DIR": ""},
        )


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

    def test_prefers_new_skill_execute_api_when_endpoint_is_available(self):
        captured_requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"content": "api result"}'

        def fake_urlopen(request, timeout=None):
            captured_requests.append((request, timeout))
            return FakeResponse()

        fallback_calls = []

        def fake_run_sandbox_agent(**kwargs):
            fallback_calls.append(kwargs)
            return "fallback"

        module = _load_execute_skills_module(
            fake_run_sandbox_agent,
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            result = module.execute_skills("do work", tool_context=self._tool_context())

        self.assertEqual(result, "api result")
        self.assertEqual([], fallback_calls)
        self.assertEqual(1, len(captured_requests))
        request_obj, timeout = captured_requests[0]
        self.assertEqual("https://sandbox.test/v1/skills/execute", request_obj.full_url)
        self.assertEqual(900, timeout)
        self.assertEqual("POST", request_obj.get_method())
        self.assertEqual("tip-from-state", request_obj.headers["X-tip-token-key"])
        self.assertIn(b'"prompt": "do work"', request_obj.data)

    def test_falls_back_to_legacy_runcode_when_skill_api_returns_404(self):
        class NotFoundResponse:
            def read(self):
                return b"not found"

            def close(self):
                return None

        def fake_urlopen(_request, **_kwargs):
            raise module.error.HTTPError(
                url="https://sandbox.test/v1/skills/execute",
                code=404,
                msg="Not Found",
                hdrs={},
                fp=NotFoundResponse(),
            )

        fallback_calls = []

        def fake_run_sandbox_agent(**kwargs):
            fallback_calls.append(kwargs)
            return "legacy result"

        module = _load_execute_skills_module(
            fake_run_sandbox_agent,
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            result = module.execute_skills("do work", tool_context=self._tool_context())

        self.assertEqual(result, "legacy result")
        self.assertEqual(1, len(fallback_calls))
        self.assertEqual("do work", fallback_calls[0]["workflow_prompt"])

    def test_falls_back_to_legacy_runcode_when_skill_api_returns_405(self):
        class MethodNotAllowedResponse:
            def read(self):
                return b"method not allowed"

            def close(self):
                return None

        def fake_urlopen(_request, **_kwargs):
            raise module.error.HTTPError(
                url="https://sandbox.test/v1/skills/execute",
                code=405,
                msg="Method Not Allowed",
                hdrs={},
                fp=MethodNotAllowedResponse(),
            )

        fallback_calls = []

        def fake_run_sandbox_agent(**kwargs):
            fallback_calls.append(kwargs)
            return "legacy result"

        module = _load_execute_skills_module(
            fake_run_sandbox_agent,
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            result = module.execute_skills("do work", tool_context=self._tool_context())

        self.assertEqual(result, "legacy result")
        self.assertEqual(1, len(fallback_calls))

    def test_falls_back_to_legacy_runcode_when_session_endpoint_is_unavailable(self):
        fallback_calls = []

        def fake_run_sandbox_agent(**kwargs):
            fallback_calls.append(kwargs)
            return "legacy result"

        def raise_endpoint_error(**_kwargs):
            raise RuntimeError("session unsupported")

        module = _load_execute_skills_module(
            fake_run_sandbox_agent,
            ensure_agentkit_session_endpoint=raise_endpoint_error,
        )

        result = module.execute_skills("do work", tool_context=self._tool_context())

        self.assertEqual(result, "legacy result")
        self.assertEqual(1, len(fallback_calls))
        self.assertEqual("do work", fallback_calls[0]["workflow_prompt"])

    def test_env_vars_disable_skill_api_and_preserve_legacy_per_request_env(self):
        fallback_calls = []

        def fake_run_sandbox_agent(**kwargs):
            fallback_calls.append(kwargs)
            return "legacy result"

        module = _load_execute_skills_module(
            fake_run_sandbox_agent,
            ensure_agentkit_session_endpoint=lambda **_kwargs: self.fail(
                "Skill API should be disabled when env_vars are provided"
            ),
        )

        result = module.execute_skills(
            "do work",
            tool_context=self._tool_context(),
            env_vars={"CUSTOM_VALUE": "custom"},
        )

        self.assertEqual(result, "legacy result")
        self.assertEqual(
            {
                "TOS_SKILLS_DIR": "tos://agentkit-platform-test-account/skills/",
                "CUSTOM_VALUE": "custom",
            },
            fallback_calls[0]["extra_env_vars"],
        )

    def test_legacy_protocol_env_disables_skill_api(self):
        fallback_calls = []

        def fake_run_sandbox_agent(**kwargs):
            fallback_calls.append(kwargs)
            return "legacy result"

        module = _load_execute_skills_module(
            fake_run_sandbox_agent,
            ensure_agentkit_session_endpoint=lambda **_kwargs: self.fail(
                "Skill API should be disabled by VEADK_EXECUTE_SKILLS_PROTOCOL"
            ),
        )

        with patch.dict(
            module.os.environ,
            {"VEADK_EXECUTE_SKILLS_PROTOCOL": "legacy"},
            clear=False,
        ):
            result = module.execute_skills("do work", tool_context=self._tool_context())

        self.assertEqual(result, "legacy result")
        self.assertEqual(1, len(fallback_calls))

    def test_missing_tool_context_keeps_legacy_execution_path(self):
        fallback_calls = []

        def fake_run_sandbox_agent(**kwargs):
            fallback_calls.append(kwargs)
            return "legacy result"

        module = _load_execute_skills_module(
            fake_run_sandbox_agent,
            ensure_agentkit_session_endpoint=lambda **_kwargs: self.fail(
                "Skill API requires a tool_context"
            ),
        )

        result = module.execute_skills("do work", tool_context=None)

        self.assertEqual(result, "legacy result")
        self.assertEqual(1, len(fallback_calls))
        self.assertIsNone(fallback_calls[0]["tool_context"])

    def test_non_compatibility_skill_api_http_error_is_not_swallowed(self):
        class ServerErrorResponse:
            def read(self):
                return b"internal error"

            def close(self):
                return None

        def fake_urlopen(_request, **_kwargs):
            raise module.error.HTTPError(
                url="https://sandbox.test/v1/skills/execute",
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=ServerErrorResponse(),
            )

        fallback_calls = []
        module = _load_execute_skills_module(
            lambda **kwargs: fallback_calls.append(kwargs) or "legacy result",
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            with self.assertRaisesRegex(RuntimeError, "HTTP 500: internal error"):
                module.execute_skills("do work", tool_context=self._tool_context())

        self.assertEqual([], fallback_calls)

    def test_stream_mode_aggregates_text_chunks_from_skill_api_sse(self):
        sse_body = (
            "event: chunk\n"
            'data: {"request_id":"req_1","type":"progress","content":"started","metadata":{}}\n\n'
            "event: chunk\n"
            'data: {"request_id":"req_1","type":"text","content":"hello ","metadata":{}}\n\n'
            "event: chunk\n"
            'data: {"request_id":"req_1","type":"text","content":"world","metadata":{}}\n\n'
            "event: done\n"
            'data: {"request_id":"req_1","type":"progress","content":"done","metadata":{}}\n\n'
        ).encode()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return sse_body

        captured_urls = []

        def fake_urlopen(request, **_kwargs):
            captured_urls.append(request.full_url)
            return FakeResponse()

        module = _load_execute_skills_module(
            lambda **_kwargs: "fallback",
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test/",
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            result = module.execute_skills(
                "do work",
                tool_context=self._tool_context(),
                prefer_stream=True,
            )

        self.assertEqual(result, "hello world")
        self.assertEqual(["https://sandbox.test/v1/skills/stream"], captured_urls)

    def test_stream_mode_raises_skill_api_error_event(self):
        sse_body = (
            "event: error\n"
            'data: {"request_id":"req_1","type":"text","content":"skill failed","metadata":{}}\n\n'
        ).encode()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return sse_body

        module = _load_execute_skills_module(
            lambda **_kwargs: "fallback",
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(
            module.request,
            "urlopen",
            lambda *_args, **_kwargs: FakeResponse(),
        ):
            with self.assertRaisesRegex(RuntimeError, "skill failed"):
                module.execute_skills(
                    "do work",
                    tool_context=self._tool_context(),
                    prefer_stream=True,
                )


if __name__ == "__main__":
    unittest.main()
