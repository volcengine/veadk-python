# Dynamic Agent Delegation

这个示例展示 Main Agent 如何在运行时收集资源、创建一个或多个 Sub Agent，并通过
Google ADK 的 `transfer_to_agent` 事件把当前任务移交给指定 Sub Agent。Sub Agent
继续使用同一会话上下文，并直接输出最终答案。

在仓库根目录启动：

```bash
set -a
source /Users/bytedance/Projects/veadk-python/.env
set +a
uv run veadk frontend \
  --agents-dir examples \
  --vite --dev \
  --host 127.0.0.1 \
  --port 8000 \
  --provider volcengine \
  --oauth2-user-pool-uid 21b042ae-2980-45d0-9ef8-1add2bccb29b \
  --oauth2-user-pool-client-uid 81798d0b-c8c1-407f-a359-fd8ec99295cc \
  --oauth2-redirect-uri http://127.0.0.1:5174/oauth2/callback \
  --no-open
```

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
