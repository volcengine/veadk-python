# codex_runtime_on_agentkit · Deploy a `runtime="codex"` agent to AgentKit

A minimal deployable app whose agent runs on the **OpenAI Codex runtime**
(`Agent(runtime="codex")`) instead of ADK's built-in LLM flow, deployed to
[Volcengine AgentKit](https://www.volcengine.com/) with `veadk agentkit launch`.

> 中文版见 [README.zh.md](./README.zh.md)

> **What this example is:** a **deployment reference**. It shows how to package
> and ship a `runtime="codex"` agent to AgentKit — the requirements pins, the
> bundled Codex binary, the `agentkit config` flags. The agent itself is a
> placeholder, and its one-shot Q&A is not a use case this runtime is good at:
> `runtime="adk"` answers that kind of question faster and cheaper. For what the
> runtime is actually *for*, see [`codex_data_analysis/`](../codex_data_analysis/)
> (a model that writes a script, runs it, reads the traceback and fixes it) and
> [`codex_ops_assistant/`](../codex_ops_assistant/) (the same loop over logs and
> metrics, under a no-network sandbox), or
> [when to use the codex runtime](../../docs/content/docs/framework/agent/runtime.en.mdx#when-to-use-the-codex-runtime).

## What's inside

```text
codex_runtime_on_agentkit/
├── app.py                       # deploy entry point (ADK agent API server)
├── agents/
│   └── codex_agent/             # the agent — Agent(runtime="codex")
├── requirements.txt             # veadk-python + openai-codex + fastapi/uvicorn
├── .env.example
└── .dockerignore
```

## How the codex runtime works here

- `agents/codex_agent` is a normal VeADK `Agent` with `runtime="codex"`. The
  `Runner` still owns session, memory and tracing; Codex only drives the inner
  turn (reasoning + tool calls).
- Codex speaks the OpenAI **Responses** API, so VeADK stands up an in-process
  shim that bridges your `MODEL_AGENT_*` chat endpoint (Volcengine Ark) to it.
  A normal Ark chat model therefore works unchanged.
- **`openai-codex` is not a veadk dependency**, so `requirements.txt` lists it
  explicitly. It pulls in `openai-codex-cli-bin`, which ships the Codex CLI
  binary as a **manylinux wheel** — no separate binary install in the Linux
  build. These pins mirror veadk-python's `[codex]` extra; the extra is not
  used directly because uv only accepts a pre-release when its exact version is
  pinned at the top level, not transitively through an extra.
- `fastapi` and `uvicorn` are listed too: `app.py` imports `uvicorn` directly
  and the runtime's Responses→chat shim imports both at module level. They
  resolve through google-adk today, but adk has been moving web deps behind
  extras, so `[codex]` declares them explicitly and so does this file.

> The codex runtime is included in `veadk-python` since **0.5.39** (on PyPI), so
> the image installs everything from PyPI via the default
> `uv pip install -r requirements.txt` — no build script or git clone needed.

## 1. Configure

```bash
cd examples/codex_runtime_on_agentkit
cp .env.example .env
# edit .env: MODEL_AGENT_API_KEY + VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY
```

## 2. Run locally (optional)

```bash
pip install "veadk-python[codex]"   # openai-codex + the bundled Codex CLI binary
python app.py            # or: python -m app
# open http://127.0.0.1:8000 ; POST /run_sse, or GET /ping -> {"status":"ok"}
```

`/list-apps` returns `["codex_agent"]`. The first turn is slightly slower while
the bundled Codex binary spawns.

## 3. Deploy to AgentKit

`agentkit config` writes `agentkit.yaml`; `agentkit launch` then builds and
deploys from it. The model config (`MODEL_AGENT_*`) is read from the `.env`
from step 1, which is bundled into the image, so it need not go in
`--runtime_envs`. A minimal config:

```bash
veadk agentkit config \
  --agent_name codex-runtime-demo --entry_point app.py \
  --language Python --language_version 3.12 \
  --launch_type cloud --region cn-beijing \
  --tos_bucket Auto \
  --runtime_name codex-runtime-demo --runtime_apikey_name Auto \
  --runtime_envs OTEL_SDK_DISABLED=true

veadk agentkit launch                       # build + deploy in one step
veadk agentkit status                       # wait until Ready
veadk agentkit invoke "你好，你叫什么"      # test it
```

**Required** — set these:

- `--agent_name`, `--entry_point app.py`, `--launch_type cloud`, `--region`.
- `--language` / `--language_version`.
- `--tos_bucket Auto` — without `Auto`, the upload fails the bucket-ownership
  (`ListBuckets`) check unless your AK/SK has `tos:ListBuckets`.
- `--runtime_name` / `--runtime_apikey_name Auto`.

**Optional** — omit and AgentKit handles it:

- `--runtime_role_name` — auto-selected/created if omitted.
- `MODEL_AGENT_*` — read from the bundled `.env`, so not needed in
  `--runtime_envs` (`OTEL_SDK_DISABLED=true` is worth passing to silence OTel).
- Auth type — defaults to **API Key**; `custom_jwt` also needs a JWT discovery
  URL and client IDs.

`veadk agentkit launch` = `build` + `deploy`. Use `veadk agentkit destroy` to
tear the runtime down.

## Notes

- **Model**: the model in `MODEL_AGENT_*` is bridged to Codex; it does not need
  to be an OpenAI model — a Volcengine Ark chat model works.
- **Tools / sandbox**: Codex runs tool calls (e.g. shell) in its own sandbox
  inside the container. The defaults are the safe ones — `workspace_write`,
  `network_access=False`, and `approval_mode="deny_all"`, which refuses every
  escalation. To let the agent reach the network, set
  `CodexRuntimeConfig(sandbox="workspace_write", network_access=True)`; see the
  [runtime docs](../../docs/content/docs/framework/agent/runtime.en.mdx).
  Do **not** reach for `approval_mode="auto_review"` — it is not a review gate,
  it auto-approves every escalation.
- **Runtime env vars override the Python config**: `VEADK_CODEX_SANDBOX`,
  `VEADK_CODEX_APPROVAL_MODE`, `VEADK_CODEX_WORKSPACE_ROOT` and
  `VEADK_CODEX_NETWORK_ACCESS` take precedence over `CodexRuntimeConfig`, so be
  careful about what you pass to `--runtime_envs`.
- **First request latency**: the Codex app-server binary is spawned on first
  use, so the first turn is slower than subsequent ones.
- **Build time**: installing veadk + openai-codex from PyPI can take several
  minutes; if the CLI's build wait expires, re-running `veadk agentkit launch`
  reuses the cached image layers and finishes quickly.
