from veadk import Agent

INSTRUCTION_AGENT = (
    """Route order questions to the order assistant and answer general questions."""
)

INSTRUCTION_AGENT_SUB_1 = """Help the user check and understand an order."""

agent_sub_1 = Agent(
    name="order_assistant",
    description="Handles order questions.",
    instruction=INSTRUCTION_AGENT_SUB_1,
)

agent = Agent(
    name="customer_support",
    description="A generated customer-support multi-agent example.",
    instruction=INSTRUCTION_AGENT,
    sub_agents=[agent_sub_1],
)

AGENT_DISPLAY_NAMES = {
    "customer_support": "customer_support",
    "order_assistant": "order_assistant",
}

# ADK requires the top-level agent to be exported as root_agent.
root_agent = agent
