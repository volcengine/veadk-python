import os

from fastapi import FastAPI
from google.adk.agents import BaseAgent
from uvicorn.importer import import_from_string


def _to_a2a(agent: BaseAgent) -> FastAPI:
    # invoke google a2a utils -> res
    # res.runner = self
    ...


def _to_mcp(app: FastAPI): ...


def _custom_routes(app: FastAPI): ...


def agent_to_server(agent: BaseAgent) -> FastAPI:
    # agent: agent
    # runner:
    #   agent.short_term_memory -> Inmemory
    #   agent.long_term_memory -> None
    app = _to_a2a(agent)
    _to_mcp(app)
    _custom_routes(app)
    return app


entrypoint_agent_string = os.getenv("VEADK_ENTRYPOINT_AGENT", None)

entrypoint_agent = import_from_string(entrypoint_agent_string)

assert isinstance(entrypoint_agent, BaseAgent), (
    "The entrypoint agent must be an instance of BaseAgent."
)

app = agent_to_server(agent=entrypoint_agent)
