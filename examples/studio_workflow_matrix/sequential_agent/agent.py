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

"""Sequential Agent Studio fixture."""

from common import labelled_agent

from veadk.agents.sequential_agent import SequentialAgent

root_agent = SequentialAgent(
    name="sequential_agent",
    description="Runs three labelled LLM stages in order.",
    sub_agents=[
        labelled_agent("sequence_one", "first sequential", output_key="seq_one"),
        labelled_agent("sequence_two", "second sequential", output_key="seq_two"),
        labelled_agent("sequence_three", "final sequential", output_key="seq_three"),
    ],
)
