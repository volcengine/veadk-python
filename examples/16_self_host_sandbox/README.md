# 16. Self-Hosted Sandbox Agent Demo

This example runs the conversation and model loop in `veadk web`. Each new VeADK Web session creates exactly one remote Managed Session. Only VeADK-generated `agent.tool_use` events are sent to the Self-Hosted Runtime dispatcher, which creates a TAE Tool session for the configured Sandbox.

---

## 🎯 Architecture

```text
       [ User Prompt ]
              │
              ▼
   ┌───────────────────────┐
   │      VeADK Web        │
   │ model + agent loop    │
   └──────────┬────────────┘
              │ POST agent.tool_use
              ▼
   ┌───────────────────────────┐
   │ Runtime 7hw8g3yr          │
   │ dispatcher only           │
   └──────────┬────────────────┘
              │ creates one tool session
              ▼
   ┌────────────────────────────────────────┐
   │ TAE Sandbox Tool m3m24zxs              │
   │ executes the Runtime's tool calls      │
   └────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Configure Environment Variables

Copy the example environment configuration file and update it with your credentials:

```bash
cp examples/16_self_host_sandbox/.env.example examples/16_self_host_sandbox/.env
```

Alternatively, export variables directly:

```bash
export ANTHROPIC_BASE_URL="https://<runtime-gateway>"
export ANTHROPIC_ENVIRONMENT_ID="env_01SLqXHseguCmohifEqeUAYu"
export ANTHROPIC_ENVIRONMENT_KEY="your-runtime-token"
export SANDBOX_AGENT_ID="agent_your_managed_agent_id"
export X_TOP_ACCOUNT_ID="your-account-id"
```

The local VeADK process needs its normal model configuration. Model reasoning happens in VeADK; only tool execution is delegated to the remote Runtime and Sandbox.


### 2. Run the Demo

#### Option A: Web UI Mode (`veadk web`)

Run the visual web debugging interface in your browser (defaults to port **8067**, configurable via `PORT` in `.env` or `--port`):

```bash
# Via run.sh helper (automatically switches to agents dir and applies port 8067)
bash examples/16_self_host_sandbox/run.sh --web

# Or directly in the agents directory
cd examples/16_self_host_sandbox/agents
veadk web --port 8067
```




#### Option B: CLI Mode

```bash
# Run with run.sh helper
bash examples/16_self_host_sandbox/run.sh

# Or using uv
uv run --extra sandbox python examples/16_self_host_sandbox/main.py

# Or select an existing local-to-remote session mapping
python examples/16_self_host_sandbox/main.py \
  --session-id "my-local-session" \
  --prompt "Create a Python script in /workspace and run it with pytest."
```


`ShortTermMemory.after_create_session_callback` creates one remote Managed Session
for each newly created VeADK session. VeADK handles the user message and model
loop locally. `DispatchRuntimeProvider` intercepts each model tool call, posts an
`agent.tool_use`, waits for its matching tool result, and returns that result to
the local VeADK model loop.

## Docker and Kubernetes deployment

Use the repository root as the Docker build context:

```bash
docker build \
  -f examples/16_self_host_sandbox/Dockerfile \
  -t <registry>/veadk-self-host-sandbox:<tag> \
  .
docker push <registry>/veadk-self-host-sandbox:<tag>
```

Replace the image and Ingress host in `k8s.yaml` for the target environment. Then
create an allowlisted Secret from the local `.env` and deploy the workload:

```bash
set -a
source examples/16_self_host_sandbox/.env
set +a

kubectl create secret generic veadk-self-host-sandbox-env \
  --from-literal=ANTHROPIC_BASE_URL="$ANTHROPIC_BASE_URL" \
  --from-literal=ANTHROPIC_ENVIRONMENT_ID="$ANTHROPIC_ENVIRONMENT_ID" \
  --from-literal=ANTHROPIC_ENVIRONMENT_KEY="$ANTHROPIC_ENVIRONMENT_KEY" \
  --from-literal=SANDBOX_AGENT_ID="$SANDBOX_AGENT_ID" \
  --from-literal=X_TOP_ACCOUNT_ID="$X_TOP_ACCOUNT_ID" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f examples/16_self_host_sandbox/k8s.yaml
kubectl rollout status deployment/veadk-self-host-sandbox
```

Do not create the Secret from the entire `.env`. The Deployment only injects
the allowlisted Runtime connection values above.

## Development verification

The repository virtual environment may omit test dependencies when it was
created for runtime use only. Install the development dependency group before
running the focused dispatch tests:

```bash
uv sync --group dev --extra sandbox
uv run pytest -q tests/runtime/test_self_host_sandbox_client.py \
  tests/runtime/test_self_host_sandbox_agent.py
```
