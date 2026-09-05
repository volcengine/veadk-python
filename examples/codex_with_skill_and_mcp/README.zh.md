# codex_with_skill_and_mcp

一个 `runtime="codex"` 的 Agent，在 chat 后端（火山方舟）上**同时使用本地 skill 和 MCP 工具**。

> **这个示例是什么：** 一份**接线参考**。它展示本地 skill 和 MCP 工具在
> `runtime="codex"` 下分别怎么到达模型，任务故意选得极简（问一次天气），
> 好让画面里只剩下管道本身。请照这个定位读它，而不要把它当成「这类任务应该用
> codex 运行时」的推荐——一次固定的工具调用加一段格式化回答，正是
> `runtime="adk"` 更快更便宜的场景，也不必每回合起一个 Codex 子进程。
> 这个运行时**真正**的用处——模型写脚本、跑起来、读 traceback、自己改好——
> 见 [`codex_data_analysis/`](../codex_data_analysis/) 与
> [`codex_ops_assistant/`](../codex_ops_assistant/)，或
> [什么时候该用 codex 运行时](../../docs/content/docs/framework/agent/runtime.mdx#什么时候该用-codex-运行时)。

```
codex_with_skill_and_mcp/
├── main.py                     # Agent 定义 + 一次示例运行
├── mcp_server.py               # 一个极简的 stdio MCP server（get_weather）
└── skills/
    └── weather-style/
        └── SKILL.md            # 一个本地 skill（规定天气回答的措辞）
```

## 演示了什么

Agent 用最普通的 VeADK 方式挂了两个工具：

- 一个 **skill**——`SkillToolset(skills=[load_skill_from_dir(...)])`
- 一个 **MCP 工具**——`MCPToolset(...)`（这里用 stdio，可换成 streamable-HTTP）

问 *“北京天气怎么样？”*，Agent 会用 skill 规定的格式、结合工具返回的数据回答，例如：

```
Beijing: sunny, 28°C. Have a nice day!
```

## codex runtime 怎么处理

Codex 接管了整轮（而不是 ADK 的 LLM flow），且只会说 Responses API——所以两个工具走不同的路：

- **Skill** → 被物化到 Codex 的磁盘 skill 目录（`$CODEX_HOME/skills/<name>/SKILL.md`），由 Codex 原生 skill 机制发现。与后端无关。
- **MCP 工具** → 不能直接交给 Codex（它会把 MCP 工具以 `namespace` 类型呈现给模型，而 chat 后端不认），所以由 runtime 的 Responses shim 把它们当普通 `function` 工具喂给后端、并**自己执行**，对 Codex 不可见。

这些都由 runtime 处理——Agent 代码就是普通的工具挂载。

## 运行

```bash
pip install "veadk-python[codex]"   # openai-codex + 自带的 Codex CLI 二进制
# 方舟（或其他 OpenAI 兼容 chat）凭证：
export MODEL_AGENT_API_KEY=...
export MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3
export MODEL_AGENT_NAME=deepseek-v4-flash-260425

python examples/codex_with_skill_and_mcp/main.py
```

## 说明

- 工具由 runtime 的 shim 调度，但调用、结果、状态变更、确认和鉴权都会作为标准 ADK 事件进入 Session/Trace/UI。
- 支持静态鉴权（header / bearer token / ve-identity workload token）以及工具执行中触发的 ADK 交互式鉴权；MCP toolset 在列举工具前触发的鉴权仍取决于对应 ADK/MCP 客户端能力。
- `runtime="codex"` 是**沙箱执行运行时**，不是 ADK 执行流程的等价替代品。`Agent` 上有一部分配置在它下面会**直接报错**（`sub_agents`、`output_schema`、`planner`、`code_executor`、`system_instruction` 以外的 `generate_content_config`、`include_contents="none"`、`enable_supervisor`，以及显式传入的 `model=`），另一部分会被丢弃并告警（`knowledgebase`、`example_store`、`skills_mode` 等）。详见[支持矩阵](../../docs/content/docs/framework/agent/runtime.mdx#支持矩阵)。
- 注意本例依赖的区别：ADK 的 `SkillToolset` 会被桥接进 Codex 原生 skill 系统，但 VeADK 自己的 `Agent(skills_mode=...)` **不会**——后者只会告警且不生效。
