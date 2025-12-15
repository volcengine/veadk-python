
# 使用 Trusted MCP 进行出站认证

Trusted MCP 通过在标准 MCP 协议基础上增加“组件身份证明与验证”能力，并提供端到端加密通信，构建全链路可信的 Agent 运行环境。结合机密计算（如 Jeddak AICC）与可信推理服务，可有效防止服务身份不可信、数据被篡改、流量劫持、隐私泄露等风险。

VeADK 原生支持连接 TrustedMCP 服务，您可以在工具调用链中开启可信通道，确保出站通信安全。

## 可信 Agent

依托机密计算技术（如Jeddak AICC），可以将 Agent 以及大模型服务（如机密豆包）运行在可信环境中，并通过 TrustedMCP 以及端到端加密通信，构建全链路可信的 Agent。其中，TrustedMCP 是火山引擎推出的可信 MCP，在标准 MCP 协议的基础上扩展核心组件之间的身份证明及验证能力，提供组件之间端到端的通信安全保障，可以解决 MCP 应用中服务身份不可信、数据被篡改、流量劫持、数据隐私泄露等安全威胁。

使用 VeADK 可以构建可信 Agent，并通过 `tools` 机制调用 TrustedMCP 服务。

## 创建连接与前置条件

1. 准备可用的 TrustedMCP 服务地址，例如 `wss://your-trusted-mcp.example.com`。
2. 准备 AICC 配置文件 `./aicc_config.json`（用于机密环境与远端证明），参考官方示例配置。
3. 在连接参数中开启 `x-trusted-mcp: true` 以启用可信模式。

## 使用方式

```python title="agent.py"
import asyncio

from veadk import Agent
from veadk.utils.mcp_utils import get_mcp_params
from veadk.tools.mcp_tool.trusted_mcp_toolset import TrustedMcpToolset

mcp_url = "<TrustedMCP server address>"

# 1. 开启 TrustedMCP 功能以及相关配置
connection_params = get_mcp_params(mcp_url)
connection_params.headers = {"x-trusted-mcp": "true"}

# 2. 初始化 TrustedMcpToolset 工具集
toolset = TrustedMcpToolset(connection_params=connection_params)

# 3. 初始化 Agent
agent = Agent(tools=[toolset])

# 4. 运行 Agent
response = asyncio.run(agent.run("北京天气怎么样？"))

print(response)  # 北京天气晴朗，气温25°C。
```

## 选项

TrustedMcpToolset 支持以下关键配置：

- `x-trusted-mcp`（Header）
    - 类型：字符串
    - 默认：`true`
    - 说明：是否开启 TrustedMCP 功能并启用可信通道。

- `aicc_config`（路径）
    - 类型：字符串
    - 默认：`./aicc_config.json`
    - 说明：AICC 配置文件路径。用于机密计算环境的证明与策略配置。

> 配置文件示例与说明请参考：TrustedMCP 配置文件（https://github.com/volcengine/AICC-Trusted-MCP/blob/main/README.md）。

## 相关资源

- [Agent Identity 产品介绍](https://www.volcengine.com/docs/86848/2080920?lang=zh)
- [API Key 认证](https://volcengine.github.io/veadk-python/auth/api-key-outbound/)
- [OAuth2 USER_FEDERATION 认证](https://volcengine.github.io/veadk-python/auth/oauth2-user-federation-outbound/)
- [Trusted MCP 认证](https://volcengine.github.io/veadk-python/auth/trusted-mcp-outbound/)
- [TrustedMCP 配置文件与说明](https://github.com/volcengine/AICC-Trusted-MCP/blob/main/README.md)
