# 不依赖 VeADK 的 CUA 接入

最小链路：**方舟模型 → 标准 MCP Client → AgentKit CUA 沙箱**。
不导入 VeADK 或 AgentKit SDK，不重复实现实例调度，不包含耗时/token 统计。[English](README.md)

```text
main.py             模型循环、MCP 调用、截图回传、绑定保存
requirements.txt    独立依赖
.env.example        配置参考
```

## 准备和运行

在 AgentKit 创建已授权、支持 CUA 的沙箱工具。桌面任务在**沙箱模板侧**配置
`ENABLE_COMPUTER=true`。执行身份需有目标工具的 `GetTool`、`ListSessions`、
`GetSession`、`CreateSession` 权限；托管时还需关联 Runtime。模型与 AgentKit 使用不同凭证。

安装 `uv`（含 `uvx`），创建独立 Python 3.12 环境：

```bash
cd examples/cua_without_veadk
uv venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt

export AGENTKIT_TOOL_ID='t-your-authorized-tool'
export ARK_MODEL='your-vision-model-or-endpoint'
export ARK_API_KEY='<模型 Key>'
export VOLCENGINE_ACCESS_KEY='<访问 AK>'
export VOLCENGINE_SECRET_KEY='<访问 SK>'
export CUA_MCP_WHEEL_URL='https://browser-use-test.tos-cn-beijing.volces.com/agentkit-cua-mcp/1.0.0/agentkit_cua_mcp-1.0.0-py3-none-any.whl'

.venv/bin/python main.py \
  --session-id customer_task_001 \
  --state-file .state/customer_task_001.json \
  --prompt '请截取一次桌面，并描述你看到的内容。'
```

该命令会调用模型，可能创建计费沙箱。模型需支持图像和工具调用。临时 AgentKit 凭证
另需 `VOLCENGINE_SESSION_TOKEN`；AK/SK 均缺省时 MCP 读取 Runtime IAM 文件。
程序读取已导出的变量，**不会自动加载 `.env`**；TTL 和创建策略等可选项见 `.env.example`。
不需要安装 VeADK 或访问私有仓库。下载后用相邻 `.whl.sha256` 校验，变量也接受已校验的本地 wheel 路径。

浏览器任务可将 prompt 改为：`打开浏览器，访问 https://example.com，截图并告诉我页面标题。`
工具由模型选择，不是写死点击顺序。

STG 使用对应 ToolId 和权限，并**同时**设置：

```bash
export AGENTKIT_TOOL_ENV=stg
export CUA_MCP_WHEEL_URL='https://browser-use-test.tos-cn-beijing.volces.com/agentkit-cua-mcp/1.0.0/revisions/dd3574c1f176/agentkit_cua_mcp-1.0.0-py3-none-any.whl'
```

环境默认 `prod`，地域默认 `cn-beijing`。原正式环境 wheel 不支持 STG 开关；Client 会显式向 MCP 传递此配置。

## 请求链路

1. 通过 `uvx --from <wheel> agentkit-cua-mcp --transport stdio` 启动 MCP。
2. 调用 `tools/list`，在 `_meta["veadk/cua"]` 中放可信应用会话。
   这是 MCP 包约定的命名空间，**不需要 VeADK**。
3. 把 schema 交给模型，校验其参数后带相同元数据执行单个工具。MCP 内部按需查询、创建或复用实例。
   `ensure_sandbox` 可选，发现工具阶段及每次点击前不必显式调用。
4. 保存响应中的物理实例绑定，动作失败时也保存；向模型回传文字和**图片内容**，不回传路由元数据。
5. 持续执行直到模型回答；退出时关闭 MCP，沙箱过期和回收由 AgentKit 管理。

同一沙箱使用相同的 `--session-id` 和状态文件。该 ID 是业务侧逻辑 `UserSessionId`，不是物理 `SessionId`。
每次运行重新开始模型对话，只持久化实例绑定，不持久化聊天历史。一个会话只由一个活动进程控制，
不同账号/身份/环境使用独立状态文件。到期或删除后，明确使用新会话键和新状态文件开始新任务。

发现工具不创建实例。CUA 关闭模板仅暴露 ensure，显式执行 ensure 仍可能创建实例。
模型一次返回多个调用时全部拒绝执行，已知动作序列可以使用一个 `cua_actions_batch`。
失败、部分成功或结果不确定时以非零退出码停止，不自动重试变更操作。终端输出工具名、状态和回答，不输出凭证或签名地址。

## 与 AgentKit 示例的关系

参考 [04-agentkit-tools](https://github.com/bytedance/agentkit-samples/tree/main/python/01-tutorials/04-agentkit-tools)，
核对版本为 `9fc58da287b9b2d5910047ca8519efea597189cb`；沿用工具发现、schema 校验和会话记录方式。
其中 `sandbox_lifecycle_mcp` 使用 Streamable HTTP 生命周期网关；本例使用独立的 CUA stdio 包，工具名与元数据不同。
本例不实现快照恢复、暂停或续期。

其他入口先创建实例时，需使用相同授权 ToolId、地域/环境及 UserSessionId，MCP 才能查询复用。
`sandbox_lifecycle_http/03_invoke_session.py` 使用物理 `SessionId` 和 `OperationType=RunCode` 执行代码，
不是 CUA 动作传输接口。不能猜测缺失的逻辑键或随意绑定实例。本例没有注册 `run_code` / `InvokeTool`。

## 验证范围

本例没有 HTTP Server/Dockerfile；设置可信会话路由后，可将函数嵌入客户 Agent 服务。

2026-11-16，本示例完成了一次经授权的正式环境冒烟：真实方舟模型 → 公开基线 wheel →
按需创建一个沙箱 → PNG 截图 → 模型描述。保存的绑定与平台实例一致，测试实例已删除。
该结果仅覆盖一次截图场景，不代表 STG、所有工具、浏览器任务或托管 Runtime 验收。
