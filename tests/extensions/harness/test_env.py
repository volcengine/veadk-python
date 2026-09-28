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

from veadk.extensions.harness.env import (
    build_harness_plugins_from_env,
    harness_enabled_from_env,
)


def test_harness_enabled_from_env():
    assert harness_enabled_from_env({"HARNESS_ENHANCE_ENABLED": "true"}) is True
    assert harness_enabled_from_env({"HARNESS_ENHANCE_ENABLED": "TRUE"}) is True
    assert harness_enabled_from_env({"HARNESS_ENHANCE_ENABLED": "1"}) is True
    assert harness_enabled_from_env({"HARNESS_ENHANCE_ENABLED": "yes"}) is True
    assert harness_enabled_from_env({"HARNESS_ENHANCE_ENABLED": "on"}) is True
    assert harness_enabled_from_env({"HARNESS_ENHANCE_ENABLED": "false"}) is False


def test_build_harness_plugins_from_env_respects_components():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "context_engine,hallucination",
            "HARNESS_ENHANCE_PROFILE": "analysis",
        }
    )

    assert [plugin.name for plugin in plugins] == [
        "harness_invocation_context_plugin",
        "harness_response_verification_plugin",
    ]


def test_build_harness_plugins_from_env_defaults_to_builtin_compression():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "compressor",
        }
    )

    assert plugins[0].name == "harness_compress_plugin"
    assert plugins[0].compressor.config.provider == "builtin"
    assert plugins[0].compressor.config.strategy == "builtin"
    assert plugins[0].compressor.uses_judgement is False


def test_build_harness_plugins_from_env_reads_decision_strategies():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": (
                "context_engine,compressor,long_run_control"
            ),
            "HARNESS_ENHANCE_COMPACTION_STRATEGY": "decision",
            "HARNESS_ENHANCE_LONG_RUN_STRATEGY": "decision",
            "HARNESS_ENHANCE_MODE_STRATEGY": "decision",
        }
    )
    by_name = {plugin.name: plugin for plugin in plugins}

    assert by_name["harness_compress_plugin"].compressor.config.strategy == "decision"
    assert by_name["harness_long_run_control_plugin"].strategy == "decision"
    assert (
        by_name[
            "harness_invocation_context_plugin"
        ].context_builder.config.mode_strategy
        == "decision"
    )


def test_decision_strategies_degrade_without_a_decision_model():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": (
                "context_engine,compressor,long_run_control"
            ),
            "HARNESS_ENHANCE_COMPACTION_STRATEGY": "decision",
            "HARNESS_ENHANCE_LONG_RUN_STRATEGY": "decision",
            "HARNESS_ENHANCE_MODE_STRATEGY": "decision",
        }
    )
    by_name = {plugin.name: plugin for plugin in plugins}

    # 没有配置判定模型时必须回落到原有规则，而不是失败
    assert by_name["harness_compress_plugin"].compressor.uses_judgement is False
    assert by_name["harness_long_run_control_plugin"].convergence_judge is None
    assert (
        by_name["harness_invocation_context_plugin"].context_builder.uses_mode_judgement
        is False
    )


def test_judgement_thresholds_default_to_a_neutral_boundary():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": (
                "context_engine,compressor,long_run_control"
            ),
        }
    )
    by_name = {plugin.name: plugin for plugin in plugins}

    assert (
        by_name["harness_compress_plugin"].compressor.config.decision_keep_threshold
        == 0.5
    )
    assert by_name["harness_long_run_control_plugin"].ready_threshold == 0.5
    assert (
        by_name[
            "harness_invocation_context_plugin"
        ].context_builder.config.mode_decision_threshold
        == 0.5
    )


def test_build_harness_plugins_from_env_reads_judgement_thresholds():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": (
                "context_engine,compressor,long_run_control"
            ),
            "HARNESS_ENHANCE_COMPACTION_KEEP_THRESHOLD": "0.8",
            "HARNESS_ENHANCE_LONG_RUN_READY_THRESHOLD": "0.3",
            "HARNESS_ENHANCE_MODE_DECISION_THRESHOLD": "0.9",
        }
    )
    by_name = {plugin.name: plugin for plugin in plugins}

    assert (
        by_name["harness_compress_plugin"].compressor.config.decision_keep_threshold
        == 0.8
    )
    assert by_name["harness_long_run_control_plugin"].ready_threshold == 0.3
    assert (
        by_name[
            "harness_invocation_context_plugin"
        ].context_builder.config.mode_decision_threshold
        == 0.9
    )


def test_judgement_thresholds_accept_the_generic_spelling_and_clamp():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": (
                "context_engine,compressor,long_run_control"
            ),
            "HARNESS_COMPACTION_KEEP_THRESHOLD": "0.25",
            "HARNESS_LONG_RUN_READY_THRESHOLD": "-1",
            "HARNESS_MODE_DECISION_THRESHOLD": "3",
        }
    )
    by_name = {plugin.name: plugin for plugin in plugins}

    assert (
        by_name["harness_compress_plugin"].compressor.config.decision_keep_threshold
        == 0.25
    )
    # 越界值夹紧而不是回落：-1 仍然是"总是生效"，3 仍然是"永不生效"。
    assert by_name["harness_long_run_control_plugin"].ready_threshold == 0.0
    assert (
        by_name[
            "harness_invocation_context_plugin"
        ].context_builder.config.mode_decision_threshold
        == 1.0
    )


def test_verifier_strategy_and_support_threshold_are_read_from_env():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "response_verification",
            "HARNESS_VERIFIER_STRATEGY": "decision",
            "HARNESS_VERIFIER_SUPPORT_THRESHOLD": "0.8",
        }
    )
    by_name = {plugin.name: plugin for plugin in plugins}

    config = by_name["harness_response_verification_plugin"].verifier.config
    assert config.strategy == "decision"
    assert config.support_threshold == 0.8


def test_verifier_support_threshold_accepts_the_prefixed_alias_and_clamps():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "response_verification",
            "HARNESS_ENHANCE_VERIFIER_SUPPORT_THRESHOLD": "2",
        }
    )
    by_name = {plugin.name: plugin for plugin in plugins}

    assert (
        by_name[
            "harness_response_verification_plugin"
        ].verifier.config.support_threshold
        == 1.0
    )


def test_verifier_keeps_the_builtin_rules_by_default():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "response_verification",
        }
    )
    plugin = {item.name: item for item in plugins}[
        "harness_response_verification_plugin"
    ]

    assert plugin.verifier.config.strategy == "deterministic"
    assert plugin.verifier.config.support_threshold == 0.5
    assert plugin.support_judge is None


def test_skill_prefilter_settings_are_read_from_env():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "skill_prefilter",
            "HARNESS_SKILL_STRATEGY": "decision",
            "HARNESS_SKILL_DECISION_THRESHOLD": "0.8",
            "HARNESS_SKILL_MAX_CANDIDATES": "12",
        }
    )

    assert [plugin.name for plugin in plugins] == ["harness_skill_prefilter_plugin"]
    config = plugins[0].config
    assert config.strategy == "decision"
    assert config.decision_threshold == 0.8
    assert config.max_candidates == 12
    # 没有判定模型时保留完整技能列表，而不是隐藏技能。
    assert plugins[0].uses_judgement is False


def test_skill_prefilter_keeps_every_skill_by_default():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "skill_prefilter",
        }
    )
    config = plugins[0].config

    assert config.strategy == "all"
    assert config.decision_threshold == 0.5
    assert config.max_candidates == 40
    # 未选判定模型时，带 ``HARNESS_ENHANCE_`` 前缀的写法也必须被接受。
    alias = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "skill_prefilter",
            "HARNESS_ENHANCE_SKILL_DECISION_THRESHOLD": "1.5",
        }
    )[0]
    assert alias.config.decision_threshold == 1.0


def test_routing_settings_are_read_from_env():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "routing",
            "HARNESS_ROUTING_STRATEGY": "decision",
            "HARNESS_ROUTING_DECISION_THRESHOLD": "0.7",
        }
    )

    assert [plugin.name for plugin in plugins] == ["harness_agent_routing_plugin"]
    plugin = plugins[0]
    assert plugin.strategy == "decision"
    assert plugin.confidence_threshold == 0.7
    # 没有判定模型时交给对话模型路由。
    assert plugin.router is None
    assert plugin.uses_judgement is False


def test_routing_keeps_the_choice_with_the_model_by_default():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "agent_router",
        }
    )
    plugin = plugins[0]

    assert plugin.strategy == "model"
    assert plugin.confidence_threshold == 0.5


def test_verifier_confidence_cascade_and_overclaim_veto_are_read_from_env():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "response_verification",
            "HARNESS_VERIFIER_MIN_CONFIDENCE": "0.9",
            "HARNESS_ENHANCE_VERIFIER_OVERCLAIM_THRESHOLD": "0.7",
        }
    )

    config = plugins[0].verifier.config
    assert config.min_confidence == 0.9
    assert config.overclaim_threshold == 0.7


def test_verifier_keeps_low_confidence_judgements_by_default():
    """服务端可以不报 confidence，所以级联默认关闭，否则判定会被整条丢掉。"""
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "response_verification",
        }
    )

    assert plugins[0].verifier.config.min_confidence == 0.0
    assert plugins[0].verifier.config.overclaim_threshold == 0.5


def test_long_run_action_min_confidence_is_read_from_env():
    plugins = build_harness_plugins_from_env(
        {
            "HARNESS_ENHANCE_ENABLED": "true",
            "HARNESS_ENHANCE_COMPONENTS": "long_run_control",
            "HARNESS_ENHANCE_LONG_RUN_MIN_CONFIDENCE": "0.9",
        }
    )

    assert plugins[0].min_confidence == 0.9
