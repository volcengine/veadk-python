# Managed Agents Worker build

[中文版](README.zh.md)

This image runs the installed `veadk.runtime.managed_agents.worker` package and
the AgentKit health listener. The dispatcher and Session adapters ship inside
VeADK; no neighboring repository, private SDK wheel, frontend build, or cloud
deployment is required to build the image.

## Build and verify locally

From the repository root:

```bash
uv sync --extra dev --extra sandbox --extra extensions
uv run --extra dev --extra sandbox pytest tests/runtime/managed_agents tests/integrations/mpa
bash docker/managed-agents/build.sh veadk-managed-agents-worker:local
docker run --rm --entrypoint python veadk-managed-agents-worker:local \
  -m veadk.runtime.managed_agents.worker --help
```

The build script defaults to `--load`; publication requires an explicit
`--push` argument and a registry/tag selected by the operator. Building an image
does not update an AgentKit Runtime, Tool, Session, or Kubernetes Deployment.
`MANAGED_AGENTS_PLATFORM` overrides the default `linux/amd64` build platform.

## Dependency and SDK pitfalls

Older source images copied a wheel from
`examples/16_self_host_sandbox/.docker-dist/anthropic-*.whl`, built from an adjacent
SDK checkout, and imported `anthropic.lib.environments._dispatcher`. A normal
Anthropic 1.3.0 installation provides Managed Sessions and native tools but does
not provide that private dispatcher. An installed package could import successfully
yet fail to start a Worker. The new dispatcher uses generated Work APIs and the
existing account model-work polling protocol instead; the Docker build validates
its import and native-tool availability before the image is considered built.

Images default to `https://pypi.org/simple`. If an approved package mirror does
not contain every version in `uv.lock`, use a complete mirror through build args;
do not loosen pins, remove hashes, or regenerate the lock to hide missing packages:

```bash
PIP_INDEX_URL=https://packages.example.com/simple \
UV_DEFAULT_INDEX=https://packages.example.com/simple \
  bash docker/managed-agents/build.sh veadk-managed-agents-worker:local
```

Indexes are build inputs, not runtime environment variables. This helper accepts
unauthenticated mirror URLs and rejects user info, query strings and fragments
before invoking Docker. Authenticated mirrors require a separately configured
BuildKit secret integration; never put credentials in build arguments, image tags,
source, or logs. Frozen export preserves dependency hashes. The component uses
its own named, locked BuildKit cache rather than sharing an unrelated image
build's cache. This dedicated Worker image installs the sandbox extra. Feishu and
optional data integrations use a separate SDK installation with the extensions
extra; development and Codex packages are not included in the Worker image.

## Runtime configuration

Configure gateway/credential/identity settings through the platform's secret and
environment mechanisms. A minimal worker needs `ANTHROPIC_BASE_URL`, a Runtime
credential (`ANTHROPIC_ENVIRONMENT_KEY` or configured Runtime Identity), and its
Work scope. Account workers default to `MANAGED_AGENT_WORK_SCOPE=account` and
`MA_AGENT_LOOP_RUNTIME_TYPE=agentkit_runtime`; environment workers must set
`MANAGED_AGENT_WORK_SCOPE=environment` and `ANTHROPIC_ENVIRONMENT_ID` explicitly.
Session creation additionally requires a configured Agent ID. Session snapshots
remain authoritative for model, tools, Skills, MCP and credentials.

`MANAGED_AGENT_WORK_CONCURRENCY` defaults to 500 in the image. It counts Work
handlers, including waits, and does not enable simultaneous turns in one Session.
The worker ready file appears only after a valid successful Work poll, and is
removed while draining. HTTP health endpoints alone do not prove worker readiness.
The entry point supervises worker/listener together; failure of either stops both.

For an AgentKit Tool executing an already claimed Work, the image also retains
`/opt/gem/run.sh`. It selects `MANAGED_AGENT_ENTRYPOINT_MODE=claimed`, uses injected
Work/Session/lease configuration, and defaults tool execution to local inside the
Tool's isolation. The regular image command selects continuous worker mode.

The process runs as UID/GID 10001. Mount a writable `/workspace` and `/tmp` when
using a read-only filesystem. Native bash must execute within the deployment's OS
isolation; path-confined file tools do not provide a shell security sandbox.

The [Kubernetes example](k8s/worker.yaml) references an operator-created Secret;
replace the image placeholder before applying. No secret values or real deployment
identifiers are supplied. Kubernetes, AgentKit and live model acceptance require
separate deployment authorization and are not proven by local tests/builds.

## Official SDK extension strategy

The current image installs the unchanged official PyPI `anthropic==1.3.0` selected
by `uv.lock`; it does **not** install the historical adjacent custom wheel.
The locked SHA256 matches the [official release](https://pypi.org/project/anthropic/1.3.0/).
The installer validates artifact hashes, and `verify_anthropic_sdk.py` checks every
installed SDK Python file against wheel RECORD, rejecting changed, missing and
unrecorded files. RECORD checking is an integrity check, not an independent origin
proof if the wheel and its RECORD are both replaced; the lock hash supplies that boundary.

VeADK uses composition rather than subclassing or globally patching the SDK:

| Behavior | Implementation |
| --- | --- |
| environment Work poll | official `beta.environments.work.with_raw_response.poll`; inspect HTTP 204 before validating Work |
| account model Work poll | public `AsyncAnthropic.get` for `/v1/model-work/poll`, a VeADK gateway extension, not a Claude API endpoint |
| ack / heartbeat / stop and Session events | official generated SDK APIs |
| account/runtime routing headers | public `default_headers` / `extra_headers` |
| Runtime Identity rotation | public HTTP client request/response hooks; preserve Work-scoped Bearer alongside gateway identity |
| native tool execution | official `agent_toolset` factory and public `ToolError` |

The official SDK documents [raw responses, custom requests and HTTP clients](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python#advanced-usage).
Its `EnvironmentWorker` has no arbitrary VeADK handler callback; subclassing would
require overriding private execution methods. No SDK source files or methods are
replaced. The per-Work client is a copy with inherited auth cleared; setting its
public `api_key=None` is necessary because SDK 1.3.0 `copy(api_key=None)` inherits
the parent key.

Two SDK internals remain version-sensitive: `_skills._download_and_extract` is
shipped by the official package and preserves fail-fast Skill download semantics
(the public helper skips failures); the tool decorator's `_context_manager` is
read for additive cleanup. VeADK performs cleanup locally to avoid the SDK helper
logging raw exception text. Real SDK archive, tool, auth and dispatcher tests cover
these boundaries. A locked official SDK does not require a custom SDK fork.

For a local VKE Worker with no Session Identity reference, explicitly set
`MANAGED_AGENT_MODEL_CREDENTIAL_SOURCE=environment` and supply `MODEL_AGENT_API_KEY`
through a dedicated Kubernetes Secret. The default is `session`; AgentKit and any
Session with a provider reference always require Identity and never fall back.
This choice verifies configured model credentials, not cloud Identity delivery.
