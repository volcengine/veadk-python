# Dynamic Agent Delegation

这个示例展示 Main Agent 如何在运行时收集资源、创建一个或多个 Sub Agent，并通过
Google ADK 的 `transfer_to_agent` 事件把当前任务移交给指定 Sub Agent。Sub Agent
继续使用同一会话上下文，并直接输出最终答案。

## 主要流程

1. Main Agent 判断当前任务是否需要专门的 Sub Agent；简单任务仍由 Main Agent
   直接完成。
2. 需要委派时，Main Agent 先调用 `collect_resources`。公共 Skill Hub 按任务关键词
   检索；AgentKit 技能中心会枚举当前凭证可访问的全部 Skill Space；知识库和 VeADK
   内置工具同时并行收集。
3. Main Agent 根据召回结果设计一个或多个 Agent 配置，明确每个 Agent 的职责、模型、
   指令以及需要绑定的 Skill、知识库和工具。
4. Main Agent 调用 `create_agents`。工具只对最终选中的 AgentKit Skill 动态下载并挂载，
   同时解析内置工具、自定义 Python Tool 和嵌套 Sub Agent。
5. 创建成功后，Main Agent 通过 `transfer_to_agent` 把原任务移交给目标 Sub Agent。
   Sub Agent 在同一会话中执行任务，结果直接返回给用户。

`collect_resources` 和 `create_agents` 属于同一个 `CreateAgentToolset`。创建 Agent 前必须
先收集资源，并使用本次资源集合返回的 `collection_id` 和资源 `ref`。

在仓库根目录启动：

```bash
set -a
source .env
set +a
uv run veadk frontend \
  --agents-dir examples \
  --vite --dev \
  --host 127.0.0.1 \
  --port 8000 \
  --provider volcengine \
  --no-open
```

本地示例默认不启用 OAuth2 用户池，不需要传入用户池或客户端 UID。

打开 `http://127.0.0.1:5174/`，选择 `dynamic_agent_delegation`。

建议测试：

- `你好，介绍一下你自己。`：Main Agent 直接回答。
- `检索并总结今天 AgentKit 的最新公开资料，给出三条结论和来源。`：Main Agent
  收集资源、创建研究员，并把任务移交给研究员。
- `写一个 Python 工具计算一组数字的中位数，让子智能体调用它计算
  [3, 9, 2, 7, 5]。`：Main Agent 创建带自定义 Python Tool 的 Sub Agent 并移交。

公共 Skill Hub 由 Main Agent 根据任务生成关键词并检索，不需要配置 Space ID。
配置 AK/SK 或 STS 后，AgentKit 技能中心会自动检索当前账号可访问的全部 Skill
Space。`SKILL_SPACE_ID` 仅用于将检索范围限制到指定 Space，多个 Space ID 用逗号
分隔。兼容旧版 Skill Hub Space 时仍可使用 `SKILL_HUB_SPACE_ID`。
