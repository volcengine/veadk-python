# harness-server · Deploy the Harness server to Volcengine AgentKit

Deploy VeADK's **Harness server** (`veadk.cloud.harness_app`) to
[Volcengine AgentKit](https://www.volcengine.com/) and call it over HTTP.

A *harness* is a named agent spec — **model + system prompt + tools**. The
server lets you register harnesses at runtime (`/harness/add`) and invoke them
(`/harness/invoke`), with an optional once-time harness that overrides the
stored one for a single call.

The server is shipped inside the `veadk` package, so there is **no app code to
write** — the runtime just runs the module:

```bash
python -m veadk.cloud.harness_app   # serves the API on 0.0.0.0:8000
```

## What's in this directory

```text
14_harness_server_on_agentkit/
├── README.md          # this file
├── .env.example       # model + Volcengine credentials (placeholders)
└── requirements.txt   # veadk-python (installed into the image)
```

> `veadk agentkit config` / `launch` will generate `agentkit.yaml`, a
> `Dockerfile`, and a `.agentkit/` dir here — those are build artifacts and are
> gitignored, not part of the example.

## API

- `POST /harness/add` — body `{harness_name, harness}`. Register a harness;
  returns `code: 400` if the name already exists.
- `POST /harness/invoke` — body
  `{prompt, harness_name, harness?, run_agent_request}`. Run a **previously
  added** harness. A non-null `harness` overrides the stored one for this call
  (`overwrite: true`).

`harness` fields: `model_name`, `system_prompt`, and `tools`. `tools` accepts
either a list (`["web_search", "web_fetch"]`) or a comma-separated string
(`"web_search,web_fetch"`). `run_agent_request` fields: `user_id`, `session_id`.

Built-in tool names come from `veadk.tools.list_builtin_tools()` (e.g.
`web_search`, `web_fetch`, `vesearch`, `link_reader`, `run_code`, `coding`,
`image_generate`, `image_edit`, `video_generate`, `text_to_speech`).

## 1. Configure

```bash
cd examples/14_harness_server_on_agentkit
cp .env.example .env
# edit .env: MODEL_AGENT_API_KEY + VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY
```

The cloud function has no `.env`, so the model credentials are baked into the
runtime as env vars at config time:

```bash
veadk agentkit config \
  --agent_name harness-server \
  --entry_point veadk.cloud.harness_app.py \
  --language Python --language_version 3.12 \
  --launch_type cloud --region cn-beijing \
  --dependencies_file requirements.txt \
  -e MODEL_AGENT_PROVIDER="$MODEL_AGENT_PROVIDER" \
  -e MODEL_AGENT_NAME="$MODEL_AGENT_NAME" \
  -e MODEL_AGENT_API_BASE="$MODEL_AGENT_API_BASE" \
  -e MODEL_AGENT_API_KEY="$MODEL_AGENT_API_KEY"
```

`entry_point` is a dotted module path (the trailing `.py` is stripped), so
AgentKit runs the container with `python -m veadk.cloud.harness_app`.

> **Tip (CN build network):** if `pip`/`uv` is slow pulling dependencies, point
> the build at a domestic mirror, e.g. set a `PIP_INDEX_URL` /
> `UV_INDEX_URL=https://mirrors.volces.com/pypi/simple/` runtime/build env.

## 2. Run locally (optional)

```bash
python -m veadk.cloud.harness_app   # http://127.0.0.1:8000
```

## 3. Deploy

```bash
veadk agentkit launch   # builds the image and deploys; prints the endpoint URL
```

## 4. Test

Replace `<ENDPOINT>` with the URL printed by `launch` and `<API_KEY>` with the
runtime's gateway key (`veadk agentkit runtime get -r <runtime-id>` →
`AuthorizerConfiguration.KeyAuth.ApiKey`).

With the VeADK CLI:

```bash
veadk agentkit harness add \
  --name research-agent \
  --model-name doubao-seed-1-6-250615 \
  --system-prompt "You are a research assistant." \
  --tools web_search,web_fetch \
  --url "<ENDPOINT>" --key "<API_KEY>"

veadk agentkit harness invoke \
  --harness research-agent \
  --url "<ENDPOINT>" --key "<API_KEY>" \
  "Summarize the latest on reinforcement learning."
```

`--url` / `--key` can also be supplied via `HARNESS_URL` / `HARNESS_KEY`.

Or with `curl` (gateway auth is `Authorization: Bearer <API_KEY>`):

```bash
curl -s -X POST "<ENDPOINT>/harness/add" \
  -H "Authorization: Bearer <API_KEY>" -H "Content-Type: application/json" \
  -d '{"harness_name":"bot","harness":{"system_prompt":"Be concise."}}'

curl -s -X POST "<ENDPOINT>/harness/invoke" \
  -H "Authorization: Bearer <API_KEY>" -H "Content-Type: application/json" \
  -d '{"prompt":"Hello","harness_name":"bot","run_agent_request":{"user_id":"u1","session_id":"s1"}}'
```

## Note on scaling

The harness registry is held **in memory per instance**. If the runtime scales
to multiple instances, an `add` on one instance is not visible to an `invoke`
routed to another. For a registered-then-invoked workflow, pin the runtime to a
single instance (`MinInstance = MaxInstance = 1`), or externalize the registry
(DB / cache) to share state across instances.
