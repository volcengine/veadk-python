# Studio MPA creation

[中文版](README.zh.md)

- Component ID: `studio-mpa-creation`
- Status: active
- Revised: 2026-09-20
- Design and evidence: [Studio MPA creation](../../prd-spec/features/mpa-agent-oneclick-provision/2026-09-20-studio-mpa-creation.md)
- Owned code: `veadk/integrations/mpa/managed/`, `frontend/server/mpa_creation.py`, `frontend/src/adk/mpaCreation.ts`, `frontend/src/ui/mpa-create/`; CLI and directory integration.
- Tests: `tests/integrations/mpa_managed/`, `frontend/tests/mpaCreation.test.tsx`.
- Dependencies: [legacy provisioning](../mpa-runtime-provisioning/README.md), [Studio MPA control plane](../studio-mpa-control-plane/README.md), existing AgentKit/Volcengine SDK, SQLAlchemy/asyncpg, SQLite, MPA image.
- Operator guide: [Managed MPA creation](../../veadk/integrations/mpa/managed/README.md).

## Responsibility and boundaries

VeADK owns managed YAML parsing, cloud/database orchestration, authorized durable creation tasks and the MPA directory dialog. No external source checkout is required. Shared registry/bootstrap contracts remain interoperable with the MPA image. Legacy `veadk mpa create` remains separate and unchanged. No model execution, channel routing, PostgreSQL instance provisioning or IAM policy management is added.

## Contracts

- **CON-1 — configuration:** The server chooses `VEADK_MPA_CREATE_CONFIG` (default `mpa-create.config.yaml`). `managed.version: 1` accepts kebab/snake aliases and rejects unknown managed keys. One profile serves one matching `cn-*` region. `from-runtime` and `template-file` are mutually exclusive; otherwise flat image/model/PG fields supply the template. `database-admin-url-env` and `shared-database-url-env` resolve PostgreSQL URLs server-side. Files/templates are limited to 256 KiB. HTTP clients cannot choose paths, commands, accounts or credentials. Configuration checks are local; they do not prove live access.
- **CON-2 — preparation:** Operators supply PostgreSQL instance/registry/login/owner, IAM roles, images, model access and network connectivity. Verify cloud account and database permissions before preparing account VPC/subnet, APIG/IM Gateway, worker, isolated business database, Skill Space and Runtime. Explicit APIG adoption requires a configured matching VPC. Never assume a newly created VPC reaches private PostgreSQL. Release account locks before waiting for application readiness.
- **CON-3 — identity:** Durable identity is verified account + region + stable agent ID. Native ownership markers, hashes, client tokens and session advisory locks govern reuse. Reject unrelated same-name resources and conflicting unfinished configuration. Persist `studio_owner` in the native deployment record; other owners and preexisting records without this owner cannot take over implicitly. CLI uses owner `cli`; Studio uses the hash of its authorized principal.
- **CON-4 — initialization:** Use real Runtime metadata and shared APIG bootstrap, not legacy placeholder endpoint seeding. Require public/private networking, KeyAuth, MPA tags, bound worker/Skill Space and metadata/IM startup. Reference Runtime templates remove source identity, channel credentials, Skill Space and worker identity. Success requires platform Ready and application `/readiness`.
- **CON-5 — authorization:** All four routes invoke Studio agent-management authorization before configuration/state access. Authenticated ordinary users cannot create; local development retains existing `local` principal semantics. Lookup/cancel is owner-scoped. Duplicate owner/request IDs reuse the task; altered inputs return 409. At most four active tasks globally and one per owner.
- **CON-6 — lifecycle:** States are `running`, `cancelling`, `succeeded`, `failed`, `cancelled`. Start/resume enters `running`; explicit cancellation enters `cancelling`, then `cancelled`; timeout/failure enters `failed`. Successful tasks do not rerun. Stages are `queued`, `checking`, `network`, `gateway`, `worker`, `database`, `skills`, `deploying`, `verifying`; stage is the last observed progress, not a second state machine. Dead supervisors are reconciled on task lookup/start. Recovery retains the original request and agent ID.
- **CON-7 — cancellation:** Run a fixed child module using the current VeADK interpreter. Cancel, deadline or server shutdown terminates the child, waits up to 3 seconds, then kills/reaps it before reporting terminal state. Default deadline is 1800 seconds (60–7200). Persistent cloud resources are retained, including unknown in-flight outcomes. Cancellation is not rollback; retry uses registered intent/token. This flow creates no temporary debugging Runtime to delete.
- **CON-8 — data/security:** `.adk/mpa-creation.sqlite3` (server override `VEADK_MPA_TASK_DB`) persists hashed owner, nonsecret input, state/stage, safe results and supervisor PID, with mode 0600. Connections close after each operation. No automatic history expiration. Native PostgreSQL tables remain `mpa_account_network`, `mpa_account_apig`, `mpa_agent_deployment`; require direct/session pooling. STS files are reread; Runtime/network/APIG/worker share account-verified credentials. Protocol messages are bounded to 16 KiB and allowlisted. Never forward raw child output, SDK errors, environment dumps, database URLs or Runtime keys.
- **CON-9 — UI:** The MPA filter on Volcengine shows a create card with agent-management permission, including empty lists. The dialog displays fixed region, generated/editable ID, description and resource plan. Persist request identity before POST; lock submitted inputs to make lost-response retry safe. Abort polling on unmount, ignore late responses, preserve server work and recover from session storage on reopen. Refresh the original region after success. Reuse localized BaseUI/Studio components, keyboard/IME behavior and semantic theme tokens. `ModalLayout.footer` is an optional React node: omitted preserves existing actions, `null` omits the footer; existing callers are unchanged.

## HTTP contract

| Method and path | Response |
| --- | --- |
| `GET /web/mpa-creation/config?region=...` | 200 `{configured,region,error?}`; success also returns safe `source`, resource names, `checks:["configuration"]`, `requiresLiveChecks:true` |
| `POST /web/mpa-creation/tasks` | 202 task snapshot; starts or resumes |
| `GET /web/mpa-creation/tasks/{id}` | 200 owner-scoped task snapshot |
| `POST /web/mpa-creation/tasks/{id}/cancel` | 200 task snapshot; terminal tasks unchanged |

POST body (maximum 8192 bytes, unknown fields rejected):

```json
{"requestId":"11111111-1111-4111-8111-111111111111","agentId":"customer-service","description":"Customer service","region":"cn-beijing"}
```

`requestId` is a UUID; `agentId` matches `[a-z0-9][a-z0-9_-]{0,63}`; `description` defaults to empty, maximum 512 characters; region matches `cn-[a-z]+`, maximum 32 characters. A snapshot contains those fields plus `taskId`, `state`, `stage`, `result`, `error`. Successful result has exactly `runtime_id`, `skill_space_id`, `gateway_id`, `agent_id`, `region`, `state:"ready"`; all are bounded identifiers. No endpoint or credentials are returned. Errors include safe codes `creationFailed`, `timeout`, `interrupted`, `cancelled`. HTTP errors: 400 configuration, 413 body size, 422 invalid input, 409 conflict/capacity, 404 unknown/other-owner task; authorization uses existing Studio status codes. Unsupported provider configuration is unavailable.

## Compatibility, verification and change record

The approved 2026-09-20 migration owns cloud provisioning code and tests in VeADK. No external deployment command or dependency on a provider checkout is supported. API/image/shared-table compatibility changes require review of this contract. Existing CLI behavior and unrelated SDK/harness contracts remain unchanged. Flat-mode supported fields and retry instructions are defined in the operator guide.

CON-1–4 map to configuration/service/network/gateway/worker/database/Runtime tests. CON-5–8 map to route/task tests (ownership, duplicates, lost results, dead supervisors, timeout/reaping, redaction). CON-9 maps to dialog tests, existing directory tests and real-browser checks. Run `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py`, frontend test/build/asset gates, changed-file Ruff/Pyright and isolated browser checks. Actual outcomes and remaining baseline/environment limitations are recorded in the design. Simulated tests and a browser with fake APIs do not prove live cloud deployment; cloud smoke is separately authorized.

Configuration failures distinguish absent/unreadable profile files, invalid YAML and absent/invalid Runtime JSON templates. Responses identify the relevant setting (`VEADK_MPA_CREATE_CONFIG` or `managed.template-file`) without returning private paths, file contents or parser exception details. This preserves CON-1/CON-8 and the existing HTTP shape.

Worker discovery follows the provider's `NextToken` cursor with `MaxResults=100`; page length does not determine completion. Repeated cursors and more than 1,000 pages fail explicitly. Matching ToolIds are deduplicated across overlapping pages, while distinct same-name resources remain ownership collisions. Failed or incomplete discovery must never be treated as resource absence (CON-2/CON-3).

CON-3 naming: fresh managed Runtime `Name` equals `MPA_AGENT_ID`. Existing registered Runtime names are preserved. A pending legacy create without a returned Runtime ID retains its hashed name only when the complete legacy payload matches the persisted request hash, preserving ClientToken retry semantics. Other input changes remain conflicts. Runtime IDs and database/worker/Skill Space identities are unchanged. The current UpdateRuntime API does not expose Name, so this does not rename existing cloud instances.
