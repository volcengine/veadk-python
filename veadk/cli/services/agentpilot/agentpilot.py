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

from __future__ import annotations

import agent_pilot as ap
from agent_pilot.models import TaskType

from veadk import Agent
from veadk.prompts import prompt_optimization
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class AgentPilot:
    def __init__(self, api_key: str, path: str = "") -> None:
        self.api_key = api_key
        self.path = path

    def optimize(
        self,
        agents: list[Agent],
        feedback: str = "",
        model_name: str = "doubao-1.5-pro-32k-250115",
    ) -> str:
        for idx, agent in enumerate(agents):
            optimized_prompt = ""
            if feedback == "":
                logger.info("Optimizing prompt without feedback.")
                task_description = prompt_optimization.render_prompt_with_jinja2(agent)
            else:
                logger.info(f"Optimizing prompt with feedback: {feedback}")
                task_description = (
                    prompt_optimization.render_prompt_feedback_with_jinja2(
                        agent, feedback
                    )
                )

            logger.info(
                f"Optimizing prompt for agent {agent.name} by {model_name} [{idx + 1}/{len(agents)}]"
            )

            usage = None
            for chunk in ap.generate_prompt_stream(
                task_description=task_description,
                current_prompt=agent.instruction,
                model_name=model_name,
                task_type=TaskType.DIALOG,
                temperature=1.0,
                top_p=0.7,
                api_key=self.api_key,
            ):  # stream chunks of optimized prompt
                # Process each chunk as it arrives
                optimized_prompt += chunk.data.content
                # print(chunk.data.content, end="", flush=True)
                if chunk.event == "usage":
                    usage = chunk.data.usage
            optimized_prompt = optimized_prompt.replace("\\n", "\n")
            print(f"Optimized prompt for agent {agent.name}:\n{optimized_prompt}")
            logger.info(f"Token usage: {usage['total_tokens']}")

        return optimized_prompt
        return optimized_prompt
        return optimized_prompt
