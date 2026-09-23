# VeADK Decision Model Extension

[中文](README.zh.md)

`veadk.extensions.decisions` adds an optional **decision model** to VeADK: a
fast model that returns typed judgements (a choice, a score, or a probability)
instead of prose. It is configured separately from your agent's conversational
model, is provider-agnostic, and is opt-in — without configuration nothing
else in VeADK changes.

Use it where a small, repeatable judgement currently costs a slow model call:
routing a request, ranking candidates, extracting a value from a closed set,
or checking whether a statement holds.

## Install

The extension ships with VeADK and needs no extra dependency.

```bash
pip install veadk-python
```

## Configure

```text
DECISION_MODEL_ENABLED=true
DECISION_MODEL_PROVIDER=typesafe        # typesafe | systemone
DECISION_MODEL_NAME=jev-latest
DECISION_MODEL_API_BASE=https://api.typesafe.ai
DECISION_MODEL_API_KEY=...
DECISION_MODEL_TIMEOUT=30
DECISION_MODEL_MAX_RETRIES=3
```

`typesafe` is the hosted service and `systemone` is a self-hosted System One
server; both expose the same request contract, so only `api_base` changes.
`api_base` may be given with or without the trailing `/v1/systemone`.

The same settings can live in `config.yaml`, which VeADK flattens into
`MODEL_DECISION_*` variables. Set both spellings and the explicit
`DECISION_MODEL_*` variable wins.

```yaml
model:
  agent: {}
  decision:
    enabled: true
    provider: typesafe
    name: jev-latest
    api_base: https://api.typesafe.ai
    api_key: ${YOUR_KEY}
```

## Quick Start

```python
from veadk.extensions.decisions import DecisionExtension

extension = DecisionExtension.from_env()

if extension.enabled:
    answer = await extension.achoose(
        "My card was charged twice.",
        "Which team should handle this?",
        ["billing", "shipping", "returns"],
    )
    print(answer.choice, answer.confidence, answer.probabilities)
```

Every answer is a typed object: `ChoiceAnswer`, `ScoreAnswer`, or
`NoulAnswer`. `noul` (the probability of "yes") has no separate confidence —
use it directly, and prefer a threshold you have measured on your own data.

| Call | Returns |
| --- | --- |
| `evaluate(state, questions)` / `aevaluate` | Every answer for one state, batched into one request. |
| `choose(state, instructions, options)` / `achoose` | `ChoiceAnswer` |
| `score(state, instructions, levels)` / `ascore` | `ScoreAnswer` |
| `noul(state, instructions)` / `anoul` | `NoulAnswer` |

Ask independent questions in **one** `evaluate` call: questions run in
parallel and code can ignore answers it does not need.

## Give the agent the tool

```python
from veadk import Agent
from veadk.extensions.decisions import decision_evaluate

agent = Agent(name="router", tools=[decision_evaluate])
```

The tool asks the configured decision model for one judgement and returns
`{"kind", "answer", "confidence", ...}`. It returns `{"error": ...}` when the
decision model is unconfigured or the request fails, so a run never breaks
because of an optional capability.

## Source Layout

| Path | Purpose |
| --- | --- |
| `config.py` | Environment/config parsing, endpoint normalization. |
| `client.py` | System One HTTP client (sync and async), retry with backoff. |
| `questions.py` | Builders for the three question types. |
| `types.py` | Typed answers and the response parser. |
| `extension.py` | Shared entry point: `DecisionExtension`, the process-wide default. |
| `tools.py` | The agent-facing `decision_evaluate` tool. |

## Not Included Yet

- Plugins that use the decision model for tool filtering, context compaction,
  or response verification. The shared `DecisionExtension` instance is the
  intended entry point for them.
- Registration of `decision_evaluate` in the core built-in tool registry
  (`veadk/tools/__init__.py`). The frontend studio tool catalog keeps a static
  declaration table that must match that registry exactly, so registering the
  tool there requires adding the matching declaration and schema.
- Tool-response caching and connection reuse; each call opens its own HTTP
  client.
- Non-English question text: judgement quality is best with English
  `instructions`, even when the evaluated state is Chinese.
