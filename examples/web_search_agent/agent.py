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

"""A plain conversational agent with the built-in web_search tool.

Servable by the ADK API server (exposes a module-level `root_agent`). Needs
Volcengine AK/SK in the environment for web_search.
"""

from veadk import Agent
from veadk.tools.builtin_tools.web_search import web_search

agent = Agent(
    name="web_search_agent",
    description="通用助手，可联网搜索实时信息。",
    instruction=(
        "你是一个有用的中文助手。当用户的问题需要实时或最新信息时，先调用 "
        "web_search 工具检索，再基于结果回答；否则直接用自然语言回答。"
    ),
    tools=[web_search],
)

# Required by the Google ADK agent loader.
root_agent = agent
