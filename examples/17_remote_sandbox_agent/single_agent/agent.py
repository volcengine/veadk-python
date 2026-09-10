"""A remote sandbox agent used directly as the application root."""

import os

from veadk import AgentkitRemoteSandboxAgent

root_agent = AgentkitRemoteSandboxAgent(
    name="remote_sandbox_demo",
    description="执行远端技能、Python、命令或文件操作，并直接报告执行过程和结果。",
    tool_id=os.getenv("AGENTKIT_TOOL_ID"),
    tool_type=os.getenv("AGENTKIT_TOOL_TYPE") or None,
    request_timeout=900,
    expiry_buffer=90,
)
