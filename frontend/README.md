# VeADK Web

A React web UI for VeADK / Google ADK agents. It talks to the standard ADK API
server that `veadk frontend` launches — no separate backend.

## Features

- **Streaming chat** over the ADK `/run_sse` event stream.
- **Markdown** rendering for user and assistant messages (GFM + code highlight).
- **Multimodal messages** with images, TXT/Markdown, PDF, and video attachments,
  including previews and history replay for both user and model media. Chat
  images use compact thumbnails and open in a zoomable full-screen viewer.
- **Composer invocations**: type `/` to select a mounted skill or `@` to route
  the turn to a mentionable sub-agent.
- **Reasoning & tool calls** shown inline (collapsible "thinking", tool blocks).
- **Sessions**: pick an agent, browse history, new chat, delete — per signed-in
  user. Long Agent lists stay within the viewport and scroll independently.
- **Tracing viewer**: a span tree + detail panel from the ADK debug trace.
- **Custom-agent workbench**: configure and debug an agent, then review
  generated source with line numbers and syntax highlighting before setting
  its region, message channel, network, environment variables, and deploying
  to AgentKit. A global task list keeps Runtime, region, and progress visible
  across page switches, follows the actual generated Runtime name, and supports
  cancellation or retry. Remote topology and trace requests use the selected
  Runtime endpoint.
- **Auth**: optional VeIdentity SSO, or a local username for dev.
- **Agent-driven UI (A2UI)**: when an agent emits A2UI, it renders as native
  components (one feature among the above — not required).

## Run

The build output ships inside the package at `veadk/webui` (committed), so
`veadk frontend` works for installed users with no build step. Run it from the
**parent folder of your agent directories** (like `adk web`) — every subdir with
an `agent.py` that exposes `root_agent` becomes a selectable app in the dropdown:

```bash
cd path/to/your/agents     # parent dir containing agent_a/, agent_b/, ...
veadk frontend             # serves UI + ADK API on http://127.0.0.1:8000
# or point elsewhere:  veadk frontend --agents-dir ./examples
```

Rebuild the UI from source after changing it:

```bash
cd frontend && npm install && npm run build   # -> veadk/webui
```

Dev loop with hot reload (Vite proxies the API):

```bash
veadk frontend --dev        # API only, CORS for the vite dev server
cd frontend && npm run dev  # http://localhost:5173
```

## Authentication

The ADK `user_id` (which scopes sessions/memory) comes from the signed-in user.

**SSO (VeIdentity OAuth2)** — enable with flags; the UI shows a login page and
redirects through VeIdentity, then uses the `sub` from `/oauth2/userinfo`:

```bash
veadk frontend \
  --oauth2-user-pool <name>      --oauth2-user-pool-client <name>
  # or by id (env: OAUTH2_USER_POOL_ID / OAUTH2_USER_POOL_CLIENT_ID):
  # --oauth2-user-pool-uid <id>  --oauth2-user-pool-client-uid <id>
```

Requires Volcengine credentials (AK/SK) in the environment. The login button's
label/icon is config-driven (`--oauth2-provider` / `--oauth2-provider-label`),
exposed at `GET /web/auth-config`.

**No SSO (local)** — without those flags, the login page asks for a username
(letters + digits, ≤16), stored locally and used as the `user_id`.

Login state is cached: SSO via the `veadk_session` cookie, local mode via
`localStorage`. The session itself is created lazily on the first message or
attachment upload.

## Multimodal media

The composer accepts PNG, JPEG, WebP, GIF, TXT, Markdown, PDF, MP4, WebM, and
QuickTime files. The default per-file limit is 20 MB. Files are uploaded as
binary form data; the browser does not put base64 payloads into chat events.

Media bytes live outside the ADK session store:

- Local mode stores `content` and `metadata.json` below
  `/tmp/veadk-media/apps/.../sessions/.../media/<media-id>/` by default.
- TOS mode stores the same two objects below
  `veadk-media/users/<encoded-username>/apps/<app>/sessions/<session>/media/<media-id>/`
  by default. The user-first prefix keeps each tenant's objects separate;
  username, app, and session segments are URL-encoded.
- Session events contain only a stable Google GenAI `FileData` reference such
  as `veadk-media://apps/.../media/<media-id>`, so history stays small and can
  load the original attachment later.

Immediately before a model call, TXT and Markdown are decoded into `Part.text`;
images and video are loaded from the selected backend into `Part.inline_data`,
and PDF pages are rendered to PNG images. PDF support and its rendering runtime
are included in the default VeADK installation. Model-returned `inline_data` is
persisted first and replaced with the same stable reference before the event is
saved or streamed. TOS uses a 15-minute signed URL only for browser delivery,
not as a model `FileData` URI.

For cloud AgentKit runtimes, media HTTP operations remain on the Studio server;
they are not sent to `/web/runtime-proxy/.../web/media`. The Studio proxy
resolves stored references into model-ready Parts only for `/run_sse` and keeps
the original `veadkMedia` metadata so history still renders the original
attachment. Both the default `/tmp` backend and TOS work without adding media
routes to the remote runtime.

| Environment variable | Default | Purpose |
| :-- | :-- | :-- |
| `VEADK_MEDIA_STORAGE` | `local` | Select `local` or `tos`. |
| `VEADK_MEDIA_LOCAL_DIR` | `/tmp/veadk-media` | Local media root. |
| `VEADK_MEDIA_MAX_FILE_BYTES` | `20971520` | Upload/model-output limit. |
| `VEADK_MEDIA_TOS_PREFIX` | `veadk-media` | TOS object-key prefix. |
| `DATABASE_TOS_BUCKET` | — | TOS bucket name. |
| `DATABASE_TOS_REGION` | cloud-aware | TOS region. |
| `DATABASE_TOS_ENDPOINT` | region-aware | TOS endpoint. |
| `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY` | — | TOS credentials. |
| `VOLCENGINE_SESSION_TOKEN` | — | Optional temporary credential token. |

Deleting a draft attachment deletes its object. Deleting a session deletes all
media scoped to that session from either backend. Because `/tmp` may be cleared
at any time, use TOS when attachments must survive process or host replacement.

## Skills and sub-agents

Type `/` in the composer to search skills mounted on the selected agent. Type
`@` to search any mentionable descendant in its sub-agent tree. Use the arrow
keys to move, Enter or Tab to select, and Escape to close the menu. A selected
item becomes a removable chip instead of remaining plain message text.

After selecting a sub-agent, the `/` menu shows that target's skills. Changing
or removing the target clears its selected skills, so a skill is never sent to
an agent that does not own it. Task and single-turn workflow nodes are shown in
the topology but cannot be selected with `@`.

Selections are sent as structured `veadkInvocation` metadata, not parsed from
the message string. The invocation plugin directs ADK to call the mounted skill
tool or transfer one tree edge at a time until it reaches the selected agent.
The same metadata is attached to the first Google GenAI `Part`, so session
history restores the `/skill` and `@agent` chips after a reload.

## How it works

- `adk/client.ts` calls `/list-apps`, creates a session, and streams `/run_sse`;
  events are normalised into ordered blocks (`blocks.ts`).
- `veadk.multimodal` validates uploads, abstracts local/TOS storage, resolves
  stable references for model calls, and persists model-returned media.
- `veadk.cli.frontend_invocation` exposes mounted skills and translates
  structured composer selections into ADK skill and transfer tool directives.
- `ui/` holds the chat shell: sidebar, composer, message blocks, trace drawer.
- `adk/identity.ts` resolves the user (SSO `userinfo` or local username).

## Agent-driven UI (A2UI)

When an agent emits [A2UI](https://a2ui.org) (declarative UI), the client renders
it natively. Each component lives in its own self-registering directory under
`src/a2ui/components/<Name>/`; unknown components fall back to a collapsible JSON
view, so a catalog/renderer mismatch never breaks the page. To add a component,
drop a folder there (frontend) and declare it in the agent's catalog (backend —
see `veadk.a2ui.BaseA2UICatalog`).
