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

"""Tests for the agent-facing ``decision_evaluate`` tool."""

from __future__ import annotations

import pytest
from google.adk.tools.function_tool import FunctionTool

from veadk.extensions.decisions import (
    DecisionModelConfig,
    DecisionExtension,
    configure_default_decision_extension,
    decision_evaluate,
)

from .fake_system_one import fake_system_one


@pytest.fixture
def unconfigured_extension() -> None:
    configure_default_decision_extension(DecisionExtension())
    yield None
    configure_default_decision_extension(None)


@pytest.mark.asyncio
async def test_unconfigured_model_returns_an_error_payload(
    unconfigured_extension: None,
) -> None:
    result = await decision_evaluate("hi", "Is this a greeting?")
    assert "not configured" in result["error"]


@pytest.mark.asyncio
async def test_noul_result_shape() -> None:
    with fake_system_one() as server:
        configure_default_decision_extension(_extension(server.base_url))
        try:
            result = await decision_evaluate("hi", "Is this a greeting?")
        finally:
            configure_default_decision_extension(None)
    assert result["kind"] == "noul"
    assert result["answer"] == pytest.approx(0.9)
    assert result["probability"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_choice_result_shape() -> None:
    with fake_system_one() as server:
        configure_default_decision_extension(_extension(server.base_url))
        try:
            result = await decision_evaluate(
                "Where is my order?",
                "Which team should handle this?",
                kind="choice",
                options=["shipping", "billing"],
            )
        finally:
            configure_default_decision_extension(None)
    assert result["kind"] == "choice"
    assert result["answer"] == "shipping"
    assert result["confidence"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_score_result_shape() -> None:
    with fake_system_one() as server:
        configure_default_decision_extension(_extension(server.base_url))
        try:
            result = await decision_evaluate(
                "This is unacceptable!",
                "How frustrated is the customer?",
                kind="score",
                levels=["Calm", "Angry"],
            )
        finally:
            configure_default_decision_extension(None)
    assert result["kind"] == "score"
    assert result["answer"] == pytest.approx(1.0)
    assert result["legend"] == {"0": "Calm", "1": "Angry"}


@pytest.mark.asyncio
async def test_choice_without_options_returns_an_error_payload() -> None:
    result = await decision_evaluate("hi", "Which team?", kind="choice")
    assert "requires options" in result["error"]


@pytest.mark.asyncio
async def test_score_without_levels_returns_an_error_payload() -> None:
    result = await decision_evaluate("hi", "How bad?", kind="score")
    assert "requires levels" in result["error"]


@pytest.mark.asyncio
async def test_transport_failure_becomes_an_error_payload() -> None:
    configure_default_decision_extension(
        DecisionExtension(
            DecisionModelConfig(
                enabled=True, api_base="http://127.0.0.1:9", api_key="k", max_retries=0
            )
        )
    )
    try:
        result = await decision_evaluate("hi", "Is this a greeting?")
    finally:
        configure_default_decision_extension(None)
    assert "transport error" in result["error"]


def _extension(server_url: str) -> DecisionExtension:
    return DecisionExtension(
        DecisionModelConfig(enabled=True, api_base=server_url, api_key="test-key")
    )


def test_adk_exposes_the_tool_contract() -> None:
    """The tool must be mountable on an Agent with a usable parameter schema."""
    declaration = FunctionTool(decision_evaluate)._get_declaration()
    schema = declaration.parameters_json_schema or (
        declaration.parameters.model_dump(exclude_none=True)
        if declaration.parameters
        else {}
    )
    assert declaration.name == "decision_evaluate"
    assert sorted(schema["properties"]) == [
        "kind",
        "levels",
        "options",
        "question",
        "state",
    ]
    assert schema["required"] == ["state", "question"]
    assert schema["properties"]["kind"]["enum"] == ["noul", "choice", "score"]
