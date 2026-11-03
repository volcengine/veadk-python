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


"""Public Skill Sandbox agent backed by AgentKit Skill A2A sessions."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from veadk.agents.agentkit_remote_sandbox_agent import AgentkitRemoteSandboxAgent


class SkillSandboxAgent(AgentkitRemoteSandboxAgent):
    """Delegate an ADK turn directly to an AgentKit Skills Sandbox session."""

    tool_type: Literal["Skill"] = "Skill"
    tool_id_env: str | None = "AGENTKIT_TOOL_ID_SKILLS"
    guardrails: str = ""
    timeout: float | None = Field(default=None, gt=0, lt=86000, exclude=True)

    def model_post_init(self, context):
        if self.timeout is not None:
            self.request_timeout = self.timeout
            self.ttl = max(int(self.timeout), self.ttl)
        super().model_post_init(context)

    def _prepare_task(self, task):
        guardrails = self.guardrails.strip()
        if not guardrails:
            return task
        return f"{guardrails}\n\n用户请求 / User request:\n{task}"
