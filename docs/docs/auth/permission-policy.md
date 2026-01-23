# 权限策略

Agent 权限策略基于 Cedar 声明式授权语言，提供了一套覆盖 User → Agent → Tool 全链路的权限管理方案。通过本指南，你将了解如何在智能体代码中启用权限校验，并通过控制台配置权限策略，确保智能体仅被授权用户访问。

## 前置准备
参考[使用文档](https://www.volcengine.com/docs/86848/2123355?lang=zh)，登录火山引擎智能体身份和权限管理平台，按以下步骤创建策略空间与权限策略：
- 进入「权限管控 > 权限策略」，创建策略空间（填写空间名称、描述，选择所属项目和标签）；
- 在目标策略空间内新建权限策略，可通过「可视化编辑」或「Cedar 语句编辑」定义规则（例如：允许指定用户调用某智能体）；
- 使用「模拟权限校验」功能验证策略是否符合预期。

## 代码实现

在调用智能体之前，需在 [AgentKit Runtime](https://console.volcengine.com/agentkit/region:agentkit+cn-beijing/runtime) 控制台配置 `RUNTIME_IDENTITY_NAMESPACE` 环境变量指定策略空间（默认为 default），以确保权限校验能匹配到对应的策略规则：
```bash
# 设置策略空间名称（替换为你实际创建的策略空间名称）
RUNTIME_IDENTITY_NAMESPACE="你的策略空间名称"
```

在初始化 Agent 时开启授权功能（enable_authz=True），即可触发权限校验流程。以下是部署到 [AgentKit Runtime](https://console.volcengine.com/agentkit/region:agentkit+cn-beijing/runtime) 的代码示例：

```python title="agent.py"
import asyncio

from veadk import Agent, Runner

# 待校验权限的用户ID
user_id = "9d154b10-285f-404c-ba67-0bf648ff9ce0"

# 初始化Agent并开启权限校验
agent = Agent(enable_authz=True)

runner = Runner(agent=agent)

# 调用智能体并传入用户ID（权限校验的核心依据）
response = asyncio.run(runner.run(messages="你好", user_id=user_id))

print(response)
```

运行结果：
- 授权通过：若用户在策略空间中拥有调用该智能体的权限，代码会正常执行并返回智能体的响应结果；
- 授权失败：若用户未被授权访问该智能体，会抛出权限异常，错误信息示例：`Agent <agent role> is not authorized to run by user 9d154b10-285f-404c-ba67-0bf648ff9ce0.`
