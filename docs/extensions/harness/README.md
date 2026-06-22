# VeADK Harness Extension

[中文](README.zh.md)

VeADK Harness is a lightweight extension for tool-using VeADK agents. It adds
runtime governance around the agent call path without changing your agent,
model, or tool implementations.

Use it when your agent handles large tool outputs, long-running multi-step
tasks, or final answers that must stay grounded in tool evidence.

## Install

```bash
pip install "veadk-python[harness]"
```

The Harness extension ships with VeADK. The `harness` extra installs optional
dependencies such as the in-process Headroom compaction provider. If you only
use the default `builtin` provider, no extra service is required.

## Quick Start

Attach Harness plugins when you create the `Runner`:

```python
from veadk import Agent, Runner
from veadk.extensions.harness.plugins import build_harness_plugins


agent = Agent(
    name="research_agent",
    instruction="Answer with evidence from tool results.",
)

runner = Runner(
    agent=agent,
    app_name="research_app",
    plugins=build_harness_plugins(
        components=[
            "invocation_context",
            "compactor",
            "response_verification",
        ],
    ),
)
```

Start with only compaction if you want the smallest measurable change:

```python
plugins = build_harness_plugins(components=["compactor"])
```

## Components

| Component | Plugin | What it adds |
| --- | --- | --- |
| `invocation_context` | `HarnessInvocationContextPlugin` | Injects task anchors, recent context, and tool-use guidance before model calls. |
| `compactor` | `HarnessCompressPlugin` | Compacts oversized tool results and old function responses. |
| `response_verification` | `HarnessResponseVerificationPlugin` | Records tool receipts and checks whether final answers are supported. |
| `long_run_control` | `HarnessLongRunControlPlugin` | Adds finish-oriented guidance when a run approaches its model-call budget. |

## Core Concepts

| Concept | Meaning |
| --- | --- |
| Harness module | Standalone capability that can be imported and tested directly. |
| Harness plugin | VeADK runtime wrapper that connects a module to lifecycle callbacks. |
| Invocation context block | Compact context injected before a model call. |
| Tool receipt | Short record of a tool call, its status, and useful evidence. |
| Compaction report | Metrics for how much context or tool output was reduced. |
| Verification report | Result showing whether the final answer is supported by evidence. |

## Source Layout

| Path | Purpose |
| --- | --- |
| `veadk/extensions/harness/extension.py` | Facade for creating Harness plugins from code. |
| `veadk/extensions/harness/env.py` | Builds plugins from environment variables. |
| `veadk/extensions/harness/schemas.py` | Public Pydantic models such as `ToolReceipt`, `CompactionReport`, and `VerificationReport`. |
| `veadk/extensions/harness/modules/invocation_context/` | Atomic invocation-context builder. |
| `veadk/extensions/harness/modules/tool_result_compactor/` | Atomic compactor plus builtin and Headroom providers. |
| `veadk/extensions/harness/modules/final_response_verifier/` | Atomic final-response verifier. |
| `veadk/extensions/harness/plugins/entrypoints.py` | Public plugin entry points. |
| `veadk/extensions/harness/plugins/builder/` | Shared-store plugin bundle assembly. |
| `veadk/extensions/harness/plugins/invocation_context/` | Invocation-context callback plugin. |
| `veadk/extensions/harness/plugins/compactor/` | Tool-result and context compaction callback plugin. |
| `veadk/extensions/harness/plugins/response_verification/` | Receipt recording and final-response verification callback plugin. |
| `veadk/extensions/harness/plugins/long_run_control/` | Long-run guidance callback plugin. |
| `veadk/extensions/harness/plugins/_shared/` | Internal callback helpers shared by plugins. |
| `veadk/extensions/harness/stores/` | Store protocol and in-memory or JSONL implementations. |

## Runtime Flow

```text
user message
  -> invocation_context builds and injects a compact context block
  -> model call
  -> tool call
  -> compactor reduces oversized tool output
  -> model continues with compacted evidence
  -> response_verification checks final answer support
  -> response is returned
```

The plugins share a store. The context plugin records messages, the compactor
writes compaction events, and the verifier reads tool receipts before adding
verification metadata or blocking unsupported answers when configured to do so.

## Use Atomic Modules

You can use modules directly without plugins. This is useful for unit tests,
custom runtimes, and focused integration checks.

```python
from veadk.extensions.harness import (
    HarnessInvocationContextBuilder,
    HarnessInvocationRef,
)


context = HarnessInvocationRef(session_id="session-1", invocation_id="run-1")
block = HarnessInvocationContextBuilder().prepare_context(
    context=context,
    user_input="Compare the tool results and explain the conclusion.",
)
print(block.header)
```

```python
from veadk.extensions.harness.modules.tool_result_compactor import ToolResultCompactor


tool_result = {
    "title": "Search results",
    "content": "important result\n" + ("raw text\n" * 2000),
}

compacted, report = ToolResultCompactor().compress_tool_result(tool_result)
print(compacted)
print(report.model_dump())
```

```python
from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifier,
)
from veadk.extensions.harness.schemas import ToolReceipt


receipts = [
    ToolReceipt(
        name="web_search",
        status="success",
        summary="The release date is 2026-05-01.",
    )
]

report = FinalResponseVerifier().verify_text(
    "The release date is 2026-05-01.",
    receipts=receipts,
)
print(report.model_dump())
```

## Runtime Configuration

Use environment variables for deployed runtimes:

```bash
export HARNESS_ENHANCE_ENABLED=true
export HARNESS_ENHANCE_COMPONENTS=invocation_context,compactor,response_verification
export HARNESS_COMPRESSION_PROVIDER=builtin
export HARNESS_VERIFIER_MODE=observe
```

Equivalent YAML:

```yaml
harness_enhance:
  enabled: true
  components: [invocation_context, compactor, response_verification]
  compression_provider: builtin
  verifier_mode: observe
```

Enable per request with the CLI:

```bash
veadk agentkit invoke \
  --harness my-agent \
  --endpoint "$HARNESS_URL" \
  --apikey "$HARNESS_KEY" \
  --enable-harness-enhance \
  --harness-components "invocation_context,compactor,response_verification" \
  "Summarize the tool results with evidence."
```

## Configuration Reference

| Setting | Default | Meaning |
| --- | --- | --- |
| `HARNESS_ENHANCE_ENABLED` | `false` | Enables Harness plugins for runtime assembly. |
| `HARNESS_ENHANCE_COMPONENTS` | `invocation_context,compactor,response_verification` | Selects enabled components. |
| `HARNESS_COMPRESSION_PROVIDER` | `builtin` | Compaction provider: `builtin` or `headroom`. |
| `HARNESS_MAX_CONTEXT_CHARS` | `24000` | Context compaction threshold. |
| `HARNESS_MAX_TOOL_RESULT_CHARS` | `4000` | Tool-result compaction threshold. |
| `HARNESS_VERIFIER_MODE` | `observe` | Verification behavior: `observe` or `block`. |
| `HARNESS_STORE_PATH` | unset | Uses a JSONL event store when set. |

## Compaction Providers

The default `builtin` provider is generic and dependency-free. It does not rely
on a task prompt, a tool name, or a business-specific output schema. For
JSON-like results, it walks mappings and sequences with bounded depth, keeps
representative facts, replaces very long scalar values with shape information,
records omitted counts, and applies basic redaction before writing summaries.

A compacted tool response includes a marker such as:

```json
{
  "harness_compressed": true,
  "provider": "builtin",
  "summary": "...",
  "original_chars": 8033
}
```

When `HARNESS_COMPRESSION_PROVIDER=headroom` is configured and the optional
dependency is installed, Harness lazy-loads Headroom through Python imports and
calls it in-process. It does not start a service. If Headroom is unavailable or
returns an invalid result, Harness falls back to the builtin provider.

## Recommended Defaults

| Setting | Suggested value | Reason |
| --- | --- | --- |
| `components` | `invocation_context,compactor,response_verification` | Balanced default for tool-heavy agents. |
| `compression_provider` | `builtin` | Stable and dependency-free. |
| `max_tool_result_chars` | `4000` | Compresses clearly large results while leaving small results untouched. |
| `max_context_chars` | `24000` | Preserves enough multi-step context while limiting prompt growth. |
| `verifier_mode` | `observe` | Lets you inspect verification reports before blocking answers. |

## Validate Impact

Start with these checks:

| Signal | What good looks like |
| --- | --- |
| Tool result compaction | Large tool responses include `harness_compressed: true` and `compressed_chars < original_chars`. |
| Prompt size reduction | Later model calls carry less raw tool context. |
| Answer support | Unsupported completion claims are detected in verification metadata. |
| Task quality | The final answer remains correct while latency or token usage improves for long-output tasks. |

## FAQ

### Do I need every component?

No. `compactor` is the easiest component to measure first. Add
`invocation_context` and `response_verification` when you need stronger context
control and answer grounding.

### Can compaction lose important details?

Compaction is designed to preserve structured facts, titles, links, numbers,
errors, and short summaries. For tasks that require exact original text, raise
the compaction thresholds or enable compaction only for selected use cases.

### Does verification block answers?

The default mode is `observe`, which records verification metadata without
blocking. Use `block` only after you have validated that the rules fit your
application.

### Does agent code need major changes?

Usually no. Add `plugins=build_harness_plugins(...)` when constructing the
`Runner`; your tools, model settings, and agent instructions can keep
their existing structure.
