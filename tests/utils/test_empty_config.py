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
"""Regression tests for empty YAML configuration files."""

import pytest

from veadk.utils.misc import set_envs


@pytest.mark.parametrize(
    "content", ["", "# Configuration is supplied by environment.\n", "---\n"]
)
def test_set_envs_accepts_empty_yaml(tmp_path, content):
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")

    assert set_envs(str(path)) == ({}, {})


def test_set_envs_keeps_nested_config_and_environment_precedence(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("scout_regression:\n  option: configured\n", encoding="utf-8")
    monkeypatch.setenv("SCOUT_REGRESSION_OPTION", "environment")

    config, environments = set_envs(str(path))

    assert config == {"scout_regression": {"option": "configured"}}
    assert environments == {"SCOUT_REGRESSION_OPTION": "environment"}
