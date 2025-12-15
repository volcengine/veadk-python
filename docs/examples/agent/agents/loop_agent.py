import asyncio

from google.adk.tools.tool_context import ToolContext
from veadk import Agent, Runner
from veadk.agents.loop_agent import LoopAgent


def exit_loop(tool_context: ToolContext):
    print(f"  [Tool Call] exit_loop triggered by {tool_context.agent_name}")
    tool_context.actions.escalate = True
    return {}


planner_agent = Agent(
    name="planner_agent",
    description="Decomposes a complex task into smaller actionable steps.",
    instruction=(
        "Given the user's goal and current progress, decide the NEXT step to take. You don't need to execute the step, just describe it clearly. "
        "If all steps are done, respond with 'TASK COMPLETE'."
    ),
)

executor_agent = Agent(
    name="executor_agent",
    description="Executes a given step and returns the result.",
    instruction="Execute the provided step and describe what was done or what result was obtained. If you received 'TASK COMPLETE', you must call the 'exit_loop' function. Do not output any text.",
    tools=[exit_loop],
)

root_agent = LoopAgent(
    sub_agents=[planner_agent, executor_agent],
    max_iterations=3,  # Limit the number of loops to prevent infinite loops
)

if __name__ == "__main__":
    runner = Runner(root_agent)
    response = asyncio.run(runner.run("用中文帮我写一首三行的小诗，主题是秋天"))
    print(response)
