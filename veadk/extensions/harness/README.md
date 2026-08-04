# VeADK Harness Extension

[中文](README.zh.md)

`veadk.extensions.harness` is a lightweight Harness extension for VeADK applications. It adds three reusable capabilities:

- context preparation for each agent turn
- tool-result compaction
- answer verification and hallucination suppression

The extension can be used directly as Python modules or attached to a VeADK
Runner. It does not require a separate runtime service.

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
