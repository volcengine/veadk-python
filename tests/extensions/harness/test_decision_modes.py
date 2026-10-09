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

"""Mode blocks: keyword default, judged modes, one judgement per run."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from types import SimpleNamespace

from google.adk.models import LlmRequest
from google.genai import types

from veadk.extensions.decisions import (
    DecisionModelConfig,
    DecisionModelDisabledError,
    DecisionExtension,
)
from veadk.extensions.harness.modules.invocation_context import (
    HarnessInvocationContextBuilder,
    HarnessInvocationContextConfig,
    build_mode_judge,
)
from veadk.extensions.harness.plugins import HarnessInvocationContextPlugin
from veadk.extensions.harness.schemas import HarnessInvocationRef
from veadk.extensions.harness.stores import InMemoryHarnessStore

# 同时命中精度关键词（排序）和产物关键词（报告）
_MIXED_INPUT = "帮我排序这些数据，然后生成一份报告"


class _FakeJudge:
    """Record the requests it judged and return fixed probabilities."""

    def __init__(
        self,
        probabilities: Mapping[str, float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.probabilities = dict(probabilities or {})
        self.error = error
        self.calls: list[str] = []

    async def aprobabilities(self, *, user_input: str) -> Mapping[str, float]:
        self.calls.append(user_input)
        if self.error is not None:
            raise self.error
        return {
            "precision": self.probabilities.get("precision", 0.0),
            "artifact": self.probabilities.get("artifact", 0.0),
        }


def _context(invocation_id: str = "r1") -> HarnessInvocationRef:
    return HarnessInvocationRef(
        app_name="app",
        user_id="u1",
        session_id="s1",
        invocation_id=invocation_id,
        profile="default",
    )


def _header(builder: HarnessInvocationContextBuilder, user_input: str, *, modes=None):
    return builder.build_context_header(
        context=_context(),
        user_input=user_input,
        modes=modes,
    )


def test_keyword_strategy_keeps_the_marker_behaviour() -> None:
    builder = HarnessInvocationContextBuilder()

    assert builder.uses_mode_judgement is False
    mixed = _header(builder, _MIXED_INPUT)
    assert "[Harness Precision Mode]" in mixed
    assert "[Harness Artifact Mode]" in mixed
    plain = _header(builder, "hello")
    assert "[Harness Precision Mode]" not in plain
    assert "[Harness Artifact Mode]" not in plain


def test_decision_strategy_uses_the_judged_modes() -> None:
    judge = _FakeJudge({"precision": 0.9, "artifact": 0.05})
    builder = HarnessInvocationContextBuilder(mode_judge=judge)

    block = asyncio.run(
        builder.aprepare_context(_context(), user_input=_MIXED_INPUT)
    ).header

    # 判定推翻了文本里的产物关键词
    assert "[Harness Precision Mode]" in block
    assert "[Harness Artifact Mode]" not in block
    assert judge.calls == [_MIXED_INPUT]


def test_judged_modes_keep_the_tool_protocol_block() -> None:
    builder = HarnessInvocationContextBuilder(mode_judge=_FakeJudge())

    block = builder.build_context_header(
        context=_context(),
        user_input="hello",
        has_tools=True,
        modes=frozenset(),
    )

    assert "[Harness Tool Protocol]" in block
    assert "[Harness Precision Mode]" not in block


def test_mode_decision_threshold_is_respected() -> None:
    builder = HarnessInvocationContextBuilder(
        HarnessInvocationContextConfig(mode_decision_threshold=0.8),
        mode_judge=_FakeJudge({"precision": 0.6}),
    )

    block = asyncio.run(
        builder.aprepare_context(_context(), user_input=_MIXED_INPUT)
    ).header

    assert "[Harness Precision Mode]" not in block
    assert "[Harness Artifact Mode]" not in block


def test_failing_judge_falls_back_to_keywords() -> None:
    builder = HarnessInvocationContextBuilder(
        mode_judge=_FakeJudge(error=DecisionModelDisabledError("not configured"))
    )

    block = asyncio.run(
        builder.aprepare_context(_context(), user_input=_MIXED_INPUT)
    ).header

    assert "[Harness Precision Mode]" in block
    assert "[Harness Artifact Mode]" in block


def test_plugin_judges_once_per_invocation() -> None:
    judge = _FakeJudge({"precision": 0.9})
    plugin = HarnessInvocationContextPlugin(
        context_builder=HarnessInvocationContextBuilder(mode_judge=judge),
        store=InMemoryHarnessStore(),
    )

    def _invoke(invocation_id: str) -> str:
        request = LlmRequest(contents=[])
        asyncio.run(
            plugin.before_model_callback(
                callback_context=SimpleNamespace(
                    session=SimpleNamespace(id="s1", app_name="app", user_id="u1"),
                    user_id="u1",
                    invocation_id=invocation_id,
                    user_content=types.Content(
                        role="user", parts=[types.Part(text=_MIXED_INPUT)]
                    ),
                ),
                llm_request=request,
            )
        )
        return str(request.config.system_instruction or "")

    first = _invoke("r1")
    second = _invoke("r1")
    third = _invoke("r2")

    assert "[Harness Precision Mode]" in first
    assert "[Harness Precision Mode]" in second
    assert "[Harness Precision Mode]" in third
    assert len(judge.calls) == 2


def test_build_mode_judge_is_opt_in() -> None:
    disabled = DecisionExtension(DecisionModelConfig.disabled())

    assert (
        build_mode_judge(HarnessInvocationContextConfig(), extension=disabled) is None
    )
    assert (
        build_mode_judge(
            HarnessInvocationContextConfig(mode_strategy="decision"),
            extension=disabled,
        )
        is None
    )
    assert (
        build_mode_judge(
            HarnessInvocationContextConfig(mode_strategy="decision"),
            extension=DecisionExtension(DecisionModelConfig(enabled=True, api_key="k")),
        )
        is not None
    )
