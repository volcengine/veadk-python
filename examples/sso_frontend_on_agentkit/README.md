# sso_frontend_on_agentkit · VeADK frontend with SSO on AgentKit

Deploy the VeADK web UI (A2UI) together with **VeIdentity single sign-on** to
a [Volcengine AgentKit](https://www.volcengine.com/) runtime. Unauthenticated
browsers see a login page; after sign-in the UI and backend agent run as the
logged-in user.

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

## 1. Prerequisites

- A VeIdentity user pool and one of its `WEB_APPLICATION` clients
  (<https://console.volcengine.com/veidentity>) — note both **UIDs**.
- A Volcengine Ark model API key and your account AK/SK.

```bash
cd examples/sso_frontend_on_agentkit
cp .env.example .env
# Fill: MODEL_AGENT_API_KEY, VOLCENGINE_ACCESS_KEY/SECRET_KEY,
#       OAUTH2_USER_POOL_ID, OAUTH2_USER_POOL_CLIENT_ID
set -a && source .env && set +a
```

## 2. Configure

Generate `agentkit.yaml` interactively (region, container registry, runtime
role, …):

```bash
veadk agentkit config
```

Then add these to `common.runtime_envs` in the generated `agentkit.yaml`
(leave `OAUTH2_REDIRECT_URI` until after the first deploy):

```yaml
    runtime_envs:
      MODEL_AGENT_PROVIDER: openai
      MODEL_AGENT_NAME: deepseek-v4-flash-260425
      MODEL_AGENT_API_BASE: https://ark.cn-beijing.volces.com/api/v3/
      MODEL_AGENT_API_KEY: <your-ark-api-key>
      OAUTH2_USER_POOL_ID: <your-user-pool-uid>
      OAUTH2_USER_POOL_CLIENT_ID: <your-user-pool-client-uid>
      VOLCENGINE_ACCESS_KEY: <your-ak>
      VOLCENGINE_SECRET_KEY: <your-sk>
      OTEL_SDK_DISABLED: 'true'
      VEADK_DISABLE_EXPIRE_AT: 'true'
```

## 3. Deploy

```bash
# Build the image and create the runtime; prints the endpoint and API key.
veadk agentkit launch
```

Set the callback to the printed endpoint and update the runtime once more:

```bash
# Add to runtime_envs in agentkit.yaml:
#   OAUTH2_REDIRECT_URI: https://<your-endpoint>/oauth2/callback
veadk agentkit deploy
```

The callback URL is registered with the user pool client automatically.

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

- **Model**: any Volcengine Ark chat model for `MODEL_AGENT_*`.
- **AK/SK**: used by `veadk agentkit` to build and deploy, and injected into the
  runtime so the app can call the VeIdentity API (resolve the pool, register the
  callback).
- **Redeploy**: after editing `runtime_envs`, re-run `veadk agentkit deploy`
  (image layers are reused). Tear down with `veadk agentkit destroy`.
