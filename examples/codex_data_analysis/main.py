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

"""A `runtime="codex"` analyst that writes, runs and *debugs* its own script.

This is the task the codex runtime exists for. The agent is handed a 2 400-row
warehouse extract with realistic defects buried in it — blank revenue cells,
prices carrying thousands separators, a second date format, three spellings of
one region — none of them in the first 200 rows and none of them mentioned in
the prompt. The file is far too big to eyeball, so the agent has to write an
analysis script, run it, read the traceback, fix it, and run it again until the
numbers come out. On ``runtime="adk"`` the model can only *emit* a script and
hope; here it executes one inside an OS sandbox and sees what happened.

What the example demonstrates:

- **Path-passing, not payload-passing.** ``fetch_sales_extract`` lands the CSV
  in Codex's workspace and returns ``{"path": ..., "rows": 2400}``. ADK tool
  results are executed by the runtime's shim and come back to the model as text
  in its context, so the workspace is the data plane and tool results are the
  control plane. See ``analytics_tools.py``.
- **Iteration on real errors.** Watch the ``exec_command`` lines below: the
  first ``python3`` run fails, and the agent recovers from the traceback.
- **The sandbox as the security boundary.** ``sandbox="workspace_write"`` +
  ``network_access=False`` + ``approval_mode="deny_all"`` means the model may
  compute anything it likes over the data but has no way to send it anywhere.
  The audited ``publish_report`` tool is the only outbound path, and ``outbox/``
  sits outside the workspace precisely so the sandbox cannot write to it.
- **A workspace that survives the turn.** Turn 2 asks for a different chart;
  the extract, the script and the report are all still there, so the agent
  edits instead of starting over.
- **A skill for the house format.** ``skills/sales-report/SKILL.md`` is driven
  by Codex's native skill system, so the report layout stays out of the prompt.

Run:
    python examples/codex_data_analysis/main.py

Requires:
- ``pip install "veadk-python[codex]"`` (openai-codex plus the bundled Codex
  CLI binary). macOS or Linux — the OS sandbox is seatbelt / landlock+seccomp.
- Ark (or another OpenAI-compatible chat) credentials via ``MODEL_AGENT_API_KEY``
  / ``MODEL_AGENT_API_BASE`` / ``MODEL_AGENT_NAME`` (see ``.env.example``).
"""

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from google.adk.agents import RunConfig
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

from analytics_tools import OUTBOX, WORKSPACE, fetch_sales_extract, publish_report
from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runtime.codex import CodexRuntimeConfig

_HERE = Path(__file__).resolve().parent
_SKILL_DIR = _HERE / "skills" / "sales-report"

_SESSION_ID = "q3-review"

INSTRUCTION = """\
You are a revenue analyst. You work inside a sandboxed workspace: you may
create and run files there, but you have no network access and only the Python
standard library — pandas, numpy and matplotlib are not installed and cannot be
installed.

Act, do not narrate. Never end a message with a plan you have not carried out:
a reply that contains no tool call ends your turn and the work stops there.
Nobody can answer you mid-turn, so never ask the user a question — decide and
proceed. Create and edit files with `exec_command` and a heredoc
(`cat > analyze.py <<'PY' ... PY`), not with `apply_patch`.

How you work:

1. Call `fetch_sales_extract` to land the quarter's extract in your workspace.
   It returns a path and a row count, never the rows themselves — read the file
   with your own code.
2. Write an analysis script and *run* it with `python3`. Never report a number
   you have not computed by executing code. If a run fails, read the error, fix
   the script, and run it again — repeat until it succeeds.
3. Write the report to `report.md` and the chart to `chart.svg`, following the
   sales-report skill.
4. Call `publish_report` with both paths — it is the only way a file leaves the
   sandbox. Your turn is finished only once it returns status "ok".

Reply only then, with a short plain-language summary of what the numbers say,
plus anything a human reading the report should know about how you got there.
"""

TURNS = (
    "Produce the 2025Q3 sales review and publish it.",
    "Reviewers want the trend chart replaced: make chart.svg a horizontal bar "
    "chart of revenue by region, highest first. Leave the rest of the report "
    "as it is and publish the updated version.",
)


def build_agent() -> Agent:
    """Build the analyst agent, sandbox settings included."""
    # The house report format, loaded the ADK-native way. The codex runtime
    # materializes it into Codex's own skill directory.
    report_skill = SkillToolset(skills=[load_skill_from_dir(str(_SKILL_DIR))])

    return Agent(
        name="codex_data_analyst",
        description="Turns a raw sales extract into a published report.",
        instruction=INSTRUCTION,
        runtime="codex",
        model_name=os.getenv("MODEL_AGENT_NAME", "deepseek-v4-flash-260425"),
        model_api_base=os.getenv(
            "MODEL_AGENT_API_BASE", "https://ark.cn-beijing.volces.com/api/v3"
        ),
        model_api_key=os.getenv("MODEL_AGENT_API_KEY", ""),
        tools=[report_skill, fetch_sales_extract, publish_report],
        codex_runtime_config=CodexRuntimeConfig(
            # The model may write and run code, but only inside the workspace.
            sandbox="workspace_write",
            # Honoured by workspace_write: no sockets from inside the sandbox.
            # With this off, the two ADK tools are the only way in or out.
            network_access=False,
            # Refuse every escalation Codex asks for. Never use "auto_review"
            # here: it is full auto-approval, not a review step.
            approval_mode="deny_all",
            # Pinned so the ADK tools (which run in *this* process) know where
            # the workspace is, and so you can read it afterwards. In a
            # multi-tenant service, leave both unset — see the README.
            workspace_root=str(WORKSPACE),
            reuse_workspace=True,
            # ADK tool round-trips allowed for the whole turn. This agent needs
            # two (fetch + publish); the rest of the budget is for retries.
            max_tool_iterations=8,
            tool_timeout_seconds=120.0,
        ),
    )


def _reset_run_dirs() -> None:
    """Start from an empty workspace and outbox so the demo is reproducible."""
    for directory in (WORKSPACE, OUTBOX):
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True, exist_ok=True)


def _truncate(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _print_event(event: Any) -> None:
    """Render one ADK event: sandboxed commands, ADK tool calls, final text.

    ``exec_command`` is Codex running something inside the sandbox — the
    runtime surfaces it as an ordinary ADK function-call event, which is what
    makes the write / run / fix / re-run loop visible from here.
    """
    if event.partial:
        return

    for call in event.get_function_calls() or []:
        args = call.args or {}
        if call.name == "exec_command":
            print(f"  $ {_truncate(args.get('command', ''))}")
        else:
            print(f"  → {call.name}({_truncate(args, 100)})")

    for response in event.get_function_responses() or []:
        payload = response.response
        if response.name == "exec_command":
            exit_code = (payload or {}).get("exit_code")
            if exit_code:  # non-zero, and not None (still running)
                tail = [
                    line
                    for line in str((payload or {}).get("output", "")).splitlines()
                    if line.strip()
                ][-2:]
                print(f"    exit={exit_code}")
                for line in tail:
                    print(f"    | {_truncate(line)}")
        else:
            print(f"  ← {response.name}: {_truncate(payload, 200)}")

    for part in event.content.parts if event.content and event.content.parts else []:
        if part.text and not part.thought:
            print(f"\nAgent: {part.text.strip()}\n")


def _print_tree(label: str, root: Path) -> None:
    print(f"\n{label} ({root}):")
    entries = sorted(p for p in root.rglob("*") if p.is_file())
    if not entries:
        print("  (empty)")
    for path in entries:
        print(f"  {path.relative_to(root)}  {path.stat().st_size} B")


async def main() -> None:
    _reset_run_dirs()

    runner = Runner(agent=build_agent(), short_term_memory=ShortTermMemory())
    await runner.short_term_memory.create_session(
        app_name=runner.app_name, user_id=runner.user_id, session_id=_SESSION_ID
    )

    # A hard cost ceiling for the turn. The shim charges this budget before
    # every backend call, so unlike other external runtimes codex enforces it
    # exactly — raise it if a turn ends with LlmCallsLimitExceededError.
    run_config = RunConfig(max_llm_calls=60)

    for number, prompt in enumerate(TURNS, start=1):
        print(f"\n{'=' * 72}\nTurn {number} — User: {prompt}\n{'=' * 72}")
        async for event in runner.run_async(
            user_id=runner.user_id,
            session_id=_SESSION_ID,
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
            run_config=run_config,
        ):
            _print_event(event)

    # The workspace is the agent's scratch space: its script and its drafts are
    # still there. The outbox holds only what publish_report let through.
    _print_tree("Workspace", WORKSPACE)
    _print_tree("Outbox", OUTBOX)


if __name__ == "__main__":
    asyncio.run(main())
