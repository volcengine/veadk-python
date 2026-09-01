# codex_data_analysis

An agent that turns a raw sales extract into a published report **by writing an
analysis script, running it, reading the traceback, fixing it, and running it
again** — inside an OS sandbox with the network switched off.

> 中文版见 [README.zh.md](./README.zh.md)

This is the flagship `runtime="codex"` example. If you want the wiring reference
for skills and MCP tools under this runtime, see
[`codex_with_skill_and_mcp/`](../codex_with_skill_and_mcp/) instead.

```
codex_data_analysis/
├── main.py                 # the agent, its sandbox settings, and a 2-turn run
├── analytics_tools.py      # the two ADK tools that bracket the sandbox
├── data/
│   └── sales_2025q3.csv    # the "internal system": 2 400 raw orders, defects included
├── skills/
│   └── sales-report/
│       └── SKILL.md        # the house format for the report
├── .codex_workspace/       # created at run time — Codex's cwd (read it afterwards!)
└── outbox/                 # created at run time — what publish_report let out
```

## The task

1. `fetch_sales_extract` (ADK tool) exports one quarter of orders from the
   internal warehouse **into Codex's workspace** and returns a receipt:
   `{"path": "data/sales_2025q3.csv", "rows": 2400, ...}`.
2. **Codex** writes an analysis script, runs it, hits a real `ValueError`, fixes
   it, re-runs, and produces `report.md` + a hand-written `chart.svg`.
3. `publish_report` (ADK tool) validates the paths and copies both files into
   `outbox/` — the only way anything leaves the sandbox.

Then a second turn — *"replace the trend chart with revenue by region"* —
reuses the same workspace: the extract, the script and the report are still
there, so the agent edits rather than starting over.

## Why this task suits codex, and not adk

The honest comparison is not "can the model run code" — `runtime="adk"` has
code executors too. It is **what shape of loop you get, and what it costs to
run it safely.**

**What this runtime gives you here:**

- **A working directory and a shell, not an expression evaluator.** Debugging is
  a loop of `ls`, `cat`, write file, `python3 x.py`, read traceback, patch,
  re-run. ADK's code-executor path evaluates a *block the model emits* and hands
  back its output; it is not a place the model can accumulate a script, a data
  file, a chart and a report next to each other and iterate over them.
- **An OS sandbox with no infrastructure to provision.** macOS seatbelt / Linux
  landlock+seccomp, established by the Codex CLI itself. ADK ships
  `UnsafeLocalCodeExecutor` — which executes in *your* process, with no
  isolation and not even stateful — and `BuiltInCodeExecutor`, which delegates
  to the model provider's server-side tool and is Gemini-only, so it is not
  available on an Ark chat backend at all. Anything safer, you provision
  yourself. Here `sandbox="workspace_write"` + `network_access=False` is four
  lines of config.
- **Files that survive the turn.** The workspace is session-scoped, so turn 2
  amends turn 1's artifacts. A code-executor block starts from nothing each time
  unless you rebuild the state yourself.
- **A debugging harness you don't have to prompt into existence.** Reading a
  traceback and patching the file is what Codex's own loop already does.

**What you pay for it:**

- A Codex subprocess per turn, and one backend request per native tool round,
  each re-serializing the turn. This example takes minutes and tens of model
  calls where a one-shot answer takes one.
- A large part of the `Agent` surface is refused outright (see
  [Constraints](#constraints)) and per-LLM-call callbacks never run.
- Non-determinism in the number of rounds. Budget for it with
  `RunConfig(max_llm_calls=...)`.

**When you should *not* reach for it:**

- One tool call and a formatted answer. `runtime="adk"` does that faster and
  cheaper — a Codex subprocess buys you nothing.
- You need `output_schema`, `sub_agents`, a `planner`, or per-call model
  callbacks. All refused under this runtime.
- The computation is known in advance. If you already know the analysis is
  "group by region, sum revenue", write that in Python and expose it as an ADK
  tool. This runtime earns its cost when **the code is not knowable ahead of
  time** — one-off analyses, unfamiliar file formats, data whose defects you
  discover only by running against it.
- Latency-sensitive interactive chat.

## The one rule to get right: paths, not payloads

> **The workspace is the data plane. Tool arguments and results are the control
> plane.**

Under this runtime an ADK tool is executed by the runtime's Responses shim, and
its JSON result is fed back to the model **as text in its context**. It does not
land in a file. So:

```python
# WRONG — 2 400 rows enter the context on this request and every later request
def fetch_sales_extract(quarter: str) -> dict:
    return {"rows": [...]}          # ~125 KB of CSV, re-sent on every round

# RIGHT — the data goes to disk, the receipt goes to the model
def fetch_sales_extract(quarter: str) -> dict:
    shutil.copyfile(source, WORKSPACE / "data" / source.name)
    return {"status": "ok", "path": "data/sales_2025q3.csv", "rows": 2400,
            "columns": [...], "bytes": 127983}
```

The model then reads the file with its own sandboxed code, where volume is free.
`publish_report` is the same rule in reverse: it takes *paths* and returns a
receipt of what it copied out.

The extract's size is doing real work here. At 40 rows a model just `cat`s the
file, sees every defect, and writes a correct script first try — the debugging
loop never happens and the example proves nothing. At 2 400 rows `cat` is
useless (Codex truncates command output), so the only way to learn what is in
the file is to write code against it and see what breaks. That is what the
runtime is for, and it is also what real extracts look like.

Two consequences worth internalising:

- **Tool docstrings should say so.** `fetch_sales_extract`'s docstring tells the
  model "returns a receipt, not the data — read the CSV at the returned path".
  Without that, models try to use the receipt as the data.
- **Paths from the model are untrusted input.** `publish_report` resolves every
  path against the workspace and rejects anything that escapes it (`..`,
  absolute paths, symlinks out). See `_resolve_in_workspace`.

### How the tools know where the workspace is

The ADK tools run in *your* process, not in the sandbox, and the runtime does
not currently expose the turn's workspace path to them. This example therefore
pins it:

```python
CodexRuntimeConfig(workspace_root=str(WORKSPACE), reuse_workspace=True, ...)
```

That makes the directory predictable — which is also why you can read Codex's
script afterwards. **Do not copy this into a multi-tenant service.**
`reuse_workspace=True` means every session shares one directory. There, leave
both fields unset: the runtime gives each `(app, user, session, agent)` its own
workspace, which still persists across the turns of that session (that is the
property turn 2 relies on — pinning only makes it visible), and have the tool
receive its destination directory as an argument instead.

## Security is the demo, not boilerplate

```python
CodexRuntimeConfig(
    sandbox="workspace_write",   # may write only in its own workspace
    network_access=False,        # honoured by workspace_write: no sockets
    approval_mode="deny_all",    # refuse every escalation Codex asks for
    max_tool_iterations=8,       # ADK tool round-trips for the whole turn
)
...
run_config = RunConfig(max_llm_calls=60)   # hard cost ceiling
```

The story these four lines tell:

- The model may compute **anything** over the data — that is the point — but
  with the network off it has no socket to send it through. `outbox/` sits
  *outside* the workspace, so the sandbox cannot write there either.
- That leaves the two audited ADK tools as the **only** outbound path. Every
  file that leaves went through `publish_report`, which logs it, size-limits it,
  digests it, and refuses anything that is not a `.md` or `.svg` from inside the
  workspace. That is a boundary you can point an auditor at.
- `approval_mode="deny_all"` keeps it that way. **Never use `"auto_review"`** in
  an example or a deployment: despite the name it is *full auto-approval* — the
  Codex SDK's built-in handler accepts every escalation and cannot be replaced.
- `max_tool_iterations` bounds ADK tool round-trips for the **whole turn**
  (default 32). It is not a cost ceiling; `RunConfig(max_llm_calls=...)` is. The
  codex runtime is the one external runtime that enforces that budget exactly —
  the shim charges it *before* each backend call.

## Why the data is dirty

`data/sales_2025q3.csv` is a realistic warehouse export, which means it is a
mess in four ordinary ways:

| Defect | Rows | What a naive script does |
| --- | --- | --- |
| Thousands separators in a numeric column (`"4,208.40"`) | 22 | `ValueError: could not convert string to float: '4,208.40'` |
| A blank revenue cell | 4 | `ValueError: could not convert string to float: ''` |
| A second date format (`07/23/2025`) | 31 | `ValueError: time data '07/23/2025' does not match format '%Y-%m-%d'` |
| Three spellings of one region (`north`, `NORTH`, `_South`) | 14 | no crash — silently splits one region into three |

**The first defect is on line 212**, so `head` looks perfectly clean and the
first script is written against a file that seems fine.

**Nothing in the prompt mentions any of this.** That is deliberate: if the
instruction described the defects, the model would write a defensive parser on
the first try and the example would demonstrate nothing that `runtime="adk"`
could not do. The first script has to actually crash for the loop to be real.

The last row is the interesting one — it doesn't crash, so only an agent that
*looks at its own output* catches it. That is what the report's `Data notes`
section is for.

## The skill

`skills/sales-report/SKILL.md` carries the house report format (sections,
column order, money formatting, hand-written-SVG rules). It is loaded the
ADK-native way and materialised into Codex's own skill directory, so Codex's
native skill system discovers and progressively loads it. Two reasons it earns
its place here: the format stays out of the prompt, and its `Data notes`
section is what makes the agent's iteration visible in the finished artifact.

## Run

```bash
pip install "veadk-python[codex]"   # openai-codex + the bundled Codex CLI binary

export MODEL_AGENT_API_KEY=...
export MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3
export MODEL_AGENT_NAME=deepseek-v4-flash-260425   # see Known rough edges: model choice matters

# Known issue: Ark rejects the request when VeADK's default prompt caching is
# combined with the `instructions` field Codex always sends
# ("caching is not supported for instructions"). Disable it for now:
export MODEL_AGENT_CACHING=disabled

python examples/codex_data_analysis/main.py
```

macOS or Linux only — the sandbox is seatbelt / landlock+seccomp.

### What to watch for

`main.py` prints every sandboxed command as it runs, because the runtime
surfaces Codex's own `commandExecution` items as ordinary ADK function-call
events:

```
  → fetch_sales_extract({'quarter': '2025Q3'})
  ← fetch_sales_extract: {'status': 'ok', 'path': 'data/sales_2025q3.csv', 'rows': 2400, ...}
  $ cat .../skills/sales-report/SKILL.md
  $ head -20 data/sales_2025q3.csv                    # looks perfectly clean
  $ cat > analyze.py << 'PY' ... PY; python3 analyze.py
    exit=1
    | ValueError: could not convert string to float: ''
  $ cat > analyze.py << 'PY' ... PY                   # rewritten
  $ python3 -c "... find the bad rows ..."
  $ cat > build_report.py << 'PY' ... PY; python3 build_report.py
  $ cat report.md
  → publish_report({'report_path': 'report.md', 'chart_path': 'chart.svg'})
  ← publish_report: {'status': 'ok', 'published': [...]}
```

That is a real transcript, lightly abridged: 12 sandboxed commands, two of them
failing, `head -20` showing nothing wrong because the first defect is 190 lines
further down. Turn 2 then read the report and chart it had left behind, replaced
just the chart and the Trend paragraph, recovered from a `zsh` quoting error,
and republished. Expect that shape rather than those exact commands — the number
of rounds varies from run to run.

Afterwards, read what Codex actually left behind:

```bash
ls examples/codex_data_analysis/.codex_workspace   # its script, its drafts
cat examples/codex_data_analysis/outbox/*/report.md
```

The `Data notes` section of the report lists the defects it had to work around
— compare it against the table above to see how much it caught. In the run
above it reported three of the four classes with exact row counts (4 null
revenues, 31 mis-formatted dates, 14 region-casing rows) and quietly handled
the fourth; every published figure matched the ground truth to the cent.

## Known rough edges (as of this writing)

These are runtime/backend issues, not example bugs. They shape the code above,
so they are worth knowing before you build on it.

- **Ark rejects VeADK's default prompt caching under this runtime.** Codex
  always sends the Responses `instructions` field, and Ark answers
  `400 InvalidParameter: caching is not supported for instructions`. Every
  codex-runtime agent on Ark fails on the first backend call until you set
  `MODEL_AGENT_CACHING=disabled`.
- **Not every Ark model can be the backend, and the failure is silent.** After
  its first tool round Codex replays its own `reasoning` items in the
  conversation, and the shim forwards them verbatim. `doubao-seed-1-6-250615`
  answers `400 InvalidParameter: input[N].reasoning ... Item reasoning is not
  supported for model`. What you see is *not* an error: the first backend call
  succeeds, the agent runs exactly one command, and the turn ends
  `status=completed` with a half-finished workspace and a cheerful summary. The
  400 appears only as a `codex_backend_api_error` warning in the log — nothing
  is raised to the caller. Use `deepseek-v4-flash-260425` (verified end to end),
  and when a codex turn stops suspiciously early, grep the log for
  `codex_backend_api_error` before believing the answer.
- **A chat model bridged into Codex's protocol narrates instead of acting.**
  Codex ends a turn on an assistant message, so a model that replies *"I'll now
  write the analysis script"* — or that calls Codex's `request_user_input` tool,
  which is advertised even though no user can answer mid-invocation — silently
  ends the turn with nothing done. That is why the instruction opens with *"Act,
  do not narrate"* and forbids asking questions. Expect to spend prompt budget
  on this with any chat backend.
- **`apply_patch` never reaches the backend.** The shim forwards only
  `function`-typed tools, and Codex's file-editing tool is not one — the list
  the backend actually sees is `exec_command`, `write_stdin`, `update_plan`,
  `request_user_input`, `view_image`, plus your ADK tools. Codex's own system
  prompt still tells the model to use `apply_patch`, so it will try, and burn a
  round. Hence the instruction's *"create files with a heredoc"*.

The general lesson: on a chat backend this runtime's effective tool surface is
narrower than Codex's documentation implies, and the instruction has to close
the gap.

## Constraints

`runtime="codex"` refuses a large part of the `Agent` surface rather than
silently ignoring it. Relevant here:

- rejected: `sub_agents`, `model=` (use `model_name=`), `output_schema`,
  `planner`, `code_executor`, `include_contents="none"`, `enable_supervisor`,
  and any `generate_content_config` field other than `system_instruction`;
- also rejected: `CodexRuntimeConfig(sandbox="full_access", network_access=False)`
  — that combination reads as "no network" while granting full access;
- dropped with a warning: `knowledgebase`, `example_store`, `skills_mode`, ...

See the [support matrix](../../docs/content/docs/framework/agent/runtime.en.mdx#support-matrix).
