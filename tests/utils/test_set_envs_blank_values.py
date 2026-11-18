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

import os

from veadk.utils.misc import set_envs


def _write_config(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_blank_yaml_values_are_not_exported_as_none(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    for name in ("MODEL_AGENT_NAME", "MODEL_AGENT_API_KEY", "MODEL_AGENT_API_BASE"):
        monkeypatch.delenv(name, raising=False)
    path = _write_config(
        tmp_path,
        "model:\n  agent:\n    name: doubao\n    api_key: \n    api_base:\n",
    )

    _, exported = set_envs(path)

    assert os.environ["MODEL_AGENT_NAME"] == "doubao"
    assert "MODEL_AGENT_API_KEY" not in os.environ
    assert "MODEL_AGENT_API_BASE" not in os.environ
    assert exported == {"MODEL_AGENT_NAME": "doubao"}


def test_blank_yaml_value_keeps_model_config_defaults(tmp_path, monkeypatch):
    from veadk.configs.model_configs import ModelConfig
    from veadk.consts import DEFAULT_MODEL_AGENT_API_BASE

    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.delenv("MODEL_AGENT_API_BASE", raising=False)
    path = _write_config(tmp_path, "model:\n  agent:\n    api_base:\n")

    set_envs(path)

    assert ModelConfig().api_base == DEFAULT_MODEL_AGENT_API_BASE


def test_non_blank_scalars_are_still_exported(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    for name in ("A_EMPTY", "A_FLAG", "A_COUNT"):
        monkeypatch.delenv(name, raising=False)
    path = _write_config(tmp_path, 'a:\n  empty: ""\n  flag: false\n  count: 0\n')

    _, exported = set_envs(path)

    assert exported == {"A_EMPTY": "", "A_FLAG": "False", "A_COUNT": "0"}
    assert os.environ["A_FLAG"] == "False"
