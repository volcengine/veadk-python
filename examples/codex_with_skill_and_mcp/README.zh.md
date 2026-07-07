# codex_with_skill_and_mcp

一个 `runtime="codex"` 的 Agent，在 chat 后端（火山方舟）上**同时使用本地 skill 和 MCP 工具**。

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
pip install openai-codex          # 自带 Codex CLI 二进制
# 方舟（或其他 OpenAI 兼容 chat）凭证：
export MODEL_AGENT_API_KEY=...
export MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3
export MODEL_AGENT_NAME=deepseek-v4-flash-260425

python examples/codex_with_skill_and_mcp/main.py
```

## 说明

- 工具在 runtime 的 shim 内执行，因此对 Codex 不可见，目前不会作为独立的 ADK 事件出现（trace/前端看不到这步）。
- 交互式 MCP 鉴权（对话中途弹凭证）在 `runtime="codex"` 下不驱动；静态鉴权（header / bearer token / ve-identity workload token）可用。
```
