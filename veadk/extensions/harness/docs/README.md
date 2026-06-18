# veADK Harness Extension Guide

[中文](README.zh.md)

This guide explains the SDK from zero to first run.

## Install

```bash
pip install "veadk-python[harness]"
```

The Harness extension is bundled with veADK. The `harness` extra installs the
optional in-process Headroom provider for `HARNESS_COMPRESSION_PROVIDER=headroom`.

## What It Does

veADK Harness Extension adds a small control layer around a veADK agent:

1. It prepares a compact context block before model calls.
2. It compacts oversized tool outputs before they pollute later turns.
3. It records tool receipts and checks whether final answers are supported.

Use it when your agent calls tools, handles long outputs, or needs stricter
answer grounding.

## Core Concepts

| Concept | Meaning |
| --- | --- |
| Harness module | A standalone capability that can be imported and tested directly. |
| Harness plugin | A veADK Runner plugin wrapper around one or more modules. |
| Invocation context block | A compact instruction/context block injected before model calls. |
| Tool receipt | A short record of what a tool did and whether it succeeded. |
| Compaction report | Metrics showing how much context or tool output was reduced. |
| Verification report | A result showing whether the final answer is supported. |

## First Run With Plugins

```python
from veadk.extensions.harness.adk import build_harness_plugins
from veadk import Agent, Runner

agent = Agent(name="demo_agent")
runner = Runner(
    agent=agent,
    app_name="demo",
    plugins=build_harness_plugins(
        components=["invocation_context", "compactor", "response_verification"],
    ),
)
```

## Use Individual Modules

```python
from veadk.extensions.harness import HarnessInvocationContextBuilder, HarnessInvocationRef

context = HarnessInvocationRef(session_id="s1", invocation_id="r1")
bundle = HarnessInvocationContextBuilder().prepare_context(
    context,
    user_input="Find the best model from the tool result.",
)
print(bundle.header)
```

```python
from veadk.extensions.harness.modules.tool_result_compactor import ToolResultCompactor

compactor = ToolResultCompactor()
compressed, report = compactor.compress_tool_result({"rows": "x" * 8000})
print(compressed)
print(report.model_dump())
```

## Configuration

Minimal runtime environment:

```text
HARNESS_ENHANCE_ENABLED=true
HARNESS_ENHANCE_COMPONENTS=invocation_context,compactor,response_verification
HARNESS_PROFILE=default
HARNESS_COMPRESSION_PROVIDER=builtin
```

Compaction provider options:

| Provider | Behavior |
| --- | --- |
| `builtin` | Default provider. Uses local structured compaction and safe fallback summaries. |
| `headroom` | Calls the installed local `headroom` Python package in-process. It does not start a service or install dependencies at runtime; if unavailable, it falls back to `builtin`. |

Verification defaults to observe behavior. Advanced hosts may configure block
behavior if they want unsupported final claims to stop the response.

## Evaluation

Run deterministic unit-style checks:

```bash
PYTHONPATH=. pytest -q tests/extensions/harness
```

Run the local HarnessApp latency/context benchmark:

```bash
PYTHONPATH=. python \
  veadk/extensions/harness/examples/harness_app_runtime/stable_latency_token_case.py \
  --repeats 3
```

The benchmark compares normal invocation with Harness-enhanced invocation and
prints latency, prompt-context size, compaction ratio, and answer consistency.
