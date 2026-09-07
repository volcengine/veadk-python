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

"""Parallel Agent Studio fixture."""

from common import labelled_agent

from veadk.agents.parallel_agent import ParallelAgent

root_agent = ParallelAgent(
    name="parallel_agent",
    description="Runs three verbose specialists concurrently.",
    sub_agents=[
        labelled_agent("parallel_alpha", "facts", output_key="parallel_alpha"),
        labelled_agent("parallel_beta", "risks", output_key="parallel_beta"),
        labelled_agent(
            "parallel_gamma", "recommendations", output_key="parallel_gamma"
        ),
    ],
)
