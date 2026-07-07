# mcp_oauth_agent

An agent whose MCP tool is guarded by **ADK-native OAuth (OIDC)**. When the MCP
server rejects a `tools/call` with `401` until a bearer token is presented,
google-adk runs the OAuth flow for you: it emits an `adk_request_credential`
event with an authorize URL, the `veadk frontend` web UI shows an authorization
card, the user logs in, and ADK exchanges the code for a token and retries the
call with `Authorization: Bearer <token>`.

Only two `McpToolset` arguments turn this on:

```python
McpToolset(
    connection_params=StreamableHTTPConnectionParams(url=...),
    auth_scheme=OpenIdConnectWithConfig(authorization_endpoint=..., token_endpoint=..., scopes=[...]),
    auth_credential=AuthCredential(
        auth_type=AuthCredentialTypes.OPEN_ID_CONNECT,
        oauth2=OAuth2Auth(client_id=..., client_secret=..., redirect_uri=...),
    ),
)
```

## Setup

1. Register an OAuth client with your OIDC provider (e.g. a Volcengine user
   pool). Add your web UI's origin to its allowed redirect URIs so the popup can
   capture the callback on its own origin — `http://localhost:8000/` for a
   default `veadk frontend`, or `http://localhost:5173/` when running `--dev`.
2. Provide the settings via environment (a `.env` file next to your run works):

   ```dotenv
   MCP_OAUTH_URL=https://<your-mcp-server>/mcp
   OIDC_ISSUER=https://<your-user-pool>/           # authorize/token derived from this
   OIDC_CLIENT_ID=<client id>
   OIDC_CLIENT_SECRET=<client secret>
   OIDC_REDIRECT_URI=http://localhost:8000/       # http://localhost:5173/ with --dev
   # optional:
   # OIDC_SCOPES=openid profile email
   # OIDC_AUTHORIZATION_ENDPOINT=https://.../authorize
   # OIDC_TOKEN_ENDPOINT=https://.../oauth/token
   ```

   The issuer's endpoints can be read from
   `<issuer>/.well-known/openid-configuration`.

3. Serve it and open the UI (`http://localhost:8000/`):

   ```bash
   veadk frontend --agents-dir examples --port 8000
   ```

   Pick **mcp_oauth_agent**, ask something that needs a tool, and complete the
   authorization card when it appears. (Add `--dev` to develop the frontend from
   the Vite server on :5173 — then set `OIDC_REDIRECT_URI=http://localhost:5173/`.)

## Notes

- `client_secret` stays on the server that runs the agent; it is never sent to
  the browser. Sharing the running service is fine — each user logs in with
  their own account.
- The redirect URI must exactly match one registered on the OAuth client, or the
  provider returns `redirect_uri mismatch`.
