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

import os
import sys
import types

from veadk.utils.misc import get_agents_dir, get_agent_dir


class GetAgentsDirTest:
    def test_get_agents_dir_from_main_file(monkeypatch):
        """
        Case 1: __main__.__file__ exists (common in CLI or uv run environments)
        """
        fake_main = types.SimpleNamespace(__file__="/tmp/project/testapp/agent.py")
        monkeypatch.setitem(sys.modules, "__main__", fake_main)

        result = get_agents_dir()
        assert result == "/tmp/project"
        result = get_agent_dir()
        assert result == "/tmp/project/testapp"

    def test_get_agents_dir_from_sys_argv(monkeypatch):
        """
        Case 2: Fallback to sys.argv[0]
        """
        fake_main = types.SimpleNamespace()
        monkeypatch.setitem(sys.modules, "__main__", fake_main)
        monkeypatch.setattr(sys, "argv", ["/tmp/project/testapp/agent.py"])

        result = get_agents_dir()
        assert result == "/tmp/project"
        result = get_agent_dir()
        assert result == "/tmp/project/testapp"

    def test_get_agents_dir_from_cwd(monkeypatch, tmp_path):
        """
        Case 3: Fallback to current working directory (REPL or no file context)
        """
        fake_main = types.SimpleNamespace()
        monkeypatch.setitem(sys.modules, "__main__", fake_main)
        monkeypatch.setattr(sys, "argv", [])

        fake_cwd = tmp_path / "some_dir"
        fake_cwd.mkdir()

        monkeypatch.setattr(os, "getcwd", lambda: str(fake_cwd))
        result = get_agents_dir()

        # should return the parent of fake_cwd
        assert result == str(tmp_path)
        result = get_agent_dir()
        assert result == str(tmp_path / "some_dir")
