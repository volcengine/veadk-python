# piagent_runtime_basic

A minimal VeADK agent with `runtime="piagent"`.

This example is for local manual testing of Phase 1:

- local Pi binary starts successfully
- VeADK can send a text message through `Runner.run(...)`
- Pi uses the normal VeADK model config from `.env`, `config.yaml`, or
  environment variables such as `MODEL_AGENT_NAME` and `MODEL_AGENT_API_KEY`
- no ADK tools or skills are bridged in this phase

## Setup

Use a Pi binary that matches your local platform. On macOS arm64:

```bash
export PIAGENT_BINARY=/private/tmp/veadk-piagent-binary/v0.80.6-darwin/extracted/pi/pi
export PIAGENT_AGENT_DIR=/private/tmp/veadk-piagent-example-home
```

The model config is not duplicated in this example. It uses your existing
VeADK `.env` / `config.yaml` settings, including `MODEL_AGENT_NAME`,
`MODEL_AGENT_API_KEY`, and Volcengine AK/SK.

## Run

```bash
.venv/bin/python examples/piagent_runtime_basic/main.py "hello"
```

## Run in the VeADK frontend

Start the frontend from the repository root with `examples` as the agents
parent directory:

```bash
export PIAGENT_BINARY=/private/tmp/veadk-piagent-binary/v0.80.6-darwin/extracted/pi/pi
export PIAGENT_AGENT_DIR=/private/tmp/veadk-piagent-example-home

veadk frontend --agents-dir examples
```

Or, if your shell is already inside `examples/`:

```bash
export PIAGENT_BINARY=/private/tmp/veadk-piagent-binary/v0.80.6-darwin/extracted/pi/pi
export PIAGENT_AGENT_DIR=/private/tmp/veadk-piagent-example-home

veadk frontend --agents-dir .
```

Do not set `--agents-dir examples/piagent_runtime_basic`; `veadk frontend`
expects the parent folder of agent apps, not a single agent app folder.

## Deploy to AgentKit

This example includes `piagent-agentkit.yaml` and `Dockerfile` for AgentKit
deployment. The image build downloads the Linux x64 Pi standalone binary from GitHub
Release, verifies its sha256, extracts it to `/opt/piagent/pi/pi`, and sets:

```text
PIAGENT_BINARY=/opt/piagent/pi/pi
PIAGENT_AGENT_DIR=/tmp/veadk-piagent-home
```

So the deployed AgentKit runtime does not need extra `PIAGENT_*` runtime envs.
Model credentials are resolved by VeADK/AgentKit the same way as other deployed
VeADK agents; do not set `MODEL_AGENT_API_KEY` in AgentKit runtime envs.

Important: `requirements.txt` must install a VeADK build that already contains
the piagent runtime. Before the feature is released to PyPI, replace
`veadk-python` in `requirements.txt` with a pushed git branch or an internal
wheel URL for cloud testing.

From this directory:

```bash
veadk agentkit launch --config-file piagent-agentkit.yaml --platform linux/amd64
veadk agentkit status --config-file piagent-agentkit.yaml
veadk agentkit invoke --config-file piagent-agentkit.yaml "你好，你能做什么"
```

Inspect the generated Pi model config:

```bash
cat /private/tmp/veadk-piagent-example-home/models.json
```
