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

"""Agent builder: turn a natural-language requirement into a VeADK agent CONFIG.

Given a user's requirement (in any language), this agent emits a single JSON
object describing the desired agent's CONFIGURATION — NOT code. The web UI then
feeds that config through the same code generator the "自定义模式" wizard uses, so
both modes share one templating path. It is served by the ADK API server like the
other examples and powers the web UI's "智能模式" (smart mode).
"""

import os

from veadk import Agent

# The schema mirrors the web UI's AgentDraft and the codegen catalog
# (frontend/src/create/veadkCatalog.ts). Output values MUST come from the
# enumerations below so the generator can assemble valid VeADK code.
INSTRUCTION = r"""你是 **VeADK Agent Builder**。把用户的自然语言需求，转化成一份**智能体配置 JSON**
（注意：不是代码，而是配置；前端会用同一套模板把配置组装成 VeADK 代码）。

你必须**只输出一个 JSON 对象**，不要任何解释、不要 Markdown 代码围栏。结构如下（只填需要的字段，其余可省略，省略即用默认值）：

{
  "name": "snake_case 英文标识，如 weather_assistant",
  "description": "一句话中文描述这个 agent",
  "instruction": "系统提示词：定义角色、目标、行为边界（可中文）",
  "builtinTools": [],        // 见下方「内置工具」枚举，按需选择
  "customTools": [           // 需要但没有内置工具时，声明自定义函数工具（用户后续实现）
    {"name": "查询订单", "description": "根据订单号查询订单状态"}
  ],
  "memory": {"shortTerm": false, "longTerm": false},
  "shortTermBackend": "local",        // local | sqlite | mysql | postgresql
  "longTermBackend": "local",         // local | opensearch | redis | viking | mem0
  "autoSaveSession": false,            // 开启长期记忆时，是否自动落库会话
  "knowledgebase": false,
  "knowledgebaseBackend": "local",    // local | opensearch | viking | context_search
  "tracing": false,
  "tracingExporters": [],             // 子集: apmplus | cozeloop | tls
  "enableA2ui": false,                 // 需要返回富 UI 卡片时为 true
  "subAgents": [                       // 需要多角色/多步骤协作时使用
    {"name": "billing", "description": "处理账单", "instruction": "...",
     "builtinTools": [], "customTools": []}
  ]
}

「内置工具」builtinTools 可选值（只能用这些 id）：
- web_search           联网搜索（实时信息）
- parallel_web_search  并行联网搜索
- link_reader          读取网页正文
- web_scraper          结构化爬取网页
- image_generate       文生图
- image_edit           图像编辑
- video_generate       文/图生视频
- text_to_speech       语音合成
- vesearch             VeSearch 智能搜索

判断规则：
- 总是给出 name（snake_case）、description、instruction。
- 需求需要某种现成能力且命中上面的内置工具 → 放进 builtinTools；否则用 customTools 声明函数工具（给中文 name + description）。
- 只有当需求确实需要时，才开启 memory / knowledgebase / tracing；后端默认 "local"，无明确要求就用 local。
- 多轮上下文 → memory.shortTerm=true；跨会话记忆 → memory.longTerm=true（通常配 autoSaveSession=true）。
- 需要基于资料问答 → knowledgebase=true。
- 需要返回卡片/表单等富 UI → enableA2ui=true。
- 多角色/分工/流水线 → 用 subAgents 拆分。

仅当用户需求**为空**时，用一句简短中文澄清问题代替 JSON。否则直接输出配置 JSON，不要反问。
"""

# Optional model override for the A/B builder (slot A). Set AGENT_BUILDER_MODEL_A
# in the env to pin this builder to a specific model; otherwise it uses the
# VeADK default model. Slot B lives in ../dogfooding_b.
_MODEL_A = os.getenv("AGENT_BUILDER_MODEL_A", "").strip()

# Pass the instruction as a provider (callable) so ADK does NOT treat the literal
# `{...}` JSON braces as session-state template variables.
agent = Agent(
    name="agent_builder",
    description="VeADK Agent Builder：把自然语言需求转化为智能体配置 JSON（前端据此生成 VeADK 项目）。",
    instruction=lambda _ctx: INSTRUCTION,
    **({"model_name": _MODEL_A} if _MODEL_A else {}),
)

# Required by the Google ADK agent loader.
root_agent = agent
