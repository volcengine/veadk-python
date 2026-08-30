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

"""Local Python tool compilation and dependency checks."""

from __future__ import annotations

import importlib.metadata
import sys
from types import ModuleType
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from packaging.requirements import Requirement

from veadk.tools.builtin_tools.create_agent.models import PythonToolSpec


def compile_python_tool(spec: PythonToolSpec) -> Callable[..., Any]:
    """Compile caller-provided source after checking the current environment."""
    missing = []
    for value in spec.dependencies:
        requirement = Requirement(value)
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        try:
            installed = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(value)
            continue
        if requirement.specifier and installed not in requirement.specifier:
            missing.append(f"{value} (installed: {installed})")
    if missing:
        raise ValueError(
            f"Python tool '{spec.name}' has unavailable dependencies: {missing}. "
            "Dependencies are checked in the current interpreter and are not "
            "installed automatically."
        )

    module_name = f"veadk.dynamic_tools.{spec.name}_{uuid4().hex}"
    module = ModuleType(module_name)
    module.__dict__["__builtins__"] = __builtins__
    sys.modules[module_name] = module
    try:
        exec(
            compile(spec.code, f"<{spec.name}>", "exec"),
            module.__dict__,
            module.__dict__,
        )
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    entrypoint = spec.entrypoint or spec.name
    function = module.__dict__.get(entrypoint)
    if not callable(function):
        raise ValueError(
            f"Python tool '{spec.name}' does not define callable '{entrypoint}'."
        )
    function.__name__ = spec.name
    function.__doc__ = spec.description
    return function
