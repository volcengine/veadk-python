"""VeADK Web: one coordinator and one remote sandbox sub-agent."""

import os

from veadk import Agent
from veadk.agents.agentkit_remote_sandbox_agent import AgentkitRemoteSandboxAgent

sandbox = AgentkitRemoteSandboxAgent(
    name="sandbox",
    description="执行需要远端技能、Python、命令或文件操作的任务，并直接报告执行过程和结果。",
    tool_id=os.getenv("AGENTKIT_TOOL_ID"),
    tool_type=os.getenv("AGENTKIT_TOOL_TYPE") or None,
    request_timeout=900,
    expiry_buffer=90,
)
root_agent = Agent(
    name="remote_sandbox_demo",
    description="A coordinator with one remote sandbox agent.",
    instruction=(
        "理解用户的请求。需要运行代码、操作文件或使用沙箱技能时，"
        "使用 transfer_to_agent 将任务交给 sandbox。"
        "不要自己运行命令，不要编造远端执行结果。"
        "sandbox 会直接展示工具过程并回答用户，无需重复总结。"
    ),
    sub_agents=[sandbox],
)
