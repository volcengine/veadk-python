from agents.customer_support.agent import AGENT_DISPLAY_NAMES, root_agent
from veadk.integrations.agentkit import create_agentkit_app, run_agentkit_app

app = create_agentkit_app(
    root_agent,
    AGENT_DISPLAY_NAMES,
    enable_feishu=False,
)

if __name__ == "__main__":
    run_agentkit_app(app)
