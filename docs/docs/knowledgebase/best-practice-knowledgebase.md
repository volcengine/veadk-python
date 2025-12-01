# 知识库最佳实践

本文档介绍如何在企业级或生产环境中，将知识库与智能体深度结合，实现复杂、多步骤的知识驱动型应用。

---

## 场景

在本最佳实践中，我们扮演企业 IT 运维部门来构建一个智能运维助手，重点支持：

- **跨部门知识整合**：整合网络、服务器、软件、权限管理等不同部门的文档和操作手册；
- **多步骤任务指导**：用户描述问题后，智能体能自动生成操作步骤，并根据执行结果进行动态调整；
- **问题追踪与知识更新**：每次任务执行后，自动记录解决方案和异常情况，更新知识库；
- **多渠道交互**：支持 Web 界面、命令行交互等入口。

在该场景中，知识库不仅存储静态文档，还与 Agent、工具和短期/长期记忆结合，实现“查询—推理—执行—更新”的闭环。

## 构建思路

### 知识整理与分类

- 将部门文档进行分类（网络、服务器、应用软件等）；
- 对文档进行向量化处理，用于语义检索；
- 对流程型文档标记操作步骤和条件分支。

### Backend 构建与集成

- 使用向量数据库存储向量化文档；
- 提供检索接口 `query(prompt, context)`，结合上下文提供针对性答案；
- 支持知识更新接口，将新的操作经验或异常处理结果写回知识库。

### 智能体与工具组合

- Agent 调用知识库获取操作步骤；
- 使用短期记忆跟踪会话状态和步骤完成情况；
- 使用长期记忆保存跨会话的偏好或历史记录；
- 调用工具（如 Sandbox 或系统 API）执行任务或模拟操作。

### 多步骤任务执行与动态调整

- 用户描述问题 → Agent 检索知识库 → 提取步骤 → 执行步骤 → 根据结果调整下一步；
- 记录失败或异常信息，并将成功经验更新至知识库。

## 效果

- 实现跨部门知识统一访问；
- 支持多轮、复杂操作任务；
- 每次操作后自动更新知识库，形成持续学习能力。

## 实现您的 IT 运维助手

下面按步骤实现智能运维助手。

### 知识库准备

准备以下知识资产，并以 Markdown 组织：

- 网络相关文档（如 IP 地址、端口、协议等）；
- 服务器相关文档（如安装配置、监控指标等）；
- 应用软件相关文档（如使用方法、故障排除等）；
- 权限管理相关文档（如角色分配、访问控制等）。

示例：

```markdown title="network_sop.md"
# 网络排障 Runbook（摘要）

## DNS 解析异常

- 检查本机 /etc/resolv.conf；
- 检查上游 DNS 可达性；
- 刷新 DNS 缓存：`systemd-resolve --flush-caches`；
- 如为权威解析变更：确认变更已在权威 DNS 生效，等待 TTL；
- 如需紧急处理，可调用标准化作业：`dns-cache-flush`
```

```markdown title="host_sop.md"
# 主机/中间件 Runbook（摘要）

## CPU 飙高

- top 确认进程；
- dump/火焰图采集；
- 参考 SOP：`collect-cpu-profile`
```

```markdown title="app_sop.md"
# 业务应用 Runbook（摘要）

## 502 网关错误

- 查看 Nginx/Ingress 错误日志；
- 回滚至上一稳定版本；
- 触发金丝雀放量回退；
```

```markdown title="security_sop.md"
# 安全事件 Runbook（摘要）

## 失陷主机初步处置

- 下线隔离；
- Hash/IOC 采集；
- 通报安全应急群；
```

将上述文档挂载至 VeADK 知识库中：

```python
from veadk.knowledgebase import KnowledgeBase

kb = KnowledgeBase(
    backend="viking",
    index="itops_kb",
)

kb.add_from_files(
    [
        "network_sop.md",
        "host_sop.md",
        "app_sop.md",
        "security_sop.md",
    ]
)
```

## 构建多智能体并挂载知识库

```python
network_agent = Agent(
    name="network_agent",
    description="Network operations agent focusing on DNS/Connectivity.",
    instruction="仅根据你的知识库回答网络排障问题。不要臆测，不要编造。必要时建议提交工单。",
    knowledgebase=kb_network,
    model=network_llm,
)

host_agent = Agent(
    name="host_agent",
    description="Host/Middleware operations agent.",
    instruction="仅根据你的知识库回答主机/中间件排障问题。必要时建议采集证据或提交工单。",
    knowledgebase=kb_host,
    model=host_llm,
)

app_agent = Agent(
    name="app_agent",
    description="Application operations agent.",
    instruction="仅根据你的知识库回答业务应用排障问题。必要时建议回滚或触发标准化作业。",
    knowledgebase=kb_app,
    model=app_llm,
)

sec_agent = Agent(
    name="sec_agent",
    description="Security operations agent.",
    instruction="仅根据你的知识库回答安全相关问题。对可能的失陷要给出初步处置建议。",
    knowledgebase=kb_sec,
    model=sec_llm,
)

root_agent = Agent(
    name="itops_root",
    description="Planner that routes user intents to the right department agent.",
    instruction=(
        "你是 IT 运维总控台。先判断用户问题属于 网络/主机/应用/安全 哪一类，"
        "然后调用相应子 Agent 获取答案并整合。若问题跨域，可分别调用多个子 Agent 并给出综合结论。"
        "若涉及动作（如创建工单），请明确说明，并在获得用户确认后再调用相关工具。"
    ),
    tools=[create_ticket, query_cmdb],
    sub_agents=[network_agent, host_agent, app_agent, sec_agent],
    model=planner_llm,
)

runner = Runner(agent=root_agent, app_name="itops_demo_app", user_id="demo_user")
```

## 运行您的 Agent

### 通过 VeADK Web

![image-2.jpeg](../assets/images/knowledge/kb-bp-1.jpeg)

### 通过终端运行

![image.jpeg](../assets/images/knowledge/kb-bp-2.jpeg)
