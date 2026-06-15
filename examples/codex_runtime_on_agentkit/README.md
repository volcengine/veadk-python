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
├── scripts/install_veadk.sh     # installs veadk (from main) + openai-codex
├── requirements.txt             # empty (deps installed by the build script)
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
- **`openai-codex` is not a veadk dependency**, so the build installs it
  explicitly (`scripts/install_veadk.sh`). It pulls in `openai-codex-cli-bin`,
  which ships the Codex CLI binary as a **manylinux wheel** — no separate
  binary install is needed in the Linux build.

> The codex runtime fixes live on `main`, so the build installs veadk from
> `main` (not PyPI) via a shallow + sparse clone of the `veadk/` package.

## 1. Configure

```bash
cd examples/codex_runtime_on_agentkit
cp .env.example .env
# edit .env: MODEL_AGENT_API_KEY + VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY
```

## 2. Run locally (optional)

```bash
pip install "veadk-python" openai-codex
python app.py            # or: python -m app
# open http://127.0.0.1:8000 ; POST /run_sse, or GET /ping -> {"status":"ok"}
```

`/list-apps` returns `["codex_agent"]`. The first turn is slightly slower while
the bundled Codex binary spawns.

## 3. Deploy to AgentKit

```bash
# fill in account-specific fields in agentkit.yaml (interactive)
veadk agentkit config

# build the image and deploy in one step
veadk agentkit launch

# check status / send a test request once it's live
veadk agentkit status
veadk agentkit invoke "你好，你叫什么"
```

`veadk agentkit launch` = `build` + `deploy`. Use `veadk agentkit destroy` to
tear the runtime down. `scripts/install_veadk.sh` is wired via
`docker_build.build_script` in `agentkit.yaml` and runs during the image build.

## Notes

- **Model**: the model in `MODEL_AGENT_*` is bridged to Codex; it does not need
  to be an OpenAI model — a Volcengine Ark chat model works.
- **Tools / sandbox**: Codex runs tool calls (e.g. shell) in its own sandbox
  inside the container. For tool-heavy agents that need filesystem/network
  access, the runtime may need to be granted the corresponding permissions.
- **First request latency**: the Codex app-server binary is spawned on first
  use, so the first turn is slower than subsequent ones.
