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

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from frontend.server.evaluation_automation.model_gateway import (
    StructuredEvaluationModels,
)
from frontend.server.evaluation_automation.models import AutoEvaluationOutput


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "override", "expected"),
    [
        ("volcengine", None, "doubao-seed-2-0-lite-260428"),
        ("byteplus", None, "seed-2-0-lite-260228"),
        ("byteplus", "custom-evaluator", "custom-evaluator"),
    ],
)
async def test_evaluator_uses_provider_model_and_validates_structured_output(
    monkeypatch, provider, override, expected
):
    import veadk

    monkeypatch.setenv("CLOUD_PROVIDER", provider)
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", provider)
    monkeypatch.delenv("VEADK_STUDIO_EVALUATION_MODEL", raising=False)
    if override:
        monkeypatch.setenv("VEADK_STUDIO_EVALUATION_MODEL", override)
    agent = Mock()
    run = AsyncMock(return_value='{"score": 0.9, "reason": "正确"}')
    monkeypatch.setattr(veadk, "Agent", agent)
    monkeypatch.setattr(veadk, "Runner", Mock(return_value=SimpleNamespace(run=run)))
    result = await StructuredEvaluationModels().evaluate(
        user_input="1+1", agent_output="2", agent_info={"name": "math"}
    )
    assert agent.call_args.kwargs["model_name"] == expected
    assert agent.call_args.kwargs["output_schema"] is AutoEvaluationOutput
    assert result.score == 0.9
    assert result.reason == "正确"
    assert "1+1" in run.call_args.args[0]
