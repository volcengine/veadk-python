# Codex 会话全流程

一个 `runtime="codex"` 会话的完整流程：MCP 工具、Python 函数工具与 skill；沙箱内写文件；流式输出；用 `runner.steer()` 向进行中的回合追加指令；取消进行中的回合；下一次请求恢复该会话的 Codex thread。

```bash
pip install "veadk-python[codex]"
export MODEL_AGENT_API_KEY=... MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3 MODEL_AGENT_NAME=...
python examples/codex_session_lifecycle/main.py
```

- Codex 直接调用方舟，Agent 的工具经本地 MCP server 交给 Codex，由 Codex 驱动工具循环（`model_transport="auto"`）。
- 每个会话保有一个 Codex thread（`thread_mode="resume"`），此处随会话存在 SQLite 中；之后的请求或再次运行脚本都会恢复该 thread，而不是回放对话记录。
- 复用 `examples/codex_with_skill_and_mcp` 的 skill 与 MCP server。
