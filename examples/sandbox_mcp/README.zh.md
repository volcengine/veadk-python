# 一个 Agent，每个 session 一个沙箱

[English](README.md)

只创建一次 Agent 和 Runner。示例直接使用未修改的 `google.adk.runners.Runner`，
也兼容 `veadk.Runner`。`Agent(sandbox=manager)` 在首次执行时，为每个
`(app_name, user_id, session_id)` 绑定独立 AgentKit 沙箱。后续消息复用该沙箱，
暂停、恢复保留绑定。每轮使用当前端点创建普通 ADK `McpToolset`，不需要
SandboxMcpToolset，也不修改共享的 `agent.tools`。

## 运行

在 Linux/macOS 上，从当前 `veadk-python` 仓库根目录运行：

```bash
cp examples/sandbox_mcp/.env.example examples/sandbox_mcp/.env
# 在本地填入 ToolId、控制面凭据和模型配置。
uv run python examples/sandbox_mcp/main.py --session-id demo --list-tools
uv run python examples/sandbox_mcp/main.py --session-id demo "Run Python print(1 + 1)." --follow-up "Run Python print(2 + 2)."
uv run python examples/sandbox_mcp/main.py --session-id demo --action status
uv run python examples/sandbox_mcp/main.py --session-id demo --action pause
uv run python examples/sandbox_mcp/main.py --session-id demo --action resume
uv run python examples/sandbox_mcp/main.py --session-id demo --action delete
```

`--follow-up` 可以重复使用：同一进程中的这些消息复用完全相同的 Agent/Runner。
重启 CLI 时重新打开持久化聊天和沙箱绑定。`SANDBOX_TOOL_ID` 回退到
`AGENTKIT_TOOL_ID`；`MODEL_AGENT_API_KEY` 回退到 `ARK_API_KEY`，其他模型配置
沿用 VeADK。`ensure` 和 `--list-tools` 只创建/恢复，不调用模型。需要已有的
支持 MCP 的 Tool；云端暂停、恢复需要后端快照支持。

## 嵌入应用

```python
import asyncio
from contextlib import aclosing
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types
from veadk import Agent
from veadk.sandbox import SandboxManager, SessionKey


async def main():
    manager = SandboxManager(tool_id="your-tool-id", state_dir=".state/bindings")
    agent = Agent(name="assistant", tools=[], sandbox=manager)
    async with DatabaseSessionService(
        db_url="sqlite+aiosqlite:///.state/chat.db"
    ) as service:
        runner = Runner(
            agent=agent,
            app_name="my_app",
            session_service=service,
            auto_create_session=True,
        )

        async def send(session_id, message):
            async with aclosing(
                runner.run_async(
                    user_id="u1",
                    session_id=session_id,
                    new_message=types.Content(
                        role="user", parts=[types.Part(text=message)]
                    ),
                )
            ) as events:
                async for event in events:
                    if event.is_final_response():
                        print(event.content)

        try:
            await asyncio.gather(
                send("s1", "Run Python print(1 + 1)."),
                send("s2", "Run Python print(2 + 2)."),
            )
            await send("s1", "Continue our task.")
            await manager.pause(SessionKey("my_app", "u1", "s1"))
        finally:
            await runner.close()  # 活跃调用结束后，在应用退出时关闭。


asyncio.run(main())
```

Agent 在模型/工具循环和 MCP 清理期间持有沙箱锁。不同 session 可以并发。
同一聊天内的消息需顺序提交：Agent 层的锁不能串行化 Runner 更早的历史写入
或更晚的压缩。每次 LlmRequest 都注册相应 MCP 工具及执行分发表。保留已有 Agent
回调字段；在 Agent 执行前通过回调提前返回时，不分配沙箱。生命周期函数不进入
模型上下文。提前停止消费 run_async 流时应使用 aclose 或 contextlib.aclosing，
以触发 Agent 清理。

`.state/bindings/` 保存物理 SessionId；`.state/chats.db` 保存聊天历史。
`--state-dir` 可指定私有本地目录，不同云账号/控制面使用不同目录。用户/会话身份
应来自可信认证信息，不能由模型决定。签名端点只临时保留，不要输出到日志。
删除托管 Session 会永久清理沙箱数据；保留本地聊天和已删除绑定。删除后请使用
新 session ID。Runner.close 不会暂停或删除沙箱。

## 第一版范围与验证

Agent 接入支持使用 ADK runtime 的独立 VeADK Agent，tools 为空、没有父/子 Agent
和 code executor。混用本地工具、其他 runtime 和 run_live 会显式拒绝。自定义
调用仍可使用底层 `SandboxManager.acquire`。POSIX 锁只协调同一本地文件系统，
不支持多机。不自动空闲暂停、续期 TTL、检测后台任务或替换丢失/过期沙箱。
暂停/删除前应确认后台任务状态。创建结果未知时通过已保存的 UserSessionId 找回，
不要删除待确认记录来强制再次创建。SDK 网络超时与轮询期限独立；本地取消不等于
取消远端任务。

```bash
uv run --extra dev pytest tests/sandbox tests/runner -q
```

本地测试使用真实 MCP HTTP、VeADK/SQLite，模型和控制面为离线模拟。
当前云端验证结果和未验证的云端暂停/恢复边界见
[契约](../../specs/sandbox-lifecycle/README.zh.md)及
[验证记录](../../prd-spec/features/sandbox-lifecycle/2026-10-23-agent-owned-mcp-sandbox.zh.md)。
manager 是从 Agent 序列化中排除的 Python 活对象；Studio UI 或生成配置中的
配置支持不在此示例范围内。
