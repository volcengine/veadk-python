# VeADK Web

A React web UI for VeADK / Google ADK agents. It talks to the standard ADK API
server that `veadk frontend` launches — no separate backend.

## Features

- **Streaming chat** over the ADK `/run_sse` event stream. While an Agent is
  generating, the composer exposes a stop control that cancels only the active
  response, preserves content already received, and immediately enables the
  next turn in the same session.
- **Context usage meter** beside Send uses provider-specific model windows and
  a 100-cell hover/focus map for estimated system/tool overhead, input/history,
  output/reasoning, and remaining capacity. System/tool usage is explicitly
  marked as an estimate because ADK usage metadata does not report it separately.
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
- **Intelligent Agent development**: describe the intended VeADK Agent once and
  receive immediate, cancellable preparation feedback before the development
  conversation opens. Studio then automatically runs intent gating,
  implementation, local checks, a temporary cloud deployment, acceptance calls,
  log inspection, and cleanup.
  Public Codex reasoning updates and Assistant replies use the normal
  conversation renderer; credentials, raw Sandbox paths, and internal commands
  stay hidden. Each build appears in the shared conversation history for the
  lifetime of its remote development environment (up to eight hours); reopening
  it restores the latest conversation and current source-delivery card.
  Navigating away from an active build requires confirmation and stops that
  build before leaving, while the conversation remains available until expiry.
  Stopping preserves received output and blocks the next submission until
  cleanup finishes. Users can inspect generated text files and download the
  complete ZIP (including binary assets) as soon as the source is ready.
  Each completed build or optimization is also saved as an immutable project
  version in the private Studio TOS bucket. Users can reopen any saved version,
  view, download, deploy, delete, or restore it into a new Sandbox for another
  intent-driven iteration after the original Sandbox expires.
  Deployable source can be sent to Runtime manually; an incomplete verification
  report requires an explicit confirmation. No separate “start verification”
  action is required.
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
  explicit deletion. Persistence is enabled by default through a snapshot Tool;
  clearing it creates an eight-hour transient Session and shows an expiry
  warning. Codex streams reasoning, tool activity, and replies into the normal
  conversation renderer, while its sidebar history can resume or remove
  standard Codex App Server threads. Leaving the conversation only
  disconnects it, so the Agent remains available until the user deletes it.
  OpenClaw and Hermes expose their main interface and Terminal through Studio.
- **Codex conversation handoff** creates a temporary cloud Sandbox, restores
  the current Git worktree, injects only completed user-visible user and
  assistant messages into the cloud Thread, then starts one new turn with
  `继续` or the user's explicit cloud task. System/developer prompts, reasoning,
  tool logs, local runtime databases, and SSH keys are never transferred.
- **System information**: open a full page from the account menu to inspect the
  Studio version, configured Sandbox Tool IDs (with snapshot Tools badged), and
  available Identity user pools. Resource identifiers remain read-only and
  require Agent-management access.
- **AgentKit Skill center**: browse Skill Spaces and their skills with
  server-side pagination by region, then inspect the selected Skill content.
- **Library hub**: manage Skills, user-owned AgentKit knowledge bases, and chat
  artifacts from one sidebar entry. Knowledge documents support verified
  JPG/PNG, PDF/PPTX/DOCX/XLSX/TXT uploads and public webpage imports. Studio
  fetches webpages server-side with SSRF protections, extracts the main content
  as Markdown, and shows a safe rendered preview before any data is created.
  Only an explicit confirmation stores the previewed Markdown through the
  existing private TOS-to-Viking flow; cancelling or a preview failure leaves
  the knowledge base unchanged. Imported webpages are named automatically from
  the page title, with the hostname as a fallback.
  AgentKit knowledge names use its native identifier rules: 1-48 characters,
  starting with a letter and containing only letters, numbers, or underscores.
  Descriptions are limited to 80 characters so the signed owner marker remains
  within AgentKit's 200-character provider limit.
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
  before writing feedback items. On finalized Volcengine Runtime replies, users
  can also select a text fragment and add an inline annotation; Studio preserves
  the selected fragment in the feedback comment and saves the reply as a Bad
  case evaluation sample. Failed saves keep the annotation open for retry.
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
  example for each one. While a deployment is running, the detail page keeps the
  Agent heading and a scrollable deployment panel visible, then reloads the
  normal detail tabs after the Runtime connects. Runtime API Keys stay masked as
  `****` and are fetched only after the user explicitly reveals them; examples
  always use placeholders
  instead of credentials. Long descriptions, names, component summaries, IDs,
  and environment values stay inside the scrollable panel.
- **Custom-agent workbench**: configure an agent with a rich Markdown
  system-prompt editor (including heading and list shortcuts), choose Harness
  Sidecar optimizations, then debug with expandable, copyable runner error
  details and per-result Trace inspection. The workbench order is `架构` →
  `优化` → `调试` → `环境` → `发布`. On the optimization page, `自定义`
  appears first and starts with no components, while `运维场景` applies the
  `ops` component combination. Component checkboxes remain editable and an empty
  selection keeps Sidecar disabled. The Environment step can optionally add the
  official Lark CLI, GitHub CLI, and Pandoc to the cloud runtime. Selecting a
  tool generates an inspectable provider-specific Dockerfile with pinned
  releases, amd64/arm64 assets, and SHA-256 verification. Advanced configuration
  can edit that Dockerfile directly or restore the generated version; selecting
  no tool and leaving the Dockerfile unchanged keeps AgentKit's default image
  build. Credentials are never written into the generated Dockerfile. Published
  Agent details display the saved Sidecar scenario and selected components as
  read-only information. In-progress drafts are stored only in the current
  browser and scoped
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
  global task list keeps Runtime, region, and progress visible across page
  switches and keeps failed or cancelled drafts available for editing. For a
  new deployment, the default Runtime name is a deterministic normalization of
  the Root Agent name, without a random suffix. Runtime names must contain
  4–64 letters, digits, hyphens (`-`), or underscores (`_`). The name can be
  changed before the first deployment, but it is read-only when updating an
  existing Runtime. Successful releases clear their drafts before Studio waits
  up to 60 seconds for the Runtime endpoint to become reachable. Remote
  topology and trace requests use the selected Runtime endpoint. The Remote
  Agent type is available only for child Agents;
  its generated internal proxy mounts AgentKit A2A center agents dynamically
  from the center ID, recall count, region, and OpenAPI endpoint. Remote names,
  descriptions, and capabilities come from the returned Agent Cards.
- **Code-package deployment**: upload a ZIP project from the add-Agent menu,
  inspect or edit its files in the existing code browser, then choose the
  region and public/VPC network before deploying it to AgentKit. The package
  uses `agentkit.yaml` `common.entry_point` when declared and otherwise keeps
  root `app.py` as the compatible default. Studio removes a single wrapping
  directory, rejects unsafe paths, and shows upload, image build, Runtime
  creation, and service publishing as separate deployment stages.
- **Existing-project migration**: upload one local ZIP of at most 50 MiB from
  the add-Agent menu. Studio creates one user-owned Dev Sandbox Session with a
  one-hour TTL, then asks the preinstalled Codex to perform read-only framework,
  entry-point, and migration-boundary analysis. Migration starts only after the
  user confirms the framework, entry point, and open questions. Structured
  frameworks run the preinstalled `ak migrate`; Dify and Any projects run
  `ak migrate --execution in-place` with Codex in the same Session. State,
  logs, and artifacts remain only under
  `/home/gem/.studio/migration/v1/` in that Session. Preview, download, and
  Runtime deployment stop when the Session expires. Runtime deployment resolves
  and verifies the owned Session artifact on the server instead of trusting
  browser-provided files or entry points. AgentKit CLI `0.51.1` is only the
  current baseline; these CLI changes must be released as a new version. The
  Dev Sandbox image must pin that migration-capable release and its SHA256 at
  image build time.
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

## Studio BFF reverse tools

Studio can expose local or intranet-only tools to a compatible AgentKit Runtime
without giving the Studio BFF a public address. For each remote `run_sse`
request, the BFF first tries an outbound WSS connection to
`/harness/studio-channel/v1`. If the public gateway doesn't support WebSocket
Upgrade, it automatically falls back to a streaming HTTP/SSE downlink plus HTTP
tool-result posts. It publishes the current tool catalog, executes `tool.call`
messages locally, and returns `tool.result` without exposing a BFF endpoint. The
Runtime sees ordinary tools, but receives neither the executor implementation nor
its credentials. The HTTP fallback currently requires exactly one Runtime
instance so its stream and result posts reach the same process.

Build the Runtime app with
`create_agentkit_app(..., enable_studio_tools=True)` to mount one generic
`StudioExternalToolset`. It contains no concrete executor and is hidden from
Agent introspection. During a Studio-channel run, an async-local immutable
snapshot supplies only the tools selected for that run; ordinary `/run_sse`
requests see an empty snapshot. With the option disabled (the default), the
Runtime advertises `enabled=false` and does not mount the Toolset or Tool Channel
execution endpoints. The enabled host is the stable Runtime compatibility layer
for future BFF-owned tools, so a new plan or goal tool does not need a matching
executor in the deployed Agent.

For a compatible remote Runtime, the existing Agent information rail exposes
**在此对话中添加 Studio 工具** below the Agent's static tools. New chats start
with every Studio tool disabled; an existing session keeps its selection in the
current browser process between turns. The browser sends an explicit
`platform_tools` list on each Runtime run, and an empty or omitted list uses the
ordinary `/run_sse` path. The BFF validates the submitted IDs and freezes an
immutable catalog-and-executor snapshot for that run, so simultaneous users and
sessions cannot add tools to one another. Tool code and credentials stay in the
BFF, while selected tool results are returned to the cloud Agent through the
reverse channel.

Studio always registers the canonical functions from
`veadk/tools/builtin_tools` in its BFF catalog; the implementation files and
their `builtin:` bindings remain unchanged. The BFF supplies the ADK
`ToolContext`, keeps state isolated by Runtime/app/user/session, and publishes
generated ADK artifacts through Studio media storage so downloads remain
available after execution moves out of Runtime.

Studio-owned tools that don't belong in VeADK's built-in catalog live in
`frontend/server/studio_tools/extensions`. Studio discovers every public Python
module in that directory at startup and calls its `register_tools(registry)`
function. Adding one of these tools requires no environment variable or Runtime
change; restart Studio after changing the module. `current_time.py` is the
minimal working example for future Studio-only tools.

Studio forwards the Runtime API-key or Identity authorization on capability
discovery, WebSocket handshakes, and HTTP/SSE fallback requests; the AgentKit
ingress remains the authentication boundary for these channels.

A deployable Runtime agent and launch scripts live in the
[local reverse-tool example](../.agents/local/studio/A_BFF_tool_for_runtime/examples/README.md).

## Studio BFF dynamic routes

A compatible Runtime can also expose Studio-owned HTTP routes without loading
their Python handlers. Build the Runtime app with
`create_agentkit_app(..., enable_studio_routes=True)` and start Studio with
`VEADK_STUDIO_ROUTE_CHANNEL=skill-catalog` (`demo` remains a compatibility
alias). After Studio connects the Runtime, the BFF keeps a separate persistent
reverse-route channel and publishes these Studio-owned, read-only routes:

- `GET /harness/skills/findskill`
- `GET /harness/skills/spaces`
- `GET /harness/skills/spaces/{space_id}/skills`

Runtimes without the dynamic-route opt-in keep their native Skill catalog
handlers. Opted-in Runtimes leave those three read-only query handlers to Studio.
The segment-template request contract is protocol v2, so a Runtime using the
older route-channel protocol must be updated once before accepting this catalog.

Requests still enter through the Runtime URL. Its dynamic dispatcher emits
`route.call`, the local BFF executes the handler, and `route.result` becomes the
Runtime HTTP response. WSS is preferred; unsupported gateways automatically use
a long-lived HTTP/SSE downlink plus HTTP result posts. The current implementation
is currently single-instance: both the persistent stream and arbitrary route
requests must reach the same Runtime process. A disconnected BFF leaves known
Studio-owned routes unavailable with HTTP 503; Agent runs remain available.

Local Studio reads transient and snapshot Tool IDs from
`SANDBOX_CHAT_CODEX`/`SANDBOX_CHAT_CODEX_SNAPSHOT`,
`SANDBOX_CHAT_OPENCLAW`/`SANDBOX_CHAT_OPENCLAW_SNAPSHOT`, and
`SANDBOX_CHAT_HERMES`/`SANDBOX_CHAT_HERMES_SNAPSHOT`. Cloud deployment creates
all six Tools when their IDs are omitted; the three snapshot Tool names end in
`_snapshot`. The matching `--sandbox-chat-*-tool-id` and
`--sandbox-chat-*-snapshot-tool-id` options select existing Tools instead.

## Mermaid diagrams in model messages

Agents can render diagrams in conversation replies by returning standard
Markdown fenced code blocks with the `mermaid` language tag. No tool call or
custom JSON envelope is required. Studio uses the official Mermaid renderer,
so the same contract covers flowcharts, line charts, pie charts, and the other
diagram types supported by the installed Mermaid version.

````markdown
```mermaid
flowchart LR
  Request --> Agent --> Response
```

```mermaid
xychart-beta
  title "Requests"
  x-axis [Jan, Feb, Mar]
  y-axis "Count" 0 --> 100
  line [24, 58, 91]
```

```mermaid
pie showData
  title Traffic sources
  "Direct" : 42
  "Search" : 58
```
````

Studio keeps the Mermaid source visible while a response is streaming and
renders it after the message completes. Users can switch each diagram between
its preview and original Mermaid code. If a definition is invalid, Studio shows
an error while keeping the original source available in the code view.

For interactive data charts, agents can return an ECharts option as JSON or
JSON5 in an `echarts` fenced block. The singular `echart` tag and case variants
such as `ECharts` are accepted as aliases. The common `option = { ... };`
wrapper is also accepted. ECharts linear and radial gradient constructors are
converted to their equivalent data objects without execution. Other functions
and executable JavaScript are not part of this data-only contract. Tooltip
content is forced to ECharts rich-text rendering.

````markdown
```echarts
{
  "tooltip": { "trigger": "axis" },
  "legend": { "data": ["Requests"] },
  "xAxis": { "type": "category", "data": ["Jan", "Feb", "Mar"] },
  "yAxis": { "type": "value" },
  "series": [{ "name": "Requests", "type": "line", "data": [24, 58, 91] }]
}
```
````

## Development specification

All frontend changes must follow [`SPEC.md`](SPEC.md). It defines the required
code, visual, interaction, security, code-generation, and testing conventions
for AgentKit Studio, including these non-negotiable rules:

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

## Environment image builds

Studio 的“工作区”用于组织一组可复用环境。一个工作区可以包含多个环境，同一个环境也可以加入多个工作区；删除工作区只会删除组合关系，不会删除环境。侧边栏只展示“工作区”入口，工作区页面内可在“工作区”和“环境”两个视图之间切换。Agent 的创建与部署仍直接选择具体环境及其构建版本。

工作区元数据保存在与环境相同的 Studio TOS 桶中，路径为 `veadk-studio/v1/workspaces/<owner>/<workspace-id>/summary.json`。接口包括 `/web/workspaces` CRUD，以及 `/web/workspaces/{workspaceId}/environments/{environmentId}` 的添加和移除操作。被工作区引用的环境不能直接删除。

The Studio `环境` page stores each environment definition, generated Dockerfile,
build version, log metadata, and resulting image reference in the private Studio
TOS bucket. Creating or saving an environment starts an asynchronous
CodePipeline build and pushes the resulting image to Container Registry.
Volcengine builds use the Aliyun PyPI mirror, Huawei Cloud Python source mirror,
and npmmirror for Playwright browsers; BytePlus builds use the corresponding
official sources. Cross-version Python combinations are compiled from pinned
source releases instead of depending on GitHub-hosted binaries.

By default, Studio creates or reuses managed CodePipeline and Container Registry
resources on the first environment build. With the account-stable default TOS
bucket, Studio reuses the account's `agentkit-cli-<account-id>` CR instance and
creates the `runtime-environments/base-images` repository inside it. Existing
resources can be selected at deployment time with flags only:

```bash
veadk studio deploy \
  --vefaas-app-name <app-name> \
  --environment-cp-workspace <workspace-id-or-name> \
  --environment-cr-repository <registry/namespace/repository>
```

Either flag can be supplied independently. The System Information page shows
the resolved workspace, pipeline, repository, ownership mode, and provider
console links. These values are resource identifiers, not credentials.

## In-app Studio updates

Studio deployments use the centrally maintained `veadk-studio` TOS bucket in
`cn-beijing` as their immutable release channel, regardless of the deployment
region. Administrators can update the frontend and Python backend together from
the navbar without extra options:

```bash
veadk studio deploy \
  --vefaas-app-name <app-name>
```

When `--user-pool-id` and `--allowed-client-id` are omitted, deployment creates
or reuses them in the selected `--region` and prints the resolved IDs. Pass both
options to keep using existing Identity resources.

After automatic provisioning, the success summary lists every Sandbox type and
Tool ID, the private Studio TOS address, and the resolved Identity user pool and
client IDs. It also links to the matching Volcengine or BytePlus Identity
console. Password sign-in remains disabled by default for security; configure
an SSO identity provider before inviting users to the deployed Studio. Pass
`--allow-dangerous-login` to explicitly enable local password, passwordless,
sign-up, recovery, and unconfirmed-user login flows on a Studio-managed user
pool. When `--user-pool-id` is provided, deployment preserves that existing
user pool's login settings regardless of this flag.

Studio checks `latest.json` every three minutes and lists newer releases with
their changelog and Git SHA. An accepted update verifies the selected complete
Bundle, replaces the current Function code, and releases the existing
Application without changing its URL or SSO configuration.

When an update fails, the administrator dialog shows the failed stage, a
searchable error ID, the complete diagnostic timeline and exception chain, and
a direct link to the deployed Function in the VeFaaS console. The log can be
copied in full for support, and retrying starts a fresh diagnostic record.
Reading the VeFaaS release log is optional: when the Function role lacks
`vefaas:GetApplicationRevisionLog`, the update continues and the dialog links
to the matching provider IAM console so an administrator can grant access.

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

## Issue feedback

Assistant responses expose an issue-feedback action, and the sidebar provides a
platform feedback page. Both flows submit through `POST /web/issue-feedback`.
The Studio server redacts credentials, includes the selected Runtime ID and
available conversation/trace context, then posts anonymously to the matching
public Lark form. Runtime deployments enable APMPlus by default; remote feedback
queries APMPlus by Session ID on the server, while local feedback uses the
in-memory development trace endpoint. Trace lookup failures do not block the
feedback submission. Form records store their submission time in Beijing time.
This path does not require TOS credentials, a Lark application, or `lark-cli`.
A successful request returns `{ "submitted": true }`; the UI shows an accessible
success state instead of exposing an internal trace ID.

## Studio persistent storage

For a cloud deployment, Studio uses the deployment region and automatically
creates or reuses the private bucket `veadk-studio-<account-id>`. The stable
account-derived name makes repeated deployments idempotent. A bucket created in
one region cannot be recreated under the same name in another region; changing
the deployment region requires an explicitly configured bucket.

Administrators can override the automatic bucket by setting only its name; the
deployment region remains the storage region:

```bash
export VEADK_STUDIO_TOS_BUCKET=teststudio
```

The server derives the provider-specific endpoint, such as
`tos-cn-beijing.volces.com`, and never sends TOS credentials to the
browser. Local Studio uses the configured Volcengine or BytePlus AK/SK; VeFaaS
uses its IAM role credentials. Studio objects use the versioned, user-first
layout
`veadk-studio/v1/users/<encoded-user-id>/<namespace>/<scope>/<resource-id>/`.
Video reference assets currently use the `video/<asset-role>/<asset-id>/`
namespace and store `content` plus `metadata.json` below it.

Intelligent-development projects use
`intelligent-development/projects/<project-id>/versions/<version-id>/` below
the signed-in user's prefix. A version contains an immutable source ZIP,
validation report, and commit marker; the mutable project summary is only an
index. Viewing, downloading, and deploying a committed version do not depend on
the original Sandbox. TOS configuration, integrity, and availability failures
are returned as distinct errors and are never rendered as an empty project
list. If persistence fails after a Sandbox delivery is generated, the current
Sandbox delivery remains usable until that environment expires.

Local Studio still accepts `VEADK_STUDIO_TOS_BUCKET` together with
`VEADK_STUDIO_TOS_REGION`. When local storage is not configured,
persistent-storage-dependent controls are disabled and show
`管理员未配置持久化存储`; text-only features remain available. The older
`VEADK_VIDEO_TOS_*` and `DATABASE_TOS_*` settings remain a temporary
compatibility fallback.

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

### Skill Center

Studio developers and admins create and optimize Skills from the Skill Center.
Each candidate runs in an isolated session on the shared AgentKit Dev Sandbox,
streams its public activity, validates the generated files, and can then be
previewed, downloaded, or published to AgentKit. Model credentials remain on
the Tool and are never returned to the browser.

Local Studio reads the DevEnv Tool ID from `SANDBOX_DEV`. A cloud
deployment creates the Dev Sandbox automatically when the ID is omitted, or
uses the Tool supplied through `--sandbox-dev-tool-id`:

```bash
export SANDBOX_DEV=<dev-env-tool-id>
veadk studio --agents-dir examples
```

The new-session page shows `技能定制` only after this Dev Sandbox and its model
credential are confirmed usable. If the administrator has not configured a
usable Dev Sandbox, the mode is hidden rather than exposing an action that must
fail.

Each task has its own one-hour DevEnv session. Leaving a running task stops and
releases its session; task state remains in Sandbox so polling can continue
across frontend instances.

Deploy Studio with:

```bash
veadk studio deploy \
  --user-pool-id <pool-id> \
  --allowed-client-id <client-id> \
  --vefaas-app-name <app-name>
```

## Scheduled tasks

The `定时任务` workspace runs a fixed text prompt on a selected deployed Runtime
Agent. Each occurrence creates an independent Agent session. Schedules support
one-time, daily, weekly, and five-field Cron expressions with an IANA timezone.

Definitions, locks, execution history, and results live in the private Studio
TOS bucket under `veadk-studio/v1/users/{user_id}/cronjobs/{job_id}`. A derived
minute index lives under `veadk-studio/v1/scheduler/cronjobs/due/{yyyyMMddHHmm}`
so the scheduler never scans user namespaces.

`veadk studio deploy` creates or updates two stateless VeFaaS functions. A
scanner runs once per minute, copies the current due bucket into the durable
`scheduler/cronjobs/ready/` queue, persists queued runs, and advances each
schedule without waiting for Runtime execution. A separate asynchronous worker
drains ready entries, invokes Runtime, and writes terminal results. The scanner,
worker, and Studio BFF can therefore restart independently without losing work.

Duplicate timer deliveries are deduplicated with immutable run IDs and TOS
conditional writes; an ETag lock prevents concurrent executions of the same
task across Studio replicas or worker instances. Ready entries are deleted only
after a terminal result is persisted. The worker uses the function IAM role to
read the Runtime's current endpoint and version. It does not store user tokens
or AK/SK credentials.

Manual runs are persisted with a `queued` status and placed in the next minute's
due bucket, so they normally start within 60 seconds. This avoids losing a run
when the current minute has already been scanned. When Studio is started with
`veadk studio --vite`, the BFF starts independent local scan and execution
loops; no separate local scheduler process is required.

## Agent usage statistics

The `用量统计` tab on a deployed Agent records one invocation after a Studio
`run_sse` stream finishes successfully without an SSE error. Failed, cancelled,
direct API Server, and direct A2A calls are not counted. The tab shows total
invocations, unique signed-in users, per-user invocation counts, and each
user's latest successful invocation.

Usage is stored in the private Studio TOS bucket configured by
`VEADK_STUDIO_TOS_BUCKET` and `VEADK_STUDIO_TOS_REGION`. Cloud deployments
provision and inject this storage automatically. Each invocation is an
immutable object, so concurrent Studio instances do not overwrite a shared
counter. User identifiers are hashed in object keys and remain visible only in
the private object content and the authorized management API.

Only Studio administrators and developers who can access the Runtime may read
the user list. A storage failure never interrupts the Agent response; the tab
instead reports that usage statistics are temporarily unavailable.

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
