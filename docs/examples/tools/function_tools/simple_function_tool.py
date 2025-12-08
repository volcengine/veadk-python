import asyncio
from typing import Any, Dict

from google.adk.tools.tool_context import ToolContext
from veadk import Agent, Runner


def calculator(
    a: float, b: float, operation: str, tool_context: ToolContext
) -> Dict[str, Any]:
    """A simple calculator tool that performs basic arithmetic operations.

    Args:
        a (float): The first operand.
        b (float): The second operand.
        operation (str): The arithmetic operation to perform.
            Supported operations are "add", "subtract", "multiply", and "divide".

    Returns:
        Dict[str, Any]: A dictionary containing the result of the operation, the operation performed,
        and the status of the operation ("success" or "error").
    """
    if operation == "add":
        return {"result": a + b, "operation": "+", "status": "success"}
    if operation == "subtract":
        return {"result": a - b, "operation": "-", "status": "success"}
    if operation == "multiply":
        return {"result": a * b, "operation": "*", "status": "success"}
    if operation == "divide":
        return {
            "result": a / b if b != 0 else "Error, divisor cannot be zero",
            "operation": "/",
            "status": "success" if b != 0 else "error",
        }
    return {"status": "error", "message": "Unsupported operation"}


agent = Agent(
    name="computing_agent",
    instruction="Please use the `calculator` tool to perform user-required calculations",
    tools=[calculator],
)
runner = Runner(agent=agent)

response = asyncio.run(runner.run(messages="Add 2 and 3"))
print(response)
