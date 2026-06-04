# front_with_sso

Try `veadk frontend` with an SSO login page, where the OAuth2 provider is
configured **entirely via environment variables** — no VeIdentity user pool
needed. Works with GitHub, Google, any OIDC provider, or a fully custom one.

When SSO is enabled, an unauthenticated browser sees a login page; after signing
in, the signed-in identity becomes the ADK `user_id`.

## How provider resolution works

`veadk frontend` picks the SSO backend like this:

1. If a VeIdentity user pool is configured (`--oauth2-user-pool*`), it uses that.
2. Otherwise, if `OAUTH2_CLIENT_ID` is set, it builds a **generic** provider from
   env vars (this example).
3. Otherwise, no SSO (local username mode).

Endpoints for the generic provider come from, in order:

- a built-in **preset** (`OAUTH2_PROVIDER=github` or `google`), or
- **OIDC discovery** when `OAUTH2_ISSUER` is set (`<issuer>/.well-known/openid-configuration`), or
- **explicit** `OAUTH2_AUTHORIZE_URL` / `OAUTH2_TOKEN_URL` / `OAUTH2_USERINFO_URL`.

## Environment variables

| Variable | Purpose |
|---|---|
| `OAUTH2_PROVIDER` | Provider id: `github`, `google`, or a custom name. Drives the login button label and the preset. |
| `OAUTH2_CLIENT_ID` | OAuth2 client id. **Setting this enables the generic provider.** |
| `OAUTH2_CLIENT_SECRET` | OAuth2 client secret. |
| `OAUTH2_ISSUER` | OIDC issuer base URL (endpoints auto-discovered). e.g. `https://accounts.google.com`. |
| `OAUTH2_AUTHORIZE_URL` / `OAUTH2_TOKEN_URL` / `OAUTH2_USERINFO_URL` | Explicit endpoints (for non-OIDC providers). |
| `OAUTH2_SCOPE` | Override the requested scopes. |
| `OAUTH2_PROVIDER_LABEL` | Override the login button text. |
| `OAUTH2_REDIRECT_URI` | **Callback URL.** Set this when deploying behind a public host/runtime; otherwise it defaults to `http://{host}:{port}/oauth2/callback`. The value must be registered as an authorized callback in your OAuth app. |

## Run

GitHub (preset — only id/secret needed):

```bash
export OAUTH2_PROVIDER=github
export OAUTH2_CLIENT_ID=<your-github-oauth-client-id>
export OAUTH2_CLIENT_SECRET=<your-github-oauth-client-secret>
# GitHub OAuth app "Authorization callback URL" must equal this:
export OAUTH2_REDIRECT_URI=http://127.0.0.1:8000/oauth2/callback

# run from the parent folder so this example is a selectable agent
veadk frontend --agents-dir examples
# open http://127.0.0.1:8000 -> "使用 GitHub 登录"
```

Google (OIDC preset):

```bash
export OAUTH2_PROVIDER=google
export OAUTH2_CLIENT_ID=<...>.apps.googleusercontent.com
export OAUTH2_CLIENT_SECRET=<...>
export OAUTH2_REDIRECT_URI=http://127.0.0.1:8000/oauth2/callback
veadk frontend --agents-dir examples
```

Any OIDC provider (Keycloak / Auth0 / Okta / …) via discovery:

```bash
export OAUTH2_PROVIDER=mycorp
export OAUTH2_PROVIDER_LABEL="MyCorp SSO"
export OAUTH2_ISSUER=https://id.mycorp.com          # /.well-known/openid-configuration
export OAUTH2_CLIENT_ID=<...>
export OAUTH2_CLIENT_SECRET=<...>
export OAUTH2_REDIRECT_URI=https://chat.mycorp.com/oauth2/callback
veadk frontend --host 0.0.0.0 --port 8000
```

A convenience launcher with the GitHub variables wired up:

```bash
bash examples/front_with_sso/run.sh
```

## Deploying behind a public host / runtime

The OAuth callback must come back to a URL the IdP knows. Locally that is
`http://127.0.0.1:8000/oauth2/callback`, but on a runtime the public host
differs — set `OAUTH2_REDIRECT_URI` to the public callback URL and register the
same value in your OAuth app. The launcher also derives the post-login/logout
origin and the cookie `Secure` flag from this URL (HTTPS → Secure cookies).
