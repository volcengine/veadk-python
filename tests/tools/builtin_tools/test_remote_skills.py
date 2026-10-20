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

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_remote_skills_module(
    *,
    invoke_skill=lambda *_args, **_kwargs: {
        "kind": "task",
        "id": "task-1",
        "status": {"state": "working"},
    },
    poll_skill=lambda *_args, **_kwargs: {
        "kind": "task",
        "id": "task-1",
        "status": {"state": "completed"},
        "artifacts": [{"parts": [{"kind": "text", "text": "remote result"}]}],
    },
):
    module_path = (
        Path(__file__).resolve().parents[3]
        / "veadk"
        / "tools"
        / "builtin_tools"
        / "remote_skills.py"
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
    fake_execute_skills = types.ModuleType("veadk.tools.builtin_tools.execute_skills")
    fake_execute_skills._A2A_MAX_POLL_INTERVAL = 16.0
    fake_execute_skills._A2A_POLL_INTERVAL = 2.0
    fake_execute_skills._A2A_TERMINAL_STATES = frozenset(
        {
            "completed",
            "failed",
            "canceled",
            "rejected",
            "input-required",
            "auth-required",
        }
    )
    fake_execute_skills._a2a_task_id = lambda task: task["id"]
    fake_execute_skills._a2a_task_result_text = lambda task: "".join(
        part["text"]
        for artifact in task.get("artifacts", [])
        for part in artifact.get("parts", [])
        if isinstance(part.get("text"), str)
    )
    fake_execute_skills._a2a_task_state = lambda task: task.get("status", {}).get(
        "state"
    )

    def fake_validate_timeout(timeout):
        if type(timeout) is not int or not 1 <= timeout <= 1800:
            raise ValueError("timeout must be an integer between 1 and 1800 seconds")

    fake_execute_skills._validate_timeout = fake_validate_timeout
    fake_invoke_skill = types.ModuleType("veadk.tools.builtin_tools.invoke_skill")
    fake_invoke_skill.invoke_skill = invoke_skill
    fake_poll_skill = types.ModuleType("veadk.tools.builtin_tools.poll_skill")
    fake_poll_skill.poll_skill = poll_skill

    stub_modules = {
        "google": fake_google,
        "google.adk": fake_google_adk,
        "google.adk.tools": fake_google_adk_tools,
        "veadk": fake_veadk,
        "veadk.tools": fake_tools,
        "veadk.tools.builtin_tools": fake_builtin_tools,
        "veadk.tools.builtin_tools.execute_skills": fake_execute_skills,
        "veadk.tools.builtin_tools.invoke_skill": fake_invoke_skill,
        "veadk.tools.builtin_tools.poll_skill": fake_poll_skill,
    }

    with patch.dict(sys.modules, stub_modules):
        spec = importlib.util.spec_from_file_location(
            "test_remote_skills_module", module_path
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


class RemoteSkillsTest(unittest.TestCase):
    def test_loads_remote_skill_manifest_from_json(self) -> None:
        module = _load_remote_skills_module()
        manifest = {
            "remote_skills": [
                {
                    "name": "report_writer",
                    "display_name": "报告撰写",
                    "description": "生成技术报告",
                    "input_schema": {"type": "object"},
                    "timeout_seconds": 60,
                }
            ]
        }

        definitions = module.load_remote_skill_definitions(json.dumps(manifest))

        self.assertEqual(1, len(definitions))
        self.assertEqual("report_writer", definitions[0].name)
        self.assertEqual("生成技术报告", definitions[0].description)
        self.assertEqual(60, definitions[0].timeout)

    def test_loads_remote_skill_manifest_from_file(self) -> None:
        module = _load_remote_skills_module()
        manifest = {
            "remote_skills": [
                {
                    "name": "report_writer",
                    "description": "生成技术报告",
                    "input_schema": {"type": "object"},
                }
            ]
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "remote-skills.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            definitions = module.load_remote_skill_definitions(path)

        self.assertEqual("report_writer", definitions[0].name)
        self.assertEqual(1800, definitions[0].timeout)

    def test_rejects_duplicate_names(self) -> None:
        module = _load_remote_skills_module()
        manifest = {
            "remote_skills": [
                {
                    "name": "report_writer",
                    "description": "生成技术报告",
                    "input_schema": {"type": "object"},
                },
                {
                    "name": "report_writer",
                    "description": "生成技术报告",
                    "input_schema": {"type": "object"},
                },
            ]
        }

        with self.assertRaisesRegex(ValueError, "duplicate"):
            module.load_remote_skill_definitions(json.dumps(manifest))

    def test_rejects_missing_input_schema(self) -> None:
        module = _load_remote_skills_module()
        manifest = {
            "remote_skills": [
                {
                    "name": "report_writer",
                    "description": "生成技术报告",
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "input_schema"):
            module.load_remote_skill_definitions(json.dumps(manifest))

    def test_remote_skill_tool_allows_custom_executor(self) -> None:
        calls = []

        def fake_executor(workflow_prompt, **kwargs):
            calls.append((workflow_prompt, kwargs))
            return "remote result"

        module = _load_remote_skills_module()
        definition = module.RemoteSkillDefinition(
            name="report_writer",
            description="生成技术报告",
            input_schema={"type": "object"},
            timeout=300,
        )

        tool = module.build_remote_skill_tools([definition], executor=fake_executor)[0]
        result = tool("写一份设计", {"format": "doc"}, object())

        self.assertEqual("remote result", result)
        self.assertEqual("report_writer", tool.__name__)
        self.assertIn("生成技术报告", tool.__doc__)
        self.assertNotIn("SKILL.md", tool.__doc__)
        workflow_prompt, kwargs = calls[0]
        query_input = json.loads(workflow_prompt)
        self.assertEqual("report_writer", query_input["skill_name"])
        self.assertEqual("写一份设计", query_input["query"])
        self.assertEqual({"format": "doc"}, query_input["arguments"])
        self.assertEqual(300, kwargs["timeout"])

    def test_remote_skill_tool_uses_invoke_poll_by_default(self) -> None:
        calls = []

        def fake_invoke_skill(workflow_prompt, **kwargs):
            calls.append(("invoke", workflow_prompt, kwargs))
            return {
                "kind": "task",
                "id": "task-1",
                "status": {"state": "working"},
            }

        def fake_poll_skill(task_id, **kwargs):
            calls.append(("poll", task_id, kwargs))
            return {
                "kind": "task",
                "id": "task-1",
                "status": {"state": "completed"},
                "artifacts": [{"parts": [{"kind": "text", "text": "done"}]}],
            }

        module = _load_remote_skills_module(
            invoke_skill=fake_invoke_skill,
            poll_skill=fake_poll_skill,
        )
        definition = module.RemoteSkillDefinition(
            name="report_writer",
            description="生成技术报告",
            input_schema={"type": "object"},
            timeout=300,
        )

        with patch.object(module.time, "sleep") as sleep:
            tool = module.build_remote_skill_tools([definition])[0]
            result = tool("写一份设计", {"format": "doc"}, object())

        self.assertEqual("done", result)
        self.assertEqual("invoke", calls[0][0])
        self.assertEqual("poll", calls[1][0])
        self.assertEqual("task-1", calls[1][1])
        self.assertEqual(300, calls[0][2]["timeout"])
        self.assertGreaterEqual(calls[1][2]["timeout"], 1)
        self.assertLessEqual(calls[1][2]["timeout"], 300)
        sleep.assert_called_once_with(2.0)

    def test_remote_skill_tool_signature_hides_context_as_optional(self) -> None:
        module = _load_remote_skills_module()
        definition = module.RemoteSkillDefinition(
            name="report_writer",
            description="生成技术报告",
            input_schema={"type": "object"},
        )

        tool = module.build_remote_skill_tools([definition])[0]
        signature = inspect.signature(tool)

        self.assertEqual(
            ["query", "arguments", "tool_context"], list(signature.parameters)
        )
        self.assertIsNone(signature.parameters["arguments"].default)
        self.assertIsNone(signature.parameters["tool_context"].default)


if __name__ == "__main__":
    unittest.main()
