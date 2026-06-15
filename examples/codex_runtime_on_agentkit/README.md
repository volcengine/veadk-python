# codex_runtime_on_agentkit · Deploy a `runtime="codex"` agent to AgentKit

A minimal deployable app whose agent runs on the **OpenAI Codex runtime**
(`Agent(runtime="codex")`) instead of ADK's built-in LLM flow, deployed to
[Volcengine AgentKit](https://www.volcengine.com/) with `veadk agentkit launch`.

> 中文版见 [README.zh.md](./README.zh.md)

## What's inside

```text
codex_runtime_on_agentkit/
├── app.py                       # deploy entry point (ADK agent API server)
├── agents/
│   └── codex_agent/             # the agent — Agent(runtime="codex")
├── requirements.txt             # veadk-python>=0.5.39 + openai-codex
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
  build.

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
pip install "veadk-python>=0.5.39" openai-codex
python app.py            # or: python -m app
# open http://127.0.0.1:8000 ; POST /run_sse, or GET /ping -> {"status":"ok"}
```

`/list-apps` returns `["codex_agent"]`. The first turn is slightly slower while
the bundled Codex binary spawns.

## 3. Deploy to AgentKit

`agentkit config` writes `agentkit.yaml`; `agentkit launch` then builds and
deploys from it. The fastest, mistake-proof path is to configure
**non-interactively** (fill in the three `<...>` placeholders):

```bash
veadk agentkit config \
  --agent_name codex-runtime-demo --entry_point app.py \
  --language Python --language_version 3.12 \
  --launch_type cloud --region cn-beijing \
  --tos_bucket Auto \
  --runtime_name codex-runtime-demo --runtime_apikey_name Auto \
  --runtime_role_name <your-AgentKit-runtime-service-role> \
  --runtime_envs MODEL_AGENT_PROVIDER=openai \
  --runtime_envs MODEL_AGENT_NAME=<your-model> \
  --runtime_envs MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3/\
  --runtime_envs MODEL_AGENT_API_KEY=<your-ark-api-key> \
  --runtime_envs OTEL_SDK_DISABLED=true

veadk agentkit launch                       # build + deploy in one step
veadk agentkit status                       # wait until Ready
veadk agentkit invoke "你好，你叫什么"      # test it
```

The fields split into **required** and **optional** (these are the same
things the interactive `agentkit config` wizard asks for):

**Required** — you must set these:

- `--agent_name`, `--entry_point app.py`, `--launch_type cloud`, `--region`.
- `--tos_bucket Auto` — without `Auto`, the upload fails the bucket-ownership
  (`ListBuckets`) check unless your AK/SK has `tos:ListBuckets`.
- `--runtime_role_name` — your account's AgentKit runtime service role.
- `--runtime_envs` for `MODEL_AGENT_NAME`, `MODEL_AGENT_API_BASE`,
  `MODEL_AGENT_API_KEY` — the codex runtime can't start a turn without the
  model's base URL + key.

**Optional** — sensible defaults if omitted:

- `--language` / `--language_version` — default to Python 3.12.
- `--runtime_name` / `--runtime_apikey_name Auto` — auto-generated if omitted.
- Auth type — defaults to **API Key**; `custom_jwt` also needs a JWT discovery
  URL and client IDs.
- `--runtime_envs MODEL_AGENT_PROVIDER=openai` (defaults to `openai`) and
  `OTEL_SDK_DISABLED=true` (recommended — silences OTel connection errors).

`veadk agentkit launch` = `build` + `deploy`. Use `veadk agentkit destroy` to
tear the runtime down.

## Notes

- **Model**: the model in `MODEL_AGENT_*` is bridged to Codex; it does not need
  to be an OpenAI model — a Volcengine Ark chat model works.
- **Tools / sandbox**: Codex runs tool calls (e.g. shell) in its own sandbox
  inside the container. For tool-heavy agents that need filesystem/network
  access, the runtime may need to be granted the corresponding permissions.
- **First request latency**: the Codex app-server binary is spawned on first
  use, so the first turn is slower than subsequent ones.
- **Build time**: installing veadk + openai-codex from PyPI can take several
  minutes; if the CLI's build wait expires, re-running `veadk agentkit launch`
  reuses the cached image layers and finishes quickly.
