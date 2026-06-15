# sso_frontend_on_agentkit · VeADK frontend with SSO on AgentKit

Deploy the VeADK web UI (A2UI) together with **VeIdentity single sign-on** to
a [Volcengine AgentKit](https://www.volcengine.com/) runtime. Unauthenticated
browsers see a login page; after sign-in the UI and backend agent run as the
logged-in user. Fully non-interactive — copy the commands to deploy.

> 中文版：[README.zh.md](./README.zh.md)

## Layout

```text
sso_frontend_on_agentkit/
├── app.py                      # entry: web UI + agent API + SSO
├── agents/
│   └── sso_demo_agent/         # a minimal agent
├── requirements.txt            # veadk-python>=0.5.39
├── .env.example
└── .dockerignore
```

## How it works

The UI, agent API, VeIdentity OAuth2 middleware and bundled web UI all come
from `veadk-python` on PyPI. SSO is configured entirely through runtime
environment variables — no code changes.

`app.py` adds two adaptations for the AgentKit gateway, which authenticates
every request with the runtime key in the `Authorization: Bearer <key>` header
and forwards that header to the container:

- **Strip the gateway key**: the SSO middleware treats any `Authorization`
  header as the user's access token and tries to decode it as a JWT — the
  opaque gateway key fails with `Invalid JWT format`. `app.py` removes that
  non-JWT header before the middleware runs, so SSO falls back to its session
  cookie. A real user JWT is kept.
- **Forward the querystring onto assets**: if the gateway is configured to take
  the key from the query string, the served `index.html` appends the page's
  querystring to its `/assets/*` URLs so subresource requests carry it too.

> Both adaptations are built into `veadk frontend` from the next release; this
> example self-contains them so it runs on the current release.

## 1. Prerequisites

- A VeIdentity user pool and one of its `WEB_APPLICATION` clients
  (<https://console.volcengine.com/veidentity>) — note both **UIDs**.
- Your account AK/SK, for the local `veadk agentkit` build & deploy. The model
  and runtime credentials are provided by the AgentKit runtime — nothing to set.

```bash
cd examples/sso_frontend_on_agentkit
cp .env.example .env
# Edit .env:
#   VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY   (local deploy auth)
#   OAUTH2_USER_POOL_ID / OAUTH2_USER_POOL_CLIENT_ID  (pool & client UIDs)
set -a && source .env && set +a
```

## 2. Configure (non-interactive)

Account-specific fields (container registry, runtime role, …) are auto-created
when omitted. The runtime only needs the two UIDs — the model and access
credentials are provided by the runtime, so they are not in `--runtime_envs`:

```bash
veadk agentkit config \
  --agent_name sso-frontend-demo \
  --entry_point app.py \
  --language Python --language_version 3.12 \
  --launch_type cloud --region cn-beijing \
  --runtime_name sso-frontend-demo \
  --runtime_auth_type key_auth \
  --runtime_envs OAUTH2_USER_POOL_ID="$OAUTH2_USER_POOL_ID" \
  --runtime_envs OAUTH2_USER_POOL_CLIENT_ID="$OAUTH2_USER_POOL_CLIENT_ID" \
  --runtime_envs OTEL_SDK_DISABLED=true \
  --runtime_envs VEADK_DISABLE_EXPIRE_AT=true
```

## 3. Deploy

```bash
# Build the image and create the runtime; prints the endpoint and API key.
veadk agentkit launch
```

Set the callback to the printed endpoint (merged into the existing
`runtime_envs`) and update the runtime once more:

```bash
veadk agentkit config \
  --runtime_envs OAUTH2_REDIRECT_URI=https://<your-endpoint>/oauth2/callback
veadk agentkit deploy
```

Locally the callback defaults to `http://127.0.0.1:8000/oauth2/callback`, so no
env var is needed; once deployed the browser hits the public endpoint, which is
only known after the runtime is created — hence this separate step. The callback
is registered with the user pool client automatically.

## 4. Access

The AgentKit gateway requires the runtime key on every request, and the runtime
key currently only supports the header location (`CreateRuntime`'s
`ApiKeyLocation` accepts only `header`). A browser's top-level navigation cannot
set a header, so use a browser extension (e.g. ModHeader) to add, for this
domain, globally:

```text
Authorization: Bearer <your-runtime-key>
```

Then open the endpoint: the UI loads → redirects to VeIdentity login → callback
(the extension adds the header to pass the gateway) → the session lives in a
cookie and the UI and agent API work.

## Notes

- **Model**: provided by the AgentKit runtime; to pin one, add
  `--runtime_envs MODEL_AGENT_NAME=... --runtime_envs MODEL_AGENT_API_KEY=...`.
- **AK/SK**: used only by the local `veadk agentkit` build & deploy; on the
  runtime the VeIdentity API calls (resolve the pool, register the callback) use
  the runtime's service-role credentials, so AK/SK are not injected.
- **Redeploy**: after changing an env var, merge it with
  `veadk agentkit config --runtime_envs K=V` and re-run `veadk agentkit deploy`
  (image layers are reused). Tear down with `veadk agentkit destroy`.
