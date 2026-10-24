"""Optional remote-backed demo Agent for VeADK discovery."""

from pathlib import Path

from dotenv import load_dotenv


def _demo_agent():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    from veadk.runtime.managed_agents.sandbox import get_default_agent

    return get_default_agent()


agent = root_agent = _demo_agent()
