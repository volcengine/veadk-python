# Ops triage assistant (`runtime="codex"`)

> 中文版见 [README.zh.md](./README.zh.md)

**The model can read a day of production logs and physically cannot leak
them.** It runs in an OS sandbox with `network_access=False` — there is no
socket to send anything out of — and it can write only its own scratch
directory. The single channel to the outside world is `file_incident_ticket`,
an ADK tool you wrote, whose arguments you can log, validate and cap.

That is the answer to "can I let an LLM near my logs", and it is why this
example exists.

What it does: an on-call agent investigates an incident it has never seen
before. ADK tools pull raw logs, a metric series and the deploy log out of an
internal system and drop them in the sandbox as files. Codex then writes and
runs its own shell and Python to grep, aggregate and correlate them —
several programs, refining as it learns the shape of the data — and finally
files a ticket naming a root cause with the numbers behind it.

```
                 ┌── ADK tools (your code, your process) ──┐
   internal      │  fetch_application_logs                 │      workspace/
   systems  ───► │  fetch_service_metrics    write files ──┼───►  logs/*.log
                 │  fetch_deploy_history                   │      metrics/*.csv
                 └─────────────────────────────────────────┘      deploys/*.json
                                                                       │
                          ┌────────────────────────────────────────────┘
                          ▼
        Codex, inside the OS sandbox: no network, no writes outside
        the workspace.  Writes analysis/*.py, runs them, reads the
        output, writes the next one.
                          │
                          ▼  file_incident_ticket(...)  ← the only egress
                     outbox/INC-....json   (outside the workspace,
                                            unreachable from the sandbox)
```

## Why this task suits `codex` and not `adk`

Be honest about this: for most agents, `runtime="codex"` is strictly worse than
the default `runtime="adk"`. It spawns a subprocess per turn, re-serializes the
conversation into the prompt, and refuses a long list of ADK features. It earns
its cost only when the agent's real work is *running code it just wrote*. Ad-hoc
log analysis is that case:

- **You cannot pre-build a tool per question.** "Which error signature changed
  rate after 14:00?" "Was the pool saturated before or after the latency rose?"
  "Does this pattern appear a week earlier?" The useful aggregations over a log
  file are unbounded, and each new incident asks a new one. A tool per question
  is a treadmill; an interpreter is not.
- **The data does not fit in the context, and the model cannot count.** One day
  is 7,494 log lines (1.4 MB) plus 8,640 metric rows. Even if you paid to paste
  them in, "951 payment timeouts vs 640 pool timeouts" is a job for
  `collections.Counter`, not for a language model reading. Executed code gives
  exact numbers; a summarized prompt gives plausible ones.
- **Getting it right takes several passes.** In our run the agent looked at the
  head of the log, discovered it is not uniformly JSON, wrote a per-hour
  signature histogram, then a change-point script, then a metrics script, then
  a saturation check — each informed by the last. That loop is Codex's native
  mode: many commands per model turn, with the program output staying inside
  its loop instead of round-tripping through your event stream.
- **Sandboxing is what makes it acceptable at all.** Letting a model write and
  execute arbitrary code over production logs is only sane if the code cannot
  reach the network or the rest of the disk. That is a runtime property, not
  something an instruction can promise.

The nearest alternative is `runtime="adk"` with an ADK `code_executor`.
Compare honestly: `UnsafeLocalCodeExecutor` runs model-written code in your own
process; `ContainerCodeExecutor` needs a Docker daemon you operate;
`VertexAiCodeExecutor` is a managed Google service. The codex runtime gives you
an OS-level sandbox (macOS seatbelt / Linux landlock+seccomp) on the machine
you already have, a workspace that survives the whole session, and an agentic
loop that runs many commands per model turn rather than one code block per LLM
call.

### When *not* to reach for this runtime

- **The question is fixed.** If on-call always asks "how many 5xx yesterday",
  write that tool. It is cheaper, faster, deterministic, and testable.
- **You need ADK features this runtime replaces.** `veadk/runtime/compat.py`
  refuses `sub_agents`, `model=` (use `model_name=`), `output_schema`,
  `planner`, `code_executor`, `include_contents="none"` and
  `enable_supervisor`, and warns that `knowledgebase`, `example_store`,
  model fallback chains, per-LLM-call callbacks and per-call tracing spans are
  dropped. Read that file before porting an agent.
- **Per-turn latency or cost is the constraint.** Each turn spawns a Codex
  subprocess, and the sandboxed loop makes many backend calls inside one turn.
- **The data must never touch this host.** The workspace is a real directory on
  the machine running the agent.

## The rule that makes ADK tools work here

**The workspace is the data plane. Tool arguments and results are the control
plane.**

An ADK tool under `runtime="codex"` does not run inside the sandbox. VeADK's
shim executes it in your process and pastes whatever it returns into the
model's context as the function-call result. A tool that returns 7,494 log
lines therefore does not "give the model the logs" — it destroys the turn, and
the model still has to grep the text afterwards.

So every `fetch_*` tool here writes a file into the workspace and returns a
receipt:

```python
{"status": "ok",
 "path": "logs/checkout-api-prod_20260824T0000_20260825T0000.log",
 "lines": 7494, "bytes": 1396879,
 "note": "one event per line, chronological; content not returned"}
```

Roughly 40 tokens instead of 400,000. The model gets a pointer; the sandbox
gets the bytes. This is the single most important thing to get right when
combining ADK tools with this runtime, in either direction:

- **Tools hand data *in* by writing files** and returning a path plus enough
  shape (row count, column names, units) to plan against.
- **The model hands conclusions *out* through tool arguments**, which are
  small, structured, and yours to validate — `file_incident_ticket` caps field
  lengths, checks the severity enum, and prints one audit line per ticket.

### Where the tools write

An ADK tool asks for the directory of the turn that is calling it:

```python
from veadk.runtime.codex import current_workspace

def fetch_application_logs(stream: str, start_time: str, end_time: str) -> dict:
    workspace = current_workspace()   # this turn's directory, or None
    if workspace is None:             # not a codex turn — an error, not a guess
        return {"status": "error", "message": "no sandbox working directory"}
    ...
```

The runtime binds that value around each tool call, so it stays correct with
several sessions in flight in one process. That is why this example leaves
`workspace_root` and `reuse_workspace` unset: every `(app, user, session,
agent)` gets its own directory — which is what an on-call service wants, since
two incidents under investigation at the same time must not share a scratch
directory — and it still persists across the turns of one session, which is what
turn 2 reuses.

`current_workspace()` returns `None` rather than raising outside a codex turn
(another runtime, an `AgentTool`, a unit test), and these tools turn that into
an ordinary error result the model can act on.

Pinning is the opposite trade, and it is a **single-tenant** one: `workspace_root`
plus `reuse_workspace=True` gives you one predictable directory you can `ls`
after the process exits, at the price of every session sharing it.

## The security configuration, knob by knob

```python
codex_runtime_config=CodexRuntimeConfig(
    sandbox="workspace_write",
    network_access=False,
    approval_mode="deny_all",
    max_tool_iterations=12,
    tool_timeout_seconds=60.0,
)
...
run_config=RunConfig(max_llm_calls=40)
```

| Setting | What it prevents |
| --- | --- |
| `sandbox="workspace_write"` | Model-written code can create and overwrite files **only** in the workspace (plus the temp dirs). It cannot touch your source tree, your dotfiles, or `outbox/`. Codex is told its writable roots explicitly, and they are exactly those three. |
| `network_access=False` | No sockets. The model reads production logs with nowhere to send them. Only the `workspace_write` sandbox honours this flag — `read_only` and `full_access` ignore it, and `full_access` + `network_access=False` now raises rather than pretending to isolate. |
| `approval_mode="deny_all"` | Escalation requests out of the sandbox are refused. **Never use `"auto_review"` in an example or in production**: it is not a review step. The Codex SDK's built-in handler accepts every escalation and cannot be replaced, so it is full auto-approval. |
| `RunConfig(max_llm_calls=40)` | A hard ceiling on a self-directed loop. Under `codex` the budget is charged *before* each backend call, so it binds exactly rather than one call late. |
| `max_tool_iterations=12` | ADK tool round-trips allowed for the **whole turn** (not per backend request). Four fetches plus a ticket fits with room to spare. |
| `tool_timeout_seconds=60.0` | A wedged ADK tool cannot hang the turn. |
| `outbox/` outside the workspace | Egress is a code path you own, not a file the model can drop somewhere. |
| no `workspace_root` / `reuse_workspace` | One workspace per `(app, user, session, agent)`, reaped when idle. Two incidents investigated at once cannot read each other's files, and yesterday's run cannot leave data in today's sandbox. |

This is checkable, not aspirational. Asking the agent to try it, from inside
its own sandbox:

```
touch ./inside-ok          -> exit 0
touch ../outbox/ESCAPED    -> touch: ../outbox/ESCAPED: Operation not permitted
touch ../ESCAPED2          -> touch: ../ESCAPED2: Operation not permitted
```

**One thing `workspace_write` does not do: it does not restrict *reads*.** The
sandbox permits reading the filesystem and only constrains writes. Nothing can
leave — no network, and the only egress is a tool whose payload you inspect —
but if the host holds secrets you would rather a model never read, run the
agent in a container or on a dedicated box.

## The incident, so you can check the answer

Everything is generated deterministically by `ops_backend.py` from a fixed
seed, so the same incident appears on every machine. Ground truth for
**2026-08-24 UTC**:

- **Root cause.** `checkout-api 4.11.0` deployed at **14:07:55Z** raised worker
  concurrency 8 → 32 while the DB connection pool stayed at 20. A new error
  signature, `db.pool acquire timeout after 5000ms`, is **zero all day until
  14:11:02Z** and then grows to 640 occurrences. `db.pool.in_use` climbs from
  ~6 and pegs at exactly `db.pool.size` = 20; p99 latency goes 180 ms → 5,200
  ms and 5xx/min goes 0.5 → 9.0, both sustained to the end of the window.
- **Decoy 1 — the loudest error.** `payments.gateway timeout` is the single
  most frequent ERROR (951, more than the real signature's 640), and it runs at
  a flat 35–45/hour all day and all of the previous week. Ranking signatures by
  count picks it, and it is chronic noise.
- **Decoy 2 — the other deploy.** `notify-worker 2.3.1` shipped at 13:52:40Z,
  fifteen minutes before the real one, and produced an immediate burst of 124
  `notify.webhook retry exhausted` errors. The burst stops on its own after six
  minutes. "Blame the most recent deploy before the errors" picks this.
- **Decoy 3 — the biggest number on the dashboard.** `notify.queue_depth`
  spikes from 12 to **900** between 13:52 and 14:25, peaking *before* the real
  onset and recovering fully. It dwarfs every other metric movement.
- **The ruled-out hypothesis.** `checkout.rps` is identical on both days, so
  the incident is not load-driven.
- **A single grep is not enough** by construction: the answer needs per-hour
  counts per signature, a change point, a pivot of a long-format CSV, and a
  join against deploy records — whose timestamps come from a CI system in
  **UTC+08:00** while the logs are UTC and the metrics are epoch seconds. And
  the log stream is not uniform: ~14% of lines are plaintext sidecar output, so
  `json.loads` on every line raises.

The follow-up turn asks about **2026-08-17**, the same weekday a week earlier.
The correct answer is *no*: zero pool timeouts, flat metrics, same chronic
payment noise.

## What actually happened when we ran it

Ark `deepseek-v4-pro-260425`, four runs of the full two-turn session.

**Turn 1 found the intended root cause in all four.** 4 ADK tool calls and
10–12 sandboxed commands, 3.5–4 minutes. The shape was the same every time:
read the runbook skill, fetch all three sources, `head` the log and the CSV —
which is how it discovered the stream is not uniformly JSON and wrote a parser
that skips non-JSON lines — then write and run a series of separate programs
under `analysis/`, each answering the question the previous one raised: a
per-hour signature histogram, then a change-point locator, then a metrics
aggregation, then a pre/post-deploy comparison.

Every ticket named `checkout-api 4.11.0`, concurrency 8→32 against a pool of
20, converted `22:07:55 +0800` to `14:07:55Z` correctly, and explicitly ruled
out both decoy deploys and the chronic payment timeouts in the evidence list.
One evidence item, verbatim:

> `db.pool.in_use: before avg=6.0 (max=8.0), after avg=19.2 (max=20.0).`
> `Saturated (in_use >= pool size of 20) for 531/592 minutes (89.7%) after deploy.`

**Turn 2 was where it went wrong, twice, for one concrete reason.** Two of the
four runs answered cleanly in 1–8 sandboxed commands, reusing the analysis from
turn 1 instead of re-deriving it. The other two got stuck: the scripts written
in turn 1 had the 08-24 filename baked in, so instead of parameterizing them
the model started renaming data files to fit — `mv`, run, `rm`, `mv` back — and
looped until `RunConfig(max_llm_calls=40)` cut the turn off. That is the
ceiling doing its job, not a bug; `main.py` catches it and prints
`[budget] the turn hit the 40-call ceiling`. But it is a fair warning that a
self-directed loop needs a budget, not just good intentions.

That failure is also what earned the skill its last paragraph. Adding one line
to the runbook — *take the input path as `sys.argv[1]`, never hardcode it* —
changed turn 2 to a single clean invocation:

```
[sandbox 1] python3 analysis/error_signatures.py logs/checkout-api-prod_20260817T0000_20260818T0000.log
```

Honest caveat about iteration: **turn 1 never produced a failing command.** Its
iteration was refinement-driven — each program written to answer what the last
one turned up — not crash-driven, because the model dodged the mixed-format
trap by looking at the file before parsing it, which is what you would want.
The failing commands we did see (`exit 1`, three of them) came from the turn-2
rabbit hole. Expect variance; a weaker model will fail more, and you will see
it in the `[sandbox N] -> exit ...` lines `main.py` prints.

## The skill

`skills/incident-triage/SKILL.md` is your team's triage runbook — pull all
sources first, characterize signatures instead of ranking them, locate the
change point, correlate with deploys, confirm in the metrics, explain the
mechanism, file one ticket. Codex's *native* skill system drives it: VeADK
materializes the ADK `SkillToolset` into `$CODEX_HOME/skills/`, and Codex
discovers and loads it on its own (the first sandboxed command in our run was
Codex reading the SKILL.md).

It deliberately encodes **method, not answers** — it never mentions the log
format, the timezone quirk, or any of the three decoys by name. That is what
makes it a runbook rather than a spoiler, and it is why the agent still has to
do the work.

## Running it

```bash
pip install "veadk-python[codex]"       # openai-codex + the bundled Codex CLI
cd examples/codex_ops_assistant
cp .env.example .env                    # add your Ark key
python main.py
```

macOS or Linux only: the sandbox is seatbelt / landlock+seccomp. Pick a model
with solid tool-calling and code-writing ability — this agent debugs its own
scripts — and read the two Ark gotchas below before swapping the model.

Afterwards, look at what left the sandbox:

```bash
cat outbox/INC-*.json      # everything that left the sandbox
```

The workspace itself — the fetched data and the programs the model wrote under
`analysis/` — is printed by `main.py` just before it exits, because the
per-session workspace lives under a temporary root the runtime removes on
process exit. Nothing to clean up between runs, and no way for last week's files
to still be in the sandbox while the model investigates today's incident. Pin
`workspace_root` + `reuse_workspace` if you would rather keep the directory
around and inspect it later.

## Two Ark gotchas worth knowing before you port an agent

**1. Prompt caching cannot ride on a Codex turn.** VeADK enables Ark prompt
caching by default (`extra_body={"caching": {"type": "enabled"}}`), and Codex
always sends a top-level `instructions` field. Ark refuses the combination:

```
InvalidParameter: The parameter `instructions` specified in the request are not
valid: caching is not supported for instructions.
```

The codex shim strips `caching` and `expire_at` out of `extra_body` for you, so
you do not have to do anything — but the codex runtime forwards the *rest* of
`model_extra_config` verbatim (unlike `piagent`, which drops it entirely), so a
body key your backend dislikes will 400 every turn and the agent will answer
with an empty string. If you ever see the error above, set
`MODEL_AGENT_CACHING=disabled` or pass
`model_extra_config={"extra_body": {"caching": {"type": "disabled"}}}`.

**2. Not every Ark model accepts Codex's conversation.** Codex replays
`reasoning` items in the request `input`. Models that do not support them abort
the turn part-way through, after the first tool round:

```
InvalidParameter: The parameter `input[3].reasoning` ... Item reasoning is not
supported for model: doubao-seed-1-6, version: 250615
```

We saw exactly that with `doubao-seed-1-6-250615`: the agent fetched two files,
ran one `grep`, and then died mid-investigation. `deepseek-v4-pro-260425` (the
default here) accepts them and completes. Try a short turn on a new model
before pointing it at real work.

## Files

| File | What it is |
| --- | --- |
| `main.py` | The agent, the sandbox configuration, and a two-turn session that narrates every sandboxed command. |
| `ops_tools.py` | The four ADK tools: three that write files into the workspace and return receipts, one that files a ticket to `outbox/`. |
| `ops_backend.py` | The simulated internal observability system. Deterministic; this is where the incident and the decoys are defined. |
| `skills/incident-triage/SKILL.md` | The triage runbook, driven by Codex's native skill system. |
