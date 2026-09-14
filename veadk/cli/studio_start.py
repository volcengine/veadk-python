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

"""Cold-start entrypoint for the Studio server without the general CLI."""

from __future__ import annotations

import os
import sys


def _bootstrap_provider() -> None:
    provider = (
        os.environ.get("AGENTKIT_CLOUD_PROVIDER")
        or os.environ.get("CLOUD_PROVIDER")
        or "volcengine"
    )
    arguments = sys.argv[1:]
    for index, argument in enumerate(arguments):
        if argument.startswith("--provider="):
            provider = argument.partition("=")[2]
            break
        if argument == "--provider" and index + 1 < len(arguments):
            provider = arguments[index + 1]
            break
    provider = provider.strip().lower()
    if provider == "volces":
        provider = "volcengine"
    if provider not in {"volcengine", "byteplus"}:
        return
    os.environ["AGENTKIT_CLOUD_PROVIDER"] = provider
    os.environ["CLOUD_PROVIDER"] = provider


_bootstrap_provider()

from veadk.cli.cli_frontend import studio  # noqa: E402


def main() -> None:
    """Run only the Studio Click command tree."""
    studio(prog_name="studio")


if __name__ == "__main__":
    main()
