# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# SPDX-License-Identifier: Apache-2.0

"""Reviewed input ceilings and SDK/Studio defaults must work without a catalog."""

import pytest

from veadk.context.budget import ContextBudgetError, check_payload, resolve_budget
from veadk.context.config import ContextCompressionConfig
from veadk.context.model_capacity import get_model_capacity


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-5.6-terra", "gpt-5.6-luna"])
def test_shared_window_does_not_override_official_input_ceiling(model):
    config = ContextCompressionConfig(context_window=2_000_000, input_limit=2_000_000)
    budget = resolve_budget("openai/" + model, config, max_output=4096)
    assert budget.window == 1_050_000
    assert budget.available == 922_000
    with pytest.raises(ContextBudgetError, match="input_too_large"):
        check_payload(
            {
                "model": "openai/" + model,
                "messages": [{"role": "user", "content": "x" * 923_000}],
                "max_tokens": 4096,
            },
            config,
        )


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_studio_agent_and_generated_defaults_have_reviewed_capacity(
    monkeypatch, provider
):
    from veadk.cli.studio_model_catalog import (
        generated_agent_model_name,
        studio_agent_model_name,
    )

    monkeypatch.setattr("veadk.context.budget._catalogue", lambda: {})
    for model in (
        generated_agent_model_name(provider),
        studio_agent_model_name(provider),
    ):
        assert get_model_capacity(model)
        budget = resolve_budget("openai/" + model, ContextCompressionConfig())
        assert budget and budget.available > 0


@pytest.mark.parametrize(
    "model,provider,input_cap",
    [
        ("dola-seed-2-1-turbo-260628", "byteplus", 256_000),
        ("deepseek-flash", "deepseek", 1_000_000),
        ("qwen3.8-max", "dashscope", 983_616),
        ("qwen3.7-plus", "dashscope", 983_616),
        ("qwen3.8-flash", "dashscope", 983_616),
        ("glm-5.3", "zai", 1_000_000),
        ("kimi-k3", "moonshot", 1_000_000),
    ],
)
def test_reviewed_native_and_openai_transport_use_same_capacity(
    monkeypatch, model, provider, input_cap
):
    monkeypatch.setattr("veadk.context.budget._catalogue", lambda: {})
    row = get_model_capacity(f"{provider}/{model}")
    assert row["max_input_tokens"] == input_cap
    assert row == get_model_capacity("openai/" + model)
    assert get_model_capacity("unreviewed/" + model) == {}
    config = ContextCompressionConfig(context_window=2_000_000, input_limit=2_000_000)
    budget = resolve_budget("openai/" + model, config)
    assert budget and 0 < budget.available <= input_cap


def test_kimi_default_generation_limit_is_reserved_before_sending():
    budget = resolve_budget("openai/kimi-k3", ContextCompressionConfig())
    assert budget.output == 131_072
    assert budget.available < 1_000_000 - 131_072
