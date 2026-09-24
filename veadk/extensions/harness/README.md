# VeADK Harness Extension

[中文](README.zh.md)

`veadk.extensions.harness` exposes two mutually exclusive integration modes.
The legacy in-process mode adds three reusable capabilities:

- context preparation for each agent turn
- tool-result compaction
- answer verification and hallucination suppression

The legacy extension can be used directly as Python modules or attached to a
VeADK Runner. It does not require a separate runtime service.

Managed Sidecar mode is different: all Harness behavior runs in the private
Sidecar Runtime. `HarnessExtension.from_env()` only starts that Runtime, applies
its model/MCP bindings, and owns its lifecycle. In this mode `plugins()` always
returns an empty list and no `veadk.extensions.harness.plugins` implementation is
loaded or attached to the application process. Do not combine the two modes.

## Install

```bash
pip install "veadk-python[harness]"
```

The base extension is bundled with VeADK. The `harness` extra installs the
optional in-process Headroom compaction provider.

For local development inside this repository:

```bash
pip install .
```

For local development with Headroom:

```bash
pip install ".[harness]"
```

## Quick Start

```python
from veadk.extensions.harness.plugins import build_harness_plugins
from veadk import Agent, Runner

agent = Agent(name="research_agent")
runner = Runner(
    agent=agent,
    app_name="research",
    plugins=build_harness_plugins(
        components=["invocation_context", "compactor", "response_verification"],
        profile="research",
    ),
)
```

## Plugins

| Plugin | Main hooks | Purpose |
| --- | --- | --- |
| `HarnessInvocationContextPlugin` | `on_user_message_callback`, `before_model_callback` | Prepares task anchors, recent context, and tool-use guardrails. |
| `HarnessCompressPlugin` | `before_model_callback`, `after_tool_callback` | Shrinks oversized tool outputs while preserving useful facts. |
| `HarnessResponseVerificationPlugin` | `after_tool_callback`, `after_model_callback`, `on_event_callback` | Records tool receipts and flags unsupported final claims. |

## Runtime Environment

```text
HARNESS_ENHANCE_ENABLED=true
HARNESS_ENHANCE_COMPONENTS=invocation_context,compactor,response_verification
HARNESS_PROFILE=research
HARNESS_COMPRESSION_PROVIDER=builtin
HARNESS_COMPACTION_STRATEGY=builtin
HARNESS_LONG_RUN_STRATEGY=counter
HARNESS_MODE_STRATEGY=keywords
```

```python
from veadk.extensions.harness.env import build_harness_plugins_from_env

plugins = build_harness_plugins_from_env()
```

With VeADK HarnessApp deployment, the same settings can be written in
`harness.yaml`:

```yaml
harness_enhance:
  enabled: true
  components: [invocation_context, compactor, response_verification]
  profile: general
  compression_provider: builtin
```

## Decision Model Strategies

Three judgement points can ask the configured decision model instead of using
their built-in rules. Every strategy is opt-in, and without a decision model
each one keeps its rule and logs a warning.

| Strategy | Setting | Rule it replaces | Unavailable behaviour |
| --- | --- | --- | --- |
| Compaction candidates | `HARNESS_COMPACTION_STRATEGY=decision` | Role and size based candidate selection | Builtin rules |
| Long-run steering | `HARNESS_LONG_RUN_STRATEGY=decision` | Model-call counter | Counter, and always after `unconditional_after_model_calls` |
| Context mode blocks | `HARNESS_MODE_STRATEGY=decision` | Precision and artifact keyword markers | Keyword markers |
| Final-answer support | `HARNESS_VERIFIER_STRATEGY=decision` | Completion markers plus a successful-receipt check | Builtin rules |

Every judgement asks for the probability of "yes" in `[0, 1]`, and each point
keeps its own threshold: raising one point's bar does not raise the others',
because the same answer costs each point a different thing. Two points rate
instead of asking yes/no, and their thresholds compare that rating. Each
setting accepts a `HARNESS_ENHANCE_`-prefixed alias, clamps out-of-range
values, and falls back to `0.5` for an unusable one.

| Threshold | Setting | What a high value means |
| --- | --- | --- |
| Compaction candidates | `HARNESS_COMPACTION_KEEP_THRESHOLD=0.5` | Keeps more tool output verbatim |
| Long-run steering | `HARNESS_LONG_RUN_READY_THRESHOLD=0.5` | Steers a run toward its answer sooner |
| Context mode blocks | `HARNESS_MODE_DECISION_THRESHOLD=0.5` | Injects the mode block more often |
| Final-answer support | `HARNESS_VERIFIER_SUPPORT_THRESHOLD=0.5` | Requires more evidence before the answer passes |

Two strategies also choose an action instead of only crossing a threshold, and
the action shapes what the plugin injects:

| Strategy | Action it picks | Effect |
| --- | --- | --- |
| Long-run steering | `narrow_scope` / `nudge_to_finish` / `force_finish` | Replaces the injected guidance with the one that fits the trajectory |
| Final-answer support | `retry_tool_call` / `soften_claim` / `drop_claim` / `ask_user` | Fills the repair instruction the caller hands back to the model |

An action that names no known option keeps the default wording; the rating it
came with is still used.

They need a configured decision model; see
[decisions](../decisions/README.md) for the `DECISION_MODEL_*` variables. A
failed judgement degrades to the rule above instead of failing the run.

Assembling plugins in code selects the same strategies as arguments instead of
environment variables: `compaction_config=ToolResultCompactorConfig(strategy="decision")`,
`context_config=HarnessInvocationContextConfig(mode_strategy="decision")`, and
`long_run_strategy="decision"` / `long_run_ready_threshold=0.5` on
`HarnessExtension`, plus `verifier_config=FinalResponseVerifierConfig(strategy="decision", support_threshold=0.5)`.
Passing an `env` mapping instead makes the environment
variables the only source, as `HarnessExtension.from_env()` does.

## Direct Module Usage

```python
from veadk.extensions.harness import HarnessInvocationContextBuilder, HarnessInvocationRef

context = HarnessInvocationRef(session_id="session-1", invocation_id="run-1")
builder = HarnessInvocationContextBuilder()
bundle = builder.prepare_context(context, user_input="Summarize these tool results.")
```

## Learn More

See [docs/extensions/harness/README.md](../../../docs/extensions/harness/README.md)
for a short zero-to-first-run guide, concepts, configuration, and integration
guidance.
