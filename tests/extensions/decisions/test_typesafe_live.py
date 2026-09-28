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

"""Smoke tests against the real TypeSafe System One endpoint.

TypeSafe is a paid, shared service, so these tests are opt in and stay out of a
normal run:

```bash
TYPESAFE_RUN_SMOKE=1 TYPESAFE_API_KEY=... pytest -m typesafe_smoke
```

They answer one question the offline tests cannot: whether the contract the
plugin was written against still holds on the live endpoint.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from veadk.extensions.decisions import (
    ChoiceAnswer,
    DecisionExtension,
    DecisionModelConfig,
    NoulAnswer,
    ScoreAnswer,
    choice_question,
    noul_question,
    score_question,
)
from veadk.extensions.harness.modules.agent_routing import DecisionAgentRouter
from veadk.extensions.harness.modules.final_response_verifier.support_judge import (
    DecisionSupportJudge,
)
from veadk.extensions.harness.modules.invocation_context.mode_judge import (
    DecisionModeJudge,
)
from veadk.extensions.harness.modules.long_run_control.judge import (
    DecisionConvergenceJudge,
)
from veadk.extensions.harness.modules.skill_prefilter import DecisionSkillJudge
from veadk.extensions.harness.modules.tool_result_compactor import (
    DecisionCompactionJudge,
)
from veadk.extensions.harness.schemas import ToolReceipt
from veadk.memory.auto_save_judge import DecisionMemorySaveJudge
from veadk.memory.recall_judge import DecisionRecallJudge

API_KEY = os.environ.get("TYPESAFE_API_KEY", "")
API_BASE = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
RUN_SMOKE = os.environ.get("TYPESAFE_RUN_SMOKE") == "1"

pytestmark = [
    pytest.mark.typesafe_smoke,
    pytest.mark.skipif(
        not (RUN_SMOKE and API_KEY),
        reason="set TYPESAFE_RUN_SMOKE=1 and TYPESAFE_API_KEY to call the live endpoint",
    ),
]

URGENT_TICKET = (
    "Hi, I have been trying to connect my Stripe account for 3 days and the "
    "integration keeps failing. I am losing sales. Please help ASAP."
)


def _extension() -> DecisionExtension:
    return DecisionExtension(
        DecisionModelConfig(enabled=True, api_base=API_BASE, api_key=API_KEY)
    )


def test_one_call_answers_all_three_primitives() -> None:
    result = _extension().evaluate(
        state=URGENT_TICKET,
        questions={
            "is_urgent": noul_question("Does this message express urgency?"),
            "department": choice_question(
                "Which team should handle this",
                {"billing": "Payment issues", "technical": "Integration problems"},
            ),
            "frustration": score_question(
                "How frustrated is the customer?", ["Calm", "Frustrated", "Angry"]
            ),
        },
    )

    assert result.model, "the response must name the model that answered"
    urgent = result.answers["is_urgent"]
    assert isinstance(urgent, NoulAnswer) and 0.0 <= urgent.noul <= 1.0

    department = result.answers["department"]
    assert isinstance(department, ChoiceAnswer)
    assert department.choice in {"billing", "technical"}
    assert set(department.probabilities) == {"billing", "technical"}
    assert sum(department.probabilities.values()) == pytest.approx(1.0, abs=0.01)
    assert 0.0 <= department.confidence <= 1.0

    frustration = result.answers["frustration"]
    assert isinstance(frustration, ScoreAnswer)
    assert set(frustration.legend) == {"0", "1", "2"}
    assert 0.0 <= frustration.score <= 2.0
    assert sum(frustration.probabilities.values()) == pytest.approx(1.0, abs=0.01)
    assert 0.0 <= frustration.confidence <= 1.0


def test_environment_configuration_reaches_the_live_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What ``from_env`` builds must be usable against the real endpoint."""
    monkeypatch.setenv("DECISION_MODEL_ENABLED", "true")
    monkeypatch.setenv("DECISION_MODEL_API_KEY", API_KEY)
    monkeypatch.setenv("DECISION_MODEL_API_BASE", API_BASE)

    extension = DecisionExtension(DecisionModelConfig.from_env())

    assert extension.enabled
    result = asyncio.run(
        extension.aevaluate(
            state=URGENT_TICKET,
            questions={
                "is_urgent": noul_question("Does this message express urgency?")
            },
        )
    )
    assert isinstance(result.answers["is_urgent"], NoulAnswer)


def test_every_judgement_point_answers_against_the_live_endpoint() -> None:
    """Each judgement point must come back with a usable, in-range answer."""

    async def judge_all() -> None:
        extension = _extension()

        routed = await DecisionAgentRouter(extension).aroute(
            user_input=URGENT_TICKET,
            agents={
                "billing_agent": "handles invoices and refunds",
                "docs_agent": "answers product questions",
            },
        )
        assert routed in {"billing_agent", "docs_agent", None}

        skills = await DecisionSkillJudge(extension).aprobabilities(
            user_input="Draw a sequence diagram for the checkout flow.",
            skills={
                "archify": "renders architecture and sequence diagrams",
                "pptx": "builds slide decks",
            },
        )
        assert set(skills) == {"archify", "pptx"}
        assert all(0.0 <= value <= 1.0 for value in skills.values())

        kept = await DecisionCompactionJudge(extension).aprotect(
            goal="rank the candidates by score",
            evidence={
                1: "candidate A scored 0.91 with 3 matching skills",
                2: "small talk about lunch",
            },
        )
        assert set(kept) == {1, 2}
        assert all(0.0 <= value <= 1.0 for value in kept.values())

        judgement = await DecisionSupportJudge(extension).areview(
            answer="Done, I deployed the service and it is healthy.",
            receipts=[
                ToolReceipt(
                    name="run_shell", status="success", summary="wrote notes.md"
                )
            ],
            goal="deploy the service",
        )
        assert judgement.verdict in {"supported", "partial", "unsupported"}
        assert 0.0 <= judgement.support <= 1.0
        assert 0.0 <= judgement.confidence <= 1.0

        modes = await DecisionModeJudge(extension).aprobabilities(
            user_input="Refactor the parser and run the tests."
        )
        assert all(0.0 <= value <= 1.0 for value in modes.values())

        convergence = await DecisionConvergenceJudge(extension).ajudge(
            goal="make the failing test pass",
            trajectory=(
                "step 1: ran pytest, 3 failures\n"
                "step 2: fixed the fixture, 1 failure left\n"
                "step 3: ran pytest again, 1 failure remains"
            ),
        )
        assert 0.0 <= convergence.ready <= 1.0

        relevance = await DecisionRecallJudge(extension).arelevance(
            query="what does the user prefer for diagrams?",
            memories=[
                "the user prefers diagrams over prose",
                "the user lives in Shanghai",
            ],
        )
        assert set(relevance) == {0, 1}
        assert all(0.0 <= value <= 1.0 for value in relevance.values())
        assert relevance[0] > relevance[1]

        worth_saving = await DecisionMemorySaveJudge(extension).aworth_saving(
            events_text="user: my preferred timezone is Asia/Shanghai; agent: noted."
        )
        assert 0.0 <= worth_saving <= 1.0

    asyncio.run(judge_all())
