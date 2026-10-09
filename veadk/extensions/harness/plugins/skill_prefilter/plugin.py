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

"""Skill-prefilter plugin for VeADK Runner.

The plugin rewrites the skill list of the request it is looking at, so the
advertised skills narrow to what this run needs. The agent instruction keeps
every skill, which is what the next run starts from.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from google.adk.models import LlmRequest, LlmResponse
from google.adk.plugins import BasePlugin

from veadk.extensions.decisions import DecisionModelError
from veadk.extensions.harness.modules.skill_prefilter import (
    AdvertisedSkills,
    HarnessSkillPrefilterConfig,
    SkillJudge,
    apply_skill_selection,
    build_skill_judge,
    parse_advertised_skills,
    skill_selection,
)
from veadk.extensions.harness.plugins._shared.callback_utils import (
    run_context_from_callback,
)
from veadk.extensions.harness.plugins.content_adapter import (
    content_to_text,
    set_system_instruction_text,
    system_instruction_text,
)
from veadk.extensions.harness.schemas import HarnessEvent, HarnessInvocationRef
from veadk.extensions.harness.stores import HarnessStoreProtocol, InMemoryHarnessStore
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext

logger = get_logger(__name__)

#: 判定结果按 invocation 缓存，同一次运行只问一次。
_MAX_CACHED_SELECTIONS = 64


class HarnessSkillPrefilterPlugin(BasePlugin):
    """Advertises only the skills a request needs."""

    def __init__(
        self,
        *,
        config: HarnessSkillPrefilterConfig | None = None,
        judge: SkillJudge | None = None,
        store: HarnessStoreProtocol | None = None,
        profile: str = "default",
    ) -> None:
        super().__init__(name="harness_skill_prefilter_plugin")
        self.config = config or HarnessSkillPrefilterConfig()
        self.judge = judge if judge is not None else build_skill_judge(self.config)
        self.store = store or InMemoryHarnessStore()
        self.profile = profile
        self._selections: OrderedDict[tuple[str, str], frozenset[str]] = OrderedDict()

    @property
    def uses_judgement(self) -> bool:
        """Whether a decision model narrows the advertised skills."""
        return self.judge is not None

    async def before_model_callback(
        self,
        *,
        callback_context: "CallbackContext",
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        advertised = self._advertised(llm_request)
        if advertised is None:
            return None
        run_context = run_context_from_callback(
            callback_context,
            profile=self.profile,
        )
        keep = await self._selection(run_context, advertised, callback_context)
        if keep is None:
            return None
        text, dropped = apply_skill_selection(advertised, keep)
        if not dropped:
            return None
        set_system_instruction_text(llm_request, text)
        self.store.append_event(
            HarnessEvent(
                event_type="skill_prefilter.report",
                run_context=run_context,
                payload={
                    "advertised": len(advertised.entries),
                    "listed": len(advertised.entries) - len(dropped),
                    "dropped": list(dropped),
                },
            )
        )
        return None

    def _advertised(self, llm_request: LlmRequest) -> AdvertisedSkills | None:
        """Return the advertised list worth judging.

        A list of one skill has nothing to narrow, and a library past the
        per-judgement budget is left alone: judging only its first candidates
        would drop the rest without ever asking about them.
        """
        if self.judge is None:
            return None
        advertised = parse_advertised_skills(system_instruction_text(llm_request))
        if advertised is None or len(advertised.entries) < 2:
            return None
        if len(advertised.entries) > self.config.max_candidates:
            logger.warning(
                "%d advertised skills exceed the %d a judgement covers; "
                "advertising every skill",
                len(advertised.entries),
                self.config.max_candidates,
            )
            return None
        return advertised

    async def _selection(
        self,
        run_context: HarnessInvocationRef,
        advertised: AdvertisedSkills,
        callback_context: "CallbackContext",
    ) -> frozenset[str] | None:
        """Return the skills to keep, or ``None`` when nothing was judged."""
        key = (run_context.session_id, run_context.invocation_id)
        cached = self._selections.get(key)
        if cached is not None:
            return cached
        try:
            probabilities = await self.judge.aprobabilities(
                # 只送用户消息的正文：消息 dump 里还有一堆未设置字段，
                # 与问题无关的内容会拉低判定准确率。
                user_input=content_to_text(
                    getattr(callback_context, "user_content", None)
                ),
                skills=advertised.descriptions,
            )
        except DecisionModelError as exc:
            logger.warning("skill judge unavailable, advertising every skill: %s", exc)
            return None
        keep = skill_selection(
            probabilities,
            advertised.names,
            threshold=self.config.decision_threshold,
        )
        self._selections[key] = keep
        while len(self._selections) > _MAX_CACHED_SELECTIONS:
            self._selections.popitem(last=False)
        return keep


__all__ = ["HarnessSkillPrefilterPlugin"]
