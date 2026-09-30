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

"""Packaged capacities must be validated before any capacity can be used."""

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from veadk.context import model_capacity as capacity


@pytest.fixture
def config():
    return {
        "schema_version": 1,
        "models": [
            {
                "provider": "example",
                "model_id": "example-v1",
                "context_window": 8000,
                "max_input_tokens": 7000,
                "max_output_tokens": 2000,
                "source": "https://example.com/models/example-v1",
                "verified_on": "2026-09-30",
                "default_output_reserve": 1000,
                "aliases": ["example-current"],
                "default_answer_tokens": None,
                "reasoning_token_reserve": 0,
                "answer_only_max_tokens": False,
                "ark_thinking_controls": False,
                "openai_transport": False,
            }
        ],
    }


def test_capacity_configuration_resource_matches_public_lookup():
    from importlib.resources import files

    data = json.loads(
        files("veadk.context").joinpath("model_capacities.json").read_text()
    )
    assert data["schema_version"] == 1 and data["models"]
    rows = json.loads(json.dumps([asdict(row) for row in capacity.MODEL_CAPACITIES]))
    assert rows == data["models"]
    for row in data["models"]:
        result = capacity.get_model_capacity(f"{row['provider']}/{row['model_id']}")
        assert json.loads(json.dumps(result)) == row


def test_capacity_configuration_package_manifest_is_explicit():
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((root / "pyproject.toml").read_text())
    assert (
        "model_capacities.json"
        in config["tool"]["setuptools"]["package-data"]["veadk.context"]
    )


def test_capacity_configuration_resource_is_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "model_capacities.json").write_text("not JSON")
    assert capacity._load_capacities() == capacity.MODEL_CAPACITIES


def test_configuration_values_and_aliases_drive_resolution(config):
    config["models"][0]["context_window"] = 9000
    rows = capacity._parse_capacities(json.dumps(config))
    lookup = capacity._capacity_lookup(rows)
    assert lookup["example-current"].context_window == 9000
    assert lookup["example/example-v1"].context_window == 9000
    assert "openai/example-v1" not in lookup
    assert rows[0].aliases == ("example-current",)


def test_openai_transport_requires_explicit_row_configuration(config):
    rows = capacity._parse_capacities(json.dumps(config))
    assert "openai/example-v1" not in capacity._capacity_lookup(rows)
    config["models"][0]["openai_transport"] = True
    rows = capacity._parse_capacities(json.dumps(config))
    lookup = capacity._capacity_lookup(rows)
    assert lookup["openai/example-v1"] == rows[0]
    assert lookup["openai/example-current"] == rows[0]
    assert "unreviewed/example-v1" not in lookup


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "[]",
        "null",
        '{"schema_version":1,"schema_version":1,"models":[]}',
        '{"schema_version":1,"models":[{"provider":"a","provider":"b"}]}',
    ],
)
def test_capacity_configuration_rejects_malformed_json(raw):
    with pytest.raises(ValueError, match="invalid_model_capacity_config"):
        capacity._parse_capacities(raw)


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("schema_version", "1"),
        ("models", []),
        ("models", {}),
        ("models", [None]),
        ("extra", "field"),
    ],
)
def test_capacity_configuration_rejects_invalid_schema(config, key, value):
    config[key] = value
    with pytest.raises(ValueError, match="invalid_model_capacity_config"):
        capacity._parse_capacities(json.dumps(config))


@pytest.mark.parametrize(
    "key,value",
    [
        ("context_window", True),
        ("context_window", "8000"),
        ("context_window", 0),
        ("context_window", 8000.0),
        ("max_input_tokens", 9000),
        ("max_output_tokens", 9000),
        ("default_output_reserve", 2001),
        ("default_output_reserve", -1),
        ("default_answer_tokens", True),
        ("default_answer_tokens", 2001),
        ("reasoning_token_reserve", -1),
        ("reasoning_token_reserve", True),
        ("reasoning_token_reserve", 1001),
        ("answer_only_max_tokens", "false"),
        ("answer_only_max_tokens", True),
        ("ark_thinking_controls", 1),
        ("openai_transport", "false"),
        ("source", "file:///local"),
        ("source", "https://example.com@"),
        ("source", 3),
        ("verified_on", "2026-02-30"),
        ("verified_on", 20260930),
        ("model_id", "other/model"),
        ("provider", ""),
        ("aliases", "example-alias"),
        ("aliases", [1]),
        ("aliases", ["example-v1"]),
        ("aliases", ["same", "same"]),
        ("unexpected_field", 1),
    ],
)
def test_capacity_configuration_rejects_invalid_model_fields(config, key, value):
    config["models"][0][key] = value
    with pytest.raises(ValueError, match="invalid_model_capacity_config"):
        capacity._parse_capacities(json.dumps(config))


def test_capacity_configuration_rejects_missing_fields(config):
    del config["models"][0]["max_input_tokens"]
    with pytest.raises(ValueError, match="invalid_model_capacity_config"):
        capacity._parse_capacities(json.dumps(config))


@pytest.mark.parametrize("collision", ["model", "alias", "provider"])
def test_capacity_configuration_rejects_ambiguous_names(config, collision):
    row = dict(config["models"][0])
    if collision == "alias":
        row["model_id"] = "second-v1"
    elif collision == "provider":
        row["provider"] = "another"
    config["models"].append(row)
    with pytest.raises(ValueError, match="duplicate model or alias"):
        capacity._parse_capacities(json.dumps(config))


@pytest.mark.parametrize("raw", [None, b"\xff", b"invalid JSON"])
def test_unavailable_or_corrupt_resource_never_becomes_empty_catalog(
    tmp_path, monkeypatch, raw
):
    if raw is not None:
        (tmp_path / "model_capacities.json").write_bytes(raw)
    monkeypatch.setattr(capacity, "files", lambda _: tmp_path)
    with pytest.raises(ValueError, match="model_capacity_config"):
        capacity._load_capacities()


def test_invalid_configuration_error_does_not_echo_values(config):
    marker = "synthetic-private-marker"
    config["models"][0]["context_window"] = marker
    with pytest.raises(ValueError) as exc:
        capacity._parse_capacities(json.dumps(config))
    assert marker not in str(exc.value)
    assert "context_window" in str(exc.value)
    assert "model_capacities.json" in str(exc.value)
