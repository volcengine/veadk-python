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

"""Best-practice composition for the example Harness Agent."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from veadk import Agent, Runner

try:  # Support both ``python examples/harness/main.py`` and package imports.
    from .harness_modules import (
        ContextEngine,
        HarnessRunProcessor,
        LocalHarnessStore,
        ResultVerifier,
        wrap_tools,
    )
except ImportError:  # pragma: no cover - exercised by direct script execution.
    from harness_modules import (  # type: ignore
        ContextEngine,
        HarnessRunProcessor,
        LocalHarnessStore,
        ResultVerifier,
        wrap_tools,
    )


BASE_INSTRUCTION = """You are a concise research assistant.
Use tools when the request needs current, policy, or sourced facts. Cite only
sources returned by tools. If a fact is not supported by tool evidence, say so
clearly instead of guessing.
"""


def sample_policy_lookup(topic: str) -> dict[str, object]:
    """Lookup a mock policy document.

    Args:
        topic: Policy topic to search for, for example "security" or "travel".
    """

    return {
        "result": (
            "Sample AI usage policy v2026-06 requires source-backed answers for "
            "current external facts and recommends storing tool receipts for audits."
        ),
        "sources": [
            {
                "title": "AI Usage Policy v2026-06",
                "url": "https://example.com/policies/ai-usage-2026-06",
                "snippet": "source-backed answers for current external facts; store tool receipts",
            }
        ],
    }


def public_web_lookup(query: str) -> dict[str, object]:
    """Lookup a mock public web result.

    Args:
        query: Search query.
    """

    return {
        "result": (
            "The veADK Harness example demonstrates ContextEngine for task "
            "anchoring and ResultVerifier for evidence-backed final answers."
        ),
        "sources": [
            {
                "title": "veADK Harness example",
                "url": "https://example.com/veadk/harness-demo",
                "snippet": "ContextEngine anchors tasks; ResultVerifier checks evidence.",
            }
        ],
    }


class HarnessAgentBundle(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    agent: Agent
    runner: Runner
    processor: HarnessRunProcessor
    store: LocalHarnessStore
    context_engine: ContextEngine
    verifier: ResultVerifier

    async def run(
        self,
        messages: object,
        *,
        user_id: str = "demo-user",
        session_id: str = "harness-demo",
        **kwargs: object,
    ) -> str:
        """Run through the veADK Runner while binding Harness metadata."""

        with self.processor.bind_run(
            user_id=user_id,
            session_id=session_id,
            original_prompt=str(messages),
        ):
            return await self.runner.run(
                messages=messages,
                user_id=user_id,
                session_id=session_id,
                **kwargs,
            )

    def latest_report(
        self, *, session_id: str = "harness-demo"
    ) -> dict[str, object] | None:
        return self.store.latest_report(session_id=session_id)


def build_harness_agent(
    *,
    store_dir: str = ".harness_runs",
    verify: bool = True,
) -> HarnessAgentBundle:
    """Build a veADK Agent with the two example Harness modules attached."""

    store = LocalHarnessStore(store_dir)
    context_engine = ContextEngine(
        store=store, max_history_messages=6, max_context_chars=6000
    )
    verifier = ResultVerifier(store=store)
    tools = wrap_tools(
        [sample_policy_lookup, public_web_lookup],
        store=store,
    )
    processor = HarnessRunProcessor(
        store=store,
        context_engine=context_engine,
        verifier=verifier,
        verify=verify,
    )
    agent = Agent(
        name="harness_research_agent",
        description="Research assistant with example Harness context and verification modules.",
        instruction=context_engine.wrap_instruction(BASE_INSTRUCTION),
        tools=tools,
        run_processor=processor,
    )
    runner = Runner(agent=agent, app_name="harness_demo")
    return HarnessAgentBundle(
        agent=agent,
        runner=runner,
        processor=processor,
        store=store,
        context_engine=context_engine,
        verifier=verifier,
    )
