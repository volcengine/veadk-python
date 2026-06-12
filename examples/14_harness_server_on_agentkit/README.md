# harness-server · Deploy the Harness server to Volcengine AgentKit

Deploy VeADK's **Harness server** (`veadk.cloud.harness_app`) to
[Volcengine AgentKit](https://www.volcengine.com/) and call it over HTTP, using
the `veadk harness` CLI — no app code to write and no local Docker.

> 中文版见 [README.zh.md](./README.zh.md)

A *harness* is an agent spec — **model + system prompt + tools + skills**, plus a
knowledge base and long/short-term memory bound at creation time. You describe it
in a layered `harness.yaml`; `deploy` flattens it into the runtime's environment
variables, and the server assembles the agent from them at startup and serves it
at `POST /harness/invoke`.

The flow is **`create` → `add` → `deploy` → `invoke`**. See the full CLI
reference in the docs (`docs/content/docs/cli/harness-cli`).

## 1. Scaffold

```bash
veadk harness create harness-server
cd harness-server
```

This writes `harness.yaml` (the agent config), `.env.example` (Volcengine deploy
credentials only), a `Dockerfile`, and a `README.md`.

## 2. Configure the agent

Set parameters into `harness.yaml` with `veadk harness add` (or edit the file):

```bash
veadk harness add \
  --name research-agent \
  --model-name doubao-seed-1-6-250615 \
  --system-prompt "You are a research assistant." \
  --tools web_search,web_fetch \
  --runtime adk
```

Built-in tool names come from `veadk.tools.list_builtin_tools()` (e.g.
`web_search`, `web_fetch`, `vesearch`, `link_reader`, `run_code`, `coding`,
`image_generate`, `image_edit`, `video_generate`, `text_to_speech`). On an
AgentKit runtime Ark auth is resolved by the runtime's IAM role, so the model
needs no API key — only its name. Review what's configured with:

```bash
veadk harness show
```

## 3. Deploy

```bash
cp .env.example .env   # then set VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY
veadk harness deploy
```

`deploy` runs an AgentKit **cloud** build (no local Docker) and creates a runtime
named after `harness_name`. On success the endpoint and gateway API key are
recorded into **`harness.json`** (`{name: {url, key, runtime_id}}`), so the next
step needs no manual URL/key copying.

> **Tip (CN build network):** if `pip`/`uv` is slow pulling dependencies, point
> the build at a domestic mirror, e.g.
> `UV_INDEX_URL=https://mirrors.volces.com/pypi/simple/`.

## 4. Invoke

```bash
veadk harness invoke --name research-agent \
  --message "Summarize the latest on reinforcement learning."
```

`url`/`key` are read from `harness.json` by `--name`; pass `--url` / `--key`
(or `HARNESS_URL` / `HARNESS_KEY`) to target a server explicitly.

### Once-time overrides

Passing any of `--model-name` / `--tools` / `--skills` / `--system-prompt` /
`--runtime` clones the deployed agent and applies the override **for that single
call only** (tools/skills are added incrementally; memory and the knowledge base
are never overridable):

```bash
veadk harness invoke --name research-agent \
  --tools get_city_weather \
  --message "What's the weather in Beijing today?"
```

## API

The server exposes a single endpoint:

- `POST /harness/invoke` — body
  `{prompt, harness_name, harness?, run_agent_request}`. Runs the deployed agent;
  a non-null `harness` is the once-time override for this call (response
  `overwrite: true`). `harness` fields: `model_name`, `system_prompt`, `tools`,
  `skills`, `runtime` (`tools`/`skills` are comma-separated strings).
  `run_agent_request` fields: `user_id`, `session_id`.

`curl` equivalent (gateway auth is `Authorization: Bearer <API_KEY>`):

```bash
curl -s -X POST "<ENDPOINT>/harness/invoke" \
  -H "Authorization: Bearer <API_KEY>" -H "Content-Type: application/json" \
  -d '{"prompt":"Hello","harness_name":"research-agent","run_agent_request":{"user_id":"u1","session_id":"s1"}}'
```

## Note on scaling

The short-term memory is held **in memory per instance**. If the runtime scales
to multiple instances, a session served by one instance is not visible to another.
To keep multi-turn sessions consistent, pin the runtime to a single instance
(`MinInstance = MaxInstance = 1`), or configure a shared `short_term_memory`
backend (e.g. `mysql` / `postgresql`) in `harness.yaml`.
