import json

import requests
from a2a.types import AgentCard
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

AGENT_CARD_WELL_KNOWN_PATH = "/.well-known/agent-card.json"


class RemoteVeAgent(RemoteA2aAgent):
    def __init__(self, name: str, url: str):
        agent_card_dict = requests.get(url + AGENT_CARD_WELL_KNOWN_PATH).json()
        agent_card_dict["url"] = url

        agent_card_json_str = json.dumps(agent_card_dict, ensure_ascii=False, indent=2)

        agent_card_object = AgentCard.model_validate_json(str(agent_card_json_str))

        super().__init__(name=name, agent_card=agent_card_object)
