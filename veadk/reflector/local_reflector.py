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

import json
import os

from typing_extensions import override

from veadk import Agent, Runner
from veadk.reflector.base_reflector import BaseReflector, ReflectorResult


class LocalReflector(BaseReflector):
    def __init__(self, agent: Agent):
        super().__init__(agent)

    def _read_traces_from_dir(self, trace_dir: str) -> list[dict]:
        traces = []
        for file in os.listdir(trace_dir):
            if file.endswith(".json"):
                with open(os.path.join(trace_dir, file), "r") as f:
                    traces.append(json.load(f))
        return traces

    @override
    async def reflect(self, trace_file: str) -> ReflectorResult:
        assert os.path.isfile(trace_file), f"{trace_file} is not a file."
        assert trace_file.endswith(".json"), f"{trace_file} is not a valid json file."

        with open(trace_file, "r") as f:
            traces = json.load(f)

        agent = Agent(
            name="agent_reflector",
            description="Reflect the traces and generate a optimized system prompt.",
            instruction="""You are a helpful optimizer and reflector.
            
Your task is to reflect the traces and generate a optimized system prompt (based on the given agent's system prompt).

You should response in json format with two fields: 
- optimized_prompt: The optimized system prompt.
- reason: The reason for the optimized prompt.
            """,
            output_schema=ReflectorResult,
        )
        runner = Runner(agent)

        response = await runner.run(
            messages=f"The system prompt is: {self.agent.instruction}, and the history traces are: {traces}"
        )

        if response:
            try:
                optimized_prompt = json.loads(response).get("optimized_prompt", "")
                reason = json.loads(response).get("reason", "")
            except Exception as e:
                optimized_prompt = ""
                reason = f"response from optimizer is not valid json: {e}, response: {response}"
        else:
            optimized_prompt = ""
            reason = "response from optimizer is empty"

        return ReflectorResult(
            optimized_prompt=optimized_prompt,
            reason=reason,
        )
