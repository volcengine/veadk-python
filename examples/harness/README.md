# Harness modules: ContextEngine + ResultVerifier

This example shows how to compose two Harness modules with a veADK Agent for
context engineering, evidence tracking, and final-answer verification.

- `ContextEngine` pins the original task, filters noisy history, assembles an
  evidence-first context header, and records a small budget report.
- `ResultVerifier` records tool receipts, gathers evidence references, checks
  final answers for unsupported URLs and ungrounded external facts, and writes a
  local verification report.

The implementation is self-contained so developers can read, run, test, and
adapt the pattern in one directory.

## Layout

```text
examples/harness/
├── main.py
├── harness_agent.py
├── harness_modules/
│   ├── core.py
│   ├── context_engine.py
│   ├── result_verifier.py
│   ├── tool_wrappers.py
│   └── stores.py
├── tests/
└── golden/
    ├── production_scenarios.jsonl
    ├── context_engine_cases.jsonl
    └── verifier_cases.jsonl
```

## Run

Configure the normal veADK model environment variables, then run:

```bash
python examples/harness/main.py
```

The run writes local audit data under `.harness_runs/`:

- `events.jsonl`
- `messages.jsonl`
- `receipts.jsonl`
- `evidence/*.txt`
- `reports/<session_id>-<run_id>.json`

## Core usage

```python
from harness_agent import build_harness_agent

bundle = build_harness_agent()
answer = await bundle.run(
    "请查一下 veADK Harness 示例的核心能力，给出来源，并用 3 条要点回答。",
    session_id="harness-demo",
)
report = bundle.latest_report(session_id="harness-demo")
```

`bundle.agent` and `bundle.runner` are regular veADK `Agent` and `Runner`
instances. The thin `bundle.run(...)` method coordinates `user_id`,
`session_id`, and `original_prompt` so the Harness processor can create local
receipts, evidence, context events, and verification reports.

## Test

The tests use fake tools and fake runner events, so no model key is needed:

```bash
pytest examples/harness/tests
```

The validation targets are:

- task anchor retention across follow-up turns;
- removal of progress and control messages from model context;
- deterministic detection of fabricated URLs;
- failure when a current/external factual answer has no evidence;
- receipt recording for failed tools;
- externalization of large tool results.

The scenario-level golden set is
`examples/harness/golden/production_scenarios.jsonl`. It groups common
production cases by scenario and module, so developers can add new regression
cases without coupling them to a specific product incident or project-specific dataset.
The smaller `verifier_cases.jsonl` and `context_engine_cases.jsonl` files keep
module-focused golden checks.

## Evaluate the Harness lift

Run the offline A/B evaluation:

```bash
python examples/harness/evaluation/run_eval.py
```

The evaluation isolates deterministic Harness effects rather than model quality.
Baseline uses raw history and trusts every non-empty answer. Harness uses
`ContextEngine` plus `ResultVerifier`.
The case set uses common production-style developer scenarios: stale RAG
memory, failed tool receipts, permission over-blocking, runtime parameter drift,
and multi-turn context anchoring.

Current result:

| Metric | Baseline | Harness | Delta |
| --- | ---: | ---: | ---: |
| Result verifier accuracy | 20.0% | 100.0% | +80.0 pp |
| Unsafe false-accept rate | 100.0% | 0.0% | -100.0 pp |
| Unsafe detection recall | 0.0% | 100.0% | +100.0 pp |
| Context quality score | 0.0% | 100.0% | +100.0 pp |

Offline report summary by scenario:

| Scenario | Baseline behavior | Harness lift | Module |
| --- | --- | --- | --- |
| RAG memory freshness | Trusts stale-memory answers without current evidence. | Blocks the answer until current knowledge evidence exists. | `ResultVerifier` |
| Tool failure claimed as success | Trusts a final JSON that says the operation passed. | Detects failed tool receipts and blocks false completion claims. | `ResultVerifier` |
| Permission over-blocking of allowed tools | Trusts a success result even when an allowed tool was blocked. | Treats failed receipts as incompatible with `operation_completed=true`. | `ResultVerifier` |
| Runtime parameter drift | Trusts unsupported runtime values such as a wrong token limit. | Blocks key numeric facts that are not present in evidence. | `ResultVerifier` |
| Multi-turn context anchoring | Raw history includes progress noise and loses the original task anchor. | Pins the original task and removes control-message pollution. | `ContextEngine` |
| Current evidence beats stale memory | Recent history can surface stale cached answers before evidence. | Puts current evidence before history and keeps the original task anchor. | `ContextEngine` |

Reports are written to
`examples/harness/evaluation/results/harness_eval_report.json` and
`examples/harness/evaluation/results/harness_eval_report.md`.

## Run model-in-the-loop evaluation

The model evaluation makes real veADK model calls. Export the standard model
environment variables, or pass any dotenv file that contains
`MODEL_AGENT_API_KEY`, `MODEL_AGENT_NAME`, and `MODEL_AGENT_API_BASE`:

```bash
python examples/harness/evaluation/run_model_eval.py \
  --env-file /path/to/model.env
```

If the variables are already exported in the shell, `--env-file` can be omitted.

No secret values are written to the reports. The script compares a normal veADK
Agent that trusts every non-empty answer with the Harness Agent that trusts an
answer only when `VerificationReport.done` is true.

Reports are written to
`examples/harness/evaluation/results/harness_model_eval_report.json` and
`examples/harness/evaluation/results/harness_model_eval_report.md`.

Current sample model result:

| Metric | Baseline | Harness | Delta |
| --- | ---: | ---: | ---: |
| Trust decision accuracy | 66.7% | 100.0% | +33.3 pp |
| Unsupported false-accept rate | 100.0% | 0.0% | -100.0 pp |
| Answerable verified pass rate | - | 100.0% | +100.0 pp |
| Answerable receipt coverage | - | 100.0% | +100.0 pp |
| Unsupported request block rate | - | 100.0% | +100.0 pp |

The model report also includes a scenario matrix with the scenario as the first
column, covering RAG freshness, tool evidence receipts, and no-evidence
hallucination suppression.

Model report summary by scenario:

| Scenario | Baseline runtime | Harness runtime | What the result shows |
| --- | --- | --- | --- |
| RAG freshness with source grounding | Trusts the non-empty model answer. | Trusts only after tool receipts and source evidence are present. | Answerable sourced requests can still pass when grounded. |
| Tool evidence and receipt coverage | Trusts the final text without runtime receipt enforcement. | Keeps the answer trusted and records tool receipts. | Harness adds auditability without blocking valid answers. |
| No-evidence hallucination suppression | Trusts a non-empty unsupported answer. | Blocks the answer because no tool evidence or source receipt exists. | The trust gate prevents no-evidence source claims from reaching callers. |

## Design Notes

This example focuses on the core developer workflow:

- build a task-aware context header before the model runs;
- wrap tools so every capability call leaves an auditable receipt;
- attach evidence references to tool outputs;
- verify the final answer before treating it as trusted;
- use tests and offline/model evaluations to measure the lift.

The modules are intentionally compact and explicit, making them suitable as a
starting point for product-specific Harness extensions.
