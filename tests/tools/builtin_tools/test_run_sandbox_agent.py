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
import os
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
    fake_auth = types.ModuleType("veadk.utils.auth")
    fake_auth.TIP_TOKEN_KEY_ENV = "TIP_TOKEN_KEY"
    fake_auth.TIP_TOKEN_KEY_METADATA_KEY = "tip_token_key"
    fake_auth.TIP_TOKEN_KEY_STATE_KEY = "TIP_TOKEN_KEY"
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
        "veadk.utils.auth": fake_auth,
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

    def test_redacts_tip_token_key_from_echoed_sandbox_response(self):
        response = {
            "Result": {"Result": "runner code contains {'TIP_TOKEN_KEY': 'secret-key'}"}
        }

        redacted = self.module._redact_sensitive_env_values(
            response,
            {"TIP_TOKEN_KEY": "secret-key", "CUSTOM_VALUE": "visible"},
        )

        self.assertNotIn("secret-key", str(redacted))
        self.assertIn("<redacted>", str(redacted))

    def test_redacts_tip_token_key_from_success_output(self):
        tool_context = types.SimpleNamespace(
            _invocation_context=types.SimpleNamespace(
                session=types.SimpleNamespace(id="session"),
                agent=types.SimpleNamespace(name="agent"),
                user_id="user",
            ),
            state={},
        )
        response = {
            "Result": {
                "Result": (
                    '{"success": true, "data": {"outputs": '
                    '[{"text": "printed secret-key"}]}}'
                )
            }
        }

        with patch.object(
            self.module,
            "invoke_agentkit_run_code",
            return_value=response,
        ):
            result = self.module.run_sandbox_agent(
                workflow_prompt="do work",
                tool_id="tool",
                tool_context=tool_context,
                extra_env_vars={"TIP_TOKEN_KEY": "secret-key"},
            )

        self.assertEqual(result, "printed <redacted>")


class TestExecuteSkillsSkillApi(unittest.TestCase):
    def _tool_context(self):
        invocation_context = types.SimpleNamespace(
            session=types.SimpleNamespace(id="session-1"),
            agent=types.SimpleNamespace(name="agent"),
            user_id="user",
            run_config=types.SimpleNamespace(
                custom_metadata={"tip_token_key": "tip-from-metadata"}
            ),
        )
        return types.SimpleNamespace(
            state={},
            run_config=invocation_context.run_config,
            _invocation_context=invocation_context,
        )

    def _tool_context_without_request_token(self):
        invocation_context = types.SimpleNamespace(
            session=types.SimpleNamespace(id="session-1"),
            agent=types.SimpleNamespace(name="agent"),
            user_id="user",
            run_config=types.SimpleNamespace(custom_metadata={}),
        )
        return types.SimpleNamespace(
            state={"TIP_TOKEN_KEY": "stale-session-key"},
            run_config=invocation_context.run_config,
            _invocation_context=invocation_context,
        )

    def test_prefers_new_skill_execute_api_when_endpoint_is_available(self):
        captured_requests = []
        health_endpoints = []
        session_kwargs = []

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

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **kwargs: (
                session_kwargs.append(kwargs) or "https://sandbox.test"
            ),
            wait_for_skill_api_health=lambda **kwargs: health_endpoints.append(
                kwargs["endpoint"]
            ),
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            result = module.execute_skills("do work", tool_context=self._tool_context())

        self.assertEqual(result, "api result")
        self.assertTrue(session_kwargs[0]["wait_until_ready"])
        self.assertEqual(["https://sandbox.test"], health_endpoints)
        self.assertEqual(1, len(captured_requests))
        request_obj, timeout = captured_requests[0]
        self.assertEqual("https://sandbox.test/v1/skills/execute", request_obj.full_url)
        self.assertEqual(900, timeout)
        self.assertEqual("POST", request_obj.get_method())
        self.assertEqual("tip-from-metadata", request_obj.headers["X-tip-token-key"])
        self.assertIn(b'"prompt": "do work"', request_obj.data)

    def test_skill_api_does_not_reuse_stale_session_state_tip_token_key(self):
        captured_requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"content": "api result"}'

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(
            module.request,
            "urlopen",
            lambda request, **_kwargs: captured_requests.append(request)
            or FakeResponse(),
        ):
            result = module.execute_skills(
                "do work",
                tool_context=self._tool_context_without_request_token(),
            )

        self.assertEqual(result, "api result")
        self.assertNotIn(
            "X-tip-token-key",
            captured_requests[0].headers,
        )

    def test_skill_api_ignores_process_env_tip_token_key_by_default(self):
        captured_requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"content": "api result"}'

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with (
            patch.dict(os.environ, {"TIP_TOKEN_KEY": "process-env-key"}),
            patch.object(
                module.request,
                "urlopen",
                lambda request, **_kwargs: captured_requests.append(request)
                or FakeResponse(),
            ),
        ):
            result = module.execute_skills(
                "do work",
                tool_context=self._tool_context_without_request_token(),
            )

        self.assertEqual(result, "api result")
        self.assertNotIn(
            "X-tip-token-key",
            captured_requests[0].headers,
        )

    def test_health_check_retries_502_until_upstream_is_ready(self):
        attempts = []

        class HealthyResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

        class ErrorResponse:
            def read(self):
                return b"bad gateway"

            def close(self):
                return None

        module = _load_execute_skills_module(wait_for_skill_api_health=None)

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
            module._wait_for_skill_api_health(endpoint="https://sandbox.test")

        self.assertEqual(
            [
                ("https://sandbox.test/v1/skills/healthz", "GET"),
                ("https://sandbox.test/v1/skills/healthz", "GET"),
            ],
            attempts,
        )
        sleep.assert_called_once_with(1.0)

    def test_health_check_allows_images_without_health_endpoint(self):
        class NotFoundResponse:
            def read(self):
                return b"not found"

            def close(self):
                return None

        module = _load_execute_skills_module(wait_for_skill_api_health=None)

        def fake_urlopen(req, **_kwargs):
            raise module.error.HTTPError(
                url=req.full_url,
                code=404,
                msg="Not Found",
                hdrs={},
                fp=NotFoundResponse(),
            )

        with patch.object(module.request, "urlopen", fake_urlopen):
            module._wait_for_skill_api_health(endpoint="https://sandbox.test")

    def test_env_vars_use_legacy_runcode_execution(self):
        captured_kwargs = {}

        def fake_run_sandbox_agent(**kwargs):
            captured_kwargs.update(kwargs)
            return "legacy result"

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: self.fail(
                "Skill API must not be used when env_vars are provided"
            ),
            run_sandbox_agent=fake_run_sandbox_agent,
        )

        result = module.execute_skills(
            "do work",
            tool_context=self._tool_context(),
            env_vars={"CUSTOM_VALUE": "custom", "TOS_SKILLS_DIR": ""},
        )

        self.assertEqual(result, "legacy result")
        self.assertEqual(
            {
                "CUSTOM_VALUE": "custom",
                "TOS_SKILLS_DIR": "",
                "TIP_TOKEN_KEY": "tip-from-metadata",
            },
            captured_kwargs["extra_env_vars"],
        )

    def test_legacy_runcode_execution_injects_tip_token_key_from_metadata(self):
        captured_kwargs = {}

        def fake_run_sandbox_agent(**kwargs):
            captured_kwargs.update(kwargs)
            return "legacy result"

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: self.fail(
                "Skill API must not be used when env_vars are provided"
            ),
            run_sandbox_agent=fake_run_sandbox_agent,
        )

        result = module.execute_skills(
            "do work",
            tool_context=self._tool_context(),
            env_vars={"CUSTOM_VALUE": "custom", "TIP_TOKEN_KEY": "model-provided"},
        )

        self.assertEqual(result, "legacy result")
        self.assertEqual(
            {
                "CUSTOM_VALUE": "custom",
                "TIP_TOKEN_KEY": "tip-from-metadata",
                "TOS_SKILLS_DIR": "tos://agentkit-platform-test-account/skills/",
            },
            captured_kwargs["extra_env_vars"],
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

    def test_requires_sandbox_upgrade_when_skill_api_returns_404(self):
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

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            with self.assertRaisesRegex(
                RuntimeError,
                r"HTTP 404.*(?:升级|upgrade).*Skill",
            ):
                module.execute_skills("do work", tool_context=self._tool_context())

    def test_requires_sandbox_upgrade_when_skill_api_returns_405(self):
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

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            with self.assertRaisesRegex(
                RuntimeError,
                r"HTTP 405.*(?:升级|upgrade).*Skill",
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

        module = _load_execute_skills_module(
            ensure_agentkit_session_endpoint=lambda **_kwargs: "https://sandbox.test",
        )

        with patch.object(module.request, "urlopen", fake_urlopen):
            with self.assertRaisesRegex(RuntimeError, "HTTP 500: internal error"):
                module.execute_skills("do work", tool_context=self._tool_context())

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
                raise AssertionError("stream response must not be buffered with read()")

            def __iter__(self):
                return iter(sse_body.splitlines(keepends=True))

        captured_urls = []

        def fake_urlopen(request, **_kwargs):
            captured_urls.append(request.full_url)
            return FakeResponse()

        module = _load_execute_skills_module(
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
                raise AssertionError("stream response must not be buffered with read()")

            def __iter__(self):
                return iter(sse_body.splitlines(keepends=True))

        module = _load_execute_skills_module(
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
