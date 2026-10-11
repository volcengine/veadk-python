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

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "scan_yaml_secrets.py"
SPEC = importlib.util.spec_from_file_location("scan_yaml_secrets", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
scan_yaml_secrets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan_yaml_secrets)


def test_concrete_runtime_api_key_is_reported_without_value(tmp_path, capsys) -> None:
    secret_value = "abcdefghijklmnopqrstuvwxyz123456"
    config = tmp_path / "agentkit.yaml"
    config.write_text(f"runtime_apikey: {secret_value}\n", encoding="utf-8")

    assert scan_yaml_secrets.main([str(config)]) == 1

    output = capsys.readouterr().out
    assert "runtime_apikey" in output
    assert secret_value not in output


def test_example_placeholders_and_env_refs_pass(tmp_path) -> None:
    config = tmp_path / "mpa-create.config.example.yaml"
    config.write_text(
        "runtime_apikey: <runtime-api-key>\n"
        "model-api-key: ${MPA_MODEL_API_KEY}\n"
        "release-token: ${{ secrets.RELEASE_TOKEN }}\n",
        encoding="utf-8",
    )

    assert scan_yaml_secrets.main([str(config)]) == 0


def test_deleted_tracked_yaml_path_is_skipped(tmp_path) -> None:
    missing = tmp_path / "deleted.yaml"

    assert scan_yaml_secrets.should_skip(missing)


def test_non_secret_yaml_passes(tmp_path) -> None:
    config = tmp_path / "workflow.yaml"
    config.write_text(
        "name: example\n"
        "permissions:\n"
        "  id-token: write\n"
        "tokenizer-package: comma-separated-tokens\n",
        encoding="utf-8",
    )

    assert scan_yaml_secrets.main([str(config)]) == 0
