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

import sys
from pathlib import Path

from packaging.requirements import Requirement

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def test_studio_requires_agentkit_sdk_with_tos_credential_type() -> None:
    project = Path(__file__).resolve().parents[2]
    metadata = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    requirement = next(
        Requirement(value)
        for value in metadata["project"]["dependencies"]
        if Requirement(value).name == "agentkit-sdk-python"
    )

    assert requirement.specifier.contains("0.8.5")
    assert not requirement.specifier.contains("0.8.4")
