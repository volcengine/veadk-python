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
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_agentkit_module():
    module_path = (
        Path(__file__).resolve().parents[3]
        / "veadk"
        / "tools"
        / "builtin_tools"
        / "_agentkit.py"
    )

    fake_veadk = types.ModuleType("veadk")
    fake_veadk.__path__ = []  # type: ignore[attr-defined]
    fake_auth = types.ModuleType("veadk.auth")
    fake_auth.__path__ = []  # type: ignore[attr-defined]
    fake_veauth = types.ModuleType("veadk.auth.veauth")
    fake_veauth.__path__ = []  # type: ignore[attr-defined]
    fake_veauth_utils = types.ModuleType("veadk.auth.veauth.utils")
    fake_config = types.ModuleType("veadk.config")
    fake_utils = types.ModuleType("veadk.utils")
    fake_utils.__path__ = []  # type: ignore[attr-defined]
    fake_logger = types.ModuleType("veadk.utils.logger")
    fake_sign = types.ModuleType("veadk.utils.volcengine_sign")

    def fake_getenv(env_name, default_value="", allow_false_values=False):
        value = os.getenv(env_name, default_value)
        if allow_false_values:
            return value
        if value:
            return value
        raise ValueError(
            f"The environment variable `{env_name}` not exists. Please set this in your environment variable or config.yaml."
        )

    class _FakeCredential:
        access_key_id = "ak"
        secret_access_key = "sk"
        session_token = "token"

    class _FakeLogger:
        def debug(self, *_args, **_kwargs):
            return None

        def warning(self, *_args, **_kwargs):
            return None

        def error(self, *_args, **_kwargs):
            return None

    fake_veauth_utils.get_credential_from_vefaas_iam = lambda: _FakeCredential()
    fake_config.getenv = fake_getenv
    fake_logger.get_logger = lambda _name: _FakeLogger()
    fake_sign.ve_request = lambda **_kwargs: {"Result": {"AccountId": "test-account"}}

    stub_modules = {
        "veadk": fake_veadk,
        "veadk.auth": fake_auth,
        "veadk.auth.veauth": fake_veauth,
        "veadk.auth.veauth.utils": fake_veauth_utils,
        "veadk.config": fake_config,
        "veadk.utils": fake_utils,
        "veadk.utils.logger": fake_logger,
        "veadk.utils.volcengine_sign": fake_sign,
    }

    with patch.dict(sys.modules, stub_modules):
        spec = importlib.util.spec_from_file_location(
            "test_agentkit_module", module_path
        )
        module = importlib.util.module_from_spec(spec)
        assert spec is not None
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module


class TestResolveAgentkitToolId(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agentkit_module = _load_agentkit_module()

    def setUp(self):
        self.env_patcher = patch.dict(
            os.environ,
            {},
            clear=False,
        )
        self.env_patcher.start()
        for env_name in [
            "AGENTKIT_TOOL_ID",
            "AGENTKIT_TOOL_ID_SCRIPT",
            "AGENTKIT_TOOL_ID_SKILLS",
            "AGENTKIT_TOOL_ID_OPENCODE",
        ]:
            os.environ.pop(env_name, None)

    def tearDown(self):
        self.env_patcher.stop()

    def test_resolve_prefers_script_tool_id(self):
        os.environ["AGENTKIT_TOOL_ID_SCRIPT"] = "script-tool"
        os.environ["AGENTKIT_TOOL_ID"] = "default-tool"

        tool_id = self.agentkit_module.resolve_agentkit_tool_id(
            "AGENTKIT_TOOL_ID_SCRIPT"
        )

        self.assertEqual(tool_id, "script-tool")

    def test_resolve_prefers_skills_tool_id(self):
        os.environ["AGENTKIT_TOOL_ID_SKILLS"] = "skills-tool"
        os.environ["AGENTKIT_TOOL_ID"] = "default-tool"

        tool_id = self.agentkit_module.resolve_agentkit_tool_id(
            "AGENTKIT_TOOL_ID_SKILLS"
        )

        self.assertEqual(tool_id, "skills-tool")

    def test_resolve_prefers_opencode_tool_id(self):
        os.environ["AGENTKIT_TOOL_ID_OPENCODE"] = "opencode-tool"
        os.environ["AGENTKIT_TOOL_ID"] = "default-tool"

        tool_id = self.agentkit_module.resolve_agentkit_tool_id(
            "AGENTKIT_TOOL_ID_OPENCODE"
        )

        self.assertEqual(tool_id, "opencode-tool")

    def test_resolve_falls_back_to_default_tool_id(self):
        os.environ["AGENTKIT_TOOL_ID"] = "default-tool"

        tool_id = self.agentkit_module.resolve_agentkit_tool_id()

        self.assertEqual(tool_id, "default-tool")

    def test_resolve_raises_when_all_tool_ids_missing(self):
        with self.assertRaisesRegex(ValueError, "AGENTKIT_TOOL_ID"):
            self.agentkit_module.resolve_agentkit_tool_id("AGENTKIT_TOOL_ID_SCRIPT")


class TestInvokeAgentkitExecBash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agentkit_module = _load_agentkit_module()

    def test_builds_exec_bash_invoke_tool_request(self):
        with patch.object(
            self.agentkit_module,
            "ve_request",
            return_value={"Result": {"Result": "shell output"}},
        ) as ve_request:
            result = self.agentkit_module.invoke_agentkit_exec_bash(
                tool_id="shell-tool",
                tool_user_session_id="kk",
                command="echo hello",
                exec_dir="/tmp",
                env={"DEMO_ENV": "from-invoke-tool"},
                timeout=30,
                hard_timeout=60,
                max_output_length=30000,
                ttl=1800,
            )

        self.assertEqual(result, {"Result": {"Result": "shell output"}})
        request_body = ve_request.call_args.kwargs["request_body"]
        self.assertEqual(request_body["ToolId"], "shell-tool")
        self.assertEqual(request_body["OperationType"], "ExecBash")
        self.assertEqual(request_body["UserSessionId"], "kk")
        self.assertEqual(request_body["Ttl"], 1800)
        self.assertEqual(
            json.loads(request_body["OperationPayload"]),
            {
                "command": "echo hello",
                "exec_dir": "/tmp",
                "env": {"DEMO_ENV": "from-invoke-tool"},
                "timeout": 30,
                "hard_timeout": 60,
                "max_output_length": 30000,
            },
        )


if __name__ == "__main__":
    unittest.main()
