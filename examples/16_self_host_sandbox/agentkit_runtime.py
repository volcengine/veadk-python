"""Run the packaged AgentKit health listener."""

import runpy

if __name__ == "__main__":
    runpy.run_module("veadk.runtime.managed_agents.health", run_name="__main__")
