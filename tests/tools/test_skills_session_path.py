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

from pathlib import Path

from veadk.tools.skills_tools import session_path


def test_default_skills_work_dir_for_linux_and_macos(monkeypatch):
    monkeypatch.delenv("VEADK_SKILLS_WORK_DIR", raising=False)
    monkeypatch.setattr(session_path.platform, "system", lambda: "Linux")

    assert session_path._get_base_path() == Path("/home/gem/veadk_skills/sessions")


def test_skills_work_dir_env_override_expands_user(monkeypatch):
    monkeypatch.setenv("VEADK_SKILLS_WORK_DIR", "~/custom-veadk-sessions")

    assert session_path._get_base_path() == Path("~/custom-veadk-sessions").expanduser()


def test_initialize_session_path_uses_configured_base(tmp_path, monkeypatch):
    monkeypatch.setenv("VEADK_SKILLS_WORK_DIR", str(tmp_path))
    session_path.clear_session_cache()

    path = session_path.initialize_session_path("session-1")

    assert path == tmp_path / "session-1"
    assert (path / "skills").is_dir()
    assert (path / "uploads").is_dir()
    assert (path / "outputs").is_dir()
