# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10.
    import tomli as tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOOGLE_ADK_BASELINE = "google-adk>=2.7.0,<2.8.0"
GOOGLE_ADK_EVAL_BASELINE = "google-adk[eval]>=2.7.0,<2.8.0"
AGENTKIT_BASELINE = "agentkit-sdk-python>=0.8.5"
OPENTELEMETRY_EXPORTER_BASELINE = "opentelemetry-exporter-otlp>=1.37.0"


def _pyproject() -> dict[str, object]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_project_dependency_metadata_uses_runtime_compatibility_baseline() -> None:
    pyproject = _pyproject()
    dependencies = pyproject["project"]["dependencies"]
    optional = pyproject["project"]["optional-dependencies"]

    assert GOOGLE_ADK_BASELINE in dependencies
    assert OPENTELEMETRY_EXPORTER_BASELINE in dependencies
    assert AGENTKIT_BASELINE in dependencies
    assert GOOGLE_ADK_EVAL_BASELINE in optional["eval"]
    assert AGENTKIT_BASELINE in optional["harness-sidecar"]


def test_lock_metadata_matches_project_dependency_baseline() -> None:
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert '{ name = "agentkit-sdk-python", specifier = ">=0.8.5" }' in lock
    assert (
        '{ name = "agentkit-sdk-python", marker = "extra == '
        '\'harness-sidecar\'", specifier = ">=0.8.5" }'
    ) in lock
    assert '{ name = "google-adk", specifier = ">=2.7.0,<2.8.0" }' in lock
    assert (
        '{ name = "google-adk", extras = ["eval"], marker = "extra == '
        '\'eval\'", specifier = ">=2.7.0,<2.8.0" }'
    ) in lock
    assert '{ name = "opentelemetry-exporter-otlp", specifier = ">=1.37.0" }' in lock
