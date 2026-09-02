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

"""Bootstrap the pinned AgentKit CLI before a Studio revision starts."""

from __future__ import annotations

import argparse
from pathlib import Path

from veadk.cli.agentkit_cli import (
    AGENTKIT_CLI_VERSION,
    AgentKitCliError,
    resolve_agentkit_cli,
)


StudioCompanionError = AgentKitCliError


def required_agentkit_cli_version() -> str:
    """Return the immutable native CLI version owned by this VeADK release."""

    return AGENTKIT_CLI_VERSION


def validate_installed_agentkit_cli(*, archive: Path | None = None) -> str:
    """Resolve or install the exact CLI required by Studio."""

    resolve_agentkit_cli(archive=archive)
    return AGENTKIT_CLI_VERSION


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    return parser


def main() -> None:
    """Fail the candidate Studio revision before serving if bootstrap fails."""

    args = _parser().parse_args()
    version = validate_installed_agentkit_cli(archive=args.archive)
    print(f"AgentKit CLI {version} is ready.")


if __name__ == "__main__":
    main()


__all__ = [
    "StudioCompanionError",
    "required_agentkit_cli_version",
    "validate_installed_agentkit_cli",
]
