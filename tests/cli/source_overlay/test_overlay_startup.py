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
"""Studio bootstrap must let the application select its own ADK installation."""

import json
import os
import subprocess
import sys

import pytest

from veadk.cli.legacy_runtime_recovery import _SITECUSTOMIZE


@pytest.mark.parametrize("system_adk", [False, True])
def test_overlay_does_not_preload_system_adk(tmp_path, system_adk):
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir()
    (bootstrap / "sitecustomize.py").write_text(_SITECUSTOMIZE)
    stale = tmp_path / "system"
    stale.mkdir()
    if system_adk:
        for directory in ("google/adk", "google/adk/apps", "google/adk/tools"):
            package = stale / directory
            package.mkdir(parents=True, exist_ok=True)
            (package / "__init__.py").write_text("")
        (stale / "google/adk/apps/app.py").write_text(
            "class App:\n    def __init__(self, **kwargs): pass\n"
        )
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    for name, value in {
        "managed.json": [],
        "selected.json": [],
        "final.json": [],
        "mcp.json": {},
    }.items():
        (overlay / name).write_text(json.dumps(value))
    marker = tmp_path / "ready"
    script = r"""
import json, os, pathlib, socket, sys
def deny(*args, **kwargs):
    raise AssertionError("offline startup attempted network")
socket.socket.connect = deny
socket.create_connection = deny
preloaded = "google.adk" in sys.modules
sys.path.remove(sys.argv[1])
from google.adk.apps.app import App
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.agents import LlmAgent
assert not preloaded, "bootstrap preloaded application ADK"
root = LlmAgent(name="fixture", tools=[SkillToolset(skills=[])])
app = App(name="fixture", root_agent=root)
assert pathlib.Path(os.environ["VEADK_STUDIO_OVERLAY_READY_FILE"]).read_text() == "ready" + chr(10)
assert getattr(App.__init__, "_veadk_studio_overlay", False)
assert not any(getattr(f, "_veadk_studio_app_observer", False) for f in sys.meta_path)
print(json.dumps({"ready": True, "application_adk_selected": True}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(stale)],
        cwd=tmp_path,
        env={
            "PATH": os.defpath,
            "PYTHONPATH": os.pathsep.join((str(bootstrap), str(stale))),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHON_DOTENV_DISABLED": "1",
            "OTEL_SDK_DISABLED": "true",
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
            "VEADK_STUDIO_SKILL_OVERLAY": str(overlay),
            "VEADK_STUDIO_OVERLAY_READY_FILE": str(marker),
        },
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "ready": True,
        "application_adk_selected": True,
    }


def test_already_loaded_app_hook_is_idempotent(tmp_path, monkeypatch):
    from google.adk.apps.app import App

    monkeypatch.setenv("VEADK_STUDIO_SKILL_OVERLAY", str(tmp_path))
    monkeypatch.setattr(App, "__init__", App.__init__)
    namespace = {}
    exec(compile(_SITECUSTOMIZE, "overlay", "exec"), namespace)
    installed = App.__init__
    namespace["_install"]()
    assert App.__init__ is installed
    assert getattr(installed, "_veadk_studio_overlay", False)


def test_original_import_failure_propagates_and_observer_is_removed(
    tmp_path, monkeypatch
):
    import importlib
    from importlib.abc import Loader
    from importlib.machinery import ModuleSpec

    import google.adk.apps.app  # noqa: F401

    target = "google.adk.apps.app"
    calls = []

    class BrokenLoader(Loader):
        def create_module(self, spec):
            calls.append("create")
            return None

        def exec_module(self, module):
            calls.append("execute")
            raise ValueError("original application import failure")

    class Finder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "google.adk.apps.app":
                return ModuleSpec(fullname, BrokenLoader())
            return None

    monkeypatch.setenv("VEADK_STUDIO_SKILL_OVERLAY", str(tmp_path))
    monkeypatch.delitem(sys.modules, target)
    monkeypatch.setattr(sys, "meta_path", [Finder(), *sys.meta_path])
    namespace = {}
    exec(compile(_SITECUSTOMIZE, "overlay", "exec"), namespace)
    namespace["_install"]()
    assert (
        sum(getattr(f, "_veadk_studio_app_observer", False) for f in sys.meta_path) == 1
    )
    with pytest.raises(ValueError, match="original application import failure"):
        importlib.import_module(target)
    assert calls == ["create", "execute"]
    assert target not in sys.modules
    assert not any(
        getattr(f, "_veadk_studio_app_observer", False) for f in sys.meta_path
    )
