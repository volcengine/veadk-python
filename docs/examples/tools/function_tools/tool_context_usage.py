import asyncio

from google.adk.tools.tool_context import ToolContext
from veadk import Agent, Runner


def message_checker(
    user_message: str,
    tool_context: ToolContext,
) -> str:
    """A user message checker tool that checks if the user message is valid.

    Args:
        user_message (str): The user message to check.

    Returns:
        str: The checked message.
    """

    print(f"user_message: {user_message}")
    print(f"current running agent name: {tool_context._invocation_context.agent.name}")
    print(f"app_name: {tool_context._invocation_context.app_name}")
    print(f"user_id: {tool_context._invocation_context.user_id}")
    print(f"session_id: {tool_context._invocation_context.session.id}")

    return f"Checked message: {user_message.upper()}"


agent = Agent(
    name="context_agent",
    tools=[message_checker],
    instruction="Use message_checker tool to check user message, and show the checked message",
)
runner = Runner(agent=agent)

response = asyncio.run(runner.run(messages="Hello world!"))
print(response)
