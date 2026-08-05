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
  the turn to a mentionable sub-agent. New conversations address the selected
  Agent by its display name in the composer placeholder.
- **New-chat modes**: keep the existing Agent conversation path, start a
  temporary Codex conversation in an AgentKit Sandbox, or create a Skill with
  a real two-model A/B run in independent AgentKit CodeEnv sessions. Skill
  progress resumes from Sandbox state if the creation stream is interrupted;
  completed candidates can be compared, downloaded as ZIP files, and added to
  AgentKit. Connected Harness agents expose supported image, video, and
  presentation task types; Studio mounts only missing task tools for the
  current session and preserves tools already supplied by the Agent.
- **Reasoning & tool calls** shown inline (collapsible "thinking", tool blocks).
- **Agent context rail** keeps the selected Agent's description, model, tools,
  skills, and optional live multi-Agent topology together in the conversation's
  right workspace, with the transcript protected from overlap on narrower screens.
- **Built-in tool activity** gives web search, image/video generation, memory,
  and knowledge-base retrieval their own repository-drawn icons and concise
  Chinese running/completed labels. Active work uses the shared Prompt Kit-style
  `TextShimmer`, which also powers thinking and branded heading shimmer states.
- **Sessions**: pick an agent, browse history, new chat, delete — per signed-in
  user. The new-session composer stays minimal until a conversation begins,
  when its session metadata appears. The page header follows the active session's
  first user message, while long titles truncate without shifting header actions.
  Session IDs use normal text with a copy action, and sidebar title tooltips show
  the full conversation name. Long Agent lists stay within the viewport and
  scroll independently.
- **Sandbox Agents**: create and reopen user-owned Codex, OpenClaw, and Hermes
  AgentKit Sessions from the Agent page. Each type supports list, detail, and
  explicit deletion. Codex streams reasoning, tool activity, and replies into
  the normal conversation renderer; leaving the conversation only disconnects
  it, so the Agent remains available until the user deletes it. OpenClaw and
  Hermes expose their main interface and Terminal through Studio.
- **AgentKit Skill center**: browse Skill Spaces and their skills with
  server-side pagination by region, then inspect the selected Skill content.
- **Automation directory**: browse development and message-channel integrations
  from the Studio sidebar. The local Coding Agents integration detects Trae,
  Claude Code, and Codex across macOS, Linux, and Windows, then globally installs
  the bundled VeADK development and AgentKit platform-operation Skills. The
  browser can select only fixed client and Skill identifiers; arbitrary shell
  commands, filesystem targets, and Skill content are never accepted. GitHub-backed
  automations can add a basic AgentKit
  project, configure Runtime continuous delivery, or add automatic Pull Request
  review. The browser creates GitHub branches, files, and Pull Requests directly;
  repository tokens stay in the current form state and are never persisted. The
  Feishu automation accepts an App ID and App Secret, generates a basic
  Studio-compatible agent, creates a new single-instance AgentKit Runtime, and
  enables the Feishu channel. The Feishu App Secret is used only for the current
  deployment and never enters generated source, workflow, documentation, or
  logs; cloud credentials remain GitHub Secrets or Runtime environment variables.
- **Tracing viewer**: a span tree + detail panel from the ADK debug trace.
- **Message feedback**: rate persisted Runtime replies with accessible,
  repository-drawn like/dislike controls. Studio identifies the final ADK Event,
  stores the latest rating through the existing Session state-delta API, and
  idempotently syncs the server-derived question and answer to per-Agent
  `{agent_name}_good_case` or `{agent_name}_bad_case` AgentKit evaluation sets.
  Studio creates regular evaluation sets and confirms they are list-visible
  before writing feedback items.
  Runtime credentials and Volcengine credentials remain server-side.
- **Smart search**: search sessions, the network through `web_search`, and a
  selected Agent's KnowledgeBase or long-term memory when mounted. The source
  picker follows live Agent metadata and disables unavailable sources before a
  search; active retrieval sources show their index/name and backend separately.
- **Runtime management**: inspect or delete deployed runtimes, or connect one
  directly so the global Agent selector switches to that Runtime. The cloud
  selector gives each two-line Runtime row explicit connect and info actions;
  the info action opens a tabbed Agent/Runtime panel. The Agent directory loads
  one selected region at a time, defaults to Beijing, and carries the Runtime's
  region through details, connection, update, evaluation, and deletion. Studio
  enables in-place updates for any authorized single-Agent Runtime that exposes
  compatible `list-apps` and `web/agent-info` endpoints, regardless of whether
  Studio originally deployed it; multi-Agent Runtimes are rejected because an
  AgentKit update replaces the whole Runtime package. Studio distinguishes its
  own ownership checks from Agent Server compatibility and authentication
  failures when a connection cannot be established. Each Agent detail page also
  probes and lists confirmed API Server and A2A integration endpoints; protocols
  that the Runtime does not expose are shown as unavailable. The integration
  panel switches between the detected protocols and provides a Python request
  example for each one. Runtime API Keys stay masked as `****` and are fetched
  only after the user explicitly reveals them; examples always use placeholders
  instead of credentials. Long descriptions, names, component summaries, IDs,
  and environment values stay inside the scrollable panel.
- **Custom-agent workbench**: configure an agent with a rich Markdown
  system-prompt editor (including heading and list shortcuts), then debug with
  expandable, copyable runner error details, per-result Trace inspection, and
  review. In-progress drafts are stored only in the current browser and scoped
  to the signed-in user. MCP tokens are converted to Runtime environment
  variables: generated source retains only the `${ENV_NAME}` reference, while
  YAML and browser drafts preserve the corresponding environment value.
  Runtime updates reload existing values, and the deployment form keeps all
  environment values visible to users who can view the Agent. Entering a
  replacement Token overrides the previous value. Long descriptions and prompts
  scroll within bounded editors, while the sidebar stays pinned to the
  viewport. On narrow desktop windows, the structure, configuration, and debug
  panels stack vertically instead of squeezing the form. The deployment page
  pairs an inspectable Agent topology with a vertically aligned action rail for
  YAML export, source download, and the code browser/editor dialog, while keeping
  region, access authentication, message channel, network, and environment
  settings primary. New Runtime deployments default to API Key authentication
  and can instead select an Identity user pool loaded by the Studio server. The
  current Studio pool is marked in the picker; selecting it lets Studio forward
  the validated login JWT to the Runtime, while other pools require a JWT issued
  by that pool. Runtime updates keep their existing authentication mode. Local
  skills accept a dropped
  folder or ZIP and detect the format automatically. Component forms omit
  credentials that VeADK can resolve automatically, while the Studio server
  forwards its Volcengine credentials to debug runs and deployed runtimes. A
  global task list keeps Runtime, region, and progress
  visible across page switches, follows the actual generated Runtime name, and
  supports cancellation or retry. Remote topology and trace requests use the selected
  Runtime endpoint. The Remote Agent type is available only for child Agents;
  its generated internal proxy mounts AgentKit A2A center agents dynamically
  from the center ID, recall count, region, and OpenAPI endpoint. Remote names,
  descriptions, and capabilities come from the returned Agent Cards.
- **Code-package deployment**: upload a ZIP project from the add-Agent menu,
  inspect or edit its files in the existing code browser, then choose the
  region and public/VPC network before deploying it to AgentKit. The package
  must contain a root `app.py`; Studio removes a single wrapping directory,
  rejects unsafe paths, and shows upload, image build, Runtime creation, and
  service publishing as separate deployment stages.
- **Built-in code execution**: selecting `代码执行` adds VeADK's `run_code`
  tool to generated Python and reveals the required `AGENTKIT_TOOL_ID` sandbox
  field and optional `AGENTKIT_TOOL_REGION` field below the built-in tool list.
  The region defaults to `cn-beijing`. Studio applies both fields to local debug
  runs and deployments, and generated `.env.example` contains both.
- **Auth**: optional VeIdentity SSO, or a local username for dev.
- **Agent-driven UI (A2UI)**: when an agent emits A2UI, it renders as native
  components (one feature among the above — not required).

Changing the Feishu channel on the deployment page regenerates the project so
`app.py`, the `extensions` dependency, and the runtime environment variables
stay aligned before deployment.

Insight Sandbox requires server-side `VOLCENGINE_ACCESS_KEY`,
`VOLCENGINE_SECRET_KEY`, `MODEL_AGENT_API_KEY`, and `MODEL_AGENT_NAME` values.
These credentials and the AgentKit session endpoint remain on the Studio server
and are never returned to the browser.

Temporary Sandbox state is process-local. Run Studio with one server worker, or
configure session affinity so create, message, and delete requests from the same
browser reach the same instance.

## Development specification

All frontend changes must follow [`SPEC.md`](SPEC.md). It defines the required
code, visual, interaction, security, code-generation, and testing conventions
for VeADK Studio, including these non-negotiable rules:

- New or updated product icons must be repository-owned, hand-drawn SVG React
  components. Do not add generic icon-library, emoji, or remote-icon usage.
- Reuse the existing semantic color tokens, restrained enterprise-workbench
  visual language, component inventory, typography and control-size scale,
  bounded scrolling regions, and accessible interaction states.
- Feature configuration must remain explicit in its domain section and runtime
  environment summary; secrets must never enter generated source, browser
  persistence, logs, documentation, or committed files.
- Run the tests, production build, documentation checks, and secret scan required
  by the specification before submitting a pull request.

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

The Vite development server proxies the ADK API routes, including the
`/dev/apps/.../debug/trace` session-trace endpoint, to the backend on port 8000.

## Branding

Set a custom title (up to six characters) and a local or remote image logo when
starting Studio. The same logo is used in the sidebar, login page, and browser
favicon; the title is also used as the browser page title.

```bash
veadk studio --site-title 火山助手 --site-logo ./logo.png
veadk studio --site-title 火山助手 --site-logo https://example.com/logo.webp
```

Supported logo formats are PNG, JPEG, GIF, WebP, AVIF, and ICO, up to 5 MB.
`VEADK_SITE_TITLE` and `VEADK_SITE_LOGO` provide equivalent environment-variable
configuration. `veadk studio deploy` accepts the same flags and copies either a
local image or a downloaded network image into the VeFaaS deployment package.

## In-app Studio updates

Studio deployments use the `veadk-studio` TOS bucket in the deployment region
as their immutable release channel by default, so administrators can update the
frontend and Python backend together from the navbar without extra options:

```bash
veadk studio deploy \
  --user-pool-id <pool-id> \
  --allowed-client-id <client-id> \
  --vefaas-app-name <app-name>
```

Use `--studio-update-bucket`, `--studio-update-region`, and
`--studio-update-prefix` (or their `VEADK_STUDIO_UPDATE_*` environment
variables) to override the default release channel.

Studio checks `latest.json` every three minutes and lists newer releases with
their changelog and Git SHA. An accepted update verifies the selected complete
Bundle, replaces the current Function code, and releases the existing
Application without changing its URL or SSO configuration.

When an update fails, the administrator dialog shows the failed stage, a
searchable error ID, the complete diagnostic timeline and exception chain, and
a direct link to the deployed Function in the VeFaaS console. The log can be
copied in full for support, and retrying starts a fresh diagnostic record.

`.github/workflows/publish-studio-release.yaml` runs only when it is manually
dispatched on `main`. Enter the user-facing changelog when starting the
workflow. GitHub builds the frontend and verifies the fixed offline wheels for
the exact checkout, uploads the prepared source through a short-lived job-bound
URL, and calls the API-key-protected release server. The server builds and
publishes the immutable Bundle and Manifest before replacing `releases.json`
and `latest.json`. Configure only
`STUDIO_RELEASE_SERVER_URL` and `STUDIO_RELEASE_SERVER_API_KEY` as GitHub
Secrets; GitHub receives no TOS credentials.

The Release Server runtime and deployment assets are isolated from the public
Python package under `frontend/service/studio_release_server`. After changing
the service, deploy it from the repository root:

```bash
frontend/service/studio_release_server/deploy.sh
```

The script updates the existing VeFaaS Function, verifies `/readyz`, rotates
the API key, and updates the two GitHub Secrets. It requires
`VOLCENGINE_ACCESS_KEY`, `VOLCENGINE_SECRET_KEY`, and an authenticated GitHub
CLI session with permission to update Actions Secrets in the upstream repository.
It validates that permission before changing any cloud resources and verifies the
new revision with the rotated API key before updating the Secrets.

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

Identity and provider discovery failures are shown as retryable errors. The UI
only offers local username login after `/web/auth-config` successfully returns
an empty provider list; network and gateway failures never silently change the
authentication mode.

Non-streaming frontend API requests use a 30-second deadline, while file
transfers use 120 seconds. Chat, debug, and deployment progress streams remain
open until the server finishes or the caller explicitly cancels them.

`veadk studio deploy` keeps the VeIdentity login page enabled and enables the
client's skip-consent setting when it registers the deployed callback URL. This
avoids presenting a second authorization confirmation after login.

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

### Skill creation mode

Skill creation uses `doubao-seed-2-0-pro-260215` and
`deepseek-v4-flash-260425` through Ark Responses. The real Ark API key is kept
by AgentKit credential hosting; Studio and the two isolated Sandbox sessions
receive only its revocable gateway ticket. Credentials are never returned to
the browser or copied into per-job Session variables. Studio also rejects
non-HTTPS or non-Volcengine credential relay URLs. Skill creation is limited
to Studio developers and admins.

After submission, Studio opens both candidate conversations immediately. Each
conversation independently renders public reasoning summaries, tool calls, and
assistant messages returned by the generator. Private chain-of-thought and
credentials never enter the UI. Completed candidates still support preview,
ZIP download, and AgentKit publish.

Configure separate ready AgentKit Tools for Codex, OpenClaw, Hermes, and Skill
creation before starting the server. The Tool IDs are intentionally server-only
and cannot be supplied by the browser:

```bash
export SANDBOX_CHAT_CODEX=<chat-code-env-tool-id>
export SANDBOX_CHAT_OPENCLAW=<openclaw-env-tool-id>
export SANDBOX_CHAT_HERMES=<hermes-env-tool-id>
export SANDBOX_SKILL_CREATOR=<skill-code-env-tool-id>
veadk frontend --agents-dir examples
```

Publishing a generated Skill uses TOS and the AgentKit Skills API. Set
`VEADK_SKILL_CREATOR_TOS_BUCKET`, `VEADK_SKILL_CREATOR_TOS_PREFIX`, and
`VEADK_SKILL_CREATOR_PROJECT_NAME` only when their defaults are unsuitable.
Each candidate session expires after 30 minutes and is deleted immediately when
a job is discarded. Job state lives in Sandbox rather than frontend-process
memory, so polling and downloads continue to work when FaaS requests reach a
different instance.

For local Studio, run the AgentKit `credential-hosting` command and bind its
result to both CodeEnv Tools. A cloud deployment creates both Tools in parallel
when their IDs are omitted. Alternatively, select existing Tools with
`--sandbox-chat-codex-tool-id`, `--sandbox-chat-openclaw-tool-id`,
`--sandbox-chat-hermes-tool-id`, and `--sandbox-skill-creator-tool-id`. The
deploy command obtains the Ark key with the deployer's Volcengine credentials,
stores it through AgentKit credential hosting, and binds only the returned
ticket and relay URL to the Tools:

```bash
veadk studio deploy \
  --user-pool-id <pool-id> \
  --allowed-client-id <client-id> \
  --vefaas-app-name <app-name>
```

## Agent naming

Studio validates every root and nested Agent name against Google ADK rules.
Names must start with an ASCII letter or underscore, may then contain ASCII
letters, digits, and underscores, cannot be `user`, and must be unique in the
Agent tree.

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
