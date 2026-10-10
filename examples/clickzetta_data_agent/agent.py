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

"""A VeADK agent that exposes ClickZetta through typed read-only tools."""

from veadk import Agent

from .tools import (
    DEFAULT_DOMAIN_ID,
    ask_clickzetta_analytics,
    get_clickzetta_runtime_overview,
    get_clickzetta_status,
    get_semantic_catalog,
    list_clickzetta_assets,
    run_readonly_sql,
)


AGENT_INSTRUCTION = f"""
你是企业数据分析 Agent，基于 VeADK 运行，并通过强类型只读工具访问 ClickZetta / 云器。
默认 ClickZetta Analytics Agent 分析域 ID 为 {DEFAULT_DOMAIN_ID}。

必须遵守：
1. 只通过已注册工具访问云器，不生成或执行 shell 命令。
2. 所有工具必须串行调用；尤其不得在同一 Analytics Agent session 并发问数。
3. 业务问数前调用 get_semantic_catalog，明确指标、数据集与口径。
4. 连接、运行状态和资产问题分别调用对应工具。
5. 仅在用户明确要求 SQL 时调用 run_readonly_sql；工具拒绝时如实解释。
6. 禁止写入、启停任务、修改集群、修改权限或读取凭据。
7. 不猜测数据，不主动扩展政策或因果分析。
8. 最终用中文给出“结论、依据/口径、数据来源、执行边界”。
""".strip()

root_agent = Agent(
    name="clickzetta_readonly_data_agent",
    description="Enterprise data agent backed by typed, read-only ClickZetta tools.",
    instruction=AGENT_INSTRUCTION,
    tools=[
        get_clickzetta_status,
        get_clickzetta_runtime_overview,
        list_clickzetta_assets,
        get_semantic_catalog,
        ask_clickzetta_analytics,
        run_readonly_sql,
    ],
)

AGENT_DISPLAY_NAMES = {
    "clickzetta_readonly_data_agent": "ClickZetta read-only data agent",
}
