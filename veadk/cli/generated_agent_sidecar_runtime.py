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

"""Launch the installed private Sidecar runtime for Studio debug runs."""

from __future__ import annotations

from importlib import metadata
import sys
from typing import Any


_RUNTIME_DISTRIBUTION = "bytedance-agentkit-harness-sidecar"
_RUNTIME_ENTRY_POINT = "agentkit-harness-sidecar-runtime"
_RUNTIME_MODULE = "veadk.cli.generated_agent_sidecar_runtime"


class GeneratedAgentSidecarRuntimeUnavailable(RuntimeError):
    """The private debug runtime is not installed with a unique entry point."""


def _installed_runtime_entry_point() -> metadata.EntryPoint:
    try:
        distribution = metadata.distribution(_RUNTIME_DISTRIBUTION)
    except metadata.PackageNotFoundError as error:
        raise GeneratedAgentSidecarRuntimeUnavailable(
            "Harness Sidecar debug runtime is not installed"
        ) from error
    matches = [
        entry_point
        for entry_point in distribution.entry_points
        if entry_point.group == "console_scripts"
        and entry_point.name == _RUNTIME_ENTRY_POINT
    ]
    if len(matches) != 1:
        raise GeneratedAgentSidecarRuntimeUnavailable(
            "Harness Sidecar debug runtime entry point is unavailable"
        )
    return matches[0]


def installed_harness_sidecar_runtime_command() -> tuple[str, ...]:
    """Return a command that resolves the private entry point at execution time."""

    _installed_runtime_entry_point()
    return (sys.executable, "-m", _RUNTIME_MODULE)


def main() -> Any:
    """Delegate to the trusted console entry point from the private distribution."""

    return _installed_runtime_entry_point().load()()


if __name__ == "__main__":
    raise SystemExit(main())
