import os
import subprocess
import sys
import textwrap


def test_runtime_import_needs_no_example_or_credentials():
    code = textwrap.dedent("""
        import anthropic
        def unexpected_client(*args, **kwargs):
            raise AssertionError("Library import constructed a remote client")
        anthropic.Anthropic.__init__ = unexpected_client
        anthropic.AsyncAnthropic.__init__ = unexpected_client
        from veadk.runtime.managed_agents.loop import ManagedAgentsLoop
        from veadk.runtime.managed_agents import worker
        assert "main" not in __import__("sys").modules
        assert worker.get_default_agent.cache_info().currsize == 0
    """)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            ("ANTHROPIC_", "SANDBOX_", "MODEL_AGENT_", "AGENTKIT_", "MA_")
        )
    }
    subprocess.run([sys.executable, "-c", code], check=True, env=env)
