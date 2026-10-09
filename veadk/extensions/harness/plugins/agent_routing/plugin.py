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

"""Agent-routing plugin for VeADK Runner.

Handing a request to a sub-agent is a choice the model makes with a tool call.
The plugin asks a decision model the same question first and returns the
transfer call itself when the judgement is confident, so the model keeps
deciding every request the judgement is unsure about.

The judgement is made once per invocation, because the transferred agent runs
inside the same invocation: without that, a sub-agent that can transfer to its
peers could hand the request straight back.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Literal

from google.adk.models import LlmRequest, LlmResponse
from google.adk.plugins import BasePlugin
from google.genai import types

from veadk.extensions.decisions import (
    DEFAULT_JUDGEMENT_THRESHOLD,
    DecisionModelError,
)
from veadk.extensions.harness.modules.agent_routing import (
    AgentRouter,
    build_agent_router,
)
from veadk.extensions.harness.plugins._shared.callback_utils import (
    run_context_from_callback,
)
from veadk.extensions.harness.plugins.content_adapter import content_to_text
from veadk.extensions.harness.schemas import HarnessEvent
from veadk.extensions.harness.stores import HarnessStoreProtocol, InMemoryHarnessStore
from veadk.runtime.agent_transfer import TRANSFER_TOOL_NAME, get_transfer_targets
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.base_agent import BaseAgent
    from google.adk.agents.callback_context import CallbackContext

logger = get_logger(__name__)

RoutingStrategy = Literal["model", "decision"]

#: 记住「已问过路由」的 invocation 数上限。
_MAX_REMEMBERED_INVOCATIONS = 256


class HarnessAgentRoutingPlugin(BasePlugin):
    """Transfers to the agent a confident judgement picked."""

    def __init__(
        self,
        *,
        store: HarnessStoreProtocol | None = None,
        profile: str = "default",
        strategy: RoutingStrategy = "model",
        router: AgentRouter | None = None,
        confidence_threshold: float = DEFAULT_JUDGEMENT_THRESHOLD,
    ) -> None:
        super().__init__(name="harness_agent_routing_plugin")
        self.store = store or InMemoryHarnessStore()
        self.profile = profile
        self.strategy = strategy
        self.confidence_threshold = confidence_threshold
        self.router = router or build_agent_router(
            strategy,
            confidence_threshold=confidence_threshold,
        )
        self._judged: OrderedDict[tuple[str, str], None] = OrderedDict()

    @property
    def uses_judgement(self) -> bool:
        """Whether a decision model picks the transfer target."""
        return self.router is not None

    async def before_model_callback(
        self,
        *,
        callback_context: "CallbackContext",
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        if self.router is None or TRANSFER_TOOL_NAME not in llm_request.tools_dict:
            return None
        candidates = self._candidates(
            getattr(callback_context, "agent", None),
            llm_request,
        )
        if candidates is None:
            return None
        run_context = run_context_from_callback(
            callback_context,
            profile=self.profile,
        )
        key = (run_context.session_id, run_context.invocation_id)
        if key in self._judged:
            return None
        # 只送用户消息的正文：消息 dump 里还有一堆未设置字段，
        # 与问题无关的内容会拉低判定准确率。
        user_text = content_to_text(getattr(callback_context, "user_content", None))
        if not user_text.strip():
            return None
        self._remember(key)
        try:
            target = await self.router.aroute(user_input=user_text, agents=candidates)
        except DecisionModelError as exc:
            logger.warning("agent router unavailable, letting the model route: %s", exc)
            return None
        if target is None:
            return None
        self.store.append_event(
            HarnessEvent(
                event_type="agent_routing.transfer",
                run_context=run_context,
                payload={"target": target, "candidates": list(candidates)},
            )
        )
        return transfer_response(target)

    def _candidates(
        self, agent: "BaseAgent | None", llm_request: LlmRequest
    ) -> dict[str, str] | None:
        """Return the transfer targets of one agent, keyed by name.

        A single target is not a choice, so an agent tree without alternatives
        keeps its routing with the model. The names the transfer tool itself
        accepts win over the agent tree, because ADK resolves the transfer
        against them.
        """
        exposed = _exposed_agent_names(llm_request.tools_dict.get(TRANSFER_TOOL_NAME))
        targets = [
            target
            for target in get_transfer_targets(agent)
            if getattr(target, "name", "") and (not exposed or target.name in exposed)
        ]
        if len(targets) < 2:
            return None
        return {str(target.name): (target.description or "") for target in targets}

    def _remember(self, key: tuple[str, str]) -> None:
        """Record that one invocation has been judged already."""
        self._judged[key] = None
        while len(self._judged) > _MAX_REMEMBERED_INVOCATIONS:
            self._judged.popitem(last=False)


def transfer_response(target: str) -> LlmResponse:
    """Return the response that asks ADK to transfer to ``target``.

    It is the same ``transfer_to_agent`` call the model would have produced, so
    the transfer keeps its normal path, event, and downstream instructions.
    """
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name=TRANSFER_TOOL_NAME,
                        args={"agent_name": target},
                    )
                )
            ],
        )
    )


def _exposed_agent_names(tool: object) -> frozenset[str]:
    """Return the agent names one transfer tool accepts, when it lists them.

    ``TransferToAgentTool`` keeps its allowed names private, and those names are
    what ADK resolves a transfer against, so a judgement must not name a target
    that is missing from them.
    """
    names = getattr(tool, "_agent_names", None)
    if not names:
        return frozenset()
    return frozenset(str(name) for name in names)


__all__ = ["HarnessAgentRoutingPlugin", "RoutingStrategy", "transfer_response"]
