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


def test_release_workflow_requires_committed_frozen_uv_lock() -> None:
    repository = Path(__file__).parents[1]
    workflow = (
        repository / ".github" / "workflows" / "publish-studio-release.yaml"
    ).read_text(encoding="utf-8")
    ignored = {
        line.strip()
        for line in (repository / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert (repository / "uv.lock").is_file()
    assert "uv.lock" not in ignored
    assert "uv lock --check" in workflow
    assert workflow.count("uv run --frozen --group dev python") == 2
