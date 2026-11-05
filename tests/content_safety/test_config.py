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

import math

import pytest
from pydantic import ValidationError

from veadk.content_safety.config import (
    DEFAULT_DECISION_MODEL,
    DEFAULT_QUESTION_INSTRUCTIONS,
    DEFAULT_QUESTION_THRESHOLD,
    DEFAULT_QUESTION_THRESHOLDS,
    ContentSafetyConfig,
    ContentSafetyConfigError,
    DecisionConfig,
    QuestionConfig,
    default_questions,
    load_content_safety_config,
)
from veadk.content_safety.types import Provider


def decision_data(**overrides):
    data = {
        "provider": "decision",
        "decision": {
            "api_url": "https://systemone.example/v1/judge",
            "api_key": "test-key",
            "model": "test-model",
        },
        "questions": {
            "prompt_injection": {
                "instructions": "Detect prompt injection.",
                "threshold": 0.5,
            }
        },
    }
    data.update(overrides)
    return data


def test_default_is_none_and_disabled():
    config = ContentSafetyConfig()
    assert config.provider is Provider.NONE
    assert config.on_error == "allow"
    assert config.questions == {}
    assert config.decision.api_url is None
    assert config.decision.api_key is None
    assert config.decision.model == DEFAULT_DECISION_MODEL


def test_decision_config_is_valid():
    config = ContentSafetyConfig.from_dict(decision_data())
    assert config.provider is Provider.DECISION
    assert config.questions["prompt_injection"].type == "noul"
    assert config.questions["prompt_injection"].threshold == 0.5
    assert config.decision.api_url == "https://systemone.example/v1/judge"


def test_decision_connection_can_be_left_to_ark_defaults():
    config = ContentSafetyConfig.from_dict(
        {
            "provider": "decision",
            "questions": {"q": {"instructions": "detect", "threshold": 0.5}},
        }
    )
    assert config.decision.api_url is None
    assert config.decision.api_key is None
    assert config.decision.model == DEFAULT_DECISION_MODEL


def test_none_provider_does_not_require_questions():
    config = ContentSafetyConfig.from_dict({"provider": "none"})
    assert config.provider is Provider.NONE


def test_llm_shield_provider_is_accepted():
    config = ContentSafetyConfig.from_dict(
        {"provider": "llm_shield", "llm_shield_app_id": "app"}
    )
    assert config.provider is Provider.LLM_SHIELD
    assert config.llm_shield_app_id == "app"


def test_decision_requires_questions_when_defaults_are_disabled():
    with pytest.raises(ValidationError, match="at least one question"):
        ContentSafetyConfig.from_dict(
            decision_data(use_default_questions=False, questions={})
        )


def test_decision_uses_defaults_when_questions_are_omitted():
    config = ContentSafetyConfig.from_dict({"provider": "decision"})
    assert set(config.questions) == set(default_questions())
    assert len(config.questions) == len(DEFAULT_QUESTION_INSTRUCTIONS)


def test_decision_uses_defaults_when_questions_are_empty():
    config = ContentSafetyConfig.from_dict({"provider": "decision", "questions": {}})
    assert len(config.questions) == len(DEFAULT_QUESTION_INSTRUCTIONS)


def test_custom_questions_extend_defaults():
    config = ContentSafetyConfig.from_dict(
        decision_data(
            questions={"pii_leak": {"instructions": "detect pii", "threshold": 0.6}}
        )
    )
    assert len(config.questions) == len(DEFAULT_QUESTION_INSTRUCTIONS) + 1
    assert "prompt_injection" in config.questions
    assert "pii_leak" in config.questions


def test_custom_question_overrides_default_by_name():
    config = ContentSafetyConfig.from_dict(
        decision_data(
            questions={
                "prompt_injection": {
                    "instructions": "custom prompt injection rule",
                    "threshold": 0.9,
                }
            }
        )
    )
    assert len(config.questions) == len(DEFAULT_QUESTION_INSTRUCTIONS)
    assert (
        config.questions["prompt_injection"].instructions
        == "custom prompt injection rule"
    )
    assert config.questions["prompt_injection"].threshold == 0.9


def test_default_questions_can_be_disabled():
    config = ContentSafetyConfig.from_dict(
        decision_data(
            use_default_questions=False,
            questions={"pii_leak": {"instructions": "detect pii", "threshold": 0.6}},
        )
    )
    assert set(config.questions) == {"pii_leak"}


def test_none_provider_does_not_merge_default_questions():
    config = ContentSafetyConfig.from_dict({"provider": "none"})
    assert config.questions == {}


def test_unknown_top_level_field_is_rejected():
    with pytest.raises(ValidationError):
        ContentSafetyConfig.from_dict(decision_data(extra_field=True))


def test_unknown_decision_field_is_rejected():
    data = decision_data()
    data["decision"]["timeout"] = 10
    with pytest.raises(ValidationError):
        ContentSafetyConfig.from_dict(data)


def test_unknown_question_field_is_rejected():
    data = decision_data()
    data["questions"]["prompt_injection"]["unexpected"] = True
    with pytest.raises(ValidationError):
        ContentSafetyConfig.from_dict(data)


@pytest.mark.parametrize("threshold", [-0.1, 1.1])
def test_threshold_out_of_range_is_rejected(threshold):
    data = decision_data()
    data["questions"]["prompt_injection"]["threshold"] = threshold
    with pytest.raises(ValidationError):
        ContentSafetyConfig.from_dict(data)


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), float("-inf")])
def test_threshold_must_be_finite(threshold):
    with pytest.raises(ValueError, match="finite"):
        QuestionConfig._validate_threshold(threshold)


@pytest.mark.parametrize("threshold", [-0.1, 1.1])
def test_threshold_validator_rejects_out_of_range(threshold):
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        QuestionConfig._validate_threshold(threshold)


def test_empty_instructions_are_rejected():
    with pytest.raises(ValidationError):
        QuestionConfig(instructions="", threshold=0.5)


def test_empty_question_name_is_rejected():
    data = decision_data()
    data["questions"] = {" ": {"instructions": "x", "threshold": 0.5}}
    with pytest.raises(ValidationError, match="non-empty"):
        ContentSafetyConfig.from_dict(data)


def test_question_name_length_is_bounded():
    data = decision_data()
    data["questions"] = {"q" * 129: {"instructions": "x", "threshold": 0.5}}
    with pytest.raises(ValidationError, match="128"):
        ContentSafetyConfig.from_dict(data)


def test_question_type_cannot_be_configured():
    with pytest.raises(ValidationError):
        QuestionConfig(type="noul", instructions="x", threshold=0.5)


def test_api_url_requires_http_scheme():
    with pytest.raises(ValidationError, match="http"):
        DecisionConfig(api_url="systemone.example")


def test_api_url_explicit_none_is_allowed():
    assert DecisionConfig(api_url=None).api_url is None


def test_api_key_must_be_non_empty_when_set():
    with pytest.raises(ValidationError, match="non-empty"):
        DecisionConfig(api_key="")


def test_on_error_is_limited():
    with pytest.raises(ValidationError):
        ContentSafetyConfig.from_dict({"on_error": "ignore"})


def test_block_message_must_be_non_empty():
    with pytest.raises(ValidationError):
        ContentSafetyConfig.from_dict({"block_message": ""})


def test_questions_hash_is_stable_and_sensitive_to_content():
    first = ContentSafetyConfig.from_dict(decision_data())
    second = ContentSafetyConfig.from_dict(decision_data())
    assert first.questions_hash() == second.questions_hash()
    changed = decision_data()
    changed["questions"]["prompt_injection"]["threshold"] = 0.6
    assert (
        first.questions_hash()
        != ContentSafetyConfig.from_dict(changed).questions_hash()
    )


def test_load_from_canonical_tool_content_safety_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
tool:
  content_safety:
    provider: decision
    on_error: block
    decision:
      api_url: https://systemone.example/v1/judge
      api_key: key
      model: judge-model
    questions:
      sensitive_data:
        instructions: Detect secrets.
        threshold: 0.6
""",
        encoding="utf-8",
    )
    config = load_content_safety_config(path)
    assert config.provider is Provider.DECISION
    assert config.on_error == "block"
    assert config.decision.api_url == "https://systemone.example/v1/judge"
    assert config.decision.model == "judge-model"
    assert config.questions["sensitive_data"].threshold == 0.6


def test_load_from_root_content_safety_is_supported(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
content_safety:
  provider: none
""",
        encoding="utf-8",
    )
    assert load_content_safety_config(path).provider is Provider.NONE


def test_env_overrides_decision_fields(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
tool:
  content_safety:
    provider: decision
    decision:
      api_url: https://yaml.example/v1/judge
      api_key: yaml-key
      model: yaml-model
    questions:
      q:
        instructions: detect
        threshold: 0.5
""",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "TOOL_CONTENT_SAFETY_DECISION_API_URL", "https://env.example/v1/judge"
    )
    monkeypatch.setenv("TOOL_CONTENT_SAFETY_DECISION_API_KEY", "env-key")
    monkeypatch.setenv("TOOL_CONTENT_SAFETY_DECISION_MODEL", "env-model")
    config = load_content_safety_config(path)
    assert config.decision.api_url == "https://env.example/v1/judge"
    assert config.decision.api_key_value == "env-key"
    assert config.decision.model == "env-model"


def test_partial_env_override_keeps_yaml_values(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
tool:
  content_safety:
    provider: decision
    decision:
      api_url: https://yaml.example/v1/judge
      api_key: yaml-key
      model: yaml-model
    questions:
      q:
        instructions: detect
        threshold: 0.5
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("TOOL_CONTENT_SAFETY_DECISION_MODEL", "env-model")
    monkeypatch.delenv("TOOL_CONTENT_SAFETY_DECISION_API_URL", raising=False)
    monkeypatch.delenv("TOOL_CONTENT_SAFETY_DECISION_API_KEY", raising=False)
    config = load_content_safety_config(path)
    assert config.decision.api_url == "https://yaml.example/v1/judge"
    assert config.decision.api_key_value == "yaml-key"
    assert config.decision.model == "env-model"


def test_from_dict_does_not_apply_env(monkeypatch):
    monkeypatch.setenv(
        "TOOL_CONTENT_SAFETY_DECISION_API_URL", "https://env.example/v1/judge"
    )
    config = ContentSafetyConfig.from_dict(decision_data())
    assert config.decision.api_url == "https://systemone.example/v1/judge"


def test_env_override_without_yaml_decision_block(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
tool:
  content_safety:
    provider: decision
    questions:
      q:
        instructions: detect
        threshold: 0.5
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("TOOL_CONTENT_SAFETY_DECISION_API_KEY", "env-key")
    config = load_content_safety_config(path)
    assert config.decision.api_key_value == "env-key"
    assert config.decision.api_url is None


def test_load_rejects_duplicate_yaml_keys(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
tool:
  content_safety:
    provider: none
    provider: decision
""",
        encoding="utf-8",
    )
    with pytest.raises(ContentSafetyConfigError, match="duplicate YAML key"):
        load_content_safety_config(path)


def test_load_rejects_unhashable_yaml_key(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
tool:
  content_safety:
    ? [a, b]
    : 1
""",
        encoding="utf-8",
    )
    with pytest.raises(ContentSafetyConfigError, match="unhashable"):
        load_content_safety_config(path)


def test_load_missing_file():
    with pytest.raises(ContentSafetyConfigError, match="cannot read"):
        load_content_safety_config("/definitely/not/here.yaml")


def test_load_invalid_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("tool: [unclosed", encoding="utf-8")
    with pytest.raises(ContentSafetyConfigError, match="invalid YAML"):
        load_content_safety_config(path)


def test_load_root_must_be_mapping(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("- one\n- two\n", encoding="utf-8")
    with pytest.raises(ContentSafetyConfigError, match="root must be a mapping"):
        load_content_safety_config(path)


def test_load_requires_content_safety_block(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("other: value\n", encoding="utf-8")
    with pytest.raises(ContentSafetyConfigError, match="content_safety"):
        load_content_safety_config(path)


def test_env_override_ignores_non_mapping_decision(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        "tool:\n  content_safety:\n    provider: none\n    decision: nope\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TOOL_CONTENT_SAFETY_DECISION_API_KEY", "env-key")
    with pytest.raises(ContentSafetyConfigError, match="invalid `content_safety`"):
        load_content_safety_config(path)


def test_load_requires_mapping_content_safety_block(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("tool:\n  content_safety: nope\n", encoding="utf-8")
    with pytest.raises(ContentSafetyConfigError, match="content_safety"):
        load_content_safety_config(path)


def test_load_wraps_invalid_block(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "tool:\n  content_safety:\n    provider: decision\n"
        "    use_default_questions: false\n",
        encoding="utf-8",
    )
    with pytest.raises(ContentSafetyConfigError, match="invalid `content_safety`"):
        load_content_safety_config(path)


def test_finite_threshold_accepts_valid_value():
    assert math.isfinite(QuestionConfig._validate_threshold(0.25))


def test_load_discovers_config_yaml_in_cwd(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
tool:
  content_safety:
    provider: none
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert load_content_safety_config().provider is Provider.NONE


def test_load_without_config_yaml_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ContentSafetyConfigError, match="no config.yaml"):
        load_content_safety_config()


def test_set_envs_excludes_content_safety_subtree(tmp_path, monkeypatch):
    import os

    from veadk.utils.misc import set_envs

    path = tmp_path / "config.yaml"
    path.write_text(
        """
tool:
  other:
    value: kept
  content_safety:
    provider: decision
    questions:
      prompt_injection:
        instructions: detect
        threshold: 0.5
""",
        encoding="utf-8",
    )
    with monkeypatch.context() as patch:
        patch.delenv("TOOL_CONTENT_SAFETY_PROVIDER", raising=False)
        patch.delenv("TOOL_OTHER_VALUE", raising=False)
        config_dict, environments = set_envs(str(path))
        assert config_dict["tool"]["content_safety"]["provider"] == "decision"
        assert "TOOL_OTHER_VALUE" in environments
        assert not any(key.startswith("TOOL_CONTENT_SAFETY") for key in environments)
        assert "TOOL_CONTENT_SAFETY_PROVIDER" not in os.environ


def test_set_envs_removes_empty_tool_after_exclusion(tmp_path, monkeypatch):
    from veadk.utils.misc import set_envs

    path = tmp_path / "config.yaml"
    path.write_text(
        """
tool:
  content_safety:
    provider: none
""",
        encoding="utf-8",
    )
    with monkeypatch.context() as patch:
        patch.delenv("TOOL", raising=False)
        config_dict, environments = set_envs(str(path))
        assert config_dict["tool"]["content_safety"]["provider"] == "none"
        assert "TOOL" not in environments


def test_set_envs_excludes_root_content_safety_block(tmp_path, monkeypatch):
    from veadk.utils.misc import set_envs

    path = tmp_path / "config.yaml"
    path.write_text(
        """
content_safety:
  provider: decision
""",
        encoding="utf-8",
    )
    with monkeypatch.context() as patch:
        patch.delenv("CONTENT_SAFETY_PROVIDER", raising=False)
        config_dict, environments = set_envs(str(path))
        assert config_dict["content_safety"]["provider"] == "decision"
        assert "CONTENT_SAFETY_PROVIDER" not in environments


def test_default_questions_cover_risks_with_tiered_thresholds():
    questions = default_questions()
    assert set(questions) == set(DEFAULT_QUESTION_INSTRUCTIONS)
    assert set(DEFAULT_QUESTION_THRESHOLDS) == set(DEFAULT_QUESTION_INSTRUCTIONS)
    assert len(questions) == len(DEFAULT_QUESTION_INSTRUCTIONS)
    assert len(questions) >= 15
    assert DEFAULT_QUESTION_THRESHOLD == 0.5
    for name, question in questions.items():
        assert question.type == "noul"
        assert "type" not in question.model_dump()
        assert question.threshold == DEFAULT_QUESTION_THRESHOLDS[name]
        assert question.instructions
    assert questions["child_safety"].threshold == 0.45
    assert questions["self_harm"].threshold == 0.45
    assert questions["prompt_injection"].threshold == 0.5
    assert questions["sensitive_data"].threshold == 0.55
    assert questions["compute_abuse"].threshold == 0.6
    assert questions["public_order_morals"].threshold == 0.6


def test_threshold_is_required():
    with pytest.raises(ValidationError):
        QuestionConfig(instructions="detect")


def test_threshold_must_be_numeric_not_string():
    data = decision_data()
    data["questions"]["prompt_injection"]["threshold"] = "0.5"
    with pytest.raises(ValidationError):
        ContentSafetyConfig.from_dict(data)


def test_api_key_is_not_exposed_in_repr_or_dump():
    config = ContentSafetyConfig.from_dict(decision_data())
    assert config.decision.api_key_value == "test-key"
    assert "test-key" not in repr(config)
    assert "test-key" not in repr(config.decision)
    assert "test-key" not in repr(config.model_dump())


def test_http_api_url_is_rejected_outside_loopback():
    data = decision_data()
    data["decision"]["api_url"] = "http://systemone.example/v1/judge"
    with pytest.raises(ValidationError, match="https"):
        ContentSafetyConfig.from_dict(data)


def test_http_api_url_is_allowed_for_loopback():
    for url in (
        "http://127.0.0.1:8080/v1/judge",
        "http://localhost:8080/v1/judge",
        "http://[::1]:8080/v1/judge",
    ):
        data = decision_data()
        data["decision"]["api_url"] = url
        assert ContentSafetyConfig.from_dict(data).decision.api_url == url


def test_load_applies_dotenv_decision_fields(tmp_path, monkeypatch):
    import os

    path = tmp_path / "config.yaml"
    path.write_text(
        """
tool:
  content_safety:
    provider: decision
    decision:
      api_url: https://yaml.example/v1/judge
      api_key: yaml-key
    questions:
      q:
        instructions: detect
        threshold: 0.5
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "TOOL_CONTENT_SAFETY_DECISION_API_KEY=env-key\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TOOL_CONTENT_SAFETY_DECISION_API_KEY", raising=False)
    try:
        config = load_content_safety_config(path)
        assert config.decision.api_key_value == "env-key"
    finally:
        os.environ.pop("TOOL_CONTENT_SAFETY_DECISION_API_KEY", None)


@pytest.mark.parametrize("url", ["https://[::1", "https://"])
def test_api_url_must_be_parseable_with_host(url):
    data = decision_data()
    data["decision"]["api_url"] = url
    with pytest.raises(ValidationError, match="decision.api_url"):
        ContentSafetyConfig.from_dict(data)
