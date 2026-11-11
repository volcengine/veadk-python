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

import pytest
from pydantic import ValidationError

from veadk.configs.routing_configs import (
    DEFAULT_QUERY_ROUTING_THRESHOLD,
    QueryRoutingConfig,
    QueryRoutingConfigError,
    RoutingQuestion,
    load_query_routing_config,
    load_query_routing_config_if_present,
)


def write_config(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_builtin_questions_are_always_present_and_ordered():
    config = QueryRoutingConfig(simple_models=["cheap-model"])
    assert [question.id for question in config.questions] == [
        "is_complex",
        "needs_tools",
        "needs_long_context",
        "is_high_stakes",
    ]
    thresholds = {question.id: question.threshold for question in config.questions}
    assert thresholds["is_high_stakes"] == 0.05
    assert all(
        thresholds[name] == 0.15
        for name in ("is_complex", "needs_tools", "needs_long_context")
    )
    assert all(question.type == "noul" for question in config.questions)


def test_simple_model_accepts_string_and_mapping():
    config = QueryRoutingConfig(
        simple_models=[
            "cheap-a",
            {"name": "cheap-b", "supports_tools": True, "max_context_chars": 1000},
        ]
    )
    assert [model.name for model in config.simple_models] == ["cheap-a", "cheap-b"]
    assert config.simple_models[0].supports_tools is False
    assert config.simple_models[0].max_context_chars == 32_000
    assert config.simple_models[1].supports_tools is True
    assert config.simple_models[1].max_context_chars == 1000


def test_custom_question_only_needs_text_and_threshold():
    config = QueryRoutingConfig(
        simple_models=["cheap"],
        questions=[{"question": "是否需要最新信息？", "threshold": 0.1}],
    )
    custom = config.questions[-1]
    assert custom.id == "custom_1"
    assert custom.instructions == "是否需要最新信息？"
    assert custom.threshold == 0.1
    assert custom.type == "noul"


def test_custom_question_accepts_leading_string():
    config = QueryRoutingConfig(
        simple_models=["cheap"], questions=["是否需要实时数据？"]
    )
    assert config.questions[-1].instructions == "是否需要实时数据？"
    assert config.questions[-1].threshold == DEFAULT_QUERY_ROUTING_THRESHOLD


def test_reserved_question_id_is_rejected():
    with pytest.raises(ValidationError, match="reserved or duplicated"):
        QueryRoutingConfig(
            simple_models=["cheap"],
            questions=[{"id": "is_complex", "question": "override", "threshold": 0}],
        )


def test_duplicate_custom_question_id_is_rejected():
    with pytest.raises(ValidationError, match="reserved or duplicated"):
        QueryRoutingConfig(
            simple_models=["cheap"],
            questions=[
                {"id": "custom_x", "question": "a"},
                {"id": "custom_x", "question": "b"},
            ],
        )


def test_non_list_simple_models_is_left_for_validation():
    with pytest.raises(ValidationError):
        QueryRoutingConfig(simple_models="cheap")


@pytest.mark.parametrize("value", ["raw", ["list"]])
def test_non_mapping_input_is_left_for_validation(value):
    with pytest.raises(ValidationError):
        QueryRoutingConfig.model_validate(value)


def test_non_list_questions_is_left_for_validation():
    with pytest.raises(ValidationError):
        QueryRoutingConfig(simple_models=["cheap"], questions="question")


def test_custom_question_accepts_routing_question_instance():
    config = QueryRoutingConfig(
        simple_models=["cheap"],
        questions=[
            RoutingQuestion(
                id="custom_x", instructions="是否需要外部知识？", threshold=0.2
            )
        ],
    )
    assert config.questions[-1].id == "custom_x"
    assert config.questions[-1].threshold == 0.2


def test_question_item_must_be_string_mapping_or_question():
    with pytest.raises(ValidationError, match="questions items must be"):
        QueryRoutingConfig(simple_models=["cheap"], questions=[123])


def test_valid_strong_model_is_kept():
    config = QueryRoutingConfig(simple_models=["cheap"], strong_model="strong")
    assert config.strong_model == "strong"


def test_from_dict_builds_configuration():
    config = QueryRoutingConfig.from_dict({"simple_models": ["cheap"]})
    assert [model.name for model in config.simple_models] == ["cheap"]


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), float("inf")])
def test_threshold_must_be_within_unit_interval(threshold):
    with pytest.raises(ValidationError):
        QueryRoutingConfig(
            simple_models=["cheap"],
            questions=[{"question": "q", "threshold": threshold}],
        )


@pytest.mark.parametrize("threshold", [0.0, 1.0])
def test_threshold_accepts_unit_interval_boundaries(threshold):
    config = QueryRoutingConfig(
        simple_models=["cheap"],
        questions=[{"question": "q", "threshold": threshold}],
    )
    assert config.questions[-1].threshold == threshold


def test_duplicate_simple_models_are_rejected():
    with pytest.raises(ValidationError, match="duplicate"):
        QueryRoutingConfig(simple_models=["cheap", "cheap"])


def test_empty_simple_models_are_rejected():
    with pytest.raises(ValidationError):
        QueryRoutingConfig(simple_models=[])


def test_strong_model_must_not_be_blank():
    with pytest.raises(ValidationError, match="non-empty"):
        QueryRoutingConfig(simple_models=["cheap"], strong_model="  ")


def test_shadow_mode_and_decision_timeout_bounds():
    config = QueryRoutingConfig(simple_models=["cheap"], mode="shadow")
    assert config.mode == "shadow"
    with pytest.raises(ValidationError):
        QueryRoutingConfig(simple_models=["cheap"], decision_timeout=0)


def test_questions_hash_is_stable_and_ignores_model_names():
    first = QueryRoutingConfig(simple_models=["a"])
    second = QueryRoutingConfig(simple_models=["b"])
    assert first.questions_hash() == second.questions_hash()

    third = QueryRoutingConfig(
        simple_models=["a"], questions=[{"question": "new gate"}]
    )
    assert third.questions_hash() != first.questions_hash()


def test_load_from_explicit_config_yaml(tmp_path):
    path = write_config(
        tmp_path,
        """
query_routing:
  simple_models:
    - cheap-a
  questions:
    - question: 是否需要最新信息？
      threshold: 0.2
""",
    )
    config = load_query_routing_config(path)
    assert [model.name for model in config.simple_models] == ["cheap-a"]
    assert config.questions[-1].id == "custom_1"
    assert config.questions[-1].threshold == 0.2


def test_load_if_present_returns_none_without_block(tmp_path):
    path = write_config(tmp_path, "model:\n  agent:\n    name: x\n")
    assert load_query_routing_config_if_present(path) is None


def test_auto_discovery_optional_returns_none_without_config_file(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    assert load_query_routing_config_if_present() is None


def test_auto_discovery_required_raises_without_config_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(QueryRoutingConfigError, match="no config.yaml"):
        load_query_routing_config()


def test_empty_config_document_is_treated_as_empty_mapping(tmp_path):
    path = write_config(tmp_path, "")
    assert load_query_routing_config_if_present(path) is None


def test_load_if_present_rejects_missing_explicit_path(tmp_path):
    with pytest.raises(QueryRoutingConfigError, match="cannot read"):
        load_query_routing_config_if_present(tmp_path / "missing.yaml")


def test_load_requires_block(tmp_path):
    path = write_config(tmp_path, "model: {}\n")
    with pytest.raises(QueryRoutingConfigError, match="query_routing"):
        load_query_routing_config(path)


def test_invalid_block_raises_with_path(tmp_path):
    path = write_config(tmp_path, "query_routing:\n  simple_models: []\n")
    with pytest.raises(QueryRoutingConfigError, match="invalid `query_routing`"):
        load_query_routing_config(path)


def test_non_mapping_block_raises(tmp_path):
    path = write_config(tmp_path, "query_routing: []\n")
    with pytest.raises(QueryRoutingConfigError, match="mapping"):
        load_query_routing_config(path)


def test_non_mapping_block_raises_when_optional(tmp_path):
    path = write_config(tmp_path, "query_routing: []\n")
    with pytest.raises(QueryRoutingConfigError, match="mapping"):
        load_query_routing_config_if_present(path)


def test_invalid_yaml_raises(tmp_path):
    path = write_config(tmp_path, "query_routing: [\n")
    with pytest.raises(QueryRoutingConfigError, match="invalid YAML"):
        load_query_routing_config(path)


def test_non_mapping_root_raises(tmp_path):
    path = write_config(tmp_path, "- just\n- a list\n")
    with pytest.raises(QueryRoutingConfigError, match="root must be a mapping"):
        load_query_routing_config_if_present(path)


def test_unreadable_path_raises(tmp_path):
    with pytest.raises(QueryRoutingConfigError, match="cannot read"):
        load_query_routing_config(tmp_path / "nope" / "config.yaml")


def test_decision_block_defaults(tmp_path):
    path = write_config(tmp_path, "query_routing:\n  simple_models: [cheap]\n")
    config = load_query_routing_config(path)
    assert config.decision.model == "doubao-seed-2-1-lite-260915"
    assert config.decision_timeout == 2.0


def test_independent_credentials_use_environment_and_remain_redacted(monkeypatch):
    from veadk.configs.routing_configs import SimpleModelConfig, QueryRoutingConfigError

    monkeypatch.setenv("ROUTING_TEST_KEY", "test-only-value")
    profile = SimpleModelConfig(name="cheap", api_key_env="ROUTING_TEST_KEY")
    assert profile.api_key_value == "test-only-value"
    monkeypatch.delenv("ROUTING_TEST_KEY")
    with pytest.raises(QueryRoutingConfigError, match="missing credential"):
        profile.api_key_value
    with pytest.raises(ValueError, match="only one"):
        SimpleModelConfig(
            name="cheap", api_key="test-only", api_key_env="ROUTING_TEST_KEY"
        )
    hidden = SimpleModelConfig(name="cheap", api_key="test-only")
    assert (
        "test-only" not in repr(hidden) and "test-only" not in hidden.model_dump_json()
    )


@pytest.mark.parametrize(
    "field",
    [
        "model",
        "api_key",
        "api_base",
        "fallbacks",
        "previous_response_id",
        "input",
        "instructions",
    ],
)
def test_profile_cannot_override_routing_contract_through_extra_config(field):
    from veadk.configs.routing_configs import SimpleModelConfig

    with pytest.raises(ValueError, match="not allowed"):
        SimpleModelConfig(name="cheap", extra_config={field: "override"})


def test_builtin_threshold_calibration_validates_ids_and_bounds():
    cfg = QueryRoutingConfig(
        simple_models=["cheap"], builtin_thresholds={"needs_tools": 0.4}
    )
    assert next(q.threshold for q in cfg.questions if q.id == "needs_tools") == 0.4
    with pytest.raises(ValueError, match="unknown"):
        QueryRoutingConfig(simple_models=["cheap"], builtin_thresholds={"unknown": 0.4})
    for threshold in (-0.1, 1.1, float("nan")):
        with pytest.raises(ValueError):
            QueryRoutingConfig(
                simple_models=["cheap"], builtin_thresholds={"needs_tools": threshold}
            )
