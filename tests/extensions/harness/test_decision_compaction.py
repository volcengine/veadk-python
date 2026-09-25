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

"""Decision-model judged compaction: opt-in, degradation, real ADK roles."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from types import SimpleNamespace

from google.adk.models import LlmRequest
from google.genai import types

from veadk.extensions.decisions import DecisionModelDisabledError
from veadk.extensions.decisions import DecisionModelConfig, DecisionExtension
from veadk.extensions.harness.modules.tool_result_compactor import (
    DECISION_KEEP_REASON,
    DECISION_SUMMARIZE_REASON,
    ToolResultCompactor,
    ToolResultCompactorConfig,
    build_compaction_judge,
)
from veadk.extensions.harness.plugins import HarnessCompressPlugin
from veadk.extensions.harness.schemas import CompressionRequest, ConversationMessage
from veadk.extensions.harness.stores import InMemoryHarnessStore

# 真实 ADK 形态：工具结果是 role=user/model，而不是协议无关的 "tool"
_ADK_ROLE_MESSAGES = [
    ConversationMessage(role="user", content="goal: rank the candidates by score"),
    ConversationMessage(role="user", content="tool_result: " + "x" * 9000),
    ConversationMessage(role="model", content="I inspected the table."),
    ConversationMessage(role="user", content="tool_result: " + "y" * 9000),
    ConversationMessage(role="model", content="One more check needed."),
    ConversationMessage(role="user", content="tool_result: " + "z" * 9000),
    ConversationMessage(role="model", content="Now I will summarize."),
    ConversationMessage(role="user", content="go on"),
]


class _FakeJudge:
    """Record what the policy asked about and return fixed probabilities."""

    def __init__(
        self,
        probabilities: Mapping[int, float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.probabilities = dict(probabilities or {})
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def aprotect(self, *, goal: str, evidence: Mapping[int, str]):
        self.calls.append({"goal": goal, "evidence": dict(evidence)})
        if self.error is not None:
            raise self.error
        return {index: self.probabilities.get(index, 0.0) for index in evidence}


def _config(**overrides) -> ToolResultCompactorConfig:
    settings = {
        "max_context_chars": 12000,
        "min_candidate_chars": 4000,
        "summary_chars": 400,
    }
    settings.update(overrides)
    return ToolResultCompactorConfig(**settings)


def _request() -> CompressionRequest:
    return CompressionRequest(
        messages=list(_ADK_ROLE_MESSAGES),
        max_context_chars=12000,
    )


def test_builtin_strategy_keeps_the_current_plan() -> None:
    """The default strategy must not change any existing decision."""

    compactor = ToolResultCompactor(_config())
    plan = compactor.policy.plan(_request().messages)

    assert compactor.uses_judgement is False
    assert [decision.action for decision in plan.decisions] == [
        "protect",
        "protect",
        "skip",
        "protect",
        "skip",
        "protect",
        "protect",
        "protect",
    ]
    assert plan.summary["candidate_count"] == 0
    assert "judged_by" not in plan.summary


def test_builtin_strategy_keeps_its_known_limitation() -> None:
    """Characterise the current behaviour the decision strategy replaces.

    Role labels are the only signal the builtin rules have, so on real ADK
    traffic no tool output becomes a candidate and the overflow is resolved by
    dropping whole messages instead of summarizing them.
    """

    compactor = ToolResultCompactor(_config())
    result = compactor.compress_messages(_request())

    assert result.report.changed is True
    assert result.report.omitted_messages > 0
    kept_roles = [message.role for message in result.messages]
    assert kept_roles.count("model") < 4


def test_judge_decides_every_candidate() -> None:
    judge = _FakeJudge({1: 0.9, 3: 0.1, 5: 0.1})
    compactor = ToolResultCompactor(_config(), compaction_judge=judge)

    plan = asyncio.run(compactor.policy.aplan(_ADK_ROLE_MESSAGES))

    reasons = {decision.index: decision.reason for decision in plan.decisions}
    assert reasons[0] == "user_intent"
    assert reasons[1] == DECISION_KEEP_REASON
    assert reasons[3] == DECISION_SUMMARIZE_REASON
    assert reasons[5] == DECISION_SUMMARIZE_REASON
    assert reasons[6] == "recent_feedback"
    assert plan.candidate_indexes == [3, 5]
    assert plan.summary["judged_by"] == "decision_model"
    assert plan.summary["judged_candidates"] == 3
    assert plan.summary["kept_verbatim"] == 1


def test_judge_receives_every_candidate_in_one_call() -> None:
    judge = _FakeJudge()
    compactor = ToolResultCompactor(_config(), compaction_judge=judge)

    asyncio.run(compactor.policy.aplan(_ADK_ROLE_MESSAGES, goal="rank them"))

    assert len(judge.calls) == 1
    assert judge.calls[0]["goal"] == "rank them"
    assert sorted(judge.calls[0]["evidence"]) == [1, 3, 5]


def test_judge_is_not_called_without_candidates() -> None:
    judge = _FakeJudge()
    compactor = ToolResultCompactor(_config(), compaction_judge=judge)
    messages = [
        ConversationMessage(role="system", content="be brief"),
        ConversationMessage(role="user", content="hello"),
        ConversationMessage(role="model", content="hi"),
    ]

    plan = asyncio.run(compactor.policy.aplan(messages))

    assert judge.calls == []
    assert plan.summary["candidate_count"] == 0


def test_keep_threshold_is_respected() -> None:
    judge = _FakeJudge({1: 0.6, 3: 0.85})
    compactor = ToolResultCompactor(
        _config(decision_keep_threshold=0.8),
        compaction_judge=judge,
    )

    plan = asyncio.run(compactor.policy.aplan(_ADK_ROLE_MESSAGES))

    reasons = {decision.index: decision.reason for decision in plan.decisions}
    assert reasons[1] == DECISION_SUMMARIZE_REASON
    assert reasons[3] == DECISION_KEEP_REASON


def test_disabled_decision_model_degrades_to_builtin_rules() -> None:
    judge = _FakeJudge(error=DecisionModelDisabledError("not configured"))
    compactor = ToolResultCompactor(_config(), compaction_judge=judge)

    plan = asyncio.run(compactor.policy.aplan(_ADK_ROLE_MESSAGES))

    assert plan == ToolResultCompactor(_config()).policy.plan(_ADK_ROLE_MESSAGES)


def test_decision_strategy_compacts_instead_of_dropping_messages() -> None:
    judge = _FakeJudge({1: 0.9})
    compactor = ToolResultCompactor(
        _config(strategy="decision"),
        compaction_judge=judge,
    )

    result = asyncio.run(compactor.acompress_messages(_request(), goal="rank them"))

    assert result.report.omitted_messages == 0
    assert result.report.compressed_chars <= 12000
    # 没有被删掉的消息，只有被摘要的内容
    assert len(result.messages) == len(_ADK_ROLE_MESSAGES)
    assert [message.role for message in result.messages] == [
        message.role for message in _ADK_ROLE_MESSAGES
    ]
    # 被判为"必须原样保留"的证据不被改写，其余大输出被摘要
    assert result.messages[1] == _ADK_ROLE_MESSAGES[1]
    assert result.messages[3] != _ADK_ROLE_MESSAGES[3]
    assert result.messages[5] != _ADK_ROLE_MESSAGES[5]


def test_async_and_sync_paths_agree_without_a_judge() -> None:
    compactor = ToolResultCompactor(_config())

    sync_result = compactor.compress_messages(_request())
    async_result = asyncio.run(compactor.acompress_messages(_request()))

    assert sync_result == async_result


def test_request_that_already_fits_is_untouched() -> None:
    judge = _FakeJudge()
    compactor = ToolResultCompactor(_config(), compaction_judge=judge)

    result = asyncio.run(
        compactor.acompress_messages(
            _request().model_copy(update={"max_context_chars": 10**6})
        )
    )

    assert result.report.changed is False
    assert judge.calls == []


def test_build_compaction_judge_is_opt_in() -> None:
    disabled = DecisionExtension(DecisionModelConfig.disabled())

    assert build_compaction_judge(_config(), extension=disabled) is None
    assert (
        build_compaction_judge(_config(strategy="decision"), extension=disabled) is None
    )
    assert (
        build_compaction_judge(
            _config(strategy="decision"),
            extension=DecisionExtension(DecisionModelConfig(enabled=True, api_key="k")),
        )
        is not None
    )


def test_compress_plugin_awaits_the_judged_path() -> None:
    judge = _FakeJudge({0: 0.9})
    plugin = HarnessCompressPlugin(
        compactor=ToolResultCompactor(
            ToolResultCompactorConfig(max_tool_result_chars=1000),
            compaction_judge=judge,
        ),
        store=InMemoryHarnessStore(),
    )
    request = LlmRequest(
        contents=[
            types.Content(role="user", parts=[types.Part(text="Create a report")]),
            types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name="run_code",
                        response={"result": "x" * 8000},
                    )
                ],
            ),
        ]
    )

    asyncio.run(
        plugin.before_model_callback(
            callback_context=SimpleNamespace(
                session=SimpleNamespace(id="s1", app_name="app", user_id="u1"),
                user_id="u1",
                invocation_id="r1",
                user_content=types.Content(
                    role="user", parts=[types.Part(text="Create a report")]
                ),
            ),
            llm_request=request,
        )
    )

    assert request.contents[1].parts[0].function_response.response["harness_compressed"]
