# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""An on-call triage agent that investigates an incident inside a sandbox.

Demonstrates the case `runtime="codex"` exists for: a question nobody can
pre-build a tool for. ADK tools pull raw logs, metrics and deploy records out
of an internal system and drop them into Codex's workspace; Codex then writes
throwaway shell and Python *in an OS sandbox* to grep, aggregate and correlate
them, refining one program into the next as it learns the shape of the data;
finally one ADK tool files a ticket.

The security posture is the demo, not boilerplate:

- ``sandbox="workspace_write"`` — Codex may write only its own workspace.
- ``network_access=False`` — the model can read production logs and physically
  cannot exfiltrate them. There is no socket to send them out of.
- ``approval_mode="deny_all"`` — escalations out of the sandbox are refused,
  not auto-approved.
- ``RunConfig(max_llm_calls=...)`` — a hard ceiling on a self-directed loop.

The only egress is ``file_incident_ticket``, an audited ADK tool that writes to
``outbox/`` — a directory beside the workspace that the sandbox cannot reach.

Run:
    cd examples/codex_ops_assistant && python main.py

Requires:
- ``pip install "veadk-python[codex]"`` (openai-codex plus the bundled Codex
  CLI binary). macOS or Linux: the sandbox is seatbelt / landlock+seccomp.
- Ark (or another OpenAI-compatible chat) credentials via
  ``MODEL_AGENT_API_KEY`` / ``MODEL_AGENT_API_BASE`` / ``MODEL_AGENT_NAME``.
"""

import asyncio
import os
import shutil
from pathlib import Path

from google.adk.agents import RunConfig
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types
from ops_tools import OPS_TOOLS, OUTBOX, WORKSPACE

from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runtime.codex import CodexRuntimeConfig

_HERE = Path(__file__).resolve().parent
_SKILL_DIR = _HERE / "skills" / "incident-triage"

SESSION_ID = "incident-2026-08-24"

MAX_LLM_CALLS = 40
"""Hard ceiling on backend calls per turn. The sandboxed loop is self-directed:
Codex issues one backend call per native tool round, and `max_tool_iterations`
bounds only the ADK tool round-trips, not those. This is the knob that stops a
model that starts repeating itself."""

INSTRUCTION = """\
You are an on-call SRE assistant for the `checkout-api` service. You
investigate incidents by analyzing raw telemetry yourself.

Your working directory is a sandbox. You may create, run and rewrite files
there — shell, awk, and Python are all available. You have NO network access,
and you cannot write anywhere outside this directory.

How to get data:
- The `fetch_*` tools do NOT return data. They download a file into your
  working directory and hand you back a receipt with its path and size. Read
  and analyze those files with your own commands.
- The files are large. Never cat a whole log file; aggregate it.
- Only the Python standard library is installed. There is no pandas, no numpy,
  no jq. Write plain Python, or use grep/awk/sort/uniq.

How to report:
- `file_incident_ticket` is the only channel out of this machine. Nothing you
  write to a file will be read by anyone. File exactly one ticket at the end,
  with a named root cause and the concrete numbers that support it.

Be rigorous. State what the data shows, and say so plainly if the evidence
does not support a conclusion.
"""

FIRST_QUESTION = """\
Checkout error rates and latency were elevated on 2026-08-24 (UTC) and we do
not know why. Investigate the full day and file a ticket with the root cause.
"""

FOLLOW_UP_QUESTION = """\
Now check whether the same pattern was already happening a week earlier, on
2026-08-17 (UTC). Fetch that day's logs, metrics and deploys, then run the
analysis scripts you already have in `analysis/` against them. Answer in one
short paragraph, and do not file a second ticket.
"""


def build_agent() -> Agent:
    """Build the triage agent, sandbox settings and all."""
    triage_runbook = SkillToolset(skills=[load_skill_from_dir(str(_SKILL_DIR))])

    return Agent(
        name="ops_triage_agent",
        description="Investigates checkout incidents from raw logs and metrics.",
        instruction=INSTRUCTION,
        runtime="codex",
        # `model_name`, never `model=`: the codex runtime resolves the model by
        # name and would silently ignore a model object.
        model_name=os.getenv("MODEL_AGENT_NAME", "deepseek-v4-pro-260425"),
        model_api_base=os.getenv(
            "MODEL_AGENT_API_BASE", "https://ark.cn-beijing.volces.com/api/v3"
        ),
        model_api_key=os.getenv("MODEL_AGENT_API_KEY"),
        tools=[*OPS_TOOLS, triage_runbook],
        codex_runtime_config=CodexRuntimeConfig(
            # Codex may write inside the workspace and nowhere else. Its own
            # scripts, its scratch files and the fetched data all live here.
            sandbox="workspace_write",
            # The whole point: the model reads production logs with no way to
            # send them anywhere. Only honoured by `workspace_write`.
            network_access=False,
            # Refuse every escalation Codex asks for. Never use "auto_review"
            # in production — it auto-approves, it does not review.
            approval_mode="deny_all",
            # Pin the workspace so the ADK tools and the sandbox agree on one
            # directory, and so you can inspect what the model wrote after the
            # run. Leave both unset in a server to get reaped, per-session
            # workspaces instead.
            workspace_root=str(WORKSPACE),
            reuse_workspace=True,
            # ADK tool round-trips allowed for the whole turn (not per model
            # request). Four fetches plus a ticket fits comfortably.
            max_tool_iterations=12,
            tool_timeout_seconds=60.0,
            reasoning_effort="medium",
        ),
    )


def _summarize(value: object, limit: int = 110) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def run_turn(runner: Runner, prompt: str, *, title: str) -> dict:
    """Run one turn, narrating what the sandbox does, and return a tally."""
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}\nUser: {_summarize(prompt, 300)}\n")
    tally = {
        "sandbox_commands": 0,
        "adk_tool_calls": 0,
        "failed_commands": 0,
        "stopped_by_budget": False,
    }
    answer = ""

    try:
        async for event in runner.run_async(
            user_id=runner.user_id,
            session_id=SESSION_ID,
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
            run_config=RunConfig(max_llm_calls=MAX_LLM_CALLS),
        ):
            for call in event.get_function_calls() or []:
                if call.name == "exec_command":
                    tally["sandbox_commands"] += 1
                    print(
                        f"  [sandbox {tally['sandbox_commands']:>2}] "
                        f"{_summarize(call.args.get('command'))}"
                    )
                elif call.name == "apply_patch":
                    print("  [sandbox   ] wrote a script into the workspace")
                else:
                    tally["adk_tool_calls"] += 1
                    print(f"  [adk tool ] {call.name}({_summarize(call.args, 90)})")

            for response in event.get_function_responses() or []:
                payload = (
                    response.response if isinstance(response.response, dict) else {}
                )
                if response.name == "exec_command":
                    if payload.get("exit_code") not in (0, None):
                        tally["failed_commands"] += 1
                        print(
                            f"             -> exit {payload.get('exit_code')} "
                            f"(the model has to fix this)"
                        )
                elif payload.get("status") == "error":
                    print(
                        f"             -> error: {_summarize(payload.get('message'))}"
                    )
                elif "path" in payload:
                    size = (
                        payload.get("lines")
                        or payload.get("rows")
                        or payload.get("records")
                    )
                    print(f"             -> {payload['path']} ({size} entries)")

            if event.partial or not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                if part.text and not part.thought:
                    answer = part.text
    except LlmCallsLimitExceededError:
        # Not a bug: this is `RunConfig(max_llm_calls=...)` doing its job. The
        # sandboxed loop is self-directed, and a model that starts repeating
        # itself would otherwise run until the wall clock stopped it.
        tally["stopped_by_budget"] = True
        print(
            f"\n  [budget] the turn hit the {MAX_LLM_CALLS}-call ceiling and was "
            "stopped. The workspace still holds everything it produced."
        )

    if answer:
        print(f"\nAgent: {answer.strip()}\n")
    print(
        f"  turn used {tally['sandbox_commands']} sandboxed commands "
        f"({tally['failed_commands']} of them failed and were retried) and "
        f"{tally['adk_tool_calls']} ADK tool calls"
    )
    return tally


async def main() -> None:
    # Start from a clean slate so the run is reproducible. `reuse_workspace`
    # means the directory would otherwise survive from the previous run.
    shutil.rmtree(WORKSPACE, ignore_errors=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    runner = Runner(agent=build_agent(), short_term_memory=ShortTermMemory())
    await runner.short_term_memory.create_session(
        app_name=runner.app_name, user_id=runner.user_id, session_id=SESSION_ID
    )

    await run_turn(runner, FIRST_QUESTION, title="Turn 1 — investigate the incident")
    # Same session, same workspace: the fetched data and the scripts the model
    # wrote in turn 1 are still on disk, so it does not start from zero.
    await run_turn(runner, FOLLOW_UP_QUESTION, title="Turn 2 — was it new?")

    print(f"\nWorkspace (what the sandbox wrote): {WORKSPACE}")
    for path in sorted(WORKSPACE.rglob("*")):
        if path.is_file():
            print(f"  {path.relative_to(WORKSPACE)} ({path.stat().st_size} bytes)")
    print(f"\nOutbox (what left the sandbox): {OUTBOX}")
    for path in sorted(OUTBOX.glob("*.json")):
        print(f"  {path.name}")


if __name__ == "__main__":
    asyncio.run(main())
