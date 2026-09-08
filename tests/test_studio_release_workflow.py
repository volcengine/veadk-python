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

"""Regression tests for the Studio release workflow."""

from pathlib import Path
from typing import Any

import yaml


def _publish_job() -> dict[str, Any]:
    workflow_path = (
        Path(__file__).parents[1]
        / ".github"
        / "workflows"
        / "publish-studio-release.yaml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    return workflow["jobs"]["publish"]


def test_thin_bundle_input_is_scoped_to_supported_provider() -> None:
    publish = _publish_job()
    providers = {
        entry["provider"]: entry for entry in publish["strategy"]["matrix"]["include"]
    }

    assert providers["volcengine"]["thin_bundles"] == "${{ inputs.thin_bundles }}"
    assert providers["byteplus"]["thin_bundles"] is False
    assert publish["env"]["RELEASE_THIN_BUNDLES"] == "${{ matrix.thin_bundles }}"
