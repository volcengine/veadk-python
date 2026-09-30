# Codex session lifecycle

One `runtime="codex"` session, end to end: an MCP tool, a Python function
tool and a skill; sandboxed file writes; a streamed answer; `runner.steer()`
into a running turn; cancelling a running turn; and resuming the session's
Codex thread on the next request.

```bash
pip install "veadk-python[codex]"
export MODEL_AGENT_API_KEY=... MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3 MODEL_AGENT_NAME=...
python examples/codex_session_lifecycle/main.py
```

- Ark is called directly and the agent's tools reach Codex over a local MCP
  server, so Codex drives the tool loop (`model_transport="auto"`).
- Each session keeps one Codex thread (`thread_mode="resume"`), saved with the
  session in SQLite here, so a later request — or a second run of the script —
  resumes it instead of replaying the transcript.
- Reuses the skill and MCP server of `examples/codex_with_skill_and_mcp`.
