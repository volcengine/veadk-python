# Managed Agent Runtime

[中文版](README.zh.md)

Component ID: `managed-agent-runtime`. Status: `active`. Revised: 2026-10-10.
Related approved PRD: [managed-agents-upstream](../../prd-spec/features/managed-agents-upstream/2026-10-10-non-ui-migration.md), `FR-1`, `FR-2`, `FR-6`, `T-1`, `T-4`, `AC-1`, `AC-5`.
This component packages the self-hosted Managed Agents execution loop. It supplements existing runtime providers without changing their public contracts.

## Ownership and interfaces

`veadk/runtime/managed_agents/` owns worker polling, Work execution, event reconciliation, native tools and credential caches. `dispatcher.py` implements public SDK raw poll requests and generated ack/heartbeat/stop operations; no adjacent SDK checkout or private dispatcher import is required. Readiness is announced only after a valid successful poll. `veadk/integrations/mpa/session_client.py` owns the Anthropic Session transport; `session_resources.py` owns pinned Skill materialization and Session-bound MCP toolsets. Neither package imports example modules. The example delegates execution to the package and loads its own optional dotenv configuration.

`ManagedAgentsLoop` consumes pending `user.message` events and publishes model/tool events. `serve_managed_agent_worker` polls Work; `serve_claimed_managed_agent_work` executes an externally claimed Work. `SelfHostSandboxClient` preserves environment variable precedence and injected Work authentication. Examples retain old module imports as compatibility adapters.

## State and isolation

The frozen Session snapshot controls model, system instruction, enabled tools, permissions, Skills and MCP servers. Each Work gets local ADK bookkeeping and its own native tool context, Skill workspace and MCP toolsets. No shared Agent is mutated to apply a Session's bindings. Event IDs/cursors reconcile prior turns and avoid replaying completed inputs. Ark response IDs restore conversational context across worker replacement; worker bookkeeping always uses the local ADK backend and ignores legacy database settings.

## Tools, failures and cleanup

Native Anthropic tools execute directly. File tools preserve bytes/content and reject workspace escapes. Native bash can run commands permitted by its host OS; the file workspace is not an OS sandbox. Mutually untrusted Sessions require separate container/OS isolation; concurrent contexts in a shared worker do not provide shell isolation. Session IDs must use letters, numbers, underscores, dots or hyphens without leading/trailing dots; unsafe IDs are rejected rather than mapped to colliding directories. `always_ask` waits for matching permission responses; custom tools wait for correlated results. The default tool budget is 300 seconds and the outer action timeout must cover it. Cancellation, timeout, terminal Session status and transport failures remain visible. Failed model turns publish a sanitized error and propagate failure, retaining the input for recovery; replay does not treat `session.error` as successful completion. Worker shutdown drains dispatcher tasks and closes toolsets and native tool contexts. Failed or cancelled Skill downloads remove partial workspaces; completed Work removes its tracked download roots without following directory symlinks. Every toolset and native tool context is closed even if another close fails.

## Credentials and diagnostics

Runtime, Session-model and MCP credentials remain process-local and isolated by identity context. Session-model cache capacity is 2000 with a 3600-second TTL. Credentials are never written to environment variables or persistent storage. Explicit Work credentials take precedence over Runtime Identity. Identity errors exposed to callers are sanitized; authentication retries refresh credentials and honor shutdown. Optional event and model/poll diagnostics redact credential fields and avoid enabling broad HTTP logging.

## Verification

| Contract | Verification |
| --- | --- |
| `CON-1`: packaged imports and CLI require no example paths or credentials | package import and installed wheel/CLI checks |
| `CON-2`: valid poll readiness, lease fencing, Session FIFO and bounded shutdown | dispatcher HTTP and lifecycle tests |
| `CON-3`: canonical history and Ark continuation restore completed turns across workers | fresh-worker replay and actual SDK transport tests |
| `CON-4`: Session-local tools/resources and complete cleanup after failure or cancellation | native tool, MCP, Skill workspace and cancellation tests |
| `CON-5`: scoped authentication and sanitized diagnostics | credential refresh, isolation and error-redaction tests |
| `CON-6`: portable worker and claimed entry points | process supervision, local image build and isolated container checks |

Package tests cover event reconciliation, cross-worker response restoration, cancellation, authentication retries, real native file/bash tools, correlated custom/MCP results, local archive streaming and cleanup. Live cloud deployment is a separate acceptance step and is not implied by these tests.

## Official SDK compatibility

The dispatcher composes the unchanged official SDK. Environment polling uses
`work.with_raw_response.poll`; account model polling uses public `get` for the
VeADK-specific gateway endpoint. HTTP client hooks implement gateway Identity
rotation; generated APIs retain Work authentication. The image validates SDK
Python files against the installed wheel RECORD after hash-locked installation.
Tool cleanup preserves close/aclose and additive context-manager exit while
logging only exception types. Published internal Skill extraction and the tool
context-manager attribute remain version-sensitive, covered by integration tests.
See [official-SDK design](../../prd-spec/refactors/managed-agents-official-sdk/2026-10-10-official-sdk.md)
and [build guide](../../docker/managed-agents/README.md#official-sdk-extension-strategy).

`MANAGED_AGENT_MODEL_CREDENTIAL_SOURCE` defaults to `session`. Explicit
`environment` permits `MODEL_AGENT_API_KEY` only for non-AgentKit Sessions without
an `ark_api_key_provider`; explicit provider references and AgentKit always require
Session Identity. Unknown sources and missing local keys fail closed. Local
Kubernetes acceptance using this option does not verify cloud Runtime Identity.
