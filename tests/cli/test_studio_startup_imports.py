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

import subprocess
import sys
from pathlib import Path


def test_studio_startup_modules_do_not_eagerly_load_generated_cloud_models() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import importlib
import sys

for module in (
    "frontend.server.user_management.directory",
    "frontend.server.skills.reviewer_profiles",
    "veadk.cli.studio_vpc_network",
):
    importlib.import_module(module)

unexpected = sorted(
    name
    for name in sys.modules
    if name.startswith((
        "volcenginesdkid",
        "volcenginesdkvefaas",
        "volcenginesdkvpc",
    ))
)
if unexpected:
    raise SystemExit("generated cloud SDKs loaded during Studio startup")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
